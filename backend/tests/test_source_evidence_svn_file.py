"""svn_file Source Evidence tests."""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from httpx import AsyncClient
from openpyxl import Workbook
from openpyxl.drawing.image import Image as OpenpyxlImage
from PIL import Image
import pytest
from sqlalchemy import func, select

from backend.app.database import async_session_factory
from backend.app.loaders import svn_manager
from backend.app.models import ProjectSvnCredentialRecord, SourceEvidenceRunRecord
from backend.app.security.crypto import encrypt_secret
from backend.app.test_cases import source_evidence_storage
from backend.app.test_cases.schemas import (
    ParsedSource,
    ParsedSourceCell,
    ParsedSourceUnit,
)


@pytest.fixture(autouse=True)
def _source_evidence_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        source_evidence_dir=tmp_path / "source-evidence",
        svn_url_allowlist=("samosvn",),
        svn_subprocess_timeout_seconds=30,
        svn_list_timeout_seconds=30,
    )
    monkeypatch.setattr(source_evidence_storage, "settings", settings)
    monkeypatch.setattr(svn_manager, "settings", settings)


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (4, 4), color=(40, 90, 220)).save(output, format="PNG")
    return output.getvalue()


def _write_xlsx_with_image(path: Path, image_path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "活动配置"
    sheet["A1"] = "活动名称"
    sheet["B2"] = "SVN 活动"
    sheet.add_image(OpenpyxlImage(str(image_path)), "B12")
    workbook.save(path)


def _fake_xls_text_source(
    *,
    original_filename: str,
    source_sha256: str,
    **_kwargs: Any,
) -> ParsedSource:
    return ParsedSource(
        title=original_filename,
        doc_type="xls",
        token=f"sha256:{source_sha256}",
        url="",
        markdown="# Source: source.xls\n\nType: xls\n\n## Sheet: 活动配置\n- A1: 活动名称\n- B2: SVN 活动\n",
        source_units=[
            ParsedSourceUnit(
                unit_id="xls_s001",
                kind="sheet",
                title="活动配置",
                cells=[
                    ParsedSourceCell(coord="A1", row=1, col=1, text="活动名称"),
                    ParsedSourceCell(coord="B2", row=2, col=2, text="SVN 活动"),
                ],
            )
        ],
        raw_manifest={"doc_type": "xls"},
    )


async def _save_source_evidence_root(
    client: AsyncClient,
    project_id: int,
    *,
    svn_url: str = "https://samosvn/game/design/",
) -> None:
    response = await client.put(
        f"/api/v1/admin/projects/{project_id}/source-evidence-svn-roots",
        json={
            "items": [
                {
                    "alias": "design_docs",
                    "display_name": "策划案 SVN",
                    "svn_url": svn_url,
                    "enabled": True,
                }
            ]
        },
    )
    assert response.status_code == 200, response.text


async def _seed_project_svn_credential(
    project_id: int,
    *,
    username: str = "project_svn",
    password: str = "secret_password_should_not_leak",
) -> None:
    async with async_session_factory() as session:
        session.add(
            ProjectSvnCredentialRecord(
                project_id=project_id,
                username=username,
                password_cipher=encrypt_secret(password),
            )
        )
        await session.commit()


def _patch_svn_checkout(
    monkeypatch: pytest.MonkeyPatch,
    *,
    file_name: str = "source.xls",
    content: bytes = b"fake-xls",
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def _list_svn_directory(dir_url: str, *, credentials, timeout=None):  # noqa: ANN001
        calls.append({"op": "list", "dir_url": dir_url, "password": credentials.password})
        return {
            "dir_url": dir_url,
            "entries": [
                {
                    "kind": "file",
                    "name": file_name,
                    "size": len(content),
                    "revision": 321,
                    "last_author": "planner",
                    "last_modified_at": "2026-07-01T08:00:00Z",
                }
            ],
        }

    def _checkout_remote_directory(*, dir_url, target_dir: Path, credentials, **_kwargs):  # noqa: ANN001
        calls.append({"op": "checkout", "dir_url": dir_url, "password": credentials.password})
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / ".svn").mkdir()
        (target_dir / file_name).write_bytes(content)
        return {"output": "Checked out revision 456."}

    monkeypatch.setattr(
        "backend.app.test_cases.svn_source_reader.list_svn_directory",
        _list_svn_directory,
    )
    monkeypatch.setattr(
        "backend.app.test_cases.svn_source_reader.checkout_remote_directory",
        _checkout_remote_directory,
    )
    monkeypatch.setattr(
        "backend.app.test_cases.svn_source_reader.get_remote_revision",
        lambda *_a, **_k: 456,
    )
    return calls


@pytest.mark.anyio
async def test_svn_file_xls_create_reuses_local_reader_and_extracts_converted_images(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    await _save_source_evidence_root(auth_client, test_project_id)
    await _seed_project_svn_credential(test_project_id)
    calls = _patch_svn_checkout(monkeypatch)

    monkeypatch.setattr(
        "backend.app.test_cases.excel_source_reader._read_xls_text_source",
        _fake_xls_text_source,
    )

    def _convert_xls_to_xlsx(*, project_id: int, run_id: int, **_kwargs: Any) -> str:
        image_path = tmp_path / "image.png"
        image_path.write_bytes(_png_bytes())
        relative_path = "raw/converted/source.xlsx"
        converted_path = source_evidence_storage.resolve_source_evidence_path(
            project_id,
            run_id,
            relative_path,
        )
        converted_path.parent.mkdir(parents=True, exist_ok=True)
        _write_xlsx_with_image(converted_path, image_path)
        return relative_path

    monkeypatch.setattr(
        "backend.app.test_cases.excel_source_reader._convert_xls_to_xlsx",
        _convert_xls_to_xlsx,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs",
        json={
            "source_type": "svn_file",
            "source_url": "https://samosvn/game/design/source.xls",
        },
    )

    assert response.status_code == 200, response.text
    run = response.json()["data"]
    assert run["status"] == "ready"
    assert run["source_type"] == "svn_file"
    assert run["resource_count"] == 1
    assert "secret_password_should_not_leak" not in response.text
    assert calls == [
        {
            "op": "list",
            "dir_url": "https://samosvn/game/design/",
            "password": "secret_password_should_not_leak",
        },
        {
            "op": "checkout",
            "dir_url": "https://samosvn/game/design/",
            "password": "secret_password_should_not_leak",
        },
    ]

    resources_response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{run['id']}/resources"
    )
    assert resources_response.status_code == 200
    resources = resources_response.json()["data"]["items"]
    assert resources[0]["ref"] == "excel_img_s001_001"
    assert resources[0]["download_status"] == "downloaded"
    assert "local_path" not in resources[0]

    snapshot_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run['id']}/snapshot"
    )
    assert snapshot_response.status_code == 200
    snapshot_values = [
        cell["value"]
        for row in snapshot_response.json()["data"]["rows"]
        for cell in row["cells"]
    ]
    assert "SVN 活动" in snapshot_values

    async with async_session_factory() as session:
        record = (
            await session.execute(
                select(SourceEvidenceRunRecord).where(SourceEvidenceRunRecord.id == run["id"])
            )
        ).scalar_one()
        manifest = json.loads(record.raw_manifest_json)
    assert manifest["svn"]["url"] == "https://samosvn/game/design/source.xls"
    assert manifest["svn"]["root_alias"] == "design_docs"
    assert manifest["svn"]["revision"] == 456
    assert manifest["svn"]["last_changed_rev"] == 321
    assert manifest["svn"]["last_author"] == "planner"
    assert manifest["svn"]["file_sha256"]
    assert "secret_password_should_not_leak" not in json.dumps(manifest, ensure_ascii=False)
    assert ":\\" not in json.dumps(manifest, ensure_ascii=False)


