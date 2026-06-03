"""数据源接口安全加固回归测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.api import source_api
from backend.app.auth.service import create_access_token, hash_password
from backend.app.database import async_session_factory
from backend.app.loaders import local_reader
from backend.app.models import Project, User, UserProjectRole
from backend.run import app


def _write_excel(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe = pd.DataFrame({"ID": [1, 2], "Name": ["Alice", "Bob"]})
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        dataframe.to_excel(writer, sheet_name="items", index=False)
    return path


def _patch_local_reader_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    allowlist: tuple[Path, ...],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        local_reader,
        "settings",
        SimpleNamespace(
            local_file_root_allowlist=allowlist,
            runtime_upload_dir=tmp_path / "uploads",
            svn_cache_dir=tmp_path / "svn-cache",
        ),
    )


async def _create_non_member_headers() -> dict[str, str]:
    async with async_session_factory() as session:
        owned_project = Project(name="source-security-owned", description="owned")
        foreign_project = Project(name="source-security-foreign", description="foreign")
        session.add_all([owned_project, foreign_project])
        await session.flush()

        user = User(
            username="source-security-user",
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
@pytest.mark.parametrize(
    ("method", "endpoint", "json_payload"),
    [
        (
            "post",
            "/api/v1/sources/metadata",
            {"id": "local", "type": "local_excel", "path": "D:/not-found.xlsx"},
        ),
        (
            "post",
            "/api/v1/sources/column-preview",
            {
                "source": {
                    "id": "local",
                    "type": "local_excel",
                    "path": "D:/not-found.xlsx",
                },
                "sheet": "items",
                "column": "ID",
            },
        ),
        (
            "post",
            "/api/v1/sources/composite-preview",
            {
                "source": {
                    "id": "local",
                    "type": "local_excel",
                    "path": "D:/not-found.xlsx",
                },
                "sheet": "items",
                "columns": ["ID", "Name"],
                "key_column": "ID",
            },
        ),
        (
            "post",
            "/api/v1/sources/local-directory-validate",
            {"directory_path": "D:/not-found"},
        ),
        (
            "post",
            "/api/v1/sources/local-pick",
            {"source_type": "local_excel"},
        ),
    ],
)
async def test_source_probe_endpoints_require_login(
    test_db,
    method: str,
    endpoint: str,
    json_payload: dict,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await getattr(client, method)(endpoint, json=json_payload)

    assert response.status_code == 401


@pytest.mark.anyio
async def test_source_endpoint_rejects_token_project_not_owned(test_db) -> None:
    headers = await _create_non_member_headers()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    ) as client:
        response = await client.get("/api/v1/sources/capabilities")

    assert response.status_code == 403
    assert response.json()["detail"] == "您不属于当前项目"


@pytest.mark.anyio
async def test_local_excel_outside_allowlist_is_rejected_for_metadata_and_preview(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_local_reader_settings(monkeypatch, allowlist=(), tmp_path=tmp_path)
    workbook_path = _write_excel(tmp_path / "outside" / "source.xlsx")
    source = {"id": "local", "type": "local_excel", "path": str(workbook_path)}

    metadata_response = await auth_client.post("/api/v1/sources/metadata", json=source)
    preview_response = await auth_client.post(
        "/api/v1/sources/column-preview",
        json={
            "source": source,
            "sheet": "items",
            "column": "ID",
        },
    )

    assert metadata_response.status_code == 403
    assert preview_response.status_code == 403
    assert "LOCAL_FILE_ROOT_ALLOWLIST" in metadata_response.json()["detail"]


@pytest.mark.anyio
async def test_local_excel_inside_allowlist_can_read_metadata_and_preview(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    allowed_dir = tmp_path / "allowed"
    workbook_path = _write_excel(allowed_dir / "source.xlsx")
    _patch_local_reader_settings(
        monkeypatch,
        allowlist=(allowed_dir,),
        tmp_path=tmp_path,
    )
    source = {"id": "local", "type": "local_excel", "path": str(workbook_path)}

    metadata_response = await auth_client.post("/api/v1/sources/metadata", json=source)
    preview_response = await auth_client.post(
        "/api/v1/sources/column-preview",
        json={
            "source": source,
            "sheet": "items",
            "column": "Name",
            "limit": 1,
        },
    )

    assert metadata_response.status_code == 200
    metadata = metadata_response.json()["data"]
    assert metadata["sheets"][0]["name"] == "items"
    assert metadata["sheets"][0]["columns"] == ["ID", "Name"]
    assert preview_response.status_code == 200
    preview = preview_response.json()["data"]
    assert preview["preview_rows"] == [{"row_index": 2, "value": "Alice"}]


@pytest.mark.anyio
async def test_local_directory_validate_rejects_outside_allowlist_without_existence_leak(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_local_reader_settings(monkeypatch, allowlist=(), tmp_path=tmp_path)
    outside_directory = tmp_path / "outside" / "missing"

    response = await auth_client.post(
        "/api/v1/sources/local-directory-validate",
        json={"directory_path": str(outside_directory)},
    )

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert "LOCAL_FILE_ROOT_ALLOWLIST" in detail
    assert "不存在" not in detail
    assert str(outside_directory) not in detail


@pytest.mark.anyio
async def test_local_pick_is_disabled_by_default(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        source_api,
        "settings",
        SimpleNamespace(enable_local_picker=False),
    )

    response = await auth_client.post(
        "/api/v1/sources/local-pick",
        json={"source_type": "local_excel"},
    )

    assert response.status_code == 403
    assert "ENABLE_LOCAL_PICKER=true" in response.json()["detail"]


@pytest.mark.anyio
async def test_local_pick_when_enabled_returns_allowlisted_selected_path(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    allowed_dir = tmp_path / "allowed-picker"
    workbook_path = _write_excel(allowed_dir / "source.xlsx")
    _patch_local_reader_settings(
        monkeypatch,
        allowlist=(allowed_dir,),
        tmp_path=tmp_path,
    )
    monkeypatch.setattr(
        source_api,
        "settings",
        SimpleNamespace(enable_local_picker=True),
    )
    monkeypatch.setattr(
        source_api,
        "_show_local_file_dialog",
        lambda _source_type: str(workbook_path),
    )

    response = await auth_client.post(
        "/api/v1/sources/local-pick",
        json={"source_type": "local_excel"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["selected_path"] == str(workbook_path.resolve())
