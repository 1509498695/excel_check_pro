"""飞书数据源相关接口。"""

from __future__ import annotations

import datetime
import html
import logging
import secrets
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import CurrentUserContext, get_current_user
from backend.app.database import get_db
from backend.app.integrations.feishu_bot import (
    FeishuApiError,
    send_card_to_chat,
    send_text_to_chat,
)
from backend.app.integrations.feishu_client import (
    FEISHU_API_ERROR,
    FEISHU_APP_PERMISSION_MISSING,
    FEISHU_DOCUMENT_NOT_FOUND,
    FEISHU_DOCUMENT_PERMISSION_DENIED,
    FEISHU_INVALID_URL,
    FeishuClientError,
    add_sheet_viewer_collaborator,
    exchange_oauth_code_for_user_token,
    get_current_bot_open_id,
    get_oauth_user_info,
    get_spreadsheet_metadata,
    resolve_wiki_sheet_locator,
    resolve_wiki_sheet_locator_with_user_token,
)
from backend.app.loaders.feishu_reader import (
    FeishuSheetError,
    FeishuSheetLocator,
    parse_feishu_sheet_url,
)
from backend.app.models import FeishuBotConfigRecord, FeishuSheetAuthorizationRecord, Project
from backend.app.services.feishu_sheet_authorization_service import (
    AUTHORIZATION_STATUS_AUTHORIZATION_FAILED,
    AUTHORIZATION_STATUS_AUTHORIZED,
    AUTHORIZATION_STATUS_SENT,
    get_authorization_by_source,
    get_authorization_by_state,
    get_success_authorization_by_token,
    hash_authorization_state,
    mark_authorization_failed,
    mark_authorization_success,
    upsert_authorization_record,
)
from backend.config import settings


router = APIRouter(prefix="/feishu", tags=["feishu"])
logger = logging.getLogger(__name__)

AUTHORIZED_STATUS = "authorized"
PENDING_AUTHORIZATION_STATUS = "pending_authorization"
INVALID_URL_STATUS = "invalid_url"
APP_PERMISSION_MISSING_STATUS = "app_permission_missing"
DOCUMENT_PERMISSION_DENIED_STATUS = "document_permission_denied"
NOT_FOUND_STATUS = "not_found"
BOT_NOT_CONFIGURED_STATUS = "bot_not_configured"
SEND_FAILED_STATUS = "send_failed"

_PENDING_AUTHORIZATION_MESSAGE = "文档权限不足，请发送授权请求到群。"
_AUTHORIZATION_TTL_SECONDS = 10 * 60


class FeishuSourcePermissionCheckRequest(BaseModel):
    """飞书电子表格数据源权限检测请求。"""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    sheet_url: str


class FeishuSendAuthorizationCardRequest(BaseModel):
    """飞书电子表格授权卡片发送请求。"""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    sheet_url: str


@router.post("/sources/check-permission")
async def check_feishu_source_permission(
    payload: FeishuSourcePermissionCheckRequest,
    db: AsyncSession = Depends(get_db),
    ctx: CurrentUserContext = Depends(get_current_user),
) -> dict[str, Any]:
    """检测当前项目飞书机器人是否可读取指定电子表格。"""
    project_id = ctx.require_project_member()
    source_id = payload.source_id.strip()

    try:
        locator = parse_feishu_sheet_url(payload.sheet_url)
    except FeishuSheetError as exc:
        return _ok(
            {
                "status": INVALID_URL_STATUS,
                "message": str(exc),
            }
        )

    configured = await _has_configured_feishu_bot(db, project_id)
    if not configured:
        return _ok(
            {
                "status": BOT_NOT_CONFIGURED_STATUS,
                "message": "当前项目尚未配置飞书机器人应用。",
            }
        )

    source_record = await get_authorization_by_source(
        db,
        project_id,
        source_id,
    )
    source_status = _build_permission_response_from_source_record(
        source_record,
        fallback_url=locator.normalized_url,
    )
    if source_status is not None:
        return _ok(source_status)

    reusable_record = await _get_reusable_authorization_record(
        db,
        project_id,
        locator,
    )
    if reusable_record is not None:
        record = await _upsert_authorized_from_reusable_record(
            db,
            project_id=project_id,
            source_id=source_id,
            reusable_record=reusable_record,
        )
        await db.commit()
        return _ok(_build_reused_authorization_response(record, locator))

    try:
        readable_sheet = await _read_authorized_sheet(db, project_id, locator)
    except FeishuClientError as exc:
        pending_status = _build_authorization_sent_fallback_response(
            source_record,
            fallback_url=locator.normalized_url,
        )
        if pending_status is not None:
            return _ok(pending_status)
        return _ok(_map_feishu_permission_error(exc))

    record = await upsert_authorization_record(
        db,
        project_id=project_id,
        source_id=source_id,
        spreadsheet_token=readable_sheet.spreadsheet_token,
        sheet_url=readable_sheet.sheet_url,
        sheet_title=readable_sheet.title,
        status=AUTHORIZATION_STATUS_AUTHORIZED,
    )
    await db.commit()

    return _ok(_build_authorized_sheet_response(record))


