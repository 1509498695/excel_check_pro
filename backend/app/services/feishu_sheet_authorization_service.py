"""飞书电子表格授权记录服务。"""

from __future__ import annotations

import datetime
import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import FeishuSheetAuthorizationRecord


AUTHORIZATION_STATUS_PENDING = "pending"
AUTHORIZATION_STATUS_SENT = "authorization_sent"
AUTHORIZATION_STATUS_AUTHORIZED = "authorized"
AUTHORIZATION_STATUS_FAILED = "failed"
AUTHORIZATION_STATUS_AUTHORIZATION_FAILED = "authorization_failed"


def hash_authorization_state(state: str) -> str:
    """对一次性 OAuth state 做不可逆哈希，避免落库明文 state。"""
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


async def get_authorization_by_source(
    db: AsyncSession,
    project_id: int,
    source_id: str,
) -> FeishuSheetAuthorizationRecord | None:
    """按项目与 source_id 查询授权记录。"""
    result = await db.execute(
        select(FeishuSheetAuthorizationRecord).where(
            FeishuSheetAuthorizationRecord.project_id == project_id,
            FeishuSheetAuthorizationRecord.source_id == source_id,
        )
    )
    return result.scalar_one_or_none()


async def get_success_authorization_by_token(
    db: AsyncSession,
    project_id: int,
    spreadsheet_token: str,
) -> FeishuSheetAuthorizationRecord | None:
    """查询同项目内已成功授权的同 spreadsheet_token 记录。"""
    result = await db.execute(
        select(FeishuSheetAuthorizationRecord)
        .where(
            FeishuSheetAuthorizationRecord.project_id == project_id,
            FeishuSheetAuthorizationRecord.spreadsheet_token == spreadsheet_token,
            FeishuSheetAuthorizationRecord.status == AUTHORIZATION_STATUS_AUTHORIZED,
        )
        .order_by(FeishuSheetAuthorizationRecord.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_authorization_by_state(
    db: AsyncSession,
    state: str,
) -> FeishuSheetAuthorizationRecord | None:
    """按明文 state 查询授权记录；数据库仅保存 state_hash。"""
    normalized_state = (state or "").strip()
    if not normalized_state:
        return None
    result = await db.execute(
        select(FeishuSheetAuthorizationRecord).where(
            FeishuSheetAuthorizationRecord.state_hash
            == hash_authorization_state(normalized_state)
        )
    )
    return result.scalar_one_or_none()


async def upsert_authorization_record(
    db: AsyncSession,
    *,
    project_id: int,
    source_id: str,
    spreadsheet_token: str,
    sheet_url: str = "",
    sheet_title: str = "",
    status: str = AUTHORIZATION_STATUS_PENDING,
    authorized_by_open_id: str = "",
    bot_open_id: str = "",
    chat_id: str = "",
    message_id: str = "",
    error_message: str = "",
    state_hash: str = "",
    state_expires_at: datetime.datetime | None = None,
    authorized_at: datetime.datetime | None = None,
) -> FeishuSheetAuthorizationRecord:
    """按 project_id + source_id 更新或插入授权记录。"""
    record = await get_authorization_by_source(db, project_id, source_id)
    if record is None:
        record = FeishuSheetAuthorizationRecord(
            project_id=project_id,
            source_id=source_id,
        )

    record.spreadsheet_token = spreadsheet_token
    record.sheet_url = sheet_url
    record.sheet_title = sheet_title
    record.status = status
    record.authorized_by_open_id = authorized_by_open_id
    record.bot_open_id = bot_open_id
    record.chat_id = chat_id
    record.message_id = message_id
    record.error_message = error_message
    record.state_hash = state_hash
    record.state_expires_at = state_expires_at
    record.authorized_at = authorized_at
    db.add(record)
    await db.flush()
    return record


async def mark_authorization_success(
    db: AsyncSession,
    record_or_id: FeishuSheetAuthorizationRecord | int,
    *,
    authorized_by_open_id: str | None = None,
    bot_open_id: str | None = None,
    chat_id: str | None = None,
    message_id: str | None = None,
    sheet_title: str | None = None,
) -> FeishuSheetAuthorizationRecord:
    """将授权记录标记为成功。"""
    record = await _resolve_authorization_record(db, record_or_id)
    record.status = AUTHORIZATION_STATUS_AUTHORIZED
    record.error_message = ""
    record.state_hash = ""
    record.state_expires_at = None
    record.authorized_at = _utc_now()
    _assign_optional_fields(
        record,
        authorized_by_open_id=authorized_by_open_id,
        bot_open_id=bot_open_id,
        chat_id=chat_id,
        message_id=message_id,
        sheet_title=sheet_title,
    )
    db.add(record)
    await db.flush()
    return record


async def mark_authorization_failed(
    db: AsyncSession,
    record_or_id: FeishuSheetAuthorizationRecord | int,
    *,
    error_message: str,
    status: str = AUTHORIZATION_STATUS_FAILED,
) -> FeishuSheetAuthorizationRecord:
    """将授权记录标记为失败并记录错误信息。"""
    record = await _resolve_authorization_record(db, record_or_id)
    record.status = status
    record.error_message = error_message
    record.state_hash = ""
    record.state_expires_at = None
    db.add(record)
    await db.flush()
    return record


async def _resolve_authorization_record(
    db: AsyncSession,
    record_or_id: FeishuSheetAuthorizationRecord | int,
) -> FeishuSheetAuthorizationRecord:
    if isinstance(record_or_id, FeishuSheetAuthorizationRecord):
        return record_or_id

    record = await db.get(FeishuSheetAuthorizationRecord, record_or_id)
    if record is None:
        raise ValueError(f"未找到飞书表格授权记录：{record_or_id}")
    return record


def _assign_optional_fields(
    record: FeishuSheetAuthorizationRecord,
    **values: Any,
) -> None:
    for field_name, value in values.items():
        if value is not None:
            setattr(record, field_name, value)


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)
