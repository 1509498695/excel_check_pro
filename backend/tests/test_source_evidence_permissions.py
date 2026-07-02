"""Source Evidence Run API 权限测试。"""

from __future__ import annotations

import datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.auth.service import create_access_token, hash_password
from backend.app.database import async_session_factory
from backend.app.models import (
    Project,
    SourceEvidenceAuthorizationRecord,
    SourceEvidenceResourceRecord,
    SourceEvidenceRunRecord,
    User,
    UserProjectRole,
)
from backend.app.test_cases.source_evidence_authorization import hash_source_token
from backend.app.test_cases import source_evidence_storage
from backend.run import app


@pytest.fixture(autouse=True)
def _source_evidence_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        source_evidence_storage,
        "settings",
        SimpleNamespace(source_evidence_dir=tmp_path / "source-evidence"),
    )


async def _create_non_member_headers() -> dict[str, str]:
    async with async_session_factory() as session:
        owned_project = Project(name=f"se-owned-{uuid4().hex[:8]}", description="")
        foreign_project = Project(name=f"se-foreign-{uuid4().hex[:8]}", description="")
        session.add_all([owned_project, foreign_project])
        await session.flush()

        user = User(
            username=f"se-user-{uuid4().hex[:8]}",
            hashed_password=hash_password("testpass"),
            is_super_admin=False,
            primary_project_id=owned_project.id,
        )
        session.add(user)
        await session.flush()
        session.add(
            UserProjectRole(
                user_id=user.id,
                project_id=owned_project.id,
                role="user",
            )
        )
        await session.commit()

        token = create_access_token(user.id, project_id=foreign_project.id)

    return {"Authorization": f"Bearer {token}"}


async def _create_project_member_headers(*, role: str = "user") -> tuple[dict[str, str], int]:
    async with async_session_factory() as session:
        project = Project(name=f"se-member-{uuid4().hex[:8]}", description="")
        session.add(project)
        await session.flush()

        user = User(
            username=f"se-member-user-{uuid4().hex[:8]}",
            hashed_password=hash_password("testpass"),
            is_super_admin=False,
            primary_project_id=project.id,
        )
        session.add(user)
        await session.flush()
        session.add(
            UserProjectRole(
                user_id=user.id,
                project_id=project.id,
                role=role,
            )
        )
        await session.commit()

        token = create_access_token(user.id, project_id=project.id)

    return {"Authorization": f"Bearer {token}"}, project.id


@pytest.mark.anyio
async def test_source_evidence_api_requires_login(test_db) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/test-cases/source-evidence-runs",
            json={"source_type": "feishu", "source_url": "https://demo.feishu.cn/docx/doc1"},
        )

    assert response.status_code == 401

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        candidates_response = await client.get(
            "/api/v1/test-cases/source-evidence-runs/1/visual-candidates"
        )
        selection_response = await client.post(
            "/api/v1/test-cases/source-evidence-runs/1/visual-selections",
            json={"selected_refs": []},
        )
        observation_response = await client.post(
            "/api/v1/test-cases/source-evidence-runs/1/observations",
            json={},
        )
        adoption_response = await client.post(
            "/api/v1/test-cases/source-evidence-runs/1/adopted-visual-evidence",
            json={"observation_ids": []},
        )
        audit_response = await client.get(
            "/api/v1/test-cases/source-evidence-cleanup-audits"
        )

    assert candidates_response.status_code == 401
    assert selection_response.status_code == 401
    assert observation_response.status_code == 401
    assert adoption_response.status_code == 401
    assert audit_response.status_code == 401


