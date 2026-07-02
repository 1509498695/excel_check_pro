"""Source Evidence Run 接入生成链路测试。"""

from __future__ import annotations

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
    SourceEvidenceResourceRecord,
    SourceEvidenceRunRecord,
    SourceEvidenceVisualObservationRecord,
)
from backend.app.security.crypto import encrypt_secret
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


async def _seed_project_ai(project_id: int) -> None:
    async with async_session_factory() as session:
        session.add(
            ProjectAiCredentialRecord(
                project_id=project_id,
                provider_preset="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                encrypted_api_key=encrypt_secret("sk-source-evidence-secret"),
                extra_headers_json="{}",
                enabled=True,
            )
        )
        await session.commit()


async def _seed_source_evidence_run(
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
            source_url="https://demo.feishu.cn/docx/doccn-secret-token",
            source_token="doccn-secret-token",
            source_identifier="doccn-secret-token",
            source_title="活动需求文档",
            status=status,
            expires_at=expires_at,
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
        session.add(
            SourceEvidenceResourceRecord(
                run_id=run.id,
                project_id=project_id,
                ref="docx_img_001",
                resource_type="image",
                position="docx:block:img",
                filename="ui.png",
                file_token="file-secret-token",
                status="unobserved",
                download_status="download_failed",
                mime_type="image/png",
            )
        )
        session.add(
            SourceEvidenceResourceRecord(
                run_id=run.id,
                project_id=project_id,
                ref="docx_att_001",
                resource_type="attachment",
                position="docx:block:file",
                filename="spec.pdf",
                file_token="attachment-secret-token",
                status="unobserved",
                download_status="pending_permission",
                mime_type="application/pdf",
            )
        )
        manifest = {
            "run_id": run.id,
            "project_id": project_id,
            "source_type": "feishu",
            "source_identifier": "doccn-secret-token",
            "source_title": "活动需求文档",
            "doc_type": "docx",
            "status": status,
            "counts": {
                "source_unit_count": 1,
                "resource_count": 2,
                "downloaded_resource_count": 0,
                "failed_resource_count": 2,
                "warning_count": 2,
            },
            "warnings": [
                {
                    "source": "feishu",
                    "level": "warning",
                    "message": "隐藏 Sheet '内部配置' 已排除。",
                },
                {
                    "source": "feishu",
                    "level": "warning",
                    "message": "unsupported resource candidate: whiteboard",
                },
            ],
            "expires_at": expires_at.isoformat(),
        }
        run.raw_manifest_json = json.dumps(manifest, ensure_ascii=False)
        source_evidence_storage.write_source_evidence_json(
            project_id,
            run.id,
            "raw/parsed_source.json",
            {
                "title": "活动需求文档",
                "doc_type": "docx",
                "token": "doccn-secret-token",
                "url": "https://demo.feishu.cn/docx/doccn-secret-token",
                "markdown": (
                    "正文规则：每日可领取一次。\n"
                    '<image ref="docx_img_001" position="docx:block:img" />\n'
                    '<attachment ref="docx_att_001" position="docx:block:file" />'
                ),
                "source_units": [
                    {
                        "unit_id": "docx_doccn_secret",
                        "kind": "docx",
                        "title": "活动需求文档",
                        "metadata": {"block_count": 3, "resource_count": 2},
                    }
                ],
                "resources": [
                    {
                        "ref": "docx_img_001",
                        "type": "image",
                        "source_id": "file-secret-token",
                        "position": "docx:block:img",
                        "filename": "ui.png",
                        "file_token": "file-secret-token",
                        "mime_type": "image/png",
                    },
                    {
                        "ref": "docx_att_001",
                        "type": "attachment",
                        "source_id": "attachment-secret-token",
                        "position": "docx:block:file",
                        "filename": "spec.pdf",
                        "file_token": "attachment-secret-token",
                        "mime_type": "application/pdf",
                    },
                ],
                "raw_manifest": {
                    "raw_content": "不得进入 prompt 的原文全文",
                    "block_pages": [{"token": "不得进入 prompt 的 block 原始结构"}],
                },
                "warnings": manifest["warnings"],
            },
        )
        await session.commit()
        return run.id


async def _seed_foreign_source_evidence_run() -> int:
    async with async_session_factory() as session:
        project = Project(name=f"se-generate-foreign-{uuid4().hex[:8]}", description="")
        session.add(project)
        await session.flush()
        project_id = project.id
    return await _seed_source_evidence_run(project_id)


async def _seed_tabular_source_evidence_run(
    project_id: int,
    *,
    source_type: str,
    doc_type: str,
    title: str,
    fact_text: str,
) -> int:
    expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
    async with async_session_factory() as session:
        run = SourceEvidenceRunRecord(
            project_id=project_id,
            source_type=source_type,
            source_url=f"https://demo.invalid/{title}",
            source_token="sha256:sensitive-token",
            source_identifier="sha256:sensitive-token",
            source_title=title,
            status="ready",
            expires_at=expires_at,
            raw_manifest_json=json.dumps(
                {
                    "run_id": 0,
                    "project_id": project_id,
                    "source_type": source_type,
                    "doc_type": doc_type,
                    "status": "ready",
                    "warnings": [],
                    "svn_password": "svn-password-must-not-leak",
                    "local_path": "D:/runtime/source-evidence/raw/source.xls",
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
        session.add(
            SourceEvidenceResourceRecord(
                run_id=run.id,
                project_id=project_id,
                ref=f"{source_type}_img_001",
                resource_type="image",
                position="excel:sheet=配置:image=1:anchor=B12",
                filename="ui.png",
                file_token="file-token-must-not-leak",
                status="unobserved",
                download_status="downloaded",
                local_path="D:/runtime/source-evidence/images/ui.png",
                mime_type="image/png",
                metadata_json=json.dumps(
                    {"provider_response": "provider-response-must-not-leak"},
                    ensure_ascii=False,
                ),
            )
        )
        source_evidence_storage.write_source_evidence_json(
            project_id,
            run.id,
            "raw/parsed_source.json",
            {
                "source_type": source_type,
                "title": title,
                "doc_type": doc_type,
                "token": "sha256:sensitive-token",
                "url": "https://demo.invalid/token-must-not-leak",
                "markdown": "",
                "source_units": [
                    {
                        "unit_id": f"{doc_type}_s001",
                        "kind": "sheet",
                        "title": "配置",
                        "cells": [
                            {
                                "coord": "B2",
                                "row": 2,
                                "col": 2,
                                "text": fact_text,
                            }
                        ],
                    }
                ],
                "resources": [],
                "raw_manifest": {
                    "svn_password": "svn-password-must-not-leak",
                    "local_path": "D:/runtime/source-evidence/raw/source.xls",
                },
                "warnings": [],
            },
        )
        await session.commit()
        return run.id


async def _seed_textless_image_source_evidence_run(project_id: int) -> int:
    expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
    async with async_session_factory() as session:
        run = SourceEvidenceRunRecord(
            project_id=project_id,
            source_type="local_file",
            source_url="",
            source_token="sha256:image",
            source_identifier="sha256:image",
            source_title="ui.png",
            status="ready",
            expires_at=expires_at,
            raw_manifest_json=json.dumps(
                {
                    "run_id": 0,
                    "project_id": project_id,
                    "source_type": "local_file",
                    "source_title": "ui.png",
                    "doc_type": "image",
                    "warnings": [],
                    "expires_at": expires_at.isoformat(),
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
        run.raw_manifest_json = json.dumps(
            {**json.loads(run.raw_manifest_json), "run_id": run.id},
            ensure_ascii=False,
        )
        session.add(
            SourceEvidenceResourceRecord(
                run_id=run.id,
                project_id=project_id,
                ref="local_img_001",
                resource_type="image",
                position="local:image=1",
                filename="local_img_001.png",
                status="unobserved",
                download_status="downloaded",
                local_path="images/local_img_001.png",
                mime_type="image/png",
            )
        )
        source_evidence_storage.write_source_evidence_json(
            project_id,
            run.id,
            "raw/parsed_source.json",
            {
                "source_type": "local_file",
                "title": "ui.png",
                "doc_type": "image",
                "token": "sha256:image",
                "url": "",
                "markdown": '<image ref="local_img_001" position="local:image=1" />',
                "source_units": [],
                "resources": [],
                "raw_manifest": {},
                "warnings": [],
            },
        )
        await session.commit()
        return run.id


async def _seed_visual_observation(
    project_id: int,
    run_id: int,
    *,
    status: str = "observed",
) -> int:
    async with async_session_factory() as session:
        run = await session.get(SourceEvidenceRunRecord, run_id)
        assert run is not None
        resource = (
            await session.execute(
                select(SourceEvidenceResourceRecord).where(
                    SourceEvidenceResourceRecord.project_id == project_id,
                    SourceEvidenceResourceRecord.run_id == run_id,
                    SourceEvidenceResourceRecord.ref == "docx_img_001",
                )
            )
        ).scalar_one()
        observation = SourceEvidenceVisualObservationRecord(
            run_id=run_id,
            project_id=project_id,
            resource_id=resource.id,
            ref=resource.ref,
            position=resource.position,
            filename=resource.filename,
            status=status,
            created_by=run.created_by,
            adopted_by=run.created_by if status == "adopted" else None,
            adopted_at=datetime.datetime.now(datetime.UTC) if status == "adopted" else None,
        )
        session.add(observation)
        await session.flush()
        observation_path = f"visual_evidence/observations/{observation.id}.json"
        source_evidence_storage.write_source_evidence_json(
            project_id,
            run_id,
            observation_path,
            {
                "id": observation.id,
                "run_id": run_id,
                "resource_id": resource.id,
                "ref": resource.ref,
                "position": resource.position,
                "summary": "图中展示活动入口按钮，按钮文案为“参与活动”。",
                "visible_text": "参与活动",
                "confidence": 0.87,
                "limitations": ["只能确认截图可见内容，不能确认配置规则。"],
                "source": {"provider": "openai", "model": "gpt-4o-mini"},
                "created_by": run.created_by,
                "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
            },
        )
        observation.observation_path = observation_path
        resource.status = status
        resource.observation_json = json.dumps(
            {
                "observation_id": observation.id,
                "status": status,
                "summary": "图中展示活动入口按钮，按钮文案为“参与活动”。",
            },
            ensure_ascii=False,
        )
        await session.commit()
        return observation.id


def _source_evidence_snapshot() -> dict[str, Any]:
    return {
        "source_summary": "飞书 docx：活动需求文档",
        "sheet_name": "Source Evidence",
        "columns": ["来源类型", "位置", "标题/页签", "内容", "证据状态"],
        "rows": [
            {
                "row_index": 1,
                "cells": [
                    {"row_index": 1, "column_index": 1, "column_name": "来源类型", "value": "feishu:docx"},
                    {"row_index": 1, "column_index": 2, "column_name": "位置", "value": "docx:line:1"},
                    {"row_index": 1, "column_index": 3, "column_name": "标题/页签", "value": "活动需求文档"},
                    {"row_index": 1, "column_index": 4, "column_name": "内容", "value": "正文规则：每日可领取一次。"},
                    {"row_index": 1, "column_index": 5, "column_name": "证据状态", "value": "text"},
                ],
            },
            {
                "row_index": 2,
                "cells": [
                    {"row_index": 2, "column_index": 1, "column_name": "来源类型", "value": "feishu:docx"},
                    {"row_index": 2, "column_index": 2, "column_name": "位置", "value": "docx:block:img"},
                    {"row_index": 2, "column_index": 3, "column_name": "标题/页签", "value": "活动需求文档"},
                    {"row_index": 2, "column_index": 4, "column_name": "内容", "value": '<image ref="docx_img_001" position="docx:block:img" />'},
                    {"row_index": 2, "column_index": 5, "column_name": "证据状态", "value": "pending_visual"},
                ],
            },
        ],
        "non_empty_cell_count": 10,
        "truncated": False,
        "warnings": [
            {
                "source": "source_evidence",
                "level": "warning",
                "message": "资源 docx_img_001 状态为 download_failed，快照保留文本/表格内容。",
            }
        ],
    }


def _generation_request(run_id: int | None, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "planning_snapshot": _source_evidence_snapshot(),
        "source_evidence_run_id": run_id,
        "reference_ids": [],
        "primary_reference_id": None,
    }
    payload.update(overrides)
    return payload


@pytest.mark.anyio
async def test_valid_source_evidence_run_adds_safe_prompt_context(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """有效 run 会把安全证据上下文加入两阶段 prompt，但不泄露 token/raw。"""
    await _seed_project_ai(test_project_id)
    run_id = await _seed_source_evidence_run(test_project_id)
    prompts: list[str] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompt = kwargs["user_prompt"]
        prompts.append(prompt)
        assert "Source Evidence 读取上下文" in prompt
        assert "读取范围" in prompt
        assert "资源清单摘要" in prompt
        assert "未观察/未采纳" in prompt
        assert "不得把文件名、附近文字或未观察资源写成已确认需求依据" in prompt
        assert "隐藏 Sheet '内部配置' 已排除" in prompt
        assert "docx_img_001" not in prompt
        assert "docx_att_001" not in prompt
        assert "ui.png" not in prompt
        assert "doccn-secret-token" not in prompt
        assert "file-secret-token" not in prompt
        assert "attachment-secret-token" not in prompt
        assert "不得进入 prompt 的原文全文" not in prompt
        if len(prompts) == 1:
            return {"modules": [], "flows": [], "warnings": []}, {}
        return {
            "cases": [
                {
                    "case_id": "TC-001",
                    "module": "奖励",
                    "title": "每日领取一次",
                    "steps": "领取奖励",
                    "expected_results": "每日仅可领取一次",
                    "source_requirement": "正文规则：每日可领取一次。",
                }
            ],
            "warnings": [],
            "requirement_trace": [],
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(run_id),
    )

    assert response.status_code == 200, response.text
    assert len(prompts) == 2
    data = response.json()["data"]
    assert data["cases"][0]["source_requirement"] == "正文规则：每日可领取一次。"
    warning_text = json.dumps(data["warnings"], ensure_ascii=False)
    assert "未观察" in warning_text
    assert "Vision AI" in warning_text
    assert "docx_img_001" not in warning_text


@pytest.mark.anyio
async def test_generated_source_evidence_snapshot_prompt_uses_neutral_resource_summary(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """由 snapshot endpoint 生成的资源行不能把 marker 或敏感字段带进 prompt。"""
    await _seed_project_ai(test_project_id)
    run_id = await _seed_source_evidence_run(test_project_id)
    snapshot_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/snapshot"
    )
    assert snapshot_response.status_code == 200, snapshot_response.text
    snapshot = snapshot_response.json()["data"]
    prompts: list[str] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompt = kwargs["user_prompt"]
        prompts.append(prompt)
        assert "资源 docx_img_001" not in prompt
        assert "docx_img_001" not in prompt
        assert "<image" not in prompt
        assert "doccn-secret-token" not in prompt
        assert "file-secret-token" not in prompt
        assert "不得进入 prompt 的原文全文" not in prompt
        if len(prompts) == 1:
            return {"modules": [], "flows": [], "warnings": []}, {}
        return {"cases": [], "warnings": [], "requirement_trace": []}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(run_id, planning_snapshot=snapshot),
    )

    assert response.status_code == 200, response.text
    assert len(prompts) == 2


@pytest.mark.anyio
async def test_textless_image_run_without_adopted_evidence_rejects_generate(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    run_id = await _seed_textless_image_source_evidence_run(test_project_id)
    snapshot_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/snapshot"
    )
    assert snapshot_response.status_code == 200, snapshot_response.text
    called = False

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        nonlocal called
        called = True
        return {}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(
            run_id,
            planning_snapshot=snapshot_response.json()["data"],
        ),
    )

    assert response.status_code == 409
    assert "采纳视觉证据" in response.text
    assert called is False


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("source_type", "doc_type", "title", "fact_text", "source_marker"),
    [
        ("local_file", "xlsx", "local.xlsx", "本地表格规则：每日限领一次。", "local_file:xlsx"),
        ("svn_file", "xls", "remote.xls", "SVN 表格规则：仅配置期内展示。", "svn_file:xls"),
    ],
)
async def test_local_and_svn_source_evidence_snapshot_can_generate_without_sensitive_leak(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
    source_type: str,
    doc_type: str,
    title: str,
    fact_text: str,
    source_marker: str,
) -> None:
    await _seed_project_ai(test_project_id)
    run_id = await _seed_tabular_source_evidence_run(
        test_project_id,
        source_type=source_type,
        doc_type=doc_type,
        title=title,
        fact_text=fact_text,
    )
    snapshot_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/snapshot"
    )
    assert snapshot_response.status_code == 200, snapshot_response.text
    snapshot = snapshot_response.json()["data"]
    prompts: list[str] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompt = kwargs["user_prompt"]
        prompts.append(prompt)
        assert fact_text in prompt
        assert source_marker in prompt
        assert "<image" not in prompt
        assert "sensitive-token" not in prompt
        assert "file-token-must-not-leak" not in prompt
        assert "svn-password-must-not-leak" not in prompt
        assert "provider-response-must-not-leak" not in prompt
        assert "D:/runtime" not in prompt
        if len(prompts) == 1:
            return {"modules": [], "flows": [], "warnings": []}, {}
        return {"cases": [], "warnings": [], "requirement_trace": []}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(run_id, planning_snapshot=snapshot),
    )

    assert response.status_code == 200, response.text
    assert len(prompts) == 2


@pytest.mark.anyio
async def test_observed_but_not_adopted_visual_evidence_is_not_added_to_prompt(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已观察但未采纳的 observation 不能进入生成事实上下文。"""
    await _seed_project_ai(test_project_id)
    run_id = await _seed_source_evidence_run(test_project_id)
    await _seed_visual_observation(test_project_id, run_id, status="observed")
    prompts: list[str] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompt = kwargs["user_prompt"]
        prompts.append(prompt)
        assert "已采纳视觉证据" in prompt
        assert "图中展示活动入口按钮" not in prompt
        assert "参与活动" not in prompt
        if len(prompts) == 1:
            return {"modules": [], "flows": [], "warnings": []}, {}
        return {"cases": [], "warnings": [], "requirement_trace": []}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(run_id),
    )

    assert response.status_code == 200, response.text
    assert len(prompts) == 2


@pytest.mark.anyio
async def test_adopted_visual_evidence_ids_add_safe_visual_context_to_prompt(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """只有已采纳视觉证据进入两阶段 prompt，且只带安全摘要。"""
    await _seed_project_ai(test_project_id)
    run_id = await _seed_source_evidence_run(test_project_id)
    observation_id = await _seed_visual_observation(test_project_id, run_id, status="adopted")
    prompts: list[str] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompt = kwargs["user_prompt"]
        prompts.append(prompt)
        assert "已采纳视觉证据" in prompt
        assert f"id={observation_id}" in prompt
        assert "ref=docx_img_001" in prompt
        assert "position=docx:block:img" in prompt
        assert "图中展示活动入口按钮" in prompt
        assert "limitations=只能确认截图可见内容，不能确认配置规则。" in prompt
        assert "file-secret-token" not in prompt
        assert "visual_evidence/observations" not in prompt
        if len(prompts) == 1:
            return {"modules": [], "flows": [], "warnings": []}, {}
        return {
            "cases": [
                {
                    "case_id": "TC-001",
                    "title": "结合已采纳视觉证据核对入口",
                    "steps": "查看入口按钮",
                    "expected_results": "入口按钮展示参与活动",
                    "source_requirement": "正文规则：每日可领取一次。",
                    "remarks": "采用 docx_img_001 的已采纳视觉证据，限制：只能确认截图可见内容。",
                }
            ],
            "warnings": [],
            "requirement_trace": [],
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(
            run_id,
            adopted_visual_evidence_ids=[observation_id],
        ),
    )

    assert response.status_code == 200, response.text
    assert len(prompts) == 2


@pytest.mark.anyio
async def test_revoked_or_cross_project_adopted_visual_evidence_is_rejected(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """撤销采纳或跨项目 evidence id 都不能进入生成。"""
    await _seed_project_ai(test_project_id)
    run_id = await _seed_source_evidence_run(test_project_id)
    revoked_id = await _seed_visual_observation(test_project_id, run_id, status="observed")
    foreign_run_id = await _seed_foreign_source_evidence_run()
    async with async_session_factory() as session:
        foreign_run = await session.get(SourceEvidenceRunRecord, foreign_run_id)
        assert foreign_run is not None
        foreign_project_id = foreign_run.project_id
    foreign_observation_id = await _seed_visual_observation(
        foreign_project_id,
        foreign_run_id,
        status="adopted",
    )
    called = False

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        nonlocal called
        called = True
        return {}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    revoked_response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(
            run_id,
            adopted_visual_evidence_ids=[revoked_id],
        ),
    )
    foreign_response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(
            run_id,
            adopted_visual_evidence_ids=[foreign_observation_id],
        ),
    )

    assert revoked_response.status_code == 400
    assert "已采纳" in revoked_response.text
    assert foreign_response.status_code == 404
    assert called is False


@pytest.mark.anyio
async def test_missing_or_other_run_adopted_visual_evidence_is_rejected(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    run_id = await _seed_source_evidence_run(test_project_id)
    other_run_id = await _seed_source_evidence_run(test_project_id)
    other_observation_id = await _seed_visual_observation(
        test_project_id,
        other_run_id,
        status="adopted",
    )
    called = False

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        nonlocal called
        called = True
        return {}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    missing_response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(
            run_id,
            adopted_visual_evidence_ids=[99999999],
        ),
    )
    other_run_response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(
            run_id,
            adopted_visual_evidence_ids=[other_observation_id],
        ),
    )

    assert missing_response.status_code == 404
    assert other_run_response.status_code == 404
    assert called is False


@pytest.mark.anyio
async def test_provider_output_referencing_unadopted_visual_ref_is_rejected(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    run_id = await _seed_source_evidence_run(test_project_id)
    prompts: list[str] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompts.append(kwargs["user_prompt"])
        return {
            "modules": [{"name": "错误引用 docx_img_001"}],
            "flows": [],
            "warnings": [],
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(run_id),
    )

    assert response.status_code == 502
    assert "未采纳" in response.text
    assert len(prompts) == 1
    assert "docx_img_001" not in prompts[0]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "expires_at", "expected_status"),
    [
        ("cleaned", datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1), 409),
        ("ready", datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1), 409),
    ],
)
async def test_expired_or_cleaned_source_evidence_run_rejects_generate(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    expires_at: datetime.datetime,
    expected_status: int,
) -> None:
    """过期或已清理 run 不能进入生成。"""
    await _seed_project_ai(test_project_id)
    run_id = await _seed_source_evidence_run(
        test_project_id,
        status=status,
        expires_at=expires_at,
    )
    called = False

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        nonlocal called
        called = True
        return {}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(run_id),
    )

    assert response.status_code == expected_status
    assert "重新读取来源" in response.text
    assert called is False


@pytest.mark.anyio
async def test_cross_project_source_evidence_run_rejects_generate(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """跨项目 Source Evidence Run 不可被当前项目生成使用。"""
    await _seed_project_ai(test_project_id)
    foreign_run_id = await _seed_foreign_source_evidence_run()
    called = False

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        nonlocal called
        called = True
        return {}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(foreign_run_id),
    )

    assert response.status_code == 404
    assert called is False


@pytest.mark.anyio
async def test_source_evidence_snapshot_must_match_run_summary(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_id 不能绑定到其他来源的 planning_snapshot。"""
    await _seed_project_ai(test_project_id)
    run_id = await _seed_source_evidence_run(test_project_id)
    called = False

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        nonlocal called
        called = True
        return {}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )
    snapshot = _source_evidence_snapshot()
    snapshot["source_summary"] = "上传 Excel：planning.xlsx"

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(run_id, planning_snapshot=snapshot),
    )

    assert response.status_code == 400
    assert "Source Evidence Snapshot" in response.text
    assert called is False
