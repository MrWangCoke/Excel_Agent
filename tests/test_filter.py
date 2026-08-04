from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from excel_agent.models import RawMessage
from excel_agent.preprocess.message_filter import filter_effective_messages


def make_message(row_id: int, message_type: str) -> RawMessage:
    return RawMessage(
        row_id=row_id,
        source_file="chat.xlsx",
        employee_name="员工姓名",
        employee_phone="员工手机号",
        employee_wechat_nickname="员工微信昵称",
        employee_wechat_id="员工微信号",
        group_name="群名称",
        message_type=message_type,
        sender_raw="发送人",
        content_raw="消息内容",
        chat_time=datetime(2026, 7, 1, 8, 0, 0),
    )


def test_filter_effective_messages_uses_exact_message_types_only() -> None:
    messages = [
        make_message(2, "文本"),
        make_message(3, "图片"),
        make_message(4, "引用消息"),
        make_message(5, "图片消息"),
        make_message(6, "文本消息"),
        make_message(7, "系统消息"),
    ]

    effective_messages, report = filter_effective_messages(
        messages,
        {"文本", "图片", "引用消息"},
        source_file="chat.xlsx",
    )

    assert [message.row_id for message in effective_messages] == [2, 3, 4]
    assert report.effective_messages == 3
    assert report.ignored_messages == 3
    assert report.effective_type_counts == {"图片": 1, "引用消息": 1, "文本": 1}
