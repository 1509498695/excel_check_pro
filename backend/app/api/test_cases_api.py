"""用例生成 V1 API 骨架。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.credentials import AiProviderInvalid, AiProviderNotConfigured
from backend.app.ai.providers import ProviderConnectionError
from backend.app.auth.dependencies import CurrentUserContext, get_current_user
from backend.app.database import get_db
from backend.app.integrations.feishu_client import (
    FEISHU_API_ERROR,
    FEISHU_APP_PERMISSION_MISSING,
    FEISHU_DOCUMENT_NOT_FOUND,
    FEISHU_DOCUMENT_PERMISSION_DENIED,
    FEISHU_INVALID_URL,
    FEISHU_READ_RANGE_TOO_LARGE,
    FeishuClientError,
)
from backend.app.loaders.local_reader import LocalFileAccessDeniedError
from backend.app.test_cases.constants import (
    FORBIDDEN_PUBLIC_KNOWLEDGE_FIELDS,
    STANDARD_CASE_FIELDS,
    TEST_CASES_NOT_IMPLEMENTED_MESSAGE,
)
from backend.app.test_cases.exporter import (
    TEST_CASE_EXPORT_MIME_TYPE,
    build_test_case_export_workbook,
)
from backend.app.test_cases.generation_runs import (
    GenerationRunError,
    build_generation_run_export_placeholder,
    cancel_generation_run,
    create_generation_run,
    get_generation_run_response,
    list_generation_run_atoms,
    list_generation_run_cases,
    retry_failed_generation_chunks,
)
from backend.app.test_cases.generation_artifacts import (
    get_generation_run_artifact_path,
    list_generation_run_artifacts,
    render_generation_run_artifacts,
)
from backend.app.test_cases.full_generation_orchestrator import (
    run_generation_run_background_task,
)
from backend.app.test_cases.planning_snapshot import build_planning_snapshot
from backend.app.test_cases.reference_library import (
    ReferenceLibraryError,
    create_reference_category,
    delete_reference_category,
    delete_reference_file,
    list_reference_categories,
    list_reference_files,
    rename_reference_category,
    set_recommended_primary_reference,
    upload_reference_file,
)
from backend.app.test_cases.reference_profiles import ReferenceProfileError
from backend.app.test_cases.schemas import (
    PlanningSnapshotBriefRequest,
    PlanningSnapshotRequest,
    ReferenceCategoryCreateRequest,
    ReferenceCategoryUpdateRequest,
    SourceEvidenceAdoptVisualEvidenceRequest,
    SourceEvidenceAuthorizationAuditItem,
    SourceEvidenceAuthorizationAuditListResponse,
    SourceEvidenceCleanupAuditItem,
    SourceEvidenceCleanupAuditListResponse,
    SourceEvidenceCapabilityStatusResponse,
    SourceEvidenceRunCreateRequest,
    SourceEvidenceSnapshotRequest,
    SourceEvidenceVisualSelectionRequest,
    TestCaseExportRequest,
    TestCaseGenerationRequest,
    TestCaseGenerationRunCreateRequest,
)
from backend.app.test_cases.source_evidence_cleanup import (
    list_source_evidence_cleanup_audits,
)
from backend.app.test_cases.source_evidence_capabilities import (
    build_source_evidence_capability_status,
)
from backend.app.test_cases.source_evidence_authorization import (
    REQUEST_EXPIRED_OR_CLEANED,
    handle_source_evidence_oauth_callback,
    invalidate_source_evidence_authorization,
    list_source_evidence_authorizations,
    render_callback_html,
    request_source_evidence_authorization,
)
from backend.app.test_cases.source_evidence import (
    SourceEvidenceError,
    build_source_evidence_resources_response,
    build_source_evidence_run_response,
    build_source_evidence_safe_context,
    build_source_evidence_snapshot,
    create_source_evidence_run_from_request,
    create_source_evidence_run_from_upload,
    ensure_no_forbidden_visual_refs,
    retry_source_evidence_run,
)
from backend.app.test_cases.visual_evidence import (
    adopt_visual_evidence,
    build_visual_candidates_response,
    build_visual_observations_response,
    create_visual_observations,
    revoke_adopted_visual_evidence,
    save_visual_selections,
)
from backend.app.test_cases.snapshot_brief import (
    SnapshotBriefPayloadError,
    generate_planning_snapshot_brief,
)
from backend.config import settings


router = APIRouter(prefix="/test-cases", tags=["test-cases"])

_FEISHU_ERROR_HTTP_MAP: dict[str, int] = {
    FEISHU_INVALID_URL: 400,
    FEISHU_APP_PERMISSION_MISSING: 403,
    FEISHU_DOCUMENT_PERMISSION_DENIED: 403,
    FEISHU_DOCUMENT_NOT_FOUND: 404,
    FEISHU_READ_RANGE_TOO_LARGE: 502,
    FEISHU_API_ERROR: 502,
}


async def reject_public_knowledge_context(request: Request) -> None:
    """拒绝 V1 公共请求中用户直接注入的知识库上下文。"""
    content_type = request.headers.get("content-type", "").lower()

    if "application/json" in content_type:
        try:
            payload: Any = await request.json()
        except ValueError:
            return

        if not isinstance(payload, dict):
            return
        payload_keys = set(payload)
    elif (
        "multipart/form-data" in content_type
        or "application/x-www-form-urlencoded" in content_type
    ):
        form = await request.form()
        payload_keys = set(form.keys())
    else:
        return

    forbidden_fields = sorted(
        field for field in FORBIDDEN_PUBLIC_KNOWLEDGE_FIELDS if field in payload_keys
    )
    if forbidden_fields:
        raise HTTPException(
            status_code=400,
            detail=(
                "V1 不接收用户传入的知识库上下文；"
                f"请移除字段：{', '.join(forbidden_fields)}"
            ),
        )


def _require_test_case_project(ctx: CurrentUserContext) -> int:
    """用例生成接口统一使用严格项目成员校验。"""
    return ctx.require_strict_project_member()


def _require_test_case_admin(ctx: CurrentUserContext) -> int:
    """用例生成管理接口先校验严格成员，再校验管理员。"""
    project_id = ctx.require_strict_project_member()
    ctx.require_project_admin()
    return project_id


def _is_project_admin(ctx: CurrentUserContext, project_id: int) -> bool:
    """判断当前用户是否拥有当前项目管理权限。"""
    return ctx.is_super_admin or ctx.role_in_project(project_id) == "admin"


def _not_implemented_response(feature: str, project_id: int) -> JSONResponse:
    """返回稳定的骨架阶段占位响应。"""
    return JSONResponse(
        status_code=501,
        content={
            "code": 501,
            "msg": TEST_CASES_NOT_IMPLEMENTED_MESSAGE,
            "data": {
                "feature": feature,
                "project_id": project_id,
                "standard_case_fields": list(STANDARD_CASE_FIELDS),
            },
        },
    )


def _raise_for_feishu_error(error: FeishuClientError) -> None:
    """将飞书读取错误转换为前端可直接展示的 HTTP 错误。"""
    status_code = _FEISHU_ERROR_HTTP_MAP.get(error.code, 502)
    message = (
        "机器人暂无该表格权限，请发送授权请求到群。"
        if error.code == FEISHU_DOCUMENT_PERMISSION_DENIED
        else error.message
    )
    raise HTTPException(
        status_code=status_code,
        detail={"code": error.code, "msg": message},
    )


def _raise_reference_library_error(error: ReferenceLibraryError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.message)


def _raise_source_evidence_error(error: SourceEvidenceError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.message)


def _raise_generation_run_error(error: GenerationRunError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.message)


def _resolve_source_evidence_oauth_callback_url(request: Request) -> str:
    """返回 Source Evidence 专用 OAuth callback URL。"""
    configured_callback_url = settings.feishu_source_evidence_oauth_callback_url.strip()
    if configured_callback_url:
        return configured_callback_url
    return str(request.url_for("handle_source_evidence_authorization_oauth_callback_api"))


@router.get("/source-evidence-cleanup-audits")
async def get_source_evidence_cleanup_audits_api(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """项目管理员查看本项目 Source Evidence 清理审计摘要。"""
    project_id = _require_test_case_admin(ctx)
    items, total = await list_source_evidence_cleanup_audits(
        db,
        project_id=project_id,
        limit=limit,
        offset=offset,
    )
    response = SourceEvidenceCleanupAuditListResponse(
        items=[SourceEvidenceCleanupAuditItem.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
    return {"code": 200, "msg": "ok", "data": response.model_dump(mode="json")}


@router.get("/source-evidence-capabilities")
async def get_source_evidence_capabilities_api(
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """读取当前项目 Source Evidence 运行能力状态。"""
    project_id = _require_test_case_project(ctx)
    result: SourceEvidenceCapabilityStatusResponse = await build_source_evidence_capability_status(
        db,
        project_id=project_id,
        is_project_admin=_is_project_admin(ctx, project_id),
    )
    return {
        "code": 200,
        "msg": "ok",
        "data": result.model_dump(mode="json", exclude_none=True),
    }


@router.post("/source-evidence-runs/{run_id}/authorization-request")
async def request_source_evidence_authorization_api(
    run_id: int,
    request: Request,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """显式发送 Source Evidence 飞书源文档授权卡。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await request_source_evidence_authorization(
            db,
            project_id=project_id,
            run_id=run_id,
            requested_by=ctx.user.username,
            callback_url=_resolve_source_evidence_oauth_callback_url(request),
        )
        await db.commit()
    except SourceEvidenceError as error:
        _raise_source_evidence_error(error)
    status_code = 409 if result.status == REQUEST_EXPIRED_OR_CLEANED else 200
    return JSONResponse(
        status_code=status_code,
        content={
            "code": status_code,
            "msg": "ok",
            "data": result.model_dump(mode="json"),
        },
    )


