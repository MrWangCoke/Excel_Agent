from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from excel_agent.config import AppConfig
from excel_agent.llm import extractor
from excel_agent.llm.client import build_chat_model
from excel_agent.llm.schema import validate_extraction_result


def make_config() -> AppConfig:
    return AppConfig(
        path=Path("config/default.json"),
        data={
            "llm": {
                "base_url_env": "TEST_BASE_URL",
                "api_key_env": "TEST_API_KEY",
                "model_env": "TEST_MODEL",
                "timeout_seconds": 30,
            },
            "context_budget": {"reserve_output_tokens": 1024},
        },
    )


def test_build_chat_model_uses_official_openai_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("TEST_API_KEY", "secret")
    monkeypatch.setenv("TEST_MODEL", "vision-model")

    client = build_chat_model(make_config())

    assert str(client.base_url) == "https://example.test/v1/"
    assert client.api_key == "secret"


def test_validate_result_defaults_optional_fields_and_normalizes_rows() -> None:
    result = validate_extraction_result(
        {
            "issues": [
                {
                    "candidate_issue_id": None,
                    "is_new": True,
                    "is_reopened": False,
                    "summary": "问题",
                    "asked_at": None,
                    "last_seen_at": None,
                    "status": "未闭环",
                    "sender_raw": "张*",
                    "sender_resolved": "",
                    "reply_users": [],
                    "row_ids": [3, 1, 3],
                    "image_row_ids": [],
                    "quoted_row_ids": [],
                }
            ]
        }
    )

    assert result["issues"][0]["row_ids"] == [1, 3]
    assert result["issues"][0]["sender_resolved"] == ""
    assert result["warnings"] == []


def test_validate_result_rejects_empty_sender_raw() -> None:
    with pytest.raises(ValueError, match="sender_raw"):
        validate_extraction_result(
            {
                "issues": [
                    {
                        "candidate_issue_id": None,
                        "is_new": True,
                        "is_reopened": False,
                        "summary": "问题",
                        "asked_at": None,
                        "last_seen_at": None,
                        "status": "未闭环",
                        "sender_raw": "",
                        "sender_resolved": "",
                        "reply_users": [],
                        "row_ids": [1],
                        "image_row_ids": [],
                        "quoted_row_ids": [],
                    }
                ]
            }
        )


def test_validate_result_rejects_invalid_status() -> None:
    with pytest.raises(ValueError, match="status"):
        validate_extraction_result(
            {
                "issues": [
                    {
                        "candidate_issue_id": None,
                        "is_new": True,
                        "is_reopened": False,
                        "summary": "问题",
                        "asked_at": None,
                        "last_seen_at": None,
                        "status": "未知",
                        "sender_raw": "张*",
                        "sender_resolved": "",
                        "reply_users": [],
                        "row_ids": [],
                        "image_row_ids": [],
                        "quoted_row_ids": [],
                    }
                ]
            }
        )


def test_extract_chunk_uses_chat_completions_and_json_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chunk = {
        "chunk_id": "chunk-1",
        "group_id": "group-1",
        "group_name": "群A",
        "chunk_fingerprint": "fp-1",
        "messages": [],
    }
    context = {"injected_lines": []}
    chunk_path = tmp_path / "chunk.json"
    context_path = tmp_path / "context.json"
    result_path = tmp_path / "result.json"
    chunk_path.write_text('{"chunk_id":"chunk-1","group_id":"group-1","group_name":"群A","chunk_fingerprint":"fp-1","messages":[]}', encoding="utf-8")
    context_path.write_text('{"injected_lines":[]}', encoding="utf-8")

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["response_format"] == {"type": "json_object"}
            assert kwargs["temperature"] == 0
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"issues": [], "warnings": []}'))])

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    monkeypatch.setattr(extractor, "build_chat_model", lambda config: fake_client)
    monkeypatch.setenv("TEST_MODEL", "vision-model")

    result = extractor.extract_chunk(
        chunk_path=chunk_path,
        context_path=context_path,
        result_path=result_path,
        config=make_config(),
    )

    assert result.issue_count == 0
    assert result_path.exists()
