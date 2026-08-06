from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from excel_agent.llm.extractor import (
    enrich_participants,
    merge_batch_results,
    parse_model_json,
    split_chunk_for_images,
)
from excel_agent.llm.prompt_builder import build_chunk_content_parts
from excel_agent.llm.schema import validate_extraction_result
from excel_agent.models import RawMessage


def make_message(row_id: int, message_type: str, content: str) -> RawMessage:
    return RawMessage(
        row_id=row_id,
        source_file="chat.xlsx",
        employee_name="员工",
        employee_phone="13800000000",
        employee_wechat_nickname="昵称",
        employee_wechat_id="wxid",
        group_name="群A",
        message_type=message_type,
        sender_raw="张*",
        content_raw=content,
        chat_time=datetime(2026, 8, 3, 10, 0, row_id, tzinfo=UTC),
    )


def test_parse_model_json_accepts_code_fence() -> None:
    result = parse_model_json('```json\n{"issues": [], "warnings": []}\n```')

    assert result == {"issues": [], "warnings": []}


def test_build_chunk_content_parts_sends_image_url_and_keeps_invalid_image() -> None:
    messages = [
        make_message(1, "图片", "https://example.com/a.webp"),
        make_message(2, "图片", "not-a-url"),
    ]

    parts, warnings = build_chunk_content_parts(messages)

    assert any(part.get("type") == "image_url" for part in parts)
    assert warnings == ["图片 URL 无效，行号=2"]
    assert any("图片 URL 无效" in part.get("text", "") for part in parts)


def test_split_chunk_for_images_preserves_all_messages() -> None:
    messages = [
        {"row_id": index, "message_type": "图片" if index in {1, 3, 5} else "文本"}
        for index in range(1, 7)
    ]

    batches = split_chunk_for_images({"chunk_id": "c1", "messages": messages}, max_chunk_images=2)

    assert len(batches) == 2
    assert [item["row_id"] for batch in batches for item in batch["messages"]] == list(range(1, 7))
    assert [sum(item["message_type"] == "图片" for item in batch["messages"]) for batch in batches] == [2, 1]


def test_enrich_participants_restores_raw_senders_and_resolves_at_mention() -> None:
    issue = {
        "row_ids": [1004, 1005, 1010],
        "sender_raw": "",
        "sender_resolved": "",
        "reply_users": [],
    }
    chunk = {
        "messages": [
            {"row_id": 1004, "sender_raw": "锦*", "content_raw": "合格证怎么拿"},
            {"row_id": 1005, "sender_raw": "赋**6", "content_raw": "@锦锦 填这个"},
            {"row_id": 1010, "sender_raw": "赋**6", "content_raw": "填三方自提"},
        ]
    }

    enriched = enrich_participants(issue, chunk)

    assert enriched["sender_raw"] == "锦*"
    assert enriched["sender_resolved"] == "锦锦"
    assert enriched["reply_users"] == ["赋**6"]


def test_validate_and_merge_batch_results() -> None:
    issue = {
        "candidate_issue_id": None,
        "is_new": True,
        "is_reopened": False,
        "summary": "问题摘要",
        "asked_at": "2026-08-03 10:00:00",
        "last_seen_at": "2026-08-03 10:01:00",
        "status": "未闭环",
        "sender_raw": "张*",
        "sender_resolved": "",
        "row_ids": [1, 2],
        "image_row_ids": [],
        "quoted_row_ids": [],
        "reply_users": [],
    }
    validated = validate_extraction_result({"issues": [issue], "warnings": []})

    merged = merge_batch_results([validated, validated])

    assert len(merged["issues"]) == 1
    assert merged["issues"][0]["summary"] == "问题摘要"
