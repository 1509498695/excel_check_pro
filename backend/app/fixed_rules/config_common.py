"""固定规则配置公共常量与基础归一化辅助。"""

from __future__ import annotations

import re
from pathlib import Path

from backend.app.api.fixed_rules_schemas import (
    FixedRuleGroup,
    FixedRulesConfigIssue,
    UNGROUPED_GROUP_ID,
    UNGROUPED_GROUP_NAME,
)
from backend.app.api.schemas import VariableTag
from backend.app.rules.domain.operators import (
    normalize_expected_value_mode,
    parse_expected_value_set,
)


FIXED_RULES_CONFIG_VERSION = 6
COMPOSITE_KEY_FIELD = "__key__"
SUPPORTED_FIXED_RULE_TYPES = {
    "fixed_value_compare",
    "regex_check",
    "not_null",
    "unique",
    "sequence_order_check",
    "cross_table_mapping",
    "composite_condition_check",
    "dual_composite_compare",
    "multi_composite_pipeline_check",
    "multi_composite_mapping_check",
    "package_items_compare",
    "event_task_reward",
    "event_task_validation",
}
SUPPORTED_FIXED_RULE_OPERATORS = {"eq", "ne", "gt", "lt"}
SUPPORTED_COMPOSITE_FILTER_OPERATORS = {
    "eq",
    "ne",
    "gt",
    "lt",
    "not_null",
    "contains",
    "not_contains",
}
SUPPORTED_COMPOSITE_ASSERTION_OPERATORS = {
    "eq",
    "ne",
    "gt",
    "lt",
    "not_null",
    "regex",
    "unique",
    "duplicate_required",
}
SUPPORTED_MULTI_PIPELINE_ASSERTION_OPERATORS = {
    "eq",
    "ne",
    "gt",
    "lt",
    "not_null",
    "regex",
    "unique",
    "duplicate_required",
}
SUPPORTED_DUAL_COMPOSITE_OPERATORS = {"eq", "ne", "gt", "lt", "not_null"}
SUPPORTED_DUAL_COMPOSITE_KEY_CHECK_MODES = {"baseline_only", "bidirectional"}
COMPARE_STYLE_OPERATORS = {"eq", "ne", "gt", "lt"}
SET_STYLE_OPERATORS = {"unique", "duplicate_required"}
SUPPORTED_LOCAL_SOURCE_SUFFIXES = {
    "local_excel": {".xls", ".xlsx"},
    "local_csv": {".csv"},
}


def _normalize_expected_value_mode_for_operator(
    *,
    operator: str,
    expected_value: str,
    expected_value_mode: str | None,
    context: str,
) -> str | None:
    """校验固定值模式；仅 eq/ne 支持规则集。"""
    try:
        normalized_mode = normalize_expected_value_mode(expected_value_mode)
    except ValueError as exc:
        raise ValueError(f"{context} 的 expected_value_mode 仅支持 single 或 set。") from exc

    if normalized_mode == "set":
        if operator not in {"eq", "ne"}:
            raise ValueError(f"{context} 只有等于/不等于支持规则集比较值。")
        try:
            parse_expected_value_set(expected_value)
        except ValueError as exc:
            raise ValueError(f"{context} 的规则集至少需要一个固定值。") from exc

    return "set" if normalized_mode == "set" else None


def _normalize_sequence_numeric(
    value: str | None,
    *,
    field_name: str,
    rule_id: str,
    positive_only: bool = False,
) -> str:
    """校验并规范顺序校验使用的数字参数。"""
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"规则 '{rule_id}' 缺少 {field_name}。")

    try:
        numeric = float(normalized)
    except ValueError as exc:
        raise ValueError(f"规则 '{rule_id}' 的 {field_name} 必须是合法数字。") from exc

    if positive_only and numeric <= 0:
        raise ValueError(f"规则 '{rule_id}' 的 {field_name} 必须大于 0。")

    if numeric.is_integer():
        return str(int(numeric))
    return format(numeric, "g")


