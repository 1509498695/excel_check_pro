"""进程内执行任务服务。"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas import TaskTree
from backend.app.database import async_session_factory
from backend.app.execution_summary import (
    build_fixed_rules_execution_summary,
    build_workbench_execution_summary,
)
from backend.app.result_store import (
    complete_execution_run,
    create_execution_run_task,
    fail_execution_run,
    mark_execution_run_started,
)


async def create_execute_run(
    db: AsyncSession,
    *,
    scope_type: str,
    project_id: int,
    user_id: int,
) -> dict[str, Any]:
    """创建执行任务并返回状态 payload。"""
    run = await create_execution_run_task(
        db,
        scope_type=scope_type,  # type: ignore[arg-type]
        project_id=project_id,
        user_id=user_id,
    )
    return {
        "run_id": run.id,
        "scope_type": run.scope_type,
        "status": run.status,
        "created_at": run.created_at,
    }


async def run_execute_run_task(
    *,
    run_id: int,
    scope_type: str,
    project_id: int,
    user_id: int,
    username: str,
    task_tree: TaskTree | None = None,
    selected_rule_ids: list[str] | None = None,
) -> None:
    """后台执行任务，并把状态和结果写回 execution_runs。"""
    start = time.perf_counter()
    async with async_session_factory() as db:
        await mark_execution_run_started(db, run_id)
        try:
            if scope_type == "workbench":
                if task_tree is None:
                    raise ValueError("个人校验任务缺少 task_tree")
                summary = await build_workbench_execution_summary(
                    task_tree,
                    db=db,
                    project_id=project_id,
                    user_id=user_id,
                )
            elif scope_type == "fixed_rules":
                summary = await build_fixed_rules_execution_summary(
                    db=db,
                    project_id=project_id,
                    user_scope=username,
                    selected_rule_ids=selected_rule_ids,
                )
            else:
                raise ValueError(f"Unsupported execute run scope_type: {scope_type}")

            await complete_execution_run(
                db,
                run_id=run_id,
                abnormal_results=summary["abnormal_results"],
                execution_time_ms=summary["execution_time_ms"],
                total_rows_scanned=summary["total_rows_scanned"],
                failed_sources=summary["failed_sources"],
            )
        except Exception as exc:
            await db.rollback()
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            await fail_execution_run(
                db,
                run_id=run_id,
                error_message=str(exc) or exc.__class__.__name__,
                execution_time_ms=elapsed_ms,
            )