@pytest.mark.anyio
async def test_svn_file_root_outside_is_rejected_without_persisting_run(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    await _save_source_evidence_root(auth_client, test_project_id)
    await _seed_project_svn_credential(test_project_id)
    async with async_session_factory() as session:
        before_count = (
            await session.execute(
                select(func.count(SourceEvidenceRunRecord.id)).where(
                    SourceEvidenceRunRecord.project_id == test_project_id
                )
            )
        ).scalar_one()

    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs",
        json={
            "source_type": "svn_file",
            "source_url": "https://samosvn/game/other/source.xls",
        },
    )

    assert response.status_code == 400
    assert "超出 Source Evidence SVN Root" in response.json()["detail"]
    async with async_session_factory() as session:
        after_count = (
            await session.execute(
                select(func.count(SourceEvidenceRunRecord.id)).where(
                    SourceEvidenceRunRecord.project_id == test_project_id
                )
            )
        ).scalar_one()
    assert after_count == before_count


@pytest.mark.anyio
async def test_svn_file_requires_project_svn_credential(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    await _save_source_evidence_root(auth_client, test_project_id)

    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs",
        json={
            "source_type": "svn_file",
            "source_url": "https://samosvn/game/design/source.xls",
        },
    )

    assert response.status_code == 400
    assert "项目级 SVN 凭据" in response.json()["detail"]


