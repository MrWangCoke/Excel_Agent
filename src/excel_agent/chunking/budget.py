from __future__ import annotations

from dataclasses import dataclass

from excel_agent.models import RawMessage

TEXT_BASE_TOKENS = 12
IMAGE_MESSAGE_TOKENS = 1200
QUOTE_MESSAGE_EXTRA_TOKENS = 80
CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class BudgetEstimate:
    estimated_tokens: int
    budget_status: str

    # 将上下文预算估算结果转换为可落盘的字典数据。
    def to_dict(self) -> dict[str, int | str]:
        return {
            "estimated_tokens": self.estimated_tokens,
            "budget_status": self.budget_status,
        }


# 根据消息类型和文本长度估算单条消息占用的 token 数。
def estimate_message_tokens(message: RawMessage) -> int:
    text_tokens = max(1, len(message.content_raw) // CHARS_PER_TOKEN)
    estimated = TEXT_BASE_TOKENS + text_tokens
    if message.message_type == "图片":
        estimated += IMAGE_MESSAGE_TOKENS
    if message.message_type == "引用消息":
        estimated += QUOTE_MESSAGE_EXTRA_TOKENS
    return estimated


# 汇总整个消息块的 token 估算并判断是否超过预算。
def estimate_chunk_budget(messages: list[RawMessage], reserve_chunk_tokens: int) -> BudgetEstimate:
    estimated_tokens = sum(estimate_message_tokens(message) for message in messages)
    status = "over_budget" if estimated_tokens > reserve_chunk_tokens else "ok"
    return BudgetEstimate(estimated_tokens=estimated_tokens, budget_status=status)
