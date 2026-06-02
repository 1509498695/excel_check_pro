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
    raw_item_id: Any
    raw_count: Any


@dataclass(frozen=True)
class _StrItemsParseIssue:
    error_type: str
    item_id: str | None
    raw_value: Any
    right_value: Any
    message: str


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
    package_id_filters = _normalize_package_id_filters(rule.params.get("package_id_filter"))
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
        package_id_filters=package_id_filters,
        display_field=display_field,
        abnormal_results=abnormal_results,
    )
    right_packages, right_order = _build_right_package_index(
        right_frame,
        right_variable=right_variable,
        rule_name=rule_name,
        right_package_field=right_package_field,
        right_items_field=right_items_field,
        package_id_filters=package_id_filters,
        abnormal_results=abnormal_results,
    )
    checked_package_ids = package_id_filters or _merge_package_order(package_order, right_order)

    compare_location = _build_compare_location(
        left_variable=left_variable,
        right_variable=right_variable,
        left_field=left_item_field,
        right_field=right_items_field,
    )
    left_package_location = _build_rule_location(left_variable, left_package_field)
    right_items_location = _build_rule_location(right_variable, right_items_field)

    for package_id in checked_package_ids:
        left_items = left_packages.get(package_id)
        right_package = right_packages.get(package_id)
        if left_items is None:
            row_index = right_package.row_index if right_package is not None else 0
            raw_value = right_package.raw_items if right_package is not None else package_id
            _append_package_result(
                abnormal_results,
                row_index=row_index,
                raw_value=raw_value,
                rule_name=rule_name,
                location=left_package_location,
                message=f"礼包id 缺失：礼包 {package_id} 在飞书 Sheet 中不存在。",
                package_id=package_id,
                item_id=None,
                error_type="left_missing_package",
                left_value=None,
                right_value=package_id,
            )
        if right_package is None:
            row_index, raw_value, display_value = _get_missing_package_display(
                left_items or {},
                package_id,
                display_field=display_field,
            )
            _append_package_result(
                abnormal_results,
                row_index=row_index,
                raw_value=raw_value,
                display_value=display_value,
                rule_name=rule_name,
                location=left_package_location,
                message=f"INT_PackageId 缺失：礼包 {package_id} 在右侧配置表中不存在。",
                package_id=package_id,
                item_id=None,
                error_type="right_missing_package",
                left_value=package_id,
                right_value=None,
            )
        if left_items is None or right_package is None:
            continue

        right_items = right_package.items
        for item_id, left_item in left_items.items():
            right_item = right_items.get(item_id)
            if right_item is None:
                _append_package_result(
                    abnormal_results,
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
                    package_id=package_id,
                    item_id=item_id,
                    error_type="right_missing_item",
                    left_value=left_item.count,
                    right_value=None,
                )
                continue
            if left_item.count != right_item.count:
                _append_package_result(
                    abnormal_results,
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
                    package_id=package_id,
                    item_id=item_id,
                    error_type="count_mismatch",
                    left_value=left_item.count,
                    right_value=right_item.count,
                )

        for item_id, right_item in right_items.items():
            if item_id in left_items:
                continue
            _append_package_result(
                abnormal_results,
                row_index=right_package.row_index,
                raw_value=right_package.raw_items,
                rule_name=rule_name,
                location=right_items_location,
                message=(
                    f"STR_Items 多出道具：礼包 {package_id} 多出道具 {item_id}，"
                    f"数量为 {right_item.count}。"
                ),
                package_id=package_id,
                item_id=item_id,
                error_type="left_missing_item",
                left_value=None,
                right_value=right_item.count,
            )

    return abnormal_results


def parse_str_items(value: Any) -> tuple[dict[str, _ParsedStrItem], list[str]]:
    """解析 STR_Items 中的 ``{item,id,count}`` 片段，忽略非 item 类型。"""
    result = _parse_str_items_detailed(value)
    return result[0], [issue.message for issue in result[1]]


