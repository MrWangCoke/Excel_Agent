from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from excel_agent.cache.cache_manager import (
    build_file_fingerprint,
    build_group_folder_name,
    build_group_id,
    build_source_id,
    get_group_chunks_manifest_path,
    get_group_dedupe_report_path,
    get_group_deduped_messages_path,
    get_group_duplicate_messages_path,
    get_group_effective_messages_path,
    get_group_issue_index_path,
    get_group_issue_store_path,
    get_group_meta_path,
    get_group_state_path,
    get_parsed_messages_path,
    get_source_effective_messages_path,
    get_source_meta_path,
    get_source_preprocess_report_path,
    get_sources_root,
    get_state_path,
    normalize_name,
)
from excel_agent.cache.serializers import read_json, read_jsonl, write_json, write_jsonl
from excel_agent.chunking.chunker import (
    GroupChunkBuildResult,
    build_chunk_config,
    build_chunks_for_group,
)
from excel_agent.config import PROJECT_ROOT, AppConfig, load_json
from excel_agent.excel.reader import read_excel_input
from excel_agent.excel.validator import build_parse_summary
from excel_agent.issues.issue_index import build_issue_index
from excel_agent.issues.issue_store import issue_store_to_dict, load_issue_store
from excel_agent.llm.context_builder import (
    LlmContextBuildResult,
    build_llm_context_for_group,
)
from excel_agent.models import ExcelTemplate, FileParseResult, ParseSummary, RawMessage
from excel_agent.preprocess.message_deduper import DedupeReport, dedupe_messages
from excel_agent.preprocess.message_filter import (
    PreprocessReport,
    filter_effective_messages,
    get_include_message_types,
)


class PublicCacheResult(tuple):
    pass