@router.get(
    "/source-evidence-authorizations/oauth/callback",
    response_class=HTMLResponse,
    name="handle_source_evidence_authorization_oauth_callback_api",
)
async def handle_source_evidence_authorization_oauth_callback_api(
    request: Request,
    code: str = Query(default=""),
    state: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Source Evidence 专用 OAuth callback，不要求系统登录。"""
    result = await handle_source_evidence_oauth_callback(
        db,
        code=code,
        state=state,
        callback_url=_resolve_source_evidence_oauth_callback_url(request),
    )
    await db.commit()
    return HTMLResponse(content=render_callback_html(result), status_code=200)


@router.get("/source-evidence-authorizations")
async def list_source_evidence_authorizations_api(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """项目管理员查看 Source Evidence 飞书授权审计摘要。"""
    project_id = _require_test_case_admin(ctx)
    items, total = await list_source_evidence_authorizations(
        db,
        project_id=project_id,
        limit=limit,
        offset=offset,
    )
    response = SourceEvidenceAuthorizationAuditListResponse(
        items=[SourceEvidenceAuthorizationAuditItem.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
    return {"code": 200, "msg": "ok", "data": response.model_dump(mode="json")}


@router.post("/source-evidence-authorizations/{authorization_id}/invalidate")
async def invalidate_source_evidence_authorization_api(
    authorization_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """项目管理员手动失效本系统授权复用，不移除飞书协作者。"""
    project_id = _require_test_case_admin(ctx)
    try:
        item = await invalidate_source_evidence_authorization(
            db,
            project_id=project_id,
            authorization_id=authorization_id,
            invalidated_by=ctx.user_id,
        )
        await db.commit()
    except SourceEvidenceError as error:
        _raise_source_evidence_error(error)
    response = SourceEvidenceAuthorizationAuditItem.model_validate(item)
    return {"code": 200, "msg": "ok", "data": response.model_dump(mode="json")}


@router.post("/planning-snapshot")
async def create_planning_snapshot(
    payload: PlanningSnapshotRequest,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """读取策划案快照，返回页面预览和生成接口复用的数据。"""
    project_id = _require_test_case_project(ctx)
    try:
        snapshot = await build_planning_snapshot(
            payload,
            db=db,
            project_id=project_id,
        )
    except LocalFileAccessDeniedError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except FeishuClientError as error:
        _raise_for_feishu_error(error)
    except (FileNotFoundError, ValueError, ImportError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "code": 200,
        "msg": "ok",
        "data": snapshot.model_dump(mode="json"),
    }


@router.post("/planning-snapshot/brief")
async def create_planning_snapshot_brief(
    payload: PlanningSnapshotBriefRequest,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """根据当前页面持有的快照生成 AI Markdown 整理稿。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await generate_planning_snapshot_brief(
            payload.planning_snapshot,
            db=db,
            project_id=project_id,
        )
    except (AiProviderInvalid, AiProviderNotConfigured) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ProviderConnectionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    except SnapshotBriefPayloadError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return {
        "code": 200,
        "msg": "ok",
        "data": result.model_dump(mode="json"),
    }


@router.post("/generation-runs")
async def create_generation_run_api(
    payload: TestCaseGenerationRunCreateRequest,
    background_tasks: BackgroundTasks,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """创建 V3 Generation Run，并按异步 run 语义启动后台 orchestrator。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await create_generation_run(
            db,
            project_id=project_id,
            created_by=ctx.user_id,
            payload=payload,
        )
        await db.commit()
    except GenerationRunError as error:
        await db.rollback()
        _raise_generation_run_error(error)
    background_tasks.add_task(
        run_generation_run_background_task,
        project_id=project_id,
        run_id=result.id,
        retry_failed_chunks_only=False,
    )
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.get("/generation-runs/{run_id}")
async def get_generation_run_api(
    run_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """读取 V3 Generation Run 摘要，跨项目不可见。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await get_generation_run_response(
            db,
            project_id=project_id,
            run_id=run_id,
        )
        await db.commit()
    except GenerationRunError as error:
        await db.rollback()
        _raise_generation_run_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.post("/generation-runs/{run_id}/cancel")
async def cancel_generation_run_api(
    run_id: int,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """取消仍处于 active 状态的 V3 Generation Run。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await cancel_generation_run(
            db,
            project_id=project_id,
            run_id=run_id,
            cancelled_by=ctx.user_id,
        )
        await db.commit()
    except GenerationRunError as error:
        await db.rollback()
        _raise_generation_run_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.post("/generation-runs/{run_id}/retry-failed-chunks")
async def retry_failed_generation_chunks_api(
    run_id: int,
    background_tasks: BackgroundTasks,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """重试 failed chunk，并启动后台 orchestrator 重建后续结果。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await retry_failed_generation_chunks(
            db,
            project_id=project_id,
            run_id=run_id,
        )
        await db.commit()
    except GenerationRunError as error:
        await db.rollback()
        _raise_generation_run_error(error)
    background_tasks.add_task(
        run_generation_run_background_task,
        project_id=project_id,
        run_id=run_id,
        retry_failed_chunks_only=True,
    )
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.get("/generation-runs/{run_id}/atoms")
async def list_generation_run_atoms_api(
    run_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """读取 V3 Generation Run 的需求原子结果。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await list_generation_run_atoms(
            db,
            project_id=project_id,
            run_id=run_id,
        )
        await db.commit()
    except GenerationRunError as error:
        await db.rollback()
        _raise_generation_run_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.get("/generation-runs/{run_id}/cases")
async def list_generation_run_cases_api(
    run_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """读取 V3 Generation Run 的用例结果。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await list_generation_run_cases(
            db,
            project_id=project_id,
            run_id=run_id,
        )
        await db.commit()
    except GenerationRunError as error:
        await db.rollback()
        _raise_generation_run_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.get("/generation-runs/{run_id}/artifacts")
async def list_generation_run_artifacts_api(
    run_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """列出 Generation Run 自动生成且可选择预览的文件产物。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await list_generation_run_artifacts(
            db,
            project_id=project_id,
            run_id=run_id,
        )
        await db.commit()
    except GenerationRunError as error:
        await db.rollback()
        _raise_generation_run_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.get("/generation-runs/{run_id}/artifacts/{artifact_key}")
async def download_generation_run_artifact_api(
    run_id: int,
    artifact_key: str,
    inline: bool = Query(default=False),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """读取已生成文件；该接口不重新生成内容。"""
    project_id = _require_test_case_project(ctx)
    try:
        path, item = await get_generation_run_artifact_path(
            db,
            project_id=project_id,
            run_id=run_id,
            artifact_key=artifact_key,
        )
        await db.commit()
    except GenerationRunError as error:
        await db.rollback()
        _raise_generation_run_error(error)
    return FileResponse(
        path,
        media_type=item.media_type,
        filename=item.file_name,
        content_disposition_type="inline" if inline else "attachment",
    )


@router.post("/generation-runs/{run_id}/artifacts/retry")
async def retry_generation_run_artifacts_api(
    run_id: int,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """只重跑确定性文件渲染，不重跑 AI、来源读取或用例生成。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await render_generation_run_artifacts(
            db,
            project_id=project_id,
            run_id=run_id,
            allow_terminal=True,
        )
        await db.commit()
    except GenerationRunError as error:
        await db.rollback()
        _raise_generation_run_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.post("/generation-runs/{run_id}/export")
async def export_generation_run_api(
    run_id: int,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """兼容旧按钮：下载 Generation Run 已生成的 Excel 文件。"""
    project_id = _require_test_case_project(ctx)
    try:
        try:
            path, item = await get_generation_run_artifact_path(
                db,
                project_id=project_id,
                run_id=run_id,
                artifact_key="workbook",
            )
        except GenerationRunError:
            # 兼容升级前已完成但尚无产物元数据的 run；进行确定性渲染前，
            # 仍沿用旧导出契约校验状态、过期时间、严格模式与非空用例。
            await build_generation_run_export_placeholder(
                db,
                project_id=project_id,
                run_id=run_id,
            )
            await render_generation_run_artifacts(
                db,
                project_id=project_id,
                run_id=run_id,
                allow_terminal=True,
            )
            path, item = await get_generation_run_artifact_path(
                db,
                project_id=project_id,
                run_id=run_id,
                artifact_key="workbook",
            )
        await db.commit()
    except GenerationRunError as error:
        await db.rollback()
        _raise_generation_run_error(error)
    return FileResponse(
        path,
        media_type=item.media_type,
        filename=item.file_name,
        content_disposition_type="attachment",
    )


@router.post("/generate")
async def generate_test_cases(
    payload: TestCaseGenerationRequest,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """旧同步生成入口已停用，V3 使用 Generation Run。"""
    _ = payload, db
    _require_test_case_project(ctx)
    raise HTTPException(
        status_code=410,
        detail="同步用例生成入口已停用，请使用 V3 Generation Run。",
    )


@router.post("/export")
async def export_test_cases(
    payload: TestCaseExportRequest,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """基于当前页面提交结果导出测试用例 Excel。"""
    project_id = _require_test_case_project(ctx)
    if payload.source_evidence_run_id is not None:
        try:
            source_evidence_context = await build_source_evidence_safe_context(
                db,
                project_id=project_id,
                run_id=payload.source_evidence_run_id,
                planning_sheet_name=payload.planning_sheet_name,
                adopted_visual_evidence_ids=payload.adopted_visual_evidence_ids,
            )
        except SourceEvidenceError as error:
            _raise_source_evidence_error(error)
        payload = payload.model_copy(
            update={"source_evidence_summary": source_evidence_context.export_summary}
        )
        try:
            ensure_no_forbidden_visual_refs(
                {
                    "blueprint": payload.blueprint.model_dump(mode="json"),
                    "cases": [case.model_dump(mode="json") for case in payload.cases],
                    "warnings": [warning.model_dump(mode="json") for warning in payload.warnings],
                    "source_evidence_summary": payload.source_evidence_summary,
                },
                forbidden_refs=source_evidence_context.forbidden_visual_refs,
                status_code=400,
                message="导出内容引用了未采纳视觉证据。",
            )
        except SourceEvidenceError as error:
            _raise_source_evidence_error(error)
    workbook = build_test_case_export_workbook(payload)
    filename = "test-cases-v1.xlsx"
    return StreamingResponse(
        workbook,
        media_type=TEST_CASE_EXPORT_MIME_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/source-evidence-runs")
async def create_source_evidence_run_api(
    payload: SourceEvidenceRunCreateRequest,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """创建 Source Evidence Run，并同步读取富来源。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await create_source_evidence_run_from_request(
            db,
            project_id=project_id,
            created_by=ctx.user_id,
            payload=payload,
        )
    except SourceEvidenceError as error:
        _raise_source_evidence_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.post("/source-evidence-runs/upload")
async def upload_source_evidence_run_api(
    file: UploadFile = File(...),
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """上传本地文件并创建 local_file Source Evidence Run。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await create_source_evidence_run_from_upload(
            db,
            project_id=project_id,
            created_by=ctx.user_id,
            file=file,
        )
    except SourceEvidenceError as error:
        _raise_source_evidence_error(error)
    finally:
        await file.close()
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.get("/source-evidence-runs/{run_id}")
async def get_source_evidence_run_api(
    run_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """读取 Source Evidence Run 摘要。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await build_source_evidence_run_response(
            db,
            project_id=project_id,
            run_id=run_id,
        )
    except SourceEvidenceError as error:
        _raise_source_evidence_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.get("/source-evidence-runs/{run_id}/resources")
async def get_source_evidence_resources_api(
    run_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """读取 Source Evidence Run 资源清单。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await build_source_evidence_resources_response(
            db,
            project_id=project_id,
            run_id=run_id,
        )
    except SourceEvidenceError as error:
        _raise_source_evidence_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.get("/source-evidence-runs/{run_id}/visual-candidates")
async def get_source_evidence_visual_candidates_api(
    run_id: int,
    sheet_name: str | None = Query(default=None),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """读取或懒生成 Source Evidence Run 视觉候选。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await build_visual_candidates_response(
            db,
            project_id=project_id,
            run_id=run_id,
            sheet_name=sheet_name,
        )
        await db.commit()
    except SourceEvidenceError as error:
        _raise_source_evidence_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.post("/source-evidence-runs/{run_id}/visual-selections")
async def save_source_evidence_visual_selections_api(
    run_id: int,
    payload: SourceEvidenceVisualSelectionRequest,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """替换式保存 Source Evidence Run 的视觉观察选择。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await save_visual_selections(
            db,
            project_id=project_id,
            run_id=run_id,
            selected_refs=payload.selected_refs,
            sheet_name=payload.sheet_name,
        )
        await db.commit()
    except SourceEvidenceError as error:
        _raise_source_evidence_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.post("/source-evidence-runs/{run_id}/observations")
async def create_source_evidence_observations_api(
    run_id: int,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """对已保存视觉选择生成 observation，不自动采纳。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await create_visual_observations(
            db,
            project_id=project_id,
            run_id=run_id,
            created_by=ctx.user_id,
        )
        await db.commit()
    except SourceEvidenceError as error:
        _raise_source_evidence_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.get("/source-evidence-runs/{run_id}/observations")
async def get_source_evidence_observations_api(
    run_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """读取 Source Evidence Run 的 observation 安全摘要。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await build_visual_observations_response(
            db,
            project_id=project_id,
            run_id=run_id,
        )
    except SourceEvidenceError as error:
        _raise_source_evidence_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.post("/source-evidence-runs/{run_id}/adopted-visual-evidence")
async def adopt_source_evidence_visual_evidence_api(
    run_id: int,
    payload: SourceEvidenceAdoptVisualEvidenceRequest,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """将已观察视觉证据显式采纳。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await adopt_visual_evidence(
            db,
            project_id=project_id,
            run_id=run_id,
            observation_ids=payload.observation_ids,
            adopted_by=ctx.user_id,
        )
        await db.commit()
    except SourceEvidenceError as error:
        _raise_source_evidence_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.delete("/source-evidence-runs/{run_id}/adopted-visual-evidence/{evidence_id}")
async def revoke_source_evidence_visual_evidence_api(
    run_id: int,
    evidence_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """撤销已采纳视觉证据。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await revoke_adopted_visual_evidence(
            db,
            project_id=project_id,
            run_id=run_id,
            evidence_id=evidence_id,
            revoked_by=ctx.user_id,
        )
        await db.commit()
    except SourceEvidenceError as error:
        _raise_source_evidence_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.post("/source-evidence-runs/{run_id}/snapshot")
async def create_source_evidence_snapshot_api(
    run_id: int,
    payload: SourceEvidenceSnapshotRequest | None = Body(default=None),
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """把 Source Evidence Run 转成 PlanningSnapshotResponse。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await build_source_evidence_snapshot(
            db,
            project_id=project_id,
            run_id=run_id,
            sheet_name=payload.sheet_name if payload else None,
        )
    except SourceEvidenceError as error:
        _raise_source_evidence_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.post("/source-evidence-runs/{run_id}/retry")
async def retry_source_evidence_run_api(
    run_id: int,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """重试读取 Source Evidence Run。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await retry_source_evidence_run(
            db,
            project_id=project_id,
            run_id=run_id,
        )
    except SourceEvidenceError as error:
        _raise_source_evidence_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.get("/reference-categories")
async def get_reference_categories(
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """列出当前项目参考案例分类。"""
    project_id = _require_test_case_project(ctx)
    result = await list_reference_categories(db, project_id=project_id)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.post("/reference-categories")
async def create_reference_category_api(
    payload: ReferenceCategoryCreateRequest,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """创建当前项目参考案例分类，项目成员可操作。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await create_reference_category(
            db,
            project_id=project_id,
            user_id=ctx.user_id,
            payload=payload,
        )
    except ReferenceLibraryError as error:
        _raise_reference_library_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.patch("/reference-categories/{category_id}")
async def rename_reference_category_api(
    category_id: int,
    payload: ReferenceCategoryUpdateRequest,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """重命名参考案例分类，项目管理员或超级管理员可操作。"""
    project_id = _require_test_case_admin(ctx)
    try:
        result = await rename_reference_category(
            db,
            project_id=project_id,
            category_id=category_id,
            payload=payload,
        )
    except ReferenceLibraryError as error:
        _raise_reference_library_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.delete("/reference-categories/{category_id}")
async def delete_reference_category_api(
    category_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """删除参考案例分类，关联参考移到未分类。"""
    project_id = _require_test_case_admin(ctx)
    try:
        result = await delete_reference_category(
            db,
            project_id=project_id,
            category_id=category_id,
        )
    except ReferenceLibraryError as error:
        _raise_reference_library_error(error)
    return {"code": 200, "msg": "ok", "data": result}


@router.get("/references")
async def get_reference_files(
    category_id: int | None = Query(default=None),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """列出当前项目 active 参考案例。"""
    project_id = _require_test_case_project(ctx)
    result = await list_reference_files(
        db,
        project_id=project_id,
        category_id=category_id,
    )
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.post("/references")
async def upload_reference_file_api(
    category_id: int | None = Form(default=None),
    file: UploadFile = File(...),
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """上传参考案例文件并生成确定性画像，项目成员可操作。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await upload_reference_file(
            db,
            project_id=project_id,
            user_id=ctx.user_id,
            upload=file,
            category_id=category_id,
        )
    except ReferenceProfileError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ReferenceLibraryError as error:
        _raise_reference_library_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.post("/references/{reference_id}/recommended-primary")
async def set_recommended_primary_reference_api(
    reference_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """设置当前分类范围内唯一推荐主参考。"""
    project_id = _require_test_case_admin(ctx)
    try:
        result = await set_recommended_primary_reference(
            db,
            project_id=project_id,
            reference_id=reference_id,
        )
    except ReferenceLibraryError as error:
        _raise_reference_library_error(error)
    return {"code": 200, "msg": "ok", "data": result.model_dump(mode="json")}


@router.delete("/references/{reference_id}")
async def delete_reference_file_api(
    reference_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """删除参考案例文件，物理删除失败时保留 active 状态。"""
    project_id = _require_test_case_admin(ctx)
    try:
        result = await delete_reference_file(
            db,
            project_id=project_id,
            reference_id=reference_id,
            user_id=ctx.user_id,
        )
    except ReferenceLibraryError as error:
        _raise_reference_library_error(error)
    return {"code": 200, "msg": "ok", "data": result}
