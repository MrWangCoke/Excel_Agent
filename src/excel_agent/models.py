from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RawMessage:
    row_id: int
    source_file: str
    employee_name: str
    employee_phone: str
    employee_wechat_nickname: str
    employee_wechat_id: str
    group_name: str
    message_type: str
    sender_raw: str
    content_raw: str
    chat_time: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "source_file": self.source_file,
            "employee_name": self.employee_name,
            "employee_phone": self.employee_phone,
            "employee_wechat_nickname": self.employee_wechat_nickname,
            "employee_wechat_id": self.employee_wechat_id,
            "group_name": self.group_name,
            "message_type": self.message_type,
            "sender_raw": self.sender_raw,
            "content_raw": self.content_raw,
            "chat_time": self.chat_time.isoformat(sep=" "),
        }


@dataclass(frozen=True)
class ExcelTemplate:
    columns: dict[str, str]
    ignored_columns: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExcelTemplate:
        return cls(
            columns=dict(data.get("columns", {})),
            ignored_columns=list(data.get("ignored_columns", [])),
        )


@dataclass(frozen=True)
class FileParseResult:
    source_file: Path
    total_rows: int
    messages: list[RawMessage]
    empty_counts: dict[str, int]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParseSummary:
    total_files: int
    total_rows: int
    total_messages: int
    time_start: datetime | None
    time_end: datetime | None
    groups: list[str]
    employees: list[str]
    message_type_counts: dict[str, int]
    empty_counts: dict[str, int]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_files": self.total_files,
            "total_rows": self.total_rows,
            "total_messages": self.total_messages,
            "time_start": self.time_start.isoformat(sep=" ") if self.time_start else None,
            "time_end": self.time_end.isoformat(sep=" ") if self.time_end else None,
            "groups": self.groups,
            "employees": self.employees,
            "message_type_counts": self.message_type_counts,
            "empty_counts": self.empty_counts,
            "warnings": self.warnings,
        }
