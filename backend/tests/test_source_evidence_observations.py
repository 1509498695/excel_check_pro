"""Source Evidence Vision observation and adopted evidence tests."""

from __future__ import annotations

import base64
import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from backend.app.database import async_session_factory
from backend.app.models import (
    Project,
    ProjectAiCredentialRecord,
    ProjectVisionAiCredentialRecord,
    SourceEvidenceResourceRecord,
    SourceEvidenceRunRecord,
    SourceEvidenceVisualObservationRecord,
)
from backend.app.security.crypto import encrypt_secret
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


async def _seed_project_ai(project_id: int) -> None:
    async with async_session_factory() as session:
        session.add(
            ProjectAiCredentialRecord(
                project_id=project_id,
                provider_preset="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                encrypted_api_key=encrypt_secret("sk-source-evidence-text"),
                extra_headers_json="{}",
                enabled=True,
            )
        )
        await session.commit()


async def _seed_project_vision_ai(project_id: int) -> None:
    async with async_session_factory() as session:
        session.add(
            ProjectVisionAiCredentialRecord(
                project_id=project_id,
                provider_preset="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                encrypted_api_key=encrypt_secret("sk-source-evidence-vision"),
                extra_headers_json="{}",
                enabled=True,
            )
        )
        await session.commit()


async def _seed_visual_run(
    project_id: int,
    *,
    status: str = "ready",
    expires_at: datetime.datetime | None = None,
) -> int:
    expires_at = expires_at or (
        datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
    )
    async with async_session_factory() as session:
        run = SourceEvidenceRunRecord(
            project_id=project_id,
            source_type="feishu",
            source_url="https://example.feishu.cn/docx/doc-secret-token",
            source_token="doc-secret-token",
            source_identifier="doc-secret-token",
            source_title="视觉需求文档",
            status=status,
            expires_at=expires_at,
            raw_manifest_json=json.dumps(
                {
                    "doc_type": "docx",
                    "warnings": [],
                    "counts": {"resource_count": 1, "source_unit_count": 1},
                },
                ensure_ascii=False,
            ),
        )
        session.add(run)
        await session.flush()
        source_evidence_storage.ensure_source_evidence_subdirs(
            project_id=project_id,
            run_id=run.id,
        )
        run.storage_path = str(
            source_evidence_storage.run_source_evidence_dir(
                project_id=project_id,
                run_id=run.id,
            )
        )
        source_evidence_storage.write_source_evidence_bytes(
            project_id,
            run.id,
            "images/ui.png",
            _PNG_1X1,
        )
        source_evidence_storage.write_source_evidence_json(
            project_id,
            run.id,
            "raw/parsed_source.json",
            {
                "title": "视觉需求文档",
                "doc_type": "docx",
                "token": "doc-secret-token",
                "url": "https://example.feishu.cn/docx/doc-secret-token",
                "markdown": "正文规则：入口按配置开放。\n"
                '<image ref="img_001" position="docx:block:3" />',
                "source_units": [
                    {
                        "unit_id": "docx_doc_secret",
                        "kind": "docx",
                        "title": "视觉需求文档",
                        "metadata": {"block_count": 2, "resource_count": 1},
                    }
                ],
                "resources": [],
                "raw_manifest": {},
                "warnings": [],
            },
        )
        resource = SourceEvidenceResourceRecord(
            run_id=run.id,
            project_id=project_id,
            ref="img_001",
            resource_type="image",
            position="docx:block:3",
            filename="入口示意图.png",
            file_token="file-secret-token",
            status="unobserved",
            download_status="downloaded",
            local_path="images/ui.png",
            mime_type="image/png",
            metadata_json=json.dumps(
                {
                    "nearby_heading": "活动入口",
                    "nearby_text_before": "如下图展示入口按钮",
                },
                ensure_ascii=False,
            ),
        )
        session.add(resource)
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
            ],
        )
        await session.commit()
        return run.id


async def _seed_foreign_project_run() -> int:
    async with async_session_factory() as session:
        project = Project(name=f"vision-foreign-{uuid4().hex[:8]}", description="")
        session.add(project)
        await session.flush()
        project_id = project.id
    return await _seed_visual_run(project_id)


