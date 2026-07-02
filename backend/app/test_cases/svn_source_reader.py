"""SVN file reader adapter for Source Evidence runs."""

from __future__ import annotations

import datetime
import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.loaders.svn_credentials import SvnCredential
from backend.app.loaders.svn_manager import (
    SvnRemoteError,
    checkout_remote_directory,
    enforce_host_allowlist,
    get_remote_revision,
    list_svn_directory,
    normalize_dir_url,
    split_remote_url,
)
from backend.app.models import (
    ProjectSourceEvidenceSvnRootRecord,
    ProjectSvnCredentialRecord,
    SourceEvidenceRunRecord,
)
from backend.app.security.crypto import decrypt_secret
from backend.app.test_cases import source_evidence_storage
from backend.app.test_cases.local_source_reader import SUPPORTED_LOCAL_SOURCE_SUFFIXES


def _source_evidence_error(status_code: int, message: str) -> Exception:
    from backend.app.test_cases.source_evidence import SourceEvidenceError

    return SourceEvidenceError(status_code, message)


async def prepare_svn_source_evidence_file(
    db: AsyncSession,
    run: SourceEvidenceRunRecord,
) -> dict[str, Any]:
    """Fetch a project-approved SVN file into the current run directory."""
    source_url = (run.source_url or "").strip()
    normalized_url, dir_url, file_name, host = _validate_svn_file_url(source_url)
    root = await _resolve_source_evidence_svn_root(db, run.project_id, normalized_url)
    credential, password = await _load_project_svn_credential(db, run.project_id, host)

    try:
        listing = list_svn_directory(dir_url, credentials=credential)
    except SvnRemoteError as exc:
        raise _map_svn_remote_error(exc, password=password) from exc
    entry = _find_file_entry(listing.get("entries", []), file_name)
    if entry is None:
        raise _source_evidence_error(404, f"SVN 文件不存在：{file_name}")

    checkout_relative_dir = f"raw/svn-cache/{_url_digest(dir_url)}"
    checkout_dir = source_evidence_storage.resolve_source_evidence_path(
        run.project_id,
        run.id,
        checkout_relative_dir,
    )
    try:
        checkout_remote_directory(
            dir_url=dir_url,
            target_dir=checkout_dir,
            credentials=credential,
            depth="files",
        )
    except SvnRemoteError as exc:
        raise _map_svn_remote_error(exc, password=password) from exc
    except NotImplementedError as exc:
        raise _source_evidence_error(400, str(exc)) from exc

    target_file = (checkout_dir / file_name).resolve(strict=False)
    try:
        target_file.relative_to(checkout_dir.resolve(strict=False))
    except ValueError as exc:
        raise _source_evidence_error(400, "SVN 文件路径非法。") from exc
    if not target_file.is_file():
        raise _source_evidence_error(404, f"SVN 文件不存在：{file_name}")

    file_bytes = target_file.read_bytes()
    file_sha256 = hashlib.sha256(file_bytes).hexdigest()
    try:
        revision = get_remote_revision(checkout_dir, credentials=credential)
    except Exception:  # noqa: BLE001 - revision 是审计增强信息，失败不阻塞读取
        revision = None

    upload = {
        "relative_path": f"{checkout_relative_dir}/{file_name}",
        "filename": file_name,
        "size": target_file.stat().st_size,
        "sha256": file_sha256,
    }
    return {
        "upload": upload,
        "svn": {
            "url": normalized_url,
            "root_alias": root.alias,
            "root_url": root.svn_root_url,
            "host": host,
            "dir_url": dir_url,
            "filename": file_name,
            "revision": revision,
            "last_changed_rev": entry.get("revision"),
            "last_author": entry.get("last_author") or "",
            "last_modified_at": entry.get("last_modified_at") or "",
            "file_sha256": file_sha256,
            "fetched_at": datetime.datetime.now(datetime.UTC).isoformat(),
        },
    }


