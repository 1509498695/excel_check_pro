"""组合变量筛选条件复用工具。"""

from __future__ import annotations

import pandas as pd

from backend.app.api.schemas import CompositeCondition, VariableTag
from backend.app.fixed_rules.composite_rule_normalizer import _normalize_composite_conditions
from backend.app.fixed_rules.config_common import (
    COMPOSITE_KEY_FIELD,
    SUPPORTED_COMPOSITE_FILTER_OPERATORS,
)
from backend.app.rules.handlers.fixed.condition_eval import _apply_composite_filters


def normalize_composite_filter_conditions(
    filters: list[CompositeCondition] | None,
    *,
    context_id: str,
    available_fields: list[str],
    section_label: str = "变量级筛选条件",
) -> list[CompositeCondition]:
    """按组合分支全局筛选口径归一化变量级筛选条件。"""
    if not filters:
        return []

    return _normalize_composite_conditions(
        rule_id=context_id,
        conditions=filters,
        section_label=section_label,
        available_fields=_unique_preserve_order([COMPOSITE_KEY_FIELD, *available_fields]),
        allowed_operators=SUPPORTED_COMPOSITE_FILTER_OPERATORS,
    )


def collect_composite_filter_dependency_fields(
    filters: list[CompositeCondition] | None,
) -> list[str]:
    """返回筛选条件需要临时读取但不一定进入变量输出结构的字段。"""
    fields: list[str] = []
    for condition in filters or []:
        _append_filter_field(fields, condition.field)
        if condition.value_source == "field":
            _append_filter_field(fields, condition.expected_field or "")
    return _unique_preserve_order(fields)


def apply_composite_filter_conditions(
    frame: pd.DataFrame,
    variable: VariableTag,
    filters: list[CompositeCondition] | None,
) -> pd.DataFrame:
    """应用组合变量筛选条件；无筛选时保持输入 frame。"""
    return _apply_composite_filters(frame, variable, filters or [])


def _append_filter_field(fields: list[str], field: str) -> None:
    normalized_field = field.strip() if field else ""
    if normalized_field and normalized_field != COMPOSITE_KEY_FIELD:
        fields.append(field)


def _unique_preserve_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result
