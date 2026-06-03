"""数据库结构迁移入口，封装应用启动时的 Alembic 调用。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from backend.config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


def to_sync_database_url(db_url: str) -> str:
    """将应用使用的异步 DB URL 转为 Alembic 可用的同步 URL。"""
    url = make_url(db_url)
    if url.drivername == "sqlite+aiosqlite":
        url = url.set(drivername="sqlite")
    return url.render_as_string(hide_password=False)


def ensure_sqlite_database_parent(db_url: str) -> None:
    """SQLite 文件库迁移前先确保父目录存在，适配干净源码首次初始化。"""
    url = make_url(to_sync_database_url(db_url))
    if not url.drivername.startswith("sqlite"):
        return
    if not url.database or url.database == ":memory:":
        return

    database_path = Path(url.database)
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)


def make_alembic_config(db_url: str | None = None) -> Config:
    """生成 Alembic 配置，并用当前应用配置覆盖 ini 中的占位 URL。"""
    resolved_db_url = db_url or settings.db_url
    ensure_sqlite_database_parent(resolved_db_url)
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", to_sync_database_url(resolved_db_url))
    return config


def run_database_migrations(
    db_url: str | None = None,
    *,
    revision: str = "head",
) -> None:
    """同步执行数据库迁移，供 CLI 测试和启动线程复用。"""
    command.upgrade(make_alembic_config(db_url), revision)


async def run_database_migrations_async(
    db_url: str | None = None,
    *,
    revision: str = "head",
) -> None:
    """异步应用启动路径使用的迁移入口，避免阻塞事件循环。"""
    await asyncio.to_thread(run_database_migrations, db_url, revision=revision)
