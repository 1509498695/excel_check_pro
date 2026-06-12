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
    create_rule_config,
    ensure_supported_rule_family,
    get_rule_config_by_id,
    list_rule_config_versions,
    list_rule_configs,
    publish_rule_config,
    rollback_rule_config_version,
    save_rule_config_draft,
    validate_rule_config_content_for_record,
)
from backend.app.security.crypto import decrypt_secret


router = APIRouter(prefix="/rule-configs", tags=["rule-configs"])


class RuleConfigCreateRequest(BaseModel):
    """创建单条规则草稿请求。"""

    model_config = ConfigDict(extra="forbid")

    content_md: str = Field(min_length=1, max_length=200_000)
    description: str = Field(default="", max_length=500)


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

    query_type: str | None = Field(default=None, max_length=100)
    versioned_config_folder: str = Field(min_length=1, max_length=500)
    lookup_input: str = Field(min_length=1, max_length=500)
    use_current_draft: bool = False
    content_md: str | None = Field(default=None, max_length=200_000)


@router.get("/{rule_family}")
async def list_rule_configs_endpoint(
    rule_family: str,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """获取当前项目指定规则族下的查询规则列表。"""
    project_id = ctx.require_strict_project_member()
    records = await list_rule_configs(db, project_id=project_id, rule_family=rule_family)
    return {
        "code": 200,
        "msg": "ok",
        "data": {
            "items": [_serialize_rule_config_record(record) for record in records],
            "total": len(records),
        },
    }


@router.post("/{rule_family}")
async def create_rule_config_endpoint(
    rule_family: str,
    payload: RuleConfigCreateRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """创建当前项目的一条查询规则草稿。"""
    project_id = ctx.require_strict_project_member()
    try:
        result = await create_rule_config(
            db,
            project_id=project_id,
            user_id=ctx.user_id,
            rule_family=rule_family,
            content_md=payload.content_md,
            description=payload.description,
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


@router.get("/{rule_family}/{rule_id}")
async def get_rule_config_endpoint(
    rule_family: str,
    rule_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """获取当前项目的一条规则配置。"""
    project_id = ctx.require_strict_project_member()
    record = await get_rule_config_by_id(
        db,
        project_id=project_id,
        rule_family=rule_family,
        rule_id=rule_id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"code": 200, "msg": "ok", "data": _serialize_rule_config_record(record)}


@router.put("/{rule_family}/{rule_id}/draft")
async def save_rule_config_draft_endpoint(
    rule_family: str,
    rule_id: int,
    payload: RuleConfigMutationRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """保存单条规则配置草稿。"""
    project_id = ctx.require_strict_project_member()
    try:
        result = await save_rule_config_draft(
            db,
            project_id=project_id,
            user_id=ctx.user_id,
            rule_family=rule_family,
            rule_id=rule_id,
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


@router.post("/{rule_family}/{rule_id}/publish")
async def publish_rule_config_endpoint(
    rule_family: str,
    rule_id: int,
    payload: RuleConfigMutationRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """发布单条规则配置。"""
    project_id = ctx.require_strict_project_member()
    try:
        result = await publish_rule_config(
            db,
            project_id=project_id,
            user_id=ctx.user_id,
            rule_family=rule_family,
            rule_id=rule_id,
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


@router.post("/{rule_family}/{rule_id}/validate")
async def validate_rule_config_endpoint(
    rule_family: str,
    rule_id: int,
    payload: RuleConfigValidateRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """校验单条规则配置结构，不保存、不发布。"""
    project_id = ctx.require_strict_project_member()
    validation = await validate_rule_config_content_for_record(
        db,
        project_id=project_id,
        rule_family=rule_family,
        rule_id=rule_id,
        content_md=payload.content_md,
    )
    return {
        "code": 200,
        "msg": "ok",
        "data": _serialize_validation_result(validation),
    }


@router.get("/{rule_family}/{rule_id}/versions")
async def list_rule_config_versions_endpoint(
    rule_family: str,
    rule_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """获取单条规则版本历史。"""
    project_id = ctx.require_strict_project_member()
    versions = await list_rule_config_versions(
        db,
        project_id=project_id,
        rule_family=rule_family,
        rule_id=rule_id,
    )
    return {
        "code": 200,
        "msg": "ok",
        "data": {
            "items": [_serialize_rule_config_version(row) for row in versions],
            "total": len(versions),
        },
    }


@router.post("/{rule_family}/{rule_id}/versions/{version}/rollback")
async def rollback_rule_config_version_endpoint(
    rule_family: str,
    rule_id: int,
    version: int,
    payload: RuleConfigRollbackRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """回滚到历史版本，生成新的草稿版本。"""
    project_id = ctx.require_strict_project_member()
    try:
        record = await rollback_rule_config_version(
            db,
            project_id=project_id,
            user_id=ctx.user_id,
            rule_family=rule_family,
            rule_id=rule_id,
            version=version,
            expected_optimistic_lock_version=payload.expected_optimistic_lock_version,
            description=payload.description,
        )
    except RuleConfigValidationError as exc:
        raise _validation_failed_exception(exc.validation) from exc
    return {"code": 200, "msg": "ok", "data": _serialize_rule_config_record(record)}


@router.post("/{rule_family}/{rule_id}/trial")
async def trial_rule_config_endpoint(
    rule_family: str,
    rule_id: int,
    payload: RuleConfigTrialRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """执行配置表查询试查，不保存草稿、不发布、不写版本历史。"""
    project_id = ctx.require_strict_project_member()
    record = await get_rule_config_by_id(
        db,
        project_id=project_id,
        rule_family=rule_family,
        rule_id=rule_id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="规则不存在")

    validation: RuleConfigValidationResult | None = None
    parsed_config_override: dict[str, Any] | None = None
    effective_query_type = record.query_type

    if payload.use_current_draft:
        content_md = (payload.content_md or "").strip()
        if not content_md:
            raise HTTPException(status_code=400, detail="使用当前草稿试查时 content_md 不能为空")
        validation = await validate_rule_config_content_for_record(
            db,
            project_id=project_id,
            rule_family=rule_family,
            rule_id=rule_id,
            content_md=content_md,
        )
        if not validation.ok:
            raise _validation_failed_exception(validation)
        parsed_config_override = validation.parsed_config_json
        effective_query_type = str(
            validation.parsed_config_json.get("query_type") or record.query_type
        )

    if payload.query_type and payload.query_type != effective_query_type:
        raise HTTPException(status_code=400, detail="试查查询类型必须与当前规则一致")

    result = await lookup_config_table(
        db,
        ConfigLookupRequest(
            project_id=project_id,
            query_type=effective_query_type,
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
    record: RuleConfigRecord,
    *,
    validation: RuleConfigValidationResult | None = None,
) -> dict[str, Any]:
    data = {
        "id": record.id,
        "rule_id": record.id,
        "project_id": record.project_id,
        "rule_family": record.rule_family,
        "query_type": record.query_type,
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
        "id": row.id,
        "rule_config_id": row.rule_config_id,
        "rule_id": row.rule_config_id,
        "project_id": row.project_id,
        "rule_family": row.rule_family,
        "query_type": row.query_type,
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
