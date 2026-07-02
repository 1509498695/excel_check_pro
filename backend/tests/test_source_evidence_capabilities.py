"""Source Evidence runtime capability status API tests."""

from __future__ import annotations

import datetime
import subprocess
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from backend.app.auth.service import create_access_token, hash_password
from backend.app.database import async_session_factory
from backend.app.models import (
    ProjectSourceEvidenceSvnRootRecord,
    ProjectSvnCredentialRecord,
    ProjectVisionAiCredentialRecord,
    SourceEvidenceRunRecord,
    User,
    UserProjectRole,
)
from backend.app.security.crypto import encrypt_secret
from backend.app.test_cases import source_evidence_capabilities
from backend.run import app


CAPABILITY_PATH = "/api/v1/test-cases/source-evidence-capabilities"


@pytest.fixture(autouse=True)
def _capability_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        source_evidence_capabilities,
        "settings",
        SimpleNamespace(
            source_evidence_soffice_executable="",
            source_evidence_xls_convert_timeout_seconds=3,
        ),
    )


async def _create_member_headers(project_id: int, *, role: str = "user") -> dict[str, str]:
    async with async_session_factory() as session:
        user = User(
            username=f"se-capability-{uuid4().hex[:8]}",
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


@pytest.mark.anyio
async def test_member_can_read_missing_capabilities_without_sensitive_details(
    test_db,
    test_project_id: int,
) -> None:
    headers = await _create_member_headers(test_project_id, role="user")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    ) as client:
        response = await client.get(CAPABILITY_PATH)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["svn_credential_configured"] is False
    assert data["source_evidence_svn_roots_configured"] is False
    assert data["vision_ai_configured"] is False
    assert data["soffice_configured"] is False
    assert data["soffice_available"] is False
    assert data["is_project_admin"] is False
    assert "admin_details" not in data
    text = response.text
    assert "当前未配置视觉模型" in text
    assert "请联系项目管理员" in text
    assert "sk-" not in text
    assert "svn_password" not in text


@pytest.mark.anyio
async def test_admin_sees_configured_capabilities_and_sanitized_admin_summary(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with async_session_factory() as session:
        session.add(
            ProjectSvnCredentialRecord(
                project_id=test_project_id,
                username="svn-admin",
                password_cipher=encrypt_secret("svn_password_secret"),
            )
        )
        session.add(
            ProjectSourceEvidenceSvnRootRecord(
                project_id=test_project_id,
                alias="design",
                display_name="Design Root",
                svn_root_url="https://samosvn/data/project/design/",
                status="enabled",
            )
        )
        session.add(
            ProjectVisionAiCredentialRecord(
                project_id=test_project_id,
                provider_preset="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                encrypted_api_key=encrypt_secret("sk-project-vision-secret"),
                enabled=True,
                last_test_status="failed",
                last_test_error_summary="Vision key sk-project-vision-secret failed",
            )
        )
        await session.commit()

    monkeypatch.setattr(
        source_evidence_capabilities,
        "settings",
        SimpleNamespace(
            source_evidence_soffice_executable="soffice",
            source_evidence_xls_convert_timeout_seconds=5,
        ),
    )
    monkeypatch.setattr(source_evidence_capabilities.shutil, "which", lambda _name: "soffice")
    monkeypatch.setattr(
        source_evidence_capabilities.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="LibreOffice 7.6.0\n",
            stderr="",
        ),
    )

    response = await auth_client.get(CAPABILITY_PATH)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["svn_credential_configured"] is True
    assert data["source_evidence_svn_roots_configured"] is True
    assert data["vision_ai_configured"] is True
    assert data["soffice_configured"] is True
    assert data["soffice_available"] is True
    assert data["is_project_admin"] is True
    assert data["admin_details"]["config_entry"] == "/admin"
    assert data["admin_details"]["enabled_source_evidence_svn_root_count"] == 1
    assert data["admin_details"]["vision_ai_last_test_status"] == "failed"
    assert "LibreOffice 7.6.0" in data["admin_details"]["soffice_detection_summary"]
    text = response.text
    assert "svn_password_secret" not in text
    assert "sk-project-vision-secret" not in text
    assert "--version" not in text


