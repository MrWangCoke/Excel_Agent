from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from excel_agent.cache.cache_manager import (
    build_group_id,
    get_group_chunks_dir,
    get_group_chunks_manifest_path,
)
from excel_agent.cache.serializers import write_json
from excel_agent.chunking.budget import estimate_chunk_budget
from excel_agent.models import RawMessage

EMPTY_GROUP_NAME = "<EMPTY_GROUP>"


@dataclass(frozen=True)
class ChunkConfig:
    size: int = 50
    overlap: int = 15
    auto_shrink: bool = True
    reserve_chunk_tokens: int = 60000
    rebuild_window_days: int = 1

    # 计算滑动窗口每次向前移动的消息数量。
    @property
    def step(self) -> int:
        return self.size - self.overlap


@dataclass(frozen=True)
class ChunkBuildResult:
    source_file: str
    run_id: str
    manifest_path: Path
    total_effective_messages: int
    total_chunks: int
    total_chunk_message_instances: int
    total_overlap_messages: int


@dataclass(frozen=True)
class GroupChunkBuildResult:
    group_id: str
    group_name: str
    manifest_path: Path
    total_deduped_messages: int
    total_chunks: int
    total_chunk_message_instances: int
    total_overlap_messages: int


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    relative_path: str
    metadata: dict[str, object]


# 从运行配置中读取并校验消息块大小、重叠和预算参数。
def build_chunk_config(config_data: dict[str, object]) -> ChunkConfig:
    chunk_data = config_data.get("chunk", {})
    budget_data = config_data.get("context_budget", {})
    if not isinstance(chunk_data, dict):
        chunk_data = {}
    if not isinstance(budget_data, dict):
        budget_data = {}

    size = _positive_int(chunk_data.get("size"), 50)
    overlap = _non_negative_int(chunk_data.get("overlap"), 15)
    if overlap >= size:
        overlap = max(0, size - 1)

    auto_shrink = chunk_data.get("auto_shrink", True)
    reserve_chunk_tokens = _positive_int(budget_data.get("reserve_chunk_tokens"), 60000)
    rebuild_window_days = _positive_int(chunk_data.get("rebuild_window_days"), 1)
    return ChunkConfig(
        size=size,
        overlap=overlap,
        auto_shrink=bool(auto_shrink),
        reserve_chunk_tokens=reserve_chunk_tokens,
        rebuild_window_days=rebuild_window_days,
    )


# 将配置值解析为正整数，失败时返回默认值。
def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


