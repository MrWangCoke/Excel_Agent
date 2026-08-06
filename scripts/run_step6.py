from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

config_module: Any = importlib.import_module("excel_agent.config")
runner_module: Any = importlib.import_module("excel_agent.llm.runner")
load_config = config_module.load_config
extract_group_chunks = runner_module.extract_group_chunks


# 创建步骤 6 群级运行脚本的命令行参数解析器。
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="仅对指定 group 缓存目录执行步骤 6 LLM 提取。")
    parser.add_argument("--group-dir", required=True, help="指定 .cache/groups 下的单个群文件夹。")
    parser.add_argument("--config", default=None, help="可选配置文件路径。")
    parser.add_argument("--max-chunks", type=int, default=None, help="最多处理多少个 chunk，测试时建议设为 1。")
    parser.add_argument("--chunk-id", default=None, help="只处理指定 chunk_id。")
    parser.add_argument("--resume", action="store_true", help="复用 fingerprint 匹配的已有 llm_results。")
    parser.add_argument("--mock", action="store_true", help="不调用模型，只生成空结果验证流程。")
    return parser


# 执行指定群的步骤 6 并打印汇总结果。
def main() -> int:
    args = build_parser().parse_args()
    config = load_config(args.config)
    result = extract_group_chunks(
        group_folder=Path(args.group_dir),
        config=config,
        mock=args.mock,
        max_chunks=args.max_chunks,
        chunk_id=args.chunk_id,
        resume=args.resume,
    )
    print(
        json.dumps(
            {
                "group_folder": str(result.group_folder),
                "manifest_path": str(result.manifest_path),
                "total_chunks": result.total_chunks,
                "completed_chunks": result.completed_chunks,
                "total_issues": result.total_issues,
                "total_warnings": result.total_warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