def _source_evidence_snapshot() -> dict[str, Any]:
    return {
        "source_summary": "飞书 docx：视觉需求文档",
        "sheet_name": "Source Evidence",
        "columns": ["来源类型", "位置", "标题/页签", "内容", "证据状态"],
        "rows": [
            {
                "row_index": 1,
                "cells": [
                    {"row_index": 1, "column_index": 1, "column_name": "来源类型", "value": "feishu:docx"},
                    {"row_index": 1, "column_index": 2, "column_name": "位置", "value": "docx:line:1"},
                    {"row_index": 1, "column_index": 3, "column_name": "标题/页签", "value": "视觉需求文档"},
                    {"row_index": 1, "column_index": 4, "column_name": "内容", "value": "正文规则：入口按配置开放。"},
                    {"row_index": 1, "column_index": 5, "column_name": "证据状态", "value": "text"},
                ],
            }
        ],
        "non_empty_cell_count": 5,
        "truncated": False,
        "warnings": [],
    }


async def _create_observation(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    *,
    project_id: int,
    run_id: int,
) -> int:
    await _seed_project_vision_ai(project_id)

    async def fake_call_provider_vision_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        assert kwargs["api_key"] == "sk-source-evidence-vision"
        assert kwargs["image_bytes"]
        assert "file-secret-token" not in kwargs["user_prompt"]
        return {
            "summary": "图中展示活动入口按钮，按钮文案为“参与活动”。",
            "visible_text": "参与活动",
            "confidence": 0.88,
            "limitations": ["仅能确认截图中可见按钮，不能确认入口开放规则。"],
        }, {"usage": {"total_tokens": 12}}

    monkeypatch.setattr(
        "backend.app.test_cases.visual_evidence.call_provider_vision_json",
        fake_call_provider_vision_json,
    )
    await client.get(f"/api/v1/test-cases/source-evidence-runs/{run_id}/visual-candidates")
    await client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/visual-selections",
        json={"selected_refs": ["img_001"]},
    )
    response = await client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/observations",
        json={},
    )
    assert response.status_code == 200, response.text
    return int(response.json()["data"]["items"][0]["id"])


@pytest.mark.anyio
async def test_vision_unconfigured_returns_displayable_error_but_text_generation_still_works(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = await _seed_visual_run(test_project_id)
    await _seed_project_ai(test_project_id)
    await auth_client.get(f"/api/v1/test-cases/source-evidence-runs/{run_id}/visual-candidates")

    observation_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/observations",
        json={},
    )
    assert observation_response.status_code == 400
    assert "Vision AI" in observation_response.text

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        if fake_call_provider_json.calls == 0:
            fake_call_provider_json.calls += 1
            return {"modules": [], "flows": [], "warnings": []}, {}
        return {
            "cases": [
                {
                    "case_id": "TC-001",
                    "title": "入口按配置开放",
                    "steps": "打开活动入口",
                    "expected_results": "入口按配置展示",
                    "source_requirement": "正文规则：入口按配置开放。",
                }
            ],
            "warnings": [],
            "requirement_trace": [],
        }, {}

    fake_call_provider_json.calls = 0
    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    generate_response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json={
            "planning_snapshot": _source_evidence_snapshot(),
            "source_evidence_run_id": run_id,
            "reference_ids": [],
            "primary_reference_id": None,
        },
    )

    assert generate_response.status_code == 200, generate_response.text
    assert generate_response.json()["data"]["cases"][0]["case_id"] == "TC-001"