@pytest.mark.anyio
async def test_source_evidence_api_rejects_token_project_not_owned(test_db) -> None:
    headers = await _create_non_member_headers()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    ) as client:
        response = await client.post(
            "/api/v1/test-cases/source-evidence-runs",
            json={"source_type": "feishu", "source_url": "https://demo.feishu.cn/docx/doc1"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "您不属于当前项目"


@pytest.mark.anyio
async def test_cleanup_audit_list_requires_project_admin(test_db) -> None:
    headers, _project_id = await _create_project_member_headers(role="user")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    ) as client:
        response = await client.get("/api/v1/test-cases/source-evidence-cleanup-audits")

    assert response.status_code == 403
    assert response.json()["detail"] == "需要项目管理员权限"


@pytest.mark.anyio
async def test_cleanup_audit_list_is_project_scoped_for_admin(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    async with async_session_factory() as session:
        own_run = SourceEvidenceRunRecord(
            project_id=test_project_id,
            source_type="feishu",
            source_identifier="sha256:own",
            source_title="本项目清理记录",
            status="cleaned",
            minimal_audit_json=(
                '{"run_id": 1, "project_id": %d, "source_identifier": "sha256:own", '
                '"resources": [{"filename": "own.png"}]}'
            )
            % test_project_id,
            expires_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1),
            cleaned_at=datetime.datetime.now(datetime.UTC),
        )
        foreign_project = Project(name=f"se-audit-foreign-{uuid4().hex[:8]}", description="")
        session.add_all([own_run, foreign_project])
        await session.flush()
        foreign_run = SourceEvidenceRunRecord(
            project_id=foreign_project.id,
            source_type="feishu",
            source_identifier="sha256:foreign",
            source_title="跨项目清理记录",
            status="cleaned",
            minimal_audit_json=(
                '{"run_id": 2, "project_id": %d, "source_identifier": "sha256:foreign", '
                '"resources": [{"filename": "foreign.png"}]}'
            )
            % foreign_project.id,
            expires_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1),
            cleaned_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(foreign_run)
        await session.commit()

    response = await auth_client.get(
        "/api/v1/test-cases/source-evidence-cleanup-audits?limit=10&offset=0"
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["source_identifier"] == "sha256:own"
    payload_text = str(data)
    assert "foreign" not in payload_text
    assert "own.png" in payload_text


@pytest.mark.anyio
async def test_cross_project_run_and_resources_are_not_visible(
    auth_client: AsyncClient,
) -> None:
    async with async_session_factory() as session:
        foreign_project = Project(name=f"se-cross-{uuid4().hex[:8]}", description="")
        session.add(foreign_project)
        await session.flush()
        run = SourceEvidenceRunRecord(
            project_id=foreign_project.id,
            source_type="feishu",
            source_identifier="doccnforeign",
            source_title="跨项目证据",
            status="ready",
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(run)
        await session.flush()
        session.add(
            SourceEvidenceResourceRecord(
                run_id=run.id,
                project_id=foreign_project.id,
                ref="img_001",
                resource_type="image",
                position="docx:block:img",
                filename="ui.png",
                status="unobserved",
                download_status="download_failed",
            )
        )
        await session.commit()
        run_id = run.id

    run_response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}"
    )
    resources_response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/resources"
    )
    candidates_response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/visual-candidates"
    )
    selection_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/visual-selections",
        json={"selected_refs": []},
    )
    observations_response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/observations"
    )
    observe_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/observations",
        json={},
    )
    adoption_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/adopted-visual-evidence",
        json={"observation_ids": [1]},
    )
    revoke_response = await auth_client.delete(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/adopted-visual-evidence/1"
    )

    assert run_response.status_code == 404
    assert resources_response.status_code == 404
    assert candidates_response.status_code == 404
    assert selection_response.status_code == 404
    assert observations_response.status_code == 404
    assert observe_response.status_code == 404
    assert adoption_response.status_code == 404
    assert revoke_response.status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize(
    "forbidden_key",
    ["knowledge_context", "qa_knowledge_context", "project_qa_knowledge"],
)
async def test_source_evidence_create_rejects_public_knowledge_context(
    auth_client: AsyncClient,
    forbidden_key: str,
) -> None:
    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs",
        json={
            "source_type": "feishu",
            "source_url": "https://demo.feishu.cn/docx/doc1",
            forbidden_key: {"raw": "不要接入"},
        },
    )

    assert response.status_code == 400
    assert "V1 不接收用户传入的知识库上下文" in response.json()["detail"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "forbidden_key",
    ["knowledge_context", "qa_knowledge_context", "project_qa_knowledge"],
)
async def test_source_evidence_visual_selection_rejects_public_knowledge_context(
    auth_client: AsyncClient,
    test_project_id: int,
    forbidden_key: str,
) -> None:
    async with async_session_factory() as session:
        run = SourceEvidenceRunRecord(
            project_id=test_project_id,
            source_type="feishu",
            source_identifier="doccnvisual",
            source_title="视觉选择",
            status="ready",
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(run)
        await session.commit()
        run_id = run.id

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/visual-selections",
        json={
            "selected_refs": [],
            forbidden_key: {"raw": "不要接入"},
        },
    )

    assert response.status_code == 400
    assert "V1 不接收用户传入的知识库上下文" in response.json()["detail"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path_suffix,payload",
    [
        ("observations", {}),
        ("adopted-visual-evidence", {"observation_ids": []}),
    ],
)
@pytest.mark.parametrize(
    "forbidden_key",
    ["knowledge_context", "qa_knowledge_context", "project_qa_knowledge"],
)
async def test_source_evidence_observation_posts_reject_public_knowledge_context(
    auth_client: AsyncClient,
    test_project_id: int,
    path_suffix: str,
    payload: dict[str, object],
    forbidden_key: str,
) -> None:
    async with async_session_factory() as session:
        run = SourceEvidenceRunRecord(
            project_id=test_project_id,
            source_type="feishu",
            source_identifier="doccnvisual",
            source_title="视觉观察",
            status="ready",
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(run)
        await session.commit()
        run_id = run.id

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/{path_suffix}",
        json={**payload, forbidden_key: {"raw": "不要接入"}},
    )

    assert response.status_code == 400
    assert "V1 不接收用户传入的知识库上下文" in response.json()["detail"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "forbidden_key",
    ["knowledge_context", "qa_knowledge_context", "project_qa_knowledge"],
)
async def test_source_evidence_authorization_request_rejects_public_knowledge_context(
    auth_client: AsyncClient,
    forbidden_key: str,
) -> None:
    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs/1/authorization-request",
        json={forbidden_key: {"raw": "不要接入"}},
    )

    assert response.status_code == 400
    assert "V1 不接收用户传入的知识库上下文" in response.json()["detail"]


