"""local_file Source Evidence upload tests."""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from openpyxl import Workbook
from openpyxl.drawing.image import Image as OpenpyxlImage
from PIL import Image
from sqlalchemy import select

from backend.app.database import async_session_factory
from backend.app.models import SourceEvidenceResourceRecord, SourceEvidenceRunRecord
from backend.app.test_cases import source_evidence_storage


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


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (4, 4), color=(40, 90, 220)).save(output, format="PNG")
    return output.getvalue()


def _xlsx_bytes() -> bytes:
    tmp = io.BytesIO()
    image_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    image_file.write(_png_bytes())
    image_file.close()
    image_path = Path(image_file.name)
    try:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "活动配置"
        sheet["A1"] = "活动名称"
        sheet["B2"] = "春节签到"
        sheet.add_image(OpenpyxlImage(str(image_path)), "B12")
        hidden = workbook.create_sheet("隐藏配置")
        hidden["A1"] = "隐藏 Sheet 内容"
        hidden.sheet_state = "hidden"
        workbook.save(tmp)
    finally:
        image_path.unlink(missing_ok=True)
    return tmp.getvalue()


def _cell_values(snapshot: dict) -> list[str]:
    return [
        cell["value"]
        for row in snapshot["rows"]
        for cell in row["cells"]
    ]


@pytest.mark.anyio
async def test_upload_xlsx_creates_ready_run_resources_and_snapshot(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs/upload",
        files={
            "file": (
                "活动配置.xlsx",
                _xlsx_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    run = response.json()["data"]
    assert run["status"] == "ready"
    assert run["source_type"] == "local_file"
    assert run["resource_count"] == 1
    run_id = run["id"]

    resources_response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/resources"
    )
    assert resources_response.status_code == 200
    resources = resources_response.json()["data"]["items"]
    assert resources == [
        {
            "id": resources[0]["id"],
            "ref": "excel_img_s001_001",
            "type": "image",
            "position": "excel:sheet=活动配置:image=1:anchor=B12",
            "filename": "excel_img_s001_001.png",
            "download_status": "downloaded",
            "adoption_status": "unobserved",
            "mime_type": "image/png",
        }
    ]
    assert "local_path" not in resources[0]
    assert ":\\" not in json.dumps(resources, ensure_ascii=False)

    async with async_session_factory() as session:
        resource = (
            await session.execute(
                select(SourceEvidenceResourceRecord).where(
                    SourceEvidenceResourceRecord.run_id == run_id
                )
            )
        ).scalar_one()
        assert resource.local_path == "images/excel_img_s001_001.png"
        assert source_evidence_storage.resolve_source_evidence_path(
            test_project_id,
            run_id,
            resource.local_path,
        ).is_file()

    snapshot_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/snapshot"
    )
    assert snapshot_response.status_code == 200
    snapshot = snapshot_response.json()["data"]
    values = _cell_values(snapshot)
    assert "春节签到" in values
    assert "隐藏 Sheet 内容" not in values
    assert any("隐藏配置" in warning["message"] for warning in snapshot["warnings"])
    assert any(
        "excel_img_s001_001" in cell["value"]
        for row in snapshot["rows"]
        for cell in row["cells"]
    )
    assert any(
        cell["column_name"] == "证据状态" and cell["value"] == "pending_visual"
        for row in snapshot["rows"]
        for cell in row["cells"]
    )
    parsed_source = source_evidence_storage.read_source_evidence_json(
        test_project_id,
        run_id,
        "raw/parsed_source.json",
    )
    assert parsed_source["source_type"] == "local_file"


@pytest.mark.anyio
async def test_upload_standalone_image_creates_resource_and_textless_snapshot_warning(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs/upload",
        files={"file": ("ui.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    run_id = response.json()["data"]["id"]
    resources_response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/resources"
    )
    assert resources_response.status_code == 200
    resources = resources_response.json()["data"]["items"]
    assert resources[0]["ref"] == "local_img_001"
    assert resources[0]["download_status"] == "downloaded"
    assert "local_path" not in resources[0]

    snapshot_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/snapshot"
    )
    assert snapshot_response.status_code == 200
    snapshot = snapshot_response.json()["data"]
    assert any("缺少文本主体" in warning["message"] for warning in snapshot["warnings"])
    assert any("local_img_001" in value for value in _cell_values(snapshot))


@pytest.mark.anyio
async def test_upload_rejects_unsupported_suffix(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs/upload",
        files={"file": ("source.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 400
    assert "不支持的本地文件类型" in response.json()["detail"]


@pytest.mark.anyio
async def test_upload_filename_cannot_escape_source_evidence_dir(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs/upload",
        files={
            "file": (
                "../evil.xlsx",
                _xlsx_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    run_id = response.json()["data"]["id"]
    async with async_session_factory() as session:
        run = (
            await session.execute(
                select(SourceEvidenceRunRecord).where(SourceEvidenceRunRecord.id == run_id)
            )
        ).scalar_one()
        manifest = json.loads(run.raw_manifest_json)
        upload_path = manifest["upload"]["relative_path"]
    assert upload_path == "raw/upload/evil.xlsx"
    assert source_evidence_storage.resolve_source_evidence_path(
        test_project_id,
        run_id,
        upload_path,
    ).is_file()


@pytest.mark.anyio
async def test_local_file_retry_preserves_uploaded_source(
    auth_client: AsyncClient,
) -> None:
    create_response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs/upload",
        files={
            "file": (
                "活动配置.xlsx",
                _xlsx_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert create_response.status_code == 200
    run_id = create_response.json()["data"]["id"]

    async with async_session_factory() as session:
        resource = (
            await session.execute(
                select(SourceEvidenceResourceRecord).where(
                    SourceEvidenceResourceRecord.run_id == run_id
                )
            )
        ).scalar_one()
        resource.download_status = "download_failed"
        await session.commit()

    retry_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/retry"
    )

    assert retry_response.status_code == 200
    assert retry_response.json()["data"]["status"] == "ready"
    resources_response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/resources"
    )
    assert resources_response.json()["data"]["items"][0]["download_status"] == "downloaded"
