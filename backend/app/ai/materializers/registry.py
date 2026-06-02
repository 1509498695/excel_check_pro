"""RuleIntent to FixedRuleDefinition materialization registry."""

from __future__ import annotations

from uuid import uuid4

from backend.app.ai.schemas import RuleIntent
from backend.app.ai.workflow_hints import MissingItem
from backend.app.api.fixed_rules_schemas import FixedRuleDefinition
from backend.app.api.schemas import VariableTag


DEFAULT_GROUP_ID = "ungrouped"


def materialize_rule_definition(
    intent: RuleIntent,
    *,
    target_variable: VariableTag | None,
    reference_variable: VariableTag | None,
    description: str,
) -> tuple[FixedRuleDefinition | None, list[MissingItem]]:
    """Convert a standard RuleIntent into one persisted fixed-rule definition."""
    rule_type = intent.rule_type
    if rule_type is None:
        return None, []
    target_tag = target_variable.tag if target_variable is not None else ""
    rule_name = (intent.rule_name or "").strip() or _default_rule_name(
        rule_type,
        target_variable,
        intent,
        description,
    )
    base = {
        "rule_id": f"ai-rule-{uuid4().hex[:12]}",
        "group_id": DEFAULT_GROUP_ID,
        "rule_name": rule_name,
        "target_variable_tag": target_tag,
        "display_field": (intent.display_field or "").strip() or None,
        "rule_type": rule_type,
    }

    if rule_type == "fixed_value_compare":
        if not intent.operator or not (intent.expected_value or "").strip():
            return None, [
                MissingItem(
                    kind="parameter",
                    message="固定值比较需要操作符和比较值。",
                    suggested_action="edit_description",
                )
            ]
        return FixedRuleDefinition(
            **base,
            operator=intent.operator,
            expected_value=(intent.expected_value or "").strip(),
            expected_value_mode=intent.expected_value_mode,
        ), []

    if rule_type == "regex_check":
        pattern = (intent.regex_pattern or intent.expected_value or "").strip()
        if not pattern:
            return None, [
                MissingItem(
                    kind="parameter",
                    message="正则校验需要正则表达式。",
                    suggested_action="edit_description",
                )
            ]
        return FixedRuleDefinition(**base, expected_value=pattern), []

    if rule_type == "sequence_order_check":
        return FixedRuleDefinition(
            **base,
            sequence_direction=intent.sequence_direction or "asc",
            sequence_step=(intent.sequence_step or "1").strip(),
            sequence_start_mode=intent.sequence_start_mode or "auto",
            sequence_start_value=(intent.sequence_start_value or "").strip() or None,
        ), []

    if rule_type == "cross_table_mapping":
        if reference_variable is None:
            return None, [
                MissingItem(
                    kind="variable",
                    message="包含(in) 规则需要基础字典变量。",
                    suggested_action="edit_description",
                )
            ]
        return FixedRuleDefinition(
            **base,
            reference_variable_tag=reference_variable.tag,
        ), []

    if rule_type == "composite_condition_check":
        if intent.composite_config is None:
            return None, [
                MissingItem(
                    kind="parameter",
                    message="组合分支校验需要全局筛选、分支筛选或分支断言配置。",
                    suggested_action="edit_description",
                )
            ]
        return FixedRuleDefinition(**base, composite_config=intent.composite_config), []

    if rule_type == "dual_composite_compare":
        if reference_variable is None or not intent.comparisons:
            return None, [
                MissingItem(
                    kind="parameter",
                    message="跨组变量校验需要目标变量和至少一条字段比对。",
                    suggested_action="edit_description",
                )
            ]
        return FixedRuleDefinition(
            **base,
            reference_variable_tag=reference_variable.tag,
            key_check_mode=intent.key_check_mode or "baseline_only",
            left_key_field=intent.left_key_field or "__key__",
            right_key_field=intent.right_key_field or "__key__",
            comparisons=intent.comparisons,
            left_filters=intent.left_filters,  # type: ignore[arg-type]
            right_filters=intent.right_filters,  # type: ignore[arg-type]
        ), []

    if rule_type == "multi_composite_pipeline_check":
        if intent.pipeline_config is None or not intent.pipeline_config.nodes:
            return None, [
                MissingItem(
                    kind="parameter",
                    message="多组串行校验需要至少一个节点配置。",
                    suggested_action="edit_description",
                )
            ]
        first_tag = intent.pipeline_config.nodes[0].variable_tag
        return FixedRuleDefinition(
            **{**base, "target_variable_tag": first_tag},
            pipeline_config=intent.pipeline_config,
        ), []

    if rule_type == "multi_composite_mapping_check":
        if intent.mapping_config is None or not intent.mapping_config.nodes:
            return None, [
                MissingItem(
                    kind="parameter",
                    message="多组映射校验需要至少一个节点配置。",
                    suggested_action="edit_description",
                )
            ]
        first_tag = intent.mapping_config.nodes[0].variable_tag
        return FixedRuleDefinition(
            **{**base, "target_variable_tag": first_tag},
            mapping_config=intent.mapping_config,
        ), []

    if rule_type == "package_items_compare":
        if reference_variable is None:
            return None, [
                MissingItem(
                    kind="variable",
                    message="礼包道具配置校验需要选择礼包配置组合变量。",
                    suggested_action="edit_description",
                )
            ]
        return FixedRuleDefinition(
            **base,
            reference_variable_tag=reference_variable.tag,
            left_package_field=(intent.left_package_field or "礼包id").strip(),
            right_package_field=(intent.right_package_field or "INT_PackageId").strip(),
            left_item_field=(intent.left_item_field or "道具ID").strip(),
            left_count_field=(intent.left_count_field or "个数").strip(),
            right_items_field=(intent.right_items_field or "STR_Items").strip(),
            package_id_filter=(intent.package_id_filter or "").strip() or None,
        ), []

    return FixedRuleDefinition(**base), []


def _default_rule_name(
    rule_type: str,
    variable: VariableTag | None,
    intent: RuleIntent,
    description: str,
) -> str:
    column = variable.column if variable is not None else None
    if variable is not None and (variable.variable_kind or "single") == "composite":
        column = variable.key_column
    target_text = column or variable.tag if variable is not None else description[:20]
    if rule_type == "not_null":
        return f"{target_text}-非空校验"
    if rule_type == "unique":
        return f"{target_text}-唯一校验"
    if rule_type == "regex_check":
        return f"{target_text}-正则校验"
    if rule_type == "fixed_value_compare":
        return f"{target_text}-{intent.operator or '比较'}-{intent.expected_value or ''}".strip("-")
    return f"{target_text}-{rule_type}"