@router.post("/sources/send-authorization-card")
async def send_feishu_source_authorization_card(
    payload: FeishuSendAuthorizationCardRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    ctx: CurrentUserContext = Depends(get_current_user),
) -> dict[str, Any]:
    """向项目默认飞书群发送电子表格读取授权卡片。"""
    project_id = ctx.require_project_member()
    source_id = payload.source_id.strip()

    try:
        locator = parse_feishu_sheet_url(payload.sheet_url)
    except FeishuSheetError as exc:
        return _ok({"status": INVALID_URL_STATUS, "message": str(exc)})

    bot_config = await _get_configured_feishu_bot(db, project_id)
    if bot_config is None or not bot_config.default_chat_id.strip():
        return _ok(
            {
                "status": BOT_NOT_CONFIGURED_STATUS,
                "message": "当前项目尚未完整配置飞书机器人应用、密钥或默认群。",
            }
        )

    try:
        readable_sheet = await _read_authorized_sheet(db, project_id, locator)
    except FeishuClientError:
        readable_sheet = None

    if readable_sheet is not None:
        record = await upsert_authorization_record(
            db,
            project_id=project_id,
            source_id=source_id,
            spreadsheet_token=readable_sheet.spreadsheet_token,
            sheet_url=readable_sheet.sheet_url,
            sheet_title=readable_sheet.title,
            status=AUTHORIZATION_STATUS_AUTHORIZED,
        )
        await db.commit()
        return _ok(_build_authorized_sheet_response(record))

    callback_url = _resolve_feishu_oauth_callback_url(request)

    project_name = await _get_project_name(db, project_id)
    sheet_title = await _try_get_sheet_title(db, project_id, locator)
    display_sheet = sheet_title or locator.normalized_url
    state = secrets.token_urlsafe(32)
    state_hash = hash_authorization_state(state)
    expires_at = _utc_now() + datetime.timedelta(seconds=_AUTHORIZATION_TTL_SECONDS)
    oauth_url = _build_feishu_oauth_url(
        app_id=bot_config.app_id.strip(),
        callback_url=callback_url,
        state=state,
    )
    card = _build_authorization_card(
        project_name=project_name,
        source_id=source_id,
        sheet_label=display_sheet,
        oauth_url=oauth_url,
    )

    try:
        send_result = await send_card_to_chat(
            db=db,
            project_id=project_id,
            chat_id=bot_config.default_chat_id,
            card=card,
        )
    except FeishuApiError as exc:
        return _ok(
            {
                "status": SEND_FAILED_STATUS,
                "message": str(exc),
            }
        )

    message_id = str(send_result.get("message_id") or "")
    record = await upsert_authorization_record(
        db,
        project_id=project_id,
        source_id=source_id,
        spreadsheet_token=locator.spreadsheet_token,
        sheet_url=locator.normalized_url,
        sheet_title=sheet_title,
        status=AUTHORIZATION_STATUS_SENT,
        chat_id=bot_config.default_chat_id.strip(),
        message_id=message_id,
        state_hash=state_hash,
        state_expires_at=expires_at,
    )
    await db.commit()

    return _ok(
        {
            "status": AUTHORIZATION_STATUS_SENT,
            "expires_at": _format_datetime(record.state_expires_at),
            "chat_id": record.chat_id,
            "message_id": record.message_id,
        }
    )


