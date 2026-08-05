from __future__ import annotations

from pathlib import Path

from excel_agent.cache.cache_manager import (
    get_candidates_manifest_path,
    get_chunk_candidates_dir,
    get_chunks_manifest_path,
    get_dedupe_report_path,
    get_deduped_messages_path,
    get_duplicate_messages_path,
    get_effective_messages_path,
    get_issue_index_path,
    get_issue_store_path,
    get_preprocess_report_path,
)
from excel_agent.cache.serializers import read_json, write_json, write_jsonl
from excel_agent.chunking.chunker import (
    ChunkBuildResult,
    build_chunk_config,
    build_chunks_for_source,
)
from excel_agent.config import PROJECT_ROOT, AppConfig, load_json
from excel_agent.excel.reader import read_excel_input
from excel_agent.excel.validator import build_parse_summary
from excel_agent.issues.candidate_selector import (
    CandidateSelection,
    ChunkInfo,
    build_candidate_config,
    select_candidates_for_chunk,
)
from excel_agent.issues.issue_index import build_issue_index
from excel_agent.issues.issue_store import (
    KnownIssue,
    issue_store_to_dict,
    load_issue_store,
)
from excel_agent.models import ExcelTemplate, FileParseResult, ParseSummary, RawMessage
from excel_agent.preprocess.message_deduper import DedupeReport, dedupe_messages
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


def dedupe_effective_messages(
    results: list[FileParseResult],
    messages_by_run: dict[str, list[RawMessage]],
) -> tuple[dict[str, list[RawMessage]], list[DedupeReport]]:
    deduped_by_run: dict[str, list[RawMessage]] = {}
    reports: list[DedupeReport] = []

    for result in results:
        effective_messages = messages_by_run[result.source_file.stem]
        deduped_messages, duplicate_records, report = dedupe_messages(
            effective_messages,
            source_file=result.source_file.name,
        )
        write_jsonl(
            get_deduped_messages_path(result.source_file),
            (message.to_dict() for message in deduped_messages),
        )
        write_jsonl(get_duplicate_messages_path(result.source_file), duplicate_records)
        write_json(get_dedupe_report_path(result.source_file), report.to_dict())
        deduped_by_run[result.source_file.stem] = deduped_messages
        reports.append(report)

    return deduped_by_run, reports


def build_message_chunks(
    results: list[FileParseResult],
    messages_by_run: dict[str, list[RawMessage]],
    config: AppConfig,
) -> list[ChunkBuildResult]:
    chunk_config = build_chunk_config(config.data)
    chunk_results: list[ChunkBuildResult] = []

    for result in results:
        deduped_messages = messages_by_run[result.source_file.stem]
        chunk_results.append(
            build_chunks_for_source(
                source_file=result.source_file,
                messages=deduped_messages,
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


def build_chunk_candidates(
    results: list[FileParseResult],
    config: AppConfig,
) -> list[CandidateSelection]:
    candidate_config = build_candidate_config(config.data)
    selections: list[CandidateSelection] = []

    for result in results:
        issue_store_path = get_issue_store_path(result.source_file)
        issues: list[KnownIssue] = load_issue_store(read_json(issue_store_path)) if issue_store_path.exists() else []
        issue_index = build_issue_index(issues)
        write_json(get_issue_store_path(result.source_file), issue_store_to_dict(issues))
        write_json(get_issue_index_path(result.source_file), issue_index.to_dict())

        chunks_manifest = read_json(get_chunks_manifest_path(result.source_file))
        candidates_dir = get_chunk_candidates_dir(result.source_file)
        candidates_dir.mkdir(parents=True, exist_ok=True)
        run_selections: list[CandidateSelection] = []

        for chunk_data in chunks_manifest.get("chunks", []):
            if not isinstance(chunk_data, dict):
                continue
            selection = select_candidates_for_chunk(
                ChunkInfo.from_dict(chunk_data),
                issue_index,
                candidate_config,
            )
            write_json(candidates_dir / f"{selection.chunk_id}.json", selection.to_dict())
            run_selections.append(selection)
            selections.append(selection)

        write_json(
            get_candidates_manifest_path(result.source_file),
            {
                "run_id": result.source_file.stem,
                "source_file": result.source_file.name,
                "lookback_days": candidate_config.lookback_days,
                "same_group_only": candidate_config.same_group_only,
                "max_candidates": candidate_config.max_candidates,
                "known_issue_budget_tokens": candidate_config.known_issue_budget_tokens,
                "total_chunks": len(run_selections),
                "total_candidates": sum(len(selection.candidates) for selection in run_selections),
                "total_dropped_candidates": sum(selection.dropped_count for selection in run_selections),
                "chunks": [
                    {
                        "chunk_id": selection.chunk_id,
                        "candidate_count": len(selection.candidates),
                        "dropped_count": selection.dropped_count,
                        "estimated_tokens": selection.estimated_tokens,
                        "path": f"chunk_candidates/{selection.chunk_id}.json",
                    }
                    for selection in run_selections
                ],
            },
        )

    return selections


def run_steps_1_to_4(
    input_path: Path,
    config: AppConfig,
) -> tuple[
    list[FileParseResult],
    ParseSummary,
    dict[str, list[RawMessage]],
    list[PreprocessReport],
    dict[str, list[RawMessage]],
    list[DedupeReport],
    list[ChunkBuildResult],
]:
    results, summary, effective_messages, preprocess_reports = run_steps_1_to_3(input_path, config)
    deduped_messages, dedupe_reports = dedupe_effective_messages(results, effective_messages)
    chunk_results = build_message_chunks(results, deduped_messages, config)
    return results, summary, effective_messages, preprocess_reports, deduped_messages, dedupe_reports, chunk_results


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
    list[ChunkBuildResult],
    list[CandidateSelection],
]:
    (
        results,
        summary,
        effective_messages,
        preprocess_reports,
        deduped_messages,
        dedupe_reports,
        chunk_results,
    ) = run_steps_1_to_4(input_path, config)
    candidate_selections = build_chunk_candidates(results, config)
    return (
        results,
        summary,
        effective_messages,
        preprocess_reports,
        deduped_messages,
        dedupe_reports,
        chunk_results,
        candidate_selections,
    )
