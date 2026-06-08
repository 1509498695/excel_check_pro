"""运行时解析节日任务表并注入临时组合变量。"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

import pandas as pd
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.fixed_rules_schemas import (
    EventTaskParseConfig,
    FixedRuleDefinition,
    FixedRulesConfig,
)
from backend.app.api.schemas import DataSource, TaskTree, ValidationRule, VariableTag
from backend.app.integrations.feishu_client import FEISHU_API_ERROR, FeishuClientError
from backend.app.rules.domain.result import build_fixed_result
from backend.app.services.event_task_parser import preview_event_tasks_from_feishu


RUNTIME_EVENT_TASK_SOURCE_ID = "__runtime_event_task_plan__"
RUNTIME_EVENT_TASK_TAG_PREFIX = f"{RUNTIME_EVENT_TASK_SOURCE_ID}:"
RUNTIME_TASK_GROUP_FIELD = "任务组ID"
RUNTIME_TASK_ID_FIELD = "INT_TaskID"
RUNTIME_TASK_DESC_FIELD = "任务描述"
RUNTIME_TASK_LOOT_FIELD = "STR_Loot"
RUNTIME_COLUMNS = [
    RUNTIME_TASK_GROUP_FIELD,
    RUNTIME_TASK_ID_FIELD,
    RUNTIME_TASK_DESC_FIELD,
    RUNTIME_TASK_LOOT_FIELD,
]
EVENT_TASK_RULE_TYPES = {"event_task_reward", "event_task_validation"}


@dataclass(frozen=True)
class EventTaskRuntimePreparation:
    """固定规则执行前生成的运行时配置与预加载数据。"""

    config: FixedRulesConfig
    preloaded_variable_frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    parse_metadata: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class EventTaskTaskTreeRuntimePreparation:
    """个人校验执行前生成的运行时 TaskTree 与预加载数据。"""

    task_tree: TaskTree
    preloaded_variable_frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    abnormal_results: list[dict[str, Any]] = field(default_factory=list)
    parse_metadata: list[dict[str, Any]] = field(default_factory=list)


async def prepare_event_task_runtime_config(
    config: FixedRulesConfig,
    *,
    db: AsyncSession,
    project_id: int,
    user_id: int | None = None,
    selected_rule_ids: list[str] | None = None,
) -> EventTaskRuntimePreparation:
    """为带飞书解析配置的节日任务规则生成临时左侧组合变量。"""
    del user_id
    selected_rule_id_set = _normalize_selected_rule_ids(selected_rule_ids)
    source_map = {source.id: source for source in config.sources}
    runtime_variables: list[VariableTag] = []
    preloaded_frames: dict[str, pd.DataFrame] = {}
    parse_metadata: list[dict[str, Any]] = []
    next_rules: list[FixedRuleDefinition] = []

    for rule in config.rules:
        if not _should_prepare_runtime_rule(rule, selected_rule_id_set):
            next_rules.append(rule)
            continue

        assert rule.event_task_parse_config is not None
        parse_config = rule.event_task_parse_config
        source = _get_feishu_source(source_map, parse_config.feishu_source_id, rule.rule_id)
        explicit_filter = _resolve_explicit_runtime_task_group_id_filter(
            rule.task_group_id_filter,
            parse_config.validation_scope,
            parse_config.task_group_id_filter,
        )
        if parse_config.validation_scope == "specified" and not explicit_filter:
            raise ValueError(f"飞书解析失败：规则 '{rule.rule_id}' 缺少指定任务组 ID。")

        preview = await preview_event_tasks_from_feishu(
            source,
            sheet_id=parse_config.feishu_sheet_id,
            parse_strategy=parse_config.parse_strategy,
            ai_parse_mode=parse_config.ai_parse_mode,
            key_delimiter=parse_config.key_delimiter or "_",
            fallback_match_field=parse_config.fallback_match_field or "INT_TaskID",
            db=db,
            project_id=project_id,
            event_task_field_mapping=parse_config.event_task_field_mapping,
        )
        if preview.parse_status != "success":
            messages = [*preview.errors, *preview.warnings]
            warning_text = "；".join(messages) if messages else "解析结果失败。"
            raise ValueError(f"飞书解析失败：规则 '{rule.rule_id}' {warning_text}")
        if not preview.rows:
            raise ValueError(f"未识别到节日任务明细：规则 '{rule.rule_id}' 未解析到有效明细行。")

        effective_filter = _resolve_runtime_task_group_id_filter(
            rule.task_group_id_filter,
            parse_config.validation_scope,
            parse_config.task_group_id_filter,
            preview_task_group_ids=preview.task_group_ids,
        )
        filtered_rows = _filter_preview_rows(preview.rows, effective_filter)
        temp_tag = f"{RUNTIME_EVENT_TASK_TAG_PREFIX}{rule.rule_id}"
        runtime_variables.append(
            VariableTag(
                tag=temp_tag,
                source_id=RUNTIME_EVENT_TASK_SOURCE_ID,
                sheet=parse_config.feishu_sheet_name or parse_config.feishu_sheet_id,
                variable_kind="composite",
                columns=list(RUNTIME_COLUMNS),
                key_column=RUNTIME_TASK_GROUP_FIELD,
                append_index_to_key=True,
                expected_type="json",
            )
        )
        preloaded_frames[temp_tag] = _build_event_task_frame(filtered_rows)
        parse_metadata.append(_build_parse_metadata(rule.rule_id, preview))
        next_rules.append(
            _build_runtime_rule(
                rule,
                temp_tag,
                task_group_id_filter=effective_filter,
            )
        )

    if not runtime_variables:
        return EventTaskRuntimePreparation(config=config)

    runtime_sources = list(config.sources)
    if RUNTIME_EVENT_TASK_SOURCE_ID not in source_map:
        runtime_sources.append(
            DataSource(
                id=RUNTIME_EVENT_TASK_SOURCE_ID,
                type="local_excel",
                path=RUNTIME_EVENT_TASK_SOURCE_ID,
            )
        )

    runtime_config = config.model_copy(
        update={
            "sources": runtime_sources,
            "variables": [*config.variables, *runtime_variables],
            "rules": next_rules,
        }
    )
    return EventTaskRuntimePreparation(
        config=runtime_config,
        preloaded_variable_frames=preloaded_frames,
        parse_metadata=parse_metadata,
    )


async def prepare_event_task_runtime_task_tree(
    task_tree: TaskTree,
    *,
    db: AsyncSession,
    project_id: int | None,
    user_id: int | None = None,
) -> EventTaskTaskTreeRuntimePreparation:
    """为个人校验 TaskTree 中的节日任务规则注入运行时左侧组合变量。"""
    del user_id
    selected_rule_id_set = _normalize_selected_rule_ids(task_tree.selected_rule_ids)
    source_map = {source.id: source for source in task_tree.sources}
    runtime_variables: list[VariableTag] = []
    preloaded_frames: dict[str, pd.DataFrame] = {}
    parse_metadata: list[dict[str, Any]] = []
    abnormal_results: list[dict[str, Any]] = []
    next_rules: list[ValidationRule] = []
    used_runtime_tags = {variable.tag for variable in task_tree.variables}

    for index, rule in enumerate(task_tree.rules):
        if not _should_prepare_task_tree_runtime_rule(rule, selected_rule_id_set):
            next_rules.append(rule)
            continue

        rule_key = _get_runtime_rule_key(rule, index)
        params = dict(rule.params)
        try:
            _get_task_tree_right_tag(rule)
            parse_config = _get_task_tree_event_parse_config(params)
            explicit_filter = _resolve_explicit_runtime_task_group_id_filter(
                _optional_string(params.get("task_group_id_filter")),
                parse_config.validation_scope,
                parse_config.task_group_id_filter,
            )
            if parse_config.validation_scope == "specified" and not explicit_filter:
                raise ValueError("指定任务组校验缺少 task_group_id_filter。")
            source = _get_feishu_source(source_map, parse_config.feishu_source_id, rule_key)
            if project_id is None:
                raise FeishuClientError(FEISHU_API_ERROR, "缺少项目上下文，无法读取飞书 Sheet。")
            preview = await preview_event_tasks_from_feishu(
                source,
                sheet_id=parse_config.feishu_sheet_id,
                parse_strategy=parse_config.parse_strategy,
                ai_parse_mode=parse_config.ai_parse_mode,
                key_delimiter=parse_config.key_delimiter or "_",
                fallback_match_field=parse_config.fallback_match_field or "INT_TaskID",
                db=db,
                project_id=project_id,
                event_task_field_mapping=parse_config.event_task_field_mapping,
            )
        except FeishuClientError as exc:
            abnormal_results.append(
                _build_runtime_failure_result(
                    rule=rule,
                    rule_key=rule_key,
                    error_type="feishu_read_failed",
                    message=f"飞书读取失败：{exc}",
                )
            )
            continue
        except (ValidationError, ValueError, FileNotFoundError, ImportError) as exc:
            abnormal_results.append(
                _build_runtime_failure_result(
                    rule=rule,
                    rule_key=rule_key,
                    error_type="event_task_parse_failed",
                    message=f"节日任务表解析失败：{exc}",
                )
            )
            continue

        if preview.parse_status != "success":
            abnormal_results.append(
                _build_runtime_failure_result(
                    rule=rule,
                    rule_key=rule_key,
                    error_type="event_task_parse_failed",
                    message=_format_preview_failure_message(preview),
                )
            )
            continue
        if not preview.rows:
            abnormal_results.append(
                _build_runtime_failure_result(
                    rule=rule,
                    rule_key=rule_key,
                    error_type="event_task_parse_failed",
                    message=f"节日任务表解析失败：规则 '{rule_key}' 未识别到有效任务明细。",
                )
            )
            continue

        effective_filter = _resolve_runtime_task_group_id_filter(
            _optional_string(params.get("task_group_id_filter")),
            parse_config.validation_scope,
            parse_config.task_group_id_filter,
            preview_task_group_ids=preview.task_group_ids,
        )
        filtered_rows = _filter_preview_rows(preview.rows, effective_filter)
        temp_tag = _build_unique_runtime_tag(rule_key, index, used_runtime_tags)
        runtime_variables.append(
            VariableTag(
                tag=temp_tag,
                source_id=RUNTIME_EVENT_TASK_SOURCE_ID,
                sheet=parse_config.feishu_sheet_name or parse_config.feishu_sheet_id,
                variable_kind="composite",
                columns=list(RUNTIME_COLUMNS),
                key_column=RUNTIME_TASK_GROUP_FIELD,
                append_index_to_key=True,
                expected_type="json",
            )
        )
        preloaded_frames[temp_tag] = _build_event_task_frame(filtered_rows)
        parse_metadata.append(_build_parse_metadata(rule.rule_id or rule_key, preview))
        next_rules.append(
            _build_task_tree_runtime_rule(
                rule,
                temp_tag,
                task_group_id_filter=effective_filter,
            )
        )

    if not runtime_variables and not abnormal_results:
        return EventTaskTaskTreeRuntimePreparation(task_tree=task_tree)

    runtime_sources = list(task_tree.sources)
    if runtime_variables and RUNTIME_EVENT_TASK_SOURCE_ID not in source_map:
        runtime_sources.append(
            DataSource(
                id=RUNTIME_EVENT_TASK_SOURCE_ID,
                type="local_excel",
                path=RUNTIME_EVENT_TASK_SOURCE_ID,
            )
        )

    runtime_task_tree = task_tree.model_copy(
        update={
            "sources": runtime_sources,
            "variables": [*task_tree.variables, *runtime_variables],
            "rules": next_rules,
        }
    )
    return EventTaskTaskTreeRuntimePreparation(
        task_tree=runtime_task_tree,
        preloaded_variable_frames=preloaded_frames,
        abnormal_results=abnormal_results,
        parse_metadata=parse_metadata,
    )


def _normalize_selected_rule_ids(selected_rule_ids: list[str] | None) -> set[str] | None:
    if selected_rule_ids is None:
        return None
    return {
        rule_id.strip()
        for rule_id in selected_rule_ids
        if isinstance(rule_id, str) and rule_id.strip()
    }


def _should_prepare_runtime_rule(
    rule: FixedRuleDefinition,
    selected_rule_ids: set[str] | None,
) -> bool:
    if not rule.enabled:
        return False
    if selected_rule_ids is not None and rule.rule_id.strip() not in selected_rule_ids:
        return False
    return rule.rule_type in EVENT_TASK_RULE_TYPES and rule.event_task_parse_config is not None


def _should_prepare_task_tree_runtime_rule(
    rule: ValidationRule,
    selected_rule_ids: set[str] | None,
) -> bool:
    if selected_rule_ids is not None:
        rule_id = (rule.rule_id or "").strip()
        if not rule_id or rule_id not in selected_rule_ids:
            return False
    return (
        rule.rule_type in EVENT_TASK_RULE_TYPES
        and isinstance(rule.params.get("event_task_parse_config"), dict)
    )


def _get_feishu_source(
    source_map: dict[str, DataSource],
    source_id: str,
    rule_id: str,
) -> DataSource:
    source = source_map.get(source_id)
    if source is None:
        raise ValueError(f"飞书解析失败：规则 '{rule_id}' 引用了不存在的飞书数据源 '{source_id}'。")
    if source.type != "feishu":
        raise ValueError(f"飞书解析失败：规则 '{rule_id}' 的任务表数据源必须是飞书数据源。")
    return source


def _get_task_tree_event_parse_config(params: dict[str, Any]) -> EventTaskParseConfig:
    payload = params.get("event_task_parse_config")
    if not isinstance(payload, dict):
        raise ValueError("缺少 event_task_parse_config。")
    return EventTaskParseConfig.model_validate(payload)


def _resolve_runtime_task_group_id_filter(
    rule_task_group_id_filter: str | None,
    validation_scope: str | None,
    parse_task_group_id_filter: str | None,
    *,
    preview_task_group_ids: list[str] | None = None,
) -> str | None:
    explicit_filter = _resolve_explicit_runtime_task_group_id_filter(
        rule_task_group_id_filter,
        validation_scope,
        parse_task_group_id_filter,
    )
    if explicit_filter:
        return explicit_filter
    return _build_preview_task_group_id_filter(preview_task_group_ids)


def _resolve_explicit_runtime_task_group_id_filter(
    rule_task_group_id_filter: str | None,
    validation_scope: str | None,
    parse_task_group_id_filter: str | None,
) -> str | None:
    rule_filter = _optional_string(rule_task_group_id_filter)
    if rule_filter:
        return rule_filter
    if validation_scope == "specified":
        return _optional_string(parse_task_group_id_filter)
    return None


def _build_preview_task_group_id_filter(task_group_ids: list[str] | None) -> str | None:
    if not task_group_ids:
        return None
    normalized_ids = _normalize_task_group_id_filters(",".join(task_group_ids))
    if not normalized_ids:
        return None
    return ",".join(normalized_ids)


def _optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_task_group_id_filters(value: str | None) -> list[str] | None:
    if not value:
        return None
    result: list[str] = []
    seen: set[str] = set()
    for item in re.split(r"[,，]", value):
        normalized = _normalize_id_text(item)
        if normalized is None or normalized in seen:
            continue
        result.append(normalized)
        seen.add(normalized)
    return result or None


def _filter_preview_rows(rows: list[Any], task_group_id_filter: str | None) -> list[Any]:
    filters = _normalize_task_group_id_filters(task_group_id_filter)
    if not filters:
        return rows
    filter_set = set(filters)
    return [row for row in rows if row.task_group_id in filter_set]


def _build_event_task_frame(detail_rows: list[Any]) -> pd.DataFrame:
    rows = [
        {
            "__key__": f"{detail_row.task_group_id}_{detail_row.row_index}",
            RUNTIME_TASK_GROUP_FIELD: detail_row.task_group_id,
            RUNTIME_TASK_ID_FIELD: detail_row.task_id,
            RUNTIME_TASK_DESC_FIELD: detail_row.task_desc,
            RUNTIME_TASK_LOOT_FIELD: detail_row.loot,
            "_row_index": detail_row.row_index,
        }
        for detail_row in detail_rows
    ]
    return pd.DataFrame(
        rows,
        columns=["__key__", *RUNTIME_COLUMNS, "_row_index"],
        dtype=object,
    )


def _build_runtime_rule(
    rule: FixedRuleDefinition,
    temp_tag: str,
    *,
    task_group_id_filter: str | None,
) -> FixedRuleDefinition:
    return rule.model_copy(
        update={
            "target_variable_tag": temp_tag,
            "left_task_group_field": RUNTIME_TASK_GROUP_FIELD,
            "left_task_id_field": RUNTIME_TASK_ID_FIELD,
            "left_task_desc_field": RUNTIME_TASK_DESC_FIELD,
            "left_task_loot_field": RUNTIME_TASK_LOOT_FIELD,
            "display_field": rule.display_field or RUNTIME_TASK_GROUP_FIELD,
            "event_task_match_strategy": rule.event_task_match_strategy
            or "groupId_desc_then_taskId",
            "ai_assist_mode": rule.ai_assist_mode or "auto",
            "task_group_id_filter": task_group_id_filter,
            "event_task_parse_config": None,
        }
    )


def _build_task_tree_runtime_rule(
    rule: ValidationRule,
    temp_tag: str,
    *,
    task_group_id_filter: str | None,
) -> ValidationRule:
    params = dict(rule.params)
    right_tag = _get_task_tree_right_tag(rule)

    return rule.model_copy(
        update={
            "params": {
                "left_tag": temp_tag,
                "right_tag": right_tag,
                "rule_name": _optional_string(params.get("rule_name"))
                or _optional_string(rule.rule_id)
                or "节日任务校验",
                "left_task_group_field": RUNTIME_TASK_GROUP_FIELD,
                "left_task_id_field": RUNTIME_TASK_ID_FIELD,
                "left_task_desc_field": RUNTIME_TASK_DESC_FIELD,
                "left_task_loot_field": RUNTIME_TASK_LOOT_FIELD,
                "right_task_group_field": _optional_string(
                    params.get("right_task_group_field")
                )
                or "INT_ID",
                "right_task_id_field": _optional_string(params.get("right_task_id_field"))
                or "INT_TaskID",
                "right_task_desc_field": _optional_string(params.get("right_task_desc_field"))
                or "STR_Desc",
                "right_task_loot_field": _optional_string(params.get("right_task_loot_field"))
                or "STR_Loot",
                "event_task_match_strategy": _optional_string(
                    params.get("event_task_match_strategy")
                )
                or _optional_string(params.get("match_strategy"))
                or "groupId_desc_then_taskId",
                "match_strategy": _optional_string(params.get("match_strategy"))
                or _optional_string(params.get("event_task_match_strategy"))
                or "groupId_desc_then_taskId",
                "ai_assist_mode": _optional_string(params.get("ai_assist_mode")) or "auto",
                "task_group_id_filter": task_group_id_filter,
                "display_field": _optional_string(params.get("display_field"))
                or RUNTIME_TASK_GROUP_FIELD,
            }
        }
    )


def _get_task_tree_right_tag(rule: ValidationRule) -> str:
    params = rule.params
    right_tag = _optional_string(params.get("right_tag")) or _optional_string(
        params.get("reference_variable_tag")
    )
    if not right_tag:
        raise ValueError(f"规则 '{rule.rule_id or rule.rule_type}' 缺少右侧任务配置变量。")
    return right_tag


def _get_runtime_rule_key(rule: ValidationRule, index: int) -> str:
    rule_id = _optional_string(rule.rule_id)
    return rule_id or f"index-{index}"


def _build_unique_runtime_tag(
    rule_key: str,
    index: int,
    used_runtime_tags: set[str],
) -> str:
    base_tag = f"{RUNTIME_EVENT_TASK_TAG_PREFIX}{rule_key}"
    if base_tag not in used_runtime_tags:
        used_runtime_tags.add(base_tag)
        return base_tag
    fallback_tag = f"{base_tag}:{index}"
    used_runtime_tags.add(fallback_tag)
    return fallback_tag


def _format_preview_failure_message(preview: Any) -> str:
    messages = [*preview.errors, *preview.warnings]
    detail = "；".join(messages) if messages else "解析结果失败。"
    return f"节日任务表解析失败：{detail}"


def _build_parse_metadata(rule_id: str | None, preview: Any) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "parse_mode": preview.parse_mode,
        "ai_used": preview.ai_used,
        "task_group_ids": preview.task_group_ids,
        "detail_row_count": preview.detail_row_count,
        "warnings": preview.warnings,
        "errors": preview.errors,
        "raw_sheet_name": preview.raw_sheet_name,
    }


def _build_runtime_failure_result(
    *,
    rule: ValidationRule,
    rule_key: str,
    error_type: str,
    message: str,
) -> dict[str, Any]:
    params = rule.params
    parse_config = params.get("event_task_parse_config")
    raw_value: Any = None
    if isinstance(parse_config, dict):
        raw_value = parse_config.get("feishu_sheet_id") or parse_config.get("sheet_id")
    result = build_fixed_result(
        row_index=0,
        raw_value=raw_value or rule_key,
        rule_name=_optional_string(params.get("rule_name")) or rule_key,
        location="飞书节日任务表",
        message=message,
    )
    result.update(
        {
            "task_group_id": None,
            "task_id": None,
            "error_type": error_type,
            "left_value": raw_value,
            "right_value": None,
        }
    )
    return result


def _normalize_id_text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"[+-]?\d+", text):
        return str(int(text))
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        return str(int(float(text)))
    return text
