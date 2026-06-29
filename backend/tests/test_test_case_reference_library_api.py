"""用例生成 V1 参考案例库 API 测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from backend.app.auth.service import create_access_token, hash_password
from backend.app.database import async_session_factory
from backend.app.models import (
    ExecutionRunRecord,
    Project,
    TestCaseReferenceCategoryRecord as ReferenceCategoryRecord,
    TestCaseReferenceFileRecord as ReferenceFileRecord,
    User,
    UserProjectRole,
)
from backend.app.test_cases import reference_library
from backend.run import app


def _patch_reference_storage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[Path, Path]:
    runtime_dir = tmp_path / "runtime"
    upload_dir = tmp_path / "runtime-uploads"
    monkeypatch.setattr(
        reference_library,
        "settings",
        SimpleNamespace(
            runtime_dir=runtime_dir,
            runtime_upload_dir=upload_dir,
        ),
    )
    return runtime_dir, upload_dir


def _write_reference_workbook(path: Path, *, sheet_name: str = "测试用例") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe = pd.DataFrame(
        {
            "用例编号": ["TC-001", "TC-002"],
            "功能模块": ["登录", "登录"],
            "用例标题": ["账号密码登录成功", "密码错误提示"],
            "操作步骤": ["输入正确账号密码", "输入错误密码"],
            "预期结果": ["进入首页", "提示密码错误"],
            "优先级": ["P1", "P2"],
        }
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        dataframe.to_excel(writer, sheet_name=sheet_name, index=False)
    return path


def _write_invalid_workbook(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe = pd.DataFrame({"姓名": ["张三"], "年龄": [18]})
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        dataframe.to_excel(writer, sheet_name="原始数据", index=False)
    return path


async def _create_role_headers(
    project_id: int,
    *,
    role: str = "user",
    super_admin: bool = False,
) -> dict[str, str]:
    async with async_session_factory() as session:
        user = User(
            username=f"tc-ref-{role}-{uuid4().hex[:8]}",
            hashed_password=hash_password("testpass"),
            is_super_admin=super_admin,
            primary_project_id=project_id,
        )
        session.add(user)
        await session.flush()
        session.add(
            UserProjectRole(
                user_id=user.id,
                project_id=project_id,
                role=role,
            )
        )
        await session.commit()
        token = create_access_token(user.id, project_id=project_id)

    return {"Authorization": f"Bearer {token}"}


async def _create_foreign_member_headers() -> dict[str, str]:
    async with async_session_factory() as session:
        owned_project = Project(name=f"tc-ref-owned-{uuid4().hex[:8]}", description="")
        foreign_project = Project(name=f"tc-ref-foreign-{uuid4().hex[:8]}", description="")
        session.add_all([owned_project, foreign_project])
        await session.flush()
        user = User(
            username=f"tc-ref-foreign-user-{uuid4().hex[:8]}",
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


async def _post_category(client: AsyncClient, name: str = "冒烟") -> dict:
    response = await client.post(
        "/api/v1/test-cases/reference-categories",
        json={"name": name},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _upload_reference(
    client: AsyncClient,
    path: Path,
    *,
    category_id: int | None = None,
    filename: str | None = None,
) -> tuple[int, dict]:
    with path.open("rb") as file_obj:
        response = await client.post(
            "/api/v1/test-cases/references",
            data={} if category_id is None else {"category_id": str(category_id)},
            files={
                "file": (
                    filename or path.name,
                    file_obj,
                    "application/octet-stream",
                )
            },
        )
    return response.status_code, response.json()


async def _get_reference_record(reference_id: int) -> ReferenceFileRecord:
    async with async_session_factory() as session:
        record = await session.get(ReferenceFileRecord, reference_id)
        assert record is not None
        return record


@pytest.mark.anyio
async def test_member_can_create_list_and_upload_reference(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_dir, upload_dir = _patch_reference_storage(monkeypatch, tmp_path)
    category = await _post_category(auth_client, "  冒烟  ")
    workbook_path = _write_reference_workbook(tmp_path / "login.xlsx")

    status_code, body = await _upload_reference(
        auth_client,
        workbook_path,
        category_id=category["id"],
    )

    assert status_code == 200
    uploaded = body["data"]
    assert uploaded["original_filename"] == "login.xlsx"
    assert uploaded["category_id"] == category["id"]
    assert uploaded["profile"]["default_sheet_name"] == "测试用例"
    assert uploaded["profile"]["reference_case_count"] == 2

    categories_response = await auth_client.get("/api/v1/test-cases/reference-categories")
    references_response = await auth_client.get("/api/v1/test-cases/references")

    assert categories_response.status_code == 200
    assert categories_response.json()["data"]["items"][0]["name"] == "冒烟"
    assert references_response.status_code == 200
    assert references_response.json()["data"]["items"][0]["id"] == uploaded["id"]

    record = await _get_reference_record(uploaded["id"])
    stored_path = Path(record.storage_path)
    assert runtime_dir / "test-case-references" in stored_path.parents
    assert upload_dir not in stored_path.parents


@pytest.mark.anyio
async def test_reference_api_uses_strict_project_membership(test_db) -> None:
    headers = await _create_foreign_member_headers()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    ) as client:
        response = await client.get("/api/v1/test-cases/references")

    assert response.status_code == 403
    assert response.json()["detail"] == "您不属于当前项目"


@pytest.mark.anyio
async def test_member_cannot_run_reference_admin_actions(
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_reference_storage(monkeypatch, tmp_path)
    member_headers = await _create_role_headers(test_project_id, role="user")
    admin_headers = await _create_role_headers(test_project_id, role="admin")
    workbook_path = _write_reference_workbook(tmp_path / "member-admin.xlsx")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=admin_headers,
    ) as admin_client:
        category = await _post_category(admin_client, "权限分类")
        status_code, body = await _upload_reference(
            admin_client,
            workbook_path,
            category_id=category["id"],
        )
        assert status_code == 200
        reference_id = body["data"]["id"]

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=member_headers,
    ) as member_client:
        rename_response = await member_client.patch(
            f"/api/v1/test-cases/reference-categories/{category['id']}",
            json={"name": "新名称"},
        )
        delete_category_response = await member_client.delete(
            f"/api/v1/test-cases/reference-categories/{category['id']}"
        )
        recommend_response = await member_client.post(
            f"/api/v1/test-cases/references/{reference_id}/recommended-primary"
        )
        delete_reference_response = await member_client.delete(
            f"/api/v1/test-cases/references/{reference_id}"
        )

    assert rename_response.status_code == 403
    assert delete_category_response.status_code == 403
    assert recommend_response.status_code == 403
    assert delete_reference_response.status_code == 403


@pytest.mark.anyio
async def test_duplicate_active_filename_in_same_category_is_rejected(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_reference_storage(monkeypatch, tmp_path)
    category = await _post_category(auth_client, "回归")
    another_category = await _post_category(auth_client, "冒烟")
    workbook_path = _write_reference_workbook(tmp_path / "same-name.xlsx")

    first_status, _ = await _upload_reference(
        auth_client,
        workbook_path,
        category_id=category["id"],
    )
    duplicate_status, duplicate_body = await _upload_reference(
        auth_client,
        workbook_path,
        category_id=category["id"],
    )
    other_category_status, _ = await _upload_reference(
        auth_client,
        workbook_path,
        category_id=another_category["id"],
    )

    assert first_status == 200
    assert duplicate_status == 400
    assert "同一分类下已存在同名参考案例" in duplicate_body["detail"]
    assert other_category_status == 200


@pytest.mark.anyio
async def test_reference_upload_rejects_public_knowledge_context(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_reference_storage(monkeypatch, tmp_path)
    workbook_path = _write_reference_workbook(tmp_path / "knowledge.xlsx")

    with workbook_path.open("rb") as file_obj:
        response = await auth_client.post(
            "/api/v1/test-cases/references",
            data={"knowledge_context": "不允许公开传入"},
            files={"file": ("knowledge.xlsx", file_obj, "application/octet-stream")},
        )

    assert response.status_code == 400
    assert "V1 不接收用户传入的知识库上下文" in response.json()["detail"]


@pytest.mark.anyio
async def test_upload_profile_failure_cleans_file_and_does_not_create_record(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_dir, _upload_dir = _patch_reference_storage(monkeypatch, tmp_path)
    invalid_path = _write_invalid_workbook(tmp_path / "invalid.xlsx")

    status_code, body = await _upload_reference(auth_client, invalid_path)

    assert status_code == 400
    assert "没有可用的测试用例 Sheet" in body["detail"]
    reference_root = runtime_dir / "test-case-references"
    assert not list(reference_root.rglob("*.*"))
    async with async_session_factory() as session:
        record_count = await session.scalar(
            select(func.count(ReferenceFileRecord.id))
        )
    assert record_count == 0


@pytest.mark.anyio
async def test_recommended_primary_is_unique_within_category_scope(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_reference_storage(monkeypatch, tmp_path)
    first_path = _write_reference_workbook(tmp_path / "first.xlsx")
    second_path = _write_reference_workbook(tmp_path / "second.xlsx")
    first_status, first_body = await _upload_reference(auth_client, first_path)
    second_status, second_body = await _upload_reference(auth_client, second_path)
    assert first_status == 200
    assert second_status == 200

    first_id = first_body["data"]["id"]
    second_id = second_body["data"]["id"]
    first_response = await auth_client.post(
        f"/api/v1/test-cases/references/{first_id}/recommended-primary"
    )
    second_response = await auth_client.post(
        f"/api/v1/test-cases/references/{second_id}/recommended-primary"
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    references_response = await auth_client.get("/api/v1/test-cases/references")
    items = references_response.json()["data"]["items"]
    recommended_ids = [item["id"] for item in items if item["is_recommended_primary"]]
    assert recommended_ids == [second_id]


@pytest.mark.anyio
async def test_delete_category_moves_references_to_uncategorized_and_clears_recommendation(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_reference_storage(monkeypatch, tmp_path)
    category = await _post_category(auth_client, "可删除分类")
    workbook_path = _write_reference_workbook(tmp_path / "category-delete.xlsx")
    status_code, body = await _upload_reference(
        auth_client,
        workbook_path,
        category_id=category["id"],
    )
    assert status_code == 200
    reference_id = body["data"]["id"]
    recommend_response = await auth_client.post(
        f"/api/v1/test-cases/references/{reference_id}/recommended-primary"
    )
    assert recommend_response.status_code == 200

    delete_response = await auth_client.delete(
        f"/api/v1/test-cases/reference-categories/{category['id']}"
    )

    assert delete_response.status_code == 200
    async with async_session_factory() as session:
        record = await session.get(ReferenceFileRecord, reference_id)
        deleted_category = await session.get(
            ReferenceCategoryRecord,
            category["id"],
        )
    assert deleted_category is None
    assert record is not None
    assert record.category_id is None
    assert record.is_recommended_primary is False


@pytest.mark.anyio
async def test_delete_reference_handles_missing_physical_file_as_success(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_reference_storage(monkeypatch, tmp_path)
    workbook_path = _write_reference_workbook(tmp_path / "missing-delete.xlsx")
    status_code, body = await _upload_reference(auth_client, workbook_path)
    assert status_code == 200
    reference_id = body["data"]["id"]
    record = await _get_reference_record(reference_id)
    Path(record.storage_path).unlink()

    delete_response = await auth_client.delete(
        f"/api/v1/test-cases/references/{reference_id}"
    )

    assert delete_response.status_code == 200
    deleted = await _get_reference_record(reference_id)
    assert deleted.deleted_at is not None
    assert deleted.storage_path == ""
    assert deleted.profile_json == ""
    assert deleted.is_recommended_primary is False


@pytest.mark.anyio
async def test_delete_reference_io_failure_keeps_active_record(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_reference_storage(monkeypatch, tmp_path)
    workbook_path = _write_reference_workbook(tmp_path / "locked-delete.xlsx")
    status_code, body = await _upload_reference(auth_client, workbook_path)
    assert status_code == 200
    reference_id = body["data"]["id"]
    before = await _get_reference_record(reference_id)
    original_storage_path = before.storage_path

    def _raise_permission_error(self: Path, *args: object, **kwargs: object) -> None:
        if self == Path(original_storage_path):
            raise PermissionError("locked")
        return original_unlink(self, *args, **kwargs)

    original_unlink = reference_library.Path.unlink
    monkeypatch.setattr(reference_library.Path, "unlink", _raise_permission_error)

    delete_response = await auth_client.delete(
        f"/api/v1/test-cases/references/{reference_id}"
    )

    assert delete_response.status_code == 500
    assert "删除参考案例文件失败" in delete_response.json()["detail"]
    after = await _get_reference_record(reference_id)
    assert after.deleted_at is None
    assert after.storage_path == original_storage_path


@pytest.mark.anyio
async def test_reference_library_operations_do_not_create_generation_history(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_reference_storage(monkeypatch, tmp_path)
    workbook_path = _write_reference_workbook(tmp_path / "no-history.xlsx")

    status_code, body = await _upload_reference(auth_client, workbook_path)
    assert status_code == 200
    reference_id = body["data"]["id"]
    await auth_client.post(f"/api/v1/test-cases/references/{reference_id}/recommended-primary")
    await auth_client.delete(f"/api/v1/test-cases/references/{reference_id}")

    async with async_session_factory() as session:
        run_count = await session.scalar(select(func.count(ExecutionRunRecord.id)))

    assert run_count == 0
