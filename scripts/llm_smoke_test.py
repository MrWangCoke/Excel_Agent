from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

sys.path.insert(0, str(SRC_ROOT))

config_module: Any = importlib.import_module("excel_agent.config")
langchain_openai: Any = importlib.import_module("langchain_openai")
load_config = config_module.load_config
ChatOpenAI = langchain_openai.ChatOpenAI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="用 LangChain 测试 OpenAI 兼容 LLM 连通性。")
    parser.add_argument("question", nargs="?", help="要发送给模型的问题；不传则运行时输入。")
    return parser


def load_project_env() -> Path:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return env_path

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")
    return env_path


def main() -> int:
    args = build_parser().parse_args()
    question = args.question or input("请输入要问模型的问题：").strip()
    if not question:
        print("问题不能为空。")
        return 1

    env_path = load_project_env()
    config = load_config()
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
        print(f"缺少环境变量：{', '.join(missing)}")
        return 1

    print("LLM 连通性测试配置：")
    print(f"ENV_FILE={env_path}")
    print(f"OPENAI_BASE_URL={base_url}")
    print(f"OPENAI_MODEL={model}")
    print("OPENAI_API_KEY=已读取，出于安全不显示")

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )

    try:
        response = llm.invoke(question)
    except Exception as exc:  # noqa: BLE001 - smoke test should print concise external client errors
        print("LLM 连通性测试失败：LangChain 调用模型接口失败。")
        print(f"错误类型：{exc.__class__.__name__}")
        print(f"错误信息：{exc}")
        return 1

    content = getattr(response, "content", response)
    print("LLM 连通性测试响应：")
    print(content)
    print("LLM 连通性测试完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
