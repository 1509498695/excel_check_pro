"""执行摘要构建：运行规则但不直接持久化结果。"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas import TaskTree
from backend.app.execution_pipeline import run_execution_pipeline
from backend.app.fixed_rules.config_loader import parse_raw_fixed_rules_config
from backend.app.fixed_rules.config_normalizer import validate_and_normalize_fixed_rules_config
from backend.app.fixed_rules.db_service import load_fixed_rules_config_from_db
from backend.app.fixed_rules.event_task_runtime import (
    prepare_event_task_runtime_config,
    prepare_event_task_runtime_task_tree,
)
from backend.app.fixed_rules.package_items_runtime import (
    prepare_package_items_runtime_config,
    prepare_package_items_runtime_task_tree,
)
from backend.app.fixed_rules.task_tree_builder import build_fixed_rules_task_tree
from backend.app.models import Project


async def build_workbench_execution_summary(
    task_tree: TaskTree,
    *,
    db: AsyncSession,
    project_id: int | None,
    user_id: int | None,
) -> dict[str, Any]:
    """执行个人校验 TaskTree，并返回可持久化的执行摘要。"""
    start = time.perf_counter()
    runtime_preparation = await prepare_package_items_runtime_task_tree(
        task_tree,
        db=db,
        project_id=project_id,
        user_id=user_id,
    )
    event_task_preparation = await prepare_event_task_runtime_task_tree(
        runtime_preparation.task_tree,
        db=db,
        project_id=project_id,
        user_id=user_id,
    )
    preloaded_variable_frames = {
        **runtime_preparation.preloaded_variable_frames,
        **event_task_preparation.preloaded_variable_frames,
    }

    execution_artifacts = await asyncio.to_thread(
        run_execution_pipeline,
        event_task_preparation.task_tree,
        project_id=project_id,
        preloaded_variable_frames=preloaded_variable_frames,
    )
    abnormal_results = [
        *runtime_preparation.abnormal_results,
        *event_task_preparation.abnormal_results,
        *execution_artifacts["abnormal_results"],
    ]
    summary = _build_execution_summary_payload(start, abnormal_results, execution_artifacts)
    if runtime_preparation.parse_metadata:
        summary["package_items_parse"] = runtime_preparation.parse_metadata
    if event_task_preparation.parse_metadata:
        summary["event_task_parse"] = event_task_preparation.parse_metadata
    return summary


async def build_fixed_rules_execution_summary(
    db: AsyncSession,
    project_id: int,
    *,
    user_scope: str | None = None,
    selected_rule_ids: list[str] | None = None,
) -> dict[str, Any]:
    """执行当前项目固定规则配置，并返回可持久化的执行摘要。"""
    raw = await load_fixed_rules_config_from_db(db, project_id)
    if raw is None:
        raise ValueError("当前项目尚未配置固定规则")

    parsed = parse_raw_fixed_rules_config(raw)
    config = validate_and_normalize_fixed_rules_config(parsed)
    runtime_preparation = await prepare_package_items_runtime_config(
        config,
        db=db,
        project_id=project_id,
        selected_rule_ids=selected_rule_ids,
    )
    event_task_preparation = await prepare_event_task_runtime_config(
        runtime_preparation.config,
        db=db,
        project_id=project_id,
        selected_rule_ids=selected_rule_ids,
    )
    task_tree = build_fixed_rules_task_tree(
        event_task_preparation.config,
        selected_rule_ids=selected_rule_ids,
    )
    preloaded_variable_frames = {
        **runtime_preparation.preloaded_variable_frames,
        **event_task_preparation.preloaded_variable_frames,
    }

    start = time.perf_counter()
    execution_artifacts = await asyncio.to_thread(
        run_execution_pipeline,
        task_tree,
        project_id=project_id,
        preloaded_variable_frames=preloaded_variable_frames,
    )
    summary = _build_execution_summary_payload(
        start,
        execution_artifacts["abnormal_results"],
        execution_artifacts,
    )

    project = await db.get(Project, project_id)
    summary["project_name"] = project.name if project is not None else f"项目 {project_id}"
    summary["package_items_parse"] = runtime_preparation.parse_metadata
    summary["event_task_parse"] = event_task_preparation.parse_metadata
    summary["user_scope"] = user_scope
    return summary


def _build_execution_summary_payload(
    start: float,
    abnormal_results: list[dict[str, Any]],
    execution_artifacts: dict[str, Any],
) -> dict[str, Any]:
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    total_rows_scanned = sum(
        len(frame) for frame in execution_artifacts["loaded_variables"].values()
    )
    return {
        "total_rows_scanned": total_rows_scanned,
        "failed_sources": execution_artifacts["failed_sources"],
        "abnormal_results": abnormal_results,
        "execution_time_ms": elapsed_ms,
    }
