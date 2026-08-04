from __future__ import annotations

from pathlib import Path

from excel_agent.config import PROJECT_ROOT, AppConfig, load_json
from excel_agent.excel.reader import read_excel_input
from excel_agent.excel.validator import build_parse_summary
from excel_agent.models import ExcelTemplate, FileParseResult, ParseSummary


def resolve_project_path(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def load_template(config: AppConfig) -> ExcelTemplate:
    template_path = resolve_project_path(config.data.get("template_path", "config/template.json"))
    template_data = load_json(template_path)
    return ExcelTemplate.from_dict(template_data)


def parse_excel_input(input_path: Path, config: AppConfig) -> tuple[list[FileParseResult], ParseSummary]:
    template = load_template(config)
    results = read_excel_input(input_path, template)
    summary = build_parse_summary(results)
    return results, summary
