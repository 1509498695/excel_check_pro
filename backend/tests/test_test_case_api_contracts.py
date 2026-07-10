"""用例生成 V1 后端骨架契约测试。"""

from __future__ import annotations

import datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
import sqlalchemy as sa

from backend.app.auth.service import create_access_token, decode_access_token, hash_password
from backend.app.database import async_session_factory
from backend.app.models import Project, SourceEvidenceRunRecord, User, UserProjectRole
from backend.run import app


TEST_CASE_API_PATHS = {
    "/api/v1/test-cases/planning-snapshot",
    "/api/v1/test-cases/planning-snapshot/brief",
    "/api/v1/test-cases/generate",
    "/api/v1/test-cases/export",
    "/api/v1/test-cases/generation-runs",
    "/api/v1/test-cases/generation-runs/{run_id}",
    "/api/v1/test-cases/generation-runs/{run_id}/cancel",
    "/api/v1/test-cases/generation-runs/{run_id}/retry-failed-chunks",
    "/api/v1/test-cases/generation-runs/{run_id}/atoms",
    "/api/v1/test-cases/generation-runs/{run_id}/cases",
    "/api/v1/test-cases/generation-runs/{run_id}/export",
    "/api/v1/test-cases/source-evidence-cleanup-audits",
    "/api/v1/test-cases/source-evidence-authorizations",
    "/api/v1/test-cases/source-evidence-authorizations/oauth/callback",
    "/api/v1/test-cases/source-evidence-authorizations/{authorization_id}/invalidate",
    "/api/v1/test-cases/source-evidence-runs",
    "/api/v1/test-cases/source-evidence-runs/upload",
    "/api/v1/test-cases/source-evidence-runs/{run_id}",
    "/api/v1/test-cases/source-evidence-runs/{run_id}/authorization-request",
    "/api/v1/test-cases/source-evidence-runs/{run_id}/resources",
    "/api/v1/test-cases/source-evidence-runs/{run_id}/visual-candidates",
    "/api/v1/test-cases/source-evidence-runs/{run_id}/visual-selections",
    "/api/v1/test-cases/source-evidence-runs/{run_id}/observations",
    "/api/v1/test-cases/source-evidence-runs/{run_id}/adopted-visual-evidence",
    "/api/v1/test-cases/source-evidence-runs/{run_id}/adopted-visual-evidence/{evidence_id}",
    "/api/v1/test-cases/source-evidence-runs/{run_id}/snapshot",
    "/api/v1/test-cases/source-evidence-runs/{run_id}/retry",
}


def _planning_snapshot_request() -> dict[str, object]:
    return {
        "source_type": "uploaded_excel",
        "source": {
            "id": "plan-source",
            "type": "local_excel",
            "pathOrUrl": "D:/plan/source.xlsx",
        },
        "sheet_name": "策划案",
    }


def _planning_snapshot_payload() -> dict[str, object]:
    return {
        "source_summary": "上传 Excel：source.xlsx",
        "sheet_name": "策划案",
        "rows": [
            {
                "row_index": 1,
                "cells": [
                    {
                        "row_index": 1,
                        "column_index": 1,
                        "column_name": "模块",
                        "value": "活动入口",
                    }
                ],
            }
        ],
        "columns": ["模块"],
        "non_empty_cell_count": 1,
        "truncated": False,
        "warnings": [],
    }


def _generation_request() -> dict[str, object]:
    return {
        "planning_snapshot": _planning_snapshot_payload(),
        "reference_ids": [],
        "primary_reference_id": None,
    }


def _brief_request() -> dict[str, object]:
    return {
        "planning_snapshot": _planning_snapshot_payload(),
    }


def _export_request() -> dict[str, object]:
    return {
        "blueprint": {
            "modules": [],
            "flows": [],
            "coverage_dimensions": [],
            "risks": [],
            "open_questions": [],
            "warnings": [],
        },
        "cases": [
            {
                "case_id": "TC-001",
                "module": "活动入口",
                "title": "活动入口按配置开放",
                "steps": "进入活动页",
                "expected_results": "入口展示正常",
                "priority": "P1",
            }
        ],
        "warnings": [],
        "stats": {
            "total": 1,
            "priority_counts": {"P1": 1},
            "module_counts": {"活动入口": 1},
            "case_type_counts": {},
            "warning_count": 0,
        },
        "export_columns": ["case_id", "module", "title", "steps", "expected_results"],
    }


def _source_evidence_create_request() -> dict[str, object]:
    return {
        "source_type": "feishu",
        "source_url": "https://demo.feishu.cn/docx/doccnabc123",
    }


def _generation_run_create_request(source_evidence_run_id: int) -> dict[str, object]:
    return {
        "source_evidence_run_id": source_evidence_run_id,
        "planning_sheet_name": "策划案",
        "reference_ids": [],
        "primary_reference_id": None,
        "primary_reference_sheet_name": None,
        "strict_mode": True,
    }


def _auth_user_id(headers: dict[str, str]) -> int:
    token = headers["Authorization"].removeprefix("Bearer ")
    return int(decode_access_token(token)["sub"])