@router.get("/sources/oauth/callback", response_class=HTMLResponse)
async def handle_feishu_source_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """处理飞书 OAuth 回调，并将机器人加入表格只读协作者。"""
    if not state or not state.strip():
        return _authorization_failure_page("授权失败：授权请求缺少 state，请重新发送授权请求。")

    record = await get_authorization_by_state(db, state)
    if record is None:
        return _authorization_failure_page("授权失败：授权请求不存在或已被使用，请重新发送授权请求。")

    validation_error = _validate_authorization_state_record(record)
    if validation_error:
        await mark_authorization_failed(
            db,
            record,
            error_message=validation_error,
            status=AUTHORIZATION_STATUS_AUTHORIZATION_FAILED,
        )
        await db.commit()
        await _send_authorization_notice(
            db,
            project_id=record.project_id,
            chat_id=record.chat_id,
            text=validation_error,
        )
        return _authorization_failure_page(validation_error)

    if not code or not code.strip():
        message = "授权失败：飞书 OAuth 回调缺少授权码，请重新发送授权请求。"
        await mark_authorization_failed(
            db,
            record,
            error_message=message,
            status=AUTHORIZATION_STATUS_AUTHORIZATION_FAILED,
        )
        await db.commit()
        await _send_authorization_notice(
            db,
            project_id=record.project_id,
            chat_id=record.chat_id,
            text=message,
        )
        return _authorization_failure_page(message)

    callback_url = _resolve_feishu_oauth_callback_url(request)

    try:
        user_access_token = await exchange_oauth_code_for_user_token(
            db,
            record.project_id,
            code,
            callback_url,
        )
        user_info = await get_oauth_user_info(user_access_token)
        bot_open_id = await get_current_bot_open_id(db, record.project_id)
        drive_locator = await _resolve_record_locator_for_oauth_callback(
            user_access_token,
            record,
        )
        await add_sheet_viewer_collaborator(
            user_access_token,
            drive_locator.spreadsheet_token,
            bot_open_id,
        )
        record.spreadsheet_token = drive_locator.spreadsheet_token
        record.sheet_url = drive_locator.normalized_url
    except FeishuClientError as exc:
        if _is_share_permission_error(exc):
            readable_sheet = await _try_read_authorized_sheet(
                db,
                record.project_id,
                drive_locator if "drive_locator" in locals() else record.sheet_url,
            )
            if readable_sheet is not None:
                record.spreadsheet_token = readable_sheet.spreadsheet_token
                record.sheet_url = readable_sheet.sheet_url
                record.sheet_title = readable_sheet.title or record.sheet_title
                await mark_authorization_success(
                    db,
                    record,
                    authorized_by_open_id=(
                        user_info.open_id if "user_info" in locals() else None
                    ),
                    bot_open_id=bot_open_id if "bot_open_id" in locals() else None,
                )
                await db.commit()
                success_message = "飞书表格授权成功，机器人已可读取该配置表。"
                await _send_authorization_notice(
                    db,
                    project_id=record.project_id,
                    chat_id=record.chat_id,
                    text=success_message,
                )
                return _authorization_success_page(success_message)
        message = _map_oauth_callback_error(exc)
        await mark_authorization_failed(
            db,
            record,
            error_message=message,
            status=AUTHORIZATION_STATUS_AUTHORIZATION_FAILED,
        )
        await db.commit()
        await _send_authorization_notice(
            db,
            project_id=record.project_id,
            chat_id=record.chat_id,
            text=message,
        )
        return _authorization_failure_page(message)

    await mark_authorization_success(
        db,
        record,
        authorized_by_open_id=user_info.open_id,
        bot_open_id=bot_open_id,
    )
    await db.commit()

    success_message = "飞书表格授权成功，机器人现在可以读取该配置表。"
    await _send_authorization_notice(
        db,
        project_id=record.project_id,
        chat_id=record.chat_id,
        text=success_message,
    )
    return _authorization_success_page(success_message)


async def _has_configured_feishu_bot(db: AsyncSession, project_id: int) -> bool:
    return await _get_configured_feishu_bot(db, project_id) is not None


