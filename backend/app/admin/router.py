"""管理后台路由：项目 CRUD、成员管理。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.admin.schemas import (
    FeishuBotConfigUpdateRequest,
    FeishuBotTestSendRequest,
    MoveMemberProjectRequest,
    ProjectAiConfigRequest,
    ProjectCreateRequest,
    SourceEvidenceSvnRootsUpdateRequest,
    ProjectUpdateRequest,
    ProjectVisionAiConfigRequest,
    ResetUserPasswordRequest,
    SetMemberRoleRequest,
)
from backend.app.auth.dependencies import CurrentUserContext, get_current_user
from backend.app.auth.service import hash_password
from backend.app.ai.credentials import sanitize_ai_error
from backend.app.ai.providers import (
    ProviderConnectionError,
    mask_api_key,
    resolve_provider_defaults,
    test_provider_connection,
    test_provider_vision_connection,
)
from backend.app.database import get_db
from backend.app.integrations.feishu_bot import (
    FeishuApiError,
    invalidate_token_cache,
    send_card_to_chat,
    send_text_to_chat,
)
from backend.app.integrations.feishu_long_conn import long_conn_supervisor
from backend.app.loaders.svn_credentials import SvnCredential
from backend.app.loaders.svn_manager import (
    SvnRemoteError,
    enforce_host_allowlist,
    list_svn_directory,
    normalize_dir_url,
)
from backend.app.models import (
    FeishuBotBoundChatRecord,
    FeishuBotConfigRecord,
    FixedRulesConfigRecord,
    Project,
    ProjectAiCredentialRecord,
    ProjectQueryRootRecord,
    ProjectSourceEvidenceSvnRootRecord,
    ProjectSvnCredentialRecord,
    ProjectVisionAiCredentialRecord,
    RuleConfigRecord,
    RuleConfigVersionRecord,
    User,
    UserProjectRole,
    WorkbenchConfigRecord,
)
from backend.app.security.crypto import decrypt_secret, encrypt_secret


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/admin", tags=["admin"])

DEFAULT_PROJECT_NAME = "默认项目"
DEFAULT_FEISHU_DOWNLOAD_SUFFIXES = [".xls", ".xlsx", ".csv", ".json", ".xml", ".txt"]


async def _get_project_or_404(db: AsyncSession, project_id: int) -> Project:
    """按项目 ID 获取项目，不存在时抛出 404。"""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


async def _get_default_project_or_500(db: AsyncSession) -> Project:
    """获取系统默认项目，不存在时视为服务端配置异常。"""
    result = await db.execute(
        select(Project).where(Project.name == DEFAULT_PROJECT_NAME)
    )
    default_project = result.scalar_one_or_none()
    if default_project is None:
        raise HTTPException(status_code=500, detail="默认项目不存在，请先初始化系统默认项目")
    return default_project


def _ensure_project_deletable(project: Project) -> None:
    """默认项目不可删除，避免破坏系统默认空间。"""
    if project.name == DEFAULT_PROJECT_NAME:
        raise HTTPException(status_code=400, detail="默认项目不可删除")


def _has_any_project_admin_role(ctx: CurrentUserContext) -> bool:
    """判断用户是否在任一项目中具备项目管理员权限。"""
    if ctx.is_super_admin:
        return True
    return any(role.role == "admin" for role in ctx.user.roles)


def _require_project_management_access(
    ctx: CurrentUserContext,
    project_id: int,
) -> None:
    """要求用户对指定项目具备管理权限。"""
    if ctx.is_super_admin:
        return
    if ctx.role_in_project(project_id) != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")


def _require_admin_member_access(
    ctx: CurrentUserContext,
    project: Project,
) -> None:
    """成员治理访问控制：默认项目对任一项目管理员开放，普通项目按原权限模型处理。"""
    if project.name == DEFAULT_PROJECT_NAME:
        if _has_any_project_admin_role(ctx):
            return
        raise HTTPException(status_code=403, detail="需要管理员权限")

    _require_project_management_access(ctx, project.id)


@router.get("/projects")
async def list_projects(
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """列出所有项目（仅管理员可用）。"""
    member_count_subquery = (
        select(
            UserProjectRole.project_id.label("project_id"),
            func.count(UserProjectRole.user_id).label("member_count"),
        )
        .group_by(UserProjectRole.project_id)
        .subquery()
    )
    member_count_column = func.coalesce(
        member_count_subquery.c.member_count,
        0,
    ).label("member_count")

    if ctx.is_super_admin:
        stmt = (
            select(Project, member_count_column)
            .outerjoin(
                member_count_subquery,
                member_count_subquery.c.project_id == Project.id,
            )
            .order_by(Project.id)
        )
    else:
        stmt = (
            select(Project, member_count_column)
            .join(UserProjectRole, UserProjectRole.project_id == Project.id)
            .outerjoin(
                member_count_subquery,
                member_count_subquery.c.project_id == Project.id,
            )
            .where(
                UserProjectRole.user_id == ctx.user_id,
                UserProjectRole.role == "admin",
            )
            .order_by(Project.id)
        )
    result = await db.execute(stmt)
    project_rows = [
        (project, int(member_count or 0))
        for project, member_count in result.all()
    ]

    if not ctx.is_super_admin and _has_any_project_admin_role(ctx):
        default_project_result = await db.execute(
            select(Project, member_count_column)
            .outerjoin(
                member_count_subquery,
                member_count_subquery.c.project_id == Project.id,
            )
            .where(Project.name == DEFAULT_PROJECT_NAME)
        )
        default_project_row = default_project_result.one_or_none()
        if default_project_row is not None:
            default_project, member_count = default_project_row
            if all(project.id != default_project.id for project, _ in project_rows):
                project_rows.append((default_project, int(member_count or 0)))

    project_rows.sort(key=lambda row: row[0].id)
    return {
        "code": 200,
        "msg": "ok",
        "data": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "member_count": member_count,
            }
            for p, member_count in project_rows
        ],
    }


@router.post("/projects")
async def create_project(
    payload: ProjectCreateRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """创建新项目（仅超级管理员）。"""
    ctx.require_super_admin()

    normalized_name = payload.name.strip()
    existing = await db.execute(select(Project).where(Project.name == normalized_name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"项目名 '{normalized_name}' 已存在")

    project = Project(name=normalized_name, description=payload.description)
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return {
        "code": 200,
        "msg": "项目创建成功",
        "data": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "created_at": project.created_at.isoformat() if project.created_at else None,
        },
    }


@router.put("/projects/{project_id}")
async def update_project(
    project_id: int,
    payload: ProjectUpdateRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """更新项目信息。"""
    _require_project_management_access(ctx, project_id)

    project = await _get_project_or_404(db, project_id)

    if payload.name is not None:
        normalized_name = payload.name.strip()
        existing = await db.execute(
            select(Project).where(
                Project.name == normalized_name,
                Project.id != project_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"项目名 '{normalized_name}' 已存在")
        project.name = normalized_name
    if payload.description is not None:
        project.description = payload.description

    db.add(project)
    await db.commit()
    await db.refresh(project)

    return {
        "code": 200,
        "msg": "项目更新成功",
        "data": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
        },
    }


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """删除普通项目前先迁移成员到默认项目，再清理项目级数据。"""
    ctx.require_super_admin()

    project = await _get_project_or_404(db, project_id)
    _ensure_project_deletable(project)
    default_project = await _get_default_project_or_500(db)

    memberships_result = await db.execute(
        select(UserProjectRole).where(UserProjectRole.project_id == project_id)
    )
    memberships = memberships_result.scalars().all()

    default_memberships_result = await db.execute(
        select(UserProjectRole).where(UserProjectRole.project_id == default_project.id)
    )
    existing_default_memberships = {
        membership.user_id: membership
        for membership in default_memberships_result.scalars().all()
    }

    for membership in memberships:
        if membership.user_id in existing_default_memberships:
            continue
        db.add(
            UserProjectRole(
                user_id=membership.user_id,
                project_id=default_project.id,
                role="user",
            )
        )
    migrated_user_ids = [membership.user_id for membership in memberships]
    if migrated_user_ids:
        await db.execute(
            update(User)
            .where(User.id.in_(migrated_user_ids))
            .values(primary_project_id=default_project.id)
        )

    # SQLite 测试环境默认不会可靠触发所有外键级联，这里显式清理项目级记录，
    # 保证删除行为与业务预期一致。
    await db.execute(
        delete(FixedRulesConfigRecord).where(
            FixedRulesConfigRecord.project_id == project_id
        )
    )
    await db.execute(
        delete(WorkbenchConfigRecord).where(
            WorkbenchConfigRecord.project_id == project_id
        )
    )
    await db.execute(
        delete(RuleConfigVersionRecord).where(
            RuleConfigVersionRecord.project_id == project_id
        )
    )
    await db.execute(
        delete(RuleConfigRecord).where(
            RuleConfigRecord.project_id == project_id
        )
    )
    await db.execute(
        delete(ProjectQueryRootRecord).where(
            ProjectQueryRootRecord.project_id == project_id
        )
    )
    await db.execute(
        delete(ProjectSourceEvidenceSvnRootRecord).where(
            ProjectSourceEvidenceSvnRootRecord.project_id == project_id
        )
    )
    await db.execute(
        delete(FeishuBotBoundChatRecord).where(
            FeishuBotBoundChatRecord.project_id == project_id
        )
    )
    await db.execute(
        delete(ProjectSvnCredentialRecord).where(
            ProjectSvnCredentialRecord.project_id == project_id
        )
    )
    await db.execute(
        delete(ProjectAiCredentialRecord).where(
            ProjectAiCredentialRecord.project_id == project_id
        )
    )
    await db.delete(project)
    await db.commit()
    return Response(status_code=204)


@router.get("/projects/{project_id}/members")
async def list_project_members(
    project_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """查看项目成员列表。超级管理员或项目管理员可用。"""
    project = await _get_project_or_404(db, project_id)
    _require_admin_member_access(ctx, project)

    result = await db.execute(
        select(UserProjectRole)
        .where(UserProjectRole.project_id == project_id)
        .options(
            selectinload(UserProjectRole.user)
            .selectinload(User.roles)
            .selectinload(UserProjectRole.project)
        )
        .order_by(UserProjectRole.joined_at)
    )
    members = result.scalars().all()

    return {
        "code": 200,
        "msg": "ok",
        "data": [
            {
                "user_id": m.user.id,
                "username": m.user.username,
                "role": m.role,
                "is_super_admin": m.user.is_super_admin,
                "primary_project_id": m.user.primary_project_id,
                "primary_project_name": next(
                    (
                        role.project.name
                        for role in m.user.roles
                        if role.project_id == m.user.primary_project_id
                    ),
                    None,
                ),
                "joined_at": m.joined_at.isoformat() if m.joined_at else None,
            }
            for m in members
        ],
    }


@router.put("/projects/{project_id}/members/{user_id}/role")
async def set_member_role(
    project_id: int,
    user_id: int,
    payload: SetMemberRoleRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """设置成员角色（设为管理员 / 普通用户）。"""
    project = await _get_project_or_404(db, project_id)
    _require_admin_member_access(ctx, project)

    result = await db.execute(
        select(UserProjectRole)
        .where(
            UserProjectRole.project_id == project_id,
            UserProjectRole.user_id == user_id,
        )
        .options(selectinload(UserProjectRole.user))
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="该用户不属于此项目")
    if membership.user.is_super_admin:
        raise HTTPException(status_code=400, detail="超级管理员角色不可调整")

    membership.role = payload.role
    db.add(membership)
    if membership.user.primary_project_id is None:
        membership.user.primary_project_id = project_id
        db.add(membership.user)
    await db.commit()

    return {"code": 200, "msg": f"已将用户角色设为 {payload.role}"}


@router.put("/projects/{project_id}/members/{user_id}/project")
async def move_member_project(
    project_id: int,
    user_id: int,
    payload: MoveMemberProjectRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """调整普通用户的归属项目。"""
    source_project = await _get_project_or_404(db, project_id)
    target_project = await _get_project_or_404(db, payload.target_project_id)
    _require_admin_member_access(ctx, source_project)

    result = await db.execute(
        select(UserProjectRole)
        .where(
            UserProjectRole.project_id == project_id,
            UserProjectRole.user_id == user_id,
        )
        .options(selectinload(UserProjectRole.user))
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="该用户不属于此项目")

    user = membership.user
    if user.is_super_admin:
        if not (ctx.is_super_admin and user_id == ctx.user_id):
            raise HTTPException(status_code=403, detail="无权调整超级管理员归属项目")

        memberships_result = await db.execute(
            select(UserProjectRole)
            .where(UserProjectRole.user_id == user_id)
            .order_by(UserProjectRole.id)
        )
        memberships = memberships_result.scalars().all()
        target_membership = next(
            (item for item in memberships if item.project_id == payload.target_project_id),
            None,
        )

        if payload.target_project_id == membership.project_id:
            user.primary_project_id = payload.target_project_id
            db.add(user)
            await db.commit()
            return {"code": 200, "msg": "归属项目未发生变化"}

        if target_membership is None:
            db.add(
                UserProjectRole(
                    user_id=user_id,
                    project_id=payload.target_project_id,
                    role="admin",
                )
            )

        user.primary_project_id = payload.target_project_id
        db.add(user)
        await db.commit()
        return {"code": 200, "msg": "归属项目已更新"}

    _require_admin_member_access(ctx, target_project)

    memberships_result = await db.execute(
        select(UserProjectRole)
        .where(UserProjectRole.user_id == user_id)
        .order_by(UserProjectRole.id)
    )
    memberships = memberships_result.scalars().all()
    if any(item.role == "admin" for item in memberships):
        raise HTTPException(status_code=400, detail="项目管理员的归属项目不可调整")

    if payload.target_project_id == membership.project_id:
        user.primary_project_id = payload.target_project_id
        db.add(user)
        await db.commit()
        return {"code": 200, "msg": "归属项目未发生变化"}

    for item in memberships:
        await db.delete(item)

    db.add(
        UserProjectRole(
            user_id=user_id,
            project_id=payload.target_project_id,
            role="user",
        )
    )
    user.primary_project_id = payload.target_project_id
    db.add(user)
    await db.commit()
    return {"code": 200, "msg": "归属项目已更新"}


@router.delete("/projects/{project_id}/members/{user_id}")
async def remove_member(
    project_id: int,
    user_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """将成员从项目中移除。"""
    project = await _get_project_or_404(db, project_id)
    _require_admin_member_access(ctx, project)

    if project.name == DEFAULT_PROJECT_NAME and not ctx.is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="默认项目中的成员删除仅限超级管理员",
        )

    if user_id == ctx.user_id:
        raise HTTPException(status_code=400, detail="不能删除自己")

    result = await db.execute(
        select(UserProjectRole)
        .where(
            UserProjectRole.project_id == project_id,
            UserProjectRole.user_id == user_id,
        )
        .options(selectinload(UserProjectRole.user))
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="该用户不属于此项目")

    if project.name == DEFAULT_PROJECT_NAME:
        if membership.user.is_super_admin:
            raise HTTPException(status_code=400, detail="默认项目中的超级管理员不可删除")
        await db.execute(
            delete(WorkbenchConfigRecord).where(WorkbenchConfigRecord.user_id == user_id)
        )
        await db.delete(membership.user)
        await db.commit()
        return {"code": 200, "msg": "用户账号已删除"}

    default_project = await _get_default_project_or_500(db)
    default_membership_result = await db.execute(
        select(UserProjectRole).where(
            UserProjectRole.project_id == default_project.id,
            UserProjectRole.user_id == user_id,
        )
    )
    default_membership = default_membership_result.scalar_one_or_none()
    if default_membership is None:
        db.add(
            UserProjectRole(
                user_id=user_id,
                project_id=default_project.id,
                role="user",
            )
        )

    membership.user.primary_project_id = default_project.id
    db.add(membership.user)
    await db.delete(membership)
    await db.commit()
    return {"code": 200, "msg": "成员已移入默认项目"}


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    payload: ResetUserPasswordRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """由超级管理员重置任意用户的登录密码（用于用户忘记密码等场景）。"""
    ctx.require_super_admin()

    if user_id == ctx.user_id:
        raise HTTPException(status_code=400, detail="不能在此处重置自己的密码，请使用个人中心「修改密码」")

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.hashed_password = hash_password(payload.new_password)
    db.add(user)
    await db.commit()

    return {"code": 200, "msg": "密码已重置"}


@router.get("/projects-public")
async def list_projects_public(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """公开接口：返回项目列表（仅 id + name），供注册页下拉选择。"""
    result = await db.execute(select(Project).order_by(Project.id))
    projects = result.scalars().all()
    return {
        "code": 200,
        "msg": "ok",
        "data": [{"id": p.id, "name": p.name} for p in projects],
    }


@router.get("/projects/{project_id}/feishu-bot")
async def get_feishu_bot_config(
    project_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """读取项目级飞书机器人配置（脱敏）。"""
    _require_project_management_access(ctx, project_id)
    await _get_project_or_404(db, project_id)

    result = await db.execute(
        select(FeishuBotConfigRecord).where(
            FeishuBotConfigRecord.project_id == project_id
        )
    )
    record = result.scalar_one_or_none()
    data = await _serialize_feishu_bot_config(db, record, project_id=project_id)
    # connection_state 由长连接 supervisor 实时维护（inactive/active/error/...）；
    # _serialize_feishu_bot_config 写死的 "inactive" 仅作未配置时的兜底，这里覆写为真实值。
    data["connection_state"] = long_conn_supervisor.get_state(project_id)
    return {"code": 200, "msg": "ok", "data": data}


@router.put("/projects/{project_id}/feishu-bot")
async def upsert_feishu_bot_config(
    project_id: int,
    payload: FeishuBotConfigUpdateRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """创建或更新项目级飞书机器人配置；密钥落库前用 Fernet 加密。"""
    _require_project_management_access(ctx, project_id)
    project = await _get_project_or_404(db, project_id)

    normalized_app_id = payload.app_id.strip()
    if not normalized_app_id:
        raise HTTPException(status_code=400, detail="app_id 不能为空")
    if len(normalized_app_id) > 64:
        raise HTTPException(status_code=400, detail="app_id 长度超过限制")

    record_result = await db.execute(
        select(FeishuBotConfigRecord).where(
            FeishuBotConfigRecord.project_id == project_id
        )
    )
    record = record_result.scalar_one_or_none()
    is_create = record is None

    if payload.app_secret is None:
        if is_create:
            raise HTTPException(
                status_code=400, detail="首次配置时必须提供 app_secret"
            )
        new_app_secret_cipher = record.app_secret_cipher  # type: ignore[union-attr]
        new_app_secret_plain = _decrypt_app_secret_or_400(new_app_secret_cipher)
    else:
        if payload.app_secret == "":
            raise HTTPException(
                status_code=400,
                detail="app_secret 不允许传空串清空，请走 DELETE 整体清除",
            )
        new_app_secret_plain = payload.app_secret
        new_app_secret_cipher = encrypt_secret(payload.app_secret)
    await _ensure_shared_app_secret_consistency(
        db,
        project_id=project_id,
        app_id=normalized_app_id,
        app_secret_plain=new_app_secret_plain,
    )

    if payload.default_chat_id is None:
        new_default_chat_id = "" if is_create else record.default_chat_id  # type: ignore[union-attr]
    else:
        new_default_chat_id = payload.default_chat_id.strip()

    if payload.allowed_open_ids is None:
        new_allowed_open_ids = "" if is_create else record.allowed_open_ids  # type: ignore[union-attr]
    else:
        new_allowed_open_ids = _normalize_allowed_open_ids_input(
            payload.allowed_open_ids
        )

    if payload.local_download_roots is None:
        new_local_download_roots = "[]" if is_create else record.local_download_roots  # type: ignore[union-attr]
    else:
        new_local_download_roots = json.dumps(
            _normalize_download_roots_input(payload.local_download_roots),
            ensure_ascii=False,
        )

    if payload.svn_download_roots is None:
        new_svn_download_roots = "[]" if is_create else record.svn_download_roots  # type: ignore[union-attr]
    else:
        new_svn_download_roots = json.dumps(
            _normalize_download_roots_input(payload.svn_download_roots),
            ensure_ascii=False,
        )

    if payload.allowed_download_suffixes is None:
        new_allowed_download_suffixes = (
            json.dumps(DEFAULT_FEISHU_DOWNLOAD_SUFFIXES, ensure_ascii=False)
            if is_create
            else record.allowed_download_suffixes  # type: ignore[union-attr]
        )
    else:
        new_allowed_download_suffixes = json.dumps(
            _normalize_download_suffixes_input(payload.allowed_download_suffixes),
            ensure_ascii=False,
        )

    existing_bound_chat_ids = (
        [] if is_create else await _list_bound_chat_ids(db, project_id)
    )
    new_bound_chat_ids, should_replace_bound_chats = _resolve_bound_chat_ids(
        payload=payload,
        is_create=is_create,
        default_chat_id=new_default_chat_id,
        existing_bound_chat_ids=existing_bound_chat_ids,
    )
    if should_replace_bound_chats:
        await _ensure_bound_chats_available(
            db,
            project_id=project_id,
            project_name=project.name,
            chat_ids=new_bound_chat_ids,
        )

    if record is None:
        record = FeishuBotConfigRecord(
            project_id=project_id,
            app_id=normalized_app_id,
            app_secret_cipher=new_app_secret_cipher,
            default_chat_id=new_default_chat_id,
            allowed_open_ids=new_allowed_open_ids,
            local_download_roots=new_local_download_roots,
            svn_download_roots=new_svn_download_roots,
            allowed_download_suffixes=new_allowed_download_suffixes,
            auto_match_threshold=_resolve_ai_match_float(
                payload.ai_match_params.auto_match_threshold
                if payload.ai_match_params
                else None,
                default=0.9,
            ),
            candidate_threshold=_resolve_ai_match_float(
                payload.ai_match_params.candidate_threshold
                if payload.ai_match_params
                else None,
                default=0.6,
            ),
            max_candidates=_resolve_ai_match_int(
                payload.ai_match_params.max_candidates
                if payload.ai_match_params
                else None,
                default=10,
            ),
        )
        db.add(record)
    else:
        record.app_id = normalized_app_id
        record.app_secret_cipher = new_app_secret_cipher
        record.default_chat_id = new_default_chat_id
        record.allowed_open_ids = new_allowed_open_ids
        record.local_download_roots = new_local_download_roots
        record.svn_download_roots = new_svn_download_roots
        record.allowed_download_suffixes = new_allowed_download_suffixes
        _apply_ai_match_params(record, payload)
        db.add(record)

    if should_replace_bound_chats:
        await _replace_bound_chats(db, project_id, new_bound_chat_ids)
    if "query_roots" in payload.model_fields_set:
        await _replace_query_roots(db, project_id, payload.query_roots or [])
    if payload.svn_credential is not None:
        await _upsert_project_svn_credential(db, project_id, payload.svn_credential)
    if payload.ai_credential is not None:
        await _upsert_project_ai_credential(db, project_id, payload.ai_credential)
    if payload.ai_credential is not None or payload.ai_match_params is not None:
        ai_record = await _get_project_ai_credential(db, project_id)
        if ai_record is not None:
            ai_record.auto_match_threshold = record.auto_match_threshold
            ai_record.candidate_threshold = record.candidate_threshold
            ai_record.max_candidates = record.max_candidates
            ai_record.updated_by = ctx.user_id
            db.add(ai_record)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=400, detail="配置保存冲突，请重试"
        ) from exc
    await db.refresh(record)

    # app_secret 可能已变更或刚刚配置，先把进程内缓存清理掉，避免 token 残留。
    invalidate_token_cache(project_id)

    # 通知长连接 supervisor 重新拉起对应项目的客户端；reload 内部已对失败做了
    # state=error 兜底，这里只防御 set_session_factory 未初始化等极端场景，避免
    # admin 接口被 supervisor 异常拖成 500。
    try:
        await long_conn_supervisor.reload(project_id, db)
    except Exception:  # noqa: BLE001
        logger.exception(
            "飞书长连接 reload 失败 project_id=%s", project_id
        )

    return {
        "code": 200,
        "msg": "保存成功",
        "data": await _serialize_feishu_bot_config(db, record, project_id=project_id),
    }


@router.delete("/projects/{project_id}/feishu-bot", status_code=204)
async def delete_feishu_bot_config(
    project_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """删除项目级飞书机器人配置；幂等：未配置也返回 204。"""
    _require_project_management_access(ctx, project_id)
    await _get_project_or_404(db, project_id)

    result = await db.execute(
        select(FeishuBotConfigRecord).where(
            FeishuBotConfigRecord.project_id == project_id
        )
    )
    record = result.scalar_one_or_none()
    if record is not None:
        await db.delete(record)
        await db.execute(
            delete(FeishuBotBoundChatRecord).where(
                FeishuBotBoundChatRecord.project_id == project_id
            )
        )
        await db.execute(
            delete(ProjectQueryRootRecord).where(
                ProjectQueryRootRecord.project_id == project_id
            )
        )
        await db.execute(
            delete(ProjectSvnCredentialRecord).where(
                ProjectSvnCredentialRecord.project_id == project_id
            )
        )
        await db.commit()
    invalidate_token_cache(project_id)

    # 不论原本是否存在配置，都通知 supervisor 停掉对应项目的客户端，幂等。
    try:
        await long_conn_supervisor.stop_one(project_id)
    except Exception:  # noqa: BLE001
        logger.exception(
            "飞书长连接 stop_one 失败 project_id=%s", project_id
        )
    return Response(status_code=204)


@router.post("/projects/{project_id}/feishu-bot/test-send")
async def test_send_feishu_bot(
    project_id: int,
    payload: FeishuBotTestSendRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """向指定 chat_id 发送一条测试消息，便于配置完后立即联调。"""
    _require_project_management_access(ctx, project_id)
    await _get_project_or_404(db, project_id)

    chat_id = payload.chat_id.strip()
    if not chat_id:
        raise HTTPException(status_code=400, detail="chat_id 不能为空")
    text_content = payload.text

    try:
        if payload.use_card:
            result = await send_card_to_chat(
                db=db,
                project_id=project_id,
                chat_id=chat_id,
                card=_build_test_card(text_content),
            )
        else:
            result = await send_text_to_chat(
                db=db,
                project_id=project_id,
                chat_id=chat_id,
                text=text_content,
            )
    except FeishuApiError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "code": 200,
        "msg": "发送成功",
        "data": {"message_id": result.get("message_id", "")},
    }


@router.post("/projects/{project_id}/svn-credential/test")
async def test_project_svn_credential(
    project_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """使用已保存的项目级 SVN 凭据测试启用的远端 query_roots。"""
    _require_project_management_access(ctx, project_id)
    await _get_project_or_404(db, project_id)

    credential_record = await _get_project_svn_credential(db, project_id)
    if credential_record is None or not credential_record.password_cipher:
        raise HTTPException(
            status_code=400,
            detail="请先保存项目级 SVN 凭据后再测试连接",
        )

    remote_roots = await _list_enabled_remote_query_roots(db, project_id)
    if not remote_roots:
        raise HTTPException(
            status_code=400,
            detail="请先配置并启用至少一个 SVN 数据根后再测试连接",
        )

    try:
        password = decrypt_secret(credential_record.password_cipher)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="项目级 SVN 凭据无法解密，请重新保存后再测试",
        ) from exc
    if not credential_record.username.strip() or not password:
        raise HTTPException(
            status_code=400,
            detail="请先保存项目级 SVN 凭据后再测试连接",
        )

    credentials = SvnCredential(
        host="",
        username=credential_record.username,
        password=password,
        updated_at=credential_record.updated_at.isoformat()
        if credential_record.updated_at
        else None,
    )
    items = [
        _test_project_svn_query_root(row, credentials=credentials, password=password)
        for row in remote_roots
    ]
    overall_status = (
        "success"
        if items and all(item["status"] == "success" for item in items)
        else "failed"
    )
    return {
        "code": 200,
        "msg": "ok",
        "data": {
            "status": overall_status,
            "items": items,
        },
    }


@router.get("/projects/{project_id}/source-evidence-svn-roots")
async def get_source_evidence_svn_roots(
    project_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """读取项目级 Source Evidence SVN Roots。"""
    _require_project_management_access(ctx, project_id)
    await _get_project_or_404(db, project_id)
    roots = await _list_source_evidence_svn_roots(db, project_id)
    return {
        "code": 200,
        "msg": "ok",
        "data": {"items": [_serialize_source_evidence_svn_root(row) for row in roots]},
    }


@router.put("/projects/{project_id}/source-evidence-svn-roots")
async def save_source_evidence_svn_roots(
    project_id: int,
    payload: SourceEvidenceSvnRootsUpdateRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """替换保存项目级 Source Evidence SVN Roots。"""
    _require_project_management_access(ctx, project_id)
    await _get_project_or_404(db, project_id)
    await _replace_source_evidence_svn_roots(db, project_id, payload.items)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Source Evidence SVN Root 保存冲突，请重试") from exc
    roots = await _list_source_evidence_svn_roots(db, project_id)
    return {
        "code": 200,
        "msg": "保存成功",
        "data": {"items": [_serialize_source_evidence_svn_root(row) for row in roots]},
    }


@router.get("/projects/{project_id}/ai-config")
async def get_project_ai_config(
    project_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """读取项目级 AI 配置；仅管理后台使用，不返回明文 API Key。"""
    _require_project_management_access(ctx, project_id)
    await _get_project_or_404(db, project_id)
    record = await _get_project_ai_credential(db, project_id)
    return {"code": 200, "msg": "ok", "data": _serialize_project_ai_config(record)}


@router.put("/projects/{project_id}/ai-config")
async def save_project_ai_config(
    project_id: int,
    payload: ProjectAiConfigRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """保存项目级 AI 凭据与名称匹配参数。"""
    _require_project_management_access(ctx, project_id)
    await _get_project_or_404(db, project_id)
    record = await _save_project_ai_config(
        db,
        project_id=project_id,
        payload=payload,
        updated_by=ctx.user_id,
    )
    await db.commit()
    await db.refresh(record)
    return {"code": 200, "msg": "保存成功", "data": _serialize_project_ai_config(record)}


@router.delete("/projects/{project_id}/ai-config", status_code=204)
async def delete_project_ai_config(
    project_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """清除项目级 AI 配置。"""
    _require_project_management_access(ctx, project_id)
    await _get_project_or_404(db, project_id)
    record = await _get_project_ai_credential(db, project_id)
    if record is not None:
        await db.delete(record)
        await db.commit()
    return Response(status_code=204)


@router.post("/projects/{project_id}/ai-config/test")
async def test_project_ai_config(
    project_id: int,
    response: Response,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """使用已保存的项目级 AI 凭据做轻量连通性测试。"""
    _require_project_management_access(ctx, project_id)
    await _get_project_or_404(db, project_id)
    record = await _get_project_ai_credential(db, project_id)
    if record is None or not record.encrypted_api_key:
        raise HTTPException(status_code=400, detail="请先保存项目级 AI 凭据。")

    try:
        api_key = decrypt_secret(record.encrypted_api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="项目级 AI API Key 无法解密，请重新保存。") from exc
    if not api_key:
        raise HTTPException(status_code=400, detail="请先保存项目级 AI API Key。")
    if not record.enabled:
        raise HTTPException(status_code=400, detail="项目级 AI 当前未启用。")

    try:
        await test_provider_connection(
            provider_preset=record.provider_preset,  # type: ignore[arg-type]
            base_url=record.base_url,
            model=record.model,
            api_key=api_key,
            extra_headers=_parse_json_object(record.extra_headers_json),
        )
    except ProviderConnectionError as exc:
        record.last_test_status = "failed"
        record.last_test_at = datetime.now(timezone.utc)
        record.last_test_error_summary = _sanitize_project_ai_error(exc.message, api_key)
        db.add(record)
        await db.commit()
        await db.refresh(record)
        response.status_code = exc.status_code
        return {
            "code": exc.status_code,
            "msg": "连接测试失败",
            "data": _serialize_project_ai_config(record),
        }

    record.last_test_status = "success"
    record.last_test_at = datetime.now(timezone.utc)
    record.last_test_error_summary = ""
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"code": 200, "msg": "连接测试成功", "data": _serialize_project_ai_config(record)}


@router.get("/projects/{project_id}/vision-ai-config")
async def get_project_vision_ai_config(
    project_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """读取项目级 Vision AI 配置；仅管理后台使用，不返回明文 API Key。"""
    _require_project_management_access(ctx, project_id)
    await _get_project_or_404(db, project_id)
    record = await _get_project_vision_ai_credential(db, project_id)
    return {"code": 200, "msg": "ok", "data": _serialize_project_vision_ai_config(record)}


@router.put("/projects/{project_id}/vision-ai-config")
async def save_project_vision_ai_config(
    project_id: int,
    payload: ProjectVisionAiConfigRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """保存项目级 Vision AI 凭据。"""
    _require_project_management_access(ctx, project_id)
    await _get_project_or_404(db, project_id)
    record = await _save_project_vision_ai_config(
        db,
        project_id=project_id,
        payload=payload,
        updated_by=ctx.user_id,
    )
    await db.commit()
    await db.refresh(record)
    return {"code": 200, "msg": "保存成功", "data": _serialize_project_vision_ai_config(record)}


@router.delete("/projects/{project_id}/vision-ai-config", status_code=204)
async def delete_project_vision_ai_config(
    project_id: int,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """清除项目级 Vision AI 配置。"""
    _require_project_management_access(ctx, project_id)
    await _get_project_or_404(db, project_id)
    record = await _get_project_vision_ai_credential(db, project_id)
    if record is not None:
        await db.delete(record)
        await db.commit()
    return Response(status_code=204)


@router.post("/projects/{project_id}/vision-ai-config/test")
async def test_project_vision_ai_config(
    project_id: int,
    response: Response,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """使用已保存的项目级 Vision AI 凭据做轻量连通性测试。"""
    _require_project_management_access(ctx, project_id)
    await _get_project_or_404(db, project_id)
    record = await _get_project_vision_ai_credential(db, project_id)
    if record is None or not record.encrypted_api_key:
        raise HTTPException(status_code=400, detail="请先保存项目级 Vision AI 凭据。")

    try:
        api_key = decrypt_secret(record.encrypted_api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="项目级 Vision AI API Key 无法解密，请重新保存。") from exc
    if not api_key:
        raise HTTPException(status_code=400, detail="请先保存项目级 Vision AI API Key。")
    if not record.enabled:
        raise HTTPException(status_code=400, detail="项目级 Vision AI 当前未启用。")

    try:
        await test_provider_vision_connection(
            provider_preset=record.provider_preset,  # type: ignore[arg-type]
            base_url=record.base_url,
            model=record.model,
            api_key=api_key,
            extra_headers=_parse_json_object(record.extra_headers_json),
        )
    except ProviderConnectionError as exc:
        record.last_test_status = "failed"
        record.last_test_at = datetime.now(timezone.utc)
        record.last_test_error_summary = _sanitize_project_ai_error(exc.message, api_key)
        db.add(record)
        await db.commit()
        await db.refresh(record)
        response.status_code = exc.status_code
        return {
            "code": exc.status_code,
            "msg": "连接测试失败",
            "data": _serialize_project_vision_ai_config(record),
        }

    record.last_test_status = "success"
    record.last_test_at = datetime.now(timezone.utc)
    record.last_test_error_summary = ""
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"code": 200, "msg": "连接测试成功", "data": _serialize_project_vision_ai_config(record)}


async def _serialize_feishu_bot_config(
    db: AsyncSession,
    record: FeishuBotConfigRecord | None,
    *,
    project_id: int,
) -> dict[str, Any]:
    """把 ORM 转成 GET / PUT 返回的脱敏 data 结构；密文不外露。"""
    bound_chat_ids = await _list_bound_chat_ids(db, project_id)
    query_roots = await _list_query_roots(db, project_id)
    svn_credential = await _get_project_svn_credential(db, project_id)
    ai_credential = await _get_project_ai_credential(db, project_id)
    if record is None:
        return {
            "configured": False,
            "app_id": "",
            "has_app_secret": False,
            "default_chat_id": "",
            "bound_chat_ids": bound_chat_ids,
            "allowed_open_ids": [],
            "local_download_roots": [],
            "svn_download_roots": [],
            "allowed_download_suffixes": DEFAULT_FEISHU_DOWNLOAD_SUFFIXES,
            "query_roots": [_serialize_query_root(row) for row in query_roots],
            "svn_credential": _serialize_svn_credential(svn_credential),
            "ai_credential": _serialize_ai_credential(ai_credential),
            "ai_match_params": {
                "auto_match_threshold": 0.9,
                "candidate_threshold": 0.6,
                "max_candidates": 10,
            },
            "connection_state": "inactive",
            "updated_at": None,
        }

    return {
        "configured": bool(record.app_id),
        "app_id": record.app_id or "",
        "has_app_secret": bool(record.app_secret_cipher),
        "default_chat_id": record.default_chat_id or "",
        "bound_chat_ids": bound_chat_ids,
        "allowed_open_ids": _parse_allowed_open_ids(record.allowed_open_ids or ""),
        "local_download_roots": _parse_json_string_list(record.local_download_roots),
        "svn_download_roots": _parse_json_string_list(record.svn_download_roots),
        "allowed_download_suffixes": _parse_json_string_list(
            record.allowed_download_suffixes,
            default=DEFAULT_FEISHU_DOWNLOAD_SUFFIXES,
        ),
        "query_roots": [_serialize_query_root(row) for row in query_roots],
        "svn_credential": _serialize_svn_credential(svn_credential),
        "ai_credential": _serialize_ai_credential(ai_credential),
        "ai_match_params": {
            "auto_match_threshold": record.auto_match_threshold,
            "candidate_threshold": record.candidate_threshold,
            "max_candidates": record.max_candidates,
        },
        # Step 1 阶段尚未引入 supervisor，状态先固定 inactive，
        # 后续 step 接入长连接后再回填真实状态。
        "connection_state": "inactive",
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


async def _list_bound_chat_ids(db: AsyncSession, project_id: int) -> list[str]:
    result = await db.execute(
        select(FeishuBotBoundChatRecord.chat_id)
        .where(FeishuBotBoundChatRecord.project_id == project_id)
        .order_by(FeishuBotBoundChatRecord.id)
    )
    return list(result.scalars().all())


async def _list_query_roots(
    db: AsyncSession,
    project_id: int,
) -> list[ProjectQueryRootRecord]:
    result = await db.execute(
        select(ProjectQueryRootRecord)
        .where(ProjectQueryRootRecord.project_id == project_id)
        .order_by(ProjectQueryRootRecord.id)
    )
    return list(result.scalars().all())


async def _list_enabled_remote_query_roots(
    db: AsyncSession,
    project_id: int,
) -> list[ProjectQueryRootRecord]:
    result = await db.execute(
        select(ProjectQueryRootRecord)
        .where(
            ProjectQueryRootRecord.project_id == project_id,
            ProjectQueryRootRecord.status == "enabled",
        )
        .order_by(ProjectQueryRootRecord.id)
    )
    return [
        row
        for row in result.scalars().all()
        if _is_remote_svn_url(row.svn_root_url)
    ]


async def _list_source_evidence_svn_roots(
    db: AsyncSession,
    project_id: int,
) -> list[ProjectSourceEvidenceSvnRootRecord]:
    result = await db.execute(
        select(ProjectSourceEvidenceSvnRootRecord)
        .where(ProjectSourceEvidenceSvnRootRecord.project_id == project_id)
        .order_by(ProjectSourceEvidenceSvnRootRecord.id)
    )
    return list(result.scalars().all())


def _is_remote_svn_url(raw_url: str | None) -> bool:
    if not raw_url:
        return False
    parsed = urlparse(raw_url.strip())
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def _sanitize_svn_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    if not parsed.username and not parsed.password:
        return raw_url
    hostname = parsed.hostname or ""
    netloc = hostname
    if parsed.port is not None:
        netloc = f"{hostname}:{parsed.port}"
    return parsed._replace(netloc=netloc).geturl()


def _sanitize_svn_test_message(message: str, password: str) -> str:
    safe_message = message.strip() or "SVN 连接测试失败"
    if password:
        safe_message = safe_message.replace(password, "******")
    return safe_message


def _test_project_svn_query_root(
    row: ProjectQueryRootRecord,
    *,
    credentials: SvnCredential,
    password: str,
) -> dict[str, Any]:
    try:
        result = list_svn_directory(row.svn_root_url, credentials=credentials)
    except SvnRemoteError as exc:
        return _build_svn_test_item(
            row,
            status="failed",
            message=_sanitize_svn_test_message(exc.message, password),
        )
    except NotImplementedError as exc:
        return _build_svn_test_item(
            row,
            status="failed",
            message=_sanitize_svn_test_message(str(exc), password),
        )
    except Exception as exc:  # noqa: BLE001 - 连接测试失败需要回传单项摘要
        return _build_svn_test_item(
            row,
            status="failed",
            message=_sanitize_svn_test_message(str(exc), password),
        )

    entries = result.get("entries", [])
    return _build_svn_test_item(
        row,
        status="success",
        message="连接成功",
        entry_count=len(entries) if isinstance(entries, list) else 0,
    )


def _build_svn_test_item(
    row: ProjectQueryRootRecord,
    *,
    status: str,
    message: str,
    entry_count: int = 0,
) -> dict[str, Any]:
    return {
        "alias": row.alias,
        "display_name": row.display_name,
        "svn_url": _sanitize_svn_url(row.svn_root_url),
        "status": status,
        "message": message,
        "entry_count": entry_count,
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


async def _get_project_vision_ai_credential(
    db: AsyncSession,
    project_id: int,
) -> ProjectVisionAiCredentialRecord | None:
    result = await db.execute(
        select(ProjectVisionAiCredentialRecord).where(
            ProjectVisionAiCredentialRecord.project_id == project_id
        )
    )
    return result.scalar_one_or_none()


def _serialize_query_root(row: ProjectQueryRootRecord) -> dict[str, Any]:
    return {
        "alias": row.alias,
        "display_name": row.display_name,
        "svn_url": row.svn_root_url,
        "enabled": row.status == "enabled",
    }


def _serialize_source_evidence_svn_root(
    row: ProjectSourceEvidenceSvnRootRecord,
) -> dict[str, Any]:
    return {
        "alias": row.alias,
        "display_name": row.display_name,
        "svn_url": row.svn_root_url,
        "enabled": row.status == "enabled",
    }


def _serialize_svn_credential(
    record: ProjectSvnCredentialRecord | None,
) -> dict[str, Any]:
    if record is None or not record.password_cipher:
        return {
            "configured": False,
            "username_masked": "",
            "updated_at": None,
        }
    return {
        "configured": True,
        "username_masked": record.username or "",
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _serialize_ai_credential(
    record: ProjectAiCredentialRecord | None,
) -> dict[str, Any]:
    if record is None or not record.encrypted_api_key:
        return {
            "configured": False,
            "provider_preset": "",
            "provider": "",
            "base_url": "",
            "model": "",
            "api_key_masked": "",
            "masked_api_key": "",
            "has_extra_headers": False,
            "enabled": False,
            "last_test_status": "",
            "last_test_at": None,
            "last_test_error_summary": "",
            "updated_at": None,
        }
    try:
        api_key = decrypt_secret(record.encrypted_api_key)
    except ValueError:
        api_key = ""
    return {
        "configured": bool(api_key),
        "provider_preset": record.provider_preset,
        "provider": record.provider_preset,
        "base_url": record.base_url,
        "model": record.model,
        "api_key_masked": mask_api_key(api_key),
        "masked_api_key": mask_api_key(api_key),
        "has_extra_headers": bool(_parse_json_object(record.extra_headers_json)),
        "enabled": bool(record.enabled),
        "last_test_status": record.last_test_status or "",
        "last_test_at": record.last_test_at.isoformat() if record.last_test_at else None,
        "last_test_error_summary": record.last_test_error_summary or "",
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _serialize_project_ai_config(
    record: ProjectAiCredentialRecord | None,
) -> dict[str, Any]:
    if record is None or not record.encrypted_api_key:
        return {
            "configured": False,
            "enabled": False,
            "provider": "",
            "model": "",
            "base_url": "",
            "masked_api_key": "",
            "has_extra_headers": False,
            "auto_match_threshold": 0.9,
            "candidate_threshold": 0.6,
            "max_candidates": 10,
            "last_test_status": "",
            "last_test_at": None,
            "last_test_error_summary": "",
            "updated_by": None,
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
        "model": record.model,
        "base_url": record.base_url,
        "masked_api_key": mask_api_key(api_key),
        "has_extra_headers": bool(_parse_json_object(record.extra_headers_json)),
        "auto_match_threshold": record.auto_match_threshold,
        "candidate_threshold": record.candidate_threshold,
        "max_candidates": record.max_candidates,
        "last_test_status": record.last_test_status or "",
        "last_test_at": record.last_test_at.isoformat() if record.last_test_at else None,
        "last_test_error_summary": record.last_test_error_summary or "",
        "updated_by": record.updated_by,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _serialize_project_vision_ai_config(
    record: ProjectVisionAiCredentialRecord | None,
) -> dict[str, Any]:
    if record is None or not record.encrypted_api_key:
        return {
            "configured": False,
            "enabled": False,
            "provider": "",
            "model": "",
            "base_url": "",
            "masked_api_key": "",
            "has_extra_headers": False,
            "last_test_status": "",
            "last_test_at": None,
            "last_test_error_summary": "",
            "updated_by": None,
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
        "model": record.model,
        "base_url": record.base_url,
        "masked_api_key": mask_api_key(api_key),
        "has_extra_headers": bool(_parse_json_object(record.extra_headers_json)),
        "last_test_status": record.last_test_status or "",
        "last_test_at": record.last_test_at.isoformat() if record.last_test_at else None,
        "last_test_error_summary": record.last_test_error_summary or "",
        "updated_by": record.updated_by,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


async def _save_project_ai_config(
    db: AsyncSession,
    *,
    project_id: int,
    payload: ProjectAiConfigRequest,
    updated_by: int | None,
) -> ProjectAiCredentialRecord:
    _validate_project_ai_config_payload(payload)
    base_url, model = resolve_provider_defaults(
        payload.provider,
        payload.base_url,
        payload.model,
    )
    if not base_url or not model:
        raise HTTPException(status_code=400, detail="请填写 Base URL 和模型名称。")

    record = await _get_project_ai_credential(db, project_id)
    encrypted_key = record.encrypted_api_key if record else ""
    if payload.api_key:
        encrypted_key = encrypt_secret(payload.api_key)
    if payload.enabled and not encrypted_key:
        raise HTTPException(status_code=400, detail="启用项目级 AI 前必须填写 API Key。")
    if record is None and not encrypted_key:
        raise HTTPException(status_code=400, detail="首次保存项目级 AI 配置时必须填写 API Key。")

    extra_headers_json = json.dumps(payload.extra_headers, ensure_ascii=False)
    if record is None:
        record = ProjectAiCredentialRecord(
            project_id=project_id,
            provider_preset=payload.provider,
            base_url=base_url,
            model=model,
            encrypted_api_key=encrypted_key,
            extra_headers_json=extra_headers_json,
        )
    else:
        record.provider_preset = payload.provider
        record.base_url = base_url
        record.model = model
        record.encrypted_api_key = encrypted_key
        record.extra_headers_json = extra_headers_json
    record.enabled = payload.enabled
    record.auto_match_threshold = float(payload.auto_match_threshold)
    record.candidate_threshold = float(payload.candidate_threshold)
    record.max_candidates = int(payload.max_candidates)
    record.updated_by = updated_by
    db.add(record)
    await _mirror_project_ai_match_params_to_feishu_config(db, project_id, record)
    return record


async def _save_project_vision_ai_config(
    db: AsyncSession,
    *,
    project_id: int,
    payload: ProjectVisionAiConfigRequest,
    updated_by: int | None,
) -> ProjectVisionAiCredentialRecord:
    base_url, model = resolve_provider_defaults(
        payload.provider,
        payload.base_url,
        payload.model,
    )
    if not base_url or not model:
        raise HTTPException(status_code=400, detail="请填写 Base URL 和模型名称。")

    record = await _get_project_vision_ai_credential(db, project_id)
    encrypted_key = record.encrypted_api_key if record else ""
    if payload.api_key:
        encrypted_key = encrypt_secret(payload.api_key)
    if payload.enabled and not encrypted_key:
        raise HTTPException(status_code=400, detail="启用项目级 Vision AI 前必须填写 API Key。")
    if record is None and not encrypted_key:
        raise HTTPException(status_code=400, detail="首次保存项目级 Vision AI 配置时必须填写 API Key。")

    extra_headers_json = json.dumps(payload.extra_headers, ensure_ascii=False)
    if record is None:
        record = ProjectVisionAiCredentialRecord(
            project_id=project_id,
            provider_preset=payload.provider,
            base_url=base_url,
            model=model,
            encrypted_api_key=encrypted_key,
            extra_headers_json=extra_headers_json,
        )
    else:
        record.provider_preset = payload.provider
        record.base_url = base_url
        record.model = model
        record.encrypted_api_key = encrypted_key
        record.extra_headers_json = extra_headers_json
    record.enabled = payload.enabled
    record.updated_by = updated_by
    db.add(record)
    return record


def _validate_project_ai_config_payload(payload: ProjectAiConfigRequest) -> None:
    if payload.auto_match_threshold < payload.candidate_threshold:
        raise HTTPException(
            status_code=400,
            detail="高置信自动返回阈值必须大于或等于候选列表阈值",
        )


async def _mirror_project_ai_match_params_to_feishu_config(
    db: AsyncSession,
    project_id: int,
    record: ProjectAiCredentialRecord,
) -> None:
    result = await db.execute(
        select(FeishuBotConfigRecord).where(
            FeishuBotConfigRecord.project_id == project_id
        )
    )
    feishu_config = result.scalar_one_or_none()
    if feishu_config is None:
        return
    feishu_config.auto_match_threshold = record.auto_match_threshold
    feishu_config.candidate_threshold = record.candidate_threshold
    feishu_config.max_candidates = record.max_candidates
    db.add(feishu_config)


def _sanitize_project_ai_error(message: str, api_key: str) -> str:
    return sanitize_ai_error(message or "连接测试失败，请检查项目级 AI 配置。", api_key)


def _decrypt_app_secret_or_400(cipher: str) -> str:
    try:
        return decrypt_secret(cipher)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="app_secret 密文无法解密，请重新配置") from exc


async def _ensure_shared_app_secret_consistency(
    db: AsyncSession,
    *,
    project_id: int,
    app_id: str,
    app_secret_plain: str,
) -> None:
    result = await db.execute(
        select(FeishuBotConfigRecord).where(
            FeishuBotConfigRecord.app_id == app_id,
            FeishuBotConfigRecord.project_id != project_id,
        )
    )
    for existing in result.scalars().all():
        existing_secret = _decrypt_app_secret_or_400(existing.app_secret_cipher)
        if existing_secret != app_secret_plain:
            raise HTTPException(
                status_code=400,
                detail="该 App ID 已在其他项目配置，请使用相同 App Secret 或联系管理员确认",
            )


def _resolve_bound_chat_ids(
    *,
    payload: FeishuBotConfigUpdateRequest,
    is_create: bool,
    default_chat_id: str,
    existing_bound_chat_ids: list[str],
) -> tuple[list[str], bool]:
    if payload.bound_chat_ids is not None:
        bound_chat_ids = payload.bound_chat_ids
        if default_chat_id and default_chat_id not in bound_chat_ids:
            raise HTTPException(
                status_code=400,
                detail="default_chat_id 必须包含在绑定群列表中",
            )
        return bound_chat_ids, True
    if payload.default_chat_id is not None and default_chat_id:
        return [default_chat_id], True
    if is_create:
        return [], True
    return existing_bound_chat_ids, False


async def _ensure_bound_chats_available(
    db: AsyncSession,
    *,
    project_id: int,
    project_name: str,
    chat_ids: list[str],
) -> None:
    if not chat_ids:
        return
    result = await db.execute(
        select(FeishuBotBoundChatRecord, Project)
        .join(Project, Project.id == FeishuBotBoundChatRecord.project_id)
        .where(
            FeishuBotBoundChatRecord.chat_id.in_(chat_ids),
            FeishuBotBoundChatRecord.project_id != project_id,
        )
        .order_by(FeishuBotBoundChatRecord.id)
    )
    conflict = result.first()
    if conflict is None:
        return
    _, owner_project = conflict
    raise HTTPException(
        status_code=400,
        detail=f"该飞书群已绑定项目「{owner_project.name}」，不能重复绑定到「{project_name}」",
    )


async def _replace_bound_chats(
    db: AsyncSession,
    project_id: int,
    chat_ids: list[str],
) -> None:
    await db.execute(
        delete(FeishuBotBoundChatRecord).where(
            FeishuBotBoundChatRecord.project_id == project_id
        )
    )
    for chat_id in chat_ids:
        db.add(FeishuBotBoundChatRecord(project_id=project_id, chat_id=chat_id))


async def _replace_query_roots(
    db: AsyncSession,
    project_id: int,
    query_roots: list[Any],
) -> None:
    normalized_rows: list[dict[str, Any]] = []
    seen_aliases: set[str] = set()
    for item in query_roots:
        alias = item.alias.strip()
        if alias in seen_aliases:
            raise HTTPException(
                status_code=400,
                detail=f"query_roots alias 重复：{alias}",
            )
        seen_aliases.add(alias)
        svn_url = item.svn_url.strip()
        if not svn_url:
            raise HTTPException(
                status_code=400,
                detail=f"query_roots.svn_url 不能为空：{alias}",
            )
        normalized_rows.append(
            {
                "alias": alias,
                "display_name": item.display_name.strip(),
                "svn_url": svn_url,
                "enabled": item.enabled,
            }
        )

    await db.execute(
        delete(ProjectQueryRootRecord).where(
            ProjectQueryRootRecord.project_id == project_id
        )
    )
    for item in normalized_rows:
        db.add(
            ProjectQueryRootRecord(
                project_id=project_id,
                alias=item["alias"],
                display_name=item["display_name"],
                svn_root_url=item["svn_url"],
                status="enabled" if item["enabled"] else "disabled",
            )
        )


async def _replace_source_evidence_svn_roots(
    db: AsyncSession,
    project_id: int,
    roots: list[Any],
) -> None:
    normalized_rows: list[dict[str, Any]] = []
    seen_aliases: set[str] = set()
    for item in roots:
        alias = item.alias.strip()
        if alias in seen_aliases:
            raise HTTPException(
                status_code=400,
                detail=f"source_evidence_svn_roots alias 重复：{alias}",
            )
        seen_aliases.add(alias)
        raw_url = item.svn_url.strip()
        if not raw_url:
            raise HTTPException(
                status_code=400,
                detail=f"source_evidence_svn_roots.svn_url 不能为空：{alias}",
            )
        normalized_rows.append(
            {
                "alias": alias,
                "display_name": item.display_name.strip(),
                "svn_url": _normalize_source_evidence_svn_root_url(raw_url),
                "enabled": item.enabled,
            }
        )

    await db.execute(
        delete(ProjectSourceEvidenceSvnRootRecord).where(
            ProjectSourceEvidenceSvnRootRecord.project_id == project_id
        )
    )
    for item in normalized_rows:
        db.add(
            ProjectSourceEvidenceSvnRootRecord(
                project_id=project_id,
                alias=item["alias"],
                display_name=item["display_name"],
                svn_root_url=item["svn_url"],
                status="enabled" if item["enabled"] else "disabled",
            )
        )


def _normalize_source_evidence_svn_root_url(raw_url: str) -> str:
    try:
        normalized = normalize_dir_url(raw_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    parsed = urlparse(normalized)
    if parsed.username or parsed.password:
        raise HTTPException(
            status_code=400,
            detail="Source Evidence SVN Root 不允许包含用户名或密码",
        )
    if parsed.query or parsed.fragment:
        raise HTTPException(
            status_code=400,
            detail="Source Evidence SVN Root 不能包含 query 或 fragment",
        )
    try:
        enforce_host_allowlist(parsed.hostname)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return normalized


async def _upsert_project_svn_credential(
    db: AsyncSession,
    project_id: int,
    payload: Any,
) -> None:
    record = await _get_project_svn_credential(db, project_id)
    username = payload.username if payload.username is not None else (record.username if record else "")
    password_cipher = record.password_cipher if record else ""
    if payload.password is not None:
        if payload.password == "":
            raise HTTPException(status_code=400, detail="SVN 密码不能为空")
        password_cipher = encrypt_secret(payload.password)
    if record is None:
        if not password_cipher:
            raise HTTPException(status_code=400, detail="首次保存 SVN 凭据时必须填写密码")
        record = ProjectSvnCredentialRecord(
            project_id=project_id,
            username=username,
            password_cipher=password_cipher,
        )
    else:
        record.username = username
        record.password_cipher = password_cipher
    db.add(record)


async def _upsert_project_ai_credential(
    db: AsyncSession,
    project_id: int,
    payload: Any,
) -> None:
    base_url, model = resolve_provider_defaults(
        payload.provider_preset,
        payload.base_url,
        payload.model,
    )
    if not base_url or not model:
        raise HTTPException(status_code=400, detail="请填写 Base URL 和模型名称。")
    record = await _get_project_ai_credential(db, project_id)
    encrypted_key = record.encrypted_api_key if record else ""
    if payload.api_key:
        encrypted_key = encrypt_secret(payload.api_key)
    if record is None and not encrypted_key:
        raise HTTPException(status_code=400, detail="首次保存 AI 配置时必须填写 API Key。")
    extra_headers_json = json.dumps(payload.extra_headers, ensure_ascii=False)
    if record is None:
        record = ProjectAiCredentialRecord(
            project_id=project_id,
            provider_preset=payload.provider_preset,
            base_url=base_url,
            model=model,
            encrypted_api_key=encrypted_key,
            extra_headers_json=extra_headers_json,
        )
    else:
        record.provider_preset = payload.provider_preset
        record.base_url = base_url
        record.model = model
        record.encrypted_api_key = encrypted_key
        record.extra_headers_json = extra_headers_json
    db.add(record)


def _apply_ai_match_params(
    record: FeishuBotConfigRecord,
    payload: FeishuBotConfigUpdateRequest,
) -> None:
    if payload.ai_match_params is None:
        return
    record.auto_match_threshold = _resolve_ai_match_float(
        payload.ai_match_params.auto_match_threshold,
        default=record.auto_match_threshold,
    )
    record.candidate_threshold = _resolve_ai_match_float(
        payload.ai_match_params.candidate_threshold,
        default=record.candidate_threshold,
    )
    record.max_candidates = _resolve_ai_match_int(
        payload.ai_match_params.max_candidates,
        default=record.max_candidates,
    )
    if record.auto_match_threshold < record.candidate_threshold:
        raise HTTPException(
            status_code=400,
            detail="高置信自动返回阈值必须大于或等于候选列表阈值",
        )


def _resolve_ai_match_float(value: float | None, *, default: float) -> float:
    return default if value is None else float(value)


def _resolve_ai_match_int(value: int | None, *, default: int) -> int:
    return default if value is None else int(value)


def _normalize_allowed_open_ids_input(raw: str) -> str:
    """前端原文（多行 / 逗号混合）→ 规范化后的逗号分隔字符串。

    步骤：按 ``,`` 与换行符切分 → strip → 去空 → 去重保序 → 用 ``,`` 拼接落库。
    """
    if not raw:
        return ""
    pieces: list[str] = []
    seen: set[str] = set()
    for chunk in raw.replace("\r", "\n").split("\n"):
        for piece in chunk.split(","):
            normalized = piece.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            pieces.append(normalized)
    return ",".join(pieces)


def _parse_allowed_open_ids(raw: str) -> list[str]:
    """落库的逗号分隔字符串 → 列表，便于前端按 tag 渲染。"""
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _normalize_download_roots_input(raw: str) -> list[str]:
    """前端根目录原文 → 去重后的绝对目录列表。"""
    if not raw:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for piece in _split_multiline_csv(raw):
        path = Path(piece).expanduser()
        if not path.is_absolute():
            raise HTTPException(status_code=400, detail="下载根目录必须是本机绝对路径")
        normalized = str(path.resolve(strict=False))
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _normalize_download_suffixes_input(raw: str) -> list[str]:
    """前端后缀白名单原文 → 规范化后缀列表；空值恢复默认。"""
    if not raw.strip():
        return list(DEFAULT_FEISHU_DOWNLOAD_SUFFIXES)
    result: list[str] = []
    seen: set[str] = set()
    for piece in _split_multiline_csv(raw):
        suffix = piece.strip().lower()
        if not suffix:
            continue
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        if suffix == "." or any(char in suffix for char in "\\/"):
            raise HTTPException(status_code=400, detail=f"文件后缀不合法：{piece}")
        if suffix in seen:
            continue
        seen.add(suffix)
        result.append(suffix)
    return result or list(DEFAULT_FEISHU_DOWNLOAD_SUFFIXES)


def _split_multiline_csv(raw: str) -> list[str]:
    """按换行与英文逗号拆分前端 textarea。"""
    pieces: list[str] = []
    for chunk in raw.replace("\r", "\n").split("\n"):
        for piece in chunk.split(","):
            normalized = piece.strip()
            if normalized:
                pieces.append(normalized)
    return pieces


def _parse_json_string_list(
    raw: str | None,
    *,
    default: list[str] | None = None,
) -> list[str]:
    """解析 JSON 数组字符串；旧库异常值按默认值兜底。"""
    fallback = list(default or [])
    if not raw:
        return fallback
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return fallback
    if not isinstance(payload, list):
        return fallback
    return [str(item).strip() for item in payload if str(item).strip()]


def _parse_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(value) for key, value in parsed.items()}


def _build_test_card(text_content: str) -> dict[str, Any]:
    """构造 test-send 接口使用的飞书富文本卡片体（最简版本）。"""
    return {
        "header": {"title": {"tag": "plain_text", "content": "测试消息"}},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": text_content}},
        ],
    }