@pytest.mark.anyio
async def test_observation_uses_saved_selection_and_does_not_leak_sensitive_fields(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = await _seed_visual_run(test_project_id)
    observation_id = await _create_observation(
        auth_client,
        monkeypatch,
        project_id=test_project_id,
        run_id=run_id,
    )

    read_response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/observations"
    )
    assert read_response.status_code == 200
    response_text = read_response.text
    assert "file-secret-token" not in response_text
    assert "images/ui.png" not in response_text
    assert "visual_evidence/images" not in response_text
    assert "sk-source-evidence-vision" not in response_text
    assert "provider_response" not in response_text
    assert "prompt" not in response_text

    item = read_response.json()["data"]["items"][0]
    assert item["id"] == observation_id
    assert item["ref"] == "img_001"
    assert item["status"] == "observed"
    assert item["summary"] == "图中展示活动入口按钮，按钮文案为“参与活动”。"
    assert item["visible_text"] == "参与活动"
    assert item["limitations"] == ["仅能确认截图中可见按钮，不能确认入口开放规则。"]

    async with async_session_factory() as session:
        record = await session.get(SourceEvidenceVisualObservationRecord, observation_id)
        assert record is not None
        assert record.status == "observed"
        assert record.observation_path.startswith("visual_evidence/observations/")
        observation_path = source_evidence_storage.resolve_source_evidence_path(
            test_project_id,
            run_id,
            record.observation_path,
        )
        observation_path.relative_to(
            source_evidence_storage.run_source_evidence_dir(
                project_id=test_project_id,
                run_id=run_id,
            )
        )
        payload = json.loads(observation_path.read_text(encoding="utf-8"))
        assert payload["summary"] == item["summary"]
        assert "provider_response" not in json.dumps(payload, ensure_ascii=False)
        assert "prompt" not in json.dumps(payload, ensure_ascii=False)
        assert "images/ui.png" not in json.dumps(payload, ensure_ascii=False)


@pytest.mark.anyio
async def test_adopt_and_revoke_visual_evidence_updates_generation_boundary(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = await _seed_visual_run(test_project_id)
    observation_id = await _create_observation(
        auth_client,
        monkeypatch,
        project_id=test_project_id,
        run_id=run_id,
    )

    adopt_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/adopted-visual-evidence",
        json={"observation_ids": [observation_id]},
    )
    assert adopt_response.status_code == 200, adopt_response.text
    assert adopt_response.json()["data"]["items"][0]["status"] == "adopted"
    adopted_index = source_evidence_storage.read_source_evidence_json(
        test_project_id,
        run_id,
        "visual_evidence/adopted_visual_evidence.json",
    )
    assert adopted_index["items"][0]["id"] == observation_id
    assert adopted_index["items"][0]["status"] == "adopted"

    async with async_session_factory() as session:
        resource = (
            await session.execute(
                select(SourceEvidenceResourceRecord).where(
                    SourceEvidenceResourceRecord.project_id == test_project_id,
                    SourceEvidenceResourceRecord.run_id == run_id,
                    SourceEvidenceResourceRecord.ref == "img_001",
                )
            )
        ).scalar_one()
        assert resource.status == "adopted"

    revoke_response = await auth_client.delete(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/adopted-visual-evidence/{observation_id}"
    )
    assert revoke_response.status_code == 200
    assert revoke_response.json()["data"]["items"][0]["status"] == "observed"
    adopted_index = source_evidence_storage.read_source_evidence_json(
        test_project_id,
        run_id,
        "visual_evidence/adopted_visual_evidence.json",
    )
    assert adopted_index["items"] == []

    async with async_session_factory() as session:
        resource = (
            await session.execute(
                select(SourceEvidenceResourceRecord).where(
                    SourceEvidenceResourceRecord.project_id == test_project_id,
                    SourceEvidenceResourceRecord.run_id == run_id,
                    SourceEvidenceResourceRecord.ref == "img_001",
                )
            )
        ).scalar_one()
        assert resource.status == "observed"


@pytest.mark.anyio
async def test_expired_or_cleaned_run_rejects_observation_and_adoption(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    run_id = await _seed_visual_run(test_project_id, status="cleaned")

    observation_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/observations",
        json={},
    )
    adoption_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/adopted-visual-evidence",
        json={"observation_ids": [1]},
    )

    assert observation_response.status_code == 409
    assert adoption_response.status_code == 409
    assert "重新读取来源" in observation_response.text


@pytest.mark.anyio
async def test_cross_project_observation_and_adoption_are_not_visible(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    foreign_run_id = await _seed_foreign_project_run()

    read_response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{foreign_run_id}/observations"
    )
    observe_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{foreign_run_id}/observations",
        json={},
    )
    adopt_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{foreign_run_id}/adopted-visual-evidence",
        json={"observation_ids": [1]},
    )

    assert read_response.status_code == 404
    assert observe_response.status_code == 404
    assert adopt_response.status_code == 404
