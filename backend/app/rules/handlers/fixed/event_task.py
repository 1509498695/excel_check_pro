"""节日任务奖励校验 handler。"""

from __future__ import annotations

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
    _get_field_display_name,
    _get_fixed_rule_param,
)
from backend.app.rules.infrastructure.tag_extractor import by_left_and_right_tag
from backend.app.services.event_task_reward_validator import (
    EventTaskExtraVariableTask,
    EventTaskRewardValidationTaskResult,
    validateEventTaskRewards,
)
from backend.app.services.event_task_variable_parser import parseEventTaskVariables
from backend.app.services.reward_parser import RewardCountMismatch, RewardItem, parseLootString


EVENT_TASK_RULE_TYPES = {"event_task_reward", "event_task_validation"}


@register_rule("event_task_reward", dependent_tags=by_left_and_right_tag)
def check_event_task_reward(
    rule: ValidationRule,
    context: RuleExecutionContext,
) -> list[dict[str, Any]]:
    """校验飞书节日任务规划奖励与 EventTask 组合变量 STR_Loot 是否一致。"""

    return _check_event_task_reward(rule, context)


@register_rule("event_task_validation", dependent_tags=by_left_and_right_tag)
def check_event_task_validation(
    rule: ValidationRule,
    context: RuleExecutionContext,
) -> list[dict[str, Any]]:
    """旧 rule_type 兼容入口，内部使用节日任务奖励集合校验。"""

    return _check_event_task_reward(rule, context)


def _check_event_task_reward(
    rule: ValidationRule,
    context: RuleExecutionContext,
) -> list[dict[str, Any]]:
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
    match_strategy = _get_match_strategy(rule)
    task_group_filters = _normalize_task_group_id_filters(
        rule.params.get("task_group_id_filter")
    )
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

    feishu_tasks = _build_feishu_tasks(
        left_frame,
        task_group_field=left_task_group_field,
        task_id_field=left_task_id_field,
        task_desc_field=left_task_desc_field,
        task_loot_field=left_task_loot_field,
        task_group_filters=task_group_filters,
    )
    variable_tasks = parseEventTaskVariables(
        _build_variable_data(
            right_frame,
            task_group_field=right_task_group_field,
            task_id_field=right_task_id_field,
            task_desc_field=right_task_desc_field,
            task_loot_field=right_task_loot_field,
            task_group_filters=task_group_filters,
        )
    )
    scope = (
        {"taskGroupIds": task_group_filters}
        if task_group_filters is not None
        else "all"
    )
    summary = validateEventTaskRewards(
        {
            "feishuTasks": feishu_tasks,
            "variableTasks": variable_tasks,
            "matchStrategy": match_strategy,
            "scope": scope,
        }
    )

    compare_location = _build_compare_location(
        left_variable=left_variable,
        right_variable=right_variable,
        left_field=left_task_desc_field,
        right_field=right_task_desc_field,
    )
    right_location = _build_rule_location(right_variable, right_task_desc_field)
    left_location = _build_rule_location(left_variable, left_task_desc_field)
    abnormal_results: list[dict[str, Any]] = []

    for result in summary.results:
        _append_validation_result_abnormals(
            abnormal_results,
            result=result,
            rule_name=rule_name,
            location=compare_location,
            missing_location=right_location,
            warning_location=compare_location,
        )
    for extra_task in summary.extra_variable_tasks:
        _append_extra_variable_task_result(
            abnormal_results,
            extra_task=extra_task,
            rule_name=rule_name,
            location=left_location,
        )

    return abnormal_results


