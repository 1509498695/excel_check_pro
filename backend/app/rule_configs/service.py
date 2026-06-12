"""规则配置存储、版本与发布服务。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import (
    ProjectQueryRootRecord,
    RuleConfigRecord,
    RuleConfigVersionRecord,
)
from backend.app.rule_configs.parser import (
    RuleConfigValidationResult,
    validate_config_lookup_markdown,
)


SUPPORTED_RULE_FAMILY = "config_lookup"
RULE_CONFIG_VERSION_CONFLICT = "RULE_CONFIG_VERSION_CONFLICT"
RULE_CONFIG_VALIDATION_FAILED = "RULE_CONFIG_VALIDATION_FAILED"
RuleConfigAction = Literal["publish"]


@dataclass(frozen=True)
class RuleConfigMutation:
    """规则配置变更请求。"""

    content_md: str
    expected_optimistic_lock_version: int
    description: str = ""


@dataclass(frozen=True)
class RuleConfigMutationResult:
    """规则配置变更结果。"""

    record: RuleConfigRecord
    validation: RuleConfigValidationResult


class RuleConfigValidationError(ValueError):
    """规则配置结构校验失败。"""

    def __init__(self, validation: RuleConfigValidationResult) -> None:
        super().__init__("规则结构校验失败")
        self.validation = validation


def ensure_supported_rule_family(rule_family: str) -> str:
    """当前仅允许 config_lookup。"""
    if rule_family != SUPPORTED_RULE_FAMILY:
        raise HTTPException(status_code=400, detail="当前仅支持 rule_family=config_lookup")
    return rule_family


async def list_rule_configs(
    db: AsyncSession,
    *,
    project_id: int,
    rule_family: str,
) -> list[RuleConfigRecord]:
    """读取当前项目某规则族下的所有查询规则。"""
    ensure_supported_rule_family(rule_family)
    result = await db.execute(
        select(RuleConfigRecord)
        .where(
            RuleConfigRecord.project_id == project_id,
            RuleConfigRecord.rule_family == rule_family,
        )
        .order_by(RuleConfigRecord.updated_at.desc(), RuleConfigRecord.id.desc())
    )
    return list(result.scalars().all())


async def get_rule_config_by_id(
    db: AsyncSession,
    *,
    project_id: int,
    rule_family: str,
    rule_id: int,
) -> RuleConfigRecord | None:
    """按内部 rule_id 读取当前项目规则。"""
    ensure_supported_rule_family(rule_family)
    result = await db.execute(
        select(RuleConfigRecord).where(
            RuleConfigRecord.id == rule_id,
            RuleConfigRecord.project_id == project_id,
            RuleConfigRecord.rule_family == rule_family,
        )
    )
    return result.scalar_one_or_none()


async def delete_rule_config(
    db: AsyncSession,
    *,
    project_id: int,
    rule_family: str,
    rule_id: int,
    expected_optimistic_lock_version: int,
) -> None:
    """硬删除当前项目的一条查询规则及其版本历史。"""
    record = await require_rule_config_by_id(
        db,
        project_id=project_id,
        rule_family=rule_family,
        rule_id=rule_id,
    )
    _ensure_expected_lock(record, expected_optimistic_lock_version)
    await db.execute(
        delete(RuleConfigVersionRecord).where(
            RuleConfigVersionRecord.rule_config_id == record.id
        )
    )
    await db.delete(record)
    await db.commit()


async def require_rule_config_by_id(
    db: AsyncSession,
    *,
    project_id: int,
    rule_family: str,
    rule_id: int,
) -> RuleConfigRecord:
    """读取规则，不存在则返回 404。"""
    record = await get_rule_config_by_id(
        db,
        project_id=project_id,
        rule_family=rule_family,
        rule_id=rule_id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="规则不存在")
    return record


async def create_rule_config(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    rule_family: str,
    content_md: str,
    description: str = "",
) -> RuleConfigMutationResult:
    """创建单条查询规则草稿。"""
    validation = await validate_rule_config_content(
        db,
        project_id=project_id,
        rule_family=rule_family,
        content_md=content_md,
    )
    validation = await _validate_query_type_constraints(
        db,
        project_id=project_id,
        rule_family=rule_family,
        validation=validation,
        record=None,
    )
    if not validation.ok:
        raise RuleConfigValidationError(validation)

    query_type = _extract_query_type(validation.parsed_config_json)
    parsed_json = json.dumps(validation.parsed_config_json, ensure_ascii=False)
    record = RuleConfigRecord(
        project_id=project_id,
        rule_family=rule_family,
        query_type=query_type,
        content_md=content_md,
        parsed_config_json=parsed_json,
        status="draft",
        draft_version=1,
        created_by=user_id,
        updated_by=user_id,
        optimistic_lock_version=1,
    )
    try:
        db.add(record)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        _raise_query_type_duplicate(query_type)
        raise exc
    await db.refresh(record)
    return RuleConfigMutationResult(record=record, validation=validation)


async def save_rule_config_draft(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    rule_family: str,
    rule_id: int,
    mutation: RuleConfigMutation,
) -> RuleConfigMutationResult:
    """保存当前草稿，不写入发布历史。"""
    record = await require_rule_config_by_id(
        db,
        project_id=project_id,
        rule_family=rule_family,
        rule_id=rule_id,
    )
    _ensure_expected_lock(record, mutation.expected_optimistic_lock_version)
    validation = await validate_rule_config_content(
        db,
        project_id=project_id,
        rule_family=rule_family,
        content_md=mutation.content_md,
    )
    validation = await _validate_query_type_constraints(
        db,
        project_id=project_id,
        rule_family=rule_family,
        validation=validation,
        record=record,
    )
    if not validation.ok:
        raise RuleConfigValidationError(validation)
    record = await _save_current_draft(
        db,
        record=record,
        user_id=user_id,
        content_md=mutation.content_md,
        parsed_config=validation.parsed_config_json,
    )
    return RuleConfigMutationResult(record=record, validation=validation)


async def publish_rule_config(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    rule_family: str,
    rule_id: int,
    mutation: RuleConfigMutation,
) -> RuleConfigMutationResult:
    """发布规则配置并写入版本历史。"""
    record = await require_rule_config_by_id(
        db,
        project_id=project_id,
        rule_family=rule_family,
        rule_id=rule_id,
    )
    _ensure_expected_lock(record, mutation.expected_optimistic_lock_version)
    validation = await validate_rule_config_content(
        db,
        project_id=project_id,
        rule_family=rule_family,
        content_md=mutation.content_md,
    )
    validation = await _validate_query_type_constraints(
        db,
        project_id=project_id,
        rule_family=rule_family,
        validation=validation,
        record=record,
    )
    if not validation.ok:
        raise RuleConfigValidationError(validation)
    record = await _mutate_rule_config(
        db,
        record=record,
        user_id=user_id,
        content_md=mutation.content_md,
        parsed_config=validation.parsed_config_json,
        action="publish",
        description=mutation.description,
    )
    return RuleConfigMutationResult(record=record, validation=validation)


async def validate_rule_config_content(
    db: AsyncSession,
    *,
    project_id: int,
    rule_family: str,
    content_md: str,
) -> RuleConfigValidationResult:
    """校验规则配置内容，不产生版本或持久化副作用。"""
    ensure_supported_rule_family(rule_family)
    enabled_aliases = await list_enabled_project_query_root_aliases(
        db,
        project_id=project_id,
    )
    return validate_config_lookup_markdown(
        content_md,
        allowed_query_roots=enabled_aliases,
    )


async def validate_rule_config_content_for_record(
    db: AsyncSession,
    *,
    project_id: int,
    rule_family: str,
    rule_id: int,
    content_md: str,
) -> RuleConfigValidationResult:
    """校验指定规则内容，并包含 query_type 唯一性与改名约束。"""
    record = await require_rule_config_by_id(
        db,
        project_id=project_id,
        rule_family=rule_family,
        rule_id=rule_id,
    )
    validation = await validate_rule_config_content(
        db,
        project_id=project_id,
        rule_family=rule_family,
        content_md=content_md,
    )
    return await _validate_query_type_constraints(
        db,
        project_id=project_id,
        rule_family=rule_family,
        validation=validation,
        record=record,
    )


async def list_enabled_project_query_root_aliases(
    db: AsyncSession,
    *,
    project_id: int,
) -> set[str]:
    """读取项目已启用 query_roots alias。"""
    result = await db.execute(
        select(ProjectQueryRootRecord.alias).where(
            ProjectQueryRootRecord.project_id == project_id,
            ProjectQueryRootRecord.status == "enabled",
        )
    )
    return set(result.scalars().all())


async def list_rule_config_versions(
    db: AsyncSession,
    *,
    project_id: int,
    rule_family: str,
    rule_id: int,
) -> list[RuleConfigVersionRecord]:
    """按版本号倒序读取指定规则发布历史。"""
    await require_rule_config_by_id(
        db,
        project_id=project_id,
        rule_family=rule_family,
        rule_id=rule_id,
    )
    result = await db.execute(
        select(RuleConfigVersionRecord)
        .where(
            RuleConfigVersionRecord.rule_config_id == rule_id,
            RuleConfigVersionRecord.status == "published",
        )
        .order_by(RuleConfigVersionRecord.version.desc())
    )
    return list(result.scalars().all())


async def rollback_rule_config_version(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    rule_family: str,
    rule_id: int,
    version: int,
    expected_optimistic_lock_version: int,
    description: str = "",
) -> RuleConfigRecord:
    """把已发布历史版本复制到当前草稿，不写入发布历史。"""
    record = await require_rule_config_by_id(
        db,
        project_id=project_id,
        rule_family=rule_family,
        rule_id=rule_id,
    )
    _ensure_expected_lock(record, expected_optimistic_lock_version)
    source_result = await db.execute(
        select(RuleConfigVersionRecord).where(
            RuleConfigVersionRecord.rule_config_id == rule_id,
            RuleConfigVersionRecord.version == version,
            RuleConfigVersionRecord.status == "published",
        )
    )
    source = source_result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="历史版本不存在")

    parsed_config = _parse_json_object(source.parsed_config_json)
    validation = RuleConfigValidationResult(
        ok=True,
        parsed_config_json=parsed_config,
        errors=[],
        summary={},
    )
    validation = await _validate_query_type_constraints(
        db,
        project_id=project_id,
        rule_family=rule_family,
        validation=validation,
        record=record,
    )
    if not validation.ok:
        raise RuleConfigValidationError(validation)
    return await _save_current_draft(
        db,
        record=record,
        user_id=user_id,
        content_md=source.content_md,
        parsed_config=parsed_config,
    )


async def load_published_rule_config(
    db: AsyncSession,
    *,
    project_id: int,
    query_type: str,
    rule_family: str = SUPPORTED_RULE_FAMILY,
) -> dict[str, Any] | None:
    """读取运行时应消费的指定查询类型已发布规则 JSON。"""
    ensure_supported_rule_family(rule_family)
    result = await db.execute(
        select(RuleConfigRecord).where(
            RuleConfigRecord.project_id == project_id,
            RuleConfigRecord.rule_family == rule_family,
            RuleConfigRecord.query_type == query_type,
        )
    )
    record = result.scalar_one_or_none()
    if record is None or record.published_version is None:
        return None
    version_result = await db.execute(
        select(RuleConfigVersionRecord).where(
            RuleConfigVersionRecord.rule_config_id == record.id,
            RuleConfigVersionRecord.version == record.published_version,
            RuleConfigVersionRecord.status == "published",
        )
    )
    version_record = version_result.scalar_one_or_none()
    if version_record is None:
        return None
    return _parse_json_object(version_record.parsed_config_json)


async def has_any_published_rule_config(
    db: AsyncSession,
    *,
    project_id: int,
    rule_family: str = SUPPORTED_RULE_FAMILY,
) -> bool:
    """判断当前项目是否存在任何已发布规则。"""
    ensure_supported_rule_family(rule_family)
    result = await db.execute(
        select(RuleConfigRecord.id)
        .where(
            RuleConfigRecord.project_id == project_id,
            RuleConfigRecord.rule_family == rule_family,
            RuleConfigRecord.published_version.is_not(None),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _save_current_draft(
    db: AsyncSession,
    *,
    record: RuleConfigRecord,
    user_id: int,
    content_md: str,
    parsed_config: dict[str, Any],
) -> RuleConfigRecord:
    query_type = _extract_query_type(parsed_config)
    parsed_json = json.dumps(parsed_config, ensure_ascii=False)

    record.query_type = query_type
    record.content_md = content_md
    record.parsed_config_json = parsed_json
    record.status = "draft"
    record.draft_version = _next_draft_version(record)
    record.updated_by = user_id
    record.optimistic_lock_version += 1

    db.add(record)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        _raise_query_type_duplicate(query_type)
        raise exc
    await db.refresh(record)
    return record


async def _mutate_rule_config(
    db: AsyncSession,
    *,
    record: RuleConfigRecord,
    user_id: int,
    content_md: str,
    parsed_config: dict[str, Any],
    action: RuleConfigAction,
    description: str,
) -> RuleConfigRecord:
    query_type = _extract_query_type(parsed_config)
    version = await _next_version(db, rule_config_id=record.id)
    parsed_json = json.dumps(parsed_config, ensure_ascii=False)

    record.query_type = query_type
    record.content_md = content_md
    record.parsed_config_json = parsed_json
    record.status = "published"
    record.draft_version = version
    record.published_version = version
    record.published_by = user_id
    record.published_at = func.now()
    record.updated_by = user_id
    record.optimistic_lock_version += 1

    db.add(record)
    db.add(
        RuleConfigVersionRecord(
            rule_config_id=record.id,
            project_id=record.project_id,
            rule_family=record.rule_family,
            query_type=query_type,
            version=version,
            content_md=content_md,
            parsed_config_json=parsed_json,
            status="published",
            action=action,
            operator=user_id,
            description=description,
        )
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        _raise_query_type_duplicate(query_type)
        raise exc
    await db.refresh(record)
    return record


def _next_draft_version(record: RuleConfigRecord) -> int:
    if record.published_version is None:
        return 1
    if record.status == "draft" and record.draft_version > record.published_version:
        return record.draft_version
    return record.published_version + 1


async def _validate_query_type_constraints(
    db: AsyncSession,
    *,
    project_id: int,
    rule_family: str,
    validation: RuleConfigValidationResult,
    record: RuleConfigRecord | None,
) -> RuleConfigValidationResult:
    if not validation.ok:
        return validation
    query_type = _extract_query_type(validation.parsed_config_json)
    errors = list(validation.errors)

    if record is not None and record.published_version is not None:
        if query_type != record.query_type:
            errors.append("已发布过的查询类型不允许直接改名")

    duplicate = await _find_rule_by_query_type(
        db,
        project_id=project_id,
        rule_family=rule_family,
        query_type=query_type,
    )
    if duplicate is not None and (record is None or duplicate.id != record.id):
        errors.append(f"查询类型已存在：{query_type}")

    if not errors:
        return validation
    return RuleConfigValidationResult(
        ok=False,
        parsed_config_json=validation.parsed_config_json,
        errors=errors,
        summary=validation.summary,
    )


async def _find_rule_by_query_type(
    db: AsyncSession,
    *,
    project_id: int,
    rule_family: str,
    query_type: str,
) -> RuleConfigRecord | None:
    result = await db.execute(
        select(RuleConfigRecord).where(
            RuleConfigRecord.project_id == project_id,
            RuleConfigRecord.rule_family == rule_family,
            RuleConfigRecord.query_type == query_type,
        )
    )
    return result.scalar_one_or_none()


def _ensure_expected_lock(
    record: RuleConfigRecord,
    expected_optimistic_lock_version: int,
) -> None:
    if record.optimistic_lock_version != expected_optimistic_lock_version:
        _raise_version_conflict(record.optimistic_lock_version)


async def _next_version(
    db: AsyncSession,
    *,
    rule_config_id: int,
) -> int:
    result = await db.execute(
        select(func.max(RuleConfigVersionRecord.version)).where(
            RuleConfigVersionRecord.rule_config_id == rule_config_id,
        )
    )
    current_max = result.scalar_one_or_none()
    return int(current_max or 0) + 1


def _extract_query_type(parsed_config: dict[str, Any]) -> str:
    query_type = str(parsed_config.get("query_type") or "").strip()
    if not query_type:
        raise HTTPException(status_code=400, detail="查询类型不能为空")
    return query_type


def _raise_version_conflict(current_lock: int) -> None:
    raise HTTPException(
        status_code=409,
        detail={
            "code": RULE_CONFIG_VERSION_CONFLICT,
            "current_optimistic_lock_version": current_lock,
        },
    )


def _raise_query_type_duplicate(query_type: str) -> None:
    raise HTTPException(status_code=400, detail=f"查询类型已存在：{query_type}")


def _parse_json_object(raw_json: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_json or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
