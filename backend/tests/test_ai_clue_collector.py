"""AI clue collector 单元测试。"""

from __future__ import annotations

from backend.app.ai.clue_collector import (
    description_mentions_unsupported_rule,
    merge_workflow_hints,
    normalize_selected_variable_tags,
)
from backend.app.ai.workflow_hints import AiRuleWorkflowHints


def test_merge_workflow_hints_prefers_explicit_values_and_keeps_extracted_fallbacks() -> None:
    explicit = AiRuleWorkflowHints(
        source_id="server_config",
        sheet="switch",
        target_field="STR_ServersParam",
        filter_field="DES",
        filter_operator="contains",
        filter_value="废弃",
    )
    extracted = AiRuleWorkflowHints(
        source_id="other",
        source_url="D:/demo.xlsx",
        target_field="ID",
        compare_fields=["A", "B"],
    )

    merged = merge_workflow_hints(explicit, extracted)

    assert merged.source_id == "server_config"
    assert merged.source_url == "D:/demo.xlsx"
    assert merged.compare_fields == ["A", "B"]
    assert merged.filter_operator == "not_contains"


def test_normalize_selected_variable_tags_deduplicates_selected_and_hint_tags() -> None:
    hints = AiRuleWorkflowHints(
        target_variable_tag="target",
        reference_variable_tag="ref",
        left_variable_tag="target",
    )

    assert normalize_selected_variable_tags(
        [" target ", "", "manual"],
        workflow_hints=hints,
    ) == ["target", "manual", "ref"]


def test_description_mentions_unsupported_rule_detects_aggregation_keywords() -> None:
    assert description_mentions_unsupported_rule("按 Key 聚合求和后比较")
    assert not description_mentions_unsupported_rule("校验字段非空")
