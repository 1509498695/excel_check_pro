"""用例生成 V1 后端骨架契约测试。"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.auth.service import create_access_token, hash_password
from backend.app.database import async_session_factory
from backend.app.models import Project, User, UserProjectRole
from backend.run import app


TEST_CASE_API_PATHS = {
    "/api/v1/test-cases/planning-snapshot",
    "/api/v1/test-cases/planning-snapshot/brief",
    "/api/v1/test-cases/generate",
    "/api/v1/test-cases/export",
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
@pytest.mark.parametrize(
    "forbidden_key",
    ["knowledge_context", "qa_knowledge_context", "project_qa_knowledge"],
)
async def test_generation_request_rejects_public_knowledge_context(
    auth_client: AsyncClient,
    forbidden_key: str,
) -> None:
    """V1 公共生成请求不得注入用户维护知识内容。"""
    payload = {**_generation_request(), forbidden_key: {"raw": "不要接入"}}

    response = await auth_client.post("/api/v1/test-cases/generate", json=payload)

    assert response.status_code == 400
    assert "V1 不接收用户传入的知识库上下文" in response.json()["detail"]
