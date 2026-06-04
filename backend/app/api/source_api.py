"""数据源相关接口。"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import textwrap
from uuid import uuid4
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas import DataSource
from backend.app.auth.dependencies import (
    CurrentUserContext,
    get_current_user,
)
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
from backend.app.loaders.feishu_reader import (
    preview_feishu_composite_variable,
    preview_feishu_source_column,
    read_feishu_source_metadata,
)
from backend.app.loaders.local_reader import (
    LocalFileAccessDeniedError,
    ensure_directory_in_local_file_allowlist,
    preview_composite_variable,
    preview_source_column,
    read_source_metadata,
)
from backend.app.loaders.svn_cache import (
    get_remote_cache_state,
    is_remote_svn_locator,
    prepare_remote_svn_source,
)
from backend.app.loaders.svn_credentials import (
    delete_credentials,
    load_credentials,
    list_hosts as list_svn_credential_hosts,
    save_credentials,
)
from backend.app.loaders.svn_manager import (
    SvnRemoteError,
    enforce_host_allowlist,
    list_svn_directory,
    normalize_dir_url,
)
from backend.config import settings


router = APIRouter(prefix="/sources", tags=["sources"])

LOCAL_PICK_SUFFIXES: dict[str, tuple[str, ...]] = {
    "local_excel": (".xlsx", ".xls"),
}
UPLOAD_SUFFIX_SOURCE_TYPES: dict[str, str] = {
    ".xlsx": "local_excel",
    ".xls": "local_excel",
}
_UPLOAD_CHUNK_SIZE = 1024 * 1024


class LocalPickRequest(BaseModel):
    """本地文件选择请求。"""

    model_config = ConfigDict(extra="forbid")

    source_type: Literal["local_excel"]


class LocalDirectoryValidateRequest(BaseModel):
    """本地目录校验请求。"""

    model_config = ConfigDict(extra="forbid")

    directory_path: str


class ColumnPreviewRequest(BaseModel):
    """单列预览请求。"""

    model_config = ConfigDict(extra="forbid")

    source: DataSource
    sheet: str
    column: str
    limit: int | None = Field(default=None, ge=1, le=20000)


class CompositePreviewRequest(BaseModel):
    """组合变量预览请求。"""

    model_config = ConfigDict(extra="forbid")

    source: DataSource
    sheet: str
    columns: list[str] = Field(default_factory=list)
    key_column: str
    append_index_to_key: bool = False
    page: int | None = Field(default=None, ge=1)
    size: int | None = Field(default=None, ge=1, le=200)


class SvnListRequest(BaseModel):
    """SVN 远端目录列表请求。"""

    model_config = ConfigDict(extra="forbid")

    dir_url: str


class SvnCredentialUpsertRequest(BaseModel):
    """保存 SVN host 凭据请求。"""

    model_config = ConfigDict(extra="forbid")

    host: str
    username: str
    password: str
    test_dir_url: str | None = None


class SvnRefreshRequest(BaseModel):
    """强制刷新某 SVN 数据源的缓存。"""

    model_config = ConfigDict(extra="forbid")

    source: DataSource


# SvnRemoteError.category → (HTTP 状态码, code)
# 注意：这里的 401 不能直接用于"SVN 业务凭据失败"——前端 apiFetch 会把任何
# 401 当成登录态过期并自动跳 /login。因此 auth_failed 用 403 表达"业务级
# 拒绝"，由前端 SVN 弹窗自己引导用户重新输入 SVN 凭据。
_SVN_ERROR_HTTP_MAP: dict[str, tuple[int, int]] = {
    "auth_failed": (403, 4030),
    "not_found": (404, 404),
    "network": (502, 502),
    "timeout": (504, 504),
    "unknown": (500, 500),
}

_FEISHU_METADATA_ERROR_HTTP_MAP: dict[str, int] = {
    FEISHU_INVALID_URL: 400,
    FEISHU_APP_PERMISSION_MISSING: 403,
    FEISHU_DOCUMENT_PERMISSION_DENIED: 403,
    FEISHU_DOCUMENT_NOT_FOUND: 404,
    FEISHU_READ_RANGE_TOO_LARGE: 502,
    FEISHU_API_ERROR: 502,
}


def _raise_for_svn_error(error: SvnRemoteError) -> None:
    status_code, code_value = _SVN_ERROR_HTTP_MAP.get(error.category, (500, 500))
    raise HTTPException(
        status_code=status_code,
        detail={"code": code_value, "msg": error.message, "category": error.category},
    )


def _raise_for_feishu_metadata_error(error: FeishuClientError) -> None:
    """将飞书客户端错误转换为 metadata 接口的 HTTP 错误。"""
    status_code = _FEISHU_METADATA_ERROR_HTTP_MAP.get(error.code, 502)
    message = (
        "机器人暂无该表格权限，请发送授权请求到群。"
        if error.code == FEISHU_DOCUMENT_PERMISSION_DENIED
        else error.message
    )
    raise HTTPException(
        status_code=status_code,
        detail={"code": error.code, "msg": message},
    )


def _require_source_project(ctx: CurrentUserContext) -> int:
    """数据源接口使用严格项目校验，避免 Token 指向非成员项目时静默回退。"""
    return ctx.require_strict_project_member()


def _get_pick_filetypes(source_type: str) -> list[tuple[str, str]]:
    """返回 tkinter 文件对话框需要的文件类型。"""
    if source_type == "local_excel":
        return [("Excel 文件", "*.xlsx *.xls")]
    raise ValueError(f"暂不支持 {source_type} 的本地文件选择。")


# 以独立子进程运行 tkinter 文件选择框，避免在长生命周期的 FastAPI/uvicorn
# 主进程里残留 Tcl 解释器与窗口焦点资源；子进程退出后所有 GUI 资源会被
# 操作系统一并回收，前后端事件循环也不会被阻塞或挂起。
_PICKER_SUBPROCESS_SCRIPT = textwrap.dedent(
    """
    import json
    import sys
    import tkinter as tk
    from tkinter import filedialog

    config = json.loads(sys.argv[1])
    filetypes = [tuple(item) for item in config.get("filetypes", [])]

    root = tk.Tk()
    try:
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
        selected_path = filedialog.askopenfilename(
            title=config.get("title", "选择文件"),
            filetypes=filetypes,
        )
    finally:
        try:
            root.destroy()
        except Exception:
            pass

    sys.stdout.write(selected_path or "")
    """
).strip()

_PICKER_SUBPROCESS_TIMEOUT_SECONDS = 600


def _validate_selected_path(source_type: str, selected_path: str) -> str:
    """校验系统文件框返回的真实路径。"""
    if not selected_path:
        return ""

    path = Path(selected_path).expanduser()
    suffix = path.suffix.lower()
    allowed_suffixes = LOCAL_PICK_SUFFIXES[source_type]

    if suffix not in allowed_suffixes:
        allowed_text = "、".join(sorted(allowed_suffixes))
        raise HTTPException(
            status_code=400,
            detail=(
                f"{source_type} 仅支持 {allowed_text} 文件，当前选择为 "
                f"{suffix or '无后缀文件'}。"
            ),
        )

    try:
        resolved_path = ensure_directory_in_local_file_allowlist(path)
    except LocalFileAccessDeniedError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error

    if not resolved_path.exists():
        raise HTTPException(status_code=400, detail=f"所选文件不存在：{resolved_path}")
    if not resolved_path.is_file():
        raise HTTPException(status_code=400, detail=f"所选路径不是文件：{resolved_path}")

    return str(resolved_path)


def _show_local_file_dialog(source_type: str) -> str:
    """在独立子进程中弹出系统文件选择框并返回真实路径。

    采用子进程隔离的原因：
    - tkinter 在长期运行的 uvicorn 主进程里反复创建/销毁 Tk 根窗口，
      容易在 Windows 上残留焦点抢占与 Tcl 资源，进而引发后续请求被卡住。
    - 子进程方案让每次选择都在干净环境里创建并销毁 GUI，事件循环不会被
      阻塞，前端连续选择文件也不会越用越慢。
    """

    config = {
        "title": "选择本地配置文件",
        "filetypes": _get_pick_filetypes(source_type),
    }

    try:
        completed = subprocess.run(
            [sys.executable, "-c", _PICKER_SUBPROCESS_SCRIPT, json.dumps(config)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=_PICKER_SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as error:  # pragma: no cover - 缺少 Python 解释器
        raise RuntimeError(
            "当前环境无法启动本机文件选择子进程，请手动输入本地文件路径。"
        ) from error
    except subprocess.TimeoutExpired as error:  # pragma: no cover - 用户长时间未操作
        raise RuntimeError("系统文件选择框等待超时，请重试。") from error

    if completed.returncode != 0:  # pragma: no cover - 真实桌面环境问题
        stderr_text = (completed.stderr or "").strip() or "未知错误"
        raise RuntimeError(f"系统文件选择框打开失败：{stderr_text}")

    return (completed.stdout or "").strip()


def _validate_directory_path(raw_directory_path: str) -> str:
    """校验并规范化本地目录路径。"""
    normalized_input = raw_directory_path.strip()
    if not normalized_input:
        raise HTTPException(status_code=400, detail="替换目录不能为空。")

    directory_path = Path(normalized_input).expanduser()
    if not directory_path.is_absolute():
        raise HTTPException(status_code=400, detail="替换目录必须是本地绝对路径。")

    try:
        resolved_path = ensure_directory_in_local_file_allowlist(directory_path)
    except LocalFileAccessDeniedError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error

    if not resolved_path.exists():
        raise HTTPException(status_code=400, detail=f"替换目录不存在：{resolved_path}")
    if not resolved_path.is_dir():
        raise HTTPException(status_code=400, detail=f"替换路径不是目录：{resolved_path}")

    return str(resolved_path)


def _sanitize_upload_filename(filename: str) -> str:
    """将浏览器上传文件名规整成安全的本地文件名。"""
    basename = Path(filename).name.strip()
    if not basename:
        raise HTTPException(status_code=400, detail="上传文件名不能为空。")

    suffix = Path(basename).suffix.lower()
    if suffix not in UPLOAD_SUFFIX_SOURCE_TYPES:
        allowed_text = "、".join(sorted(UPLOAD_SUFFIX_SOURCE_TYPES))
        raise HTTPException(
            status_code=400,
            detail=f"仅支持上传 {allowed_text} 文件。",
        )

    stem = Path(basename).stem
    safe_stem = re.sub(r"[^A-Za-z0-9_\-.]+", "_", stem).strip("._-") or "upload"
    return f"{safe_stem}{suffix}"


async def _save_upload_file(
    upload: UploadFile,
    *,
    project_id: int,
    user_id: int,
) -> dict[str, Any]:
    """保存上传文件并返回可复用为 DataSource.pathOrUrl 的绝对路径。"""
    safe_filename = _sanitize_upload_filename(upload.filename or "")
    suffix = Path(safe_filename).suffix.lower()
    source_type = UPLOAD_SUFFIX_SOURCE_TYPES[suffix]
    upload_dir = settings.runtime_upload_dir / str(project_id) / str(user_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    target_path = upload_dir / f"{uuid4().hex}_{safe_filename}"
    total_size = 0

    try:
        with target_path.open("wb") as file_handle:
            while True:
                chunk = await upload.read(_UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"上传文件不能超过 {settings.max_upload_mb} MB。",
                    )
                file_handle.write(chunk)
    except Exception:
        if target_path.exists():
            target_path.unlink()
        raise
    finally:
        await upload.close()

    return {
        "source_type": source_type,
        "original_filename": Path(upload.filename or safe_filename).name,
        "stored_filename": target_path.name,
        "selected_path": str(target_path.resolve()),
        "size": total_size,
    }


@router.get("/capabilities")
def get_source_capabilities(
    ctx: CurrentUserContext = Depends(get_current_user),
) -> dict[str, Any]:
    """返回当前后端声明支持的数据源能力。"""
    _require_source_project(ctx)
    return {
        "code": 200,
        "msg": "ok",
        "data": {
            "source_types": list(settings.supported_source_types),
            "implemented": True,
        },
    }


@router.post("/local-pick")
async def pick_local_source_file(
    payload: LocalPickRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
) -> dict[str, Any]:
    """在本机弹出系统文件选择框，并返回真实本地路径。"""
    _require_source_project(ctx)
    if not settings.enable_local_picker:
        raise HTTPException(
            status_code=403,
            detail="本机文件选择器默认关闭，请使用上传文件，或由管理员设置 ENABLE_LOCAL_PICKER=true。",
        )

    try:
        selected_path = _show_local_file_dialog(payload.source_type)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    if not selected_path:
        return {
            "code": 204,
            "msg": "cancelled",
            "data": {
                "selected_path": "",
                "source_type": payload.source_type,
            },
        }

    resolved_path = _validate_selected_path(payload.source_type, selected_path)
    return {
        "code": 200,
        "msg": "ok",
        "data": {
            "selected_path": resolved_path,
            "source_type": payload.source_type,
        },
    }


@router.post("/upload")
async def upload_source_file(
    file: UploadFile = File(...),
    ctx: CurrentUserContext = Depends(get_current_user),
) -> dict[str, Any]:
    """接收浏览器上传的 Excel，并保存到项目/用户隔离目录。"""
    project_id = _require_source_project(ctx)
    saved_file = await _save_upload_file(
        file,
        project_id=project_id,
        user_id=ctx.user_id,
    )
    return {
        "code": 200,
        "msg": "ok",
        "data": {
            **saved_file,
            "project_id": project_id,
            "user_id": ctx.user_id,
        },
    }


@router.post("/local-directory-validate")
async def validate_local_directory_path(
    payload: LocalDirectoryValidateRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
) -> dict[str, Any]:
    """校验并返回规范化后的本地目录路径。"""
    _require_source_project(ctx)
    normalized_directory = _validate_directory_path(payload.directory_path)
    return {
        "code": 200,
        "msg": "ok",
        "data": {
            "directory_path": normalized_directory,
        },
    }


@router.post("/metadata")
async def get_source_metadata(
    source: DataSource,
    include_columns: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    ctx: CurrentUserContext = Depends(get_current_user),
) -> dict[str, Any]:
    """返回变量池构建所需的 Sheet 与列结构。"""
    project_id = _require_source_project(ctx)
    if source.type == "feishu":
        try:
            metadata = await read_feishu_source_metadata(
                source,
                db=db,
                project_id=project_id,
                include_columns=include_columns,
            )
        except FeishuClientError as error:
            _raise_for_feishu_metadata_error(error)
        return {
            "code": 200,
            "msg": "ok",
            "data": metadata,
        }

    try:
        metadata = read_source_metadata(source)
    except LocalFileAccessDeniedError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except (FileNotFoundError, ValueError, ImportError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "code": 200,
        "msg": "ok",
        "data": metadata,
    }


@router.post("/column-preview")
async def get_source_column_preview(
    payload: ColumnPreviewRequest,
    db: AsyncSession = Depends(get_db),
    ctx: CurrentUserContext = Depends(get_current_user),
) -> dict[str, Any]:
    """返回单个变量详情弹窗所需的列预览数据。"""
    project_id = _require_source_project(ctx)
    if payload.source.type == "feishu":
        try:
            preview = await preview_feishu_source_column(
                payload.source,
                sheet_name=payload.sheet,
                column_name=payload.column,
                limit=payload.limit,
                db=db,
                project_id=project_id,
            )
        except FeishuClientError as error:
            _raise_for_feishu_metadata_error(error)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        return {
            "code": 200,
            "msg": "ok",
            "data": preview,
        }

    try:
        preview = preview_source_column(
            payload.source,
            sheet_name=payload.sheet,
            column_name=payload.column,
            limit=payload.limit,
        )
    except LocalFileAccessDeniedError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except (FileNotFoundError, ValueError, ImportError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "code": 200,
        "msg": "ok",
        "data": preview,
    }


@router.post("/composite-preview")
async def get_composite_variable_preview(
    payload: CompositePreviewRequest,
    db: AsyncSession = Depends(get_db),
    ctx: CurrentUserContext = Depends(get_current_user),
) -> dict[str, Any]:
    """返回组合变量所需的 JSON 映射预览。"""
    project_id = _require_source_project(ctx)
    if payload.source.type == "feishu":
        try:
            preview = await preview_feishu_composite_variable(
                payload.source,
                sheet_name=payload.sheet,
                columns=payload.columns,
                key_column=payload.key_column,
                append_index_to_key=payload.append_index_to_key,
                page=payload.page,
                size=payload.size,
                db=db,
                project_id=project_id,
            )
        except FeishuClientError as error:
            _raise_for_feishu_metadata_error(error)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        return {
            "code": 200,
            "msg": "ok",
            "data": preview,
        }

    try:
        preview = preview_composite_variable(
            payload.source,
            sheet_name=payload.sheet,
            columns=payload.columns,
            key_column=payload.key_column,
            append_index_to_key=payload.append_index_to_key,
            page=payload.page,
            size=payload.size,
        )
    except LocalFileAccessDeniedError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except (FileNotFoundError, ValueError, ImportError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "code": 200,
        "msg": "ok",
        "data": preview,
    }


@router.post("/svn-list")
async def list_remote_svn_directory(
    payload: SvnListRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
) -> dict[str, Any]:
    """列出 SVN 远端目录下的文件与子目录（最多 1 层下钻在前端控制）。"""
    _require_source_project(ctx)
    try:
        normalized_dir_url = normalize_dir_url(payload.dir_url)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    try:
        host = enforce_host_allowlist(urlparse(normalized_dir_url).hostname)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    credentials = load_credentials(host=host, user_scope=ctx.user.username)

    try:
        result = list_svn_directory(
            normalized_dir_url,
            credentials=credentials,
        )
    except SvnRemoteError as error:
        _raise_for_svn_error(error)
    except NotImplementedError as error:
        raise HTTPException(status_code=501, detail=str(error)) from error

    return {
        "code": 200,
        "msg": "ok",
        "data": {
            "dir_url": result["dir_url"],
            "host": host,
            "entries": result["entries"],
            "credential_username": credentials.username if credentials else "",
        },
    }


@router.post("/svn-credentials")
async def save_svn_credentials_endpoint(
    payload: SvnCredentialUpsertRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
) -> dict[str, Any]:
    """保存当前登录用户在某 SVN host 上的凭据。"""
    _require_source_project(ctx)
    try:
        host = enforce_host_allowlist(payload.host)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if not payload.username.strip() or not payload.password:
        raise HTTPException(status_code=400, detail="用户名与密码不能为空。")

    normalized_test_dir_url: str | None = None
    if payload.test_dir_url is not None:
        try:
            normalized_test_dir_url = normalize_dir_url(payload.test_dir_url)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        try:
            test_dir_host = enforce_host_allowlist(urlparse(normalized_test_dir_url).hostname)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        if test_dir_host != host:
            raise HTTPException(status_code=400, detail="测试目录 URL 与当前 SVN host 不匹配。")

    try:
        record = save_credentials(
            host=host,
            username=payload.username.strip(),
            password=payload.password,
            user_scope=ctx.user.username,
            test_dir_url=normalized_test_dir_url,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "code": 200,
        "msg": "ok",
        "data": {
            "host": record.host,
            "username": record.username,
            "updated_at": record.updated_at,
            "test_dir_url": record.test_dir_url,
        },
    }


@router.get("/svn-credentials")
async def list_svn_credentials_endpoint(
    ctx: CurrentUserContext = Depends(get_current_user),
) -> dict[str, Any]:
    """列出当前登录用户已保存的 SVN host（不返回密码）。"""
    _require_source_project(ctx)
    items = list_svn_credential_hosts(user_scope=ctx.user.username)
    return {
        "code": 200,
        "msg": "ok",
        "data": {"items": items},
    }


@router.get("/svn-credentials/{host}")
async def get_svn_credential_detail_endpoint(
    host: str,
    ctx: CurrentUserContext = Depends(get_current_user),
) -> dict[str, Any]:
    """读取当前登录用户在某 host 上已保存的 SVN 凭据详情。"""
    _require_source_project(ctx)
    try:
        normalized_host = enforce_host_allowlist(host)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    credential = load_credentials(host=normalized_host, user_scope=ctx.user.username)
    if credential is None:
        raise HTTPException(status_code=404, detail="当前 host 尚未保存 SVN 凭据。")

    return {
        "code": 200,
        "msg": "ok",
        "data": {
            "host": credential.host,
            "username": credential.username,
            "password": credential.password,
            "updated_at": credential.updated_at,
            "test_dir_url": credential.test_dir_url,
        },
    }


@router.delete("/svn-credentials/{host}")
async def delete_svn_credentials_endpoint(
    host: str,
    ctx: CurrentUserContext = Depends(get_current_user),
) -> dict[str, Any]:
    """删除当前登录用户在某 host 上的凭据。"""
    _require_source_project(ctx)
    deleted = delete_credentials(host=host, user_scope=ctx.user.username)
    return {
        "code": 200,
        "msg": "ok",
        "data": {"host": host.strip().lower(), "deleted": deleted},
    }


@router.post("/svn-refresh")
async def refresh_remote_svn_source(
    payload: SvnRefreshRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
) -> dict[str, Any]:
    """强制刷新某 SVN 数据源缓存（绕过 TTL）。"""
    _require_source_project(ctx)
    if payload.source.type != "svn":
        raise HTTPException(status_code=400, detail="仅支持 SVN 数据源刷新。")

    locator = (payload.source.pathOrUrl or payload.source.path or "").strip()
    if not is_remote_svn_locator(locator):
        raise HTTPException(
            status_code=400,
            detail="该数据源的 path/pathOrUrl 不是远端 HTTP URL，无需刷新缓存。",
        )

    try:
        cached_path = prepare_remote_svn_source(
            payload.source,
            user_scope=ctx.user.username,
            force_refresh=True,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    state = get_remote_cache_state(locator)
    return {
        "code": 200,
        "msg": "ok",
        "data": {
            "source_id": payload.source.id,
            "cached_path": str(cached_path),
            "host": state["host"],
            "revision": state["revision"],
            "last_updated_at": state["last_updated_at"],
        },
    }
