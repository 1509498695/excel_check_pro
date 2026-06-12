"""规则配置按 rule_id 管理的 API 测试。"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.auth.service import create_access_token, hash_password
from backend.app.database import async_session_factory
from backend.app.models import (
    Project,
    ProjectAiCredentialRecord,
    ProjectQueryRootRecord,
    ProjectSvnCredentialRecord,
    RuleConfigRecord,
    RuleConfigVersionRecord,
    User,
    UserProjectRole,
)
from backend.app.config_lookup.schemas import ConfigLookupRequest
from backend.app.config_lookup.service import lookup_config_table
from backend.app.security.crypto import encrypt_secret
from backend.run import app


def content_md(query_type: str = "礼包") -> str:
    return f"""
查询类型: {query_type}
数据根: game_datas
配置文件: IAPConfig.xls

  - 分页名称: AbsolutePack
  - 匹配字段
    - ID字段: INT_PackageId
    - 礼包名称: DESC
  - 输出字段
    - 礼包ID: INT_PackageId
    - 礼包名称:DESC
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


async def _seed_query_root(
    project_id: int,
    *,
    alias: str = "game_datas",
    status: str = "enabled",
) -> None:
    async with async_session_factory() as session:
        session.add(
            ProjectQueryRootRecord(
                project_id=project_id,
                alias=alias,
                display_name="游戏配置主目录",
                svn_root_url="https://svn.example.com/game_datas",
                status=status,
            )
        )
        await session.commit()


async def _seed_project_credentials(project_id: int) -> None:
    async with async_session_factory() as session:
        session.add(
            ProjectSvnCredentialRecord(
                project_id=project_id,
                username="svn_admin",
                password_cipher=encrypt_secret("svn_password"),
            )
        )
        session.add(
            ProjectAiCredentialRecord(
                project_id=project_id,
                provider_preset="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                encrypted_api_key=encrypt_secret("sk-project-secret"),
                extra_headers_json='{"X-Project":"ExcelCheck"}',
                enabled=True,
                last_test_status="success",
            )
        )
        await session.commit()


def _client(headers: dict[str, str]) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    )