# 将配置中的相对路径解析为项目内的绝对路径。
def resolve_project_path(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


# 加载配置指定的 Excel 表头映射模板。
def load_template(config: AppConfig) -> ExcelTemplate:
    template_path = resolve_project_path(config.data.get("template_path", "config/template.json"))
    template_data = load_json(template_path)
    return ExcelTemplate.from_dict(template_data)


# 读取并校验 Excel 输入，同时落盘每个来源文件的解析结果。
def parse_excel_input(input_path: Path, config: AppConfig) -> tuple[list[FileParseResult], ParseSummary]:
    template = load_template(config)
    results = read_excel_input(input_path, template)
    summary = build_parse_summary(results)
    for result in results:
        write_source_parse_outputs(result)
    write_global_state(results, status="parsed")
    return results, summary


# 将单个 Excel 来源的原始消息和来源元数据写入 source 缓存。
def write_source_parse_outputs(result: FileParseResult) -> None:
    source_file = result.source_file
    write_jsonl(get_parsed_messages_path(source_file), (message.to_dict() for message in result.messages))
    write_json(
        get_source_meta_path(source_file),
        {
            "source_id": build_source_id(source_file),
            "source_file": source_file.name,
            "input_path": str(source_file),
            "file_fingerprint": build_file_fingerprint(source_file),
            "total_rows": result.total_rows,
            "total_messages": len(result.messages),
            "empty_counts": result.empty_counts,
            "warnings": result.warnings,
        },
    )


# 过滤各来源文件的有效消息，并保存消息文件和预处理报告。
def save_effective_messages(
    results: list[FileParseResult],
    config: AppConfig,
) -> tuple[dict[str, list[RawMessage]], list[PreprocessReport]]:
    include_message_types = get_include_message_types(config.data)
    messages_by_source: dict[str, list[RawMessage]] = {}
    reports: list[PreprocessReport] = []

    for result in results:
        effective_messages, report = filter_effective_messages(
            result.messages,
            include_message_types,
            source_file=result.source_file.name,
        )
        write_jsonl(
            get_source_effective_messages_path(result.source_file),
            (message.to_dict() for message in effective_messages),
        )
        write_json(get_source_preprocess_report_path(result.source_file), report.to_dict())
        messages_by_source[build_source_id(result.source_file)] = effective_messages
        reports.append(report)

    write_global_state(results, status="preprocessed")
    return messages_by_source, reports


# 从所有 source 缓存中加载有效消息，供公共群消息库汇总使用。
def load_all_source_effective_messages() -> list[RawMessage]:
    source_root = get_sources_root()
    if not source_root.exists():
        return []

    messages: list[RawMessage] = []
    for path in sorted(source_root.glob("*/effective_messages.jsonl")):
        messages.extend(RawMessage.from_dict(record) for record in read_jsonl(path))
    return messages


# 按群名称归集消息，并在每个群内按聊天时间和来源顺序排序。
def group_messages_by_name(messages: list[RawMessage]) -> dict[str, list[RawMessage]]:
    groups: dict[str, list[RawMessage]] = defaultdict(list)
    for message in messages:
        groups[message.group_name].append(message)
    return {
        group_name: sorted(items, key=lambda message: (message.chat_time, message.row_id, message.source_file))
        for group_name, items in groups.items()
    }


# 保存群 ID、真实群名、来源文件和消息时间范围等群元数据。
def write_group_meta(group_name: str, messages: list[RawMessage]) -> None:
    write_json(
        get_group_meta_path(group_name),
        {
            "group_id": build_group_id(group_name),
            "group_folder": build_group_folder_name(group_name),
            "group_name": group_name,
            "normalized_group_name": normalize_name(group_name),
            "is_empty_group": not bool(normalize_name(group_name)),
            "source_files": sorted({message.source_file for message in messages}),
            "total_effective_messages": len(messages),
            "time_start": messages[0].chat_time.isoformat(sep=" ") if messages else None,
            "time_end": messages[-1].chat_time.isoformat(sep=" ") if messages else None,
        },
    )


# 更新指定群某个处理阶段的状态、输出文件和统计数量。
def write_group_state(group_name: str, stage: str, status: str, outputs: list[str], counts: dict[str, int]) -> None:
    state_path = get_group_state_path(group_name)
    state = read_json(state_path) if state_path.exists() else {}
    stages = state.get("stages", {})
    if not isinstance(stages, dict):
        stages = {}
    stages[stage] = {"status": status, "outputs": outputs, "counts": counts}
    state.update(
        {
            "group_id": build_group_id(group_name),
            "group_name": group_name,
            "status": status,
            "stages": stages,
        }
    )
    write_json(state_path, state)


# 将全部 source 有效消息按群汇入公共 group 消息库并写入群状态。
def ingest_groups_from_sources() -> dict[str, list[RawMessage]]:
    all_messages = load_all_source_effective_messages()
    grouped = group_messages_by_name(all_messages)
    for group_name, messages in grouped.items():
        write_group_meta(group_name, messages)
        write_jsonl(get_group_effective_messages_path(group_name), (message.to_dict() for message in messages))
        write_group_state(
            group_name,
            "group_ingest",
            "completed",
            ["effective_messages.jsonl", "group_meta.json"],
            {"effective_messages": len(messages)},
        )
    return grouped


# 对每个群的公共有效消息执行确定性去重并保存去重结果和报告。
def dedupe_group_messages(groups: dict[str, list[RawMessage]]) -> tuple[dict[str, list[RawMessage]], list[DedupeReport]]:
    deduped_by_group: dict[str, list[RawMessage]] = {}
    reports: list[DedupeReport] = []

    for group_name, effective_messages in groups.items():
        deduped_messages, duplicate_records, report = dedupe_messages(
            effective_messages,
            source_file="<group>",
            group_name=group_name,
        )
        deduped_messages = sorted(deduped_messages, key=lambda message: (message.chat_time, message.row_id, message.source_file))
        write_jsonl(get_group_deduped_messages_path(group_name), (message.to_dict() for message in deduped_messages))
        write_jsonl(get_group_duplicate_messages_path(group_name), duplicate_records)
        write_json(get_group_dedupe_report_path(group_name), report.to_dict())
        write_group_state(
            group_name,
            "dedupe",
            "completed",
            ["deduped_messages.jsonl", "duplicate_messages.jsonl", "dedupe_report.json"],
            {"deduped_messages": len(deduped_messages), "duplicate_messages": len(duplicate_records)},
        )
        deduped_by_group[group_name] = deduped_messages
        reports.append(report)

    return deduped_by_group, reports


# 将每个群去重后的连续消息时间线切成供 LLM 读取的消息块。
def build_group_chunks(
    groups: dict[str, list[RawMessage]],
    config: AppConfig,
) -> list[GroupChunkBuildResult]:
    chunk_config = build_chunk_config(config.data)
    chunk_results: list[GroupChunkBuildResult] = []

    for group_name, deduped_messages in groups.items():
        result = build_chunks_for_group(group_name=group_name, messages=deduped_messages, config=chunk_config)
        write_group_state(
            group_name,
            "chunk",
            "completed",
            ["chunks_manifest.json", "chunks/"],
            {"total_chunks": result.total_chunks, "total_deduped_messages": result.total_deduped_messages},
        )
        chunk_results.append(result)

    return chunk_results


# 确保指定群的问题主库和问题索引文件存在并返回问题主库数据。
def ensure_group_issue_files(group_name: str) -> dict[str, Any]:
    issue_store_path = get_group_issue_store_path(group_name)
    issues = load_issue_store(read_json(issue_store_path)) if issue_store_path.exists() else []
    issue_store_data = issue_store_to_dict(issues)
    write_json(issue_store_path, issue_store_data)
    write_json(get_group_issue_index_path(group_name), build_issue_index(issues).to_dict())
    return issue_store_data


# 为每个群的每个 chunk 构造受预算控制的 LLM 历史问题上下文包。
def build_llm_contexts(
    groups: dict[str, list[RawMessage]],
    config: AppConfig,
) -> list[LlmContextBuildResult]:
    results: list[LlmContextBuildResult] = []
    for group_name in groups:
        chunks_manifest = read_json(get_group_chunks_manifest_path(group_name))
        issue_store_data = ensure_group_issue_files(group_name)
        result = build_llm_context_for_group(
            group_name=group_name,
            chunks_manifest=chunks_manifest,
            issue_store_data=issue_store_data,
            config_data=config.data,
        )
        write_group_state(
            group_name,
            "build_llm_context",
            "completed",
            ["llm_context/", "llm_context_manifest.json"],
            {
                "total_chunks": result.total_chunks,
                "total_issue_context_items": result.total_issue_context_items,
                "total_dropped_issue_context_items": result.total_dropped_issue_context_items,
            },
        )
        results.append(result)
    return results


# 串联执行 Excel 解析、来源落盘和有效消息预处理步骤。
def run_steps_1_to_3(
    input_path: Path,
    config: AppConfig,
) -> tuple[list[FileParseResult], ParseSummary, dict[str, list[RawMessage]], list[PreprocessReport]]:
    results, summary = parse_excel_input(input_path, config)
    effective_messages, reports = save_effective_messages(results, config)
    return results, summary, effective_messages, reports


# 串联执行从项目输入到群级切块和 LLM 上下文包生成的完整步骤 1-5。
def run_steps_1_to_5(
    input_path: Path,
    config: AppConfig,
) -> tuple[
    list[FileParseResult],
    ParseSummary,
    dict[str, list[RawMessage]],
    list[PreprocessReport],
    dict[str, list[RawMessage]],
    list[DedupeReport],
    list[GroupChunkBuildResult],
    list[LlmContextBuildResult],
]:
    results, summary, effective_messages, preprocess_reports = run_steps_1_to_3(input_path, config)
    group_effective_messages = ingest_groups_from_sources()
    deduped_groups, dedupe_reports = dedupe_group_messages(group_effective_messages)
    chunk_results = build_group_chunks(deduped_groups, config)
    llm_context_results = build_llm_contexts(deduped_groups, config)
    write_global_state(results, status="step_5_completed")
    return (
        results,
        summary,
        effective_messages,
        preprocess_reports,
        deduped_groups,
        dedupe_reports,
        chunk_results,
        llm_context_results,
    )


# 将当前来源文件清单、文件指纹和整体处理状态写入全局状态文件。
def write_global_state(results: list[FileParseResult], *, status: str) -> None:
    source_entries = []
    for result in results:
        source_entries.append(
            {
                "source_id": build_source_id(result.source_file),
                "source_file": result.source_file.name,
                "input_path": str(result.source_file),
                "file_fingerprint": build_file_fingerprint(result.source_file),
            }
        )
    write_json(
        get_state_path(),
        {
            "status": status,
            "sources": source_entries,
        },
    )
