"""节日任务表与 EventTask 配置比对 handler。"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import pandas as pd

from backend.app.api.schemas import ValidationRule, VariableTag
from backend.app.rules.domain.result import build_fixed_result
from backend.app.rules.domain.value import is_empty_value
from backend.app.rules.engine_core import RuleExecutionContext, register_rule
from backend.app.rules.handlers.fixed.common import (
    COMPOSITE_KEY_FIELD,
    _build_rule_location,
    _get_composite_variable_frame,
    _get_display_field_param,
    _get_field_display_name,
    _get_fixed_rule_param,
    _get_row_display_value,
)
from backend.app.rules.infrastructure.tag_extractor import by_left_and_right_tag


@dataclass(frozen=True)
class _TaskRow:
    task_group_id: str
    task_id: str | None
    task_desc: str
    loot: str | None
    row_index: int
    raw_group_id: Any
    raw_task_id: Any
    raw_desc: Any
    raw_loot: Any
    display_value: Any = None


@register_rule("event_task_validation", dependent_tags=by_left_and_right_tag)
def check_event_task_validation(
    rule: ValidationRule,
    context: RuleExecutionContext,
) -> list[dict[str, Any]]:
    """按任务组 ID + 描述对齐任务表与 EventTask，并比较任务 ID 与 STR_Loot。"""
    left_tag = _get_fixed_rule_param(rule, "left_tag")
    right_tag = _get_fixed_rule_param(rule, "right_tag")
    rule_name = _get_fixed_rule_param(rule, "rule_name")
    left_task_group_field = _get_fixed_rule_param(rule, "left_task_group_field")
    left_task_id_field = _get_fixed_rule_param(rule, "left_task_id_field")
    left_task_desc_field = _get_fixed_rule_param(rule, "left_task_desc_field")
    left_task_loot_field = _get_fixed_rule_param(rule, "left_task_loot_field")
    right_task_group_field = _get_fixed_rule_param(rule, "right_task_group_field")
    right_task_id_field = _get_fixed_rule_param(rule, "right_task_id_field")
    right_task_desc_field = _get_fixed_rule_param(rule, "right_task_desc_field")
    right_task_loot_field = _get_fixed_rule_param(rule, "right_task_loot_field")
    task_group_filters = _normalize_task_group_id_filters(
        rule.params.get("task_group_id_filter")
    )
    display_field = _get_display_field_param(rule)

    left_variable, left_frame = _get_composite_variable_frame(context, left_tag, rule.rule_type)
    right_variable, right_frame = _get_composite_variable_frame(context, right_tag, rule.rule_type)
    _ensure_composite_fields(
        frame=left_frame,
        variable=left_variable,
        fields=[
            left_task_group_field,
            left_task_id_field,
            left_task_desc_field,
            left_task_loot_field,
        ],
        rule_type=rule.rule_type,
    )
    _ensure_composite_fields(
        frame=right_frame,
        variable=right_variable,
        fields=[
            right_task_group_field,
            right_task_id_field,
            right_task_desc_field,
            right_task_loot_field,
        ],
        rule_type=rule.rule_type,
    )

    abnormal_results: list[dict[str, Any]] = []
    left_tasks, left_group_order = _build_task_rows(
        left_frame,
        variable=left_variable,
        rule_name=rule_name,
        task_group_field=left_task_group_field,
        task_id_field=left_task_id_field,
        task_desc_field=left_task_desc_field,
        task_loot_field=left_task_loot_field,
        task_group_filters=task_group_filters,
        display_field=display_field,
        side_label="飞书任务表",
        abnormal_results=abnormal_results,
    )
    right_tasks, right_group_order = _build_task_rows(
        right_frame,
        variable=right_variable,
        rule_name=rule_name,
        task_group_field=right_task_group_field,
        task_id_field=right_task_id_field,
        task_desc_field=right_task_desc_field,
        task_loot_field=right_task_loot_field,
        task_group_filters=task_group_filters,
        display_field=None,
        side_label="EventTask 配置",
        abnormal_results=abnormal_results,
        extract_group_from_key=True,
    )

    left_by_group_desc = _index_by_group_desc(left_tasks)
    right_by_group_desc = _index_by_group_desc(right_tasks)
    right_by_task_id = _index_by_task_id(right_tasks)
    _append_duplicate_results(
        abnormal_results,
        grouped_rows=left_by_group_desc,
        rule_name=rule_name,
        location=_build_rule_location(left_variable, left_task_desc_field),
        error_type="left_duplicate_task",
        message_prefix="飞书任务表重复任务",
        left_side=True,
    )
    _append_duplicate_results(
        abnormal_results,
        grouped_rows=right_by_group_desc,
        rule_name=rule_name,
        location=_build_rule_location(right_variable, right_task_desc_field),
        error_type="right_duplicate_task",
        message_prefix="EventTask 重复任务",
        left_side=False,
    )

    checked_group_ids = task_group_filters or _merge_task_group_order(
        left_group_order,
        right_group_order,
    )
    compare_location = _build_compare_location(
        left_variable=left_variable,
        right_variable=right_variable,
        left_field=left_task_desc_field,
        right_field=right_task_desc_field,
    )
    right_location = _build_rule_location(right_variable, right_task_desc_field)
    left_location = _build_rule_location(left_variable, left_task_desc_field)
    matched_right_keys: set[tuple[int, str, str]] = set()

    for task_group_id in checked_group_ids:
        left_rows = [row for row in left_tasks if row.task_group_id == task_group_id]
        right_rows = [row for row in right_tasks if row.task_group_id == task_group_id]
        if not left_rows:
            for right_row in right_rows:
                _append_event_task_result(
                    abnormal_results,
                    row_index=right_row.row_index,
                    raw_value=right_row.raw_desc,
                    rule_name=rule_name,
                    location=left_location,
                    message=(
                        f"飞书任务表缺失：任务组 {task_group_id} 未找到任务 "
                        f"{right_row.task_desc}。"
                    ),
                    task_group_id=task_group_id,
                    task_id=right_row.task_id,
                    error_type="left_missing_task",
                    left_value=None,
                    right_value=right_row.task_desc,
                )
            continue
        if not right_rows:
            for left_row in left_rows:
                _append_event_task_result(
                    abnormal_results,
                    row_index=left_row.row_index,
                    raw_value=left_row.raw_desc,
                    display_value=left_row.display_value,
                    rule_name=rule_name,
                    location=right_location,
                    message=(
                        f"EventTask 缺失：任务组 {task_group_id} 未找到任务 "
                        f"{left_row.task_desc}。"
                    ),
                    task_group_id=task_group_id,
                    task_id=left_row.task_id,
                    error_type="right_missing_task",
                    left_value=left_row.task_desc,
                    right_value=None,
                )
            continue

        for left_row in left_rows:
            matched_row, match_type = _match_right_task(
                left_row,
                right_by_group_desc=right_by_group_desc,
                right_by_task_id=right_by_task_id,
            )
            if matched_row is None:
                _append_event_task_result(
                    abnormal_results,
                    row_index=left_row.row_index,
                    raw_value=left_row.raw_desc,
                    display_value=left_row.display_value,
                    rule_name=rule_name,
                    location=right_location,
                    message=(
                        f"EventTask 缺失：任务组 {task_group_id} 未找到任务 "
                        f"{left_row.task_desc}。"
                    ),
                    task_group_id=task_group_id,
                    task_id=left_row.task_id,
                    error_type="right_missing_task",
                    left_value=left_row.task_desc,
                    right_value=None,
                )
                continue

            matched_right_keys.add(_task_identity(matched_row))
            if match_type == "task_id" and _normalize_desc(left_row.task_desc) != _normalize_desc(
                matched_row.task_desc
            ):
                _append_event_task_result(
                    abnormal_results,
                    row_index=left_row.row_index,
                    raw_value=left_row.raw_desc,
                    display_value=left_row.display_value,
                    rule_name=rule_name,
                    location=compare_location,
                    message=(
                        f"任务描述不一致：任务组 {task_group_id} / INT_TaskID "
                        f"{left_row.task_id}，飞书={left_row.task_desc}，"
                        f"EventTask={matched_row.task_desc}。"
                    ),
                    task_group_id=task_group_id,
                    task_id=left_row.task_id,
                    error_type="desc_mismatch",
                    left_value=left_row.task_desc,
                    right_value=matched_row.task_desc,
                )

            if _normalize_loot(left_row.loot) != _normalize_loot(matched_row.loot):
                _append_event_task_result(
                    abnormal_results,
                    row_index=left_row.row_index,
                    raw_value=left_row.raw_loot,
                    display_value=left_row.display_value,
                    rule_name=rule_name,
                    location=compare_location,
                    message=(
                        f"STR_Loot 不一致：任务组 {task_group_id} / "
                        f"{left_row.task_desc}，飞书={_display_value(left_row.loot)}，"
                        f"EventTask={_display_value(matched_row.loot)}。"
                    ),
                    task_group_id=task_group_id,
                    task_id=left_row.task_id or matched_row.task_id,
                    error_type="loot_mismatch",
                    left_value=left_row.loot,
                    right_value=matched_row.loot,
                )

    for right_row in right_tasks:
        if checked_group_ids and right_row.task_group_id not in checked_group_ids:
            continue
        if _task_identity(right_row) in matched_right_keys:
            continue
        if any(
            left_row.task_group_id == right_row.task_group_id
            for left_row in left_tasks
        ):
            _append_event_task_result(
                abnormal_results,
                row_index=right_row.row_index,
                raw_value=right_row.raw_desc,
                rule_name=rule_name,
                location=left_location,
                message=(
                    f"飞书任务表缺失：任务组 {right_row.task_group_id} 未找到任务 "
                    f"{right_row.task_desc}。"
                ),
                task_group_id=right_row.task_group_id,
                task_id=right_row.task_id,
                error_type="left_missing_task",
                left_value=None,
                right_value=right_row.task_desc,
            )

    return abnormal_results


def _build_task_rows(
    frame: pd.DataFrame,
    *,
    variable: VariableTag,
    rule_name: str,
    task_group_field: str,
    task_id_field: str,
    task_desc_field: str,
    task_loot_field: str,
    task_group_filters: list[str] | None,
    display_field: str | None,
    side_label: str,
    abnormal_results: list[dict[str, Any]],
    extract_group_from_key: bool = False,
) -> tuple[list[_TaskRow], list[str]]:
    task_rows: list[_TaskRow] = []
    task_group_order: list[str] = []
    seen_group_ids: set[str] = set()
    group_location = _build_rule_location(variable, task_group_field)
    desc_location = _build_rule_location(variable, task_desc_field)

    for _, row in frame.iterrows():
        row_index = int(row["_row_index"])
        task_group_id = (
            _extract_task_group_id_from_key(row.get(COMPOSITE_KEY_FIELD))
            if extract_group_from_key
            else None
        ) or _normalize_id_text(row[task_group_field])
        task_desc = _normalize_text(row[task_desc_field])
        task_id = _normalize_id_text(row[task_id_field])
        if task_group_id is None:
            _append_event_task_result(
                abnormal_results,
                row_index=row_index,
                raw_value=row[task_group_field],
                display_value=_get_row_display_value(row, display_field),
                rule_name=rule_name,
                location=group_location,
                message=f"{side_label}任务组 ID 为空，无法参与节日任务校验。",
                task_group_id=None,
                task_id=task_id,
                error_type="invalid_task_group_id",
                left_value=row[task_group_field],
                right_value=None,
            )
            continue
        if task_group_filters is not None and task_group_id not in task_group_filters:
            continue
        if not task_desc:
            _append_event_task_result(
                abnormal_results,
                row_index=row_index,
                raw_value=row[task_desc_field],
                display_value=_get_row_display_value(row, display_field),
                rule_name=rule_name,
                location=desc_location,
                message=f"{side_label}任务描述为空，无法参与节日任务校验。",
                task_group_id=task_group_id,
                task_id=task_id,
                error_type="invalid_task_desc",
                left_value=row[task_desc_field],
                right_value=None,
            )
            continue

        if task_group_id not in seen_group_ids:
            task_group_order.append(task_group_id)
            seen_group_ids.add(task_group_id)
        task_rows.append(
            _TaskRow(
                task_group_id=task_group_id,
                task_id=task_id,
                task_desc=task_desc,
                loot=_normalize_text(row[task_loot_field]),
                row_index=row_index,
                raw_group_id=row[task_group_field],
                raw_task_id=row[task_id_field],
                raw_desc=row[task_desc_field],
                raw_loot=row[task_loot_field],
                display_value=_get_row_display_value(row, display_field),
            )
        )

    return task_rows, task_group_order


def _match_right_task(
    left_row: _TaskRow,
    *,
    right_by_group_desc: dict[tuple[str, str], list[_TaskRow]],
    right_by_task_id: dict[str, list[_TaskRow]],
) -> tuple[_TaskRow | None, str | None]:
    primary = right_by_group_desc.get(
        (left_row.task_group_id, _normalize_desc(left_row.task_desc)),
        [],
    )
    if primary:
        return primary[0], "group_desc"
    if not left_row.task_id:
        return None, None
    fallback = [
        row
        for row in right_by_task_id.get(left_row.task_id, [])
        if row.task_group_id == left_row.task_group_id
    ]
    if not fallback:
        fallback = right_by_task_id.get(left_row.task_id, [])
    if fallback:
        return fallback[0], "task_id"
    return None, None


def _index_by_group_desc(rows: list[_TaskRow]) -> dict[tuple[str, str], list[_TaskRow]]:
    result: dict[tuple[str, str], list[_TaskRow]] = {}
    for row in rows:
        result.setdefault((row.task_group_id, _normalize_desc(row.task_desc)), []).append(row)
    return result


def _index_by_task_id(rows: list[_TaskRow]) -> dict[str, list[_TaskRow]]:
    result: dict[str, list[_TaskRow]] = {}
    for row in rows:
        if row.task_id:
            result.setdefault(row.task_id, []).append(row)
    return result


def _append_duplicate_results(
    abnormal_results: list[dict[str, Any]],
    *,
    grouped_rows: dict[tuple[str, str], list[_TaskRow]],
    rule_name: str,
    location: str,
    error_type: str,
    message_prefix: str,
    left_side: bool,
) -> None:
    for (_task_group_id, _desc), rows in grouped_rows.items():
        if len(rows) <= 1:
            continue
        first_row = rows[0]
        for duplicate_row in rows[1:]:
            _append_event_task_result(
                abnormal_results,
                row_index=duplicate_row.row_index,
                raw_value=duplicate_row.raw_desc,
                display_value=duplicate_row.display_value,
                rule_name=rule_name,
                location=location,
                message=(
                    f"{message_prefix}：任务组 {duplicate_row.task_group_id} / "
                    f"{duplicate_row.task_desc} 在第 {first_row.row_index} 行和 "
                    f"第 {duplicate_row.row_index} 行重复。"
                ),
                task_group_id=duplicate_row.task_group_id,
                task_id=duplicate_row.task_id,
                error_type=error_type,
                left_value=duplicate_row.task_desc if left_side else None,
                right_value=None if left_side else duplicate_row.task_desc,
            )


def _normalize_task_group_id_filters(value: Any) -> list[str] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    result: list[str] = []
    seen: set[str] = set()
    for item in re.split(r"[,，]", value):
        task_group_id = _normalize_id_text(item)
        if task_group_id is None or task_group_id in seen:
            continue
        result.append(task_group_id)
        seen.add(task_group_id)
    return result or None


def _normalize_id_text(value: Any) -> str | None:
    if is_empty_value(value) or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"[+-]?\d+", text):
        return str(int(text))
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        return str(int(float(text)))
    return text


def _normalize_text(value: Any) -> str | None:
    if is_empty_value(value):
        return None
    text = str(value).strip()
    return text or None


def _normalize_desc(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def _normalize_loot(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _extract_task_group_id_from_key(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text or "_" not in text:
        return None
    return _normalize_id_text(text.split("_", 1)[0])


def _merge_task_group_order(left_order: list[str], right_order: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for task_group_id in [*left_order, *right_order]:
        if task_group_id in seen:
            continue
        result.append(task_group_id)
        seen.add(task_group_id)
    return result


def _task_identity(row: _TaskRow) -> tuple[int, str, str]:
    return (row.row_index, row.task_group_id, _normalize_desc(row.task_desc))


def _display_value(value: Any) -> str:
    normalized = _normalize_text(value)
    return normalized if normalized is not None else "<空>"


def _append_event_task_result(
    abnormal_results: list[dict[str, Any]],
    *,
    row_index: int,
    raw_value: Any,
    rule_name: str,
    location: str,
    message: str,
    task_group_id: str | None,
    task_id: str | None,
    error_type: str,
    left_value: Any,
    right_value: Any,
    display_value: Any = None,
) -> None:
    result = build_fixed_result(
        row_index=row_index,
        raw_value=raw_value,
        display_value=display_value,
        rule_name=rule_name,
        location=location,
        message=message,
    )
    result.update(
        {
            "task_group_id": task_group_id,
            "task_id": task_id,
            "error_type": error_type,
            "left_value": left_value,
            "right_value": right_value,
        }
    )
    abnormal_results.append(result)


def _ensure_composite_fields(
    *,
    frame: pd.DataFrame,
    variable: VariableTag,
    fields: list[str],
    rule_type: str,
) -> None:
    missing_fields = [field for field in fields if field not in frame.columns]
    if missing_fields:
        missing_text = "、".join(missing_fields)
        raise ValueError(
            f"Rule '{rule_type}' references missing fields in composite variable "
            f"'{variable.tag}': {missing_text}."
        )


def _build_compare_location(
    *,
    left_variable: VariableTag,
    right_variable: VariableTag,
    left_field: str,
    right_field: str,
) -> str:
    return (
        f"{left_variable.sheet} -> {_get_field_display_name(left_variable, left_field)}"
        f" ⇄ {right_variable.sheet} -> {_get_field_display_name(right_variable, right_field)}"
    )