def _parse_str_items_detailed(value: Any) -> tuple[dict[str, _ParsedStrItem], list[_StrItemsParseIssue]]:
    """解析 STR_Items 并保留结构化错误上下文。"""
    if is_empty_value(value):
        return {}, []

    text = str(value).strip()
    if _is_empty_str_items_array(text):
        return {}, []

    matches = list(_BRACED_TOKEN_PATTERN.finditer(text))
    if not matches:
        return {}, [
            _StrItemsParseIssue(
                error_type="str_items_format_error",
                item_id=None,
                raw_value=value,
                right_value=value,
                message=f"STR_Items 格式错误：{text}",
            )
        ]

    outer_text = _BRACED_TOKEN_PATTERN.sub("", text)
    errors: list[_StrItemsParseIssue] = []
    if not _PERMITTED_OUTER_PATTERN.fullmatch(outer_text):
        errors.append(
            _StrItemsParseIssue(
                error_type="str_items_format_error",
                item_id=None,
                raw_value=value,
                right_value=value,
                message=f"STR_Items 格式错误：{text}",
            )
        )

    items: dict[str, _ParsedStrItem] = {}
    for match in matches:
        token = match.group(0)
        parts = [part.strip() for part in match.group(1).split(",")]
        kind = parts[0] if parts else ""
        if kind != "item":
            continue

        if len(parts) != 3:
            errors.append(
                _StrItemsParseIssue(
                    error_type="str_items_format_error",
                    item_id=None,
                    raw_value=token,
                    right_value=token,
                    message=f"STR_Items 片段格式错误：{token}",
                )
            )
            continue

        item_id, item_error = _normalize_integer_text(parts[1], "道具 ID")
        count, count_error = _normalize_integer(parts[2], "道具数量")
        if item_error:
            errors.append(
                _StrItemsParseIssue(
                    error_type="right_invalid_item_id",
                    item_id=None,
                    raw_value=parts[1],
                    right_value=parts[1],
                    message=f"STR_Items 片段 {token} 的{item_error}",
                )
            )
            continue
        if count_error:
            errors.append(
                _StrItemsParseIssue(
                    error_type="right_invalid_count",
                    item_id=item_id,
                    raw_value=parts[2],
                    right_value=parts[2],
                    message=f"STR_Items 片段 {token} 的{count_error}",
                )
            )
            continue
        assert item_id is not None
        assert count is not None
        if item_id in items:
            errors.append(
                _StrItemsParseIssue(
                    error_type="right_duplicate_item",
                    item_id=item_id,
                    raw_value=token,
                    right_value=count,
                    message=f"STR_Items 道具重复：{item_id}",
                )
            )
            continue
        items[item_id] = _ParsedStrItem(
            item_id=item_id,
            count=count,
            token=token,
            raw_item_id=parts[1],
            raw_count=parts[2],
        )

    return items, errors


def _is_empty_str_items_array(text: str) -> bool:
    return bool(re.fullmatch(r"\[\s*\]", text))