@pytest.mark.anyio
async def test_svn_file_rejects_host_outside_allowlist(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs",
        json={
            "source_type": "svn_file",
            "source_url": "https://evil.example.com/game/design/source.xls",
        },
    )

    assert response.status_code == 400
    assert "不在允许列表" in response.json()["detail"]


@pytest.mark.anyio
async def test_svn_file_translates_auth_failure_without_leaking_password(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _save_source_evidence_root(auth_client, test_project_id)
    await _seed_project_svn_credential(test_project_id)

    def _failing_list(*_args, **_kwargs):
        raise svn_manager.SvnRemoteError("auth_failed", "Authorization failed secret_password_should_not_leak")

    monkeypatch.setattr(
        "backend.app.test_cases.svn_source_reader.list_svn_directory",
        _failing_list,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs",
        json={
            "source_type": "svn_file",
            "source_url": "https://samosvn/game/design/source.xls",
        },
    )

    assert response.status_code == 403
    assert "SVN 鉴权失败" in response.json()["detail"]
    assert "secret_password_should_not_leak" not in response.text


@pytest.mark.anyio
async def test_svn_file_not_found_returns_404(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _save_source_evidence_root(auth_client, test_project_id)
    await _seed_project_svn_credential(test_project_id)

    monkeypatch.setattr(
        "backend.app.test_cases.svn_source_reader.list_svn_directory",
        lambda dir_url, **_kwargs: {"dir_url": dir_url, "entries": []},
    )

    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs",
        json={
            "source_type": "svn_file",
            "source_url": "https://samosvn/game/design/missing.xls",
        },
    )

    assert response.status_code == 404
    assert "SVN 文件不存在" in response.json()["detail"]


@pytest.mark.anyio
async def test_svn_xls_conversion_failure_keeps_text_with_warning(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _save_source_evidence_root(auth_client, test_project_id)
    await _seed_project_svn_credential(test_project_id)
    _patch_svn_checkout(monkeypatch)
    monkeypatch.setattr(
        "backend.app.test_cases.excel_source_reader._read_xls_text_source",
        _fake_xls_text_source,
    )
    monkeypatch.setattr(
        "backend.app.test_cases.excel_source_reader._convert_xls_to_xlsx",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("fake convert failed")),
    )

    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs",
        json={
            "source_type": "svn_file",
            "source_url": "https://samosvn/game/design/source.xls",
        },
    )

    assert response.status_code == 200
    run = response.json()["data"]
    assert run["status"] == "ready"
    assert run["resource_count"] == 0
    assert any(".xls 图片转换失败" in warning["message"] for warning in run["warnings"])
    snapshot_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run['id']}/snapshot"
    )
    values = [
        cell["value"]
        for row in snapshot_response.json()["data"]["rows"]
        for cell in row["cells"]
    ]
    assert "SVN 活动" in values


@pytest.mark.anyio
async def test_svn_standalone_image_uses_svn_image_ref(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _save_source_evidence_root(auth_client, test_project_id)
    await _seed_project_svn_credential(test_project_id)
    _patch_svn_checkout(monkeypatch, file_name="ui.png", content=_png_bytes())

    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs",
        json={
            "source_type": "svn_file",
            "source_url": "https://samosvn/game/design/ui.png",
        },
    )

    assert response.status_code == 200
    run_id = response.json()["data"]["id"]
    resources_response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/resources"
    )
    assert resources_response.status_code == 200
    resources = resources_response.json()["data"]["items"]
    assert resources[0]["ref"] == "svn_img_001"
    assert resources[0]["position"] == "svn:image=1"
    assert resources[0]["download_status"] == "downloaded"
