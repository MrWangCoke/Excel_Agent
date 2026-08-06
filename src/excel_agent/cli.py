from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import PROJECT_ROOT, load_config
from .excel.reader import ExcelReadError
from .excel.validator import ExcelValidationError
from .pipeline import run_steps_1_to_5

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


def print_json_report(title: str, data: object) -> None:
    print(title)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    try:
        validate_paths(input_path, output_path)
        print_json_report("Excel Agent 启动参数", build_startup_summary(args))

        config = load_config(args.config)
        (
            _,
            summary,
            _,
            preprocess_reports,
            deduped_groups,
            dedupe_reports,
            chunk_results,
            llm_context_results,
        ) = run_steps_1_to_5(input_path, config)
        print_json_report("Excel 解析摘要", summary.to_dict())
        print_json_report("消息预处理报告", [report.to_dict() for report in preprocess_reports])
        print_json_report(
            "群级消息去重报告",
            {
                "total_groups": len(dedupe_reports),
                "total_effective_messages": sum(report.total_messages for report in dedupe_reports),
                "total_deduped_messages": sum(report.deduped_messages for report in dedupe_reports),
                "total_duplicate_messages": sum(report.duplicate_messages for report in dedupe_reports),
                "groups_with_duplicates": sum(1 for report in dedupe_reports if report.duplicate_messages),
            },
        )
        print_json_report(
            "群级消息切块报告",
            {
                "total_groups": len(chunk_results),
                "total_deduped_messages": sum(result.total_deduped_messages for result in chunk_results),
                "total_chunks": sum(result.total_chunks for result in chunk_results),
                "total_chunk_message_instances": sum(result.total_chunk_message_instances for result in chunk_results),
                "total_overlap_messages": sum(result.total_overlap_messages for result in chunk_results),
            },
        )
        print_json_report(
            "LLM 上下文包报告",
            {
                "total_groups": len(deduped_groups),
                "total_chunks": sum(result.total_chunks for result in llm_context_results),
                "total_issue_context_items": sum(result.total_issue_context_items for result in llm_context_results),
                "total_dropped_issue_context_items": sum(
                    result.total_dropped_issue_context_items for result in llm_context_results
                ),
            },
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

    print("步骤 5 LLM 上下文包已完成；sources、groups、chunks、llm_context 和 issues 已写入 .cache/。")
    return 0
