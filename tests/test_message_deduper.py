from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from excel_agent.models import RawMessage
from excel_agent.preprocess.message_deduper import build_dedupe_key, dedupe_messages


def make_message(
    row_id: int,
    *,
    employee_name: str = "员工A",
    group_name: str = "群A",
    sender_raw: str = "张三",
    message_type: str = "文本",
    content_raw: str = "请问这个订单怎么处理？",
    chat_time: datetime | None = None,
) -> RawMessage:
    return RawMessage(
        row_id=row_id,
        source_file="chat.xlsx",
        employee_name=employee_name,
        employee_phone=f"1380000{row_id:04d}",
        employee_wechat_nickname=f"昵称{row_id}",
        employee_wechat_id=f"wxid_{row_id}",
        group_name=group_name,
        message_type=message_type,
        sender_raw=sender_raw,
        content_raw=content_raw,
        chat_time=chat_time or datetime(2026, 8, 5, 10, 0, 0),
    )


def test_dedupe_messages_removes_same_group_time_sender_type_and_content() -> None:
    first = make_message(2, employee_name="员工A")
    duplicate_from_other_employee = make_message(8, employee_name="员工B")
    different_content = make_message(9, employee_name="员工B", content_raw="这是另一条消息")

    deduped_messages, duplicate_records, report = dedupe_messages(
        [first, duplicate_from_other_employee, different_content],
        source_file="chat.xlsx",
    )

    assert [message.row_id for message in deduped_messages] == [2, 9]
    assert len(duplicate_records) == 1
    assert duplicate_records[0]["canonical"]["row_id"] == 2
    assert duplicate_records[0]["duplicate"]["row_id"] == 8
    assert duplicate_records[0]["duplicate"]["employee_name"] == "员工B"
    assert report.total_messages == 3
    assert report.deduped_messages == 2
    assert report.duplicate_messages == 1
    assert report.duplicate_key_count == 1
    assert report.duplicate_type_counts == {"文本": 1}
    assert report.duplicate_group_counts == {"群A": 1}


def test_dedupe_messages_keeps_same_content_at_different_time() -> None:
    first = make_message(2)
    later = make_message(3, chat_time=first.chat_time + timedelta(seconds=1))

    deduped_messages, duplicate_records, report = dedupe_messages(
        [first, later],
        source_file="chat.xlsx",
    )

    assert [message.row_id for message in deduped_messages] == [2, 3]
    assert duplicate_records == []
    assert report.duplicate_messages == 0


def test_build_dedupe_key_normalizes_text_whitespace_and_microseconds() -> None:
    first = make_message(
        2,
        group_name=" 群A ",
        sender_raw=" 张三 ",
        content_raw="请问   这个订单\n怎么处理？",
        chat_time=datetime(2026, 8, 5, 10, 0, 0, 123456),
    )
    same_after_normalization = make_message(
        3,
        group_name="群A",
        sender_raw="张三",
        content_raw="请问 这个订单 怎么处理？",
        chat_time=datetime(2026, 8, 5, 10, 0, 0),
    )

    assert build_dedupe_key(first) == build_dedupe_key(same_after_normalization)


def test_build_dedupe_key_keeps_image_url_body() -> None:
    first = make_message(2, message_type="图片", content_raw=" https://example.com/a.jpg ")
    same_url = make_message(3, message_type="图片", content_raw="https://example.com/a.jpg")
    different_url = make_message(4, message_type="图片", content_raw="https://example.com/b.jpg")

    assert build_dedupe_key(first) == build_dedupe_key(same_url)
    assert build_dedupe_key(first) != build_dedupe_key(different_url)
