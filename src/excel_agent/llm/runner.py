from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from excel_agent.cache.serializers import read_json, write_json
from excel_agent.config import AppConfig
from excel_agent.llm.extractor import ChunkExtractionResult, extract_chunk


@dataclass(frozen=True)
class GroupExtractionResult:
    group_folder: Path
    manifest_path: Path
    total_chunks: int
    completed_chunks: int
    total_issues: int
    total_warnings: int


# 在指定群文件夹内逐块执行步骤 6，并生成群级 LLM 结果清单。
def extract_group_chunks(
    *,
    group_folder: Path,
    config: AppConfig,
    mock: bool = False,
    max_chunks: int | None = None,
    chunk_id: str | None = None,
    resume: bool = False,
    progress_callback: Callable[[str, int, int, bool], None] | None = None,
) -> GroupExtractionResult:
    group_folder = group_folder.expanduser().resolve()
    chunks_manifest_path = group_folder / "chunks_manifest.json"
    context_manifest_path = group_folder / "llm_context_manifest.json"
    if not chunks_manifest_path.exists():
        raise FileNotFoundError(f"缺少 chunks_manifest.json：{group_folder}")
    if not context_manifest_path.exists():
        raise FileNotFoundError(f"缺少 llm_context_manifest.json：{group_folder}")

    chunks_manifest = read_json(chunks_manifest_path)
    context_manifest = read_json(context_manifest_path)
    context_paths = {
        str(item.get("chunk_id", "")): str(item.get("path", ""))
        for item in context_manifest.get("contexts", [])
        if isinstance(item, dict)
    }
    raw_chunks = [
        item for item in chunks_manifest.get("chunks", []) if isinstance(item, dict)
    ]
    if chunk_id is not None:
        raw_chunks = [
            item for item in raw_chunks if str(item.get("chunk_id", "")) == chunk_id
        ]
        if not raw_chunks:
            raise ValueError(f"指定群中不存在 chunk：{chunk_id}")
    if max_chunks is not None:
        raw_chunks = raw_chunks[: max(0, max_chunks)]

    results_dir = group_folder / "llm_results"
    results_dir.mkdir(parents=True, exist_ok=True)
    extraction_results: list[ChunkExtractionResult] = []
    result_entries: list[dict[str, Any]] = []

    total_selected_chunks = len(raw_chunks)
    for chunk_number, chunk_data in enumerate(raw_chunks, start=1):
        chunk_id = str(chunk_data.get("chunk_id", ""))
        chunk_relative_path = str(chunk_data.get("path", ""))
        context_relative_path = context_paths.get(
            chunk_id, f"llm_context/{chunk_id}.json"
        )
        chunk_path = group_folder / chunk_relative_path
        context_path = group_folder / context_relative_path
        result_path = results_dir / f"{chunk_id}.json"
        fingerprint = str(chunk_data.get("chunk_fingerprint", ""))

        if resume and result_path.exists():
            existing = read_json(result_path)
            if existing.get("chunk_fingerprint") == fingerprint:
                result_entries.append(
                    build_result_entry(
                        existing, result_path, group_folder, skipped=True
                    )
                )
                if progress_callback is not None:
                    progress_callback(
                        chunk_id, chunk_number, total_selected_chunks, True
                    )
                continue

        result = extract_chunk(
            chunk_path=chunk_path,
            context_path=context_path,
            result_path=result_path,
            config=config,
            mock=mock,
        )
        extraction_results.append(result)
        result_entries.append(
            {
                "chunk_id": result.chunk_id,
                "path": result_path.relative_to(group_folder).as_posix(),
                "issue_count": result.issue_count,
                "warning_count": result.warning_count,
                "batch_count": result.batch_count,
                "skipped": False,
            }
        )
        if progress_callback is not None:
            progress_callback(chunk_id, chunk_number, total_selected_chunks, False)

    manifest_path = group_folder / "llm_results_manifest.json"
    write_json(
        manifest_path,
        {
            "group_id": chunks_manifest.get("group_id", ""),
            "group_name": chunks_manifest.get("group_name", ""),
            "model": config.llm_model if not mock else "mock",
            "total_chunks": len(raw_chunks),
            "completed_chunks": len(result_entries),
            "total_issues": sum(
                int(item.get("issue_count", 0)) for item in result_entries
            ),
            "total_warnings": sum(
                int(item.get("warning_count", 0)) for item in result_entries
            ),
            "results": result_entries,
        },
    )
    return GroupExtractionResult(
        group_folder=group_folder,
        manifest_path=manifest_path,
        total_chunks=len(raw_chunks),
        completed_chunks=len(result_entries),
        total_issues=sum(int(item.get("issue_count", 0)) for item in result_entries),
        total_warnings=sum(
            int(item.get("warning_count", 0)) for item in result_entries
        ),
    )


# 将已存在的单块 LLM 结果转换为群级结果清单条目。
def build_result_entry(
    data: dict[str, Any],
    result_path: Path,
    group_folder: Path,
    *,
    skipped: bool,
) -> dict[str, Any]:
    issues = data.get("issues", [])
    warnings = data.get("warnings", [])
    return {
        "chunk_id": str(data.get("chunk_id", result_path.stem)),
        "path": result_path.relative_to(group_folder).as_posix(),
        "issue_count": len(issues) if isinstance(issues, list) else 0,
        "warning_count": len(warnings) if isinstance(warnings, list) else 0,
        "batch_count": int(data.get("batch_count", 1)),
        "skipped": skipped,
    }
