"""在终端输入问题，测试 OpenAI 兼容接口是否可用。"""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def get_question() -> str:
    """从终端接收问题。"""
    return input("请输入问题：").strip()


def build_client() -> OpenAI:
    """读取 .env 并创建 OpenAI 兼容客户端。"""
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    return OpenAI(
        base_url=os.environ["OPENAI_BASE_URL"],
        api_key=os.environ["OPENAI_API_KEY"],
    )


def ask_model(client: OpenAI, question: str) -> str:
    """将问题发送给模型，并返回回答。"""
    response = client.chat.completions.create(
        model=os.environ["OPENAI_MODEL"],
        messages=[{"role": "user", "content": question}],
    )
    return response.choices[0].message.content or "模型没有返回文字内容。"


def main() -> None:
    question = get_question()
    if not question:
        print("问题不能为空。")
        return

    try:
        client = build_client()
        answer = ask_model(client, question)
        print("\n模型回答：")
        print(answer)
    except KeyError as error:
        print(f".env 缺少配置：{error.args[0]}")
    except OpenAIError as error:
        print(f"API 调用失败：{error}")


if __name__ == "__main__":
    main()
