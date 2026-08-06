from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from excel_agent.cache.serializers import read_json, write_json
from excel_agent.config import AppConfig
from excel_agent.llm.client import build_chat_model
from excel_agent.llm.prompt_builder import build_extraction_messages
from excel_agent.llm.schema import validate_extraction_result


@dataclass(frozen=True)
class ChunkExtractionResult:
    chunk_id: str
    result_path: Path
    issue_count: int
    warning_count: int
    batch_count: int


def _get_max_output_tokens(config: AppConfig) -> int:
    """读取输出预算，避免模型输出截断导致结果不是完整 JSON。"""
    budget = config.data.get("context_budget", {})
    if isinstance(budget, dict):
        reserve = budget.get("reserve_output_tokens", 8000)
        try:
            return max(256, int(reserve))
        except (TypeError, ValueError):
            pass
    return 8000


# 从模型响应中提取并解析 JSON 对象，兼容少量代码围栏输出。
def parse_model_json(content: object) -> dict[str, Any]:
    if isinstance(content, list):
        text = "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content)
    else:
        text = str(content)
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise TypeError("LLM 返回的 JSON 顶层必须是对象")
    return data


# 按最大图片数量将一个逻辑 chunk 拆成连续的 LLM 调用批次。
def split_chunk_for_images(chunk_data: dict[str, Any], max_chunk_images: int) -> list[dict[str, Any]]:
    raw_messages = [item for item in chunk_data.get("messages", []) if isinstance(item, dict)]
    if not raw_messages:
        return [{**chunk_data, "messages": []}]
    if max_chunk_images <= 0:
        return [chunk_data]

    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    image_count = 0
    for message in raw_messages:
        is_image = str(message.get("message_type", "")) == "图片"
        if is_image and image_count >= max_chunk_images and current:
            batches.append(current)
            current = []
            image_count = 0
        current.append(message)
        if is_image:
            image_count += 1
    if current:
        batches.append(current)

    result: list[dict[str, Any]] = []
    for index, messages in enumerate(batches, start=1):
        batch = dict(chunk_data)
        batch["messages"] = messages
        batch["batch_index"] = index
        batch["batch_count"] = len(batches)
        result.append(batch)
    return result


# 合并同一逻辑 chunk 多个调用批次的局部问题和告警。
def _is_masked_sender(sender: str) -> bool:
    return "*" in sender or "＊" in sender


def _name_matches_masked(masked: str, full_name: str) -> bool:
    masked = masked.replace("＊", "*").strip()
    full_name = full_name.strip()
    if not masked or not full_name or "*" not in masked:
        return False
    pattern = "^" + re.escape(masked).replace(r"\*", ".+") + "$"
    return bool(re.match(pattern, full_name))


def enrich_participants(issue: dict[str, Any], chunk_data: dict[str, Any]) -> dict[str, Any]:
    """用原始消息和 @ 提及对模型参与人结果做确定性校正。"""
    messages = [item for item in chunk_data.get("messages", []) if isinstance(item, dict)]
    row_ids = {int(row_id) for row_id in issue.get("row_ids", [])}
    related = [item for item in messages if int(item.get("row_id", -1)) in row_ids]
    if not related:
        return issue

    first_sender = str(related[0].get("sender_raw", "")).strip()
    if first_sender:
        issue["sender_raw"] = first_sender

    participants: list[str] = []
    for item in related[1:]:
        sender = str(item.get("sender_raw", "")).strip()
        if sender and sender != first_sender and sender not in participants:
            participants.append(sender)
        content = str(item.get("content_raw", ""))
        mentions = re.findall(r"@([一-鿿]{2,4})", content)
        if _is_masked_sender(first_sender):
            for name in mentions:
                if _name_matches_masked(first_sender, name):
                    issue["sender_resolved"] = name
    if participants:
        issue["reply_users"] = participants
    return issue


def enrich_result_participants(result: dict[str, Any], chunk_data: dict[str, Any]) -> dict[str, Any]:
    result["issues"] = [enrich_participants(dict(issue), chunk_data) for issue in result.get("issues", [])]
    return result


# 合并同一逻辑 chunk 多个调用批次的局部问题和警告。
def merge_batch_results(batch_results: list[dict[str, Any]]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for result in batch_results:
        for issue in result.get("issues", []):
            key = json.dumps(
                {
                    "candidate_issue_id": issue.get("candidate_issue_id"),
                    "summary": issue.get("summary", ""),
                    "row_ids": sorted(issue.get("row_ids", [])),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            if key not in seen:
                seen.add(key)
                issues.append(issue)
        warnings.extend(str(item) for item in result.get("warnings", []))
    return {"issues": issues, "warnings": list(dict.fromkeys(warnings))}


# 调用模型处理一个逻辑 chunk，并将多批次结果汇总后落盘。
def extract_chunk(
    *,
    chunk_path: Path,
    context_path: Path,
    result_path: Path,
    config: AppConfig,
    mock: bool = False,
) -> ChunkExtractionResult:
    chunk_data = read_json(chunk_path)
    context_data = read_json(context_path)
    chunk_id = str(chunk_data.get("chunk_id", chunk_path.stem))
    context_config = config.data.get("llm_context", {})
    max_images = int(context_config.get("max_chunk_images", 10)) if isinstance(context_config, dict) else 10
    batches = split_chunk_for_images(chunk_data, max_images)
    model = None if mock else build_chat_model(config)
    model_name = "mock" if mock else config.llm_model
    batch_results: list[dict[str, Any]] = []
    prompt_warnings: list[str] = []

    for batch in batches:
        if mock:
            parsed = {"issues": [], "warnings": []}
            warnings: list[str] = []
        else:
            if model is None or model_name is None:
                raise RuntimeError("真实模式下 LLM 客户端和模型名称不能为空")
            messages, warnings = build_extraction_messages(chunk_data=batch, context_data=context_data)
            response = model.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0,
                response_format={"type": "json_object"},
                max_tokens=_get_max_output_tokens(config),
            )
            content = response.choices[0].message.content if response.choices else ""
            parsed = parse_model_json(content)
            parsed = enrich_result_participants(parsed, batch)
            parsed = validate_extraction_result(parsed)
        prompt_warnings.extend(warnings)
        batch_results.append(parsed)

    merged = merge_batch_results(batch_results)
    merged["warnings"] = list(dict.fromkeys([*merged["warnings"], *prompt_warnings]))
    output = {
        "chunk_id": chunk_id,
        "group_id": chunk_data.get("group_id", ""),
        "group_name": chunk_data.get("group_name", ""),
        "chunk_fingerprint": chunk_data.get("chunk_fingerprint", ""),
        "model": model_name,
        "batch_count": len(batches),
        "issues": merged["issues"],
        "warnings": merged["warnings"],
    }
    write_json(result_path, output)
    return ChunkExtractionResult(
        chunk_id=chunk_id,
        result_path=result_path,
        issue_count=len(output["issues"]),
        warning_count=len(output["warnings"]),
        batch_count=len(batches),
    )
