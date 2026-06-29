"""参考案例库确定性画像。

V1 只做本地结构识别，不调用 AI，不把参考案例数量作为生成目标。
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import pandas as pd

from backend.app.test_cases.constants import (
    REFERENCE_ALLOWED_SUFFIXES,
    REFERENCE_DEFAULT_SHEET_NAMES,
    STANDARD_CASE_FIELD_LABELS,
)
from backend.app.test_cases.schemas import (
    GenerationWarning,
    ReferenceProfile,
    ReferenceProfileColumn,
    ReferenceSheetOption,
)


class ReferenceProfileError(ValueError):
    """参考案例无法生成确定性画像。"""


def _normalize_header(value: str) -> str:
    return re.sub(r"[\s_\-:：/（）()\[\]【】]+", "", value).lower()


_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "case_id": ("用例编号", "用例ID", "用例 Id", "用例号", "Case ID", "ID"),
    "module": ("功能模块", "模块", "所属模块", "一级模块"),
    "feature": ("功能点", "功能", "检查点", "测试点", "二级模块"),
    "scenario": ("测试场景", "场景", "业务场景"),
    "title": ("用例标题", "用例名称", "标题", "测试标题", "Test Case"),
    "preconditions": ("前置条件", "前置", "预置条件", "Prerequisite"),
    "steps": ("操作步骤", "测试步骤", "步骤", "Step", "Steps"),
    "expected_results": ("预期结果", "期望结果", "预期", "Expected Result"),
    "priority": ("优先级", "优先度", "级别", "Priority"),
    "case_type": ("用例类型", "类型", "Case Type"),
    "source_requirement": ("来源测试点", "需求依据", "需求来源", "需求", "检查点"),
    "config_source": ("配置来源", "配置", "配置项"),
    "planning_answer": ("策划答疑", "答疑", "策划备注"),
    "initial_status": ("初始状态", "状态", "执行状态"),
    "bug_link": ("Bug 链接", "Bug", "缺陷链接"),
    "remarks": ("备注", "说明", "Remark", "Comment"),
}

_ALIAS_LOOKUP = {
    _normalize_header(alias): field
    for field, aliases in _HEADER_ALIASES.items()
    for alias in aliases
}

_CORE_CASE_FIELDS = {
    "title",
    "steps",
    "expected_results",
    "source_requirement",
}
_CASE_SIGNAL_FIELDS = _CORE_CASE_FIELDS | {"case_id", "preconditions"}


def extract_reference_profile(path: Path | str) -> ReferenceProfile:
    """根据文件后缀生成参考案例确定性画像。"""
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix not in REFERENCE_ALLOWED_SUFFIXES:
        raise ReferenceProfileError(f"不支持的参考案例文件类型：{suffix}")
    if suffix in {".xlsx", ".xls"}:
        return _extract_excel_profile(file_path)
    return _extract_plain_text_profile(file_path)


def _extract_excel_profile(path: Path) -> ReferenceProfile:
    try:
        workbook = pd.ExcelFile(path, engine=_get_excel_engine(path))
    except ImportError as exc:
        raise ReferenceProfileError(_build_excel_dependency_error(path)) from exc
    except ValueError as exc:
        raise ReferenceProfileError(f"读取参考案例 Excel 失败：{exc}") from exc

    sheet_options: list[ReferenceSheetOption] = []
    warnings: list[GenerationWarning] = []

    try:
        sheet_names = list(workbook.sheet_names)
        for sheet_name in sheet_names:
            try:
                frame = workbook.parse(sheet_name=sheet_name, header=None, dtype=object)
            except ValueError as exc:
                warnings.append(
                    GenerationWarning(
                        source="reference_profile",
                        message=f"Sheet '{sheet_name}' 读取失败，已跳过：{exc}",
                    )
                )
                continue

            option = _profile_sheet(sheet_name, frame)
            if option is None:
                warnings.append(
                    GenerationWarning(
                        source="reference_profile",
                        message=f"Sheet '{sheet_name}' 未识别为可用测试用例 Sheet，已跳过。",
                    )
                )
                continue
            sheet_options.append(option)
    finally:
        workbook.close()

    if not sheet_options:
        raise ReferenceProfileError("没有可用的测试用例 Sheet，已拒绝上传。")

    default_option = _select_default_sheet(sheet_options)
    for option in sheet_options:
        option.is_default = option.name == default_option.name

    return ReferenceProfile(
        source_type="excel",
        source_name=path.name,
        default_sheet_name=default_option.name,
        reference_case_count=default_option.reference_case_count,
        columns=default_option.columns,
        sheet_options=sheet_options,
        warnings=warnings,
    )


def _profile_sheet(
    sheet_name: str,
    frame: pd.DataFrame,
) -> ReferenceSheetOption | None:
    header = _detect_header(frame)
    if header is None:
        return None

    header_row_index, mapped_fields = header
    columns = _build_columns(frame.iloc[header_row_index].tolist(), mapped_fields)
    reference_case_count = _count_case_rows(
        frame,
        header_row_index=header_row_index,
        mapped_fields=mapped_fields,
    )
    if reference_case_count <= 0:
        return None

    return ReferenceSheetOption(
        name=sheet_name,
        reference_case_count=reference_case_count,
        header_row_index=header_row_index + 1,
        columns=columns,
    )


def _detect_header(frame: pd.DataFrame) -> tuple[int, list[str | None]] | None:
    best: tuple[int, int, list[str | None]] | None = None
    row_count = min(len(frame.index), 20)
    for row_index in range(row_count):
        raw_values = frame.iloc[row_index].tolist()
        normalized_values = [_normalize_cell(value) for value in raw_values]
        mapped_fields = [_map_header(value) for value in normalized_values]
        mapped_unique = {field for field in mapped_fields if field}
        if len(mapped_unique) < 2:
            continue
        if not mapped_unique.intersection(_CORE_CASE_FIELDS):
            continue
        non_empty_count = sum(1 for value in normalized_values if value)
        score = len(mapped_unique) * 10
        score += len(mapped_unique.intersection(_CORE_CASE_FIELDS)) * 6
        score += min(non_empty_count, 12)
        if best is None or score > best[1]:
            best = (row_index, score, mapped_fields)
    if best is None:
        return None
    return best[0], best[2]


def _build_columns(
    raw_headers: list[Any],
    mapped_fields: list[str | None],
) -> list[ReferenceProfileColumn]:
    columns: list[ReferenceProfileColumn] = []
    for index, raw_header in enumerate(raw_headers, start=1):
        original_name = _normalize_cell(raw_header)
        if not original_name:
            continue
        standard_field = mapped_fields[index - 1] if index - 1 < len(mapped_fields) else None
        columns.append(
            ReferenceProfileColumn(
                index=index,
                original_name=original_name,
                standard_field=standard_field,
                standard_label=(
                    STANDARD_CASE_FIELD_LABELS.get(standard_field)
                    if standard_field
                    else None
                ),
            )
        )
    return columns


def _count_case_rows(
    frame: pd.DataFrame,
    *,
    header_row_index: int,
    mapped_fields: list[str | None],
) -> int:
    count = 0
    for row_index in range(header_row_index + 1, len(frame.index)):
        row_values = frame.iloc[row_index].tolist()
        values_by_field: dict[str, str] = {}
        for column_index, standard_field in enumerate(mapped_fields):
            if standard_field is None or column_index >= len(row_values):
                continue
            value = _normalize_cell(row_values[column_index])
            if value:
                values_by_field[standard_field] = value
        if _is_case_row(values_by_field):
            count += 1
    return count


def _is_case_row(values_by_field: dict[str, str]) -> bool:
    if not values_by_field:
        return False
    combined = " ".join(values_by_field.values())
    if _looks_like_summary_row(combined):
        return False
    if any(values_by_field.get(field) for field in _CORE_CASE_FIELDS):
        return True
    signal_count = sum(1 for field in _CASE_SIGNAL_FIELDS if values_by_field.get(field))
    return signal_count >= 2


def _looks_like_summary_row(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return False
    summary_words = ("合计", "总计", "汇总", "小计")
    return any(word in compact for word in summary_words)


def _select_default_sheet(
    sheet_options: list[ReferenceSheetOption],
) -> ReferenceSheetOption:
    exact_names = {option.name.strip(): option for option in sheet_options}
    lower_names = {option.name.strip().lower(): option for option in sheet_options}
    for default_name in REFERENCE_DEFAULT_SHEET_NAMES:
        if default_name in exact_names:
            return exact_names[default_name]
        lower_name = default_name.lower()
        if lower_name in lower_names:
            return lower_names[lower_name]
    return sheet_options[0]


def _extract_plain_text_profile(path: Path) -> ReferenceProfile:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = path.read_text(encoding="utf-8-sig", errors="ignore")

    lines = [line.strip() for line in content.splitlines()]
    non_empty_lines = [line for line in lines if line]
    case_count = _count_plain_text_cases(non_empty_lines)
    source_type = "markdown" if path.suffix.lower() == ".md" else "text"
    warnings: list[GenerationWarning] = []
    if case_count == 0 and non_empty_lines:
        warnings.append(
            GenerationWarning(
                source="reference_profile",
                message="文本参考案例未识别出明确用例行，仅作为风格参考展示。",
            )
        )

    return ReferenceProfile(
        source_type=source_type,
        source_name=path.name,
        reference_case_count=case_count,
        warnings=warnings,
    )


def _count_plain_text_cases(lines: list[str]) -> int:
    checklist_count = sum(
        1 for line in lines if re.match(r"^[-*]\s+\[[ xX]\]\s+\S", line)
    )
    if checklist_count:
        return checklist_count

    table_lines = [line for line in lines if line.startswith("|") and line.endswith("|")]
    table_body_lines = [
        line
        for line in table_lines
        if not re.match(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$", line)
    ]
    if len(table_body_lines) > 1:
        return len(table_body_lines) - 1

    return sum(1 for line in lines if not line.startswith("#"))


def _map_header(header: str) -> str | None:
    normalized = _normalize_header(header)
    if not normalized:
        return None
    direct = _ALIAS_LOOKUP.get(normalized)
    if direct:
        return direct
    for alias, field in _ALIAS_LOOKUP.items():
        if len(alias) >= 3 and alias in normalized:
            return field
    return None


def _normalize_cell(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _get_excel_engine(path: Path) -> str:
    if path.suffix.lower() == ".xls":
        return "xlrd"
    return "openpyxl"


def _build_excel_dependency_error(path: Path) -> str:
    if path.suffix.lower() == ".xls":
        return "读取 .xls 参考案例需要安装 xlrd 依赖。"
    return "读取 .xlsx 参考案例需要安装 openpyxl 依赖。"
