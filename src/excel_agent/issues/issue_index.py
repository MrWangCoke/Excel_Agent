from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from excel_agent.issues.issue_store import KnownIssue


@dataclass(frozen=True)
class IssueIndex:
    by_group: dict[str, list[KnownIssue]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "groups": {
                group_name: [issue.issue_id for issue in issues]
                for group_name, issues in sorted(self.by_group.items())
            }
        }


def build_issue_index(issues: list[KnownIssue]) -> IssueIndex:
    grouped: dict[str, list[KnownIssue]] = defaultdict(list)
    for issue in issues:
        grouped[issue.group_name].append(issue)

    return IssueIndex(
        by_group={
            group_name: sorted(items, key=lambda issue: (issue.last_seen_at, issue.issue_id), reverse=True)
            for group_name, items in grouped.items()
        }
    )
