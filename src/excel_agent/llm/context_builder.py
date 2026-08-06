from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from excel_agent.cache.cache_manager import get_group_llm_context_dir, get_group_llm_context_manifest_path
from excel_agent.cache.serializers import read_json, write_json
from excel_agent.issues.candidate_selector import (
    CandidateConfig,
    ChunkInfo,
    build_candidate_config,
    select_candidates_for_chunk,
)
from excel_agent.issues.issue_index import build_issue_index
from excel_agent.issues.issue_store import KnownIssue, load_issue_store
from excel_agent.models import RawMessage


@dataclass(frozen=True)
class LlmContextBuildResult:
    group_name: str
    manifest_path: Path
    total_chunks: int
    total_issue_context_items: int
    total_dropped_issue_context_items: int


def build_llm_context_for_group(
    *,
    group_name: str,
    chunks_manifest: dict[str, Any],
    issue_store_data: dict[str, Any],
    config_data: dict[str, object],
    cache_root: Path | None = None,
) -> LlmContextBuildResult:
    candidate_config = build_candidate_config(config_data)
    issues: list[KnownIssue] = load_issue_store(issue_store_data)
    issue_index = build_issue_index(issues)
    context_dir = get_group_llm_context_dir(group_name, cache_root) if cache_root else get_group_llm_context_dir(group_name)
    context_dir.mkdir(parents=True, exist_ok=True)

    context_entries: list[dict[str, object]] = []
    total_items = 0
    total_dropped = 0

    for chunk_data in chunks_manifest.get("chunks", []):
        if not isinstance(chunk_data, dict):
            continue
        chunk = ChunkInfo.from_dict(chunk_data)
        selection = select_candidates_for_chunk(chunk, issue_index, candidate_config)
        chunk_context = {
            "chunk_id": selection.chunk_id,
            "group_name": group_name,
            "target_chunk_path": chunk_data.get("path", ""),
            "chunk_fingerprint": chunk_data.get("chunk_fingerprint", ""),
            "context_before_messages": [],
            "context_after_messages": [],
            "issue_context_budget_tokens": candidate_config.known_issue_budget_tokens,
            "selected_issue_count": len(selection.candidates),
            "dropped_issue_count": selection.dropped_count,
            "estimated_tokens": selection.estimated_tokens,
            "issue_summaries": [issue.to_dict() for issue in selection.candidates],
            "injected_lines": selection.injected_lines,
        }
        relative_path = f"llm_context/{selection.chunk_id}.json"
        write_json(context_dir / f"{selection.chunk_id}.json", chunk_context)
        context_entries.append(
            {
                "chunk_id": selection.chunk_id,
                "path": relative_path,
                "selected_issue_count": len(selection.candidates),
                "dropped_issue_count": selection.dropped_count,
                "estimated_tokens": selection.estimated_tokens,
            }
        )
        total_items += len(selection.candidates)
        total_dropped += selection.dropped_count

    manifest_path = (
        get_group_llm_context_manifest_path(group_name, cache_root)
        if cache_root
        else get_group_llm_context_manifest_path(group_name)
    )
    write_json(
        manifest_path,
        {
            "group_name": group_name,
            "issue_context_budget_tokens": candidate_config.known_issue_budget_tokens,
            "max_issue_context_items": candidate_config.max_candidates,
            "total_chunks": len(context_entries),
            "total_issue_context_items": total_items,
            "total_dropped_issue_context_items": total_dropped,
            "contexts": context_entries,
        },
    )
    return LlmContextBuildResult(
        group_name=group_name,
        manifest_path=manifest_path,
        total_chunks=len(context_entries),
        total_issue_context_items=total_items,
        total_dropped_issue_context_items=total_dropped,
    )


def load_chunk_messages(chunk_path: Path) -> list[RawMessage]:
    data = read_json(chunk_path)
    messages = data.get("messages", [])
    if not isinstance(messages, list):
        return []
    return [RawMessage.from_dict(item) for item in messages if isinstance(item, dict)]
