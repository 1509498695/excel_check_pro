"""Source Evidence 视觉候选和选择契约测试。"""

from __future__ import annotations

import base64
import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import AsyncClient

from backend.app.database import async_session_factory
from backend.app.models import SourceEvidenceResourceRecord, SourceEvidenceRunRecord
from backend.app.test_cases import source_evidence_storage


_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


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


async def _seed_visual_run(project_id: int, *, status: str = "ready") -> int:
    async with async_session_factory() as session:
        run = SourceEvidenceRunRecord(
            project_id=project_id,
            source_type="feishu",
            source_identifier=f"docx-{uuid4().hex[:8]}",
            source_title="视觉候选需求",
            status=status,
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
            raw_manifest_json=json.dumps({"doc_type": "docx"}, ensure_ascii=False),
        )
        session.add(run)
        await session.flush()

        source_evidence_storage.ensure_source_evidence_subdirs(project_id=project_id, run_id=run.id)
        source_evidence_storage.write_source_evidence_bytes(project_id, run.id, "images/ui-a.png", _PNG_1X1)
        source_evidence_storage.write_source_evidence_bytes(project_id, run.id, "images/ui-b.png", _PNG_1X1)
        resources = [
            SourceEvidenceResourceRecord(
                run_id=run.id,
                project_id=project_id,
                ref="img_a",
                resource_type="image",
                position="docx:block:1",
                filename="入口按钮.png",
                status="unobserved",
                download_status="downloaded",
                local_path="images/ui-a.png",
                mime_type="image/png",
                metadata_json=json.dumps(
                    {
                        "nearby_text_before": "如下图展示入口按钮",
                        "nearby_heading": "活动入口",
                    },
                    ensure_ascii=False,
                ),
            ),
            SourceEvidenceResourceRecord(
                run_id=run.id,
                project_id=project_id,
                ref="img_b",
                resource_type="image",
                position="docx:block:2",
                filename="重复截图.png",
                status="unobserved",
                download_status="downloaded",
                local_path="images/ui-b.png",
                mime_type="image/png",
                metadata_json=json.dumps({"nearby_text_before": "普通配图"}, ensure_ascii=False),
            ),
            SourceEvidenceResourceRecord(
                run_id=run.id,
                project_id=project_id,
                ref="img_missing",
                resource_type="image",
                position="docx:block:3",
                filename="缺失图片.png",
                status="unobserved",
                download_status="downloaded",
                local_path="",
                mime_type="image/png",
            ),
            SourceEvidenceResourceRecord(
                run_id=run.id,
                project_id=project_id,
                ref="img_permission",
                resource_type="image",
                position="docx:block:4",
                filename="权限图片.png",
                status="unobserved",
                download_status="pending_permission",
                mime_type="image/png",
            ),
            SourceEvidenceResourceRecord(
                run_id=run.id,
                project_id=project_id,
                ref="att_pdf",
                resource_type="attachment",
                position="docx:block:5",
                filename="规则说明.pdf",
                status="unobserved",
                download_status="downloaded",
                local_path="attachments/spec.pdf",
                mime_type="application/pdf",
            ),
        ]
        session.add_all(resources)
        await session.flush()
        source_evidence_storage.write_source_evidence_json(
            project_id,
            run.id,
            "resources.json",
            [
                {
                    "id": resource.id,
                    "ref": resource.ref,
                    "type": resource.resource_type,
                    "position": resource.position,
                    "filename": resource.filename,
                    "download_status": resource.download_status,
                    "adoption_status": resource.status,
                    "mime_type": resource.mime_type,
                    "local_path": resource.local_path,
                }
                for resource in resources
            ],
        )
        await session.commit()
        return run.id


@pytest.mark.anyio
async def test_visual_candidates_prepare_optimized_images_and_default_selection(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    run_id = await _seed_visual_run(test_project_id)

    response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/visual-candidates"
    )

    assert response.status_code == 200
    data = response.json()["data"]
    candidates = {item["ref"]: item for item in data["items"]}
    assert set(candidates) == {"img_a", "img_b", "img_missing", "img_permission", "att_pdf"}
    assert candidates["img_a"]["selectable"] is True
    assert candidates["img_a"]["recommended"] is True
    assert candidates["img_a"]["selected"] is True
    assert candidates["img_a"]["dimensions"]["original_width"] == 1
    assert candidates["img_a"]["dimensions"]["optimized_width"] == 1
    assert candidates["img_a"]["recommendation_reasons"]
    assert candidates["img_b"]["selectable"] is True
    assert data["selected_refs"] != ["img_a", "img_b"]

    for ref in ("img_missing", "img_permission", "att_pdf"):
        assert candidates[ref]["selectable"] is False
    assert candidates["img_missing"]["status"] == "missing"
    assert candidates["img_permission"]["status"] == "pending_permission"
    assert candidates["att_pdf"]["status"] == "unsupported_attachment"

    assert "optimized_path" not in candidates["img_a"]
    assert "local_path" not in candidates["img_a"]
    assert "file_token" not in json.dumps(data, ensure_ascii=False)

    visual_candidates = source_evidence_storage.read_source_evidence_json(
        test_project_id,
        run_id,
        "visual_evidence/visual_candidates.json",
    )
    optimized_relative = visual_candidates[0]["packet"]["optimized_image"]
    optimized_path = source_evidence_storage.resolve_source_evidence_path(
        test_project_id,
        run_id,
        optimized_relative,
    )
    assert optimized_path.is_file()
    assert optimized_path.suffix == ".jpg"
    optimized_path.relative_to(
        source_evidence_storage.run_source_evidence_dir(project_id=test_project_id, run_id=run_id)
    )


@pytest.mark.anyio
async def test_visual_selection_can_be_saved_and_read_back(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    run_id = await _seed_visual_run(test_project_id)

    save_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/visual-selections",
        json={"selected_refs": ["img_b"]},
    )
    assert save_response.status_code == 200
    assert save_response.json()["data"]["selected_refs"] == ["img_b"]

    read_response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/visual-candidates"
    )
    items = {item["ref"]: item for item in read_response.json()["data"]["items"]}
    assert items["img_a"]["selected"] is False
    assert items["img_b"]["selected"] is True


@pytest.mark.anyio
async def test_expired_or_cleaned_run_rejects_visual_selection(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    run_id = await _seed_visual_run(test_project_id, status="cleaned")

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/visual-selections",
        json={"selected_refs": ["img_a"]},
    )

    assert response.status_code == 409
    assert "重新读取来源" in response.json()["detail"]
