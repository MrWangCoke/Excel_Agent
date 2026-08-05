from __future__ import annotations

from pathlib import Path

from excel_agent.cache.cache_manager import (
    get_effective_messages_path,
    get_preprocess_report_path,
)
from excel_agent.cache.serializers import write_json, write_jsonl
from excel_agent.chunking.chunker import (
    ChunkBuildResult,
    build_chunk_config,
    build_chunks_for_source,
)
from excel_agent.config import PROJECT_ROOT, AppConfig, load_json
from excel_agent.excel.reader import read_excel_input
from excel_agent.excel.validator import build_parse_summary
from excel_agent.models import ExcelTemplate, FileParseResult, ParseSummary, RawMessage
from excel_agent.preprocess.message_filter import (
    PreprocessReport,
    filter_effective_messages,
    get_include_message_types,
)


def resolve_project_path(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def load_template(config: AppConfig) -> ExcelTemplate:
    template_path = resolve_project_path(config.data.get("template_path", "config/template.json"))
    template_data = load_json(template_path)
    return ExcelTemplate.from_dict(template_data)


def parse_excel_input(input_path: Path, config: AppConfig) -> tuple[list[FileParseResult], ParseSummary]:
    template = load_template(config)
    results = read_excel_input(input_path, template)
    summary = build_parse_summary(results)
    return results, summary


def save_effective_messages(
    results: list[FileParseResult],
    config: AppConfig,
) -> tuple[dict[str, list[RawMessage]], list[PreprocessReport]]:
    include_message_types = get_include_message_types(config.data)
    messages_by_run: dict[str, list[RawMessage]] = {}
    reports: list[PreprocessReport] = []

    for result in results:
        effective_messages, report = filter_effective_messages(
            result.messages,
            include_message_types,
            source_file=result.source_file.name,
        )
        write_jsonl(
            get_effective_messages_path(result.source_file),
            (message.to_dict() for message in effective_messages),
        )
        write_json(get_preprocess_report_path(result.source_file), report.to_dict())
        messages_by_run[result.source_file.stem] = effective_messages
        reports.append(report)

    return messages_by_run, reports


def build_message_chunks(
    results: list[FileParseResult],
    messages_by_run: dict[str, list[RawMessage]],
    config: AppConfig,
) -> list[ChunkBuildResult]:
    chunk_config = build_chunk_config(config.data)
    chunk_results: list[ChunkBuildResult] = []

    for result in results:
        effective_messages = messages_by_run[result.source_file.stem]
        chunk_results.append(
            build_chunks_for_source(
                source_file=result.source_file,
                messages=effective_messages,
                config=chunk_config,
            )
        )

    return chunk_results


def run_steps_1_to_3(
    input_path: Path,
    config: AppConfig,
) -> tuple[list[FileParseResult], ParseSummary, dict[str, list[RawMessage]], list[PreprocessReport]]:
    results, summary = parse_excel_input(input_path, config)
    effective_messages, reports = save_effective_messages(results, config)
    return results, summary, effective_messages, reports


def run_steps_1_to_4(
    input_path: Path,
    config: AppConfig,
) -> tuple[
    list[FileParseResult],
    ParseSummary,
    dict[str, list[RawMessage]],
    list[PreprocessReport],
    list[ChunkBuildResult],
]:
    results, summary, effective_messages, preprocess_reports = run_steps_1_to_3(input_path, config)
    chunk_results = build_message_chunks(results, effective_messages, config)
    return results, summary, effective_messages, preprocess_reports, chunk_results
