"""运行时解析礼包规划表并注入临时组合变量。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.fixed_rules_schemas import FixedRuleDefinition, FixedRulesConfig
from backend.app.api.schemas import DataSource, VariableTag
from backend.app.services.package_items_parser import preview_package_items_from_feishu


RUNTIME_PACKAGE_SOURCE_ID = "__runtime_package_plan__"
RUNTIME_PACKAGE_TAG_PREFIX = "__package_plan__:"
RUNTIME_PACKAGE_FIELD = "礼包id"
RUNTIME_ITEM_FIELD = "道具ID"
RUNTIME_COUNT_FIELD = "个数"
RUNTIME_COLUMNS = [RUNTIME_PACKAGE_FIELD, RUNTIME_ITEM_FIELD, RUNTIME_COUNT_FIELD]


@dataclass(frozen=True)
class PackageItemsRuntimePreparation:
    """固定规则执行前生成的运行时配置与预加载数据。"""

    config: FixedRulesConfig
    preloaded_variable_frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    parse_metadata: list[dict[str, Any]] = field(default_factory=list)


async def prepare_package_items_runtime_config(
    config: FixedRulesConfig,
    *,
    db: AsyncSession,
    project_id: int,
    user_id: int | None = None,
    selected_rule_ids: list[str] | None = None,
) -> PackageItemsRuntimePreparation:
    """为带飞书解析配置的礼包规则生成临时左侧组合变量。"""
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

        assert rule.package_parse_config is not None
        parse_config = rule.package_parse_config
        source = _get_feishu_source(source_map, parse_config.feishu_source_id, rule.rule_id)
        preview = await preview_package_items_from_feishu(
            source,
            sheet_id=parse_config.feishu_sheet_id,
            parse_strategy=parse_config.parse_strategy,
            ai_parse_mode=parse_config.ai_parse_mode,
            db=db,
            project_id=project_id,
            user_id=user_id,
        )
        if preview.parse_status != "success":
            messages = [*preview.errors, *preview.warnings]
            warning_text = "；".join(messages) if messages else "解析结果失败。"
            raise ValueError(f"飞书解析失败：规则 '{rule.rule_id}' {warning_text}")
        _ensure_package_field_mapping(rule.rule_id, preview.field_mapping)
        if not preview.rows:
            raise ValueError(f"未识别到礼包明细：规则 '{rule.rule_id}' 未解析到有效明细行。")

        temp_tag = f"{RUNTIME_PACKAGE_TAG_PREFIX}{rule.rule_id}"
        runtime_variables.append(
            VariableTag(
                tag=temp_tag,
                source_id=RUNTIME_PACKAGE_SOURCE_ID,
                sheet=parse_config.feishu_sheet_name or parse_config.feishu_sheet_id,
                variable_kind="composite",
                columns=list(RUNTIME_COLUMNS),
                key_column=RUNTIME_PACKAGE_FIELD,
                append_index_to_key=True,
                expected_type="json",
            )
        )
        preloaded_frames[temp_tag] = _build_package_items_frame(preview.rows)
        parse_metadata.append(
            {
                "rule_id": rule.rule_id,
                "parse_mode": preview.parse_mode,
                "ai_used": preview.ai_used,
                "cache_hit": preview.cache_hit,
                "confidence": preview.confidence,
                "header_rows": preview.header_rows,
                "package_ids": preview.package_ids,
                "detail_row_count": preview.detail_row_count,
                "warnings": preview.warnings,
                "errors": preview.errors,
            }
        )
        next_rules.append(_build_runtime_rule(rule, temp_tag))

    if not runtime_variables:
        return PackageItemsRuntimePreparation(config=config)

    runtime_config = config.model_copy(
        update={
            "variables": [*config.variables, *runtime_variables],
            "rules": next_rules,
        }
    )
    return PackageItemsRuntimePreparation(
        config=runtime_config,
        preloaded_variable_frames=preloaded_frames,
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
    if selected_rule_ids is not None and rule.rule_id.strip() not in selected_rule_ids:
        return False
    return rule.rule_type == "package_items_compare" and rule.package_parse_config is not None


def _get_feishu_source(
    source_map: dict[str, DataSource],
    source_id: str,
    rule_id: str,
) -> DataSource:
    source = source_map.get(source_id)
    if source is None:
        raise ValueError(f"飞书解析失败：规则 '{rule_id}' 引用了不存在的飞书数据源 '{source_id}'。")
    if source.type != "feishu":
        raise ValueError(f"飞书解析失败：规则 '{rule_id}' 的规划表数据源必须是飞书数据源。")
    return source


def _ensure_package_field_mapping(
    rule_id: str,
    field_mapping: Any,
) -> None:
    if hasattr(field_mapping, "model_dump"):
        field_mapping = field_mapping.model_dump()
    missing_fields = [
        field_name
        for field_name in ("package_id", "item_id", "count")
        if not isinstance(field_mapping.get(field_name), str)
        or not field_mapping[field_name].strip()
    ]
    if missing_fields:
        missing_text = "、".join(missing_fields)
        raise ValueError(f"字段映射失败：规则 '{rule_id}' 缺少 {missing_text} 字段映射。")


def _build_package_items_frame(detail_rows: list[Any]) -> pd.DataFrame:
    rows = [
        {
            "__key__": f"{detail_row.package_id}_{index}",
            RUNTIME_PACKAGE_FIELD: detail_row.package_id,
            RUNTIME_ITEM_FIELD: detail_row.item_id,
            RUNTIME_COUNT_FIELD: detail_row.count,
            "_row_index": detail_row.row_index,
        }
        for index, detail_row in enumerate(detail_rows)
    ]
    return pd.DataFrame(
        rows,
        columns=["__key__", *RUNTIME_COLUMNS, "_row_index"],
        dtype=object,
    )


def _build_runtime_rule(
    rule: FixedRuleDefinition,
    temp_tag: str,
) -> FixedRuleDefinition:
    return rule.model_copy(
        update={
            "target_variable_tag": temp_tag,
            "left_package_field": RUNTIME_PACKAGE_FIELD,
            "left_item_field": RUNTIME_ITEM_FIELD,
            "left_count_field": RUNTIME_COUNT_FIELD,
            "display_field": rule.display_field or RUNTIME_PACKAGE_FIELD,
            "package_parse_config": None,
        }
    )