def _build_left_package_index(
    frame: pd.DataFrame,
    *,
    left_variable: VariableTag,
    rule_name: str,
    left_package_field: str,
    left_item_field: str,
    left_count_field: str,
    package_id_filters: list[str] | None,
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
            if package_id_filters is None:
                _append_package_result(
                    abnormal_results,
                    row_index=row_index,
                    raw_value=row[left_package_field],
                    display_value=_get_row_display_value(row, display_field),
                    rule_name=rule_name,
                    location=package_location,
                    message="礼包id 为空，无法参与礼包明细对比。",
                    package_id=None,
                    item_id=None,
                    error_type="left_invalid_package_id",
                    left_value=row[left_package_field],
                    right_value=None,
                )
            continue
        if package_id_filters is not None and package_id not in package_id_filters:
            continue

        if package_id not in packages:
            packages[package_id] = {}
            package_order.append(package_id)

        item_id, item_error = _normalize_integer_text(row[left_item_field], "道具id")
        count, count_error = _normalize_integer(row[left_count_field], "个数")
        if item_error:
            _append_package_result(
                abnormal_results,
                row_index=row_index,
                raw_value=row[left_item_field],
                display_value=_get_row_display_value(row, display_field),
                rule_name=rule_name,
                location=item_location,
                message=f"礼包 {package_id} 的{item_error}。",
                package_id=package_id,
                item_id=None,
                error_type="left_invalid_item_id",
                left_value=row[left_item_field],
                right_value=None,
            )
            continue
        if count_error:
            _append_package_result(
                abnormal_results,
                row_index=row_index,
                raw_value=row[left_count_field],
                display_value=_get_row_display_value(row, display_field),
                rule_name=rule_name,
                location=count_location,
                message=f"礼包 {package_id} 的{count_error}。",
                package_id=package_id,
                item_id=item_id,
                error_type="left_invalid_count",
                left_value=row[left_count_field],
                right_value=None,
            )
            continue
        assert item_id is not None
        assert count is not None

        package_items = packages[package_id]
        if item_id in package_items:
            _append_package_result(
                abnormal_results,
                row_index=row_index,
                raw_value=row[left_item_field],
                display_value=_get_row_display_value(row, display_field),
                rule_name=rule_name,
                location=item_location,
                message=f"礼包 {package_id} 左侧道具重复配置：{item_id}。",
                package_id=package_id,
                item_id=item_id,
                error_type="left_duplicate_item",
                left_value=count,
                right_value=None,
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


def _merge_package_order(left_order: list[str], right_order: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for package_id in [*left_order, *right_order]:
        if package_id in seen:
            continue
        result.append(package_id)
        seen.add(package_id)
    return result


def _append_package_result(
    abnormal_results: list[dict[str, Any]],
    *,
    row_index: int,
    raw_value: Any,
    rule_name: str,
    location: str,
    message: str,
    package_id: str | None,
    item_id: str | None,
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
            "package_id": package_id,
            "item_id": item_id,
            "error_type": error_type,
            "left_value": left_value,
            "right_value": right_value,
        }
    )
    abnormal_results.append(result)


def _build_right_package_index(
    frame: pd.DataFrame,
    *,
    right_variable: VariableTag,
    rule_name: str,
    right_package_field: str,
    right_items_field: str,
    package_id_filters: list[str] | None,
    abnormal_results: list[dict[str, Any]],
) -> tuple[dict[str, _RightPackageItems], list[str]]:
    packages: dict[str, _RightPackageItems] = {}
    package_order: list[str] = []
    package_location = _build_rule_location(right_variable, right_package_field)
    items_location = _build_rule_location(right_variable, right_items_field)

    for _, row in frame.iterrows():
        row_index = int(row["_row_index"])
        package_id = _normalize_package_id(row[right_package_field])
        if package_id is None:
            _append_package_result(
                abnormal_results,
                row_index=row_index,
                raw_value=row[right_package_field],
                rule_name=rule_name,
                location=package_location,
                message="INT_PackageId 为空，无法参与礼包配置对比。",
                package_id=None,
                item_id=None,
                error_type="right_invalid_package_id",
                left_value=None,
                right_value=row[right_package_field],
            )
            continue
        if package_id_filters is not None and package_id not in package_id_filters:
            continue

        if package_id in packages:
            _append_package_result(
                abnormal_results,
                row_index=row_index,
                raw_value=row[right_package_field],
                rule_name=rule_name,
                location=package_location,
                message=f"INT_PackageId 重复配置：礼包 {package_id} 在右侧配置表出现多行。",
                package_id=package_id,
                item_id=None,
                error_type="right_duplicate_package",
                left_value=None,
                right_value=row[right_package_field],
            )
            continue

        package_order.append(package_id)
        items, parse_errors = _parse_str_items_detailed(row[right_items_field])
        for parse_error in parse_errors:
            _append_package_result(
                abnormal_results,
                row_index=row_index,
                raw_value=parse_error.raw_value,
                rule_name=rule_name,
                location=items_location,
                message=f"礼包 {package_id} 的{parse_error.message}。",
                package_id=package_id,
                item_id=parse_error.item_id,
                error_type=parse_error.error_type,
                left_value=None,
                right_value=parse_error.right_value,
            )
        packages[package_id] = _RightPackageItems(
            items=items,
            row_index=row_index,
            raw_items=row[right_items_field],
        )

    return packages, package_order


def _normalize_package_id_filters(value: Any) -> list[str] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    result: list[str] = []
    seen: set[str] = set()
    for item in re.split(r"[,，]", value):
        package_id = _normalize_package_id(item)
        if package_id is None or package_id in seen:
            continue
        result.append(package_id)
        seen.add(package_id)
    return result or None


def _normalize_package_id(value: Any) -> str | None:
    if is_empty_value(value):
        return None
    if isinstance(value, bool):
        return None
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
