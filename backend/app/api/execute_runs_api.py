"""异步执行任务接口。"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas import TaskTree
from backend.app.auth.dependencies import CurrentUserContext, get_current_user
from backend.app.database import get_db
from backend.app.execute_runs_service import create_execute_run, run_execute_run_task
from backend.app.result_store import (
    fetch_execution_run_items,
    fetch_execution_run_status,
    normalize_result_page,
)


router = APIRouter(prefix="/execute-runs", tags=["execute-runs"])


class ExecuteRunCreateRequest(BaseModel):
    """创建执行任务请求。"""

    model_config = ConfigDict(extra="forbid")

    scope_type: Literal["workbench", "fixed_rules"]
    task_tree: TaskTree | None = None
    selected_rule_ids: list[str] | None = None


@router.post("")
async def create_execute_run_endpoint(
    payload: ExecuteRunCreateRequest,
    background_tasks: BackgroundTasks,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """创建异步执行任务，并交给进程内 BackgroundTasks 执行。"""
    project_id = ctx.require_project_member()
    if payload.scope_type == "workbench" and payload.task_tree is None:
        raise HTTPException(status_code=400, detail="个人校验任务必须提供 task_tree")
    if payload.scope_type == "fixed_rules" and payload.task_tree is not None:
        raise HTTPException(status_code=400, detail="项目校验任务不需要 task_tree")

    run_payload = await create_execute_run(
        db,
        scope_type=payload.scope_type,
        project_id=project_id,
        user_id=ctx.user_id,
    )
    background_tasks.add_task(
        run_execute_run_task,
        run_id=run_payload["run_id"],
        scope_type=payload.scope_type,
        project_id=project_id,
        user_id=ctx.user_id,
        username=ctx.user.username,
        task_tree=payload.task_tree,
        selected_rule_ids=payload.selected_rule_ids,
    )
    return {"code": 200, "msg": "ok", "data": run_payload}


@router.get("/{run_id}")
async def get_execute_run_status_endpoint(
    run_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """查询执行任务状态。"""
    project_id = ctx.require_project_member()
    payload = await fetch_execution_run_status(
        db,
        run_id=run_id,
        project_id=project_id,
        user_id=ctx.user_id,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="未找到对应的执行任务")
    return {"code": 200, "msg": "ok", "data": payload}


@router.get("/{run_id}/items")
async def get_execute_run_items_endpoint(
    run_id: int,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """分页读取执行任务异常明细。"""
    project_id = ctx.require_project_member()
    normalized_page, normalized_size = normalize_result_page(page, size)
    payload = await fetch_execution_run_items(
        db,
        run_id=run_id,
        project_id=project_id,
        user_id=ctx.user_id,
        page=normalized_page,
        size=normalized_size,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="未找到对应的执行任务")

    return {
        "code": 200,
        "msg": "ok",
        "meta": {
            "run_id": payload["run_id"],
            "scope_type": payload["scope_type"],
            "status": payload["status"],
            "error_message": payload["error_message"],
            "execution_time_ms": payload["execution_time_ms"],
            "total_rows_scanned": payload["total_rows_scanned"],
            "failed_sources": payload["failed_sources"],
        },
        "data": {
            "list": payload["list"],
            "abnormal_results": payload["list"],
            "total": payload["total"],
            "page": payload["page"],
            "size": payload["size"],
        },
    }
