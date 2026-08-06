from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from openai.types.chat import (
    ChatCompletionContentPartParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from excel_agent.llm.schema import build_extraction_schema
from excel_agent.models import RawMessage

SYSTEM_PROMPT = """你是群聊问题识别助手。你的任务是从当前 chunk 的群聊消息中提取结构化问题。
严格要求：
1. 只输出一个合法 JSON 对象，不输出 Markdown、解释或代码围栏。
2. 当前 chunk 是本次正式识别内容；前后文只用于理解，不要仅凭前后文新建问题。
3. 历史问题摘要只用于判断 candidate_issue_id、二次提问、回复和闭环。
4. 图片必须结合相邻文本、发送人、时间和图片视觉内容理解，不要臆测图片无法确认的信息。
5. 相同问题在本 chunk 内只能输出一次，row_ids 应包含提问、回复、图片和闭环相关行号。
6. 无问题时返回 {"issues": [], "warnings": []}。
7. 不输出员工姓名、手机号、微信昵称、微信号等员工四字段。
8. 闭环指本轮群聊问答已形成明确结论，不要求业务事项已经实际执行完毕。只要原因、当前状态、处理方式、责任归属或下一步条件已经明确告知，且发起人以“好的”“了解”“收到”等表示知悉，或发起人当前能做的事项已经完成、后续只能等待其他责任人或外部条件，即判定为已闭环。此时 closed_at 使用确认知悉或最终明确答复的时间，close_evidence 写明答复内容和确认依据。
9. 只有既没有明确答复/结论，也仍需当前对话参与人继续确认或处理时，才判定为处理中或未闭环；“尚待其他人执行”“车辆尚未到达”“手续后续办理”本身不等于未闭环。
10. 每个问题必须填写 sender_raw；只要问题行存在回复，就必须填写 reply_users。无法还原全名时保留原始脱敏发送人，不能留空。
11. sender_resolved 仅在有可靠证据时填写。可使用紧邻回复中的 @姓名、引用关系、直接称呼和问答对应关系还原脱敏姓名。例如发送人是“锦*”，直接回复写有“@锦锦”，可推断 sender_resolved="锦锦"。消息正文里的联系人、收件人或电话号码姓名不能据此认定为消息发送人。
"""


# 判断给定字符串是否是可直接发送给多模态模型的 HTTP/HTTPS 图片地址。
def is_http_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


# 将一条文本或引用消息格式化为保留行号、时间和发送人的提示文本。
def format_message_text(message: RawMessage) -> str:
    return (
        f"[行号={message.row_id}][时间={message.chat_time.isoformat(sep=' ')}]"
        f"[类型={message.message_type}][发送人={message.sender_raw}]\n{message.content_raw}"
    )


# 将当前 chunk 消息构造成文本与 image_url 交错的多模态内容块。
def build_chunk_content_parts(
    messages: list[RawMessage],
) -> tuple[list[ChatCompletionContentPartParam], list[str]]:
    parts: list[ChatCompletionContentPartParam] = []
    warnings: list[str] = []
    for message in messages:
        if message.message_type == "图片":
            parts.append(
                {
                    "type": "text",
                    "text": (
                        f"[行号={message.row_id}][时间={message.chat_time.isoformat(sep=' ')}]"
                        f"[类型=图片][发送人={message.sender_raw}]"
                    ),
                }
            )
            if is_http_url(message.content_raw):
                parts.append(
                    {"type": "image_url", "image_url": {"url": message.content_raw}}
                )
            else:
                warning = f"图片 URL 无效，行号={message.row_id}"
                warnings.append(warning)
                parts.append({"type": "text", "text": f"[{warning}]"})
            continue
        parts.append({"type": "text", "text": format_message_text(message)})
    return parts, warnings


# 构造步骤 6 单块调用所需的系统提示和多模态用户消息。
def build_extraction_messages(
    *,
    chunk_data: dict[str, Any],
    context_data: dict[str, Any],
) -> tuple[list[ChatCompletionMessageParam], list[str]]:
    messages = [
        RawMessage.from_dict(item)
        for item in chunk_data.get("messages", [])
        if isinstance(item, dict)
    ]
    content_parts, warnings = build_chunk_content_parts(messages)
    header = {
        "chunk_id": chunk_data.get("chunk_id", ""),
        "chunk_fingerprint": chunk_data.get("chunk_fingerprint", ""),
        "group_name": chunk_data.get("group_name", ""),
        "start_time": chunk_data.get("start_time", ""),
        "end_time": chunk_data.get("end_time", ""),
        "overlap_from_prev": chunk_data.get("overlap_from_prev", 0),
    }
    instruction = (
        "【当前 chunk 元数据】\n"
        + json.dumps(header, ensure_ascii=False)
        + "\n\n【历史问题摘要】\n"
        + json.dumps(context_data.get("injected_lines", []), ensure_ascii=False)
        + "\n\n【前置上下文】\n"
        + json.dumps(
            context_data.get("context_before_messages", []), ensure_ascii=False
        )
        + "\n\n【后置上下文】\n"
        + json.dumps(context_data.get("context_after_messages", []), ensure_ascii=False)
        + "\n\n【输出 JSON 结构】\n"
        + json.dumps(build_extraction_schema(), ensure_ascii=False)
        + "\n\n【当前 chunk 消息】"
    )
    user_content: list[ChatCompletionContentPartParam] = [
        {"type": "text", "text": instruction},
        *content_parts,
    ]
    system_message: ChatCompletionSystemMessageParam = {
        "role": "system",
        "content": SYSTEM_PROMPT,
    }
    user_message: ChatCompletionUserMessageParam = {
        "role": "user",
        "content": user_content,
    }
    return [system_message, user_message], warnings
