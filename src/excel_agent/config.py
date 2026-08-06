from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.json"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class AppConfig:
    path: Path
    data: dict[str, Any]

    # 从环境变量中读取 LLM 接口的基础地址。
    @property
    def llm_base_url(self) -> str | None:
        env_name = self.data.get("llm", {}).get("base_url_env", "OPENAI_BASE_URL")
        return os.getenv(env_name)

    # 从环境变量中读取调用 LLM 所需的 API Key。
    @property
    def llm_api_key(self) -> str | None:
        env_name = self.data.get("llm", {}).get("api_key_env", "OPENAI_API_KEY")
        return os.getenv(env_name)

    # 从环境变量中读取当前要调用的 LLM 模型名称。
    @property
    def llm_model(self) -> str | None:
        env_name = self.data.get("llm", {}).get("model_env", "OPENAI_MODEL")
        return os.getenv(env_name)


# 读取 .env 文件并将尚未设置的配置项写入环境变量。
def load_dotenv_file(path: Path = DEFAULT_ENV_PATH) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


# 读取指定路径的 JSON 配置文件并返回字典数据。
def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


# 递归合并默认配置与用户覆盖配置并返回新字典。
def merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


# 加载默认配置并按需合并用户指定的配置文件。
def load_config(config_path: str | Path | None = None) -> AppConfig:
    load_dotenv_file()

    default_data = load_json(DEFAULT_CONFIG_PATH)
    if config_path is None:
        return AppConfig(path=DEFAULT_CONFIG_PATH, data=default_data)

    path = Path(config_path).expanduser().resolve()
    user_data = load_json(path)
    return AppConfig(path=path, data=merge_dict(default_data, user_data))
