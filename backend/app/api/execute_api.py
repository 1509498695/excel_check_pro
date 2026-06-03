"""执行入口接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas import TaskTree
from backend.app.auth.dependencies import (
    CurrentUserContext,
    get_current_user,
    get_optional_user,
)
from backend.app.database import get_db
from backend.app.execution_summary import (
    build_workbench_execution_summary,
)
from backend.app.result_store import (
    fetch_execution_result_export,
    fetch_execution_result_page,
    normalize_result_page,
    paginate_abnormal_results,
    persist_execution_result,
)
from backend.app.result_exporter import (
    RESULT_EXPORT_MIME_TYPE,
    build_execution_result_workbook,
)
from backend.app.utils.formatter import build_execution_response


router = APIRouter(prefix="/engine", tags=["engine"])


@router.post("/execute")
async def execute_engine(
    task_tree: TaskTree,
    ctx: CurrentUserContext | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """按 TaskTree 串起加载、规则执行与响应组装流程。"""
    project_id = (
        ctx.require_project_member()
        if ctx is not None and ctx.project_id is not None
        else None
    )

    try:
        execution_summary = await build_workbench_execution_summary(
            task_tree,
            db=db,
            project_id=project_id,
            user_id=ctx.user_id if ctx is not None else None,
        )
    except (ValueError, ImportError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    abnormal_results = execution_summary["abnormal_results"]
    elapsed_ms = execution_summary["execution_time_ms"]
    total_rows_scanned = execution_summary["total_rows_scanned"]
    failed_sources = execution_summary["failed_sources"]
    page, size = normalize_result_page(task_tree.page, task_tree.size)

    result_id: int | None = None
    if ctx is not None and project_id is not None:
        result_id = await persist_execution_result(
            db,
            scope_type="workbench",
            project_id=project_id,
            user_id=ctx.user_id,
            abnormal_results=abnormal_results,
            execution_time_ms=elapsed_ms,
            total_rows_scanned=total_rows_scanned,
            failed_sources=failed_sources,
        )

    if task_tree.page is None and task_tree.size is None and result_id is None:
        return build_execution_response(
            abnormal_results=abnormal_results,
            execution_time_ms=elapsed_ms,
            total_rows_scanned=total_rows_scanned,
            failed_sources=failed_sources,
            msg="Execution Completed",
        )

    return build_execution_response(
        abnormal_results=abnormal_results,
        execution_time_ms=elapsed_ms,
        total_rows_scanned=total_rows_scanned,
        failed_sources=failed_sources,
        msg="Execution Completed",
        result_id=result_id,
        page=page,
        size=size,
        total=len(abnormal_results),
        result_list=paginate_abnormal_results(abnormal_results, page, size),
    )


@router.get("/results/{result_id}")
async def get_execution_result_page(
    result_id: int,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """分页读取个人校验最近一次执行结果。"""
    project_id = ctx.require_project_member()
    normalized_page, normalized_size = normalize_result_page(page, size)
    payload = await fetch_execution_result_page(
        db,
        scope_type="workbench",
        result_id=result_id,
        project_id=project_id,
        user_id=ctx.user_id,
        page=normalized_page,
        size=normalized_size,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="未找到对应的执行结果")

    return build_execution_response(
        abnormal_results=payload["list"],
        execution_time_ms=payload["execution_time_ms"],
        total_rows_scanned=payload["total_rows_scanned"],
        failed_sources=payload["failed_sources"],
        msg="Execution Completed",
        result_id=payload["result_id"],
        page=payload["page"],
        size=payload["size"],
        total=payload["total"],
        result_list=payload["list"],
    )


@router.get("/results/{result_id}/export")
async def export_execution_result(
    result_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """导出个人校验最近一次执行结果为 Excel。"""
    project_id = ctx.require_project_member()
    payload = await fetch_execution_result_export(
        db,
        scope_type="workbench",
        result_id=result_id,
        project_id=project_id,
        user_id=ctx.user_id,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="未找到对应的执行结果")

    workbook = build_execution_result_workbook(payload, scope_label="个人校验")
    filename = f"personal-check-results-{result_id}.xlsx"
    return StreamingResponse(
        workbook,
        media_type=RESULT_EXPORT_MIME_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
