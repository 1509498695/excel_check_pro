"""Workbench context loading for AI rule drafting."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.schemas import RuleIntent
from backend.app.ai.workflow_hints import AiRuleWorkflowHints
from backend.app.api.fixed_rules_schemas import FixedRuleDefinition, FixedRuleGroup
from backend.app.api.schemas import DataSource, VariableTag
from backend.app.loaders.local_reader import read_source_metadata
from backend.app.models import WorkbenchConfigRecord


DEFAULT_GROUP_ID = "ungrouped"
DEFAULT_GROUP_NAME = "未分组"


async def load_workbench_context(
    db: AsyncSession,
    project_id: int,
    user_id: int,
    *,
    metadata_reader: Callable[[DataSource], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Load the current user's personal workbench config as AI context."""
    result = await db.execute(
        select(WorkbenchConfigRecord).where(
            WorkbenchConfigRecord.project_id == project_id,
            WorkbenchConfigRecord.user_id == user_id,
        )
    )
    record = result.scalar_one_or_none()
    raw_config: dict[str, Any] = {}
    if record is not None:
        try:
            parsed = json.loads(record.config_json)
            raw_config = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            raw_config = {}

    sources = _validate_list(raw_config.get("sources"), DataSource)
    variables = _validate_list(raw_config.get("variables"), VariableTag)
    groups = _validate_list(raw_config.get("ruleGroups"), FixedRuleGroup)
    rules = _validate_list(raw_config.get("orchestrationRules"), FixedRuleDefinition)
    source_metadata = read_safe_source_metadata(
        sources,
        metadata_reader=metadata_reader or read_source_metadata,
    )

    prompt_context = {
        "sources": [
            {
                "id": source.id,
                "type": source.type,
                "locator": source.pathOrUrl or source.path or source.url or "",
                "sheets": source_metadata.get(source.id, {}).get("sheets", []),
            }
            for source in sources
        ],
        "variables": [
            {
                "tag": variable.tag,
                "source_id": variable.source_id,
                "sheet": variable.sheet,
                "variable_kind": variable.variable_kind,
                "column": variable.column,
                "columns": variable.columns,
                "key_column": variable.key_column,
                "expected_type": variable.expected_type,
            }
            for variable in variables
        ],
        "rules": [
            {
                "rule_id": rule.rule_id,
                "rule_name": rule.rule_name,
                "rule_type": rule.rule_type,
                "target_variable_tag": rule.target_variable_tag,
            }
            for rule in rules
        ],
    }
    return {
        "sources": sources,
        "variables": variables,
        "groups": groups or [FixedRuleGroup(group_id=DEFAULT_GROUP_ID, group_name=DEFAULT_GROUP_NAME, builtin=True)],
        "rules": rules,
        "source_metadata": source_metadata,
        "prompt_context": prompt_context,
    }


def read_safe_source_metadata(
    sources: list[DataSource],
    *,
    metadata_reader: Callable[[DataSource], dict[str, Any]] = read_source_metadata,
) -> dict[str, Any]:
    """Read source metadata for prompt context without blocking the page."""
    metadata: dict[str, Any] = {}
    for source in sources:
        if source.type not in {"local_excel", "svn"}:
            metadata[source.id] = {"sheets": [], "error": "当前数据源类型暂不支持元数据读取。"}
            continue
        try:
            metadata[source.id] = metadata_reader(source)
        except Exception as exc:  # noqa: BLE001 - only used as degraded AI context.
            metadata[source.id] = {"sheets": [], "error": str(exc)}
    return metadata


def context_with_temporary_hint_metadata(
    context: dict[str, Any],
    *,
    workflow_hints: AiRuleWorkflowHints,
    intent: RuleIntent,
    sanitize_hints: Callable[[AiRuleWorkflowHints], AiRuleWorkflowHints],
    first_text: Callable[..., str | None],
    derive_source_id: Callable[[str | None], str | None],
    guess_source_type: Callable[[str | None], str],
) -> dict[str, Any]:
    """Read unsaved source metadata for the current draft compile only."""
    workflow_hints = sanitize_hints(workflow_hints)
    source_url = first_text(
        workflow_hints.source_url,
        intent.target.path_or_url if intent.target else None,
    )
    if not source_url:
        return context

    source_id = first_text(
        workflow_hints.source_id,
        intent.target.source_id if intent.target else None,
        derive_source_id(source_url),
    )
    if not source_id:
        return context

    source_metadata = context.get("source_metadata", {})
    if isinstance(source_metadata, dict):
        current_metadata = source_metadata.get(source_id)
        current_sheets = current_metadata.get("sheets") if isinstance(current_metadata, dict) else None
        if isinstance(current_sheets, list) and current_sheets:
            return context
    else:
        source_metadata = {}

    source_type = first_text(
        workflow_hints.source_type,
        intent.target.source_type if intent.target else None,
        guess_source_type(source_url),
    )
    if source_type not in {"local_excel", "svn"}:
        return context

    source = DataSource(
        id=source_id,
        type=source_type,  # type: ignore[arg-type]
        pathOrUrl=source_url,
    )
    next_metadata = dict(source_metadata)
    try:
        next_metadata[source_id] = read_source_metadata(source)
    except Exception as exc:  # noqa: BLE001 - draft completion only degrades to missing input.
        next_metadata[source_id] = {"sheets": [], "error": str(exc)}
    return {**context, "source_metadata": next_metadata}


def _validate_list(raw_items: Any, model_type: type) -> list[Any]:
    if not isinstance(raw_items, list):
        return []
    validated: list[Any] = []
    for item in raw_items:
        try:
            validated.append(model_type.model_validate(item))
        except ValidationError:
            continue
    return validated
