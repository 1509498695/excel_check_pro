"""Alembic environment configuration for Excel Check database migrations."""

from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import models as _models  # noqa: F401,E402
from backend.app.database import Base  # noqa: E402
from backend.app.db_migrations import (  # noqa: E402
    ensure_sqlite_database_parent,
    to_sync_database_url,
)
from backend.config import settings  # noqa: E402


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configured_database_url() -> str:
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url and not configured_url.startswith("driver://"):
        ensure_sqlite_database_parent(configured_url)
        return to_sync_database_url(configured_url)
    ensure_sqlite_database_parent(settings.db_url)
    return to_sync_database_url(settings.db_url)


def run_migrations_offline() -> None:
    """Run migrations without creating an Engine."""
    context.configure(
        url=_configured_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a synchronous Alembic Engine."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _configured_database_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