# 将配置值解析为非负整数，失败时返回默认值。
def _non_negative_int(value: object, default: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


# 按来源文件和群名称归集消息，并在各组内按时间排序。
def group_messages(messages: list[RawMessage]) -> dict[tuple[str, str], list[RawMessage]]:
    grouped: dict[tuple[str, str], list[RawMessage]] = defaultdict(list)
    for message in messages:
        group_key = message.group_name or EMPTY_GROUP_NAME
        grouped[(message.source_file, group_key)].append(message)

    return {
        key: sorted(items, key=lambda message: (message.chat_time, message.row_id))
        for key, items in grouped.items()
    }


# 按固定大小和重叠数量迭代生成连续消息窗口。
def iter_windows(messages: list[RawMessage], config: ChunkConfig) -> Iterator[tuple[list[RawMessage], int]]:
    start = 0
    is_first = True
    while start < len(messages):
        end = min(start + config.size, len(messages))
        window = messages[start:end]
        overlap_from_prev = 0 if is_first else min(config.overlap, len(window))
        yield window, overlap_from_prev
        if end == len(messages):
            break
        start += config.step
        is_first = False


# 将时间格式化为适合 chunk 文件名使用的无冒号字符串。
def format_chunk_time(value) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


# 根据 chunk 内消息内容生成稳定的短指纹。
def build_chunk_fingerprint(messages: list[RawMessage]) -> str:
    payload = "\n".join(
        f"{message.source_file}|{message.row_id}|{message.chat_time.isoformat(sep=' ')}|"
        f"{message.group_name}|{message.sender_raw}|{message.message_type}|{message.content_raw}"
        for message in messages
    )
    return sha256(payload.encode("utf-8")).hexdigest()[:8]


# 根据消息时间范围和内容指纹生成 chunk 标识。
def make_time_range_chunk_id(messages: list[RawMessage]) -> tuple[str, str]:
    fingerprint = build_chunk_fingerprint(messages)
    start_time = format_chunk_time(messages[0].chat_time)
    end_time = format_chunk_time(messages[-1].chat_time)
    chunk_id = f"chunk_{start_time}_{end_time}__{fingerprint}"
    return chunk_id, fingerprint


# 构造单个 chunk 的时间、数量、预算和文件路径等元数据。
def build_chunk_metadata(
    *,
    chunk_id: str,
    group_id: str,
    group_name: str,
    source_files: list[str],
    messages: list[RawMessage],
    overlap_from_prev: int,
    relative_path: str,
    config: ChunkConfig,
    chunk_fingerprint: str,
) -> dict[str, object]:
    budget = estimate_chunk_budget(messages, config.reserve_chunk_tokens)
    return {
        "chunk_id": chunk_id,
        "group_id": group_id,
        "group_name": group_name,
        "source_files": source_files,
        "start_time": messages[0].chat_time.isoformat(sep=" "),
        "end_time": messages[-1].chat_time.isoformat(sep=" "),
        "row_id_start": messages[0].row_id,
        "row_id_end": messages[-1].row_id,
        "message_count": len(messages),
        "image_count": sum(1 for message in messages if message.message_type == "图片"),
        "quote_count": sum(1 for message in messages if message.message_type == "引用消息"),
        "overlap_from_prev": overlap_from_prev,
        "estimated_tokens": budget.estimated_tokens,
        "budget_status": budget.budget_status,
        "chunk_fingerprint": chunk_fingerprint,
        "path": relative_path,
    }


# 为单个群聊按连续时间线生成 chunk 文件和 manifest 清单。
def build_chunks_for_group(
    *,
    group_name: str,
    messages: list[RawMessage],
    config: ChunkConfig,
) -> GroupChunkBuildResult:
    group_id = build_group_id(group_name)
    chunks_dir = get_group_chunks_dir(group_name)
    manifest_path = get_group_chunks_manifest_path(group_name)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    sorted_messages = sorted(messages, key=lambda message: (message.chat_time, message.row_id, message.source_file))
    chunks: list[dict[str, object]] = []
    warnings: list[str] = []
    total_chunk_message_instances = 0

    for window, overlap_from_prev in iter_windows(sorted_messages, config):
        chunk_id, fingerprint = make_time_range_chunk_id(window)
        relative_path = f"chunks/{chunk_id}.json"
        source_files = sorted({message.source_file for message in window})
        metadata = build_chunk_metadata(
            chunk_id=chunk_id,
            group_id=group_id,
            group_name=group_name,
            source_files=source_files,
            messages=window,
            overlap_from_prev=overlap_from_prev,
            relative_path=relative_path,
            config=config,
            chunk_fingerprint=fingerprint,
        )
        chunk_data = {key: value for key, value in metadata.items() if key != "path"}
        chunk_data["messages"] = [message.to_dict() for message in window]
        write_json(chunks_dir / f"{chunk_id}.json", chunk_data)
        chunks.append(metadata)
        total_chunk_message_instances += len(window)

    if not group_name:
        warnings.append("群名称为空，已统一进入 g_empty__empty_group")

    manifest = {
        "group_id": group_id,
        "group_name": group_name,
        "chunk_size": config.size,
        "chunk_overlap": config.overlap,
        "rebuild_window_days": config.rebuild_window_days,
        "auto_shrink": config.auto_shrink,
        "auto_shrink_applied": False,
        "total_deduped_messages": len(sorted_messages),
        "total_chunks": len(chunks),
        "total_chunk_message_instances": total_chunk_message_instances,
        "total_overlap_messages": total_chunk_message_instances - len(sorted_messages),
        "warnings": warnings,
        "chunks": chunks,
    }
    write_json(manifest_path, manifest)

    return GroupChunkBuildResult(
        group_id=group_id,
        group_name=group_name,
        manifest_path=manifest_path,
        total_deduped_messages=len(sorted_messages),
        total_chunks=len(chunks),
        total_chunk_message_instances=total_chunk_message_instances,
        total_overlap_messages=total_chunk_message_instances - len(sorted_messages),
    )


# 兼容按来源构建 chunk 的旧入口，并汇总各群的切块统计。
def build_chunks_for_source(
    *,
    source_file: Path,
    messages: list[RawMessage],
    config: ChunkConfig,
) -> ChunkBuildResult:
    grouped = group_messages(messages)
    group_results = [
        build_chunks_for_group(group_name=group_name if group_name != EMPTY_GROUP_NAME else "", messages=items, config=config)
        for (_, group_name), items in sorted(grouped.items(), key=lambda item: item[0])
    ]
    total_messages = len(messages)
    total_chunks = sum(result.total_chunks for result in group_results)
    total_instances = sum(result.total_chunk_message_instances for result in group_results)
    manifest_path = group_results[0].manifest_path if group_results else Path()
    return ChunkBuildResult(
        source_file=source_file.name,
        run_id=source_file.stem,
        manifest_path=manifest_path,
        total_effective_messages=total_messages,
        total_chunks=total_chunks,
        total_chunk_message_instances=total_instances,
        total_overlap_messages=total_instances - total_messages,
    )