@pytest.mark.anyio
async def test_source_evidence_authorization_request_cross_project_run_returns_404(
    auth_client: AsyncClient,
) -> None:
    async with async_session_factory() as session:
        foreign_project = Project(name=f"se-authz-cross-{uuid4().hex[:8]}", description="")
        session.add(foreign_project)
        await session.flush()
        run = SourceEvidenceRunRecord(
            project_id=foreign_project.id,
            source_type="feishu",
            source_url="https://demo.feishu.cn/docx/doccnforeign",
            source_identifier="doccnforeign",
            source_title="跨项目证据",
            status="pending_permission",
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(run)
        await session.commit()
        run_id = run.id

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/authorization-request",
        json={},
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_source_evidence_authorization_audit_and_invalidate_require_admin(
    test_db,
) -> None:
    member_headers, project_id = await _create_project_member_headers(role="user")
    async with async_session_factory() as session:
        record = SourceEvidenceAuthorizationRecord(
            project_id=project_id,
            app_id="cli_source_evidence",
            doc_type="docx",
            permission="edit",
            source_token_hash=hash_source_token("doccnsecret"),
            status="authorized",
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=90),
        )
        session.add(record)
        await session.commit()
        authorization_id = record.id

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=member_headers,
    ) as client:
        list_response = await client.get(
            "/api/v1/test-cases/source-evidence-authorizations"
        )
        invalidate_response = await client.post(
            f"/api/v1/test-cases/source-evidence-authorizations/{authorization_id}/invalidate"
        )

    assert list_response.status_code == 403
    assert invalidate_response.status_code == 403


@pytest.mark.anyio
async def test_source_evidence_authorization_admin_can_audit_and_invalidate(
    test_db,
) -> None:
    admin_headers, project_id = await _create_project_member_headers(role="admin")
    async with async_session_factory() as session:
        record = SourceEvidenceAuthorizationRecord(
            project_id=project_id,
            app_id="cli_source_evidence",
            doc_type="docx",
            permission="edit",
            source_token_hash=hash_source_token("doccnsecret"),
            source_token_alias_hashes_json="[]",
            status="authorized",
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=90),
        )
        session.add(record)
        await session.commit()
        authorization_id = record.id

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=admin_headers,
    ) as client:
        list_response = await client.get(
            "/api/v1/test-cases/source-evidence-authorizations?limit=50&offset=0"
        )
        invalidate_response = await client.post(
            f"/api/v1/test-cases/source-evidence-authorizations/{authorization_id}/invalidate"
        )

    assert list_response.status_code == 200
    list_data = list_response.json()["data"]
    assert list_data["total"] == 1
    payload_text = str(list_data)
    assert "doccnsecret" not in payload_text
    assert list_data["items"][0]["source_fingerprint"].startswith("sha256:")

    assert invalidate_response.status_code == 200
    assert invalidate_response.json()["data"]["status"] == "invalidated"