@pytest.mark.anyio
async def test_successful_vision_status_hides_stale_failure_summary(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    async with async_session_factory() as session:
        await session.execute(
            delete(ProjectVisionAiCredentialRecord).where(
                ProjectVisionAiCredentialRecord.project_id == test_project_id
            )
        )
        session.add(
            ProjectVisionAiCredentialRecord(
                project_id=test_project_id,
                provider_preset="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                encrypted_api_key=encrypt_secret("sk-project-vision-secret"),
                enabled=True,
                last_test_status="success",
                last_test_error_summary="历史失败：sk-project-vision-secret 无权限",
            )
        )
        await session.commit()

    response = await auth_client.get(CAPABILITY_PATH)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["vision_ai_configured"] is True
    assert data["admin_details"]["vision_ai_last_test_status"] == "success"
    assert data["admin_details"]["vision_ai_last_test_error_summary"] == ""
    assert "历史失败" not in response.text
    assert "sk-project-vision-secret" not in response.text


@pytest.mark.anyio
async def test_vision_missing_warns_but_does_not_block_text_source_evidence_run(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    async with async_session_factory() as session:
        run = SourceEvidenceRunRecord(
            project_id=test_project_id,
            source_type="local_file",
            source_identifier="sha256:text",
            source_title="Text Only.xlsx",
            source_url="",
            status="ready",
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(run)
        await session.commit()
        run_id = run.id

    capability_response = await auth_client.get(CAPABILITY_PATH)
    run_response = await auth_client.get(f"/api/v1/test-cases/source-evidence-runs/{run_id}")

    assert capability_response.status_code == 200
    assert capability_response.json()["data"]["vision_ai_configured"] is False
    assert "当前未配置视觉模型" in capability_response.text
    assert run_response.status_code == 200
    assert run_response.json()["data"]["status"] == "ready"


@pytest.mark.anyio
async def test_member_capability_status_does_not_trigger_admin_connection_tests(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _create_member_headers(test_project_id, role="user")

    async def forbidden_vision_test(**_kwargs):
        raise AssertionError("普通成员读取 capability 不应触发 Vision AI 连接测试")

    def forbidden_svn_test(*_args, **_kwargs):
        raise AssertionError("普通成员读取 capability 不应触发 SVN 连接测试")

    monkeypatch.setattr(
        "backend.app.admin.router.test_provider_vision_connection",
        forbidden_vision_test,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.app.admin.router.list_svn_directory",
        forbidden_svn_test,
        raising=False,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    ) as client:
        capability_response = await client.get(CAPABILITY_PATH)
        admin_test_response = await client.post(
            f"/api/v1/admin/projects/{test_project_id}/vision-ai-config/test"
        )

    assert capability_response.status_code == 200
    assert admin_test_response.status_code == 403


@pytest.mark.anyio
@pytest.mark.parametrize(
    "configured,run_impl,expected_configured,expected_available,expected_message,forbidden_text",
    [
        ("", None, False, False, "未配置 LibreOffice/soffice", ""),
        (
            "C:/Sensitive/LibreOffice/program/soffice.exe",
            None,
            True,
            False,
            "无法找到可执行文件",
            "Sensitive",
        ),
        (
            "soffice",
            "timeout",
            True,
            False,
            "检测超时",
            "--version",
        ),
        (
            "soffice",
            "failed",
            True,
            False,
            "检测失败",
            "C:/secret",
        ),
        (
            "soffice",
            "success",
            True,
            True,
            "LibreOffice/soffice 可用",
            "--version",
        ),
    ],
)
async def test_soffice_detection_statuses_are_sanitized(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    configured: str,
    run_impl: str | None,
    expected_configured: bool,
    expected_available: bool,
    expected_message: str,
    forbidden_text: str,
) -> None:
    monkeypatch.setattr(
        source_evidence_capabilities,
        "settings",
        SimpleNamespace(
            source_evidence_soffice_executable=configured,
            source_evidence_xls_convert_timeout_seconds=2,
        ),
    )
    monkeypatch.setattr(
        source_evidence_capabilities.shutil,
        "which",
        lambda name: name if name == "soffice" else None,
    )

    def fake_run(*args, **kwargs):
        if run_impl == "timeout":
            raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 1))
        if run_impl == "failed":
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=1,
                stdout="",
                stderr="failed at C:/secret/runtime/source.xls using --version",
            )
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="LibreOffice 7.6.0\n",
            stderr="",
        )

    if run_impl is not None:
        monkeypatch.setattr(source_evidence_capabilities.subprocess, "run", fake_run)

    response = await auth_client.get(CAPABILITY_PATH)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["soffice_configured"] is expected_configured
    assert data["soffice_available"] is expected_available
    assert expected_message in response.text
    assert "C:/Sensitive/LibreOffice/program/soffice.exe" not in response.text
    if forbidden_text:
        assert forbidden_text not in response.text