def _build_feishu_tasks(
    frame: pd.DataFrame,
    *,
    task_group_field: str,
    task_id_field: str,
    task_desc_field: str,
    task_loot_field: str,
    task_group_filters: list[str] | None,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        task_group_id = _normalize_id_text(row[task_group_field]) or ""
        if task_group_filters is not None and task_group_id not in task_group_filters:
            continue
        raw_loot = _normalize_text(row[task_loot_field])
        parse_result = parseLootString(raw_loot, field_label="STR_Loot")
        tasks.append(
            {
                "taskGroupId": task_group_id,
                "taskId": _normalize_id_text(row[task_id_field]),
                "desc": _normalize_text(row[task_desc_field]) or "",
                "rowIndex": _normalize_row_index(row.get("_row_index")),
                "rewards": list(parse_result.rewards),
                "warnings": [
                    issue.message
                    for issue in [*parse_result.warnings, *parse_result.errors]
                ],
            }
        )
    return tasks


def _build_variable_data(
    frame: pd.DataFrame,
    *,
    task_group_field: str,
    task_id_field: str,
    task_desc_field: str,
    task_loot_field: str,
    task_group_filters: list[str] | None,
) -> dict[str, dict[str, Any]]:
    variable_data: dict[str, dict[str, Any]] = {}
    for _, row in frame.iterrows():
        task_group_id = _normalize_id_text(row[task_group_field]) or ""
        if task_group_filters is not None and task_group_id not in task_group_filters:
            continue
        row_index = _normalize_row_index(row.get("_row_index"))
        variable_key = _normalize_text(row.get(COMPOSITE_KEY_FIELD)) or f"{task_group_id}_{row_index}"
        variable_data[variable_key] = {
            "INT_TaskID": row[task_id_field],
            "STR_Title": row["STR_Title"] if "STR_Title" in row.index else None,
            "STR_Desc": row[task_desc_field],
            "STR_Loot": row[task_loot_field],
        }
    return variable_data


def _append_validation_result_abnormals(
    abnormal_results: list[dict[str, Any]],
    *,
    result: EventTaskRewardValidationTaskResult,
    rule_name: str,
    location: str,
    missing_location: str,
    warning_location: str,
) -> None:
    if result.error_message == "未找到对应组合变量任务":
        _append_event_task_result(
            abnormal_results,
            row_index=result.feishu_row_index or 0,
            raw_value=result.task_desc,
            rule_name=rule_name,
            location=missing_location,
            message=(
                f"EventTask 缺失：任务组 {result.task_group_id} 未找到任务 "
                f"{result.task_desc}。"
            ),
            result=result,
            error_type="right_missing_task",
            left_value=result.task_desc,
            right_value=None,
        )
    elif result.error_message == "匹配到多个组合变量任务":
        _append_event_task_result(
            abnormal_results,
            row_index=result.feishu_row_index or 0,
            raw_value=result.task_desc,
            rule_name=rule_name,
            location=location,
            message=(
                f"匹配到多个 EventTask 任务：任务组 {result.task_group_id} / "
                f"{result.task_desc}。"
            ),
            result=result,
            error_type="duplicate_variable_match",
            left_value=result.task_desc,
            right_value=None,
        )

    should_emit_reward_diffs = result.error_message not in {
        "未找到对应组合变量任务",
        "匹配到多个组合变量任务",
    }

    for reward in (result.missing_rewards if should_emit_reward_diffs else []):
        _append_event_task_result(
            abnormal_results,
            row_index=result.feishu_row_index or 0,
            raw_value=_format_rewards(result.expected_rewards),
            rule_name=rule_name,
            location=location,
            message=(
                f"EventTask 缺少奖励：任务组 {result.task_group_id} / "
                f"{result.task_desc} 缺少 {reward.item_id}x{reward.count}。"
            ),
            result=result,
            error_type="missing_reward",
            item_id=reward.item_id,
            left_value=_reward_to_dict(reward),
            right_value=None,
        )
    for reward in (result.extra_rewards if should_emit_reward_diffs else []):
        _append_event_task_result(
            abnormal_results,
            row_index=result.feishu_row_index or 0,
            raw_value=_format_rewards(result.actual_rewards),
            rule_name=rule_name,
            location=location,
            message=(
                f"EventTask 多余奖励：任务组 {result.task_group_id} / "
                f"{result.task_desc} 多出 {reward.item_id}x{reward.count}。"
            ),
            result=result,
            error_type="extra_reward",
            item_id=reward.item_id,
            left_value=None,
            right_value=_reward_to_dict(reward),
        )
    for mismatch in (result.count_mismatches if should_emit_reward_diffs else []):
        _append_event_task_result(
            abnormal_results,
            row_index=result.feishu_row_index or 0,
            raw_value=_format_rewards(result.expected_rewards),
            rule_name=rule_name,
            location=location,
            message=(
                f"奖励数量不一致：任务组 {result.task_group_id} / {result.task_desc} / "
                f"道具 {mismatch.item_id}，飞书={mismatch.expected_count}，"
                f"EventTask={mismatch.actual_count}。"
            ),
            result=result,
            error_type="count_mismatch",
            item_id=mismatch.item_id,
            left_value=mismatch.expected_count,
            right_value=mismatch.actual_count,
            count_mismatch=mismatch,
        )

    if (
        result.status == "fail"
        and not result.missing_rewards
        and not result.extra_rewards
        and not result.count_mismatches
        and result.error_message not in {"未找到对应组合变量任务", "匹配到多个组合变量任务"}
    ):
        _append_event_task_result(
            abnormal_results,
            row_index=result.feishu_row_index or 0,
            raw_value=result.task_desc,
            rule_name=rule_name,
            location=location,
            message=result.error_message or "节日任务奖励校验失败。",
            result=result,
            error_type="event_task_reward_failed",
            left_value=_format_rewards(result.expected_rewards),
            right_value=_format_rewards(result.actual_rewards),
        )

    for warning in [*result.duplicate_warnings, *result.parse_warnings]:
        _append_event_task_result(
            abnormal_results,
            row_index=result.feishu_row_index or 0,
            raw_value=warning,
            rule_name=rule_name,
            location=warning_location,
            message=f"Warning：{warning}",
            result=result,
            error_type="event_task_warning",
            left_value=warning,
            right_value=None,
        )


def _append_extra_variable_task_result(
    abnormal_results: list[dict[str, Any]],
    *,
    extra_task: EventTaskExtraVariableTask,
    rule_name: str,
    location: str,
) -> None:
    result = build_fixed_result(
        row_index=0,
        raw_value=extra_task.task_desc,
        rule_name=rule_name,
        location=location,
        message=(
            f"飞书任务表缺失：任务组 {extra_task.task_group_id} 未找到 EventTask 任务 "
            f"{extra_task.task_desc}。"
        ),
    )
    result.update(
        {
            "task_group_id": extra_task.task_group_id,
            "task_desc": extra_task.task_desc,
            "task_id": extra_task.variable_task_id,
            "variable_key": extra_task.variable_key,
            "variable_task_id": extra_task.variable_task_id,
            "match_strategy": None,
            "status": "fail",
            "error_type": "extra_variable_task",
            "left_value": None,
            "right_value": _format_rewards(extra_task.actual_rewards),
            "actual_rewards": [_reward_to_dict(reward) for reward in extra_task.actual_rewards],
            "parse_warnings": list(extra_task.parse_warnings),
        }
    )
    abnormal_results.append(result)


def _append_event_task_result(
    abnormal_results: list[dict[str, Any]],
    *,
    row_index: int,
    raw_value: Any,
    rule_name: str,
    location: str,
    message: str,
    result: EventTaskRewardValidationTaskResult,
    error_type: str,
    left_value: Any,
    right_value: Any,
    item_id: int | None = None,
    count_mismatch: RewardCountMismatch | None = None,
) -> None:
    fixed_result = build_fixed_result(
        row_index=row_index,
        raw_value=raw_value,
        display_value=result.task_desc,
        rule_name=rule_name,
        location=location,
        message=message,
    )
    fixed_result.update(
        {
            "task_group_id": result.task_group_id,
            "task_desc": result.task_desc,
            "task_id": result.variable_task_id,
            "item_id": item_id,
            "variable_key": result.variable_key,
            "variable_task_id": result.variable_task_id,
            "match_strategy": result.match_strategy,
            "status": result.status,
            "error_type": error_type,
            "left_value": left_value,
            "right_value": right_value,
            "expected_rewards": [
                _reward_to_dict(reward) for reward in result.expected_rewards
            ],
            "actual_rewards": [_reward_to_dict(reward) for reward in result.actual_rewards],
            "missing_rewards": [
                _reward_to_dict(reward) for reward in result.missing_rewards
            ],
            "extra_rewards": [_reward_to_dict(reward) for reward in result.extra_rewards],
            "count_mismatches": [
                _mismatch_to_dict(mismatch) for mismatch in result.count_mismatches
            ],
            "duplicate_warnings": list(result.duplicate_warnings),
            "parse_warnings": list(result.parse_warnings),
            "error_message": result.error_message,
        }
    )
    if count_mismatch is not None:
        fixed_result["count_mismatch"] = _mismatch_to_dict(count_mismatch)
    abnormal_results.append(fixed_result)


def _get_match_strategy(rule: ValidationRule) -> str:
    raw_value = rule.params.get("event_task_match_strategy") or rule.params.get("match_strategy")
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value.strip()
    return "groupId_desc_then_taskId"


def _reward_to_dict(reward: RewardItem) -> dict[str, Any]:
    return {
        "type": reward.type,
        "item_id": reward.item_id,
        "itemId": reward.item_id,
        "count": reward.count,
        "name": reward.name,
        "source": reward.source,
    }


def _mismatch_to_dict(mismatch: RewardCountMismatch) -> dict[str, Any]:
    return {
        "item_id": mismatch.item_id,
        "itemId": mismatch.item_id,
        "expected_count": mismatch.expected_count,
        "expectedCount": mismatch.expected_count,
        "actual_count": mismatch.actual_count,
        "actualCount": mismatch.actual_count,
    }


def _format_rewards(rewards: list[RewardItem]) -> str:
    if not rewards:
        return "无"
    return ", ".join(f"{reward.item_id}x{reward.count}" for reward in rewards)


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


def _normalize_row_index(value: Any) -> int:
    normalized = _normalize_id_text(value)
    if normalized and re.fullmatch(r"[+-]?\d+", normalized):
        return int(normalized)
    return 0


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
