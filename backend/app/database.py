"""异步 SQLAlchemy 引擎与会话工厂，供全局复用。"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import inspect, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

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
    """应用启动时创建所有表结构（幂等操作），并确保默认项目与管理员存在。"""
    # 先显式导入 ORM 模型，确保 Base.metadata 已完整收集所有表。
    from backend.app import models as _models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _ensure_user_primary_project_column()
    await _ensure_execution_result_display_value_column()
    await _ensure_execution_result_extra_column()
    await _ensure_feishu_bot_download_columns()
    await _ensure_feishu_bot_app_id_unique_index()
    await ensure_default_auth_bootstrap()


async def ensure_default_auth_bootstrap() -> None:
    """确保默认项目、默认管理员与主归属项目口径处于可登录状态。"""
    default_project = await _seed_default_project()
    await _seed_default_super_admin(default_project.id)
    await _backfill_user_primary_projects()


async def _ensure_user_primary_project_column() -> None:
    """为已有运行时数据库补齐 users.primary_project_id 列。"""

    def _has_primary_project_column(sync_conn) -> bool:
        inspector = inspect(sync_conn)
        user_columns = inspector.get_columns("users")
        return any(column["name"] == "primary_project_id" for column in user_columns)

    async with engine.begin() as conn:
        has_column = await conn.run_sync(_has_primary_project_column)
        if not has_column:
            await conn.execute(text("ALTER TABLE users ADD COLUMN primary_project_id INTEGER"))


async def _ensure_execution_result_display_value_column() -> None:
    """为已有运行时数据库补齐 execution_result_items.display_value_json 列。"""

    def _has_display_value_column(sync_conn) -> bool:
        inspector = inspect(sync_conn)
        columns = inspector.get_columns("execution_result_items")
        return any(column["name"] == "display_value_json" for column in columns)

    async with engine.begin() as conn:
        has_column = await conn.run_sync(_has_display_value_column)
        if not has_column:
            await conn.execute(
                text(
                    "ALTER TABLE execution_result_items "
                    "ADD COLUMN display_value_json TEXT DEFAULT 'null'"
                )
            )


async def _ensure_execution_result_extra_column() -> None:
    """为已有运行时数据库补齐 execution_result_items.extra_json 列。"""

    def _has_extra_column(sync_conn) -> bool:
        inspector = inspect(sync_conn)
        columns = inspector.get_columns("execution_result_items")
        return any(column["name"] == "extra_json" for column in columns)

    async with engine.begin() as conn:
        has_column = await conn.run_sync(_has_extra_column)
        if not has_column:
            await conn.execute(
                text(
                    "ALTER TABLE execution_result_items "
                    "ADD COLUMN extra_json TEXT DEFAULT '{}'"
                )
            )


async def _ensure_feishu_bot_download_columns() -> None:
    """为已有运行时数据库补齐飞书机器人下载配置列。"""

    def _existing_columns(sync_conn) -> set[str]:
        inspector = inspect(sync_conn)
        return {column["name"] for column in inspector.get_columns("feishu_bot_configs")}

    columns_to_add = {
        "local_download_roots": "TEXT DEFAULT '[]'",
        "svn_download_roots": "TEXT DEFAULT '[]'",
        "allowed_download_suffixes": (
            "TEXT DEFAULT '[\".xls\",\".xlsx\",\".csv\",\".json\",\".xml\",\".txt\"]'"
        ),
    }

    async with engine.begin() as conn:
        existing_columns = await conn.run_sync(_existing_columns)
        for column_name, column_definition in columns_to_add.items():
            if column_name not in existing_columns:
                await conn.execute(
                    text(
                        f"ALTER TABLE feishu_bot_configs "
                        f"ADD COLUMN {column_name} {column_definition}"
                    )
                )


async def _ensure_feishu_bot_app_id_unique_index() -> None:
    """为 feishu_bot_configs.app_id 建立 partial unique index（仅对非空值生效）。

    使用 partial index 是为了允许多行 app_id='' 共存（未配置时的初始空值），
    同时强制已配置的 app_id 全局唯一，避免不同项目复用同一个飞书自建应用。
    """
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_feishu_bot_configs_app_id "
                "ON feishu_bot_configs(app_id) WHERE app_id <> ''"
            )
        )


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