def _validate_svn_file_url(raw_url: str) -> tuple[str, str, str, str]:
    if not raw_url:
        raise _source_evidence_error(400, "SVN Source Evidence URL 不能为空。")
    parsed = urlsplit(raw_url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise _source_evidence_error(400, "SVN Source Evidence URL 必须以 http(s):// 开头。")
    if parsed.username or parsed.password:
        raise _source_evidence_error(400, "SVN Source Evidence URL 不允许包含用户名或密码。")
    if parsed.query or parsed.fragment:
        raise _source_evidence_error(400, "SVN Source Evidence URL 不能包含 query 或 fragment。")
    try:
        host = enforce_host_allowlist(parsed.hostname)
    except ValueError as exc:
        raise _source_evidence_error(400, str(exc)) from exc

    normalized_url = urlunsplit((parsed.scheme.lower(), parsed.netloc, parsed.path, "", ""))
    dir_url, file_name = split_remote_url(normalized_url)
    if not file_name or file_name in {".", ".."} or Path(file_name).name != file_name:
        raise _source_evidence_error(400, "SVN Source Evidence URL 必须指向具体文件。")
    suffix = Path(file_name).suffix.lower()
    if suffix not in SUPPORTED_LOCAL_SOURCE_SUFFIXES:
        raise _source_evidence_error(
            400,
            f"不支持的 SVN Source Evidence 文件类型：{suffix or '无后缀'}。",
        )
    return normalized_url, dir_url, file_name, host


async def _resolve_source_evidence_svn_root(
    db: AsyncSession,
    project_id: int,
    file_url: str,
) -> ProjectSourceEvidenceSvnRootRecord:
    result = await db.execute(
        select(ProjectSourceEvidenceSvnRootRecord)
        .where(
            ProjectSourceEvidenceSvnRootRecord.project_id == project_id,
            ProjectSourceEvidenceSvnRootRecord.status == "enabled",
        )
        .order_by(ProjectSourceEvidenceSvnRootRecord.id)
    )
    roots = list(result.scalars().all())
    if not roots:
        raise _source_evidence_error(400, "请先配置并启用 Source Evidence SVN Root。")
    for root in roots:
        if _is_url_under_root(file_url, root.svn_root_url):
            return root
    raise _source_evidence_error(400, "SVN URL 超出 Source Evidence SVN Root。")


def _is_url_under_root(file_url: str, root_url: str) -> bool:
    try:
        normalized_root = normalize_dir_url(root_url)
    except ValueError:
        return False
    file_parsed = urlparse(file_url)
    root_parsed = urlparse(normalized_root)
    if file_parsed.scheme.lower() != root_parsed.scheme.lower():
        return False
    if (file_parsed.hostname or "").lower() != (root_parsed.hostname or "").lower():
        return False
    if file_parsed.port != root_parsed.port:
        return False
    root_path = root_parsed.path if root_parsed.path.endswith("/") else f"{root_parsed.path}/"
    return file_parsed.path.startswith(root_path)


async def _load_project_svn_credential(
    db: AsyncSession,
    project_id: int,
    host: str,
) -> tuple[SvnCredential, str]:
    result = await db.execute(
        select(ProjectSvnCredentialRecord).where(
            ProjectSvnCredentialRecord.project_id == project_id
        )
    )
    record = result.scalar_one_or_none()
    if record is None or not record.password_cipher:
        raise _source_evidence_error(400, "请先配置项目级 SVN 凭据后再读取 SVN Source Evidence。")
    try:
        password = decrypt_secret(record.password_cipher)
    except ValueError as exc:
        raise _source_evidence_error(400, "项目级 SVN 凭据无法解密，请重新保存后再读取。") from exc
    username = (record.username or "").strip()
    if not username or not password:
        raise _source_evidence_error(400, "请先配置项目级 SVN 凭据后再读取 SVN Source Evidence。")
    return (
        SvnCredential(
            host=host,
            username=username,
            password=password,
            updated_at=record.updated_at.isoformat() if record.updated_at else None,
        ),
        password,
    )


def _find_file_entry(entries: Any, file_name: str) -> dict[str, Any] | None:
    if not isinstance(entries, list):
        return None
    for item in entries:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "file" and item.get("name") == file_name:
            return item
    return None


def _map_svn_remote_error(error: SvnRemoteError, *, password: str) -> Exception:
    message = _sanitize_svn_error_message(error.message, password=password)
    if error.category == "auth_failed":
        return _source_evidence_error(403, "SVN 鉴权失败：请检查项目级 SVN 凭据或该账号权限。")
    if error.category == "not_found":
        return _source_evidence_error(404, "SVN 文件不存在或当前账号无权访问。")
    if error.category == "timeout":
        return _source_evidence_error(504, message or "SVN 读取超时，请稍后重试。")
    if error.category == "network":
        return _source_evidence_error(502, message or "无法连接 SVN 服务器，请检查网络与 URL。")
    return _source_evidence_error(400, message or "SVN 文件读取失败。")


def _sanitize_svn_error_message(message: str, *, password: str) -> str:
    safe_message = (message or "SVN 文件读取失败。").strip()
    if password:
        safe_message = safe_message.replace(password, "******")
    return safe_message.replace("\r", " ").replace("\n", " ")[:300]


def _url_digest(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
