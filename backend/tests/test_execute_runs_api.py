"""异步执行任务接口测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.auth.service import create_access_token, hash_password
from backend.app.database import async_session_factory
from backend.app.models import Project, User, UserProjectRole
from backend.run import app
from backend.tests.conftest import seed_fixed_rules_config


TEST_DATA_PATH = Path(__file__).resolve().parent / "data" / "minimal_rules.xlsx"
TERMINAL_STATUSES = {"success", "failed", "cancelled"}


def _workbench_task_tree(*, rule_type: str = "not_null") -> dict[str, object]:
    return {
        "sources": [
            {
                "id": "src_test",
                "type": "local_excel",
                "path": str(TEST_DATA_PATH),
            }
        ],
        "variables": [
            {
                "tag": "[items-id]",
                "source_id": "src_test",
                "sheet": "items",
                "column": "ID",
            }
        ],
        "rules": [
            {
                "rule_type": rule_type,
                "params": {"target_tags": ["[items-id]"]},
            }
        ],
    }


async def _wait_for_terminal_status(client: AsyncClient, run_id: int) -> dict[str, object]:
    for _ in range(20):
        response = await client.get(f"/api/v1/execute-runs/{run_id}")
        assert response.status_code == 200
        payload = response.json()["data"]
        if payload["status"] in TERMINAL_STATUSES:
            return payload
        await asyncio.sleep(0.01)
    raise AssertionError("execute run did not reach a terminal status")


def _create_fixed_rules_workbook(target_path: Path) -> Path:
    with pd.ExcelWriter(target_path, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "INT_ID": [1, 2, 3],
                "DESC": ["a", "b", "c"],
            }
        ).to_excel(writer, sheet_name="items", index=False)
    return target_path


def _build_fixed_rules_config(workbook_path: Path) -> dict[str, object]:
    int_id_tag = "[items-source-items-INT_ID]"
    return {
        "version": 4,
        "configured": True,
        "sources": [
            {
                "id": "items-source",
                "type": "local_excel",
                "path": str(workbook_path),
                "pathOrUrl": str(workbook_path),
            }
        ],
        "variables": [
            {
                "tag": int_id_tag,
                "source_id": "items-source",
                "sheet": "items",
                "variable_kind": "single",
                "column": "INT_ID",
                "expected_type": "str",
            }
        ],
        "groups": [
            {"group_id": "ungrouped", "group_name": "未分组", "builtin": True},
            {"group_id": "basic-checks", "group_name": "基础校验", "builtin": False},
        ],
        "rules": [
            {
                "rule_id": "rule-int-id",
                "group_id": "basic-checks",
                "rule_name": "INT_ID 必须大于 0",
                "target_variable_tag": int_id_tag,
                "rule_type": "fixed_value_compare",
                "operator": "gt",
                "expected_value": "0",
            }
        ],
    }


async def _create_same_project_user_headers(project_id: int) -> dict[str, str]:
    async with async_session_factory() as session:
        user = User(
            username="same-project-reader",
            hashed_password=hash_password("testpass"),
            is_super_admin=False,
            primary_project_id=project_id,
        )
        session.add(user)
        await session.flush()
        session.add(
            UserProjectRole(
                user_id=user.id,
                project_id=project_id,
                role="user",
            )
        )
        await session.commit()
        token = create_access_token(user.id, project_id=project_id)
    return {"Authorization": f"Bearer {token}"}


async def _create_other_project_user_headers() -> dict[str, str]:
    async with async_session_factory() as session:
        project = Project(name="other-project", description="")
        session.add(project)
        await session.flush()
        user = User(
            username="other-project-reader",
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
                role="user",
            )
        )
        await session.commit()
        token = create_access_token(user.id, project_id=project.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_create_workbench_execute_run_and_fetch_items(
    auth_client: AsyncClient,
) -> None:
    """创建个人校验任务后应能查询状态和异常明细。"""
    response = await auth_client.post(
        "/api/v1/execute-runs",
        json={
            "scope_type": "workbench",
            "task_tree": _workbench_task_tree(),
        },
    )

    assert response.status_code == 200
    created = response.json()["data"]
    assert created["status"] in {"pending", "running", "success"}
    run_id = created["run_id"]

    status = await _wait_for_terminal_status(auth_client, run_id)
    assert status["status"] == "success"
    assert status["scope_type"] == "workbench"
    assert status["execution_time_ms"] >= 0
    assert status["total_rows_scanned"] > 0

    items_response = await auth_client.get(
        f"/api/v1/execute-runs/{run_id}/items",
        params={"page": 1, "size": 5},
    )
    assert items_response.status_code == 200
    items_payload = items_response.json()
    assert items_payload["meta"]["run_id"] == run_id
    assert items_payload["meta"]["status"] == "success"
    assert items_payload["data"]["page"] == 1
    assert items_payload["data"]["size"] == 5
    assert isinstance(items_payload["data"]["list"], list)


@pytest.mark.anyio
async def test_execute_run_records_failed_status(auth_client: AsyncClient) -> None:
    """执行异常应写入 failed 状态和错误信息。"""
    response = await auth_client.post(
        "/api/v1/execute-runs",
        json={
            "scope_type": "workbench",
            "task_tree": _workbench_task_tree(rule_type="unknown_rule_type"),
        },
    )
    assert response.status_code == 200
    run_id = response.json()["data"]["run_id"]

    status = await _wait_for_terminal_status(auth_client, run_id)
    assert status["status"] == "failed"
    assert "Unsupported rule_type" in status["error_message"]
    assert status["finished_at"] is not None


@pytest.mark.anyio
async def test_workbench_execute_run_isolated_by_user_and_project(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """个人校验任务仅创建者可读，其他项目也不可读。"""
    response = await auth_client.post(
        "/api/v1/execute-runs",
        json={
            "scope_type": "workbench",
            "task_tree": _workbench_task_tree(),
        },
    )
    assert response.status_code == 200
    run_id = response.json()["data"]["run_id"]
    await _wait_for_terminal_status(auth_client, run_id)

    same_project_headers = await _create_same_project_user_headers(test_project_id)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=same_project_headers,
    ) as client:
        same_project_response = await client.get(f"/api/v1/execute-runs/{run_id}")
    assert same_project_response.status_code == 404

    other_project_headers = await _create_other_project_user_headers()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=other_project_headers,
    ) as client:
        other_project_response = await client.get(f"/api/v1/execute-runs/{run_id}")
    assert other_project_response.status_code == 404


@pytest.mark.anyio
async def test_fixed_rules_execute_run_success(
    auth_client: AsyncClient,
    test_project_id: int,
    tmp_path: Path,
) -> None:
    """固定规则也可以通过任务接口执行，并按项目读取结果。"""
    workbook_path = _create_fixed_rules_workbook(tmp_path / "fixed-rules.xlsx")
    await seed_fixed_rules_config(_build_fixed_rules_config(workbook_path), test_project_id)

    response = await auth_client.post(
        "/api/v1/execute-runs",
        json={
            "scope_type": "fixed_rules",
            "selected_rule_ids": ["rule-int-id"],
        },
    )
    assert response.status_code == 200
    run_id = response.json()["data"]["run_id"]

    status = await _wait_for_terminal_status(auth_client, run_id)
    assert status["status"] == "success"
    assert status["scope_type"] == "fixed_rules"
    assert status["total_rows_scanned"] == 3


@pytest.mark.anyio
async def test_execute_run_requires_login() -> None:
    """任务接口必须登录。"""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/execute-runs",
            json={
                "scope_type": "workbench",
                "task_tree": _workbench_task_tree(),
            },
        )
    assert response.status_code == 401
