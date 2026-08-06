from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from excel_agent.issues.issue_store import KnownIssue, issue_store_to_dict
from excel_agent.llm.context_builder import build_llm_context_for_group


def make_issue(issue_id: str, last_seen_offset_days: int) -> KnownIssue:
    base_time = datetime(2026, 8, 5, 10, 0, 0)
    return KnownIssue(
        issue_id=issue_id,
        source_file="chat.xlsx",
        group_name="群A",
        asked_at=base_time - timedelta(days=last_seen_offset_days, hours=1),
        last_seen_at=base_time - timedelta(days=last_seen_offset_days),
        status="open",
        reopened=False,
        summary=f"{issue_id} 摘要",
        row_ids=[1, 2, 3],
    )


def test_build_llm_context_uses_group_issue_store_and_chunk_manifest(tmp_path: Path) -> None:
    manifest = {
        "chunks": [
            {
                "chunk_id": "chunk_20260805T100000_20260805T110000__abcdef12",
                "group_name": "群A",
                "source_files": ["chat.xlsx"],
                "start_time": "2026-08-05 10:00:00",
                "end_time": "2026-08-05 11:00:00",
                "chunk_fingerprint": "abcdef12",
                "path": "chunks/chunk_20260805T100000_20260805T110000__abcdef12.json",
            }
        ]
    }
    issue_store = issue_store_to_dict([make_issue("P1", 1), make_issue("P2", 3)])

    result = build_llm_context_for_group(
        group_name="群A",
        chunks_manifest=manifest,
        issue_store_data=issue_store,
        config_data={"llm_context": {"lookback_days": 2, "max_issue_context_items": 10, "issue_context_budget_tokens": 6000}},
        cache_root=tmp_path,
    )

    assert result.total_chunks == 1
    assert result.total_issue_context_items == 1
    assert result.total_dropped_issue_context_items == 0
