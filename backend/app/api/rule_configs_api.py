"""规则配置存储与版本接口。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.providers import mask_api_key
from backend.app.auth.dependencies import CurrentUserContext, get_current_user
from backend.app.config_lookup.schemas import ConfigLookupRequest, ConfigLookupResponse
from backend.app.config_lookup.service import lookup_config_table
from backend.app.database import get_db
from backend.app.models import (
    ProjectAiCredentialRecord,
    ProjectSvnCredentialRecord,
    RuleConfigRecord,
    RuleConfigVersionRecord,
)
from backend.app.rule_configs.parser import RuleConfigValidationResult
from backend.app.rule_configs.service import (
    RULE_CONFIG_VALIDATION_FAILED,
    RuleConfigMutation,
    RuleConfigValidationError,
    ensure_supported_rule_family,
    get_current_rule_config,
    list_rule_config_versions,
    publish_rule_config,
    rollback_rule_config_version,
    save_rule_config_draft,
    validate_rule_config_content,
)
from backend.app.security.crypto import decrypt_secret


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


class RuleConfigValidateRequest(BaseModel):
    """结构校验请求。"""

    model_config = ConfigDict(extra="forbid")

    content_md: str = Field(min_length=1, max_length=200_000)


class RuleConfigTrialRequest(BaseModel):
    """配置表查询试查请求。"""

    model_config = ConfigDict(extra="forbid")

    query_type: str = Field(min_length=1, max_length=100)
    versioned_config_folder: str = Field(min_length=1, max_length=500)
    lookup_input: str = Field(min_length=1, max_length=500)
    use_current_draft: bool = False
    content_md: str | None = Field(default=None, max_length=200_000)


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


@router.post("/{rule_family}/validate")
async def validate_rule_config_endpoint(
    rule_family: str,
    payload: RuleConfigValidateRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """校验规则配置结构，不保存、不发布。"""
    project_id = ctx.require_strict_project_member()
    validation = await validate_rule_config_content(
        db,
        project_id=project_id,
        rule_family=rule_family,
        content_md=payload.content_md,
    )
    return {
        "code": 200,
        "msg": "ok",
        "data": _serialize_validation_result(validation),
    }


@router.post("/{rule_family}/trial")
async def trial_rule_config_endpoint(
    rule_family: str,
    payload: RuleConfigTrialRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """执行配置表查询试查，不保存草稿、不发布、不写版本历史。"""
    project_id = ctx.require_strict_project_member()
    ensure_supported_rule_family(rule_family)
    validation: RuleConfigValidationResult | None = None
    parsed_config_override: dict[str, Any] | None = None

    if payload.use_current_draft:
        content_md = (payload.content_md or "").strip()
        if not content_md:
            raise HTTPException(status_code=400, detail="使用当前草稿试查时 content_md 不能为空")
        validation = await validate_rule_config_content(
            db,
            project_id=project_id,
            rule_family=rule_family,
            content_md=content_md,
        )
        if not validation.ok:
            raise _validation_failed_exception(validation)
        parsed_config_override = validation.parsed_config_json

    result = await lookup_config_table(
        db,
        ConfigLookupRequest(
            project_id=project_id,
            query_type=payload.query_type,
            versioned_config_folder=payload.versioned_config_folder,
            lookup_input=payload.lookup_input,
        ),
        parsed_config_override=parsed_config_override,
    )
    return {
        "code": 200,
        "msg": "ok",
        "data": _serialize_trial_result(result, validation=validation),
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
        result = await save_rule_config_draft(
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
    except RuleConfigValidationError as exc:
        raise _validation_failed_exception(exc.validation) from exc
    return {
        "code": 200,
        "msg": "ok",
        "data": _serialize_rule_config_record(
            result.record,
            validation=result.validation,
        ),
    }


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
        result = await publish_rule_config(
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
    except RuleConfigValidationError as exc:
        raise _validation_failed_exception(exc.validation) from exc
    return {
        "code": 200,
        "msg": "ok",
        "data": _serialize_rule_config_record(
            result.record,
            validation=result.validation,
        ),
    }


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
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """获取项目凭据脱敏状态骨架，不返回任何密钥。"""
    project_id = ctx.require_strict_project_member()
    ensure_supported_rule_family(rule_family)
    svn_credential = await _get_project_svn_credential(db, project_id)
    ai_credential = await _get_project_ai_credential(db, project_id)
    return {
        "code": 200,
        "msg": "ok",
        "data": {
            "svn": _serialize_svn_credential_status(svn_credential),
            "ai": _serialize_ai_credential_status(ai_credential),
        },
    }


async def _get_project_svn_credential(
    db: AsyncSession,
    project_id: int,
) -> ProjectSvnCredentialRecord | None:
    result = await db.execute(
        select(ProjectSvnCredentialRecord).where(
            ProjectSvnCredentialRecord.project_id == project_id
        )
    )
    return result.scalar_one_or_none()


async def _get_project_ai_credential(
    db: AsyncSession,
    project_id: int,
) -> ProjectAiCredentialRecord | None:
    result = await db.execute(
        select(ProjectAiCredentialRecord).where(
            ProjectAiCredentialRecord.project_id == project_id
        )
    )
    return result.scalar_one_or_none()


def _serialize_svn_credential_status(
    record: ProjectSvnCredentialRecord | None,
) -> dict[str, Any]:
    if record is None or not record.password_cipher:
        return {
            "configured": False,
            "account_masked": "",
            "updated_at": None,
        }
    return {
        "configured": True,
        "account_masked": record.username or "",
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _serialize_ai_credential_status(
    record: ProjectAiCredentialRecord | None,
) -> dict[str, Any]:
    if record is None or not record.encrypted_api_key:
        return {
            "configured": False,
            "enabled": False,
            "provider": "",
            "base_url": "",
            "model": "",
            "credential_masked": "",
            "masked_api_key": "",
            "last_test_status": "",
            "last_test_at": None,
            "updated_at": None,
        }
    try:
        api_key = decrypt_secret(record.encrypted_api_key)
    except ValueError:
        api_key = ""
    return {
        "configured": bool(api_key),
        "enabled": bool(record.enabled),
        "provider": record.provider_preset,
        "base_url": record.base_url,
        "model": record.model,
        "credential_masked": mask_api_key(api_key),
        "masked_api_key": mask_api_key(api_key),
        "last_test_status": record.last_test_status or "",
        "last_test_at": record.last_test_at.isoformat() if record.last_test_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _serialize_rule_config_record(
    record: RuleConfigRecord | None,
    *,
    project_id: int | None = None,
    rule_family: str | None = None,
    validation: RuleConfigValidationResult | None = None,
) -> dict[str, Any]:
    if record is None:
        if project_id is None or rule_family is None:
            raise ValueError("empty skeleton requires project_id and rule_family")
        ensure_supported_rule_family(rule_family)
        data = {
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
        if validation is not None:
            data["validation"] = _serialize_validation_result(validation)
        return data

    data = {
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
    if validation is not None:
        data["validation"] = _serialize_validation_result(validation)
    return data


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


def _serialize_validation_result(validation: RuleConfigValidationResult) -> dict[str, Any]:
    return {
        "ok": validation.ok,
        "parsed_config_json": validation.parsed_config_json,
        "errors": validation.errors,
        "summary": validation.summary,
    }


def _serialize_trial_result(
    result: ConfigLookupResponse,
    *,
    validation: RuleConfigValidationResult | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": result.status,
        "message": result.message,
        "results": [
            {
                "query_type": item.query_type,
                "page": item.page,
                "id_value": item.id_value,
                "name_value": item.name_value,
                "fields": [
                    {"field": field.field, "label": field.label, "value": field.value}
                    for field in item.fields
                ],
                "warnings": item.warnings,
            }
            for item in result.results
        ],
        "candidates": [
            {
                "key": candidate.key,
                "page": candidate.page,
                "id_value": candidate.id_value,
                "name_value": candidate.name_value,
                "score": candidate.score,
            }
            for candidate in result.candidates
        ],
        "ai": {
            "used": result.ai.used,
            "unavailable_reason": result.ai.unavailable_reason,
            "thresholds": {
                "auto_match_threshold": result.ai.thresholds.auto_match_threshold,
                "candidate_threshold": result.ai.thresholds.candidate_threshold,
                "max_candidates": result.ai.thresholds.max_candidates,
            },
        },
    }
    if validation is not None:
        payload["validation"] = _serialize_validation_result(validation)
    return payload


def _validation_failed_exception(validation: RuleConfigValidationResult) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": RULE_CONFIG_VALIDATION_FAILED,
            "msg": "规则结构校验失败",
            "errors": validation.errors,
            "summary": validation.summary,
        },
    )
