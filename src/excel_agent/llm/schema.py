from __future__ import annotations

from typing import Any

REQUIRED_ISSUE_FIELDS = {
    "candidate_issue_id",
    "is_new",
    "is_reopened",
    "summary",
    "asked_at",
    "last_seen_at",
    "status",
    "sender_raw",
    "sender_resolved",
    "reply_users",
    "row_ids",
    "image_row_ids",
    "quoted_row_ids",
}

OPTIONAL_ISSUE_DEFAULTS: dict[str, Any] = {
    "title": "",
    "category": "",
    "closed_at": None,
    "close_evidence": "",
    "confidence": "low",
    "notes": "",
}
VALID_STATUSES = {"未闭环", "处理中", "已闭环"}
VALID_CONFIDENCES = {"high", "medium", "low"}


def build_extraction_schema() -> dict[str, Any]:
    """返回步骤 6 要求模型输出的 JSON 结构说明。"""
    return {
        "issues": [
            {
                "candidate_issue_id": "Pxxxxxx or null",
                "is_new": True,
                "is_reopened": False,
                "title": "问题标题",
                "summary": "问题摘要",
                "category": "问题分类",
                "asked_at": "YYYY-MM-DD HH:MM:SS or null",
                "last_seen_at": "YYYY-MM-DD HH:MM:SS or null",
                "status": "未闭环/已闭环/处理中",
                "closed_at": "YYYY-MM-DD HH:MM:SS or null",
                "close_evidence": "闭环依据",
                "sender_raw": "原始发起人",
                "sender_resolved": "可确认的发起人全名，否则空字符串",
                "reply_users": ["回复人"],
                "row_ids": [123],
                "image_row_ids": [124],
                "quoted_row_ids": [125],
                "confidence": "high/medium/low",
                "notes": "备注",
            }
        ],
        "warnings": ["无法确认的内容"],
    }


def validate_extraction_result(data: object) -> dict[str, Any]:
    """校验并规范 LLM 返回的步骤 6 结果。"""
    if not isinstance(data, dict):
        raise TypeError("LLM 返回结果必须是 JSON 对象")
    raw_issues = data.get("issues", [])
    if not isinstance(raw_issues, list):
        raise TypeError("LLM 返回结果的 issues 必须是数组")

    normalized_issues: list[dict[str, Any]] = []
    for index, issue in enumerate(raw_issues):
        if not isinstance(issue, dict):
            raise TypeError(f"issues[{index}] 必须是对象")
        normalized = dict(issue)
        missing = REQUIRED_ISSUE_FIELDS - normalized.keys()
        if missing:
            raise TypeError(f"issues[{index}] 缺少字段：{', '.join(sorted(missing))}")
        for field, default in OPTIONAL_ISSUE_DEFAULTS.items():
            normalized.setdefault(field, list(default) if isinstance(default, list) else default)
        for field in ("row_ids", "image_row_ids", "quoted_row_ids", "reply_users"):
            if not isinstance(normalized.get(field), list):
                raise TypeError(f"issues[{index}].{field} 必须是数组")
        for field in ("is_new", "is_reopened"):
            if not isinstance(normalized[field], bool):
                raise TypeError(f"issues[{index}].{field} 必须是布尔值")
        if normalized["status"] not in VALID_STATUSES:
            raise ValueError(f"issues[{index}].status 不是有效状态：{normalized['status']}")
        if normalized["confidence"] not in VALID_CONFIDENCES:
            raise ValueError(f"issues[{index}].confidence 不是有效值：{normalized['confidence']}")
        if not isinstance(normalized["sender_raw"], str) or not normalized["sender_raw"].strip():
            raise ValueError(f"issues[{index}].sender_raw 不能为空")
        if not isinstance(normalized["sender_resolved"], str):
            raise TypeError(f"issues[{index}].sender_resolved 必须是字符串")
        normalized["sender_raw"] = normalized["sender_raw"].strip()
        normalized["sender_resolved"] = normalized["sender_resolved"].strip()
        normalized["reply_users"] = list(dict.fromkeys(str(user).strip() for user in normalized["reply_users"] if str(user).strip()))
        normalized["row_ids"] = sorted({int(row_id) for row_id in normalized["row_ids"]})
        normalized["image_row_ids"] = sorted({int(row_id) for row_id in normalized["image_row_ids"]})
        normalized["quoted_row_ids"] = sorted({int(row_id) for row_id in normalized["quoted_row_ids"]})
        normalized_issues.append(normalized)

    warnings = data.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = [str(warnings)]
    return {"issues": normalized_issues, "warnings": [str(item) for item in warnings]}
