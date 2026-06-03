"""AI 规则草稿服务门面。

本模块保留历史 import 路径和测试 monkeypatch 入口；具体实现拆到
``backend.app.ai.draft_service`` 以及相邻职责模块。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.credentials import AiProviderInvalid, AiProviderNotConfigured
from backend.app.ai.draft_repository import (
    clear_drafts,
    delete_draft,
    list_rule_drafts,
    mark_draft_applied,
    persist_draft_history,
)
from backend.app.ai.draft_service import (
    dry_run_rule_prompt_optimize as _dry_run_rule_prompt_optimize,
)
from backend.app.ai.draft_service import generate_rule_draft as _generate_rule_draft
from backend.app.ai.draft_service import optimize_rule_prompt as _optimize_rule_prompt
from backend.app.ai.providers import ProviderConnectionError, call_provider_json
from backend.app.ai.schemas import RuleDraftResponse, RulePromptOptimizeResponse
from backend.app.ai.workflow_hints import AiRuleWorkflowHints
from backend.app.loaders.local_reader import read_source_metadata


__all__ = [
    "AiProviderInvalid",
    "AiProviderNotConfigured",
    "ProviderConnectionError",
    "call_provider_json",
    "read_source_metadata",
    "optimize_rule_prompt",
    "dry_run_rule_prompt_optimize",
    "generate_rule_draft",
    "list_rule_drafts",
    "mark_draft_applied",
    "delete_draft",
    "clear_drafts",
    "persist_draft_history",
]


async def optimize_rule_prompt(
    *,
    db: AsyncSession,
    project_id: int,
    user_id: int,
    raw_description: str,
    selected_variable_tags: list[str],
    allow_auto_complete: bool = False,
    context: dict[str, Any] | None = None,
) -> RulePromptOptimizeResponse:
    """优化智能规则输入文本；保留历史门面签名。"""

    return await _optimize_rule_prompt(
        db=db,
        project_id=project_id,
        user_id=user_id,
        raw_description=raw_description,
        selected_variable_tags=selected_variable_tags,
        allow_auto_complete=allow_auto_complete,
        context=context,
        provider_caller=call_provider_json,
        metadata_reader=read_source_metadata,
    )


async def dry_run_rule_prompt_optimize(
    *,
    raw_description: str,
) -> RulePromptOptimizeResponse:
    """返回本地 deterministic 线索，不加载凭据、不调用模型。"""

    return await _dry_run_rule_prompt_optimize(raw_description=raw_description)


async def generate_rule_draft(
    *,
    db: AsyncSession,
    project_id: int,
    user_id: int,
    description: str,
    extra_hints: str | None = None,
    workflow_hints: AiRuleWorkflowHints | None = None,
    input_mode: str = "free_text",
    allow_auto_complete: bool = True,
    selected_variable_tags: list[str] | None = None,
) -> RuleDraftResponse:
    """生成规则草稿，持久化历史，并返回前端可展示的结果。"""

    return await _generate_rule_draft(
        db=db,
        project_id=project_id,
        user_id=user_id,
        description=description,
        extra_hints=extra_hints,
        workflow_hints=workflow_hints,
        input_mode=input_mode,
        allow_auto_complete=allow_auto_complete,
        selected_variable_tags=selected_variable_tags,
        provider_caller=call_provider_json,
        metadata_reader=read_source_metadata,
    )
