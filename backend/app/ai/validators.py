"""AI 规则草稿校验与建议生成。"""

from __future__ import annotations

from backend.app.ai.schemas import RuleDraftResponse
from backend.app.ai.workflow_hints import MissingItem
from backend.app.api.fixed_rules_schemas import FixedRuleDefinition
from backend.app.api.schemas import VariableTag


def enforce_variable_scope(
    response: RuleDraftResponse,
    *,
    context: dict,
    selected_variable_tags: list[str],
    allow_auto_complete: bool,
) -> RuleDraftResponse:
    """关闭自动补齐时，确保草稿只复用用户已选择变量。"""

    if allow_auto_complete:
        return response

    selected_tags = {tag.strip() for tag in selected_variable_tags if tag.strip()}
    if response.verdict != "ready":
        return response

    if not selected_tags:
        return RuleDraftResponse(
            verdict="needs_input",
            rule_type=response.rule_type,
            confidence=response.confidence,
            reasoning_summary="请先在智能规则页签选择变量池变量；当前模式不会自动新增数据源或变量。",
            missing=[
                MissingItem(
                    kind="variable",
                    message="未选择变量池变量，无法生成只复用现有变量的规则。",
                    suggested_action="none",
                )
            ],
        )

    existing_tags = {
        variable.tag
        for variable in context.get("variables", [])
        if isinstance(variable, VariableTag)
    }
    unknown_selected = sorted(tag for tag in selected_tags if tag not in existing_tags)
    if unknown_selected:
        return RuleDraftResponse(
            verdict="needs_input",
            rule_type=response.rule_type,
            confidence=response.confidence,
            reasoning_summary="已选择的变量不在当前变量池中，请重新选择变量后再校验。",
            missing=[
                MissingItem(
                    kind="variable",
                    message=f"变量池中不存在：{', '.join(unknown_selected)}。",
                    suggested_action="none",
                )
            ],
        )

    dependency_tags: set[str] = set()
    for rule in response.draft.rules_to_add:
        dependency_tags.update(collect_rule_dependency_tags(rule))
    if not dependency_tags:
        return RuleDraftResponse(
            verdict="needs_input",
            rule_type=response.rule_type,
            confidence=response.confidence,
            reasoning_summary="规则草稿没有明确引用变量，无法在只复用变量模式下添加。",
            missing=[
                MissingItem(
                    kind="variable",
                    message="请在结构化表单中选择目标变量，必要时选择引用变量或左右变量。",
                    suggested_action="none",
                )
            ],
        )

    out_of_scope = sorted(tag for tag in dependency_tags if tag not in selected_tags)
    if out_of_scope:
        return RuleDraftResponse(
            verdict="needs_input",
            rule_type=response.rule_type,
            confidence=response.confidence,
            reasoning_summary="当前草稿引用了未选择的变量；请调整变量选择后重新校验。",
            missing=[
                MissingItem(
                    kind="variable",
                    message=f"未选择但被规则引用的变量：{', '.join(out_of_scope)}。",
                    suggested_action="none",
                )
            ],
        )

    response.draft.sources_to_add = []
    response.draft.variables_to_add = []
    response.draft.reuse_variable_tags = sorted(
        set(response.draft.reuse_variable_tags).union(dependency_tags)
    )
    return response


def attach_extension_suggestions(
    response: RuleDraftResponse,
    *,
    description: str,
) -> RuleDraftResponse:
    """为 rejected 草稿补充后续能力扩展建议。"""

    if response.verdict != "rejected" or response.extension_suggestions:
        return response
    response.extension_suggestions = build_extension_suggestions(
        description,
        response.rejection_reason,
    )
    return response


def collect_rule_dependency_tags(rule: FixedRuleDefinition) -> set[str]:
    tags = {
        (rule.target_variable_tag or "").strip(),
        (rule.reference_variable_tag or "").strip(),
    }
    if rule.pipeline_config is not None:
        tags.update(node.variable_tag.strip() for node in rule.pipeline_config.nodes)
    if rule.mapping_config is not None:
        tags.update(node.variable_tag.strip() for node in rule.mapping_config.nodes)
    return {tag for tag in tags if tag}


def build_extension_suggestions(description: str, reason: str | None) -> list[str]:
    text = f"{description} {reason or ''}"
    suggestions: list[str] = []
    if any(keyword in text for keyword in ("公式", "计算后", "求和", "平均", "聚合")):
        suggestions.append("新增公式/表达式校验规则，支持对字段计算结果再做比较。")
    if any(keyword in text for keyword in ("跨行", "统计", "分组", "汇总")):
        suggestions.append("新增分组聚合或跨行统计规则，支持按 Key 汇总后校验数量、求和或唯一性。")
    if any(keyword in text for keyword in ("脚本", "自定义", "复杂逻辑")):
        suggestions.append("新增受控脚本或自定义校验插件能力，用白名单方式承载复杂业务逻辑。")
    if not suggestions:
        suggestions.append("扩展规则库时优先新增一个明确的 rule_type，并补齐前端配置表单、后端执行器和测试快照。")
    suggestions.append("如果能拆成非空、唯一、固定值、正则、组合分支或跨组变量比对，可先用现有规则临时覆盖部分场景。")
    return suggestions
