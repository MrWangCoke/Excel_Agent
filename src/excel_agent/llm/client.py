from __future__ import annotations

from openai import OpenAI

from excel_agent.config import AppConfig


class LlmConfigurationError(ValueError):
    pass


# 根据项目配置和 .env 环境变量创建官方 OpenAI SDK 客户端。
def build_chat_model(config: AppConfig) -> OpenAI:
    base_url = config.llm_base_url
    api_key = config.llm_api_key
    model = config.llm_model
    missing = []
    if not base_url:
        missing.append("OPENAI_BASE_URL")
    if not api_key:
        missing.append("OPENAI_API_KEY")
    if not model:
        missing.append("OPENAI_MODEL")
    if missing:
        raise LlmConfigurationError(f"缺少环境变量：{', '.join(missing)}")

    llm_data = config.data.get("llm", {})
    timeout = (
        llm_data.get("timeout_seconds", 120) if isinstance(llm_data, dict) else 120
    )
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=float(timeout),
    )