def _collect_composite_available_fields(variable: VariableTag) -> list[str]:
    """??????????????????"""
    available_fields = [COMPOSITE_KEY_FIELD]
    key_column = variable.key_column or ""
    if key_column.strip():
        available_fields.append(key_column)
    available_fields.extend(
        column
        for column in (variable.columns or [])
        if column and column.strip()
    )
    available_fields = list(dict.fromkeys(available_fields))
    return available_fields


def _normalize_display_field(
    *,
    rule_id: str,
    variable: VariableTag,
    display_field: str | None,
) -> str | None:
    """校验规则结果显示字段，并限制在当前关联变量内。"""
    normalized_field = (display_field or "").strip()
    if not normalized_field:
        return None

    if (variable.variable_kind or "single") == "composite":
        available_fields = _collect_composite_available_fields(variable)
    else:
        available_fields = [variable.column] if variable.column else []

    if normalized_field not in available_fields:
        raise ValueError(
            f"规则 '{rule_id}' 的结果显示字段 '{normalized_field}' 不属于当前关联变量。"
        )
    return normalized_field


def _normalize_local_source_path(
    source_id: str,
    raw_path: str,
    source_type: str,
) -> Path:
    """?????????????"""
    if not raw_path.strip():
        raise ValueError(f"数据源“{source_id}”缺少本地文件路径。")

    normalized_path = Path(raw_path).expanduser().resolve(strict=False)
    allowed_suffixes = SUPPORTED_LOCAL_SOURCE_SUFFIXES.get(source_type)
    if allowed_suffixes and normalized_path.suffix.lower() not in allowed_suffixes:
        suffix_text = " / ".join(sorted(allowed_suffixes))
        raise ValueError(
            f"数据源“{source_id}”的文件格式不正确，当前仅支持 {suffix_text}。"
        )
    return normalized_path


def _normalize_local_path_replacement_presets(presets: list[str] | None) -> list[str]:
    """规范化并去重本地路径管理目录列表。"""
    normalized_presets: list[str] = []
    seen_presets: set[str] = set()
    for preset in presets or []:
        normalized_preset = str(preset or "").strip()
        if not normalized_preset:
            continue
        resolved_preset = str(Path(normalized_preset).expanduser().resolve(strict=False))
        dedupe_key = resolved_preset.lower()
        if dedupe_key in seen_presets:
            continue
        seen_presets.add(dedupe_key)
        normalized_presets.append(resolved_preset)
    return normalized_presets


def _normalize_selected_local_path_replacement_preset(
    selected_preset: str | None,
    presets: list[str] | None,
) -> str | None:
    """规范化当前选中的本地路径管理目录。"""
    normalized_selected = str(selected_preset or "").strip()
    if not normalized_selected:
        return None

    resolved_selected = str(Path(normalized_selected).expanduser().resolve(strict=False))
    normalized_presets = _normalize_local_path_replacement_presets(presets)
    if any(preset.lower() == resolved_selected.lower() for preset in normalized_presets):
        return resolved_selected
    return None


def _normalize_svn_path_replacement_presets(presets: list[str] | None) -> list[str]:
    """规范化并去重 SVN 路径管理目录列表。"""
    normalized_presets: list[str] = []
    seen_presets: set[str] = set()
    for preset in presets or []:
        normalized_preset = str(preset or "").strip()
        if not normalized_preset:
            continue
        if not normalized_preset.endswith("/"):
            normalized_preset = f"{normalized_preset}/"
        dedupe_key = normalized_preset.lower()
        if dedupe_key in seen_presets:
            continue
        seen_presets.add(dedupe_key)
        normalized_presets.append(normalized_preset)
    return normalized_presets


def _normalize_selected_svn_path_replacement_preset(
    selected_preset: str | None,
    presets: list[str] | None,
) -> str | None:
    """规范化当前选中的 SVN 路径管理目录。"""
    normalized_selected = str(selected_preset or "").strip()
    if not normalized_selected:
        return None

    if not normalized_selected.endswith("/"):
        normalized_selected = f"{normalized_selected}/"
    normalized_presets = _normalize_svn_path_replacement_presets(presets)
    if any(preset.lower() == normalized_selected.lower() for preset in normalized_presets):
        return normalized_selected
    return None


