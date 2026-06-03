"""异步 SQLAlchemy 引擎与会话工厂，供全局复用。"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.app.db_migrations import run_database_migrations_async
from backend.config import settings

DEFAULT_PROJECT_NAME = "默认项目"
DEFAULT_PROJECT_DESCRIPTION = "系统自动创建的默认项目"

engine = create_async_engine(settings.db_url, echo=settings.debug)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """ORM 基类。"""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：每次请求分配一个独立的数据库会话。"""
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """应用启动时升级数据库结构，并确保默认项目与管理员存在。"""
    # 先显式导入 ORM 模型，确保 Base.metadata 已完整收集所有表。
    from backend.app import models as _models  # noqa: F401

    await run_database_migrations_async()
    await ensure_default_auth_bootstrap()


async def ensure_default_auth_bootstrap() -> None:
    """确保默认项目、默认管理员与主归属项目口径处于可登录状态。"""
    default_project = await _seed_default_project()
    await _seed_default_super_admin(default_project.id)
    await _backfill_user_primary_projects()


async def _seed_default_project():
    """确保系统默认项目存在，并返回该项目实例。"""
    from backend.app.models import Project  # 延迟导入，避免循环依赖

    async with async_session_factory() as session:
        result = await session.execute(
            select(Project).where(Project.name == DEFAULT_PROJECT_NAME).limit(1)
        )
        project = result.scalar_one_or_none()
        if project is None:
            project = Project(
                name=DEFAULT_PROJECT_NAME,
                description=DEFAULT_PROJECT_DESCRIPTION,
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)
        return project


async def _seed_default_super_admin(default_project_id: int) -> None:
    """确保系统始终存在且仅存在一个默认超级管理员。"""
    from backend.app.auth.service import hash_password
    from backend.app.models import User, UserProjectRole

    async with async_session_factory() as session:
        result = await session.execute(
            select(User.id).where(User.username == settings.default_super_admin_username)
        )
        admin_user_id = result.scalar_one_or_none()

        if admin_user_id is None:
            admin_user = User(
                username=settings.default_super_admin_username,
                hashed_password=hash_password(settings.default_super_admin_password),
                is_super_admin=True,
                primary_project_id=default_project_id,
            )
            session.add(admin_user)
            await session.flush()
            admin_user_id = admin_user.id
        else:
            update_values = {
                "is_super_admin": True,
                "primary_project_id": default_project_id,
            }
            if settings.default_super_admin_password_configured:
                update_values["hashed_password"] = hash_password(
                    settings.default_super_admin_password
                )
            await session.execute(
                update(User)
                .where(User.id == admin_user_id)
                .values(**update_values)
            )
        if admin_user_id is None:
            raise RuntimeError("默认超级管理员创建失败")

        await session.execute(
            update(User)
            .where(
                User.id != admin_user_id,
                User.is_super_admin.is_(True),
            )
            .values(is_super_admin=False)
        )

        role_result = await session.execute(
            select(UserProjectRole).where(
                UserProjectRole.user_id == admin_user_id,
                UserProjectRole.project_id == default_project_id,
            )
        )
        role = role_result.scalar_one_or_none()
        if role is None:
            session.add(
                UserProjectRole(
                    user_id=admin_user_id,
                    project_id=default_project_id,
                    role="admin",
                )
            )
        else:
            role.role = "admin"
            session.add(role)

        await session.commit()


async def _backfill_user_primary_projects() -> None:
    """为缺少主归属项目的旧用户回填默认项目。"""
    from sqlalchemy.orm import selectinload

    from backend.app.auth.service import get_default_project_id
    from backend.app.models import User, UserProjectRole

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).options(
                selectinload(User.roles).selectinload(UserProjectRole.project)
            )
        )
        users = result.scalars().all()

        dirty = False
        for user in users:
            default_project_id = get_default_project_id(user)
            if default_project_id is None:
                continue
            if user.primary_project_id == default_project_id:
                continue
            user.primary_project_id = default_project_id
            session.add(user)
            dirty = True

        if dirty:
            await session.commit()
