"""AI 规则线索收集与合并。"""

from __future__ import annotations

from backend.app.ai.rule_type_inference import infer_hint_rule_type
from backend.app.ai.schemas import RuleIntent
from backend.app.ai.workflow_hints import AiRuleWorkflowHints, sanitize_workflow_hints


def merge_workflow_hints(
    explicit_hints: AiRuleWorkflowHints | None,
    extracted_hints: AiRuleWorkflowHints,
) -> AiRuleWorkflowHints:
    """合并前端线索与后端自然语言抽取结果，显式线索优先。"""

    if explicit_hints is None:
        return sanitize_workflow_hints(extracted_hints)
    merged = AiRuleWorkflowHints(
        rule_type_hint=explicit_hints.rule_type_hint or extracted_hints.rule_type_hint,
        target_variable_tag=first_text(
            explicit_hints.target_variable_tag,
            extracted_hints.target_variable_tag,
        ),
        reference_variable_tag=first_text(
            explicit_hints.reference_variable_tag,
            extracted_hints.reference_variable_tag,
        ),
        left_variable_tag=first_text(
            explicit_hints.left_variable_tag,
            extracted_hints.left_variable_tag,
        ),
        right_variable_tag=first_text(
            explicit_hints.right_variable_tag,
            extracted_hints.right_variable_tag,
        ),
        source_id=first_text(explicit_hints.source_id, extracted_hints.source_id),
        source_type=explicit_hints.source_type or extracted_hints.source_type,
        source_url=first_text(explicit_hints.source_url, extracted_hints.source_url),
        sheet=first_text(explicit_hints.sheet, extracted_hints.sheet),
        target_field=first_text(explicit_hints.target_field, extracted_hints.target_field),
        display_field=first_text(explicit_hints.display_field, extracted_hints.display_field),
        filter_field=first_text(explicit_hints.filter_field, extracted_hints.filter_field),
        filter_operator=explicit_hints.filter_operator or extracted_hints.filter_operator,
        filter_value=first_text(explicit_hints.filter_value, extracted_hints.filter_value),
        filters=explicit_hints.filters if explicit_hints.filters else extracted_hints.filters,
        assertion_field=first_text(
            explicit_hints.assertion_field,
            extracted_hints.assertion_field,
        ),
        assertion_operator=(
            explicit_hints.assertion_operator or extracted_hints.assertion_operator
        ),
        assertion_value_source=(
            explicit_hints.assertion_value_source
            or extracted_hints.assertion_value_source
        ),
        assertion_expected_field=first_text(
            explicit_hints.assertion_expected_field,
            extracted_hints.assertion_expected_field,
        ),
        assertion_value=first_text(
            explicit_hints.assertion_value,
            extracted_hints.assertion_value,
        ),
        operator=explicit_hints.operator or extracted_hints.operator,
        expected_value=first_text(
            explicit_hints.expected_value,
            extracted_hints.expected_value,
        ),
        expected_value_mode=(
            explicit_hints.expected_value_mode or extracted_hints.expected_value_mode
        ),
        regex_pattern=first_text(
            explicit_hints.regex_pattern,
            extracted_hints.regex_pattern,
        ),
        sequence_direction=(
            explicit_hints.sequence_direction or extracted_hints.sequence_direction
        ),
        sequence_step=first_text(
            explicit_hints.sequence_step,
            extracted_hints.sequence_step,
        ),
        sequence_start_mode=(
            explicit_hints.sequence_start_mode or extracted_hints.sequence_start_mode
        ),
        sequence_start_value=first_text(
            explicit_hints.sequence_start_value,
            extracted_hints.sequence_start_value,
        ),
        key_column=first_text(explicit_hints.key_column, extracted_hints.key_column),
        composite_columns=(
            explicit_hints.composite_columns
            if explicit_hints.composite_columns
            else extracted_hints.composite_columns
        ),
        reference_source_id=first_text(
            explicit_hints.reference_source_id,
            extracted_hints.reference_source_id,
        ),
        reference_source_type=(
            explicit_hints.reference_source_type
            or extracted_hints.reference_source_type
        ),
        reference_source_url=first_text(
            explicit_hints.reference_source_url,
            extracted_hints.reference_source_url,
        ),
        reference_sheet=first_text(
            explicit_hints.reference_sheet,
            extracted_hints.reference_sheet,
        ),
        reference_field=first_text(
            explicit_hints.reference_field,
            extracted_hints.reference_field,
        ),
        reference_key_column=first_text(
            explicit_hints.reference_key_column,
            extracted_hints.reference_key_column,
        ),
        reference_composite_columns=(
            explicit_hints.reference_composite_columns
            if explicit_hints.reference_composite_columns
            else extracted_hints.reference_composite_columns
        ),
        left_filter_field=first_text(
            explicit_hints.left_filter_field,
            extracted_hints.left_filter_field,
        ),
        left_filter_operator=(
            explicit_hints.left_filter_operator
            or extracted_hints.left_filter_operator
        ),
        left_filter_value=first_text(
            explicit_hints.left_filter_value,
            extracted_hints.left_filter_value,
        ),
        right_filter_field=first_text(
            explicit_hints.right_filter_field,
            extracted_hints.right_filter_field,
        ),
        right_filter_operator=(
            explicit_hints.right_filter_operator
            or extracted_hints.right_filter_operator
        ),
        right_filter_value=first_text(
            explicit_hints.right_filter_value,
            extracted_hints.right_filter_value,
        ),
        left_key_field=first_text(
            explicit_hints.left_key_field,
            extracted_hints.left_key_field,
        ),
        right_key_field=first_text(
            explicit_hints.right_key_field,
            extracted_hints.right_key_field,
        ),
        compare_operator=(
            explicit_hints.compare_operator or extracted_hints.compare_operator
        ),
        key_check_mode=explicit_hints.key_check_mode or extracted_hints.key_check_mode,
        compare_fields=(
            explicit_hints.compare_fields
            if explicit_hints.compare_fields
            else extracted_hints.compare_fields
        ),
        pipeline_nodes=(
            explicit_hints.pipeline_nodes
            if explicit_hints.pipeline_nodes
            else extracted_hints.pipeline_nodes
        ),
        mapping_nodes=(
            explicit_hints.mapping_nodes
            if explicit_hints.mapping_nodes
            else extracted_hints.mapping_nodes
        ),
    )
    if (
        merged.source_id == "server_config"
        and merged.sheet == "switch"
        and merged.target_field == "STR_ServersParam"
        and merged.filter_field == "DES"
        and merged.filter_value == "废弃"
    ):
        merged.filter_operator = "not_contains"
    return sanitize_workflow_hints(merged)


