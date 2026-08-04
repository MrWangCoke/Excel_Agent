from __future__ import annotations

from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from excel_agent.models import ExcelTemplate, FileParseResult, RawMessage

SUPPORTED_SUFFIXES = {".xlsx"}


class ExcelReadError(RuntimeError):
    pass


def load_pandas() -> Any:
    try:
        return import_module("pandas")
    except ImportError as exc:
        raise ExcelReadError("缺少 pandas 依赖，请先运行 pip install -r requirements.txt") from exc


#找出要处理的文件
def discover_excel_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]

    return sorted(
        path
        for path in input_path.rglob("*.xlsx")
        if path.is_file() and not path.name.startswith("~$")
    )


#把单元格值弄干净
def normalize_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


#把时间字符串变成 datetime
def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    if not text:
        return None

    pd = load_pandas()
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return cast(datetime, parsed.to_pydatetime())


#把 Excel 读成表格
def load_dataframe(file_path: Path) -> Any:
    pd = load_pandas()

    try:
        return pd.read_excel(
            file_path,
            engine="openpyxl",
            dtype=str,
            keep_default_na=False,
        )
    except ImportError as exc:
        raise ExcelReadError("缺少 openpyxl 依赖，请先运行 pip install -r requirements.txt") from exc
    except (OSError, ValueError) as exc:
        raise ExcelReadError(f"读取 Excel 失败：{file_path}；原因：{exc}") from exc


#校验表头齐不齐
def validate_required_columns(actual_columns: set[str], expected_columns: dict[str, str], source_file: Path) -> None:
    missing = [column_name for column_name in expected_columns.values() if column_name not in actual_columns]
    if missing:
        missing_text = "、".join(missing)
        raise ExcelReadError(f"{source_file.name} 缺少必需表头：{missing_text}")


#数每列空了几个
def count_empty_values(dataframe: Any, columns: dict[str, str]) -> dict[str, int]:
    empty_counts: dict[str, int] = {}
    for field_name, column_name in columns.items():
        series = dataframe[column_name].map(normalize_cell)
        empty_counts[field_name] = int((series == "").sum())
    return empty_counts


# 一行变一条消息
def row_to_message(
    row_number: int,
    row: Any,
    source_file: Path,
    columns: dict[str, str],
) -> RawMessage | None:
    chat_time = parse_datetime(row.get(columns["chat_time"], ""))
    if chat_time is None:
        return None

    return RawMessage(
        row_id=row_number,
        source_file=source_file.name,
        employee_name=normalize_cell(row.get(columns["employee_name"], "")),
        employee_phone=normalize_cell(row.get(columns["employee_phone"], "")),
        employee_wechat_nickname=normalize_cell(row.get(columns["employee_wechat_nickname"], "")),
        employee_wechat_id=normalize_cell(row.get(columns["employee_wechat_id"], "")),
        group_name=normalize_cell(row.get(columns["group_name"], "")),
        message_type=normalize_cell(row.get(columns["message_type"], "")),
        sender_raw=normalize_cell(row.get(columns["sender"], "")),
        content_raw=normalize_cell(row.get(columns["content"], "")),
        chat_time=chat_time,
    )


#读一个文件,交成绩单
def read_excel_file(file_path: Path, template: ExcelTemplate) -> FileParseResult:
    dataframe = load_dataframe(file_path)
    validate_required_columns(set(dataframe.columns), template.columns, file_path)

    messages: list[RawMessage] = []
    warnings: list[str] = []

    for row_offset, row in enumerate(dataframe.to_dict("records")):
        row_number = row_offset + 2
        message = row_to_message(row_number, row, file_path, template.columns)
        if message is None:
            warnings.append(f"{file_path.name}: Excel 行 {row_number} 聊天时间为空或不可解析，已跳过")
            continue
        messages.append(message)

    return FileParseResult(
        source_file=file_path,
        total_rows=len(dataframe),
        messages=messages,
        empty_counts=count_empty_values(dataframe, template.columns),
        warnings=warnings,
    )


# 读"输入"(可能多个文件)
def read_excel_input(input_path: Path, template: ExcelTemplate) -> list[FileParseResult]:
    files = discover_excel_files(input_path)
    if not files:
        raise FileNotFoundError(f"未找到 .xlsx 文件：{input_path}")

    return [read_excel_file(file_path, template) for file_path in files]
