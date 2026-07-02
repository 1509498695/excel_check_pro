"""Project Vision AI credential API tests."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.ai.providers import ProviderConnectionError
from backend.app.auth.service import create_access_token, hash_password
from backend.app.database import async_session_factory
from backend.app.models import ProjectVisionAiCredentialRecord, User, UserProjectRole
from backend.app.security.crypto import decrypt_secret
from backend.run import app


PROJECT_VISION_AI_PATH = "/api/v1/admin/projects/{project_id}/vision-ai-config"


async def _create_user_headers(project_id: int, *, role: str = "user") -> dict[str, str]:
    async with async_session_factory() as session:
        user = User(
            username=f"project_vision_ai_{uuid4().hex[:8]}",
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


async def _read_project_vision_ai_record(
    project_id: int,
) -> ProjectVisionAiCredentialRecord | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ProjectVisionAiCredentialRecord).where(
                ProjectVisionAiCredentialRecord.project_id == project_id
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
async def test_admin_can_save_project_vision_ai_config_and_response_is_masked(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    response = await auth_client.put(
        PROJECT_VISION_AI_PATH.format(project_id=test_project_id),
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-project-vision-secret",
            "enabled": True,
            "extra_headers": {"X-Test": "vision"},
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
    assert data["has_extra_headers"] is True
    assert "sk-project-vision-secret" not in response.text

    record = await _read_project_vision_ai_record(test_project_id)
    assert record is not None
    assert record.encrypted_api_key != "sk-project-vision-secret"
    assert decrypt_secret(record.encrypted_api_key) == "sk-project-vision-secret"
    assert record.enabled is True
    assert record.updated_by is not None


@pytest.mark.anyio
async def test_normal_member_cannot_modify_project_vision_ai_config(
    test_project_id: int,
) -> None:
    headers = await _create_user_headers(test_project_id, role="user")
    async with _client(headers) as client:
        save = await client.put(
            PROJECT_VISION_AI_PATH.format(project_id=test_project_id),
            json={
                "provider": "openai",
                "model": "gpt-4o-mini",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-project-vision-secret",
                "enabled": True,
            },
        )
        delete = await client.delete(
            PROJECT_VISION_AI_PATH.format(project_id=test_project_id)
        )
        test = await client.post(
            f"{PROJECT_VISION_AI_PATH.format(project_id=test_project_id)}/test"
        )

    assert save.status_code == 403
    assert delete.status_code == 403
    assert test.status_code == 403


@pytest.mark.anyio
async def test_project_vision_ai_connection_test_updates_status_and_sanitizes_failure(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_failure(**kwargs: Any) -> int:
        assert kwargs["api_key"] == "sk-project-vision-secret"
        raise ProviderConnectionError(
            "auth_failed",
            "Vision API Key sk-project-vision-secret 无权限。",
            status_code=400,
        )

    monkeypatch.setattr(
        "backend.app.admin.router.test_provider_vision_connection",
        fake_failure,
        raising=False,
    )
    path = PROJECT_VISION_AI_PATH.format(project_id=test_project_id)
    await auth_client.put(
        path,
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-project-vision-secret",
            "enabled": True,
        },
    )

    failed = await auth_client.post(f"{path}/test")

    assert failed.status_code == 400
    assert "sk-project-vision-secret" not in failed.text
    assert failed.json()["data"]["last_test_status"] == "failed"

    async def fake_success(**kwargs: Any) -> int:
        assert kwargs["api_key"] == "sk-project-vision-secret"
        return 123

    monkeypatch.setattr(
        "backend.app.admin.router.test_provider_vision_connection",
        fake_success,
        raising=False,
    )

    success = await auth_client.post(f"{path}/test")

    assert success.status_code == 200, success.text
    assert success.json()["data"]["last_test_status"] == "success"
    assert success.json()["data"]["last_test_at"] is not None
    assert success.json()["data"]["last_test_error_summary"] == ""


@pytest.mark.anyio
async def test_project_vision_ai_config_is_independent_from_text_ai_config(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    vision_path = PROJECT_VISION_AI_PATH.format(project_id=test_project_id)
    text_path = f"/api/v1/admin/projects/{test_project_id}/ai-config"
    await auth_client.put(
        vision_path,
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-project-vision-secret",
            "enabled": True,
        },
    )
    await auth_client.put(
        text_path,
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-project-text-secret",
            "enabled": True,
        },
    )

    delete_text = await auth_client.delete(text_path)
    vision = await auth_client.get(vision_path)

    assert delete_text.status_code == 204
    assert vision.status_code == 200
    assert vision.json()["data"]["configured"] is True
