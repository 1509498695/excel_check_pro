"""测试公共 fixtures：提供认证上下文和数据库初始化。"""

from __future__ import annotations

import json
import os
from pathlib import Path


TEST_DB_PATH = Path(__file__).resolve().parents[1] / ".runtime" / "test_excel_check.db"
os.environ.setdefault("DB_URL", f"sqlite+aiosqlite:///{TEST_DB_PATH}")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from backend.app.auth.service import create_access_token, hash_password
from backend.app.database import (
    Base,
    _ensure_feishu_bot_download_columns,
    async_session_factory,
    engine,
)
from backend.app.models import FixedRulesConfigRecord, Project, User, UserProjectRole
from backend.run import app


@pytest.fixture
async def test_db():
    """在每个测试前创建表结构，测试结束后清理。"""
    # 显式导入模型，确保测试环境中的 metadata 完整可用。
    from backend.app import models as _models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _ensure_feishu_bot_download_columns()
    async with async_session_factory() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(delete(table))
        await session.commit()

    yield

    async with async_session_factory() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(delete(table))
        await session.commit()


@pytest.fixture
async def _auth_context(test_db) -> tuple[dict[str, str], int]:
    """创建测试用户和项目，返回 (headers, project_id)。"""
    async with async_session_factory() as session:
        project = Project(name="test-project", description="测试项目")
        session.add(project)
        await session.flush()
        project_id: int = project.id

        user = User(
            username="testuser",
            hashed_password=hash_password("testpass"),
            is_super_admin=True,
            primary_project_id=project_id,
        )
        session.add(user)
        await session.flush()

        role = UserProjectRole(
            user_id=user.id,
            project_id=project_id,
            role="admin",
        )
        session.add(role)
        await session.commit()

        token = create_access_token(user.id, project_id=project_id)

    return {"Authorization": f"Bearer {token}"}, project_id


@pytest.fixture
async def auth_headers(_auth_context) -> dict[str, str]:
    """返回带有 Bearer Token 的 headers。"""
    return _auth_context[0]


@pytest.fixture
async def test_project_id(_auth_context) -> int:
    """返回测试项目 ID。"""
    return _auth_context[1]


@pytest.fixture
async def auth_client(auth_headers) -> AsyncClient:
    """返回已认证的异步测试客户端。"""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=auth_headers,
    ) as client:
        yield client


async def seed_fixed_rules_config(config_dict: dict, project_id: int) -> None:
    """直接向数据库插入固定规则配置，用于测试预填充场景。"""
    async with async_session_factory() as session:
        record = FixedRulesConfigRecord(
            project_id=project_id,
            config_json=json.dumps(config_dict, ensure_ascii=False),
        )
        session.add(record)
        await session.commit()
