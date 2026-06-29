"""用例生成 V1 Excel 导出。"""

from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from backend.app.test_cases.constants import (
    STANDARD_CASE_FIELD_LABELS,
    STANDARD_CASE_FIELDS,
)
from backend.app.test_cases.schemas import (
    GeneratedTestCase,
    TestCaseBlueprint,
    TestCaseExportRequest,
)


TEST_CASE_EXPORT_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

_SENSITIVE_PROFILE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "encrypted_api_key",
    "raw_prompt",
    "prompt",
    "system_prompt",
    "user_prompt",
    "provider_response",
    "raw_provider_response",
    "raw_response",
}


def build_test_case_export_workbook(payload: TestCaseExportRequest) -> BytesIO:
    """基于当前页面提交的结果构建用例生成导出工作簿。"""
    workbook = Workbook()
    case_sheet = workbook.active
    case_sheet.title = "测试用例"
    blueprint_sheet = workbook.create_sheet("用例蓝图")
    summary_sheet = workbook.create_sheet("生成说明")

    export_fields = resolve_export_fields(payload)
    _write_case_sheet(case_sheet, payload.cases, export_fields)
    _write_blueprint_sheet(blueprint_sheet, payload.blueprint)
    _write_summary_sheet(summary_sheet, payload, export_fields)

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


def resolve_export_fields(payload: TestCaseExportRequest) -> list[str]:
    """解析导出字段顺序：主参考可映射字段优先，标准字段兜底。"""
    return resolve_export_fields_from_reference_profile(
        payload.primary_reference_profile,
        fallback_fields=payload.export_columns,
    )


def resolve_export_fields_from_reference_profile(
    profile: dict[str, Any] | None,
    *,
    fallback_fields: list[str] | None = None,
) -> list[str]:
    """按主参考画像可识别字段生成导出字段顺序，缺失标准字段后置补齐。"""
    recognized_fields = _extract_profile_standard_fields(profile)
    if not recognized_fields and fallback_fields:
        recognized_fields = [field for field in fallback_fields if field in STANDARD_CASE_FIELDS]
    if not recognized_fields:
        recognized_fields = list(STANDARD_CASE_FIELDS)

    ordered_fields = _unique_preserve_order(
        [field for field in recognized_fields if field in STANDARD_CASE_FIELDS]
    )
    for field in STANDARD_CASE_FIELDS:
        if field not in ordered_fields:
            ordered_fields.append(field)
    return ordered_fields


def _write_case_sheet(
    sheet: Any,
    cases: list[GeneratedTestCase],
    export_fields: list[str],
) -> None:
    sheet.append([STANDARD_CASE_FIELD_LABELS[field] for field in export_fields])
    for case in cases:
        data = case.model_dump(mode="json")
        sheet.append([_format_cell_value(data.get(field, "")) for field in export_fields])

    sheet.freeze_panes = "A2"
    _style_header(sheet, 1)
    _auto_fit_columns(sheet)


def _write_blueprint_sheet(sheet: Any, blueprint: TestCaseBlueprint) -> None:
    sheet.append(["区块", "内容"])
    rows = [
        ("模块树", blueprint.modules),
        ("核心流程", blueprint.flows),
        ("需求追踪", blueprint.requirement_traces),
        ("覆盖维度", blueprint.coverage_dimensions),
        ("风险点", blueprint.risks),
        ("未映射需求", blueprint.unmapped_requirements),
        ("无依据测试点", blueprint.unsupported_or_unfounded_test_points),
        ("待确认问题", blueprint.open_questions),
        ("蓝图 warnings", [warning.model_dump(mode="json") for warning in blueprint.warnings]),
    ]
    for title, value in rows:
        sheet.append([title, _format_cell_value(value)])

    sheet.freeze_panes = "A2"
    _style_header(sheet, 1)
    _auto_fit_columns(sheet)


