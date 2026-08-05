from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Self


@dataclass(frozen=True)
class IssuePerson:
    sender_raw: str
    sender_resolved: str = ""
    role: str = "unknown"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            sender_raw=str(data.get("sender_raw", "")),
            sender_resolved=str(data.get("sender_resolved", "")),
            role=str(data.get("role", "unknown")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sender_raw": self.sender_raw,
            "sender_resolved": self.sender_resolved,
            "role": self.role,
        }


@dataclass(frozen=True)
class IssueEvidence:
    row_id: int
    kind: str
    quote: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            row_id=int(data["row_id"]),
            kind=str(data.get("kind", "context")),
            quote=str(data.get("quote", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "kind": self.kind,
            "quote": self.quote,
        }


@dataclass(frozen=True)
class IssueClosure:
    is_closed: bool = False
    closed_at: datetime | None = None
    closed_by: str = ""
    basis: str = ""
    confidence: str = "low"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        closed_at = data.get("closed_at")
        return cls(
            is_closed=bool(data.get("is_closed", False)),
            closed_at=datetime.fromisoformat(str(closed_at)) if closed_at else None,
            closed_by=str(data.get("closed_by", "")),
            basis=str(data.get("basis", "")),
            confidence=str(data.get("confidence", "low")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_closed": self.is_closed,
            "closed_at": self.closed_at.isoformat(sep=" ") if self.closed_at else None,
            "closed_by": self.closed_by,
            "basis": self.basis,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class IssueMergeInfo:
    parent_issue_id: str | None = None
    merged_issue_ids: list[str] = field(default_factory=list)
    duplicate_of: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            parent_issue_id=_optional_str(data.get("parent_issue_id")),
            merged_issue_ids=[str(issue_id) for issue_id in data.get("merged_issue_ids", [])],
            duplicate_of=_optional_str(data.get("duplicate_of")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_issue_id": self.parent_issue_id,
            "merged_issue_ids": self.merged_issue_ids,
            "duplicate_of": self.duplicate_of,
        }


@dataclass(frozen=True)
class IssueLlmInfo:
    source_chunk_ids: list[str] = field(default_factory=list)
    candidate_issue_ids: list[str] = field(default_factory=list)
    confidence: str = "medium"
    notes: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            source_chunk_ids=[str(chunk_id) for chunk_id in data.get("source_chunk_ids", [])],
            candidate_issue_ids=[str(issue_id) for issue_id in data.get("candidate_issue_ids", [])],
            confidence=str(data.get("confidence", "medium")),
            notes=str(data.get("notes", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_chunk_ids": self.source_chunk_ids,
            "candidate_issue_ids": self.candidate_issue_ids,
            "confidence": self.confidence,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class Issue:
    issue_id: str
    source_file: str
    group_name: str
    status: str
    reopened: bool
    title: str
    summary: str
    category: str
    asked_at: datetime
    last_seen_at: datetime
    closed_at: datetime | None
    asker: IssuePerson
    participants: list[IssuePerson] = field(default_factory=list)
    row_ids: list[int] = field(default_factory=list)
    quoted_row_ids: list[int] = field(default_factory=list)
    image_row_ids: list[int] = field(default_factory=list)
    evidence: list[IssueEvidence] = field(default_factory=list)
    closure: IssueClosure = field(default_factory=IssueClosure)
    merge: IssueMergeInfo = field(default_factory=IssueMergeInfo)
    llm: IssueLlmInfo = field(default_factory=IssueLlmInfo)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        closed_at = data.get("closed_at")
        return cls(
            issue_id=str(data["issue_id"]),
            source_file=str(data.get("source_file", "")),
            group_name=str(data.get("group_name", "")),
            status=str(data.get("status", "unknown")),
            reopened=bool(data.get("reopened", False)),
            title=str(data.get("title", "")),
            summary=str(data.get("summary", "")),
            category=str(data.get("category", "")),
            asked_at=datetime.fromisoformat(str(data["asked_at"])),
            last_seen_at=datetime.fromisoformat(str(data["last_seen_at"])),
            closed_at=datetime.fromisoformat(str(closed_at)) if closed_at else None,
            asker=IssuePerson.from_dict(data.get("asker", {})),
            participants=[IssuePerson.from_dict(item) for item in data.get("participants", [])],
            row_ids=[int(row_id) for row_id in data.get("row_ids", [])],
            quoted_row_ids=[int(row_id) for row_id in data.get("quoted_row_ids", [])],
            image_row_ids=[int(row_id) for row_id in data.get("image_row_ids", [])],
            evidence=[IssueEvidence.from_dict(item) for item in data.get("evidence", [])],
            closure=IssueClosure.from_dict(data.get("closure", {})),
            merge=IssueMergeInfo.from_dict(data.get("merge", {})),
            llm=IssueLlmInfo.from_dict(data.get("llm", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "source_file": self.source_file,
            "group_name": self.group_name,
            "status": self.status,
            "reopened": self.reopened,
            "title": self.title,
            "summary": self.summary,
            "category": self.category,
            "asked_at": self.asked_at.isoformat(sep=" "),
            "last_seen_at": self.last_seen_at.isoformat(sep=" "),
            "closed_at": self.closed_at.isoformat(sep=" ") if self.closed_at else None,
            "asker": self.asker.to_dict(),
            "participants": [participant.to_dict() for participant in self.participants],
            "row_ids": self.row_ids,
            "quoted_row_ids": self.quoted_row_ids,
            "image_row_ids": self.image_row_ids,
            "evidence": [item.to_dict() for item in self.evidence],
            "closure": self.closure.to_dict(),
            "merge": self.merge.to_dict(),
            "llm": self.llm.to_dict(),
        }


@dataclass(frozen=True)
class KnownIssue:
    issue_id: str
    source_file: str
    group_name: str
    asked_at: datetime
    last_seen_at: datetime
    status: str
    reopened: bool
    summary: str
    row_ids: list[int] = field(default_factory=list)

    @classmethod
    def from_issue(cls, issue: Issue) -> KnownIssue:
        return cls(
            issue_id=issue.issue_id,
            source_file=issue.source_file,
            group_name=issue.group_name,
            asked_at=issue.asked_at,
            last_seen_at=issue.last_seen_at,
            status=issue.status,
            reopened=issue.reopened,
            summary=issue.summary,
            row_ids=issue.row_ids,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            issue_id=str(data["issue_id"]),
            source_file=str(data.get("source_file", "")),
            group_name=str(data.get("group_name", "")),
            asked_at=datetime.fromisoformat(str(data["asked_at"])),
            last_seen_at=datetime.fromisoformat(str(data["last_seen_at"])),
            status=str(data.get("status", "unknown")),
            reopened=bool(data.get("reopened", False)),
            summary=str(data.get("summary", "")),
            row_ids=[int(row_id) for row_id in data.get("row_ids", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "source_file": self.source_file,
            "group_name": self.group_name,
            "asked_at": self.asked_at.isoformat(sep=" "),
            "last_seen_at": self.last_seen_at.isoformat(sep=" "),
            "status": self.status,
            "reopened": self.reopened,
            "summary": self.summary,
            "row_ids": self.row_ids,
        }


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def load_issue_store(data: dict[str, Any]) -> list[KnownIssue]:
    raw_issues = data.get("issues", [])
    if not isinstance(raw_issues, list):
        return []
    return [KnownIssue.from_dict(item) for item in raw_issues if isinstance(item, dict)]


def issue_store_to_dict(issues: list[KnownIssue]) -> dict[str, Any]:
    return {"issues": [issue.to_dict() for issue in issues]}
