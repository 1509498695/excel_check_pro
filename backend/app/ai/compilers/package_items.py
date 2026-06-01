"""Compiler for package detail vs STR_Items compare hints."""

from __future__ import annotations

import re

from backend.app.ai.compilers.base import WorkflowCompileState, WorkflowCompilerHelpers
from backend.app.ai.schemas import RuleIntent, VariableIntent
from backend.app.ai.workflow_hints import MissingItem
from backend.app.api.schemas import VariableTag


class PackageItemsCompiler:
    rule_types = {"package_items_compare"}

    def compile(
        self,
        state: WorkflowCompileState,
        helpers: WorkflowCompilerHelpers,
    ) -> tuple[RuleIntent | None, list[MissingItem]]:
        target_variable = state.target_variable
        reference_variable = state.reference_variable
        if target_variable is not None and (target_variable.variable_kind or "single") != "composite":
            return None, [
                MissingItem(
                    kind="variable",
                    message="礼包明细变量必须是组合变量。",
                    suggested_action="none",
                )
            ]
        if reference_variable is not None and (reference_variable.variable_kind or "single") != "composite":
            return None, [
                MissingItem(
                    kind="variable",
                    message="礼包配置变量必须是组合变量。",
                    suggested_action="none",
                )
            ]
        if reference_variable is None:
            return None, [
                MissingItem(
                    kind="variable",
                    message="礼包道具配置校验需要选择包含 INT_PackageId 和 STR_Items 的配置组合变量。",
                    suggested_action="none",
                )
            ]

        left_package_field = _pick_field(target_variable, ("礼包id", "礼包ID", "礼包 id"), "礼包id")
        left_item_field = _pick_field(target_variable, ("道具ID", "道具id", "道具 id", "item_id"), "道具ID")
        left_count_field = _pick_field(target_variable, ("个数", "数量", "count"), "个数")
        right_package_field = _pick_field(reference_variable, ("INT_PackageId", "PackageId", "礼包id"), "INT_PackageId")
        right_items_field = _pick_field(reference_variable, ("STR_Items", "Items"), "STR_Items")

        target = helpers.variable_intent_from_existing(target_variable) or VariableIntent(
            **state.common_variable_kwargs,
            variable_kind="composite",
            columns=[left_package_field, left_item_field, left_count_field],
            key_column=left_package_field,
            append_index_to_key=True,
            expected_type="json",
        )
        reference = helpers.variable_intent_from_existing(reference_variable)
        package_id_filter = state.intent.package_id_filter or _extract_package_id_filter(state.description)

        return RuleIntent(
            verdict="ready",
            rule_type=state.rule_type,
            confidence=max(state.intent.confidence, 0.78),
            reasoning_summary=helpers.append_field_correction_summary(
                state.intent.reasoning_summary or "已生成礼包明细与 STR_Items 的确定性比对规则。",
                state.field_correction_warnings,
            ),
            rule_name=state.intent.rule_name or "礼包明细对比STR_Items",
            display_field=state.display_field,
            target=target,
            reference=reference,
            left_package_field=left_package_field,
            right_package_field=right_package_field,
            left_item_field=left_item_field,
            left_count_field=left_count_field,
            right_items_field=right_items_field,
            package_id_filter=package_id_filter,
        ), []


def _pick_field(variable: VariableTag | None, candidates: tuple[str, ...], fallback: str) -> str:
    if variable is None:
        return fallback
    fields = list(variable.columns or [])
    if variable.key_column:
        fields.insert(0, variable.key_column)
    for candidate in candidates:
        for field in fields:
            if field == candidate:
                return field
    normalized_candidates = {candidate.lower().replace(" ", "") for candidate in candidates}
    for field in fields:
        normalized_field = field.lower().replace(" ", "")
        if normalized_field in normalized_candidates:
            return field
    return fallback


def _extract_package_id_filter(description: str) -> str | None:
    match = re.search(r"(?:礼包\s*id|礼包id|INT_PackageId)\s*[=＝:：]\s*([0-9]+)", description, re.IGNORECASE)
    return match.group(1) if match else None