async def _seed_source_evidence_run(
    project_id: int,
    *,
    created_by: int | None = None,
    status: str = "ready",
    expires_delta: datetime.timedelta = datetime.timedelta(days=1),
) -> int:
    async with async_session_factory() as session:
        run = SourceEvidenceRunRecord(
            project_id=project_id,
            source_type="feishu",
            source_url="https://demo.feishu.cn/docx/doccnabc123",
            source_identifier="doccnabc123",
            source_title="V3 策划案",
            status=status,
            created_by=created_by,
            expires_at=datetime.datetime.now(datetime.UTC) + expires_delta,
        )
        session.add(run)
        await session.commit()
        return run.id


async def _seed_generation_run(
    project_id: int,
    *,
    source_evidence_run_id: int | None = None,
    created_by: int | None = None,
    status: str = "queued",
    expires_delta: datetime.timedelta = datetime.timedelta(days=1),
) -> int:
    if source_evidence_run_id is None:
        source_evidence_run_id = await _seed_source_evidence_run(
            project_id,
            created_by=created_by,
        )
    async with async_session_factory() as session:
        await session.execute(
            sa.text(
                """
                INSERT INTO test_case_generation_runs (
                    project_id,
                    source_evidence_run_id,
                    created_by,
                    status,
                    planning_sheet_name,
                    reference_ids_json,
                    primary_reference_id,
                    primary_reference_sheet_name,
                    strict_mode,
                    total_chunks,
                    completed_chunks,
                    failed_chunks,
                    atom_count,
                    case_count,
                    warning_count,
                    error_summary,
                    warnings_json,
                    summary_json,
                    expires_at,
                    created_at,
                    updated_at
                ) VALUES (
                    :project_id,
                    :source_evidence_run_id,
                    :created_by,
                    :status,
                    '策划案',
                    '[]',
                    NULL,
                    NULL,
                    1,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    '',
                    '[]',
                    '{}',
                    :expires_at,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "project_id": project_id,
                "source_evidence_run_id": source_evidence_run_id,
                "created_by": created_by,
                "status": status,
                "expires_at": datetime.datetime.now(datetime.UTC) + expires_delta,
            },
        )
        result = await session.execute(sa.text("SELECT last_insert_rowid()"))
        await session.commit()
        return int(result.scalar_one())


async def _create_non_member_headers() -> dict[str, str]:
    async with async_session_factory() as session:
        owned_project = Project(name=f"tc-owned-{uuid4().hex[:8]}", description="")
        foreign_project = Project(name=f"tc-foreign-{uuid4().hex[:8]}", description="")
        session.add_all([owned_project, foreign_project])
        await session.flush()

        user = User(
            username=f"tc-user-{uuid4().hex[:8]}",
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


@pytest.mark.anyio
async def test_test_case_api_routes_are_registered(test_db) -> None:
    """用例生成 V1 路由应挂载到 /api/v1/test-cases。"""
    registered_paths = {getattr(route, "path", "") for route in app.routes}

    assert TEST_CASE_API_PATHS.issubset(registered_paths)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/test-cases/planning-snapshot", _planning_snapshot_request()),
        ("/api/v1/test-cases/planning-snapshot/brief", _brief_request()),
        ("/api/v1/test-cases/generate", _generation_request()),
        ("/api/v1/test-cases/export", _export_request()),
        ("/api/v1/test-cases/generation-runs", _generation_run_create_request(1)),
        ("/api/v1/test-cases/source-evidence-runs", _source_evidence_create_request()),
    ],
)
async def test_test_case_api_requires_login(
    test_db,
    path: str,
    payload: dict[str, object],
) -> None:
    """用例生成接口必须先登录。"""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(path, json=payload)

    assert response.status_code == 401


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/test-cases/planning-snapshot", _planning_snapshot_request()),
        ("/api/v1/test-cases/planning-snapshot/brief", _brief_request()),
        ("/api/v1/test-cases/source-evidence-runs", _source_evidence_create_request()),
    ],
)
async def test_test_case_api_rejects_token_project_not_owned(
    test_db,
    path: str,
    payload: dict[str, object],
) -> None:
    """用例生成接口必须使用严格项目成员校验。"""
    headers = await _create_non_member_headers()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    ) as client:
        response = await client.post(path, json=payload)

    assert response.status_code == 403
    assert response.json()["detail"] == "您不属于当前项目"


@pytest.mark.anyio
async def test_legacy_generation_endpoint_returns_410(
    auth_client: AsyncClient,
) -> None:
    """旧同步生成入口不再作为 V3 全量生成主路径。"""
    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(),
    )

    assert response.status_code == 410
    assert response.json()["detail"] == "同步用例生成入口已停用，请使用 V3 Generation Run。"


@pytest.mark.anyio
async def test_create_generation_run_returns_queued_with_project_and_user(
    auth_client: AsyncClient,
    auth_headers: dict[str, str],
    test_project_id: int,
) -> None:
    """创建 Generation Run 只登记任务骨架，不同步生成用例。"""
    user_id = _auth_user_id(auth_headers)
    source_run_id = await _seed_source_evidence_run(test_project_id, created_by=user_id)

    response = await auth_client.post(
        "/api/v1/test-cases/generation-runs",
        json=_generation_run_create_request(source_run_id),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "queued"
    assert data["project_id"] == test_project_id
    assert data["created_by"] == user_id
    assert data["source_evidence_run_id"] == source_run_id
    assert data["planning_sheet_name"] == "策划案"
    assert data["strict_mode"] is True
    assert data["reference_ids"] == []
    assert data["case_count"] == 0
    assert data["atom_count"] == 0


@pytest.mark.anyio
async def test_non_project_member_cannot_read_or_cancel_generation_run(
    auth_headers: dict[str, str],
    test_project_id: int,
) -> None:
    """Generation Run 读取和取消必须先过严格项目成员校验。"""
    user_id = _auth_user_id(auth_headers)
    run_id = await _seed_generation_run(test_project_id, created_by=user_id)
    headers = await _create_non_member_headers()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    ) as client:
        read_response = await client.get(f"/api/v1/test-cases/generation-runs/{run_id}")
        cancel_response = await client.post(
            f"/api/v1/test-cases/generation-runs/{run_id}/cancel"
        )

    assert read_response.status_code == 403
    assert read_response.json()["detail"] == "您不属于当前项目"
    assert cancel_response.status_code == 403
    assert cancel_response.json()["detail"] == "您不属于当前项目"


@pytest.mark.anyio
async def test_cross_project_generation_run_is_not_visible(
    auth_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """跨项目 run 必须隔离，不能按裸 run_id 泄露。"""
    user_id = _auth_user_id(auth_headers)
    async with async_session_factory() as session:
        foreign_project = Project(name=f"tc-v3-foreign-{uuid4().hex[:8]}", description="")
        session.add(foreign_project)
        await session.commit()
        foreign_project_id = foreign_project.id
    run_id = await _seed_generation_run(foreign_project_id, created_by=user_id)

    response = await auth_client.get(f"/api/v1/test-cases/generation-runs/{run_id}")

    assert response.status_code in {403, 404}


@pytest.mark.anyio
async def test_cancel_generation_run_moves_active_status_to_cancelled(
    auth_client: AsyncClient,
    auth_headers: dict[str, str],
    test_project_id: int,
) -> None:
    """可取消状态应转为 cancelled 并记录取消人。"""
    user_id = _auth_user_id(auth_headers)
    run_id = await _seed_generation_run(
        test_project_id,
        created_by=user_id,
        status="reading",
    )

    response = await auth_client.post(f"/api/v1/test-cases/generation-runs/{run_id}/cancel")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "cancelled"
    assert data["cancelled_by"] == user_id
    assert data["cancelled_at"] is not None


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["completed", "failed", "expired"])
async def test_terminal_generation_run_cannot_be_cancelled(
    auth_client: AsyncClient,
    auth_headers: dict[str, str],
    test_project_id: int,
    status: str,
) -> None:
    """终态 run 不允许取消。"""
    user_id = _auth_user_id(auth_headers)
    run_id = await _seed_generation_run(
        test_project_id,
        created_by=user_id,
        status=status,
    )

    response = await auth_client.post(f"/api/v1/test-cases/generation-runs/{run_id}/cancel")

    assert response.status_code == 409
    assert response.json()["detail"] == "当前 Generation Run 状态不允许取消。"


@pytest.mark.anyio
async def test_generation_run_get_marks_expired_by_ttl(
    auth_client: AsyncClient,
    auth_headers: dict[str, str],
    test_project_id: int,
) -> None:
    """TTL 到期的非终态 run 应在读取时暴露为 expired。"""
    user_id = _auth_user_id(auth_headers)
    run_id = await _seed_generation_run(
        test_project_id,
        created_by=user_id,
        status="queued",
        expires_delta=datetime.timedelta(days=-1),
    )

    response = await auth_client.get(f"/api/v1/test-cases/generation-runs/{run_id}")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "expired"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "suffix", "message"),
    [
        ("get", "atoms", "Generation Run 尚无需求原子结果。"),
        ("get", "cases", "Generation Run 尚无用例结果。"),
        ("post", "export", "Generation Run 尚未生成可导出的用例结果。"),
    ],
)
async def test_generation_run_result_endpoints_return_clear_errors_when_empty(
    auth_client: AsyncClient,
    auth_headers: dict[str, str],
    test_project_id: int,
    method: str,
    suffix: str,
    message: str,
) -> None:
    """无结果 run 的 atoms/cases/export 骨架必须返回明确中文错误。"""
    user_id = _auth_user_id(auth_headers)
    run_id = await _seed_generation_run(test_project_id, created_by=user_id)

    response = await getattr(auth_client, method)(
        f"/api/v1/test-cases/generation-runs/{run_id}/{suffix}"
    )

    assert response.status_code == 409
    assert response.json()["detail"] == message