async def _get_configured_feishu_bot(
    db: AsyncSession,
    project_id: int,
) -> FeishuBotConfigRecord | None:
    result = await db.execute(
        select(FeishuBotConfigRecord).where(
            FeishuBotConfigRecord.project_id == project_id
        )
    )
    record = result.scalar_one_or_none()
    if record and record.app_id.strip() and record.app_secret_cipher.strip():
        return record
    return None


async def _get_project_name(db: AsyncSession, project_id: int) -> str:
    project = await db.get(Project, project_id)
    if project is None:
        return str(project_id)
    return project.name


async def _try_get_sheet_title(db: AsyncSession, project_id: int, locator) -> str:
    try:
        readable_sheet = await _read_authorized_sheet(db, project_id, locator)
    except FeishuClientError:
        return ""
    return readable_sheet.title


class _AuthorizedSheet:
    def __init__(
        self,
        *,
        spreadsheet_token: str,
        sheet_url: str,
        title: str,
    ) -> None:
        self.spreadsheet_token = spreadsheet_token
        self.sheet_url = sheet_url
        self.title = title


async def _read_authorized_sheet(
    db: AsyncSession,
    project_id: int,
    locator: FeishuSheetLocator | str,
) -> _AuthorizedSheet:
    resolved_locator = await resolve_wiki_sheet_locator(db, project_id, locator)
    metadata = await get_spreadsheet_metadata(db, project_id, resolved_locator)
    spreadsheet_token = metadata.token or resolved_locator.spreadsheet_token
    return _AuthorizedSheet(
        spreadsheet_token=spreadsheet_token,
        sheet_url=_build_authorized_sheet_url(
            metadata.url,
            resolved_locator,
            spreadsheet_token,
        ),
        title=metadata.title,
    )


async def _try_read_authorized_sheet(
    db: AsyncSession,
    project_id: int,
    locator: FeishuSheetLocator | str,
) -> _AuthorizedSheet | None:
    try:
        return await _read_authorized_sheet(db, project_id, locator)
    except FeishuClientError:
        return None


def _build_authorized_sheet_url(
    metadata_url: str,
    resolved_locator: FeishuSheetLocator,
    spreadsheet_token: str,
) -> str:
    base_url = (metadata_url or "").strip() or resolved_locator.normalized_url
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        return resolved_locator.normalized_url
    if not resolved_locator.sheet_id:
        return base_url
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key != "sheet"
    ]
    query_pairs.append(("sheet", resolved_locator.sheet_id))
    path = parsed.path or f"/sheets/{spreadsheet_token}"
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            path,
            "",
            urlencode(query_pairs),
            "",
        )
    )


async def _get_reusable_authorization_record(
    db: AsyncSession,
    project_id: int,
    locator: FeishuSheetLocator,
) -> FeishuSheetAuthorizationRecord | None:
    reusable_record = await get_success_authorization_by_token(
        db,
        project_id,
        locator.spreadsheet_token,
    )
    if reusable_record is not None:
        return reusable_record
    try:
        resolved_locator = await resolve_wiki_sheet_locator(db, project_id, locator)
    except FeishuClientError:
        return None
    if resolved_locator.spreadsheet_token == locator.spreadsheet_token:
        return None
    return await get_success_authorization_by_token(
        db,
        project_id,
        resolved_locator.spreadsheet_token,
    )


async def _upsert_authorized_from_reusable_record(
    db: AsyncSession,
    *,
    project_id: int,
    source_id: str,
    reusable_record: FeishuSheetAuthorizationRecord,
) -> FeishuSheetAuthorizationRecord:
    return await upsert_authorization_record(
        db,
        project_id=project_id,
        source_id=source_id,
        spreadsheet_token=reusable_record.spreadsheet_token,
        sheet_url=reusable_record.sheet_url,
        sheet_title=reusable_record.sheet_title,
        status=AUTHORIZATION_STATUS_AUTHORIZED,
        authorized_by_open_id=reusable_record.authorized_by_open_id,
        bot_open_id=reusable_record.bot_open_id,
        authorized_at=reusable_record.authorized_at,
    )


