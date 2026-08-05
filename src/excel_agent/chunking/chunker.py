from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from excel_agent.cache.cache_manager import get_chunks_dir, get_chunks_manifest_path
from excel_agent.cache.serializers import read_jsonl, write_json
from excel_agent.chunking.budget import estimate_chunk_budget
from excel_agent.models import RawMessage

EMPTY_GROUP_NAME = "<EMPTY_GROUP>"


@dataclass(frozen=True)
class ChunkConfig:
    size: int = 50
    overlap: int = 15
    auto_shrink: bool = True
    reserve_chunk_tokens: int = 60000

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
    return ChunkConfig(
        size=size,
        overlap=overlap,
        auto_shrink=bool(auto_shrink),
        reserve_chunk_tokens=reserve_chunk_tokens,
    )


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _non_negative_int(value: object, default: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def load_effective_messages(path: Path) -> list[RawMessage]:
    return [RawMessage.from_dict(record) for record in read_jsonl(path)]


def group_messages(messages: list[RawMessage]) -> dict[tuple[str, str], list[RawMessage]]:
    grouped: dict[tuple[str, str], list[RawMessage]] = defaultdict(list)
    for message in messages:
        group_key = message.group_name or EMPTY_GROUP_NAME
        grouped[(message.source_file, group_key)].append(message)

    return {
        key: sorted(items, key=lambda message: (message.chat_time, message.row_id))
        for key, items in grouped.items()
    }


def make_chunk_id(index: int) -> str:
    return f"chunk_{index:06d}"


def build_chunk_metadata(
    *,
    chunk_id: str,
    source_file: str,
    group_name: str,
    messages: list[RawMessage],
    overlap_from_prev: int,
    relative_path: str,
    config: ChunkConfig,
) -> dict[str, object]:
    budget = estimate_chunk_budget(messages, config.reserve_chunk_tokens)
    return {
        "chunk_id": chunk_id,
        "source_file": source_file,
        "group_name": group_name,
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
        "path": relative_path,
    }


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


def build_chunks_for_source(
    *,
    source_file: Path,
    messages: list[RawMessage],
    config: ChunkConfig,
) -> ChunkBuildResult:
    run_id = source_file.stem
    chunks_dir = get_chunks_dir(source_file)
    manifest_path = get_chunks_manifest_path(source_file)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    grouped = group_messages(messages)
    chunks: list[dict[str, object]] = []
    group_summaries: list[dict[str, object]] = []
    warnings: list[str] = []
    chunk_index = 1
    empty_group_count = 0
    total_chunk_message_instances = 0

    for (group_source_file, group_name), group_messages_list in sorted(grouped.items(), key=lambda item: item[0]):
        group_chunk_count = 0
        if group_name == EMPTY_GROUP_NAME:
            empty_group_count += len(group_messages_list)

        for window, overlap_from_prev in iter_windows(group_messages_list, config):
            chunk_id = make_chunk_id(chunk_index)
            relative_path = f"chunks/{chunk_id}.json"
            metadata = build_chunk_metadata(
                chunk_id=chunk_id,
                source_file=group_source_file,
                group_name=group_name,
                messages=window,
                overlap_from_prev=overlap_from_prev,
                relative_path=relative_path,
                config=config,
            )
            chunk_data = {key: value for key, value in metadata.items() if key != "path"}
            chunk_data["messages"] = [message.to_dict() for message in window]
            write_json(chunks_dir / f"{chunk_id}.json", chunk_data)
            chunks.append(metadata)
            chunk_index += 1
            group_chunk_count += 1
            total_chunk_message_instances += len(window)

        group_summaries.append(
            {
                "source_file": group_source_file,
                "group_name": group_name,
                "message_count": len(group_messages_list),
                "chunk_count": group_chunk_count,
            }
        )

    if empty_group_count:
        warnings.append(f"存在 {empty_group_count} 条有效消息 group_name 为空，已作为 {EMPTY_GROUP_NAME} 单独切块")

    manifest = {
        "run_id": run_id,
        "source_file": source_file.name,
        "chunk_size": config.size,
        "chunk_overlap": config.overlap,
        "auto_shrink": config.auto_shrink,
        "auto_shrink_applied": False,
        "total_effective_messages": len(messages),
        "total_chunks": len(chunks),
        "total_chunk_message_instances": total_chunk_message_instances,
        "total_overlap_messages": total_chunk_message_instances - len(messages),
        "groups": group_summaries,
        "warnings": warnings,
        "chunks": chunks,
    }
    write_json(manifest_path, manifest)

    return ChunkBuildResult(
        source_file=source_file.name,
        run_id=run_id,
        manifest_path=manifest_path,
        total_effective_messages=len(messages),
        total_chunks=len(chunks),
        total_chunk_message_instances=total_chunk_message_instances,
        total_overlap_messages=total_chunk_message_instances - len(messages),
    )
