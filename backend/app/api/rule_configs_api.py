"""规则配置存储与版本接口。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import CurrentUserContext, get_current_user
from backend.app.database import get_db
from backend.app.models import RuleConfigRecord, RuleConfigVersionRecord
from backend.app.rule_configs.parser import RuleConfigParseError
from backend.app.rule_configs.service import (
    RuleConfigMutation,
    ensure_supported_rule_family,
    get_current_rule_config,
    list_rule_config_versions,
    publish_rule_config,
    rollback_rule_config_version,
    save_rule_config_draft,
)


router = APIRouter(prefix="/rule-configs", tags=["rule-configs"])


class RuleConfigMutationRequest(BaseModel):
    """保存草稿 / 发布请求。"""

    model_config = ConfigDict(extra="forbid")

    content_md: str = Field(min_length=1, max_length=200_000)
    expected_optimistic_lock_version: int = Field(ge=0)
    description: str = Field(default="", max_length=500)


class RuleConfigRollbackRequest(BaseModel):
    """回滚到历史版本请求。"""

    model_config = ConfigDict(extra="forbid")

    expected_optimistic_lock_version: int = Field(ge=0)
    description: str = Field(default="", max_length=500)


@router.get("/{rule_family}")
async def get_rule_config(
    rule_family: str,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """获取当前项目当前规则配置。"""
    project_id = ctx.require_strict_project_member()
    record = await get_current_rule_config(
        db,
        project_id=project_id,
        rule_family=rule_family,
    )
    return {
        "code": 200,
        "msg": "ok",
        "data": _serialize_rule_config_record(
            record,
            project_id=project_id,
            rule_family=rule_family,
        ),
    }


@router.put("/{rule_family}/draft")
async def save_rule_config_draft_endpoint(
    rule_family: str,
    payload: RuleConfigMutationRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """保存规则配置草稿。"""
    project_id = ctx.require_strict_project_member()
    try:
        record = await save_rule_config_draft(
            db,
            project_id=project_id,
            user_id=ctx.user_id,
            rule_family=rule_family,
            mutation=RuleConfigMutation(
                content_md=payload.content_md,
                expected_optimistic_lock_version=payload.expected_optimistic_lock_version,
                description=payload.description,
            ),
        )
    except RuleConfigParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"code": 200, "msg": "ok", "data": _serialize_rule_config_record(record)}


@router.post("/{rule_family}/publish")
async def publish_rule_config_endpoint(
    rule_family: str,
    payload: RuleConfigMutationRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """发布规则配置。"""
    project_id = ctx.require_strict_project_member()
    try:
        record = await publish_rule_config(
            db,
            project_id=project_id,
            user_id=ctx.user_id,
            rule_family=rule_family,
            mutation=RuleConfigMutation(
                content_md=payload.content_md,
                expected_optimistic_lock_version=payload.expected_optimistic_lock_version,
                description=payload.description,
            ),
        )
    except RuleConfigParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"code": 200, "msg": "ok", "data": _serialize_rule_config_record(record)}


@router.get("/{rule_family}/versions")
async def list_rule_config_versions_endpoint(
    rule_family: str,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """获取版本历史。"""
    project_id = ctx.require_strict_project_member()
    versions = await list_rule_config_versions(
        db,
        project_id=project_id,
        rule_family=rule_family,
    )
    return {
        "code": 200,
        "msg": "ok",
        "data": {
            "items": [_serialize_rule_config_version(row) for row in versions],
            "total": len(versions),
        },
    }


@router.post("/{rule_family}/versions/{version}/rollback")
async def rollback_rule_config_version_endpoint(
    rule_family: str,
    version: int,
    payload: RuleConfigRollbackRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """回滚到历史版本，生成新的草稿版本。"""
    project_id = ctx.require_strict_project_member()
    record = await rollback_rule_config_version(
        db,
        project_id=project_id,
        user_id=ctx.user_id,
        rule_family=rule_family,
        version=version,
        expected_optimistic_lock_version=payload.expected_optimistic_lock_version,
        description=payload.description,
    )
    return {"code": 200, "msg": "ok", "data": _serialize_rule_config_record(record)}


@router.get("/{rule_family}/credentials/status")
async def get_rule_config_credentials_status(
    rule_family: str,
    ctx: CurrentUserContext = Depends(get_current_user),
) -> dict[str, Any]:
    """获取项目凭据脱敏状态骨架，不返回任何密钥。"""
    ctx.require_strict_project_member()
    ensure_supported_rule_family(rule_family)
    return {
        "code": 200,
        "msg": "ok",
        "data": {
            "svn": {
                "configured": False,
                "account_masked": "",
                "updated_at": None,
            },
            "ai": {
                "configured": False,
                "model": "",
                "credential_masked": "",
                "updated_at": None,
            },
        },
    }


def _serialize_rule_config_record(
    record: RuleConfigRecord | None,
    *,
    project_id: int | None = None,
    rule_family: str | None = None,
) -> dict[str, Any]:
    if record is None:
        if project_id is None or rule_family is None:
            raise ValueError("empty skeleton requires project_id and rule_family")
        ensure_supported_rule_family(rule_family)
        return {
            "project_id": project_id,
            "rule_family": rule_family,
            "content_md": "",
            "parsed_config_json": {},
            "status": "empty",
            "draft_version": 0,
            "published_version": None,
            "created_by": None,
            "updated_by": None,
            "published_by": None,
            "published_at": None,
            "optimistic_lock_version": 0,
            "created_at": None,
            "updated_at": None,
        }

    return {
        "project_id": record.project_id,
        "rule_family": record.rule_family,
        "content_md": record.content_md,
        "parsed_config_json": _parse_json_object(record.parsed_config_json),
        "status": record.status,
        "draft_version": record.draft_version,
        "published_version": record.published_version,
        "created_by": record.created_by,
        "updated_by": record.updated_by,
        "published_by": record.published_by,
        "published_at": record.published_at.isoformat() if record.published_at else None,
        "optimistic_lock_version": record.optimistic_lock_version,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _serialize_rule_config_version(row: RuleConfigVersionRecord) -> dict[str, Any]:
    return {
        "project_id": row.project_id,
        "rule_family": row.rule_family,
        "version": row.version,
        "content_md": row.content_md,
        "parsed_config_json": _parse_json_object(row.parsed_config_json),
        "status": row.status,
        "action": row.action,
        "operator": row.operator,
        "description": row.description,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _parse_json_object(raw_json: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_json or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
