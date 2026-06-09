"""规则配置存储与版本 API 测试。"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.auth.service import create_access_token, hash_password
from backend.app.database import async_session_factory
from backend.app.models import Project, RuleConfigRecord, User, UserProjectRole
from backend.run import app


CONTENT_MD = """
查询类型: 礼包
数据根: game_datas
配置文件: IAPConfig.xls

分页:
  - 名称: AbsolutePack
    ID字段: INT_PackageId
    名称字段: DESC
    输出字段:
      - INT_PackageId
""".strip()


async def _create_user_headers(project_id: int, *, role: str = "user") -> dict[str, str]:
    async with async_session_factory() as session:
        user = User(
            username=f"user_{uuid4().hex[:8]}",
            hashed_password=hash_password("pwd"),
            is_super_admin=False,
            primary_project_id=project_id,
        )
        session.add(user)
        await session.flush()
        session.add(UserProjectRole(user_id=user.id, project_id=project_id, role=role))
        await session.commit()
        token = create_access_token(user.id, project_id=project_id)
    return {"Authorization": f"Bearer {token}"}


async def _create_project(name: str | None = None) -> int:
    async with async_session_factory() as session:
        project = Project(name=name or f"project-{uuid4().hex[:8]}", description="")
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project.id


def _client(headers: dict[str, str]) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    )


@pytest.mark.anyio
async def test_project_member_can_save_draft(test_project_id: int) -> None:
    """普通项目成员可以保存 config_lookup 草稿。"""
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        response = await client.put(
            "/api/v1/rule-configs/config_lookup/draft",
            json={
                "content_md": CONTENT_MD,
                "expected_optimistic_lock_version": 0,
                "description": "初始草稿",
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["rule_family"] == "config_lookup"
    assert data["status"] == "draft"
    assert data["draft_version"] == 1
    assert data["published_version"] is None
    assert data["optimistic_lock_version"] == 1
    assert data["parsed_config_json"]["queries"][0]["query_type"] == "礼包"


@pytest.mark.anyio
async def test_project_member_can_publish(test_project_id: int) -> None:
    """普通项目成员可以直接发布结构合法的 Markdown。"""
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        response = await client.post(
            "/api/v1/rule-configs/config_lookup/publish",
            json={
                "content_md": CONTENT_MD,
                "expected_optimistic_lock_version": 0,
                "description": "发布 v1",
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "published"
    assert data["draft_version"] == 1
    assert data["published_version"] == 1
    assert data["published_at"] is not None


@pytest.mark.anyio
async def test_non_project_member_cannot_access(test_project_id: int) -> None:
    """非项目成员不能访问当前项目规则配置。"""
    other_project_id = await _create_project()
    headers = await _create_user_headers(other_project_id)
    token = headers["Authorization"].removeprefix("Bearer ")

    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.primary_project_id == other_project_id))
        user = result.scalar_one()
        forbidden_token = create_access_token(user.id, project_id=test_project_id)

    async with _client({"Authorization": f"Bearer {forbidden_token}"}) as client:
        response = await client.get("/api/v1/rule-configs/config_lookup")

    assert response.status_code == 403
    assert token != forbidden_token


@pytest.mark.anyio
async def test_version_conflict_returns_409(test_project_id: int) -> None:
    """保存草稿时旧 lock 不允许静默覆盖。"""
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        first = await client.put(
            "/api/v1/rule-configs/config_lookup/draft",
            json={"content_md": CONTENT_MD, "expected_optimistic_lock_version": 0},
        )
        conflict = await client.put(
            "/api/v1/rule-configs/config_lookup/draft",
            json={"content_md": CONTENT_MD, "expected_optimistic_lock_version": 0},
        )

    assert first.status_code == 200
    assert conflict.status_code == 409
    detail = conflict.json()["detail"]
    assert detail["code"] == "RULE_CONFIG_VERSION_CONFLICT"
    assert detail["current_optimistic_lock_version"] == 1


@pytest.mark.anyio
async def test_rollback_creates_new_draft_version_without_changing_published_version(
    test_project_id: int,
) -> None:
    """回滚产生新版本，但不静默替换已发布版本。"""
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        published = await client.post(
            "/api/v1/rule-configs/config_lookup/publish",
            json={"content_md": CONTENT_MD, "expected_optimistic_lock_version": 0},
        )
        changed_content = CONTENT_MD.replace("礼包", "活动")
        draft = await client.put(
            "/api/v1/rule-configs/config_lookup/draft",
            json={
                "content_md": changed_content,
                "expected_optimistic_lock_version": published.json()["data"]["optimistic_lock_version"],
            },
        )
        rollback = await client.post(
            "/api/v1/rule-configs/config_lookup/versions/1/rollback",
            json={
                "expected_optimistic_lock_version": draft.json()["data"]["optimistic_lock_version"],
                "description": "回滚到 v1",
            },
        )
        history = await client.get("/api/v1/rule-configs/config_lookup/versions")

    assert rollback.status_code == 200, rollback.text
    data = rollback.json()["data"]
    assert data["draft_version"] == 3
    assert data["published_version"] == 1
    assert data["status"] == "draft"
    assert history.json()["data"]["items"][0]["action"] == "rollback"


@pytest.mark.anyio
async def test_different_projects_have_independent_config_lookup(test_project_id: int) -> None:
    """不同项目可以各自拥有 config_lookup 当前文档。"""
    first_headers = await _create_user_headers(test_project_id)
    other_project_id = await _create_project()
    second_headers = await _create_user_headers(other_project_id)

    async with _client(first_headers) as first_client:
        first = await first_client.put(
            "/api/v1/rule-configs/config_lookup/draft",
            json={"content_md": CONTENT_MD, "expected_optimistic_lock_version": 0},
        )
    async with _client(second_headers) as second_client:
        second = await second_client.put(
            "/api/v1/rule-configs/config_lookup/draft",
            json={
                "content_md": CONTENT_MD.replace("礼包", "玩法开关"),
                "expected_optimistic_lock_version": 0,
            },
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["project_id"] == test_project_id
    assert second.json()["data"]["project_id"] == other_project_id


@pytest.mark.anyio
async def test_same_project_has_single_current_config_lookup_record(test_project_id: int) -> None:
    """同项目同 rule_family 只维护一条当前记录。"""
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        first = await client.put(
            "/api/v1/rule-configs/config_lookup/draft",
            json={"content_md": CONTENT_MD, "expected_optimistic_lock_version": 0},
        )
        second = await client.put(
            "/api/v1/rule-configs/config_lookup/draft",
            json={
                "content_md": CONTENT_MD.replace("礼包", "活动"),
                "expected_optimistic_lock_version": first.json()["data"]["optimistic_lock_version"],
            },
        )

    assert second.status_code == 200
    async with async_session_factory() as session:
        result = await session.execute(
            select(RuleConfigRecord).where(
                RuleConfigRecord.project_id == test_project_id,
                RuleConfigRecord.rule_family == "config_lookup",
            )
        )
        assert len(result.scalars().all()) == 1


@pytest.mark.anyio
async def test_only_config_lookup_rule_family_is_allowed(test_project_id: int) -> None:
    """第一阶段拒绝其它 rule_family。"""
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        response = await client.get("/api/v1/rule-configs/project_check")

    assert response.status_code == 400
    assert "config_lookup" in response.json()["detail"]


@pytest.mark.anyio
async def test_credential_status_does_not_expose_secrets(test_project_id: int) -> None:
    """凭据状态接口只返回脱敏状态，不暴露密码或 API Key。"""
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        response = await client.get("/api/v1/rule-configs/config_lookup/credentials/status")

    assert response.status_code == 200
    payload_text = response.text.lower()
    assert "password" not in payload_text
    assert "api_key" not in payload_text
    data = response.json()["data"]
    assert data["svn"]["configured"] is False
    assert data["ai"]["configured"] is False