def _build_reused_authorization_response(
    record: FeishuSheetAuthorizationRecord,
    locator: FeishuSheetLocator,
) -> dict[str, Any]:
    return {
        "status": AUTHORIZED_STATUS,
        "spreadsheet_token": record.spreadsheet_token,
        "sheet_url": record.sheet_url or locator.normalized_url,
        "title": record.sheet_title,
        "reused_authorization": True,
    }


def _build_authorized_sheet_response(
    record: FeishuSheetAuthorizationRecord,
) -> dict[str, Any]:
    return {
        "status": AUTHORIZED_STATUS,
        "spreadsheet_token": record.spreadsheet_token,
        "sheet_url": record.sheet_url,
        "title": record.sheet_title,
    }


async def _resolve_record_locator_for_oauth_callback(
    user_access_token: str,
    record: FeishuSheetAuthorizationRecord,
) -> FeishuSheetLocator:
    try:
        locator = parse_feishu_sheet_url(
            record.sheet_url or f"https://feishu.cn/sheets/{record.spreadsheet_token}"
        )
    except FeishuSheetError:
        locator = FeishuSheetLocator(
            spreadsheet_token=record.spreadsheet_token,
            sheet_id=None,
            normalized_url=f"https://feishu.cn/sheets/{record.spreadsheet_token}",
        )
    if locator.url_type != "wiki":
        return locator
    return await resolve_wiki_sheet_locator_with_user_token(user_access_token, locator)


def _resolve_feishu_oauth_callback_url(request: Request) -> str:
    """返回飞书 OAuth callback URL，优先使用显式配置，缺省时按当前请求生成。"""
    configured_callback_url = settings.feishu_oauth_callback_url.strip()
    if configured_callback_url:
        return configured_callback_url
    return str(request.url_for("handle_feishu_source_oauth_callback"))


def _build_feishu_oauth_url(
    *,
    app_id: str,
    callback_url: str,
    state: str,
) -> str:
    query = urlencode(
        {
            "client_id": app_id,
            "redirect_uri": callback_url,
            "scope": settings.feishu_sheet_oauth_scope,
            "state": state,
        }
    )
    return f"{settings.feishu_oauth_authorize_url}?{query}"


def _build_authorization_card(
    *,
    project_name: str,
    source_id: str,
    sheet_label: str,
    oauth_url: str,
) -> dict[str, Any]:
    content = "\n".join(
        [
            f"**项目：** {project_name}",
            f"**数据源：** {source_id}",
            f"**表格：** {sheet_label}",
            "**说明：** 机器人需要只读访问该表格，用于配置校验。",
            "**权限：** 仅申请 view 只读权限，不会修改表格内容。",
            "**有效期：** 10 分钟",
        ]
    )
    return {
        "header": {
            "title": {"tag": "plain_text", "content": "飞书表格读取授权请求"}
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
                            "content": "授权机器人读取",
                        },
                        "type": "primary",
                        "url": oauth_url,
                    }
                ],
            },
        ],
    }


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _format_datetime(value: datetime.datetime | None) -> str:
    if value is None:
        return ""
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=datetime.UTC)
    return normalized.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z")


def _map_feishu_permission_error(error: FeishuClientError) -> dict[str, Any]:
    if error.code == FEISHU_INVALID_URL:
        return {
            "status": INVALID_URL_STATUS,
            "message": error.message,
        }
    if error.code == FEISHU_APP_PERMISSION_MISSING:
        return {
            "status": APP_PERMISSION_MISSING_STATUS,
            "message": error.message,
        }
    if error.code == FEISHU_DOCUMENT_PERMISSION_DENIED:
        return {
            "status": PENDING_AUTHORIZATION_STATUS,
            "error_status": DOCUMENT_PERMISSION_DENIED_STATUS,
            "message": _PENDING_AUTHORIZATION_MESSAGE,
        }
    if error.code == FEISHU_DOCUMENT_NOT_FOUND:
        return {
            "status": NOT_FOUND_STATUS,
            "message": error.message,
        }
    if error.code == FEISHU_API_ERROR:
        return {
            "status": APP_PERMISSION_MISSING_STATUS,
            "message": error.message,
        }
    return {
        "status": APP_PERMISSION_MISSING_STATUS,
        "message": error.message,
    }


