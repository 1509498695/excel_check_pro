"""Source Evidence 飞书授权闭环 service。

只负责后端授权状态、发卡和 OAuth callback，不读取/重试 Source Evidence Run。
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime
import hashlib
import html
import json
import re
import secrets
from typing import Any
from urllib.parse import quote, urlencode

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.integrations.feishu_bot import (
    FeishuApiError,
    send_card_to_chat,
    send_card_to_open_id,
)
from backend.app.integrations.feishu_client import (
    FEISHU_METADATA_UNAVAILABLE,
    FeishuClientError,
    FeishuDriveMetadata,
    add_source_document_collaborator,
    exchange_oauth_code_for_user_token,
    feishu_json_request,
    get_current_bot_open_id,
    get_drive_metadata,
    get_oauth_user_info,
    resolve_source_evidence_wiki_node,
)
from backend.app.models import (
    FeishuBotConfigRecord,
    Project,
    SourceEvidenceAuthorizationRecord,
    SourceEvidenceResourceRecord,
    SourceEvidenceRunRecord,
)
from backend.app.test_cases.feishu_source_parser import (
    FeishuSourceUrlError,
    parse_feishu_source_url,
)
from backend.app.test_cases.schemas import (
    SourceEvidenceAuthorizationAuditItem,
    SourceEvidenceAuthorizationRequestResponse,
)
from backend.app.test_cases.source_evidence import (
    SourceEvidenceError,
    is_source_evidence_expired,
    source_evidence_now,
)
from backend.config import settings


AUTHORIZATION_PERMISSION = "edit"
AUTHORIZATION_STATE_TTL_SECONDS = 10 * 60
MAX_DIRECT_TARGETS = 3

STATUS_AUTHORIZATION_SENT = "authorization_sent"
STATUS_AUTHORIZED = "authorized"
STATUS_PENDING_VERIFICATION = "pending_verification"
STATUS_AUTHORIZATION_FAILED = "authorization_failed"
STATUS_EXPIRED = "expired"
STATUS_INVALIDATED = "invalidated"

REQUEST_ALREADY_READABLE = "already_readable"
REQUEST_ALREADY_SENT = "already_sent"
REQUEST_ALREADY_AUTHORIZED = "already_authorized"
REQUEST_AUTHORIZATION_SENT = "authorization_sent"
REQUEST_SEND_FAILED = "send_failed"
REQUEST_BOT_NOT_CONFIGURED = "bot_not_configured"
REQUEST_EXPIRED_OR_CLEANED = "expired_or_cleaned"
REQUEST_INVALID_RUN_STATE = "invalid_run_state"

TARGET_NOT_SENT = "not_sent"
TARGET_OWNER_DIRECT = "owner_direct"
TARGET_CREATOR_DIRECT = "creator_direct"
TARGET_DEFAULT_CHAT = "default_chat"

PERMISSION_FAILURE_DOWNLOAD_STATUSES = {"pending_permission", "download_failed"}
RUN_AUTHORIZATION_STATUSES = {"pending_permission", "failed"}


@dataclass(frozen=True)
class AuthorizationSource:
    """授权闭环内使用的真实源对象，不暴露给 API。"""

    token: str
    doc_type: str
    title: str
    alias_hashes_json: str
    alias_fingerprints: list[str]


@dataclass(frozen=True)
class CallbackResult:
    """OAuth callback 页面渲染结果。"""

    ok: bool
    title: str
    message: str


@dataclass(frozen=True)
class SendAttempt:
    """一次发卡尝试的聚合结果。"""

    success: bool
    target_mode: str
    sent_count: int
    failed_count: int
    fallback_to_default_chat: bool
    last_error: str = ""


def hash_source_token(value: str) -> str:
    """返回源 token/state 的稳定 SHA-256 哈希。"""
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def hash_authorization_state(value: str) -> str:
    """返回 OAuth state 哈希；DB 只保存该值。"""
    return hash_source_token(value)


def source_fingerprint(source_hash: str) -> str:
    """审计展示用短指纹，不可还原源 token。"""
    normalized = (source_hash or "").strip()
    return f"sha256:{normalized[:12]}" if normalized else ""


async def request_source_evidence_authorization(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    requested_by: str,
    callback_url: str,
) -> SourceEvidenceAuthorizationRequestResponse:
    """按 Source Evidence Run 显式发起飞书源文档授权请求。"""
    run = await _load_run_without_cleanup(db, project_id=project_id, run_id=run_id)
    now = source_evidence_now()
    if _run_is_cleaned_or_expired(run, now=now):
        return _request_response(
            status=REQUEST_EXPIRED_OR_CLEANED,
            message="证据已过期，请重新读取来源并重新申请授权。",
        )

    resources = await _load_run_resources(db, project_id=project_id, run_id=run.id)
    if not _run_needs_authorization(run, resources):
        return _request_response(
            status=REQUEST_ALREADY_READABLE,
            message="当前 Source Evidence Run 已可读取，无需发送授权卡。",
            can_retry_read=False,
        )

    if not run.source_url.strip():
        return _request_response(
            status=REQUEST_INVALID_RUN_STATE,
            message="Source Evidence Run 缺少来源 URL，无法发起授权。",
        )

    bot_config = await _load_bot_config(db, project_id=project_id)
    if bot_config is None:
        return _request_response(
            status=REQUEST_BOT_NOT_CONFIGURED,
            message="项目未配置飞书应用，无法发送授权卡。",
        )

    try:
        source = await _resolve_authorization_source(db, project_id=project_id, run=run)
    except Exception as exc:
        return await _record_send_failure(
            db,
            project_id=project_id,
            run=run,
            bot_config=bot_config,
            error_message=sanitize_authorization_error(str(exc)),
        )

    source_hash = hash_source_token(source.token)
    existing = await _find_authorization_record(
        db,
        project_id=project_id,
        app_id=bot_config.app_id,
        source_hash=source_hash,
    )
    if _authorization_is_reusable(existing, now=now):
        return _request_response(
            status=REQUEST_ALREADY_AUTHORIZED,
            message="该源文档授权仍在有效期内，可回到用例生成页面重试读取。",
            authorization_id=existing.id,
            target_mode=existing.target_mode,
            sent_targets_count=existing.sent_targets_count,
            failed_targets_count=existing.failed_targets_count,
            owner_candidates_truncated=existing.owner_candidates_truncated,
            expires_at=_datetime_to_iso(existing.expires_at),
            can_retry_read=True,
        )
    if _authorization_sent_is_active(existing, now=now):
        return _request_response(
            status=REQUEST_ALREADY_SENT,
            message="该源文档已有未过期的授权卡，不重复发送。",
            authorization_id=existing.id,
            target_mode=existing.target_mode,
            sent_targets_count=existing.sent_targets_count,
            failed_targets_count=existing.failed_targets_count,
            fallback_to_default_chat=existing.target_mode == TARGET_DEFAULT_CHAT,
            owner_candidates_truncated=existing.owner_candidates_truncated,
            expires_at=_datetime_to_iso(existing.state_expires_at),
        )

    state = secrets.token_urlsafe(32)
    oauth_url = _build_source_evidence_oauth_url(
        app_id=bot_config.app_id,
        callback_url=callback_url,
        state=state,
    )
    metadata = await _load_metadata_best_effort(
        db,
        project_id=project_id,
        source=source,
    )
    card = _build_authorization_card(
        project_name=await _project_name(db, project_id=project_id),
        run=run,
        source=source,
        metadata=metadata,
        requested_by=requested_by,
        oauth_url=oauth_url,
    )
    send_attempt = await _send_authorization_card(
        db,
        project_id=project_id,
        bot_config=bot_config,
        metadata=metadata,
        card=card,
    )
    if not send_attempt.success:
        record = await _upsert_authorization_record(
            db,
            project_id=project_id,
            run=run,
            bot_config=bot_config,
            source=source,
            source_hash=source_hash,
            now=now,
        )
        _mark_record_send_failed(record, send_attempt)
        await db.flush()
        return _request_response(
            status=REQUEST_SEND_FAILED,
            message=record.last_error_summary or "授权卡发送失败。",
            authorization_id=record.id,
            target_mode=record.target_mode,
            sent_targets_count=record.sent_targets_count,
            failed_targets_count=record.failed_targets_count,
            fallback_to_default_chat=record.target_mode == TARGET_DEFAULT_CHAT,
            owner_candidates_truncated=record.owner_candidates_truncated,
        )

    record = await _upsert_authorization_record(
        db,
        project_id=project_id,
        run=run,
        bot_config=bot_config,
        source=source,
        source_hash=source_hash,
        now=now,
    )
    record.status = STATUS_AUTHORIZATION_SENT
    record.state_hash = hash_authorization_state(state)
    record.state_expires_at = now + datetime.timedelta(seconds=AUTHORIZATION_STATE_TTL_SECONDS)
    record.originating_run_id = run.id
    record.target_mode = send_attempt.target_mode
    record.sent_targets_count = send_attempt.sent_count
    record.failed_targets_count = send_attempt.failed_count
    record.owner_candidates_truncated = bool(
        metadata is not None and len(metadata.owner_ids) > MAX_DIRECT_TARGETS
    )
    record.authorized_by_open_id = ""
    record.authorized_by_display_name_masked = ""
    record.authorized_at = None
    record.invalidated_at = None
    record.invalidated_by = None
    record.last_error_summary = ""
    await db.flush()
    return _request_response(
        status=REQUEST_AUTHORIZATION_SENT,
        message="授权卡已发送。",
        authorization_id=record.id,
        target_mode=record.target_mode,
        sent_targets_count=record.sent_targets_count,
        failed_targets_count=record.failed_targets_count,
        fallback_to_default_chat=record.target_mode == TARGET_DEFAULT_CHAT,
        owner_candidates_truncated=record.owner_candidates_truncated,
        expires_at=_datetime_to_iso(record.state_expires_at),
    )


async def find_reusable_source_evidence_authorization_for_run(
    db: AsyncSession,
    *,
    project_id: int,
    run: SourceEvidenceRunRecord,
) -> SourceEvidenceAuthorizationRecord | None:
    """查找当前 run 可复用的 Source Evidence edit 授权记录。

    该 helper 只做查询，不发卡、不创建记录；解析失败时返回 None，让调用方按
    既有 retry/read 流程继续尝试真实读取。
    """
    bot_config = await _load_bot_config(db, project_id=project_id)
    if bot_config is None:
        return None
    if _run_is_cleaned_or_expired(run, now=source_evidence_now()):
        return None
    try:
        source = await _resolve_authorization_source(
            db,
            project_id=project_id,
            run=run,
        )
    except Exception:
        return None
    record = await _find_authorization_record(
        db,
        project_id=project_id,
        app_id=bot_config.app_id,
        source_hash=hash_source_token(source.token),
    )
    if _authorization_is_reusable(record, now=source_evidence_now()):
        return record
    return None


async def handle_source_evidence_oauth_callback(
    db: AsyncSession,
    *,
    code: str,
    state: str,
    callback_url: str,
) -> CallbackResult:
    """处理 Source Evidence 专用 OAuth callback，不依赖系统登录态。"""
    normalized_state = (state or "").strip()
    normalized_code = (code or "").strip()
    if not normalized_state or not normalized_code:
        return CallbackResult(
            ok=False,
            title="授权失败",
            message="授权回调缺少必要参数，请重新发起授权。",
        )

    record = await _find_record_by_state(db, state=normalized_state)
    if record is None:
        return CallbackResult(
            ok=False,
            title="授权失败",
            message="授权请求不存在或已失效，请重新发起授权。",
        )

    now = source_evidence_now()
    if not _state_is_active(record, now=now):
        _mark_callback_failure(record, STATUS_EXPIRED, "授权链接已过期，请重新发起授权。")
        await db.flush()
        return CallbackResult(
            ok=False,
            title="授权链接已过期",
            message="授权链接已过期，请重新发起授权。",
        )

    run = await _load_run_by_record(db, record)
    if run is None or _run_is_cleaned_or_expired(run, now=now):
        _mark_callback_failure(
            record,
            STATUS_EXPIRED,
            "证据已过期，请重新读取来源并重新申请授权。",
        )
        await db.flush()
        return CallbackResult(
            ok=False,
            title="证据已过期",
            message="证据已过期，请重新读取来源并重新申请授权。",
        )

    try:
        source = await _resolve_authorization_source(db, project_id=record.project_id, run=run)
        user_access_token = await exchange_oauth_code_for_user_token(
            db,
            record.project_id,
            normalized_code,
            callback_url,
        )
        user_info = await get_oauth_user_info(user_access_token)
        bot_open_id = await get_current_bot_open_id(db, record.project_id)
        await add_source_document_collaborator(
            user_access_token,
            source.token,
            bot_open_id,
            source.doc_type,
            perm=record.permission or AUTHORIZATION_PERMISSION,
        )
    except Exception as exc:
        error_summary = sanitize_authorization_error(
            str(exc),
            secrets=[normalized_code, run.source_url, run.source_token],
        )
        record.state_hash = None
        record.state_expires_at = None
        record.status = STATUS_AUTHORIZATION_FAILED
        record.last_error_summary = error_summary
        await db.flush()
        return CallbackResult(
            ok=False,
            title="授权未完成",
            message=f"授权未完成：{html.escape(error_summary)}",
        )

    try:
        await _verify_source_readable(db, project_id=record.project_id, source=source)
    except Exception as exc:
        error_summary = sanitize_authorization_error(
            str(exc),
            secrets=[normalized_code, run.source_url, run.source_token],
        )
        record.state_hash = None
        record.state_expires_at = None
        record.status = STATUS_PENDING_VERIFICATION
        record.last_error_summary = error_summary
        await db.flush()
        return CallbackResult(
            ok=False,
            title="授权待校验",
            message=f"授权已提交，但轻量读取校验未通过：{html.escape(error_summary)}",
        )

    record.status = STATUS_AUTHORIZED
    record.state_hash = None
    record.state_expires_at = None
    record.authorized_by_open_id = user_info.open_id
    record.authorized_at = now
    record.expires_at = _authorization_expires_at(now)
    record.last_error_summary = ""
    await db.flush()
    return CallbackResult(
        ok=True,
        title="授权已完成",
        message="授权已完成，请回到用例生成页面点击重试读取。",
    )


async def list_source_evidence_authorizations(
    db: AsyncSession,
    *,
    project_id: int,
    limit: int,
    offset: int,
) -> tuple[list[SourceEvidenceAuthorizationAuditItem], int]:
    """列出项目 Source Evidence 授权审计摘要。"""
    total_result = await db.execute(
        select(func.count())
        .select_from(SourceEvidenceAuthorizationRecord)
        .where(SourceEvidenceAuthorizationRecord.project_id == project_id)
    )
    total = int(total_result.scalar_one() or 0)
    result = await db.execute(
        select(SourceEvidenceAuthorizationRecord)
        .where(SourceEvidenceAuthorizationRecord.project_id == project_id)
        .order_by(
            SourceEvidenceAuthorizationRecord.updated_at.desc(),
            SourceEvidenceAuthorizationRecord.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    records = list(result.scalars().all())
    return [_audit_item(record) for record in records], total


async def invalidate_source_evidence_authorization(
    db: AsyncSession,
    *,
    project_id: int,
    authorization_id: int,
    invalidated_by: int | None,
) -> SourceEvidenceAuthorizationAuditItem:
    """手动标记本系统授权复用失效，不调用飞书移除协作者。"""
    result = await db.execute(
        select(SourceEvidenceAuthorizationRecord).where(
            SourceEvidenceAuthorizationRecord.id == authorization_id,
            SourceEvidenceAuthorizationRecord.project_id == project_id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise SourceEvidenceError(404, "Source Evidence 授权记录不存在。")
    record.status = STATUS_INVALIDATED
    record.state_hash = None
    record.state_expires_at = None
    record.invalidated_at = source_evidence_now()
    record.invalidated_by = invalidated_by
    await db.flush()
    await db.refresh(record)
    return _audit_item(record)


def render_callback_html(result: CallbackResult) -> str:
    """生成简洁 callback 页面。"""
    title = html.escape(result.title)
    message = html.escape(result.message)
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{title}</title></head><body>"
        f"<h1>{title}</h1><p>{message}</p>"
        "</body></html>"
    )


def sanitize_authorization_error(message: str, *, secrets: list[str] | None = None) -> str:
    """脱敏 OAuth/飞书错误，不泄露 token、code 或 Authorization。"""
    sanitized = str(message or "")
    for raw_secret in secrets or []:
        value = str(raw_secret or "").strip()
        if value:
            sanitized = sanitized.replace(value, "[REDACTED]")
    sanitized = re.sub(
        r"(?i)([\"']?\b(?:app_secret|tenant_access_token|user_access_token|code)[\"']?\s*[:=]\s*[\"']?)[^,\"'}\s]+",
        r"\1[REDACTED]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)(\b(?:oauth[\s_-]*code|authorization[\s_-]*code|auth[\s_-]*code)\s*[:=]\s*[\"']?)[^,\"'}\s]+",
        r"\1[REDACTED]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)\bAuthorization\s*[:=]\s*Bearer\s+[^,\s]+",
        "Authorization=[REDACTED]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)\bAuthorization\s*[:=]\s*[^,\s]+",
        "Authorization=[REDACTED]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)\bBearer\s+[^,\s]+",
        "Bearer [REDACTED]",
        sanitized,
    )
    for marker in (
        "app_secret",
        "tenant_access_token",
        "user_access_token",
        "authorization",
        "Authorization",
        "bearer",
        "Bearer",
        "oauth_code",
        "authorization_code",
        "auth_code",
        "oauth code",
        "OAuth code",
    ):
        sanitized = sanitized.replace(marker, "[REDACTED]")
    return sanitized[:500]


async def _load_run_without_cleanup(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> SourceEvidenceRunRecord:
    result = await db.execute(
        select(SourceEvidenceRunRecord).where(
            SourceEvidenceRunRecord.id == run_id,
            SourceEvidenceRunRecord.project_id == project_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise SourceEvidenceError(404, "Source Evidence Run 不存在。")
    return run


async def _load_run_by_record(
    db: AsyncSession,
    record: SourceEvidenceAuthorizationRecord,
) -> SourceEvidenceRunRecord | None:
    if record.originating_run_id is None:
        return None
    result = await db.execute(
        select(SourceEvidenceRunRecord).where(
            SourceEvidenceRunRecord.id == record.originating_run_id,
            SourceEvidenceRunRecord.project_id == record.project_id,
        )
    )
    return result.scalar_one_or_none()


async def _load_run_resources(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> list[SourceEvidenceResourceRecord]:
    result = await db.execute(
        select(SourceEvidenceResourceRecord).where(
            SourceEvidenceResourceRecord.project_id == project_id,
            SourceEvidenceResourceRecord.run_id == run_id,
        )
    )
    return list(result.scalars().all())


def _run_is_cleaned_or_expired(
    run: SourceEvidenceRunRecord,
    *,
    now: datetime.datetime,
) -> bool:
    return run.status in {"cleaned", "expired"} or is_source_evidence_expired(run, now=now)


def _run_needs_authorization(
    run: SourceEvidenceRunRecord,
    resources: list[SourceEvidenceResourceRecord],
) -> bool:
    if run.status in RUN_AUTHORIZATION_STATUSES:
        return True
    return any(
        resource.download_status in PERMISSION_FAILURE_DOWNLOAD_STATUSES
        for resource in resources
    )


async def _load_bot_config(
    db: AsyncSession,
    *,
    project_id: int,
) -> FeishuBotConfigRecord | None:
    result = await db.execute(
        select(FeishuBotConfigRecord).where(FeishuBotConfigRecord.project_id == project_id)
    )
    record = result.scalar_one_or_none()
    if record is None or not record.app_id.strip() or not record.app_secret_cipher.strip():
        return None
    return record


async def _resolve_authorization_source(
    db: AsyncSession,
    *,
    project_id: int,
    run: SourceEvidenceRunRecord,
) -> AuthorizationSource:
    try:
        locator = parse_feishu_source_url(run.source_url)
    except FeishuSourceUrlError as exc:
        raise SourceEvidenceError(400, exc.message) from exc

    aliases: list[dict[str, str]] = []
    token = locator.token
    doc_type = locator.doc_type
    title = run.source_title or ""
    if locator.doc_type == "wiki":
        node = await resolve_source_evidence_wiki_node(db, project_id, locator.token)
        token = node.obj_token
        doc_type = node.doc_type
        title = title or node.title
        alias_hash = hash_source_token(locator.token)
        aliases.append(
            {
                "kind": "wiki",
                "hash": alias_hash,
                "fingerprint": source_fingerprint(alias_hash),
            }
        )
    if not token.strip():
        raise SourceEvidenceError(400, "飞书源文档缺少真实 token，无法发起授权。")
    alias_fingerprints = [
        item["fingerprint"] for item in aliases if item.get("fingerprint")
    ]
    return AuthorizationSource(
        token=token,
        doc_type=doc_type,
        title=title,
        alias_hashes_json=json.dumps(aliases, ensure_ascii=False),
        alias_fingerprints=alias_fingerprints,
    )


async def _find_authorization_record(
    db: AsyncSession,
    *,
    project_id: int,
    app_id: str,
    source_hash: str,
) -> SourceEvidenceAuthorizationRecord | None:
    result = await db.execute(
        select(SourceEvidenceAuthorizationRecord).where(
            SourceEvidenceAuthorizationRecord.project_id == project_id,
            SourceEvidenceAuthorizationRecord.app_id == app_id,
            SourceEvidenceAuthorizationRecord.source_token_hash == source_hash,
            SourceEvidenceAuthorizationRecord.permission == AUTHORIZATION_PERMISSION,
        )
    )
    return result.scalar_one_or_none()


async def _find_record_by_state(
    db: AsyncSession,
    *,
    state: str,
) -> SourceEvidenceAuthorizationRecord | None:
    result = await db.execute(
        select(SourceEvidenceAuthorizationRecord).where(
            SourceEvidenceAuthorizationRecord.state_hash == hash_authorization_state(state)
        )
    )
    return result.scalar_one_or_none()


def _authorization_is_reusable(
    record: SourceEvidenceAuthorizationRecord | None,
    *,
    now: datetime.datetime,
) -> bool:
    if record is None:
        return False
    return (
        record.status == STATUS_AUTHORIZED
        and record.invalidated_at is None
        and _as_aware_utc(record.expires_at) > _as_aware_utc(now)
    )


def _authorization_sent_is_active(
    record: SourceEvidenceAuthorizationRecord | None,
    *,
    now: datetime.datetime,
) -> bool:
    if record is None:
        return False
    if record.status != STATUS_AUTHORIZATION_SENT or not record.state_hash:
        return False
    if record.state_expires_at is None:
        return False
    return _as_aware_utc(record.state_expires_at) > _as_aware_utc(now)


def _state_is_active(
    record: SourceEvidenceAuthorizationRecord,
    *,
    now: datetime.datetime,
) -> bool:
    if record.status != STATUS_AUTHORIZATION_SENT or not record.state_hash:
        return False
    if record.state_expires_at is None:
        return False
    return _as_aware_utc(record.state_expires_at) > _as_aware_utc(now)


async def _upsert_authorization_record(
    db: AsyncSession,
    *,
    project_id: int,
    run: SourceEvidenceRunRecord,
    bot_config: FeishuBotConfigRecord,
    source: AuthorizationSource,
    source_hash: str,
    now: datetime.datetime,
) -> SourceEvidenceAuthorizationRecord:
    record = await _find_authorization_record(
        db,
        project_id=project_id,
        app_id=bot_config.app_id,
        source_hash=source_hash,
    )
    if record is None:
        record = SourceEvidenceAuthorizationRecord(
            project_id=project_id,
            app_id=bot_config.app_id,
            source_token_hash=source_hash,
            permission=AUTHORIZATION_PERMISSION,
            expires_at=_authorization_expires_at(now),
        )
        db.add(record)
    record.doc_type = source.doc_type
    record.source_token_alias_hashes_json = source.alias_hashes_json
    record.originating_run_id = run.id
    record.permission = AUTHORIZATION_PERMISSION
    record.expires_at = _authorization_expires_at(now)
    return record


async def _record_send_failure(
    db: AsyncSession,
    *,
    project_id: int,
    run: SourceEvidenceRunRecord,
    bot_config: FeishuBotConfigRecord,
    error_message: str,
) -> SourceEvidenceAuthorizationRequestResponse:
    source_hash = hash_source_token(run.source_token or run.source_identifier or run.source_url)
    record = await _find_authorization_record(
        db,
        project_id=project_id,
        app_id=bot_config.app_id,
        source_hash=source_hash,
    )
    if record is None:
        record = SourceEvidenceAuthorizationRecord(
            project_id=project_id,
            app_id=bot_config.app_id,
            source_token_hash=source_hash,
            permission=AUTHORIZATION_PERMISSION,
            originating_run_id=run.id,
            expires_at=_authorization_expires_at(source_evidence_now()),
        )
        db.add(record)
    record.status = STATUS_AUTHORIZATION_FAILED
    record.state_hash = None
    record.state_expires_at = None
    record.target_mode = TARGET_NOT_SENT
    record.sent_targets_count = 0
    record.failed_targets_count = 0
    record.last_error_summary = error_message
    await db.flush()
    return _request_response(
        status=REQUEST_SEND_FAILED,
        message=error_message,
        authorization_id=record.id,
    )


async def _load_metadata_best_effort(
    db: AsyncSession,
    *,
    project_id: int,
    source: AuthorizationSource,
) -> FeishuDriveMetadata | None:
    try:
        return await get_drive_metadata(db, project_id, source.token, source.doc_type)
    except FeishuClientError as exc:
        if exc.code == FEISHU_METADATA_UNAVAILABLE:
            return None
        return None
    except Exception:
        return None


async def _send_authorization_card(
    db: AsyncSession,
    *,
    project_id: int,
    bot_config: FeishuBotConfigRecord,
    metadata: FeishuDriveMetadata | None,
    card: dict[str, Any],
) -> SendAttempt:
    owner_targets = (metadata.owner_ids if metadata is not None else [])[:MAX_DIRECT_TARGETS]
    if owner_targets:
        owner_attempt = await _send_to_open_ids(
            db,
            project_id=project_id,
            target_mode=TARGET_OWNER_DIRECT,
            open_ids=owner_targets,
            card=card,
        )
        if owner_attempt.success:
            return owner_attempt
    else:
        owner_attempt = SendAttempt(False, TARGET_OWNER_DIRECT, 0, 0, False)

    creator_targets = (metadata.creator_ids if metadata is not None else [])[:MAX_DIRECT_TARGETS]
    if creator_targets:
        creator_attempt = await _send_to_open_ids(
            db,
            project_id=project_id,
            target_mode=TARGET_CREATOR_DIRECT,
            open_ids=creator_targets,
            card=card,
        )
        if creator_attempt.success:
            return SendAttempt(
                True,
                creator_attempt.target_mode,
                creator_attempt.sent_count,
                creator_attempt.failed_count + owner_attempt.failed_count,
                False,
            )
        direct_failed_count = owner_attempt.failed_count + creator_attempt.failed_count
        last_error = creator_attempt.last_error or owner_attempt.last_error
    else:
        direct_failed_count = owner_attempt.failed_count
        last_error = owner_attempt.last_error

    default_chat_id = bot_config.default_chat_id.strip()
    if not default_chat_id:
        return SendAttempt(
            False,
            TARGET_NOT_SENT,
            0,
            direct_failed_count,
            False,
            last_error or "飞书 Drive metadata 不可用且未配置默认授权群。",
        )
    try:
        await send_card_to_chat(db, project_id, default_chat_id, card)
    except FeishuApiError as exc:
        return SendAttempt(
            False,
            TARGET_DEFAULT_CHAT,
            0,
            direct_failed_count + 1,
            True,
            sanitize_authorization_error(str(exc)),
        )
    return SendAttempt(
        True,
        TARGET_DEFAULT_CHAT,
        1,
        direct_failed_count,
        True,
    )


async def _send_to_open_ids(
    db: AsyncSession,
    *,
    project_id: int,
    target_mode: str,
    open_ids: list[str],
    card: dict[str, Any],
) -> SendAttempt:
    sent_count = 0
    failed_count = 0
    last_error = ""
    for open_id in open_ids:
        try:
            await send_card_to_open_id(db, project_id, open_id, card)
            sent_count += 1
        except FeishuApiError as exc:
            failed_count += 1
            last_error = sanitize_authorization_error(str(exc))
    return SendAttempt(
        sent_count > 0,
        target_mode,
        sent_count,
        failed_count,
        False,
        last_error,
    )


def _mark_record_send_failed(
    record: SourceEvidenceAuthorizationRecord,
    send_attempt: SendAttempt,
) -> None:
    record.status = STATUS_AUTHORIZATION_FAILED
    record.state_hash = None
    record.state_expires_at = None
    record.target_mode = send_attempt.target_mode
    record.sent_targets_count = send_attempt.sent_count
    record.failed_targets_count = send_attempt.failed_count
    record.last_error_summary = sanitize_authorization_error(
        send_attempt.last_error or "授权卡发送失败。"
    )


def _mark_callback_failure(
    record: SourceEvidenceAuthorizationRecord,
    status: str,
    message: str,
) -> None:
    record.status = status
    record.state_hash = None
    record.state_expires_at = None
    record.last_error_summary = sanitize_authorization_error(message)


async def _verify_source_readable(
    db: AsyncSession,
    *,
    project_id: int,
    source: AuthorizationSource,
) -> None:
    token = quote(source.token, safe="")
    if source.doc_type in {"docx", "docs", "doc"}:
        await feishu_json_request(
            db,
            project_id,
            "GET",
            f"/open-apis/docx/v1/documents/{token}/blocks",
            params={"page_size": 1, "document_revision_id": -1},
        )
        return
    if source.doc_type in {"sheets", "sheet"}:
        await feishu_json_request(
            db,
            project_id,
            "GET",
            f"/open-apis/sheets/v3/spreadsheets/{token}/sheets/query",
        )
        return
    if source.doc_type in {"bitable", "base"}:
        await feishu_json_request(
            db,
            project_id,
            "GET",
            f"/open-apis/bitable/v1/apps/{token}/tables",
            params={"page_size": 1},
        )
        return
    raise SourceEvidenceError(400, f"暂不支持的飞书源文档类型：{source.doc_type}")


async def _project_name(db: AsyncSession, *, project_id: int) -> str:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    return project.name if project is not None else f"project-{project_id}"


def _build_source_evidence_oauth_url(
    *,
    app_id: str,
    callback_url: str,
    state: str,
) -> str:
    scope = settings.feishu_source_evidence_oauth_scope.strip() or settings.feishu_sheet_oauth_scope
    query = urlencode(
        {
            "client_id": app_id,
            "redirect_uri": callback_url,
            "scope": scope,
            "state": state,
        }
    )
    return f"{settings.feishu_oauth_authorize_url}?{query}"


def _build_authorization_card(
    *,
    project_name: str,
    run: SourceEvidenceRunRecord,
    source: AuthorizationSource,
    metadata: FeishuDriveMetadata | None,
    requested_by: str,
    oauth_url: str,
) -> dict[str, Any]:
    title = source.title or (metadata.title if metadata is not None else "") or run.source_title
    fingerprint = source_fingerprint(hash_source_token(source.token))
    content = "\n".join(
        [
            f"**项目：** {project_name}",
            f"**来源：** {title or source.doc_type}",
            f"**类型：** {source.doc_type}",
            f"**指纹：** {fingerprint}",
            f"**申请人：** {requested_by or '系统用户'}",
            "**说明：** 仅用于读取正文、表格、下载图片/附件和生成证据，不修改源文档。",
            "**权限：** 将项目 App/Bot 添加为整篇源文档 edit 协作者。",
            "**有效期：** 10 分钟",
        ]
    )
    return {
        "header": {
            "title": {"tag": "plain_text", "content": "Source Evidence 源文档授权请求"}
        },
        "elements": [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": content},
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "授权项目 App/Bot 读取",
                        },
                        "type": "primary",
                        "url": oauth_url,
                    }
                ],
            },
        ],
    }


def _request_response(
    *,
    status: str,
    message: str,
    authorization_id: int | None = None,
    target_mode: str = TARGET_NOT_SENT,
    sent_targets_count: int = 0,
    failed_targets_count: int = 0,
    fallback_to_default_chat: bool = False,
    owner_candidates_truncated: bool = False,
    expires_at: str | None = None,
    can_retry_read: bool = False,
) -> SourceEvidenceAuthorizationRequestResponse:
    return SourceEvidenceAuthorizationRequestResponse(
        status=status,
        message=message,
        authorization_id=authorization_id,
        target_mode=target_mode,
        sent_targets_count=sent_targets_count,
        failed_targets_count=failed_targets_count,
        fallback_to_default_chat=fallback_to_default_chat,
        owner_candidates_truncated=owner_candidates_truncated,
        expires_at=expires_at,
        can_retry_read=can_retry_read,
    )


def _audit_item(record: SourceEvidenceAuthorizationRecord) -> SourceEvidenceAuthorizationAuditItem:
    alias_fingerprints = _alias_fingerprints(record.source_token_alias_hashes_json)
    return SourceEvidenceAuthorizationAuditItem(
        id=record.id,
        project_id=record.project_id,
        app_id=record.app_id,
        doc_type=record.doc_type,
        permission=record.permission,
        status=record.status,
        source_fingerprint=source_fingerprint(record.source_token_hash),
        source_alias_fingerprints=alias_fingerprints,
        originating_run_id=record.originating_run_id,
        target_mode=record.target_mode,
        sent_targets_count=record.sent_targets_count,
        failed_targets_count=record.failed_targets_count,
        owner_candidates_truncated=record.owner_candidates_truncated,
        authorized_by_open_id=record.authorized_by_open_id,
        authorized_by_display_name_masked=record.authorized_by_display_name_masked,
        state_expires_at=_datetime_to_iso(record.state_expires_at),
        authorized_at=_datetime_to_iso(record.authorized_at),
        expires_at=_datetime_to_iso(record.expires_at),
        invalidated_at=_datetime_to_iso(record.invalidated_at),
        invalidated_by=record.invalidated_by,
        last_error_summary=record.last_error_summary,
        created_at=_datetime_to_iso(record.created_at),
        updated_at=_datetime_to_iso(record.updated_at),
    )


def _alias_fingerprints(raw_json: str | None) -> list[str]:
    try:
        payload = json.loads(raw_json or "[]")
    except ValueError:
        return []
    if not isinstance(payload, list):
        return []
    fingerprints: list[str] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        fingerprint = str(item.get("fingerprint") or "").strip()
        if fingerprint:
            fingerprints.append(fingerprint)
            continue
        alias_hash = str(item.get("hash") or "").strip()
        if alias_hash:
            fingerprints.append(source_fingerprint(alias_hash))
    return fingerprints


def _authorization_expires_at(now: datetime.datetime) -> datetime.datetime:
    ttl_days = settings.source_evidence_authorization_ttl_days
    if ttl_days <= 0:
        ttl_days = 90
    return _as_aware_utc(now) + datetime.timedelta(days=ttl_days)


def _as_aware_utc(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.UTC)
    return value.astimezone(datetime.UTC)


def _datetime_to_iso(value: datetime.datetime | None) -> str | None:
    if value is None:
        return None
    return _as_aware_utc(value).isoformat()
