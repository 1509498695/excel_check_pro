"""固定规则模块接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.fixed_rules_schemas import (
    FixedRulesConfig,
    FixedRulesExecuteRequest,
    PackageItemsPreviewRequest,
)
from backend.app.auth.dependencies import CurrentUserContext, get_current_user
from backend.app.database import get_db
from backend.app.integrations.feishu_client import FeishuClientError
from backend.app.fixed_rules.db_service import (
    load_fixed_rules_config_from_db,
    save_fixed_rules_config_to_db,
)
from backend.app.fixed_rules.service import (
    build_default_fixed_rules_config,
    execute_fixed_rules_for_project,
    load_fixed_rules_config_with_issues,
    parse_raw_fixed_rules_config,
    run_saved_fixed_rules_svn_update,
    validate_and_normalize_fixed_rules_config,
)
from backend.app.fixed_rules.importer.schemas import WorkbenchImportPreviewRequest
from backend.app.fixed_rules.importer.workbench_import_service import (
    build_workbench_import_draft,
    commit_workbench_import,
    preview_workbench_import,
)
from backend.app.result_store import (
    fetch_execution_result_export,
    fetch_execution_result_page,
    normalize_result_page,
    paginate_abnormal_results,
)
from backend.app.result_exporter import (
    RESULT_EXPORT_MIME_TYPE,
    build_execution_result_workbook,
)
from backend.app.services.package_items_parser import preview_package_items_from_feishu
from backend.app.utils.formatter import build_execution_response


router = APIRouter(prefix="/fixed-rules", tags=["fixed-rules"])


@router.get("/import/workbench/draft")
async def get_workbench_import_draft(
    selected_rule_ids: list[str] | None = Query(default=None),
    selected_group_ids: list[str] | None = Query(default=None),
    user_id: int | None = Query(default=None),
    project_id: int | None = Query(default=None),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """读取当前用户个人校验配置，并生成导入项目校验的初始草稿。"""
    current_project_id = ctx.require_project_member()
    _validate_workbench_import_context(
        current_user_id=ctx.user_id,
        current_project_id=current_project_id,
        requested_user_id=user_id,
        requested_project_id=project_id,
    )
    try:
        draft = await build_workbench_import_draft(
            db,
            project_id=current_project_id,
            user_id=ctx.user_id,
            selected_rule_ids=selected_rule_ids,
            selected_group_ids=selected_group_ids,
        )
    except (ValueError, FileNotFoundError, ImportError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "code": 200,
        "msg": "ok",
        "data": draft.model_dump(mode="json", exclude_none=True),
    }


@router.post("/import/workbench/preview")
async def preview_workbench_import_endpoint(
    payload: WorkbenchImportPreviewRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """预览导入个人校验规则到项目校验；不保存配置。"""
    project_id = ctx.require_project_member()
    _validate_workbench_import_context(
        current_user_id=ctx.user_id,
        current_project_id=project_id,
        requested_user_id=payload.user_id,
        requested_project_id=payload.project_id,
    )
    try:
        preview = await preview_workbench_import(
            db,
            project_id=project_id,
            user_id=ctx.user_id,
            request=payload,
        )
    except (ValueError, FileNotFoundError, ImportError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "code": 200,
        "msg": "ok",
        "data": preview.model_dump(mode="json", exclude_none=True),
    }


@router.post("/import/workbench/commit")
async def commit_workbench_import_endpoint(
    payload: WorkbenchImportPreviewRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """重新校验并提交个人校验规则导入，失败时不写入项目配置。"""
    project_id = ctx.require_project_member()
    _validate_workbench_import_context(
        current_user_id=ctx.user_id,
        current_project_id=project_id,
        requested_user_id=payload.user_id,
        requested_project_id=payload.project_id,
    )
    try:
        result = await commit_workbench_import(
            db,
            project_id=project_id,
            user_id=ctx.user_id,
            request=payload,
        )
    except (ValueError, FileNotFoundError, ImportError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "code": 200,
        "msg": "ok",
        "data": result.config.model_dump(mode="json", exclude_none=True),
        "meta": {
            "import_summary": result.import_summary.model_dump(mode="json", exclude_none=True),
            "source_results": [
                item.model_dump(mode="json", exclude_none=True)
                for item in result.source_results
            ],
            "variable_results": [
                item.model_dump(mode="json", exclude_none=True)
                for item in result.variable_results
            ],
            "group_results": [
                item.model_dump(mode="json", exclude_none=True)
                for item in result.group_results
            ],
            "rule_results": [
                item.model_dump(mode="json", exclude_none=True)
                for item in result.rule_results
            ],
        },
    }


def _validate_workbench_import_context(
    *,
    current_user_id: int,
    current_project_id: int,
    requested_user_id: int | None,
    requested_project_id: int | None,
) -> None:
    """Reject attempts to import another user's or another project's workbench config."""
    if requested_user_id is not None and requested_user_id != current_user_id:
        raise HTTPException(status_code=403, detail="不能导入其他用户的个人校验配置。")
    if requested_project_id is not None and requested_project_id != current_project_id:
        raise HTTPException(status_code=403, detail="不能导入其他项目的个人校验配置。")


@router.get("/config")
async def get_fixed_rules_config(
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """读取当前固定规则配置（按 project_id 隔离）。"""
    project_id = ctx.require_project_member()

    try:
        raw = await load_fixed_rules_config_from_db(db, project_id)
        if raw is None:
            config = build_default_fixed_rules_config()
            config_issues = []
        else:
            parsed = parse_raw_fixed_rules_config(raw)
            config, config_issues = load_fixed_rules_config_with_issues(
                parsed,
                allow_legacy_mapping_config=True,
            )
    except (FileNotFoundError, ValueError, ImportError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response: dict[str, Any] = {
        "code": 200,
        "msg": "ok",
        "data": config.model_dump(mode="json", exclude_none=True),
    }
    if config_issues:
        response["meta"] = {
            "config_issues": [
                issue.model_dump(mode="json", exclude_none=True)
                for issue in config_issues
            ]
        }

    return response


@router.post("/package-items/preview")
async def preview_package_items_endpoint(
    payload: PackageItemsPreviewRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """预览飞书礼包规划表解析结果。"""
    project_id = ctx.require_project_member()
    try:
        raw = await load_fixed_rules_config_from_db(db, project_id)
        if raw is None:
            raise ValueError("当前项目尚未配置固定规则")
        parsed = parse_raw_fixed_rules_config(raw)
        config, _ = load_fixed_rules_config_with_issues(
            parsed,
            allow_legacy_mapping_config=True,
        )
        source = next(
            (
                item
                for item in config.sources
                if item.id == payload.feishu_source_id
            ),
            None,
        )
        if source is None:
            raise ValueError(f"未找到飞书数据源：{payload.feishu_source_id}")
        if source.type != "feishu":
            raise ValueError(f"数据源 '{payload.feishu_source_id}' 不是飞书数据源")
        preview = await preview_package_items_from_feishu(
            source,
            sheet_id=payload.sheet_id,
            parse_strategy=payload.parse_strategy,
            ai_parse_mode=payload.ai_parse_mode,
            db=db,
            project_id=project_id,
        )
    except (ValueError, FileNotFoundError, ImportError, FeishuClientError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "code": 200,
        "msg": "ok",
        "data": preview.model_dump(mode="json", exclude_none=True),
    }


@router.put("/config")
async def put_fixed_rules_config(
    payload: FixedRulesConfig,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """整体保存固定规则配置（按 project_id 隔离）。"""
    project_id = ctx.require_project_member()

    try:
        config, config_issues = load_fixed_rules_config_with_issues(
            payload,
            allow_unsupported_csv=False,
        )
    except (FileNotFoundError, ValueError, ImportError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await save_fixed_rules_config_to_db(
        db,
        project_id,
        config.model_dump(mode="json", exclude_none=True),
    )

    response: dict[str, Any] = {
        "code": 200,
        "msg": "ok",
        "data": config.model_dump(mode="json", exclude_none=True),
    }
    if config_issues:
        response["meta"] = {
            "config_issues": [
                issue.model_dump(mode="json", exclude_none=True)
                for issue in config_issues
            ]
        }

    return response


@router.post("/svn-update")
async def trigger_fixed_rules_svn_update(
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """对当前固定规则配置中的数据源目录执行 SVN 更新。"""
    project_id = ctx.require_project_member()

    raw = await load_fixed_rules_config_from_db(db, project_id)
    if raw is None:
        raise HTTPException(status_code=400, detail="当前项目尚未配置固定规则")

    try:
        parsed = parse_raw_fixed_rules_config(raw)
        config = validate_and_normalize_fixed_rules_config(parsed)
    except (FileNotFoundError, ValueError, ImportError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        update_result = run_saved_fixed_rules_svn_update(
            config,
            user_scope=ctx.user.username,
        )
    except (FileNotFoundError, ValueError, ImportError, NotImplementedError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "code": 200,
        "msg": "ok",
        "data": update_result,
    }


@router.post("/execute")
async def execute_fixed_rules_endpoint(
    payload: FixedRulesExecuteRequest | None = Body(default=None),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """执行当前项目的固定规则配置。"""
    project_id = ctx.require_project_member()

    page, size = normalize_result_page(
        payload.page if payload else None,
        payload.size if payload else None,
    )

    try:
        execution_summary = await execute_fixed_rules_for_project(
            db,
            project_id,
            user_scope=ctx.user.username,
            selected_rule_ids=payload.selected_rule_ids if payload else None,
        )
    except (FileNotFoundError, ValueError, ImportError, NotImplementedError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    abnormal_results = execution_summary["abnormal_results"]
    response = build_execution_response(
        abnormal_results=abnormal_results,
        execution_time_ms=execution_summary["execution_time_ms"],
        total_rows_scanned=execution_summary["total_rows_scanned"],
        failed_sources=execution_summary["failed_sources"],
        msg="Execution Completed",
        result_id=execution_summary["result_id"],
        page=page,
        size=size,
        total=len(abnormal_results),
        result_list=paginate_abnormal_results(abnormal_results, page, size),
    )
    if execution_summary.get("package_items_parse"):
        response["meta"]["package_items_parse"] = execution_summary["package_items_parse"]
    return response


@router.get("/results/{result_id}")
async def get_fixed_rules_result_page(
    result_id: int,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """分页读取当前项目最近一次项目校验结果。"""
    project_id = ctx.require_project_member()
    normalized_page, normalized_size = normalize_result_page(page, size)
    payload = await fetch_execution_result_page(
        db,
        scope_type="fixed_rules",
        result_id=result_id,
        project_id=project_id,
        user_id=None,
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
async def export_fixed_rules_result(
    result_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """导出当前项目的项目校验执行结果为 Excel。"""
    project_id = ctx.require_project_member()
    payload = await fetch_execution_result_export(
        db,
        scope_type="fixed_rules",
        result_id=result_id,
        project_id=project_id,
        user_id=None,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="未找到对应的执行结果")

    workbook = build_execution_result_workbook(payload, scope_label="项目校验")
    filename = f"project-check-results-{result_id}.xlsx"
    return StreamingResponse(
        workbook,
        media_type=RESULT_EXPORT_MIME_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
