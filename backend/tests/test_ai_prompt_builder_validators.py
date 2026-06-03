"""AI prompt builder 与 validators 单元测试。"""

from __future__ import annotations

from backend.app.ai.prompt_builder import prompt_variable_metadata, rule_library_summary
from backend.app.ai.schemas import RuleDraftPayload, RuleDraftResponse
from backend.app.ai.validators import attach_extension_suggestions, enforce_variable_scope
from backend.app.api.fixed_rules_schemas import FixedRuleDefinition
from backend.app.api.schemas import VariableTag


def test_prompt_builder_exposes_package_items_rule_and_variable_metadata() -> None:
    variable = VariableTag(
        tag="[src-items-ID]",
        source_id="src",
        sheet="items",
        column="ID",
        variable_kind="single",
        expected_type="str",
    )

    assert {"rule_type": "package_items_compare", "display_name": "IAP礼包校验"} in rule_library_summary()
    assert prompt_variable_metadata([variable]) == [
        {
            "tag": "[src-items-ID]",
            "source_id": "src",
            "sheet": "items",
            "variable_kind": "single",
            "column": "ID",
            "columns": None,
            "key_column": None,
            "expected_type": "str",
        }
    ]


def test_enforce_variable_scope_rejects_unselected_dependency_when_auto_complete_disabled() -> None:
    response = RuleDraftResponse(
        verdict="ready",
        rule_type="not_null",
        draft=RuleDraftPayload(
            rules_to_add=[
                FixedRuleDefinition(
                    rule_id="r1",
                    group_id="g1",
                    rule_name="非空",
                    rule_type="not_null",
                    target_variable_tag="target",
                )
            ]
        ),
    )
    context = {
        "variables": [
            VariableTag(
                tag="target",
                source_id="src",
                sheet="items",
                column="ID",
                variable_kind="single",
            ),
            VariableTag(
                tag="other",
                source_id="src",
                sheet="items",
                column="Name",
                variable_kind="single",
            )
        ]
    }

    scoped = enforce_variable_scope(
        response,
        context=context,
        selected_variable_tags=["other"],
        allow_auto_complete=False,
    )

    assert scoped.verdict == "needs_input"
    assert "未选择但被规则引用的变量：target。" in scoped.missing[0].message


def test_attach_extension_suggestions_only_changes_rejected_response() -> None:
    response = RuleDraftResponse(
        verdict="rejected",
        reasoning_summary="无法表达",
        rejection_reason="需要聚合平均值",
    )

    updated = attach_extension_suggestions(response, description="按分组求平均")

    assert updated.extension_suggestions
    assert "公式/表达式" in updated.extension_suggestions[0] or "分组聚合" in updated.extension_suggestions[0]