def _write_summary_sheet(
    sheet: Any,
    payload: TestCaseExportRequest,
    export_fields: list[str],
) -> None:
    sheet.append(["项目", "类型", "内容"])
    rows = [
        ("生成时间", "meta", datetime.now().isoformat(sep=" ", timespec="seconds")),
        ("策划案来源", "source", payload.source_summary),
        ("导出字段", "fields", "、".join(STANDARD_CASE_FIELD_LABELS[field] for field in export_fields)),
        ("用例总数", "stats", payload.stats.total),
        ("优先级分布", "stats", payload.stats.priority_counts),
        ("模块分布", "stats", payload.stats.module_counts),
        ("用例类型分布", "stats", payload.stats.case_type_counts),
        ("warning 数", "stats", payload.stats.warning_count),
        ("主参考画像", "reference", _summarize_primary_reference_profile(payload.primary_reference_profile)),
        (
            "V1 限制",
            "limit",
            "导出完全基于当前页面提交的 blueprint/cases/warnings/stats；"
            "不读取生成历史，不写入完整 API Key、原始 prompt 或 provider response。",
        ),
    ]
    for row in rows:
        sheet.append([_format_cell_value(item) for item in row])
    for warning in payload.warnings:
        sheet.append(["warning", warning.level, warning.message])

    sheet.freeze_panes = "A2"
    _style_header(sheet, 1)
    _auto_fit_columns(sheet)


def _extract_profile_standard_fields(profile: dict[str, Any] | None) -> list[str]:
    if not isinstance(profile, dict):
        return []

    fields: list[str] = []
    for item in _iter_profile_columns(profile):
        if isinstance(item, str):
            standard_field = item
        elif isinstance(item, dict):
            standard_field = _first_text(
                item,
                "standard_field",
                "mapped_standard_field",
                "mapped_field",
                "standard_key",
                "field",
            )
        else:
            continue

        if standard_field in STANDARD_CASE_FIELDS:
            fields.append(standard_field)
    return _unique_preserve_order(fields)


def _iter_profile_columns(profile: dict[str, Any]) -> list[Any]:
    selected_sheet_name = _first_text(
        profile,
        "selected_sheet_name",
        "sheet_name",
        "primary_reference_sheet_name",
    )
    default_sheet_name = _first_text(profile, "default_sheet_name")
    for sheet_key in ("sheet_options", "sheets"):
        sheets = profile.get(sheet_key)
        if not isinstance(sheets, list):
            continue
        if selected_sheet_name:
            selected_columns = _find_sheet_columns(sheets, selected_sheet_name)
            if selected_columns:
                return selected_columns
        if default_sheet_name:
            default_columns = _find_sheet_columns(sheets, default_sheet_name)
            if default_columns:
                return default_columns

    for key in ("columns", "fields", "ordered_columns", "field_order"):
        value = profile.get(key)
        if isinstance(value, list):
            return value

    for key in ("selected_sheet_profile", "sheet_profile", "primary_sheet_profile"):
        nested = profile.get(key)
        if isinstance(nested, dict):
            nested_columns = _iter_profile_columns(nested)
            if nested_columns:
                return nested_columns

    return []


def _find_sheet_columns(sheets: list[Any], sheet_name: str) -> list[Any]:
    for item in sheets:
        if not isinstance(item, dict):
            continue
        if _first_text(item, "name", "sheet_name") != sheet_name:
            continue
        columns = item.get("columns")
        if isinstance(columns, list):
            return columns
    return []


def _summarize_primary_reference_profile(profile: dict[str, Any] | None) -> str:
    if not isinstance(profile, dict):
        return "未使用主参考"

    safe_summary: dict[str, Any] = {}
    for key in ("name", "file_name", "filename", "sheet_name", "default_sheet_name"):
        value = profile.get(key)
        if value is not None:
            safe_summary[key] = value
    mapped_fields = _extract_profile_standard_fields(profile)
    if mapped_fields:
        safe_summary["mapped_standard_fields"] = mapped_fields
    return _format_cell_value(safe_summary or "已使用主参考画像")


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _style_header(sheet: Any, row_index: int) -> None:
    fill = PatternFill("solid", fgColor="EAF2FF")
    font = Font(bold=True, color="1F2A44")
    for cell in sheet[row_index]:
        cell.fill = fill
        cell.font = font


def _auto_fit_columns(sheet: Any) -> None:
    for column_cells in sheet.columns:
        max_length = 0
        column_index = column_cells[0].column
        for cell in column_cells:
            max_length = max(max_length, len(str(cell.value or "")))
        sheet.column_dimensions[get_column_letter(column_index)].width = min(
            max(max_length + 2, 12),
            60,
        )


def _format_cell_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(_sanitize_json_value(value), ensure_ascii=False)
    return str(value)


def _sanitize_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, child in value.items():
            normalized_key = str(key).strip().lower()
            if normalized_key in _SENSITIVE_PROFILE_KEYS:
                continue
            sanitized[str(key)] = _sanitize_json_value(child)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    return value


def _unique_preserve_order(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
