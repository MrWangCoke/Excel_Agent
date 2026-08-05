from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from excel_agent.issues.issue_index import IssueIndex
from excel_agent.issues.issue_store import KnownIssue

OPEN_STATUSES = {"open", "running", "未闭环", "处理中", "二次提问"}
CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class CandidateConfig:
    lookback_days: int = 2
    same_group_only: bool = True
    include_long_open_issues: bool = False
    max_candidates: int = 80
    known_issue_budget_tokens: int = 6000


@dataclass(frozen=True)
class ChunkInfo:
    chunk_id: str
    source_file: str
    group_name: str
    start_time: str
    end_time: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChunkInfo:
        return cls(
            chunk_id=str(data["chunk_id"]),
            source_file=str(data["source_file"]),
            group_name=str(data.get("group_name", "")),
            start_time=str(data["start_time"]),
            end_time=str(data["end_time"]),
        )


@dataclass(frozen=True)
class CandidateSelection:
    chunk_id: str
    source_file: str
    group_name: str
    candidates: list[KnownIssue]
    injected_lines: list[str]
    dropped_count: int
    estimated_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source_file": self.source_file,
            "group_name": self.group_name,
            "candidate_count": len(self.candidates),
            "dropped_count": self.dropped_count,
            "estimated_tokens": self.estimated_tokens,
            "candidates": [issue.to_dict() for issue in self.candidates],
            "injected_lines": self.injected_lines,
        }


def build_candidate_config(config_data: dict[str, object]) -> CandidateConfig:
    data = config_data.get("candidate_issues", {})
    if not isinstance(data, dict):
        data = {}

    return CandidateConfig(
        lookback_days=_positive_int(data.get("lookback_days"), 2),
        same_group_only=bool(data.get("same_group_only", True)),
        include_long_open_issues=bool(data.get("include_long_open_issues", False)),
        max_candidates=_positive_int(data.get("max_candidates"), 80),
        known_issue_budget_tokens=_positive_int(data.get("known_issue_budget_tokens"), 6000),
    )


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def select_candidates_for_chunk(
    chunk: ChunkInfo,
    issue_index: IssueIndex,
    config: CandidateConfig,
) -> CandidateSelection:
    chunk_start = _parse_datetime(chunk.start_time)
    chunk_end = _parse_datetime(chunk.end_time)
    window_start = chunk_start - timedelta(days=config.lookback_days)

    source_issues = issue_index.by_group.get(chunk.group_name, []) if config.same_group_only else _all_issues(issue_index)
    candidates = [
        issue
        for issue in source_issues
        if issue.asked_at <= chunk_end
        and (
            issue.last_seen_at >= window_start
            or (config.include_long_open_issues and issue.status in OPEN_STATUSES)
        )
    ]
    candidates.sort(key=_candidate_sort_key, reverse=True)

    selected: list[KnownIssue] = []
    injected_lines: list[str] = []
    estimated_tokens = 0
    dropped_count = 0

    for issue in candidates:
        if len(selected) >= config.max_candidates:
            dropped_count += 1
            continue

        line = format_candidate_line(issue)
        line_tokens = estimate_line_tokens(line)
        if estimated_tokens + line_tokens > config.known_issue_budget_tokens:
            dropped_count += 1
            continue

        selected.append(issue)
        injected_lines.append(line)
        estimated_tokens += line_tokens

    return CandidateSelection(
        chunk_id=chunk.chunk_id,
        source_file=chunk.source_file,
        group_name=chunk.group_name,
        candidates=selected,
        injected_lines=injected_lines,
        dropped_count=dropped_count,
        estimated_tokens=estimated_tokens,
    )


def _parse_datetime(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)


def _all_issues(issue_index: IssueIndex) -> list[KnownIssue]:
    return [issue for issues in issue_index.by_group.values() for issue in issues]


def _candidate_sort_key(issue: KnownIssue) -> tuple[int, int, Any, str]:
    status_score = 1 if issue.status in OPEN_STATUSES else 0
    reopened_score = 1 if issue.reopened else 0
    return status_score, reopened_score, issue.last_seen_at, issue.issue_id


def format_candidate_line(issue: KnownIssue) -> str:
    row_ids = ",".join(str(row_id) for row_id in issue.row_ids)
    return (
        f"{issue.issue_id} | 群={issue.group_name} | "
        f"首次={issue.asked_at.isoformat(sep=' ')} | "
        f"最近={issue.last_seen_at.isoformat(sep=' ')} | "
        f"状态={issue.status} | 二次={'是' if issue.reopened else '否'} | "
        f"摘要={issue.summary} | 行号={row_ids}"
    )


def estimate_line_tokens(line: str) -> int:
    return max(1, len(line) // CHARS_PER_TOKEN)