def normalize_selected_variable_tags(
    selected_variable_tags: list[str] | None,
    *,
    workflow_hints: AiRuleWorkflowHints | None,
) -> list[str]:
    """合并用户显式选择和结构化线索中的变量 tag，去空去重保序。"""

    seen: set[str] = set()
    result: list[str] = []
    for value in [
        *(selected_variable_tags or []),
        workflow_hints.target_variable_tag if workflow_hints else None,
        workflow_hints.reference_variable_tag if workflow_hints else None,
        workflow_hints.left_variable_tag if workflow_hints else None,
        workflow_hints.right_variable_tag if workflow_hints else None,
    ]:
        tag = value.strip() if isinstance(value, str) else ""
        if tag and tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def infer_workflow_hint_rule_type(
    workflow_hints: AiRuleWorkflowHints,
    description: str,
) -> str | None:
    """按当前线索推断规则类型。"""

    return infer_hint_rule_type(
        RuleIntent(verdict="needs_input", confidence=0, reasoning_summary=""),
        workflow_hints,
        description,
    )


def description_mentions_unsupported_rule(description: str) -> bool:
    """识别当前 11 类规则无法确定表达的聚合/脚本类描述。"""

    return any(
        keyword in description
        for keyword in ("公式", "聚合", "平均", "求和", "脚本", "计算后", "跨行统计")
    )


def first_text(*values: str | None) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
