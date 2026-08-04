from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from excel_agent.models import RawMessage

DEFAULT_INCLUDE_MESSAGE_TYPES = {"文本", "图片", "引用消息"}


@dataclass(frozen=True)
class PreprocessReport:
    source_file: str
    total_messages: int
    effective_messages: int
    ignored_messages: int
    include_message_types: list[str]
    effective_type_counts: dict[str, int]
    ignored_type_counts: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "source_file": self.source_file,
            "total_messages": self.total_messages,
            "effective_messages": self.effective_messages,
            "ignored_messages": self.ignored_messages,
            "include_message_types": self.include_message_types,
            "effective_type_counts": self.effective_type_counts,
            "ignored_type_counts": self.ignored_type_counts,
        }


def get_include_message_types(config_data: dict[str, object]) -> set[str]:
    message_types = config_data.get("message_types", {})
    if not isinstance(message_types, dict):
        return set(DEFAULT_INCLUDE_MESSAGE_TYPES)

    include = message_types.get("include")
    if not isinstance(include, list):
        return set(DEFAULT_INCLUDE_MESSAGE_TYPES)

    include_types = {item.strip() for item in include if isinstance(item, str) and item.strip()}
    return include_types or set(DEFAULT_INCLUDE_MESSAGE_TYPES)


def filter_effective_messages(
    messages: list[RawMessage],
    include_message_types: set[str],
    *,
    source_file: str,
) -> tuple[list[RawMessage], PreprocessReport]:
    effective_messages: list[RawMessage] = []
    ignored_type_counts: Counter[str] = Counter()
    effective_type_counts: Counter[str] = Counter()

    for message in messages:
        if message.message_type in include_message_types:
            effective_messages.append(message)
            effective_type_counts[message.message_type] += 1
        else:
            ignored_type_counts[message.message_type or "<空>"] += 1

    report = PreprocessReport(
        source_file=source_file,
        total_messages=len(messages),
        effective_messages=len(effective_messages),
        ignored_messages=len(messages) - len(effective_messages),
        include_message_types=sorted(include_message_types),
        effective_type_counts=dict(sorted(effective_type_counts.items())),
        ignored_type_counts=dict(sorted(ignored_type_counts.items())),
    )
    return effective_messages, report
