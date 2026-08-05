from __future__ import annotations

import importlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

chunker = importlib.import_module("excel_agent.chunking.chunker")
models = importlib.import_module("excel_agent.models")
ChunkConfig = chunker.ChunkConfig
group_messages = chunker.group_messages
iter_windows = chunker.iter_windows
RawMessage: Any = models.RawMessage


def make_message(row_id: int, group_name: str = "群A", message_type: str = "文本") -> Any:
    return RawMessage(
        row_id=row_id,
        source_file="chat.xlsx",
        employee_name="员工姓名",
        employee_phone="员工手机号",
        employee_wechat_nickname="员工微信昵称",
        employee_wechat_id="员工微信号",
        group_name=group_name,
        message_type=message_type,
        sender_raw="发送人",
        content_raw="消息内容",
        chat_time=datetime(2026, 7, 1, 8, 0, 0, tzinfo=UTC) + timedelta(minutes=row_id),
    )


def test_group_messages_uses_source_file_and_group_name() -> None:
    messages = [make_message(3, "群B"), make_message(1, "群A"), make_message(2, "群A")]

    grouped = group_messages(messages)

    assert list(grouped[("chat.xlsx", "群A")]) == [messages[1], messages[2]]
    assert list(grouped[("chat.xlsx", "群B")]) == [messages[0]]


def test_iter_windows_uses_size_and_overlap() -> None:
    messages = [make_message(row_id) for row_id in range(1, 9)]
    config = ChunkConfig(size=5, overlap=2)

    windows = list(iter_windows(messages, config))

    assert [[message.row_id for message in window] for window, _ in windows] == [
        [1, 2, 3, 4, 5],
        [4, 5, 6, 7, 8],
    ]
    assert [overlap for _, overlap in windows] == [0, 2]


def test_raw_message_json_round_trip() -> None:
    message = make_message(12, message_type="图片")
    encoded = json.dumps(message.to_dict(), ensure_ascii=False)
    decoded = RawMessage.from_dict(json.loads(encoded))

    assert decoded == message
