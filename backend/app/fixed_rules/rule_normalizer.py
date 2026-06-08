"""固定规则定义归一化。"""

from __future__ import annotations

import re

from backend.app.api.fixed_rules_schemas import (
    CompositeCondition,
    CompositeRuleConfig,
    DualCompositeComparison,
    DualCompositeKeyCheckMode,
    FixedRuleDefinition,
    FixedRulesConfigIssue,
    MultiCompositeMappingConfig,
    MultiCompositePipelineConfig,
    UNGROUPED_GROUP_ID,
)
from backend.app.api.schemas import VariableTag
from backend.app.fixed_rules.composite_rule_normalizer import _normalize_composite_rule_config
from backend.app.fixed_rules.config_common import (
    SUPPORTED_FIXED_RULE_OPERATORS,
    SUPPORTED_FIXED_RULE_TYPES,
    _normalize_display_field,
    _normalize_expected_value_mode_for_operator,
    _normalize_sequence_numeric,
)
from backend.app.fixed_rules.dual_composite_normalizer import _normalize_dual_composite_rule
from backend.app.fixed_rules.event_task_normalizer import (
    SUPPORTED_EVENT_TASK_RULE_TYPES,
    _normalize_event_task_reward_rule,
)
from backend.app.fixed_rules.mapping_rule_normalizer import _normalize_multi_composite_mapping_config
from backend.app.fixed_rules.package_items_normalizer import _normalize_package_items_compare_rule
from backend.app.fixed_rules.pipeline_rule_normalizer import _normalize_multi_composite_pipeline_config