async def _create_rule(
    client: AsyncClient,
    query_type: str = "礼包",
    *,
    description: str = "创建草稿",
) -> dict:
    response = await client.post(
        "/api/v1/rule-configs/config_lookup",
        json={"content_md": content_md(query_type), "description": description},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.anyio
async def test_create_query_rule_success(test_project_id: int) -> None:
    """项目成员可以创建一条 config_lookup 查询规则草稿。"""
    await _seed_query_root(test_project_id)
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        data = await _create_rule(client)

    assert data["rule_id"] == data["id"]
    assert data["rule_family"] == "config_lookup"
    assert data["query_type"] == "礼包"
    assert data["status"] == "draft"
    assert data["draft_version"] == 1
    assert data["published_version"] is None
    assert data["optimistic_lock_version"] == 1
    assert data["parsed_config_json"]["query_type"] == "礼包"
    async with async_session_factory() as session:
        version_result = await session.execute(
            select(RuleConfigVersionRecord).where(
                RuleConfigVersionRecord.rule_config_id == data["rule_id"]
            )
        )
    assert version_result.scalars().all() == []


@pytest.mark.anyio
async def test_same_project_duplicate_query_type_fails(test_project_id: int) -> None:
    """同项目同规则族内 query_type 唯一。"""
    await _seed_query_root(test_project_id)
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        await _create_rule(client, "礼包")
        duplicate = await client.post(
            "/api/v1/rule-configs/config_lookup",
            json={"content_md": content_md("礼包")},
        )

    assert duplicate.status_code == 400
    detail = duplicate.json()["detail"]
    assert detail["code"] == "RULE_CONFIG_VALIDATION_FAILED"
    assert "查询类型已存在：礼包" in detail["errors"]


@pytest.mark.anyio
async def test_different_projects_can_reuse_query_type(test_project_id: int) -> None:
    """不同项目可以使用同名 query_type。"""
    await _seed_query_root(test_project_id)
    first_headers = await _create_user_headers(test_project_id)
    other_project_id = await _create_project()
    await _seed_query_root(other_project_id)
    second_headers = await _create_user_headers(other_project_id)

    async with _client(first_headers) as first_client:
        first = await _create_rule(first_client, "礼包")
    async with _client(second_headers) as second_client:
        second = await _create_rule(second_client, "礼包")

    assert first["project_id"] == test_project_id
    assert second["project_id"] == other_project_id
    assert first["query_type"] == second["query_type"] == "礼包"


@pytest.mark.anyio
async def test_unpublished_draft_can_rename_query_type(test_project_id: int) -> None:
    """未发布草稿允许通过 Markdown 修改查询类型。"""
    await _seed_query_root(test_project_id)
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        created = await _create_rule(client, "礼包")
        response = await client.put(
            f"/api/v1/rule-configs/config_lookup/{created['rule_id']}/draft",
            json={
                "content_md": content_md("玩法开关"),
                "expected_optimistic_lock_version": created["optimistic_lock_version"],
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["query_type"] == "玩法开关"
    assert data["draft_version"] == 1


@pytest.mark.anyio
async def test_publish_history_records_only_publish_entries(test_project_id: int) -> None:
    """发布历史只记录发布成功的版本，创建和保存草稿不进入历史。"""
    await _seed_query_root(test_project_id)
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        created = await _create_rule(client, "礼包")
        initial_history = await client.get(
            f"/api/v1/rule-configs/config_lookup/{created['rule_id']}/versions"
        )
        saved = await client.put(
            f"/api/v1/rule-configs/config_lookup/{created['rule_id']}/draft",
            json={
                "content_md": content_md("礼包"),
                "expected_optimistic_lock_version": created["optimistic_lock_version"],
                "description": "保存草稿",
            },
        )
        draft_history = await client.get(
            f"/api/v1/rule-configs/config_lookup/{created['rule_id']}/versions"
        )
        published = await client.post(
            f"/api/v1/rule-configs/config_lookup/{created['rule_id']}/publish",
            json={
                "content_md": content_md("礼包"),
                "expected_optimistic_lock_version": saved.json()["data"][
                    "optimistic_lock_version"
                ],
                "description": "发布规则",
            },
        )
        publish_history = await client.get(
            f"/api/v1/rule-configs/config_lookup/{created['rule_id']}/versions"
        )

    assert initial_history.status_code == 200
    assert initial_history.json()["data"]["items"] == []
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["draft_version"] == 1
    assert draft_history.json()["data"]["items"] == []
    assert published.status_code == 200, published.text
    assert published.json()["data"]["published_version"] == 1
    assert published.json()["data"]["draft_version"] == 1
    items = publish_history.json()["data"]["items"]
    assert [row["action"] for row in items] == ["publish"]
    assert [row["status"] for row in items] == ["published"]
    assert [row["version"] for row in items] == [1]


@pytest.mark.anyio
async def test_published_query_type_cannot_be_renamed(test_project_id: int) -> None:
    """已发布过的查询类型不允许直接改名。"""
    await _seed_query_root(test_project_id)
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        created = await _create_rule(client, "礼包")
        published = await client.post(
            f"/api/v1/rule-configs/config_lookup/{created['rule_id']}/publish",
            json={
                "content_md": content_md("礼包"),
                "expected_optimistic_lock_version": created["optimistic_lock_version"],
            },
        )
        renamed = await client.put(
            f"/api/v1/rule-configs/config_lookup/{created['rule_id']}/draft",
            json={
                "content_md": content_md("玩法开关"),
                "expected_optimistic_lock_version": published.json()["data"][
                    "optimistic_lock_version"
                ],
            },
        )

    assert published.status_code == 200, published.text
    assert renamed.status_code == 400
    detail = renamed.json()["detail"]
    assert detail["code"] == "RULE_CONFIG_VALIDATION_FAILED"
    assert "已发布过的查询类型不允许直接改名" in detail["errors"]


@pytest.mark.anyio
async def test_save_draft_version_conflict_returns_409(test_project_id: int) -> None:
    """保存草稿时旧 lock 不允许静默覆盖。"""
    await _seed_query_root(test_project_id)
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        created = await _create_rule(client)
        response = await client.put(
            f"/api/v1/rule-configs/config_lookup/{created['rule_id']}/draft",
            json={
                "content_md": content_md("礼包"),
                "expected_optimistic_lock_version": 0,
            },
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "RULE_CONFIG_VERSION_CONFLICT"
    assert detail["current_optimistic_lock_version"] == 1


@pytest.mark.anyio
async def test_publish_version_conflict_returns_409(test_project_id: int) -> None:
    """发布时旧 lock 不允许静默覆盖。"""
    await _seed_query_root(test_project_id)
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        created = await _create_rule(client)
        response = await client.post(
            f"/api/v1/rule-configs/config_lookup/{created['rule_id']}/publish",
            json={
                "content_md": content_md("礼包"),
                "expected_optimistic_lock_version": 0,
            },
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "RULE_CONFIG_VERSION_CONFLICT"
    assert detail["current_optimistic_lock_version"] == 1


@pytest.mark.anyio
async def test_rollback_only_affects_current_rule_id(test_project_id: int) -> None:
    """回滚按 rule_id 替换当前草稿，不新增发布历史且不影响其它查询规则。"""
    await _seed_query_root(test_project_id)
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        gift = await _create_rule(client, "礼包")
        activity = await _create_rule(client, "活动")
        gift_published = await client.post(
            f"/api/v1/rule-configs/config_lookup/{gift['rule_id']}/publish",
            json={
                "content_md": content_md("礼包"),
                "expected_optimistic_lock_version": gift["optimistic_lock_version"],
            },
        )
        gift_draft = await client.put(
            f"/api/v1/rule-configs/config_lookup/{gift['rule_id']}/draft",
            json={
                "content_md": content_md("礼包"),
                "expected_optimistic_lock_version": gift_published.json()["data"][
                    "optimistic_lock_version"
                ],
                "description": "修改草稿",
            },
        )
        rollback = await client.post(
            f"/api/v1/rule-configs/config_lookup/{gift['rule_id']}/versions/1/rollback",
            json={
                "expected_optimistic_lock_version": gift_draft.json()["data"][
                    "optimistic_lock_version"
                ],
                "description": "回滚到 v1",
            },
        )
        activity_detail = await client.get(
            f"/api/v1/rule-configs/config_lookup/{activity['rule_id']}"
        )
        gift_history = await client.get(
            f"/api/v1/rule-configs/config_lookup/{gift['rule_id']}/versions"
        )
        activity_history = await client.get(
            f"/api/v1/rule-configs/config_lookup/{activity['rule_id']}/versions"
        )
        republished = await client.post(
            f"/api/v1/rule-configs/config_lookup/{gift['rule_id']}/publish",
            json={
                "content_md": content_md("礼包"),
                "expected_optimistic_lock_version": rollback.json()["data"][
                    "optimistic_lock_version"
                ],
                "description": "发布回滚草稿",
            },
        )
        republished_history = await client.get(
            f"/api/v1/rule-configs/config_lookup/{gift['rule_id']}/versions"
        )

        assert rollback.status_code == 200, rollback.text
    assert rollback.json()["data"]["draft_version"] == 2
    assert rollback.json()["data"]["published_version"] == 1
    assert activity_detail.json()["data"]["draft_version"] == 1
    assert [row["action"] for row in gift_history.json()["data"]["items"]] == [
        "publish",
    ]
    assert activity_history.json()["data"]["items"] == []
    assert republished.status_code == 200, republished.text
    assert republished.json()["data"]["published_version"] == 2
    assert [row["version"] for row in republished_history.json()["data"]["items"]] == [2, 1]


@pytest.mark.anyio
async def test_list_returns_only_current_project_rules(test_project_id: int) -> None:
    """列表接口只返回当前 token 项目的查询规则。"""
    await _seed_query_root(test_project_id)
    headers = await _create_user_headers(test_project_id)
    other_project_id = await _create_project()
    await _seed_query_root(other_project_id)
    other_headers = await _create_user_headers(other_project_id)

    async with _client(headers) as client:
        await _create_rule(client, "礼包")
        await _create_rule(client, "玩法开关")
        response = await client.get("/api/v1/rule-configs/config_lookup")
    async with _client(other_headers) as other_client:
        await _create_rule(other_client, "活动")

    data = response.json()["data"]
    assert response.status_code == 200
    assert data["total"] == 2
    assert {item["query_type"] for item in data["items"]} == {"礼包", "玩法开关"}
    assert all(item["project_id"] == test_project_id for item in data["items"])


@pytest.mark.anyio
async def test_member_can_delete_draft_rule_and_history(test_project_id: int) -> None:
    """项目成员可以硬删除草稿规则，版本历史随规则清理。"""
    await _seed_query_root(test_project_id)
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        created = await _create_rule(client, "礼包")
        delete_response = await client.delete(
            f"/api/v1/rule-configs/config_lookup/{created['rule_id']}",
            params={
                "expected_optimistic_lock_version": created[
                    "optimistic_lock_version"
                ]
            },
        )
        detail_response = await client.get(
            f"/api/v1/rule-configs/config_lookup/{created['rule_id']}"
        )
        list_response = await client.get("/api/v1/rule-configs/config_lookup")

    assert delete_response.status_code == 204
    assert detail_response.status_code == 404
    assert list_response.json()["data"]["total"] == 0
    async with async_session_factory() as session:
        rule_result = await session.execute(
            select(RuleConfigRecord).where(RuleConfigRecord.id == created["rule_id"])
        )
        version_result = await session.execute(
            select(RuleConfigVersionRecord).where(
                RuleConfigVersionRecord.rule_config_id == created["rule_id"]
            )
        )
    assert rule_result.scalars().all() == []
    assert version_result.scalars().all() == []


@pytest.mark.anyio
async def test_member_can_delete_published_rule_without_affecting_other_rules(
    test_project_id: int,
) -> None:
    """已发布规则也可删除，且只影响当前 rule_id。"""
    await _seed_query_root(test_project_id)
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        gift = await _create_rule(client, "礼包")
        activity = await _create_rule(client, "活动")
        published_gift = await client.post(
            f"/api/v1/rule-configs/config_lookup/{gift['rule_id']}/publish",
            json={
                "content_md": content_md("礼包"),
                "expected_optimistic_lock_version": gift["optimistic_lock_version"],
            },
        )
        published_activity = await client.post(
            f"/api/v1/rule-configs/config_lookup/{activity['rule_id']}/publish",
            json={
                "content_md": content_md("活动"),
                "expected_optimistic_lock_version": activity[
                    "optimistic_lock_version"
                ],
            },
        )
        delete_response = await client.delete(
            f"/api/v1/rule-configs/config_lookup/{gift['rule_id']}",
            params={
                "expected_optimistic_lock_version": published_gift.json()["data"][
                    "optimistic_lock_version"
                ]
            },
        )
        list_response = await client.get("/api/v1/rule-configs/config_lookup")

    assert published_gift.status_code == 200, published_gift.text
    assert published_activity.status_code == 200, published_activity.text
    assert delete_response.status_code == 204
    items = list_response.json()["data"]["items"]
    assert [item["query_type"] for item in items] == ["活动"]
    async with async_session_factory() as session:
        runtime_result = await lookup_config_table(
            session,
            ConfigLookupRequest(
                project_id=test_project_id,
                query_type="礼包",
                versioned_config_folder="/datas_qa88",
                lookup_input="26060405",
            ),
        )
    assert runtime_result.status == "not_found"
    assert runtime_result.message == "查询类型不存在：礼包"


@pytest.mark.anyio
async def test_delete_rule_rejects_non_member_and_missing_rule(
    test_project_id: int,
) -> None:
    """非项目成员不可删除；不存在的 rule_id 返回 404。"""
    await _seed_query_root(test_project_id)
    owner_headers = await _create_user_headers(test_project_id)
    other_project_id = await _create_project()
    other_headers = await _create_user_headers(other_project_id)

    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.primary_project_id == other_project_id))
        user = result.scalar_one()
        forbidden_token = create_access_token(user.id, project_id=test_project_id)

    async with _client(owner_headers) as client:
        created = await _create_rule(client, "礼包")
        missing_response = await client.delete(
            "/api/v1/rule-configs/config_lookup/999999",
            params={"expected_optimistic_lock_version": 0},
        )
    async with _client({"Authorization": f"Bearer {forbidden_token}"}) as forbidden_client:
        forbidden_response = await forbidden_client.delete(
            f"/api/v1/rule-configs/config_lookup/{created['rule_id']}",
            params={
                "expected_optimistic_lock_version": created[
                    "optimistic_lock_version"
                ]
            },
        )

    assert other_headers["Authorization"] != f"Bearer {forbidden_token}"
    assert missing_response.status_code == 404
    assert forbidden_response.status_code == 403


@pytest.mark.anyio
async def test_delete_rule_version_conflict_returns_409(test_project_id: int) -> None:
    """删除也必须带当前乐观锁版本，旧 lock 返回冲突。"""
    await _seed_query_root(test_project_id)
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        created = await _create_rule(client, "礼包")
        response = await client.delete(
            f"/api/v1/rule-configs/config_lookup/{created['rule_id']}",
            params={"expected_optimistic_lock_version": 0},
        )
        detail_response = await client.get(
            f"/api/v1/rule-configs/config_lookup/{created['rule_id']}"
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "RULE_CONFIG_VERSION_CONFLICT"
    assert detail["current_optimistic_lock_version"] == 1
    assert detail_response.status_code == 200


@pytest.mark.anyio
async def test_validate_endpoint_is_rule_scoped(test_project_id: int) -> None:
    """结构校验按 rule_id 校验改名和唯一性，但不保存。"""
    await _seed_query_root(test_project_id)
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        gift = await _create_rule(client, "礼包")
        await _create_rule(client, "玩法开关")
        response = await client.post(
            f"/api/v1/rule-configs/config_lookup/{gift['rule_id']}/validate",
            json={"content_md": content_md("玩法开关")},
        )
        detail = await client.get(
            f"/api/v1/rule-configs/config_lookup/{gift['rule_id']}"
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["ok"] is False
    assert "查询类型已存在：玩法开关" in data["errors"]
    assert detail.json()["data"]["query_type"] == "礼包"


@pytest.mark.anyio
async def test_validation_failure_returns_error_list(test_project_id: int) -> None:
    """创建规则时结构校验失败返回明确错误码和中文错误列表。"""
    await _seed_query_root(test_project_id)
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        response = await client.post(
            "/api/v1/rule-configs/config_lookup",
            json={"content_md": content_md("礼包").replace("数据根: game_datas\n", "")},
        )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "RULE_CONFIG_VALIDATION_FAILED"
    assert "缺少必填字段：数据根" in detail["errors"]
    assert "summary" in detail


@pytest.mark.anyio
async def test_missing_query_root_alias_blocks_create(test_project_id: int) -> None:
    """未配置项目 query_roots alias 时不能创建规则。"""
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        response = await client.post(
            "/api/v1/rule-configs/config_lookup",
            json={"content_md": content_md("礼包")},
        )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "RULE_CONFIG_VALIDATION_FAILED"
    assert "数据根 alias 不存在：game_datas" in detail["errors"]


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
async def test_only_config_lookup_rule_family_is_allowed(test_project_id: int) -> None:
    """当前拒绝其它 rule_family。"""
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        response = await client.get("/api/v1/rule-configs/project_check")

    assert response.status_code == 400
    assert "config_lookup" in response.json()["detail"]


@pytest.mark.anyio
async def test_credential_status_does_not_expose_secrets(test_project_id: int) -> None:
    """凭据状态接口只返回脱敏状态，不暴露密码或 API Key。"""
    await _seed_project_credentials(test_project_id)
    headers = await _create_user_headers(test_project_id)

    async with _client(headers) as client:
        response = await client.get("/api/v1/rule-configs/config_lookup/credentials/status")

    assert response.status_code == 200
    payload_text = response.text.lower()
    assert "password" not in payload_text
    assert "sk-project-secret" not in payload_text
    data = response.json()["data"]
    assert data["svn"]["configured"] is True
    assert data["svn"]["account_masked"] == "svn_admin"
    assert data["svn"]["updated_at"] is not None
    assert data["ai"]["configured"] is True
    assert data["ai"]["enabled"] is True
    assert data["ai"]["provider"] == "openai"
    assert data["ai"]["model"] == "gpt-4o-mini"
    assert data["ai"]["base_url"] == "https://api.openai.com/v1"
    assert data["ai"]["masked_api_key"] == "sk-***cret"
    assert data["ai"]["last_test_status"] == "success"
    assert data["ai"]["last_test_at"] is None
    assert data["ai"]["updated_at"] is not None
