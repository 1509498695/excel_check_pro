"""Rule type inference for AI workflow hints."""

from __future__ import annotations

from backend.app.ai.schemas import RuleIntent
from backend.app.ai.workflow_hints import AiRuleWorkflowHints


def infer_hint_rule_type(
    intent: RuleIntent,
    workflow_hints: AiRuleWorkflowHints,
    description: str,
) -> str | None:
    """Infer the most specific fixed-rule type from normalized workflow hints."""
    has_filter_assertion_pair = bool(
        (
            workflow_hints.filters
            or (
                workflow_hints.filter_field
                and (workflow_hints.filter_value or workflow_hints.filter_operator == "not_null")
            )
        )
        and workflow_hints.assertion_field
        and (
            workflow_hints.assertion_value
            or workflow_hints.assertion_expected_field
            or workflow_hints.assertion_operator
        )
    )
    has_composite_signals = bool(
        workflow_hints.filters
        or workflow_hints.filter_field
        or workflow_hints.display_field
        or workflow_hints.key_column
        or workflow_hints.composite_columns
    )
    if has_filter_assertion_pair and workflow_hints.rule_type_hint not in {
        "dual_composite_compare",
        "multi_composite_pipeline_check",
        "multi_composite_mapping_check",
        "cross_table_mapping",
    }:
        return "composite_condition_check"
    if workflow_hints.rule_type_hint == "regex_check" and has_composite_signals:
        return "composite_condition_check"
    if workflow_hints.rule_type_hint:
        return workflow_hints.rule_type_hint
    if (
        workflow_hints.left_filter_field
        and workflow_hints.left_filter_value
        and workflow_hints.right_filter_field
        and workflow_hints.right_filter_value
        and workflow_hints.compare_fields
    ):
        return "dual_composite_compare"
    if workflow_hints.pipeline_nodes:
        return "multi_composite_pipeline_check"
    if workflow_hints.mapping_nodes:
        return "multi_composite_mapping_check"
    if workflow_hints.regex_pattern:
        return (
            "composite_condition_check"
            if workflow_hints.filters
            or workflow_hints.filter_field
            or workflow_hints.display_field
            or workflow_hints.key_column
            or workflow_hints.composite_columns
            else "regex_check"
        )
    if intent.rule_type:
        return intent.rule_type
    text = description.lower()
    if "str_items" in text and any(keyword in description for keyword in ("礼包", "道具")):
        return "package_items_compare"
    if any(keyword in description for keyword in ("两组", "两个配置", "两份配置", "是不是相等", "是否相等")):
        return "dual_composite_compare"
    if any(keyword in description for keyword in ("多组串行", "多节点串行", "多级链路", "链路")):
        return "multi_composite_pipeline_check"
    if any(keyword in description for keyword in ("多组映射", "多节点映射", "映射校验")):
        return "multi_composite_mapping_check"
    if any(keyword in description for keyword in ("存在于", "字典表", "字典变量", "包含(in)")):
        return "cross_table_mapping"
    if any(keyword in text for keyword in ("不能为空", "非空", "not null", "not_null")):
        return "not_null"
    if any(keyword in text for keyword in ("唯一", "unique")):
        return "unique"
    if any(keyword in description for keyword in ("升序", "降序", "递增", "递减", "连续", "步长", "顺序")):
        return "sequence_order_check"
    if any(keyword in text for keyword in ("格式", "正则", "regex")):
        return "composite_condition_check" if workflow_hints.filter_field else "regex_check"
    if any(keyword in description for keyword in ("等于", "不等于", "大于", "小于", "只能是", "必须是")):
        return "fixed_value_compare"
    return None