def _normalize_rules(
    rules: list[FixedRuleDefinition],
    *,
    group_ids: set[str],
    variable_map: dict[str, VariableTag],
    allow_legacy_mapping_config: bool = False,
    config_issues: list[FixedRulesConfigIssue] | None = None,
    issue_keys: set[tuple[str, str | None, str | None, str | None, str]] | None = None,
) -> list[FixedRuleDefinition]:
    """???????????????????????"""
    normalized_rules: list[FixedRuleDefinition] = []
    seen_rule_ids: set[str] = set()

    for rule in rules:
        rule_id = rule.rule_id.strip()
        group_id = rule.group_id.strip() or UNGROUPED_GROUP_ID
        rule_name = rule.rule_name.strip()
        target_variable_tag = (rule.target_variable_tag or "").strip()
        rule_type = str(rule.rule_type).strip()
        operator = rule.operator.strip() if rule.operator else ""
        expected_value = rule.expected_value.strip() if rule.expected_value else ""
        expected_value_mode = rule.expected_value_mode
        reference_variable_tag = (rule.reference_variable_tag or "").strip()
        sequence_direction = (rule.sequence_direction or "").strip()
        sequence_step = (rule.sequence_step or "").strip()
        sequence_start_mode = (rule.sequence_start_mode or "").strip()
        sequence_start_value = (rule.sequence_start_value or "").strip()

        if not rule_id:
            raise ValueError("?????? rule_id?")
        if rule_id in seen_rule_ids:
            raise ValueError(f"???? ID ???'{rule_id}'?")
        if group_id not in group_ids:
            raise ValueError(f"???? '{rule_id}' ?????????? '{group_id}'?")
        if rule_type not in SUPPORTED_FIXED_RULE_TYPES:
            raise ValueError(f"???? '{rule_id}' ??????? rule_type '{rule_type}'?")

        if not rule_name:
            raise ValueError(f"???? '{rule_id}' ?? rule_name?")

        is_node_driven_rule = rule_type in {
            "multi_composite_pipeline_check",
            "multi_composite_mapping_check",
        }
        is_runtime_package_rule = (
            rule_type == "package_items_compare" and rule.package_parse_config is not None
        )
        is_runtime_event_task_rule = (
            rule_type in SUPPORTED_EVENT_TASK_RULE_TYPES
            and rule.event_task_parse_config is not None
        )
        target_variable = variable_map.get(target_variable_tag)
        if not is_node_driven_rule and not is_runtime_package_rule and not is_runtime_event_task_rule:
            if not target_variable_tag:
                raise ValueError(f"???? '{rule_id}' ?? target_variable_tag?")
            if target_variable is None:
                raise ValueError(
                    f"???? '{rule_id}' ????????? '{target_variable_tag}'?"
                )
        variable_kind = (target_variable.variable_kind or "single") if target_variable else ""
        normalized_operator: str | None = None
        normalized_expected_value: str | None = None
        normalized_expected_value_mode: str | None = None
        normalized_reference_variable_tag: str | None = None
        normalized_sequence_direction: str | None = None
        normalized_sequence_step: str | None = None
        normalized_sequence_start_mode: str | None = None
        normalized_sequence_start_value: str | None = None
        normalized_composite_config: CompositeRuleConfig | None = None
        normalized_key_check_mode: DualCompositeKeyCheckMode | None = None
        normalized_left_key_field: str | None = None
        normalized_right_key_field: str | None = None
        normalized_dual_comparisons: list[DualCompositeComparison] = []
        normalized_left_filters: list[CompositeCondition] = []
        normalized_right_filters: list[CompositeCondition] = []
        normalized_pipeline_config: MultiCompositePipelineConfig | None = None
        normalized_mapping_config: MultiCompositeMappingConfig | None = None
        normalized_display_field: str | None = None
        normalized_package_parse_config = rule.package_parse_config
        normalized_event_task_parse_config = rule.event_task_parse_config
        normalized_left_package_field: str | None = None
        normalized_left_item_field: str | None = None
        normalized_left_count_field: str | None = None
        normalized_right_package_field: str | None = None
        normalized_right_items_field: str | None = None
        normalized_package_id_filter: str | None = None
        normalized_left_task_group_field: str | None = None
        normalized_left_task_id_field: str | None = None
        normalized_left_task_desc_field: str | None = None
        normalized_left_task_loot_field: str | None = None
        normalized_right_task_group_field: str | None = None
        normalized_right_task_id_field: str | None = None
        normalized_right_task_desc_field: str | None = None
        normalized_right_task_loot_field: str | None = None
        normalized_task_group_id_filter: str | None = None
        normalized_event_task_match_strategy: str | None = None
        normalized_ai_assist_mode: str | None = None

        if not is_node_driven_rule and target_variable is not None:
            if variable_kind == "single" and rule_type == "composite_condition_check":
                raise ValueError(
                    f"???? '{rule_id}' ???????? '{target_variable_tag}'????????????????"
                )
            if variable_kind == "single" and rule_type in {
                "dual_composite_compare",
                "package_items_compare",
                *SUPPORTED_EVENT_TASK_RULE_TYPES,
            }:
                raise ValueError(
                    f"规则 '{rule_id}' 引用了单变量 '{target_variable_tag}'，不能保存双组合变量比对。"
                )
            if variable_kind == "composite" and rule_type not in {
                "composite_condition_check",
                "dual_composite_compare",
                "package_items_compare",
                *SUPPORTED_EVENT_TASK_RULE_TYPES,
            }:
                raise ValueError(
                    f"规则 '{rule_id}' 引用了组合变量 '{target_variable_tag}'，不能保存单变量规则。"
                )

        if rule_type == "fixed_value_compare":
            if operator not in SUPPORTED_FIXED_RULE_OPERATORS:
                raise ValueError(
                    f"???? '{rule_id}' ?????????? '{operator}'?"
                )
            if not expected_value:
                raise ValueError(f"???? '{rule_id}' ?? expected_value?")
            if operator in {"gt", "lt"}:
                try:
                    float(expected_value)
                except ValueError as exc:
                    raise ValueError(
                        f"???? '{rule_id}' ? expected_value ????????"
                    ) from exc
            normalized_expected_value_mode = _normalize_expected_value_mode_for_operator(
                operator=operator,
                expected_value=expected_value,
                expected_value_mode=expected_value_mode,
                context=f"规则 '{rule_id}'",
            )
            normalized_operator = operator
            normalized_expected_value = expected_value
        elif rule_type == "regex_check":
            if operator or reference_variable_tag or rule.composite_config is not None:
                raise ValueError(
                    f"规则 '{rule_id}' 的正则校验不应包含比较操作符、参考变量或组合配置。"
                )
            if not expected_value:
                raise ValueError(f"规则 '{rule_id}' 缺少正则表达式。")
            try:
                re.compile(expected_value)
            except re.error as exc:
                raise ValueError(
                    f"规则 '{rule_id}' 的正则表达式无效：{expected_value}"
                ) from exc
            normalized_expected_value = expected_value
        elif rule_type == "cross_table_mapping":
            if not reference_variable_tag:
                raise ValueError(
                    f"规则 '{rule_id}' 缺少 reference_variable_tag。"
                )
            if reference_variable_tag == target_variable_tag:
                raise ValueError(
                    f"规则 '{rule_id}' 的参考变量不能与目标变量相同。"
                )
            if reference_variable_tag not in variable_map:
                raise ValueError(
                    f"规则 '{rule_id}' 引用了不存在的参考变量 '{reference_variable_tag}'。"
                )
            reference_variable = variable_map[reference_variable_tag]
            if (reference_variable.variable_kind or "single") != "single":
                raise ValueError(
                    f"规则 '{rule_id}' 的参考变量 '{reference_variable_tag}' 必须是单个变量。"
                )
            normalized_reference_variable_tag = reference_variable_tag
        elif rule_type == "sequence_order_check":
            if operator or expected_value or reference_variable_tag or rule.composite_config is not None:
                raise ValueError(
                    f"规则 '{rule_id}' 的顺序校验不应包含比较值、参考变量或组合配置。"
                )
            if sequence_direction not in {"asc", "desc"}:
                raise ValueError(
                    f"规则 '{rule_id}' 的顺序方向仅支持 asc 或 desc。"
                )
            if sequence_start_mode not in {"auto", "manual"}:
                raise ValueError(
                    f"规则 '{rule_id}' 的起始值模式仅支持 auto 或 manual。"
                )
            normalized_sequence_direction = sequence_direction
            normalized_sequence_step = _normalize_sequence_numeric(
                sequence_step,
                field_name="step",
                rule_id=rule_id,
                positive_only=True,
            )
            normalized_sequence_start_mode = sequence_start_mode
            if sequence_start_mode == "manual":
                normalized_sequence_start_value = _normalize_sequence_numeric(
                    sequence_start_value,
                    field_name="start_value",
                    rule_id=rule_id,
                )
            elif sequence_start_value:
                raise ValueError(
                    f"规则 '{rule_id}' 在自动起始模式下不应填写 start_value。"
                )
        elif rule_type == "composite_condition_check":
            normalized_composite_config = _normalize_composite_rule_config(
                rule_id=rule_id,
                variable=target_variable,
                composite_config=rule.composite_config,
            )
        elif rule_type == "dual_composite_compare":
            (
                normalized_reference_variable_tag,
                normalized_key_check_mode,
                normalized_left_key_field,
                normalized_right_key_field,
                normalized_dual_comparisons,
                normalized_left_filters,
                normalized_right_filters,
            ) = _normalize_dual_composite_rule(
                rule_id=rule_id,
                target_variable=target_variable,
                target_variable_tag=target_variable_tag,
                reference_variable_tag=reference_variable_tag,
                key_check_mode=rule.key_check_mode,
                left_key_field=rule.left_key_field,
                right_key_field=rule.right_key_field,
                comparisons=rule.comparisons,
                left_filters=rule.left_filters,
                right_filters=rule.right_filters,
                variable_map=variable_map,
            )
        elif rule_type == "package_items_compare":
            (
                normalized_reference_variable_tag,
                normalized_left_package_field,
                normalized_right_package_field,
                normalized_left_item_field,
                normalized_left_count_field,
                normalized_right_items_field,
                normalized_package_id_filter,
            ) = _normalize_package_items_compare_rule(
                rule_id=rule_id,
                left_variable=target_variable,
                right_variable_tag=reference_variable_tag,
                left_package_field=rule.left_package_field,
                right_package_field=rule.right_package_field,
                left_item_field=rule.left_item_field,
                left_count_field=rule.left_count_field,
                right_items_field=rule.right_items_field,
                package_id_filter=rule.package_id_filter,
                variable_map=variable_map,
                allow_runtime_left_variable=is_runtime_package_rule,
            )
        elif rule_type in SUPPORTED_EVENT_TASK_RULE_TYPES:
            (
                normalized_reference_variable_tag,
                normalized_left_task_group_field,
                normalized_left_task_id_field,
                normalized_left_task_desc_field,
                normalized_left_task_loot_field,
                normalized_right_task_group_field,
                normalized_right_task_id_field,
                normalized_right_task_desc_field,
                normalized_right_task_loot_field,
                normalized_task_group_id_filter,
                normalized_event_task_match_strategy,
                normalized_ai_assist_mode,
            ) = _normalize_event_task_reward_rule(
                rule_id=rule_id,
                left_variable=target_variable,
                right_variable_tag=reference_variable_tag,
                left_task_group_field=rule.left_task_group_field,
                left_task_id_field=rule.left_task_id_field,
                left_task_desc_field=rule.left_task_desc_field,
                left_task_loot_field=rule.left_task_loot_field,
                right_task_group_field=rule.right_task_group_field,
                right_task_id_field=rule.right_task_id_field,
                right_task_desc_field=rule.right_task_desc_field,
                right_task_loot_field=rule.right_task_loot_field,
                task_group_id_filter=rule.task_group_id_filter,
                event_task_match_strategy=rule.event_task_match_strategy,
                ai_assist_mode=rule.ai_assist_mode,
                variable_map=variable_map,
                allow_runtime_left_variable=is_runtime_event_task_rule,
            )
        elif rule_type == "multi_composite_pipeline_check":
            normalized_pipeline_config = _normalize_multi_composite_pipeline_config(
                rule_id=rule_id,
                pipeline_config=rule.pipeline_config,
                variable_map=variable_map,
            )
            target_variable_tag = normalized_pipeline_config.nodes[0].variable_tag
        elif rule_type == "multi_composite_mapping_check":
            normalized_mapping_config = _normalize_multi_composite_mapping_config(
                rule_id=rule_id,
                mapping_config=rule.mapping_config,
                variable_map=variable_map,
                allow_legacy_mapping_config=allow_legacy_mapping_config,
                config_issues=config_issues,
                issue_keys=issue_keys,
            )
            target_variable_tag = normalized_mapping_config.nodes[0].variable_tag

        if not is_node_driven_rule and target_variable is not None:
            normalized_display_field = _normalize_display_field(
                rule_id=rule_id,
                variable=target_variable,
                display_field=rule.display_field,
            )
        elif rule.display_field:
            normalized_display_field = rule.display_field.strip() or None

        normalized_rules.append(
            FixedRuleDefinition(
                rule_id=rule_id,
                group_id=group_id,
                rule_name=rule_name,
                enabled=rule.enabled,
                description=rule.description,
                target_variable_tag=target_variable_tag,
                display_field=normalized_display_field,
                rule_type=rule_type,
                operator=normalized_operator,
                expected_value=normalized_expected_value,
                expected_value_mode=normalized_expected_value_mode,
                reference_variable_tag=normalized_reference_variable_tag,
                sequence_direction=normalized_sequence_direction,
                sequence_step=normalized_sequence_step,
                sequence_start_mode=normalized_sequence_start_mode,
                sequence_start_value=normalized_sequence_start_value,
                composite_config=normalized_composite_config,
                key_check_mode=normalized_key_check_mode,
                left_key_field=normalized_left_key_field,
                right_key_field=normalized_right_key_field,
                comparisons=normalized_dual_comparisons,
                left_filters=normalized_left_filters,
                right_filters=normalized_right_filters,
                pipeline_config=normalized_pipeline_config,
                mapping_config=normalized_mapping_config,
                package_parse_config=normalized_package_parse_config,
                event_task_parse_config=normalized_event_task_parse_config,
                left_package_field=normalized_left_package_field,
                left_item_field=normalized_left_item_field,
                left_count_field=normalized_left_count_field,
                right_package_field=normalized_right_package_field,
                right_items_field=normalized_right_items_field,
                package_id_filter=normalized_package_id_filter,
                left_task_group_field=normalized_left_task_group_field,
                left_task_id_field=normalized_left_task_id_field,
                left_task_desc_field=normalized_left_task_desc_field,
                left_task_loot_field=normalized_left_task_loot_field,
                right_task_group_field=normalized_right_task_group_field,
                right_task_id_field=normalized_right_task_id_field,
                right_task_desc_field=normalized_right_task_desc_field,
                right_task_loot_field=normalized_right_task_loot_field,
                event_task_match_strategy=normalized_event_task_match_strategy,
                ai_assist_mode=normalized_ai_assist_mode,
                task_group_id_filter=normalized_task_group_id_filter,
            )
        )
        seen_rule_ids.add(rule_id)

    return normalized_rules
