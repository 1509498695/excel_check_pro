"""礼包明细与 STR_Items 比对 handler。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

from backend.app.api.schemas import ValidationRule, VariableTag
from backend.app.rules.domain.result import build_fixed_result
from backend.app.rules.domain.value import is_empty_value
from backend.app.rules.engine_core import RuleExecutionContext, register_rule
from backend.app.rules.handlers.fixed.common import (
    _build_rule_location,
    _get_composite_variable_frame,
    _get_display_field_param,
    _get_field_display_name,
    _get_fixed_rule_param,
    _get_row_display_value,
)
from backend.app.rules.infrastructure.tag_extractor import by_left_and_right_tag


_BRACED_TOKEN_PATTERN = re.compile(r"\{([^{}]*)\}")
_PERMITTED_OUTER_PATTERN = re.compile(r"^[\s,\[\]]*$")


@dataclass(frozen=True)
class _PackageItem:
    item_id: str
    count: int
    row_index: int
    raw_item_id: Any
    raw_count: Any


@dataclass(frozen=True)
class _ParsedStrItem:
    item_id: str
    count: int
    token: str


@dataclass(frozen=True)
class _RightPackageItems:
    items: dict[str, _ParsedStrItem]
    row_index: int
    raw_items: Any


@register_rule("package_items_compare", dependent_tags=by_left_and_right_tag)
def check_package_items_compare(
    rule: ValidationRule,
    context: RuleExecutionContext,
) -> list[dict[str, Any]]:
    """按礼包 ID 对齐明细表与 STR_Items，并比较 item 道具数量。"""
    left_tag = _get_fixed_rule_param(rule, "left_tag")
    right_tag = _get_fixed_rule_param(rule, "right_tag")
    rule_name = _get_fixed_rule_param(rule, "rule_name")
    left_package_field = _get_fixed_rule_param(rule, "left_package_field")
    right_package_field = _get_fixed_rule_param(rule, "right_package_field")
    left_item_field = _get_fixed_rule_param(rule, "left_item_field")
    left_count_field = _get_fixed_rule_param(rule, "left_count_field")
    right_items_field = _get_fixed_rule_param(rule, "right_items_field")
    package_id_filter = _normalize_optional_package_id(rule.params.get("package_id_filter"))
    display_field = _get_display_field_param(rule)

    left_variable, left_frame = _get_composite_variable_frame(context, left_tag, rule.rule_type)
    right_variable, right_frame = _get_composite_variable_frame(context, right_tag, rule.rule_type)
    _ensure_composite_fields(
        frame=left_frame,
        variable=left_variable,
        fields=[left_package_field, left_item_field, left_count_field],
        rule_type=rule.rule_type,
    )
    _ensure_composite_fields(
        frame=right_frame,
        variable=right_variable,
        fields=[right_package_field, right_items_field],
        rule_type=rule.rule_type,
    )

    abnormal_results: list[dict[str, Any]] = []
    left_packages, package_order = _build_left_package_index(
        left_frame,
        left_variable=left_variable,
        rule_name=rule_name,
        left_package_field=left_package_field,
        left_item_field=left_item_field,
        left_count_field=left_count_field,
        package_id_filter=package_id_filter,
        display_field=display_field,
        abnormal_results=abnormal_results,
    )
    checked_package_ids = [package_id_filter] if package_id_filter else package_order
    right_packages = _build_right_package_index(
        right_frame,
        right_variable=right_variable,
        rule_name=rule_name,
        right_package_field=right_package_field,
        right_items_field=right_items_field,
        checked_package_ids=set(checked_package_ids),
        abnormal_results=abnormal_results,
    )

    compare_location = _build_compare_location(
        left_variable=left_variable,
        right_variable=right_variable,
        left_field=left_item_field,
        right_field=right_items_field,
    )
    left_package_location = _build_rule_location(left_variable, left_package_field)
    right_items_location = _build_rule_location(right_variable, right_items_field)

    for package_id in checked_package_ids:
        left_items = left_packages.get(package_id, {})
        right_package = right_packages.get(package_id)
        if right_package is None:
            row_index, raw_value, display_value = _get_missing_package_display(
                left_items,
                package_id,
                display_field=display_field,
            )
            abnormal_results.append(
                build_fixed_result(
                    row_index=row_index,
                    raw_value=raw_value,
                    display_value=display_value,
                    rule_name=rule_name,
                    location=left_package_location,
                    message=f"INT_PackageId 缺失：礼包 {package_id} 在右侧配置表中不存在。",
                )
            )
            continue

        right_items = right_package.items
        for item_id, left_item in left_items.items():
            right_item = right_items.get(item_id)
            if right_item is None:
                abnormal_results.append(
                    build_fixed_result(
                        row_index=left_item.row_index,
                        raw_value=left_item.raw_item_id,
                        display_value=_get_left_item_display_value(
                            left_frame,
                            row_index=left_item.row_index,
                            display_field=display_field,
                        ),
                        rule_name=rule_name,
                        location=compare_location,
                        message=(
                            f"STR_Items 缺少道具：礼包 {package_id} 缺少道具 {item_id}，"
                            f"图1数量为 {left_item.count}。"
                        ),
                    )
                )
                continue
            if left_item.count != right_item.count:
                abnormal_results.append(
                    build_fixed_result(
                        row_index=left_item.row_index,
                        raw_value=left_item.raw_count,
                        display_value=_get_left_item_display_value(
                            left_frame,
                            row_index=left_item.row_index,
                            display_field=display_field,
                        ),
                        rule_name=rule_name,
                        location=compare_location,
                        message=(
                            f"数量不一致：礼包 {package_id} 道具 {item_id} "
                            f"图1={left_item.count}，STR_Items={right_item.count}。"
                        ),
                    )
                )

        for item_id, right_item in right_items.items():
            if item_id in left_items:
                continue
            abnormal_results.append(
                build_fixed_result(
                    row_index=right_package.row_index,
                    raw_value=right_package.raw_items,
                    rule_name=rule_name,
                    location=right_items_location,
                    message=(
                        f"STR_Items 多出道具：礼包 {package_id} 多出道具 {item_id}，"
                        f"数量为 {right_item.count}。"
                    ),
                )
            )

    return abnormal_results


def parse_str_items(value: Any) -> tuple[dict[str, _ParsedStrItem], list[str]]:
    """解析 STR_Items 中的 ``{item,id,count}`` 片段，忽略非 item 类型。"""
    if is_empty_value(value):
        return {}, []

    text = str(value).strip()
    matches = list(_BRACED_TOKEN_PATTERN.finditer(text))
    if not matches:
        return {}, [f"STR_Items 格式错误：{text}"]

    outer_text = _BRACED_TOKEN_PATTERN.sub("", text)
    errors: list[str] = []
    if not _PERMITTED_OUTER_PATTERN.fullmatch(outer_text):
        errors.append(f"STR_Items 格式错误：{text}")

    items: dict[str, _ParsedStrItem] = {}
    for match in matches:
        token = match.group(0)
        parts = [part.strip() for part in match.group(1).split(",")]
        if len(parts) != 3:
            errors.append(f"STR_Items 片段格式错误：{token}")
            continue

        kind = parts[0]
        if kind != "item":
            continue

        item_id, item_error = _normalize_integer_text(parts[1], "道具 ID")
        count, count_error = _normalize_integer(parts[2], "道具数量")
        if item_error:
            errors.append(f"STR_Items 片段 {token} 的{item_error}")
            continue
        if count_error:
            errors.append(f"STR_Items 片段 {token} 的{count_error}")
            continue
        assert item_id is not None
        assert count is not None
        if item_id in items:
            errors.append(f"STR_Items 道具重复：{item_id}")
            continue
        items[item_id] = _ParsedStrItem(item_id=item_id, count=count, token=token)

    return items, errors


def _build_left_package_index(
    frame: pd.DataFrame,
    *,
    left_variable: VariableTag,
    rule_name: str,
    left_package_field: str,
    left_item_field: str,
    left_count_field: str,
    package_id_filter: str | None,
    display_field: str | None,
    abnormal_results: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, _PackageItem]], list[str]]:
    packages: dict[str, dict[str, _PackageItem]] = {}
    package_order: list[str] = []
    package_location = _build_rule_location(left_variable, left_package_field)
    item_location = _build_rule_location(left_variable, left_item_field)
    count_location = _build_rule_location(left_variable, left_count_field)

    for _, row in frame.iterrows():
        row_index = int(row["_row_index"])
        package_id = _normalize_package_id(row[left_package_field])
        if package_id is None:
            if package_id_filter is None:
                abnormal_results.append(
                    build_fixed_result(
                        row_index=row_index,
                        raw_value=row[left_package_field],
                        display_value=_get_row_display_value(row, display_field),
                        rule_name=rule_name,
                        location=package_location,
                        message="礼包id 为空，无法参与礼包明细对比。",
                    )
                )
            continue
        if package_id_filter is not None and package_id != package_id_filter:
            continue

        item_id, item_error = _normalize_integer_text(row[left_item_field], "道具id")
        count, count_error = _normalize_integer(row[left_count_field], "个数")
        if item_error:
            abnormal_results.append(
                build_fixed_result(
                    row_index=row_index,
                    raw_value=row[left_item_field],
                    display_value=_get_row_display_value(row, display_field),
                    rule_name=rule_name,
                    location=item_location,
                    message=f"礼包 {package_id} 的{item_error}。",
                )
            )
            continue
        if count_error:
            abnormal_results.append(
                build_fixed_result(
                    row_index=row_index,
                    raw_value=row[left_count_field],
                    display_value=_get_row_display_value(row, display_field),
                    rule_name=rule_name,
                    location=count_location,
                    message=f"礼包 {package_id} 的{count_error}。",
                )
            )
            continue
        assert item_id is not None
        assert count is not None

        if package_id not in packages:
            packages[package_id] = {}
            package_order.append(package_id)
        package_items = packages[package_id]
        if item_id in package_items:
            abnormal_results.append(
                build_fixed_result(
                    row_index=row_index,
                    raw_value=row[left_item_field],
                    display_value=_get_row_display_value(row, display_field),
                    rule_name=rule_name,
                    location=item_location,
                    message=f"礼包 {package_id} 左侧道具重复配置：{item_id}。",
                )
            )
            continue

        package_items[item_id] = _PackageItem(
            item_id=item_id,
            count=count,
            row_index=row_index,
            raw_item_id=row[left_item_field],
            raw_count=row[left_count_field],
        )

    return packages, package_order


def _build_right_package_index(
    frame: pd.DataFrame,
    *,
    right_variable: VariableTag,
    rule_name: str,
    right_package_field: str,
    right_items_field: str,
    checked_package_ids: set[str],
    abnormal_results: list[dict[str, Any]],
) -> dict[str, _RightPackageItems]:
    packages: dict[str, _RightPackageItems] = {}
    package_location = _build_rule_location(right_variable, right_package_field)
    items_location = _build_rule_location(right_variable, right_items_field)

    for _, row in frame.iterrows():
        package_id = _normalize_package_id(row[right_package_field])
        if package_id is None:
            if not checked_package_ids:
                continue
            abnormal_results.append(
                build_fixed_result(
                    row_index=int(row["_row_index"]),
                    raw_value=row[right_package_field],
                    rule_name=rule_name,
                    location=package_location,
                    message="INT_PackageId 为空，无法参与礼包配置对比。",
                )
            )
            continue
        if package_id not in checked_package_ids:
            continue

        if package_id in packages:
            abnormal_results.append(
                build_fixed_result(
                    row_index=int(row["_row_index"]),
                    raw_value=row[right_package_field],
                    rule_name=rule_name,
                    location=package_location,
                    message=f"INT_PackageId 重复配置：礼包 {package_id} 在右侧配置表出现多行。",
                )
            )
            continue

        items, parse_errors = parse_str_items(row[right_items_field])
        for parse_error in parse_errors:
            abnormal_results.append(
                build_fixed_result(
                    row_index=int(row["_row_index"]),
                    raw_value=row[right_items_field],
                    rule_name=rule_name,
                    location=items_location,
                    message=f"礼包 {package_id} 的{parse_error}。",
                )
            )
        packages[package_id] = _RightPackageItems(
            items=items,
            row_index=int(row["_row_index"]),
            raw_items=row[right_items_field],
        )

    return packages


def _normalize_optional_package_id(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return _normalize_package_id(value)


def _normalize_package_id(value: Any) -> str | None:
    if is_empty_value(value):
        return None
    if isinstance(value, bool):
        return str(value).strip()
    text = str(value).strip()
    normalized_integer = _try_normalize_integer_text(text)
    return normalized_integer or text


def _normalize_integer_text(value: Any, field_label: str) -> tuple[str | None, str | None]:
    normalized, error = _normalize_integer(value, field_label)
    if error:
        return None, error
    assert normalized is not None
    return str(normalized), None


def _normalize_integer(value: Any, field_label: str) -> tuple[int | None, str | None]:
    if is_empty_value(value):
        return None, f"{field_label} 为空"
    if isinstance(value, bool):
        return None, f"{field_label} 必须是整数"

    text = str(value).strip()
    normalized = _try_normalize_integer_text(text)
    if normalized is None:
        return None, f"{field_label} 必须是整数"
    return int(normalized), None


def _try_normalize_integer_text(text: str) -> str | None:
    if not text:
        return None
    if re.fullmatch(r"[+-]?\d+", text):
        return str(int(text))
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        return str(int(float(text)))
    return None


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


def _get_missing_package_display(
    left_items: dict[str, _PackageItem],
    package_id: str,
    *,
    display_field: str | None,
) -> tuple[int, Any, Any]:
    if not left_items:
        return 0, package_id, None
    first_item = next(iter(left_items.values()))
    return first_item.row_index, package_id, None if display_field else None


def _get_left_item_display_value(
    frame: pd.DataFrame,
    *,
    row_index: int,
    display_field: str | None,
) -> Any:
    if not display_field or display_field not in frame.columns:
        return None
    rows = frame.loc[frame["_row_index"] == row_index]
    if rows.empty:
        return None
    return rows.iloc[0][display_field]
