"""Source Evidence runtime capability status aggregation."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.credentials import sanitize_ai_error
from backend.app.models import (
    ProjectSourceEvidenceSvnRootRecord,
    ProjectSvnCredentialRecord,
    ProjectVisionAiCredentialRecord,
)
from backend.app.security.crypto import decrypt_secret
from backend.app.test_cases.schemas import (
    GenerationWarning,
    SourceEvidenceCapabilityItem,
    SourceEvidenceCapabilityStatusResponse,
)
from backend.config import settings


_WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"']+")
_UNIX_PATH_RE = re.compile(r"(?<!\w)/(?:[^\s\"']+/){1,}[^\s\"']*")


@dataclass(frozen=True)
class _SofficeDetection:
    configured: bool
    available: bool
    status: str
    message: str
    summary: str


async def build_source_evidence_capability_status(
    db: AsyncSession,
    *,
    project_id: int,
    is_project_admin: bool,
) -> SourceEvidenceCapabilityStatusResponse:
    """Return current project Source Evidence runtime capability status."""

    svn_credential = await _load_svn_credential_status(db, project_id)
    svn_roots = await _load_source_evidence_svn_root_status(db, project_id)
    vision_ai = await _load_vision_ai_status(db, project_id)
    soffice = _detect_soffice_status()

    items = [
        _capability_item(
            key="svn_credential",
            label="项目级 SVN 凭据",
            configured=svn_credential["configured"],
            available=svn_credential["available"],
            status=svn_credential["status"],
            available_message="项目级 SVN 凭据已配置。",
            unavailable_message="当前未配置项目级 SVN 凭据，SVN 文件 Source Evidence 不可用。",
            member_action="请联系项目管理员配置项目级 SVN 凭据。",
            admin_action="请前往管理后台配置项目级 SVN 凭据。",
            is_project_admin=is_project_admin,
        ),
        _capability_item(
            key="source_evidence_svn_roots",
            label="Source Evidence SVN Root",
            configured=svn_roots["configured"],
            available=svn_roots["available"],
            status=svn_roots["status"],
            available_message="Source Evidence SVN Root 已配置。",
            unavailable_message="当前未配置 Source Evidence SVN Root，SVN 文件 Source Evidence 不可用。",
            member_action="请联系项目管理员配置 Source Evidence SVN Root。",
            admin_action="请前往管理后台配置 Source Evidence SVN Root。",
            is_project_admin=is_project_admin,
        ),
        _capability_item(
            key="vision_ai",
            label="Vision AI",
            configured=vision_ai["configured"],
            available=vision_ai["available"],
            status=vision_ai["status"],
            available_message="项目级视觉模型已配置。",
            unavailable_message="当前未配置视觉模型，图片不会参与语义理解。",
            member_action="请联系项目管理员配置 Project Vision AI Credential。",
            admin_action="请前往管理后台配置 Project Vision AI Credential。",
            is_project_admin=is_project_admin,
        ),
        _capability_item(
            key="soffice",
            label="LibreOffice/soffice",
            configured=soffice.configured,
            available=soffice.available,
            status=soffice.status,
            available_message=soffice.message if soffice.available else "",
            unavailable_message=soffice.message,
            member_action="请联系项目管理员配置 SOURCE_EVIDENCE_SOFFICE_EXECUTABLE。",
            admin_action="请在服务端配置 SOURCE_EVIDENCE_SOFFICE_EXECUTABLE。",
            is_project_admin=is_project_admin,
        ),
    ]

    warnings = [
        GenerationWarning(
            source="source_evidence_capabilities",
            level=item.level,
            message=f"{item.message}{(' ' + item.action) if item.action else ''}",
        )
        for item in items
        if not item.available
    ]

    admin_details: dict[str, Any] | None = None
    if is_project_admin:
        admin_details = {
            "config_entry": "/admin",
            "enabled_source_evidence_svn_root_count": svn_roots["enabled_count"],
            "source_evidence_svn_root_count": svn_roots["total_count"],
            "vision_ai_last_test_status": vision_ai["last_test_status"],
            "vision_ai_last_test_at": vision_ai["last_test_at"],
            "vision_ai_last_test_error_summary": vision_ai["last_test_error_summary"],
            "soffice_detection_summary": soffice.summary,
        }

    return SourceEvidenceCapabilityStatusResponse(
        svn_credential_configured=bool(svn_credential["available"]),
        source_evidence_svn_roots_configured=bool(svn_roots["available"]),
        vision_ai_configured=bool(vision_ai["available"]),
        soffice_configured=soffice.configured,
        soffice_available=soffice.available,
        is_project_admin=is_project_admin,
        items=items,
        warnings=warnings,
        admin_details=admin_details,
    )


async def _load_svn_credential_status(
    db: AsyncSession,
    project_id: int,
) -> dict[str, Any]:
    result = await db.execute(
        select(ProjectSvnCredentialRecord).where(
            ProjectSvnCredentialRecord.project_id == project_id
        )
    )
    record = result.scalar_one_or_none()
    if record is None or not record.password_cipher:
        return {"configured": False, "available": False, "status": "missing"}
    try:
        password = decrypt_secret(record.password_cipher)
    except ValueError:
        return {"configured": True, "available": False, "status": "invalid"}
    username = (record.username or "").strip()
    if not username or not password:
        return {"configured": bool(username or password), "available": False, "status": "incomplete"}
    return {"configured": True, "available": True, "status": "available"}


async def _load_source_evidence_svn_root_status(
    db: AsyncSession,
    project_id: int,
) -> dict[str, Any]:
    total_result = await db.execute(
        select(func.count(ProjectSourceEvidenceSvnRootRecord.id)).where(
            ProjectSourceEvidenceSvnRootRecord.project_id == project_id
        )
    )
    enabled_result = await db.execute(
        select(func.count(ProjectSourceEvidenceSvnRootRecord.id)).where(
            ProjectSourceEvidenceSvnRootRecord.project_id == project_id,
            ProjectSourceEvidenceSvnRootRecord.status == "enabled",
        )
    )
    total_count = int(total_result.scalar_one() or 0)
    enabled_count = int(enabled_result.scalar_one() or 0)
    return {
        "configured": total_count > 0,
        "available": enabled_count > 0,
        "status": "available" if enabled_count > 0 else "missing",
        "total_count": total_count,
        "enabled_count": enabled_count,
    }


async def _load_vision_ai_status(
    db: AsyncSession,
    project_id: int,
) -> dict[str, Any]:
    result = await db.execute(
        select(ProjectVisionAiCredentialRecord).where(
            ProjectVisionAiCredentialRecord.project_id == project_id
        )
    )
    record = result.scalar_one_or_none()
    if record is None or not record.encrypted_api_key:
        return _vision_ai_status(configured=False, available=False, status="missing")
    try:
        api_key = decrypt_secret(record.encrypted_api_key)
    except ValueError:
        return _vision_ai_status(
            configured=True,
            available=False,
            status="invalid",
            record=record,
            error_summary="项目级 Vision AI API Key 无法解密，请重新保存。",
        )
    if not api_key or not record.enabled:
        return _vision_ai_status(configured=True, available=False, status="disabled", record=record)
    return _vision_ai_status(configured=True, available=True, status="available", record=record)


def _vision_ai_status(
    *,
    configured: bool,
    available: bool,
    status: str,
    record: ProjectVisionAiCredentialRecord | None = None,
    error_summary: str | None = None,
) -> dict[str, Any]:
    last_test_status = record.last_test_status if record is not None else ""
    raw_summary = error_summary
    if raw_summary is None and record is not None and last_test_status != "success":
        raw_summary = record.last_test_error_summary or ""
    clean_summary = (
        _sanitize_status_text(sanitize_ai_error(raw_summary))
        if raw_summary
        else ""
    )
    return {
        "configured": configured,
        "available": available,
        "status": status,
        "last_test_status": last_test_status,
        "last_test_at": record.last_test_at.isoformat() if record is not None and record.last_test_at else None,
        "last_test_error_summary": clean_summary,
    }


def _detect_soffice_status() -> _SofficeDetection:
    configured = _configured_soffice_value()
    if not configured:
        message = "未配置 LibreOffice/soffice，.xls 图片不会参与语义理解。"
        return _SofficeDetection(
            configured=False,
            available=False,
            status="missing",
            message=message,
            summary=message,
        )

    executable = _resolve_soffice_executable(configured)
    if executable is None:
        message = "已配置 LibreOffice/soffice，但服务端无法找到可执行文件。"
        return _SofficeDetection(
            configured=True,
            available=False,
            status="not_found",
            message=message,
            summary=message,
        )

    timeout = min(max(1, int(settings.source_evidence_xls_convert_timeout_seconds)), 10)
    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        message = f"LibreOffice/soffice 检测超时（>{timeout}s），.xls 图片不会参与语义理解。"
        return _SofficeDetection(
            configured=True,
            available=False,
            status="timeout",
            message=message,
            summary=message,
        )
    except OSError:
        message = "LibreOffice/soffice 检测失败，服务端无法执行已配置的转换器。"
        return _SofficeDetection(
            configured=True,
            available=False,
            status="failed",
            message=message,
            summary=message,
        )

    output = _first_status_line(completed.stdout or completed.stderr)
    if completed.returncode != 0:
        suffix = f"：{output}" if output else f"：退出码 {completed.returncode}"
        message = f"LibreOffice/soffice 检测失败{_sanitize_status_text(suffix)}，.xls 图片不会参与语义理解。"
        return _SofficeDetection(
            configured=True,
            available=False,
            status="failed",
            message=message,
            summary=message,
        )

    version = _sanitize_status_text(output or "版本信息不可用")
    message = f"LibreOffice/soffice 可用：{version}"
    return _SofficeDetection(
        configured=True,
        available=True,
        status="available",
        message=message,
        summary=message,
    )


def _capability_item(
    *,
    key: str,
    label: str,
    configured: bool,
    available: bool,
    status: str,
    available_message: str,
    unavailable_message: str,
    member_action: str,
    admin_action: str,
    is_project_admin: bool,
) -> SourceEvidenceCapabilityItem:
    message = available_message if available else unavailable_message
    action = "" if available else (admin_action if is_project_admin else member_action)
    return SourceEvidenceCapabilityItem(
        key=key,
        label=label,
        configured=configured,
        available=available,
        status=status,
        message=message,
        action=action,
        level="info" if available else "warning",
    )


def _configured_soffice_value() -> str:
    return (settings.source_evidence_soffice_executable or "").strip().strip('"').strip("'")


def _resolve_soffice_executable(configured: str) -> str | None:
    configured_path = Path(configured).expanduser()
    if configured_path.is_file():
        return str(configured_path.resolve(strict=False))
    return shutil.which(configured)


def _first_status_line(value: str) -> str:
    for line in (value or "").replace("\r", "\n").split("\n"):
        normalized = line.strip()
        if normalized:
            return normalized[:240]
    return ""


def _sanitize_status_text(value: str) -> str:
    safe = value or ""
    safe = _WINDOWS_PATH_RE.sub("[本地路径已脱敏]", safe)
    safe = _UNIX_PATH_RE.sub("[本地路径已脱敏]", safe)
    safe = safe.replace("--version", "[检测参数已脱敏]")
    return safe[:500]
