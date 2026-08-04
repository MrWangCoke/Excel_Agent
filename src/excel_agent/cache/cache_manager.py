from __future__ import annotations

from pathlib import Path

from excel_agent.config import PROJECT_ROOT

CACHE_ROOT = PROJECT_ROOT / ".cache"


def build_run_id(source_file: Path) -> str:
    return source_file.stem


def get_run_dir(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return cache_root / build_run_id(source_file)


def get_effective_messages_path(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_run_dir(source_file, cache_root) / "effective_messages.jsonl"


def get_preprocess_report_path(source_file: Path, cache_root: Path = CACHE_ROOT) -> Path:
    return get_run_dir(source_file, cache_root) / "preprocess_report.json"
