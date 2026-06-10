"""项目级 AI 凭据配置增强 API 测试。"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.ai.providers import ProviderConnectionError
from backend.app.auth.service import create_access_token, hash_password
from backend.app.database import async_session_factory
from backend.app.models import ProjectAiCredentialRecord, User, UserProjectRole
from backend.app.security.crypto import decrypt_secret
from backend.run import app


PROJECT_AI_PATH = "/api/v1/admin/projects/{project_id}/ai-config"


async def _create_user_headers(project_id: int, *, role: str = "user") -> dict[str, str]:
    async with async_session_factory() as session:
        user = User(
            username=f"project_ai_{uuid4().hex[:8]}",
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


async def _read_project_ai_record(project_id: int) -> ProjectAiCredentialRecord | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ProjectAiCredentialRecord).where(
                ProjectAiCredentialRecord.project_id == project_id
            )
        )
        return result.scalar_one_or_none()


def _client(headers: dict[str, str]) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    )


@pytest.mark.anyio
async def test_admin_can_save_project_ai_config_and_response_is_masked(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """管理员可保存项目级 AI 配置，API Key 加密落库且响应只返回脱敏值。"""
    response = await auth_client.put(
        PROJECT_AI_PATH.format(project_id=test_project_id),
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-project-secret",
            "enabled": True,
            "auto_match_threshold": 0.9,
            "candidate_threshold": 0.6,
            "max_candidates": 10,
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["configured"] is True
    assert data["enabled"] is True
    assert data["provider"] == "openai"
    assert data["model"] == "gpt-4o-mini"
    assert data["base_url"] == "https://api.openai.com/v1"
    assert data["masked_api_key"] == "sk-***cret"
    assert "sk-project-secret" not in response.text

    record = await _read_project_ai_record(test_project_id)
    assert record is not None
    assert record.encrypted_api_key != "sk-project-secret"
    assert decrypt_secret(record.encrypted_api_key) == "sk-project-secret"
    assert record.enabled is True
    assert record.updated_by is not None
    assert record.auto_match_threshold == 0.9
    assert record.candidate_threshold == 0.6
    assert record.max_candidates == 10


@pytest.mark.anyio
async def test_normal_member_cannot_modify_project_ai_config(test_project_id: int) -> None:
    """普通项目成员不能保存、删除或测试项目级 AI 凭据。"""
    headers = await _create_user_headers(test_project_id, role="user")
    async with _client(headers) as client:
        save = await client.put(
            PROJECT_AI_PATH.format(project_id=test_project_id),
            json={
                "provider": "openai",
                "model": "gpt-4o-mini",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-project-secret",
                "enabled": True,
            },
        )
        delete = await client.delete(PROJECT_AI_PATH.format(project_id=test_project_id))
        test = await client.post(
            f"{PROJECT_AI_PATH.format(project_id=test_project_id)}/test"
        )

    assert save.status_code == 403
    assert delete.status_code == 403
    assert test.status_code == 403


@pytest.mark.anyio
async def test_project_ai_threshold_validation(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """阈值必须满足 0-1、auto >= candidate、max_candidates 1-20。"""
    path = PROJECT_AI_PATH.format(project_id=test_project_id)
    invalid_threshold = await auth_client.put(
        path,
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-project-secret",
            "enabled": True,
            "auto_match_threshold": 0.5,
            "candidate_threshold": 0.7,
            "max_candidates": 10,
        },
    )
    invalid_candidates = await auth_client.put(
        path,
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-project-secret",
            "enabled": True,
            "auto_match_threshold": 0.9,
            "candidate_threshold": 0.6,
            "max_candidates": 21,
        },
    )

    assert invalid_threshold.status_code == 400
    assert "高置信自动返回阈值必须大于或等于候选列表阈值" in invalid_threshold.text
    assert invalid_candidates.status_code in {400, 422}
    assert "最大候选数量" in invalid_candidates.text or "max_candidates" in invalid_candidates.text


@pytest.mark.anyio
async def test_connection_test_success_updates_project_ai_status(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """项目级连接测试成功后记录 success 和 last_test_at。"""
    async def fake_test_provider_connection(**kwargs: Any) -> int:
        assert kwargs["api_key"] == "sk-project-secret"
        assert kwargs["model"] == "gpt-4o-mini"
        return 123

    monkeypatch.setattr(
        "backend.app.admin.router.test_provider_connection",
        fake_test_provider_connection,
        raising=False,
    )
    path = PROJECT_AI_PATH.format(project_id=test_project_id)
    await auth_client.put(
        path,
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-project-secret",
            "enabled": True,
        },
    )

    response = await auth_client.post(f"{path}/test")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["last_test_status"] == "success"
    assert data["last_test_at"] is not None
    assert data["last_test_error_summary"] == ""

    record = await _read_project_ai_record(test_project_id)
    assert record is not None
    assert record.last_test_status == "success"
    assert record.last_test_at is not None


@pytest.mark.anyio
async def test_connection_test_failure_does_not_expose_api_key(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """项目级连接测试失败时记录 failed，响应不暴露完整 API Key。"""
    async def fake_test_provider_connection(**_: Any) -> int:
        raise ProviderConnectionError(
            "auth_failed",
            "上游拒绝了 API Key sk-project-secret，请检查配置。",
            status_code=400,
        )

    monkeypatch.setattr(
        "backend.app.admin.router.test_provider_connection",
        fake_test_provider_connection,
        raising=False,
    )
    path = PROJECT_AI_PATH.format(project_id=test_project_id)
    await auth_client.put(
        path,
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-project-secret",
            "enabled": True,
        },
    )

    response = await auth_client.post(f"{path}/test")

    assert response.status_code == 400
    assert "sk-project-secret" not in response.text
    data = response.json()["data"]
    assert data["last_test_status"] == "failed"
    assert data["last_test_at"] is not None
    assert data["last_test_error_summary"]

    record = await _read_project_ai_record(test_project_id)
    assert record is not None
    assert record.last_test_status == "failed"
    assert "sk-project-secret" not in record.last_test_error_summary


@pytest.mark.anyio
async def test_copy_personal_ai_credential_endpoint_is_removed(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """个人 AI 凭据复制到项目级的接口已删除。"""
    registered_paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/v1/admin/projects/{project_id}/ai-config/copy-from-me" not in registered_paths

    response = await auth_client.post(
        f"{PROJECT_AI_PATH.format(project_id=test_project_id)}/copy-from-me"
    )

    assert response.status_code in {404, 405}


@pytest.mark.anyio
async def test_personal_ai_provider_api_is_removed(auth_client: AsyncClient) -> None:
    """个人 AI provider API 不再注册，项目级 AI API 是唯一后台配置入口。"""
    registered_paths = {getattr(route, "path", "") for route in app.routes}

    assert "/api/v1/ai/providers/me" not in registered_paths
    assert "/api/v1/ai/providers/test" not in registered_paths

    responses = [
        await auth_client.get("/api/v1/ai/providers/me"),
        await auth_client.put("/api/v1/ai/providers/me", json={}),
        await auth_client.delete("/api/v1/ai/providers/me"),
        await auth_client.post("/api/v1/ai/providers/test", json={}),
    ]
    assert all(response.status_code >= 400 for response in responses)


@pytest.mark.anyio
async def test_clearing_feishu_bot_config_keeps_project_ai_config(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """项目 AI 配置独立于飞书机器人基础配置，清除飞书配置不应删除 AI 凭据。"""
    ai_path = PROJECT_AI_PATH.format(project_id=test_project_id)
    await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot",
        json={
            "app_id": "cli_demo",
            "app_secret": "app-secret",
            "default_chat_id": "oc_default",
        },
    )
    await auth_client.put(
        ai_path,
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-project-secret",
            "enabled": True,
        },
    )

    delete_response = await auth_client.delete(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot"
    )
    ai_response = await auth_client.get(ai_path)

    assert delete_response.status_code == 204
    assert ai_response.status_code == 200
    assert ai_response.json()["data"]["configured"] is True
