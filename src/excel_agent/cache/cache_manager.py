from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path

from excel_agent.config import PROJECT_ROOT

CACHE_ROOT = PROJECT_ROOT / ".cache"
EMPTY_GROUP_FOLDER = "g_empty__empty_group"
EMPTY_GROUP_ID = "g_empty"
INVALID_PATH_CHARS = re.compile(r'[/\\:*?"<>|]')
WHITESPACE = re.compile(r"\s+")


def normalize_name(value: str) -> str:
    return WHITESPACE.sub(" ", value.strip())


def safe_path_part(value: str, *, default: str, max_length: int = 48) -> str:
    text = normalize_name(value)
    text = INVALID_PATH_CHARS.sub("_", text)
    text = re.sub(r"_+", "_", text).strip(" ._")
    if not text:
        text = default
    if len(text) > max_length:
        text = text[:max_length].rstrip(" ._")
    return text or default


def short_hash(value: str, length: int = 8) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:length]


def build_file_fingerprint(source_file: Path) -> str:
    if source_file.exists():
        stat = source_file.stat()
        payload = f"{source_file.name}|{stat.st_size}|{stat.st_mtime_ns}"
    else:
        payload = source_file.name
    return short_hash(payload)


def build_source_id(source_file: Path) -> str:
    safe_name = safe_path_part(source_file.stem, default="source")
    return f"s_{safe_name}__{build_file_fingerprint(source_file)}"


def build_group_id(group_name: str) -> str:
    normalized = normalize_name(group_name)
    if not normalized:
        return EMPTY_GROUP_ID
    return f"g_{short_hash(normalized)}"


def build_group_folder_name(group_name: str) -> str:
    normalized = normalize_name(group_name)
    if not normalized:
        return EMPTY_GROUP_FOLDER
    safe_name = safe_path_part(normalized, default="group")
    return f"{build_group_id(normalized)}__{safe_name}"


def get_state_path(cache_root: Path = CACHE_ROOT) -> Path:
    return cache_root / "state.json"


def get_sources_root(cache_root: Path = CACHE_ROOT) -> Path:
    return cache_root / "sources"


def get_source_dir(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_sources_root(cache_root) / build_source_id(source_file)


def get_source_meta_path(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_source_dir(source_file, cache_root) / "source_meta.json"


def get_parsed_messages_path(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_source_dir(source_file, cache_root) / "parsed_messages.jsonl"


def get_source_effective_messages_path(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_source_dir(source_file, cache_root) / "effective_messages.jsonl"


def get_source_preprocess_report_path(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_source_dir(source_file, cache_root) / "preprocess_report.json"


def get_groups_root(cache_root: Path = CACHE_ROOT) -> Path:
    return cache_root / "groups"


def get_group_dir(group_name: str, cache_root: Path = CACHE_ROOT) -> Path:
    return get_groups_root(cache_root) / build_group_folder_name(group_name)


def get_group_meta_path(group_name: str, cache_root: Path = CACHE_ROOT) -> Path:
    return get_group_dir(group_name, cache_root) / "group_meta.json"


def get_group_state_path(group_name: str, cache_root: Path = CACHE_ROOT) -> Path:
    return get_group_dir(group_name, cache_root) / "group_state.json"


def get_group_effective_messages_path(group_name: str, cache_root: Path = CACHE_ROOT) -> Path:
    return get_group_dir(group_name, cache_root) / "effective_messages.jsonl"


def get_group_deduped_messages_path(group_name: str, cache_root: Path = CACHE_ROOT) -> Path:
    return get_group_dir(group_name, cache_root) / "deduped_messages.jsonl"


def get_group_duplicate_messages_path(group_name: str, cache_root: Path = CACHE_ROOT) -> Path:
    return get_group_dir(group_name, cache_root) / "duplicate_messages.jsonl"


def get_group_dedupe_report_path(group_name: str, cache_root: Path = CACHE_ROOT) -> Path:
    return get_group_dir(group_name, cache_root) / "dedupe_report.json"


def get_group_chunks_dir(group_name: str, cache_root: Path = CACHE_ROOT) -> Path:
    return get_group_dir(group_name, cache_root) / "chunks"


def get_group_chunks_manifest_path(group_name: str, cache_root: Path = CACHE_ROOT) -> Path:
    return get_group_dir(group_name, cache_root) / "chunks_manifest.json"


def get_group_issues_dir(group_name: str, cache_root: Path = CACHE_ROOT) -> Path:
    return get_group_dir(group_name, cache_root) / "issues"


def get_group_issue_store_path(group_name: str, cache_root: Path = CACHE_ROOT) -> Path:
    return get_group_issues_dir(group_name, cache_root) / "issue_store.json"


def get_group_issue_index_path(group_name: str, cache_root: Path = CACHE_ROOT) -> Path:
    return get_group_issues_dir(group_name, cache_root) / "issue_index.json"


def get_group_llm_context_dir(group_name: str, cache_root: Path = CACHE_ROOT) -> Path:
    return get_group_dir(group_name, cache_root) / "llm_context"


def get_group_llm_context_manifest_path(group_name: str, cache_root: Path = CACHE_ROOT) -> Path:
    return get_group_dir(group_name, cache_root) / "llm_context_manifest.json"


def get_group_llm_results_dir(group_name: str, cache_root: Path = CACHE_ROOT) -> Path:
    return get_group_dir(group_name, cache_root) / "llm_results"


# Legacy per-source/run helpers kept for compatibility with earlier modules/tests.
def build_run_id(source_file: Path) -> str:
    return source_file.stem


def get_run_dir(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return cache_root / build_run_id(source_file)


def get_effective_messages_path(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_source_effective_messages_path(source_file, cache_root)


def get_deduped_messages_path(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_run_dir(source_file, cache_root) / "deduped_messages.jsonl"


def get_duplicate_messages_path(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_run_dir(source_file, cache_root) / "duplicate_messages.jsonl"


def get_dedupe_report_path(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_run_dir(source_file, cache_root) / "dedupe_report.json"


def get_preprocess_report_path(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_source_preprocess_report_path(source_file, cache_root)


def get_chunks_dir(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_run_dir(source_file, cache_root) / "chunks"


def get_chunks_manifest_path(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_run_dir(source_file, cache_root) / "chunks_manifest.json"


def get_issues_dir(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_run_dir(source_file, cache_root) / "issues"


def get_issue_store_path(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_issues_dir(source_file, cache_root) / "issue_store.json"


def get_issue_index_path(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_issues_dir(source_file, cache_root) / "issue_index.json"


def get_chunk_candidates_dir(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_run_dir(source_file, cache_root) / "chunk_candidates"


def get_candidates_manifest_path(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_run_dir(source_file, cache_root) / "candidates_manifest.json"
