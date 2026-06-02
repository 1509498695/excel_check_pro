"""固定规则配置到 TaskTree 的转换。"""

from __future__ import annotations

from backend.app.api.fixed_rules_schemas import FixedRuleDefinition, FixedRulesConfig
from backend.app.api.schemas import TaskTree, ValidationRule, VariableTag
from backend.app.fixed_rules.config_common import COMPOSITE_KEY_FIELD


def build_fixed_rules_task_tree(
    config: FixedRulesConfig,
    selected_rule_ids: list[str] | None = None,
) -> TaskTree:
    """????????????????????? TaskTree?"""
    ordered_rules = _get_ordered_rules(config, selected_rule_ids=selected_rule_ids)
    variable_map = {variable.tag: variable for variable in config.variables}
    needed_tags = {
        tag
        for rule in ordered_rules
        for tag in [
            rule.target_variable_tag,
            rule.reference_variable_tag,
            *[
                node.variable_tag
                for node in (rule.pipeline_config.nodes if rule.pipeline_config else [])
            ],
            *[
                node.variable_tag
                for node in (rule.mapping_config.nodes if rule.mapping_config else [])
            ],
        ]
        if tag
    }

    variables = [variable for variable in config.variables if variable.tag in needed_tags]
    source_ids = {variable.source_id for variable in variables}
    sources = [source for source in config.sources if source.id in source_ids]

    task_rules = [
        ValidationRule(
            rule_id=rule.rule_id,
            rule_type=rule.rule_type,
            params=_build_fixed_rule_params(
                rule,
                variable_map[_get_primary_rule_target_tag(rule)],
            ),
        )
        for rule in ordered_rules
    ]

    return TaskTree(
        sources=sources,
        variables=variables,
        rules=task_rules,
        selected_rule_ids=selected_rule_ids,
    )


def _get_primary_rule_target_tag(rule: FixedRuleDefinition) -> str:
    """返回规则参数里用于兼容 target_tag 的主变量。"""
    if rule.rule_type == "multi_composite_pipeline_check" and rule.pipeline_config:
        return rule.pipeline_config.nodes[0].variable_tag
    if rule.rule_type == "multi_composite_mapping_check" and rule.mapping_config:
        return rule.mapping_config.nodes[0].variable_tag
    return rule.target_variable_tag


def _get_ordered_rules(
    config: FixedRulesConfig,
    *,
    selected_rule_ids: list[str] | None = None,
) -> list[FixedRuleDefinition]:
    """?????????????????????"""
    group_order = {group.group_id: index for index, group in enumerate(config.groups)}
    rule_order = {rule.rule_id: index for index, rule in enumerate(config.rules)}
    ordered_rules = sorted(
        config.rules,
        key=lambda rule: (
            group_order.get(rule.group_id, len(group_order)),
            rule_order[rule.rule_id],
        ),
    )
    if selected_rule_ids is None:
        return ordered_rules

    selected_rule_id_set = {
        rule_id.strip()
        for rule_id in selected_rule_ids
        if isinstance(rule_id, str) and rule_id.strip()
    }
    if not selected_rule_id_set:
        return []

    return [
        rule for rule in ordered_rules if rule.rule_id.strip() in selected_rule_id_set
    ]


def _build_fixed_rule_params(
    rule: FixedRuleDefinition,
    target_variable: VariableTag,
) -> dict[str, object]:
    """???????????????? params?"""
    if rule.rule_type == "composite_condition_check":
        return {
            "target_tag": target_variable.tag,
            "rule_name": rule.rule_name,
            "display_field": rule.display_field,
            "composite_config": rule.composite_config.model_dump(mode="json", exclude_none=True)
            if rule.composite_config
            else None,
        }

    if rule.rule_type == "dual_composite_compare":
        return {
            "target_tag": target_variable.tag,
            "reference_tag": rule.reference_variable_tag,
            "key_check_mode": rule.key_check_mode,
            "left_key_field": rule.left_key_field or COMPOSITE_KEY_FIELD,
            "right_key_field": rule.right_key_field or COMPOSITE_KEY_FIELD,
            "display_field": rule.display_field,
            "comparisons": [
                comparison.model_dump(mode="json", exclude_none=True)
                for comparison in rule.comparisons
            ],
            "left_filters": [
                condition.model_dump(mode="json", exclude_none=True)
                for condition in rule.left_filters
            ],
            "right_filters": [
                condition.model_dump(mode="json", exclude_none=True)
                for condition in rule.right_filters
            ],
            "rule_name": rule.rule_name,
        }

    if rule.rule_type == "multi_composite_pipeline_check":
        return {
            "target_tag": target_variable.tag,
            "rule_name": rule.rule_name,
            "display_field": rule.display_field,
            "pipeline_config": rule.pipeline_config.model_dump(mode="json", exclude_none=True)
            if rule.pipeline_config
            else None,
        }

    if rule.rule_type == "multi_composite_mapping_check":
        return {
            "target_tag": target_variable.tag,
            "rule_name": rule.rule_name,
            "display_field": rule.display_field,
            "mapping_config": rule.mapping_config.model_dump(mode="json", exclude_none=True)
            if rule.mapping_config
            else None,
        }

    if rule.rule_type == "package_items_compare":
        return {
            "left_tag": target_variable.tag,
            "right_tag": rule.reference_variable_tag,
            "rule_name": rule.rule_name,
            "left_package_field": rule.left_package_field,
            "right_package_field": rule.right_package_field,
            "left_item_field": rule.left_item_field,
            "left_count_field": rule.left_count_field,
            "right_items_field": rule.right_items_field,
            "package_id_filter": rule.package_id_filter,
            "display_field": rule.display_field,
        }

    location = f"{target_variable.sheet} -> {target_variable.column}"

    if rule.rule_type == "fixed_value_compare":
        return {
            "target_tag": target_variable.tag,
            "operator": rule.operator,
            "expected_value": rule.expected_value,
            "expected_value_mode": rule.expected_value_mode,
            "rule_name": rule.rule_name,
            "location": location,
            "display_field": rule.display_field,
        }

    if rule.rule_type == "regex_check":
        return {
            "target_tag": target_variable.tag,
            "pattern": rule.expected_value,
            "rule_name": rule.rule_name,
            "location": location,
            "display_field": rule.display_field,
        }

    if rule.rule_type == "cross_table_mapping":
        return {
            "dict_tag": rule.reference_variable_tag,
            "target_tag": target_variable.tag,
            "rule_name": rule.rule_name,
            "location": location,
            "display_field": rule.display_field,
        }

    if rule.rule_type == "sequence_order_check":
        return {
            "target_tag": target_variable.tag,
            "direction": rule.sequence_direction,
            "step": rule.sequence_step,
            "start_mode": rule.sequence_start_mode,
            "start_value": rule.sequence_start_value,
            "rule_name": rule.rule_name,
            "location": location,
            "display_field": rule.display_field,
        }

    return {
        "target_tags": [target_variable.tag],
        "rule_name": rule.rule_name,
        "location": location,
        "display_field": rule.display_field,
    }
