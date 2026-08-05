from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from excel_agent.issues.candidate_selector import (
    CandidateConfig,
    ChunkInfo,
    select_candidates_for_chunk,
)
from excel_agent.issues.issue_index import build_issue_index
from excel_agent.issues.issue_store import KnownIssue


def make_issue(issue_id: str, group_name: str, last_seen_offset_days: int, status: str = "open") -> KnownIssue:
    base_time = datetime(2026, 8, 5, 10, 0, 0)  # noqa: DTZ001 - project chat times are timezone-naive
    return KnownIssue(
        issue_id=issue_id,
        source_file="chat.xlsx",
        group_name=group_name,
        asked_at=base_time - timedelta(days=last_seen_offset_days, hours=1),
        last_seen_at=base_time - timedelta(days=last_seen_offset_days),
        status=status,
        reopened=False,
        summary=f"{issue_id} 摘要",
        row_ids=[1, 2, 3],
    )


def make_chunk() -> ChunkInfo:
    return ChunkInfo(
        chunk_id="chunk_000001",
        source_file="chat.xlsx",
        group_name="群A",
        start_time="2026-08-05 10:00:00",
        end_time="2026-08-05 11:00:00",
    )


def test_select_candidates_uses_two_day_same_group_window() -> None:
    issues = [
        make_issue("P1", "群A", 1),
        make_issue("P2", "群A", 2),
        make_issue("P3", "群A", 3),
        make_issue("P4", "群B", 1),
    ]
    issue_index = build_issue_index(issues)

    selection = select_candidates_for_chunk(make_chunk(), issue_index, CandidateConfig(lookback_days=2))

    assert [issue.issue_id for issue in selection.candidates] == ["P1", "P2"]
    assert all("发起人=" not in line for line in selection.injected_lines)


def test_select_candidates_respects_max_candidates() -> None:
    issues = [make_issue(f"P{index}", "群A", 1) for index in range(5)]
    issue_index = build_issue_index(issues)

    selection = select_candidates_for_chunk(
        make_chunk(),
        issue_index,
        CandidateConfig(lookback_days=2, max_candidates=2),
    )

    assert len(selection.candidates) == 2
    assert selection.dropped_count == 3