def _normalize_columns(columns: list[str]) -> list[str]:
    """?????????"""
    normalized_columns: list[str] = []
    seen_columns: set[str] = set()
    for column in columns:
        if not column.strip() or column in seen_columns:
            continue
        normalized_columns.append(column)
        seen_columns.add(column)
    return normalized_columns


def _resolve_identifier_against_available(
    requested_value: str,
    available_values: list[str],
    *,
    identifier_label: str,
    context: str,
) -> str:
    """优先按原始值匹配，找不到时兼容 trim 后的唯一匹配。"""
    if requested_value in available_values:
        return requested_value

    normalized_requested = requested_value.strip()
    if not normalized_requested:
        raise ValueError(f"{context}缺少{identifier_label}。")

    matched_values = [
        candidate
        for candidate in available_values
        if candidate.strip() == normalized_requested
    ]
    if len(matched_values) == 1:
        return matched_values[0]
    if len(matched_values) > 1:
        raise ValueError(
            f"{context}中的{identifier_label}“{requested_value}”在忽略首尾空白后匹配到多个候选：{matched_values}。"
        )

    raise ValueError(f"{context}中未找到{identifier_label}“{requested_value}”。")


def _resolve_identifiers_against_available(
    requested_values: list[str],
    available_values: list[str],
    *,
    identifier_label: str,
    context: str,
) -> list[str]:
    """批量解析真实标识，并保持顺序去重。"""
    resolved_values: list[str] = []
    seen_values: set[str] = set()

    for requested_value in requested_values:
        resolved_value = _resolve_identifier_against_available(
            requested_value,
            available_values,
            identifier_label=identifier_label,
            context=context,
        )
        if resolved_value in seen_values:
            continue
        resolved_values.append(resolved_value)
        seen_values.add(resolved_value)

    return resolved_values


def _append_config_issue(
    issues: list[FixedRulesConfigIssue],
    issue_keys: set[tuple[str, str | None, str | None, str | None, str]] | None,
    *,
    message: str,
    level: str = "warning",
    source_id: str | None = None,
    variable_tag: str | None = None,
    rule_id: str | None = None,
) -> None:
    """?????????????????"""
    issue_key = (level, source_id, variable_tag, rule_id, message)
    if issue_keys is not None and issue_key in issue_keys:
        return

    issues.append(
        FixedRulesConfigIssue(
            level=level,
            source_id=source_id,
            variable_tag=variable_tag,
            rule_id=rule_id,
            message=message,
        )
    )
    if issue_keys is not None:
        issue_keys.add(issue_key)


def _build_default_group() -> FixedRuleGroup:
    """????????"""
    return FixedRuleGroup(
        group_id=UNGROUPED_GROUP_ID,
        group_name=UNGROUPED_GROUP_NAME,
        builtin=True,
    )


def _normalize_group_name(group_id: str, group_name: str) -> str:
    """修正已知的历史乱码分组名称，避免运行态配置继续回显脏数据。"""
    if group_id == UNGROUPED_GROUP_ID and (
        not group_name or "æ" in group_name or "?" in group_name
    ):
        return UNGROUPED_GROUP_NAME

    if group_id == "basic-checks" and (
        not group_name or group_name.strip("?") == "" or "æ" in group_name
    ):
        return "基础校验"

    return group_name


def _build_source_id_from_path(source_path: Path, seen_ids: set[str]) -> str:
    """?????????????? source_id?"""
    raw_stem = re.sub(r"[^0-9A-Za-z_-]+", "-", source_path.stem).strip("-").lower()
    base_id = raw_stem or "source"
    if base_id not in seen_ids:
        return base_id

    index = 2
    while f"{base_id}-{index}" in seen_ids:
        index += 1
    return f"{base_id}-{index}"


def _build_single_variable_tag(
    *,
    source_id: str,
    sheet: str,
    column: str,
    seen_tags: set[str],
) -> str:
    """???????????????"""
    base_tag = f"[{source_id}-{sheet.strip() or 'sheet'}-{column.strip() or 'column'}]"
    if base_tag not in seen_tags:
        return base_tag

    index = 2
    while f"{base_tag[:-1]}-{index}]" in seen_tags:
        index += 1
    return f"{base_tag[:-1]}-{index}]"
