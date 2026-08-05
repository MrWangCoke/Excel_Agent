from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from excel_agent.issues.issue_store import (
    Issue,
    IssueClosure,
    IssueEvidence,
    IssueLlmInfo,
    IssueMergeInfo,
    IssuePerson,
    KnownIssue,
)


def make_issue() -> Issue:
    return Issue(
        issue_id="P000001",
        source_file="8.3.xlsx",
        group_name="群A",
        status="open",
        reopened=False,
        title="设备离线需要处理",
        summary="客户反馈车辆设备长时间离线，需要核实设备状态。",
        category="设备离线",
        asked_at=datetime(2026, 8, 3, 10, 22, 0),  # noqa: DTZ001 - project chat times are timezone-naive
        last_seen_at=datetime(2026, 8, 3, 14, 35, 0),  # noqa: DTZ001 - project chat times are timezone-naive
        closed_at=None,
        asker=IssuePerson(sender_raw="张*", sender_resolved=""),
        participants=[IssuePerson(sender_raw="李*", sender_resolved="李四", role="responder")],
        row_ids=[12, 13, 14, 205],
        quoted_row_ids=[13],
        image_row_ids=[14],
        evidence=[IssueEvidence(row_id=12, kind="ask", quote="设备离线，麻烦核实处理")],
        closure=IssueClosure(is_closed=False, confidence="low"),
        merge=IssueMergeInfo(),
        llm=IssueLlmInfo(source_chunk_ids=["chunk_000001"], confidence="medium"),
    )


def test_issue_json_round_trip() -> None:
    issue = make_issue()

    decoded = Issue.from_dict(issue.to_dict())

    assert decoded == issue
    assert decoded.asker.to_dict() == {
        "sender_raw": "张*",
        "sender_resolved": "",
        "role": "unknown",
    }
    assert decoded.participants[0].role == "responder"


def test_known_issue_from_full_issue() -> None:
    issue = make_issue()

    known_issue = KnownIssue.from_issue(issue)

    assert known_issue.issue_id == issue.issue_id
    assert known_issue.group_name == issue.group_name
    assert known_issue.summary == issue.summary
    assert known_issue.row_ids == issue.row_ids
