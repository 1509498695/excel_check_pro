"""规则配置存储、版本与发布服务。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import RuleConfigRecord, RuleConfigVersionRecord
from backend.app.rule_configs.parser import parse_config_lookup_markdown


SUPPORTED_RULE_FAMILY = "config_lookup"
RULE_CONFIG_VERSION_CONFLICT = "RULE_CONFIG_VERSION_CONFLICT"
RuleConfigAction = Literal["save_draft", "publish", "rollback"]


@dataclass(frozen=True)
class RuleConfigMutation:
    """规则配置变更请求。"""

    content_md: str
    expected_optimistic_lock_version: int
    description: str = ""


def ensure_supported_rule_family(rule_family: str) -> str:
    """第一阶段仅允许 config_lookup。"""
    if rule_family != SUPPORTED_RULE_FAMILY:
        raise HTTPException(status_code=400, detail="当前仅支持 rule_family=config_lookup")
    return rule_family


async def get_current_rule_config(
    db: AsyncSession,
    *,
    project_id: int,
    rule_family: str,
) -> RuleConfigRecord | None:
    """读取当前规则配置记录。"""
    ensure_supported_rule_family(rule_family)
    result = await db.execute(
        select(RuleConfigRecord).where(
            RuleConfigRecord.project_id == project_id,
            RuleConfigRecord.rule_family == rule_family,
        )
    )
    return result.scalar_one_or_none()


async def save_rule_config_draft(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    rule_family: str,
    mutation: RuleConfigMutation,
) -> RuleConfigRecord:
    """保存草稿并写入版本历史。"""
    parsed_config = parse_config_lookup_markdown(mutation.content_md)
    return await _mutate_rule_config(
        db,
        project_id=project_id,
        user_id=user_id,
        rule_family=rule_family,
        content_md=mutation.content_md,
        parsed_config=parsed_config,
        expected_optimistic_lock_version=mutation.expected_optimistic_lock_version,
        action="save_draft",
        description=mutation.description,
    )


async def publish_rule_config(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    rule_family: str,
    mutation: RuleConfigMutation,
) -> RuleConfigRecord:
    """发布规则配置并写入版本历史。"""
    parsed_config = parse_config_lookup_markdown(mutation.content_md)
    return await _mutate_rule_config(
        db,
        project_id=project_id,
        user_id=user_id,
        rule_family=rule_family,
        content_md=mutation.content_md,
        parsed_config=parsed_config,
        expected_optimistic_lock_version=mutation.expected_optimistic_lock_version,
        action="publish",
        description=mutation.description,
    )


async def list_rule_config_versions(
    db: AsyncSession,
    *,
    project_id: int,
    rule_family: str,
) -> list[RuleConfigVersionRecord]:
    """按版本号倒序读取版本历史。"""
    ensure_supported_rule_family(rule_family)
    result = await db.execute(
        select(RuleConfigVersionRecord)
        .where(
            RuleConfigVersionRecord.project_id == project_id,
            RuleConfigVersionRecord.rule_family == rule_family,
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
    version: int,
    expected_optimistic_lock_version: int,
    description: str = "",
) -> RuleConfigRecord:
    """回滚到历史版本，生成新的草稿版本。"""
    ensure_supported_rule_family(rule_family)
    source_result = await db.execute(
        select(RuleConfigVersionRecord).where(
            RuleConfigVersionRecord.project_id == project_id,
            RuleConfigVersionRecord.rule_family == rule_family,
            RuleConfigVersionRecord.version == version,
        )
    )
    source = source_result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="历史版本不存在")

    parsed_config = _parse_json_object(source.parsed_config_json)
    return await _mutate_rule_config(
        db,
        project_id=project_id,
        user_id=user_id,
        rule_family=rule_family,
        content_md=source.content_md,
        parsed_config=parsed_config,
        expected_optimistic_lock_version=expected_optimistic_lock_version,
        action="rollback",
        description=description or f"回滚到 v{version}",
    )


async def load_published_rule_config(
    db: AsyncSession,
    *,
    project_id: int,
    rule_family: str = SUPPORTED_RULE_FAMILY,
) -> dict[str, Any] | None:
    """读取机器人运行时应消费的已发布规则 JSON。"""
    record = await get_current_rule_config(
        db,
        project_id=project_id,
        rule_family=rule_family,
    )
    if record is None or record.published_version is None:
        return None
    version_result = await db.execute(
        select(RuleConfigVersionRecord).where(
            RuleConfigVersionRecord.project_id == project_id,
            RuleConfigVersionRecord.rule_family == rule_family,
            RuleConfigVersionRecord.version == record.published_version,
            RuleConfigVersionRecord.status == "published",
        )
    )
    version_record = version_result.scalar_one_or_none()
    if version_record is None:
        return None
    return _parse_json_object(version_record.parsed_config_json)


async def _mutate_rule_config(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    rule_family: str,
    content_md: str,
    parsed_config: dict[str, Any],
    expected_optimistic_lock_version: int,
    action: RuleConfigAction,
    description: str,
) -> RuleConfigRecord:
    ensure_supported_rule_family(rule_family)
    record = await get_current_rule_config(
        db,
        project_id=project_id,
        rule_family=rule_family,
    )
    current_lock = record.optimistic_lock_version if record is not None else 0
    if current_lock != expected_optimistic_lock_version:
        _raise_version_conflict(current_lock)

    version = await _next_version(db, project_id=project_id, rule_family=rule_family)
    status = "published" if action == "publish" else "draft"
    parsed_json = json.dumps(parsed_config, ensure_ascii=False)

    if record is None:
        record = RuleConfigRecord(
            project_id=project_id,
            rule_family=rule_family,
            created_by=user_id,
        )
    record.content_md = content_md
    record.parsed_config_json = parsed_json
    record.status = status
    record.draft_version = version
    record.updated_by = user_id
    record.optimistic_lock_version = current_lock + 1
    if action == "publish":
        record.published_version = version
        record.published_by = user_id
        record.published_at = func.now()

    db.add(record)
    db.add(
        RuleConfigVersionRecord(
            project_id=project_id,
            rule_family=rule_family,
            version=version,
            content_md=content_md,
            parsed_config_json=parsed_json,
            status=status,
            action=action,
            operator=user_id,
            description=description,
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        record = await get_current_rule_config(
            db,
            project_id=project_id,
            rule_family=rule_family,
        )
        _raise_version_conflict(record.optimistic_lock_version if record else 0)
    await db.refresh(record)
    return record


async def _next_version(
    db: AsyncSession,
    *,
    project_id: int,
    rule_family: str,
) -> int:
    result = await db.execute(
        select(func.max(RuleConfigVersionRecord.version)).where(
            RuleConfigVersionRecord.project_id == project_id,
            RuleConfigVersionRecord.rule_family == rule_family,
        )
    )
    current_max = result.scalar_one_or_none()
    return int(current_max or 0) + 1


def _raise_version_conflict(current_lock: int) -> None:
    raise HTTPException(
        status_code=409,
        detail={
            "code": RULE_CONFIG_VERSION_CONFLICT,
            "current_optimistic_lock_version": current_lock,
        },
    )


def _parse_json_object(raw_json: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_json or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
