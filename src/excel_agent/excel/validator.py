from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import datetime

from excel_agent.models import FileParseResult, ParseSummary, RawMessage


class ExcelValidationError(ValueError):
    pass


CORE_NON_EMPTY_FIELDS = {
    "group_name": "群名称",
    "message_type": "消息类型",
    "sender_raw": "发送人",
    "content_raw": "消息内容",
}

EMPLOYEE_FIELDS = {
    "employee_name": "员工姓名",
    "employee_phone": "员工手机号",
    "employee_wechat_nickname": "员工微信昵称",
    "employee_wechat_id": "员工微信号",
}


# 获取消息指定字段的字符串值并清理首尾空白。
def get_field(message: RawMessage, field_name: str) -> str:
    return str(getattr(message, field_name)).strip()


# 去除空值和重复项后返回排序好的字符串列表。
def unique_sorted(values: Iterable[str]) -> list[str]:
    return sorted({value for value in values if value})


# 统计消息列表中每种非空消息类型的数量。
def count_message_types(messages: list[RawMessage]) -> dict[str, int]:
    counter = Counter(message.message_type for message in messages if message.message_type)
    return dict(sorted(counter.items()))


# 汇总多个 Excel 解析结果中各字段的空值数量。
def aggregate_empty_counts(results: list[FileParseResult]) -> dict[str, int]:
    totals: Counter[str] = Counter()
    for result in results:
        totals.update(result.empty_counts)
    return dict(sorted(totals.items()))


# 汇集解析过程中的原有警告和消息字段空值警告。
def collect_warnings(results: list[FileParseResult], messages: list[RawMessage]) -> list[str]:
    warnings: list[str] = []
    for result in results:
        warnings.extend(result.warnings)

    for field_name, label in CORE_NON_EMPTY_FIELDS.items():
        empty_count = sum(1 for message in messages if not get_field(message, field_name))
        if empty_count:
            warnings.append(f"字段 {label} 存在空值：{empty_count} 条")

    for field_name, label in EMPLOYEE_FIELDS.items():
        empty_count = sum(1 for message in messages if not get_field(message, field_name))
        if empty_count == len(messages) and messages:
            warnings.append(f"员工信息字段 {label} 整列为空")
        elif empty_count:
            warnings.append(f"员工信息字段 {label} 存在空值：{empty_count} 条")

    return warnings


# 检查解析结果是否存在阻止流程继续的致命错误。
def validate_no_fatal_errors(results: list[FileParseResult], messages: list[RawMessage]) -> None:
    if not results:
        raise ExcelValidationError("没有可校验的 Excel 解析结果")

    if not messages:
        raise ExcelValidationError("没有解析出任何有效消息，请检查表头和聊天时间列")

    for field_name, label in CORE_NON_EMPTY_FIELDS.items():
        empty_count = sum(1 for message in messages if not get_field(message, field_name))
        if empty_count == len(messages):
            raise ExcelValidationError(f"核心字段 {label} 整列为空，无法继续解析")


# 汇总多个文件的解析结果并生成整体解析摘要。
def build_parse_summary(results: list[FileParseResult]) -> ParseSummary:
    messages = [message for result in results for message in result.messages]
    validate_no_fatal_errors(results, messages)

    times: list[datetime] = [message.chat_time for message in messages]
    warnings = collect_warnings(results, messages)

    return ParseSummary(
        total_files=len(results),
        total_rows=sum(result.total_rows for result in results),
        total_messages=len(messages),
        time_start=min(times) if times else None,
        time_end=max(times) if times else None,
        groups=unique_sorted(message.group_name for message in messages),
        employees=unique_sorted(message.employee_name for message in messages),
        message_type_counts=count_message_types(messages),
        empty_counts=aggregate_empty_counts(results),
        warnings=warnings,
    )
