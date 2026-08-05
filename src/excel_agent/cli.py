from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import PROJECT_ROOT, load_config
from .excel.reader import ExcelReadError
from .excel.validator import ExcelValidationError
from .pipeline import run_steps_1_to_4

DEFAULT_INPUT_PATH = PROJECT_ROOT / "data"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "output"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="excel-agent",
        description="读取 Excel 群聊记录，提取问题并输出 Markdown 问题列表。",
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT_PATH),
        help=f"Excel 文件或包含 Excel 文件的文件夹路径，默认 {DEFAULT_INPUT_PATH}。",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help=f"Markdown 输出根目录，默认 {DEFAULT_OUTPUT_PATH}。",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="配置文件路径，默认使用 config/default.json。",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="从已落盘的中间结果继续运行。",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="不调用模型，用规则占位跑通流程。",
    )
    return parser


def validate_paths(input_path: Path, output_path: Path) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"输入路径不存在：{input_path}")

    if input_path.is_file() and input_path.suffix.lower() != ".xlsx":
        raise ValueError(f"输入文件必须是 .xlsx：{input_path}")

    output_path.mkdir(parents=True, exist_ok=True)


def build_startup_summary(args: argparse.Namespace) -> dict[str, str]:
    config = load_config(args.config)
    return {
        "input": str(Path(args.input).expanduser().resolve()),
        "output": str(Path(args.output).expanduser().resolve()),
        "config": str(config.path),
        "resume": str(args.resume),
        "mock": str(args.mock),
        "model": config.llm_model or "未配置",
        "base_url": config.llm_base_url or "未配置",
    }


def print_startup_summary(args: argparse.Namespace) -> None:
    summary = build_startup_summary(args)
    print("Excel Agent 启动参数")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def print_parse_summary(summary: dict[str, object]) -> None:
    print("Excel 解析摘要")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def print_preprocess_reports(reports: list[dict[str, object]]) -> None:
    print("消息预处理报告")
    print(json.dumps(reports, ensure_ascii=False, indent=2))


def print_chunk_reports(reports: list[dict[str, object]]) -> None:
    print("消息切块报告")
    print(json.dumps(reports, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    try:
        validate_paths(input_path, output_path)
        print_startup_summary(args)

        config = load_config(args.config)
        _, summary, _, preprocess_reports, chunk_results = run_steps_1_to_4(input_path, config)
        print_parse_summary(summary.to_dict())
        print_preprocess_reports([report.to_dict() for report in preprocess_reports])
        print_chunk_reports(
            [
                {
                    "source_file": result.source_file,
                    "run_id": result.run_id,
                    "manifest_path": str(result.manifest_path),
                    "total_effective_messages": result.total_effective_messages,
                    "total_chunks": result.total_chunks,
                    "total_chunk_message_instances": result.total_chunk_message_instances,
                    "total_overlap_messages": result.total_overlap_messages,
                }
                for result in chunk_results
            ]
        )
    except (
        ExcelReadError,
        ExcelValidationError,
        FileNotFoundError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"启动失败：{exc}")
        return 1

    print("步骤 4 消息切块已完成；chunks 和 chunks_manifest.json 已写入 .cache/<run_id>/。")
    return 0
