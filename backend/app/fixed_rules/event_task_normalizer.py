"""节日任务奖励校验规则归一化。"""

from __future__ import annotations

from backend.app.api.schemas import VariableTag
from backend.app.fixed_rules.config_common import (
    _collect_composite_available_fields,
    _resolve_identifier_against_available,
)


SUPPORTED_EVENT_TASK_RULE_TYPES = {"event_task_reward", "event_task_validation"}
SUPPORTED_EVENT_TASK_MATCH_STRATEGIES = {
    "groupId_desc",
    "groupId_taskId",
    "groupId_desc_then_taskId",
}
SUPPORTED_EVENT_TASK_AI_ASSIST_MODES = {"auto", "on", "off"}


def _normalize_event_task_reward_rule(
    *,
    rule_id: str,
    left_variable: VariableTag | None,
    right_variable_tag: str,
    left_task_group_field: str | None,
    left_task_id_field: str | None,
    left_task_desc_field: str | None,
    left_task_loot_field: str | None,
    right_task_group_field: str | None,
    right_task_id_field: str | None,
    right_task_desc_field: str | None,
    right_task_loot_field: str | None,
    task_group_id_filter: str | None,
    event_task_match_strategy: str | None,
    ai_assist_mode: str | None,
    variable_map: dict[str, VariableTag],
    allow_runtime_left_variable: bool = False,
) -> tuple[str, str, str, str, str, str, str, str, str, str | None, str, str]:
    """校验并规范节日任务奖励校验规则。"""

    normalized_right_tag = right_variable_tag.strip()
    if not normalized_right_tag:
        raise ValueError(f"规则 '{rule_id}' 缺少 reference_variable_tag。")
    if normalized_right_tag not in variable_map:
        raise ValueError(
            f"规则 '{rule_id}' 引用了不存在的 EventTask 配置变量 '{normalized_right_tag}'。"
        )

    right_variable = variable_map[normalized_right_tag]
    if (right_variable.variable_kind or "single") != "composite":
        raise ValueError(
            f"规则 '{rule_id}' 的 EventTask 配置变量 '{normalized_right_tag}' 必须是组合变量。"
        )

    right_fields = _collect_composite_available_fields(right_variable)
    if allow_runtime_left_variable:
        normalized_left_task_group_field = (left_task_group_field or "").strip() or "任务组ID"
        normalized_left_task_id_field = (left_task_id_field or "").strip() or "INT_TaskID"
        normalized_left_task_desc_field = (left_task_desc_field or "").strip() or "任务描述"
        normalized_left_task_loot_field = (left_task_loot_field or "").strip() or "STR_Loot"
    else:
        if left_variable is None:
            raise ValueError(f"规则 '{rule_id}' 缺少左侧节日任务明细变量。")
        left_fields = _collect_composite_available_fields(left_variable)
        normalized_left_task_group_field = _normalize_required_field(
            rule_id=rule_id,
            raw_field=left_task_group_field,
            available_fields=left_fields,
            section_label="左侧任务组 ID 字段",
        )
        normalized_left_task_id_field = _normalize_required_field(
            rule_id=rule_id,
            raw_field=left_task_id_field,
            available_fields=left_fields,
            section_label="左侧任务 ID 字段",
        )
        normalized_left_task_desc_field = _normalize_required_field(
            rule_id=rule_id,
            raw_field=left_task_desc_field,
            available_fields=left_fields,
            section_label="左侧任务描述字段",
        )
        normalized_left_task_loot_field = _normalize_required_field(
            rule_id=rule_id,
            raw_field=left_task_loot_field,
            available_fields=left_fields,
            section_label="左侧 STR_Loot 字段",
        )

    normalized_right_task_group_field = _normalize_required_field(
        rule_id=rule_id,
        raw_field=right_task_group_field,
        available_fields=right_fields,
        section_label="右侧任务组 ID 字段",
    )
    normalized_right_task_id_field = _normalize_required_field(
        rule_id=rule_id,
        raw_field=right_task_id_field,
        available_fields=right_fields,
        section_label="右侧 INT_TaskID 字段",
    )
    normalized_right_task_desc_field = _normalize_required_field(
        rule_id=rule_id,
        raw_field=right_task_desc_field,
        available_fields=right_fields,
        section_label="右侧 STR_Desc 字段",
    )
    normalized_right_task_loot_field = _normalize_required_field(
        rule_id=rule_id,
        raw_field=right_task_loot_field,
        available_fields=right_fields,
        section_label="右侧 STR_Loot 字段",
    )
    normalized_task_group_id_filter = (task_group_id_filter or "").strip() or None
    normalized_match_strategy = (
        (event_task_match_strategy or "").strip() or "groupId_desc_then_taskId"
    )
    if normalized_match_strategy not in SUPPORTED_EVENT_TASK_MATCH_STRATEGIES:
        raise ValueError(
            f"规则 '{rule_id}' 的 event_task_match_strategy 无效：{normalized_match_strategy}。"
        )
    normalized_ai_assist_mode = (ai_assist_mode or "").strip() or "auto"
    if normalized_ai_assist_mode not in SUPPORTED_EVENT_TASK_AI_ASSIST_MODES:
        raise ValueError(f"规则 '{rule_id}' 的 ai_assist_mode 仅支持 auto/on/off。")

    return (
        normalized_right_tag,
        normalized_left_task_group_field,
        normalized_left_task_id_field,
        normalized_left_task_desc_field,
        normalized_left_task_loot_field,
        normalized_right_task_group_field,
        normalized_right_task_id_field,
        normalized_right_task_desc_field,
        normalized_right_task_loot_field,
        normalized_task_group_id_filter,
        normalized_match_strategy,
        normalized_ai_assist_mode,
    )


def _normalize_required_field(
    *,
    rule_id: str,
    raw_field: str | None,
    available_fields: list[str],
    section_label: str,
) -> str:
    normalized_field = (raw_field or "").strip()
    if not normalized_field:
        raise ValueError(f"规则 '{rule_id}' 缺少{section_label}。")
    try:
        return _resolve_identifier_against_available(
            normalized_field,
            available_fields,
            identifier_label=section_label,
            context=f"规则 '{rule_id}'",
        )
    except ValueError as exc:
        raise ValueError(
            f"规则 '{rule_id}' 的{section_label} '{normalized_field}' 不属于对应组合变量。"
        ) from exc
