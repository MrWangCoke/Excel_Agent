from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from excel_agent.cache.cache_manager import (
    EMPTY_GROUP_FOLDER,
    build_group_folder_name,
    build_group_id,
    safe_path_part,
)
from excel_agent.chunking.chunker import ChunkConfig, build_chunk_fingerprint, make_time_range_chunk_id
from excel_agent.models import RawMessage


def make_message(row_id: int, *, group_name: str = "群A") -> RawMessage:
    return RawMessage(
        row_id=row_id,
        source_file="chat.xlsx",
        employee_name="员工姓名",
        employee_phone="员工手机号",
        employee_wechat_nickname="员工微信昵称",
        employee_wechat_id="员工微信号",
        group_name=group_name,
        message_type="文本",
        sender_raw="发送人",
        content_raw=f"消息内容 {row_id}",
        chat_time=datetime(2026, 8, 3, 8, 0, 0) + timedelta(minutes=row_id),
    )


def test_group_folder_uses_hash_and_safe_group_name() -> None:
    folder = build_group_folder_name("AAA青岛兴业/运营—合格证保管员")

    assert folder.startswith("g_")
    assert "__AAA青岛兴业_运营—合格证保管员" in folder
    assert "/" not in folder


def test_empty_group_uses_single_shared_folder() -> None:
    assert build_group_id("") == "g_empty"
    assert build_group_folder_name("  ") == EMPTY_GROUP_FOLDER


def test_safe_path_part_replaces_windows_invalid_characters() -> None:
    assert safe_path_part('a/b\\c:d*e?f"g<h>i|j', default="x") == "a_b_c_d_e_f_g_h_i_j"


def test_time_range_chunk_id_contains_time_range_and_fingerprint() -> None:
    messages = [make_message(1), make_message(2), make_message(3)]

    chunk_id, fingerprint = make_time_range_chunk_id(messages)

    assert chunk_id.startswith("chunk_20260803T080100_20260803T080300__")
    assert chunk_id.endswith(fingerprint)
    assert fingerprint == build_chunk_fingerprint(messages)
    assert len(fingerprint) == 8


def test_chunk_config_reads_rebuild_window_days() -> None:
    config = ChunkConfig(rebuild_window_days=2)

    assert config.rebuild_window_days == 2
