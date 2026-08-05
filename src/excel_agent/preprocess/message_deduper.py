from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from excel_agent.models import RawMessage

DedupeKey = tuple[str, str, str, str, str]


@dataclass(frozen=True)
class DedupeReport:
    source_file: str
    total_messages: int
    deduped_messages: int
    duplicate_messages: int
    duplicate_key_count: int
    duplicate_type_counts: dict[str, int]
    duplicate_group_counts: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "source_file": self.source_file,
            "total_messages": self.total_messages,
            "deduped_messages": self.deduped_messages,
            "duplicate_messages": self.duplicate_messages,
            "duplicate_key_count": self.duplicate_key_count,
            "duplicate_type_counts": self.duplicate_type_counts,
            "duplicate_group_counts": self.duplicate_group_counts,
        }


def dedupe_messages(
    messages: list[RawMessage],
    *,
    source_file: str,
) -> tuple[list[RawMessage], list[dict[str, Any]], DedupeReport]:
    seen: dict[DedupeKey, RawMessage] = {}
    duplicate_keys: set[DedupeKey] = set()
    deduped_messages: list[RawMessage] = []
    duplicate_records: list[dict[str, Any]] = []
    duplicate_type_counts: Counter[str] = Counter()
    duplicate_group_counts: Counter[str] = Counter()

    for message in messages:
        key = build_dedupe_key(message)
        canonical = seen.get(key)
        if canonical is None:
            seen[key] = message
            deduped_messages.append(message)
            continue

        duplicate_keys.add(key)
        duplicate_type_counts[message.message_type or "<空>"] += 1
        duplicate_group_counts[message.group_name or "<空>"] += 1
        duplicate_records.append(
            {
                "dedupe_key": dedupe_key_to_dict(key),
                "canonical": source_ref(canonical),
                "duplicate": source_ref(message),
            }
        )

    report = DedupeReport(
        source_file=source_file,
        total_messages=len(messages),
        deduped_messages=len(deduped_messages),
        duplicate_messages=len(duplicate_records),
        duplicate_key_count=len(duplicate_keys),
        duplicate_type_counts=dict(sorted(duplicate_type_counts.items())),
        duplicate_group_counts=dict(sorted(duplicate_group_counts.items())),
    )
    return deduped_messages, duplicate_records, report


def build_dedupe_key(message: RawMessage) -> DedupeKey:
    return (
        normalize_text(message.group_name),
        normalize_chat_time(message),
        normalize_text(message.sender_raw),
        normalize_message_type(message.message_type),
        normalize_content(message),
    )


def normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def normalize_message_type(value: str) -> str:
    return normalize_text(value)


def normalize_chat_time(message: RawMessage) -> str:
    return message.chat_time.replace(microsecond=0).isoformat(sep=" ")


def normalize_content(message: RawMessage) -> str:
    content = message.content_raw.strip()
    if normalize_message_type(message.message_type) == "图片":
        return content
    return normalize_text(content)


def dedupe_key_to_dict(key: DedupeKey) -> dict[str, str]:
    group_name, chat_time, sender_raw, message_type, content_raw = key
    return {
        "group_name": group_name,
        "chat_time": chat_time,
        "sender_raw": sender_raw,
        "message_type": message_type,
        "content_raw": content_raw,
    }


def source_ref(message: RawMessage) -> dict[str, object]:
    return {
        "source_file": message.source_file,
        "row_id": message.row_id,
        "employee_name": message.employee_name,
        "employee_phone": message.employee_phone,
        "employee_wechat_nickname": message.employee_wechat_nickname,
        "employee_wechat_id": message.employee_wechat_id,
        "group_name": message.group_name,
        "chat_time": message.chat_time.isoformat(sep=" "),
        "sender_raw": message.sender_raw,
        "message_type": message.message_type,
        "content_raw": message.content_raw,
    }
