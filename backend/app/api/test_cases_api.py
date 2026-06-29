"""用例生成 V1 API 骨架。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
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
from backend.app.test_cases.generation import (
    TestCaseGenerationPayloadError,
    generate_test_case_response,
)
from backend.app.test_cases.exporter import (
    TEST_CASE_EXPORT_MIME_TYPE,
    build_test_case_export_workbook,
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
    TestCaseExportRequest,
    TestCaseGenerationRequest,
)
from backend.app.test_cases.snapshot_brief import (
    SnapshotBriefPayloadError,
    generate_planning_snapshot_brief,
)


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


@router.post("/generate")
async def generate_test_cases(
    payload: TestCaseGenerationRequest,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """按 QA Case Method 生成蓝图和测试用例。"""
    project_id = _require_test_case_project(ctx)
    try:
        result = await generate_test_case_response(
            payload,
            db=db,
            project_id=project_id,
        )
    except (AiProviderInvalid, AiProviderNotConfigured) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ProviderConnectionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    except ReferenceLibraryError as error:
        _raise_reference_library_error(error)
    except TestCaseGenerationPayloadError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return {
        "code": 200,
        "msg": "ok",
        "data": result.model_dump(mode="json"),
    }


@router.post("/export")
async def export_test_cases(
    payload: TestCaseExportRequest,
    _knowledge_guard: None = Depends(reject_public_knowledge_context),
    ctx: CurrentUserContext = Depends(get_current_user),
) -> StreamingResponse:
    """基于当前页面提交结果导出测试用例 Excel。"""
    _require_test_case_project(ctx)
    workbook = build_test_case_export_workbook(payload)
    filename = "test-cases-v1.xlsx"
    return StreamingResponse(
        workbook,
        media_type=TEST_CASE_EXPORT_MIME_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
