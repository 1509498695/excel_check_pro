"""Registry for deterministic workflow-hint compilers."""

from __future__ import annotations

from backend.app.ai.compilers.base import WorkflowCompileState, WorkflowCompilerHelpers, WorkflowHintCompiler
from backend.app.ai.compilers.composite_condition import CompositeConditionCompiler
from backend.app.ai.compilers.dual_composite import DualCompositeCompiler
from backend.app.ai.compilers.multi_composite import MultiCompositeCompiler
from backend.app.ai.compilers.package_items import PackageItemsCompiler
from backend.app.ai.compilers.single_target import CrossTableMappingCompiler, SingleTargetCompiler
from backend.app.ai.schemas import RuleIntent
from backend.app.ai.workflow_hints import MissingItem


_COMPILERS: tuple[WorkflowHintCompiler, ...] = (
    SingleTargetCompiler(),
    CrossTableMappingCompiler(),
    CompositeConditionCompiler(),
    DualCompositeCompiler(),
    MultiCompositeCompiler(),
    PackageItemsCompiler(),
)


def compile_workflow_hint_intent(
    state: WorkflowCompileState,
    *,
    helpers: WorkflowCompilerHelpers,
) -> tuple[RuleIntent | None, list[MissingItem]]:
    """Dispatch normalized workflow hints to the rule-type compiler."""
    for compiler in _COMPILERS:
        if state.rule_type in compiler.rule_types:
            return compiler.compile(state, helpers)
    return None, [
        MissingItem(
            kind="ability",
            message="当前自然语言线索无法稳定映射到现有规则。",
            suggested_action="none",
        )
    ]