def _build_permission_response_from_source_record(
    record: FeishuSheetAuthorizationRecord | None,
    *,
    fallback_url: str,
) -> dict[str, Any] | None:
    if record is None:
        return None
    if record.status == AUTHORIZATION_STATUS_AUTHORIZED:
        return {
            "status": AUTHORIZED_STATUS,
            "spreadsheet_token": record.spreadsheet_token,
            "sheet_url": record.sheet_url or fallback_url,
            "title": record.sheet_title,
            "reused_authorization": True,
        }
    return None


def _build_authorization_sent_fallback_response(
    record: FeishuSheetAuthorizationRecord | None,
    *,
    fallback_url: str,
) -> dict[str, Any] | None:
    if record is None or record.status != AUTHORIZATION_STATUS_SENT:
        return None
    if _is_authorization_record_expired(record):
        return None
    return {
        "status": AUTHORIZATION_STATUS_SENT,
        "spreadsheet_token": record.spreadsheet_token,
        "sheet_url": record.sheet_url or fallback_url,
        "title": record.sheet_title,
        "expires_at": _format_datetime(record.state_expires_at),
        "chat_id": record.chat_id,
        "message_id": record.message_id,
        "message": "授权请求已发送到群，等待有权限的成员完成授权。",
    }


def _is_authorization_record_expired(record: FeishuSheetAuthorizationRecord) -> bool:
    if record.state_expires_at is None:
        return False
    expires_at = record.state_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=datetime.UTC)
    return expires_at <= _utc_now()


def _validate_authorization_state_record(
    record: FeishuSheetAuthorizationRecord,
) -> str:
    if record.status != AUTHORIZATION_STATUS_SENT:
        return "授权失败：该授权请求已被使用或状态不可用，请重新发送授权请求。"
    if not record.state_hash:
        return "授权失败：该授权请求已被使用，请重新发送授权请求。"
    if not record.spreadsheet_token:
        return "授权失败：授权请求缺少飞书表格 token，请重新发送授权请求。"
    if record.state_expires_at is None:
        return "授权失败：授权请求已过期，请重新发送授权请求。"

    expires_at = record.state_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=datetime.UTC)
    if expires_at <= _utc_now():
        return "授权失败：授权请求已过期，请重新发送授权请求。"
    return ""


def _map_oauth_callback_error(error: FeishuClientError) -> str:
    if _is_share_permission_error(error):
        return (
            "授权失败：飞书拒绝添加机器人为表格协作者。请确认当前用户是文档所有者或可管理协作者，"
            "并确认飞书应用已开通“添加云文档协作者”或云文档权限管理相关权限且已发布生效。"
        )
    return f"授权失败：{error.message}"


def _is_share_permission_error(error: FeishuClientError) -> bool:
    if error.code == FEISHU_DOCUMENT_PERMISSION_DENIED:
        return True
    message = error.message.lower()
    return any(
        keyword in message
        for keyword in (
            "permission",
            "forbidden",
            "access denied",
            "no access",
            "share",
            "无权限",
            "权限不足",
            "没有权限",
            "无权",
            "分享",
            "协作者",
        )
    )


async def _send_authorization_notice(
    db: AsyncSession,
    *,
    project_id: int,
    chat_id: str,
    text: str,
) -> None:
    if not chat_id.strip():
        return
    try:
        await send_text_to_chat(
            db=db,
            project_id=project_id,
            chat_id=chat_id,
            text=text,
        )
    except FeishuApiError:
        logger.warning("飞书授权回调群通知发送失败")


def _authorization_success_page(message: str) -> HTMLResponse:
    return _authorization_html_page("飞书表格授权成功", message)


def _authorization_failure_page(message: str) -> HTMLResponse:
    return _authorization_html_page("飞书表格授权失败", message)


def _authorization_html_page(title: str, message: str) -> HTMLResponse:
    escaped_title = html.escape(title)
    escaped_message = html.escape(message)
    content = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
</head>
<body>
  <h1>{escaped_title}</h1>
  <p>{escaped_message}</p>
</body>
</html>"""
    return HTMLResponse(content=content)


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": 200,
        "msg": "ok",
        "data": data,
    }
