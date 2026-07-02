"""Source Evidence Snapshot 转换测试。"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from backend.app.database import async_session_factory
from backend.app.models import SourceEvidenceResourceRecord, SourceEvidenceRunRecord
from backend.app.test_cases import source_evidence, source_evidence_storage
from backend.app.test_cases.schemas import (
    GenerationWarning,
    ParsedFeishuSource,
    ParsedSource,
    ParsedSourceCell,
    ParsedSourceResource,
    ParsedSourceUnit,
    PlanningSnapshotBriefRequest,
    PlanningSnapshotResponse,
    TestCaseGenerationRequest,
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


def _parsed_sheet_source() -> ParsedFeishuSource:
    return ParsedFeishuSource(
        title="富表格",
        doc_type="sheets",
        token="shtcnabc123",
        url="https://demo.feishu.cn/sheets/shtcnabc123",
        markdown="# Source: 富表格\n",
        source_units=[
            ParsedSourceUnit(
                unit_id="sheet_gid001",
                kind="sheet",
                title="需求",
                cells=[
                    ParsedSourceCell(coord="A1", row=1, col=1, text="模块"),
                    ParsedSourceCell(coord="B2", row=2, col=2, text="入口规则"),
                ],
                metadata={"sheet_id": "gid001"},
            )
        ],
        resources=[
            ParsedSourceResource(
                ref="img_需求_B2_001",
                type="image",
                source_id="img_token",
                position="需求!B2",
                filename="ui.png",
                file_token="img_token",
                mime_type="image/png",
            )
        ],
        raw_manifest={"doc_type": "sheets"},
        warnings=[GenerationWarning(source="feishu", message="隐藏 Sheet 已排除。")],
    )


def _cell_values(snapshot: dict) -> list[str]:
    return [
        cell["value"]
        for row in snapshot["rows"]
        for cell in row["cells"]
    ]


async def _seed_generic_source_evidence_run(
    project_id: int,
    *,
    source_type: str,
    doc_type: str,
    title: str,
    parsed_source: dict,
    manifest: dict | None = None,
    resources: list[dict] | None = None,
) -> int:
    async with async_session_factory() as session:
        record = SourceEvidenceRunRecord(
            project_id=project_id,
            source_type=source_type,
            source_identifier=f"sha256:{source_type}-{doc_type}",
            source_title=title,
            status="ready",
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
            raw_manifest_json=json.dumps(manifest or {"warnings": []}, ensure_ascii=False),
        )
        session.add(record)
        await session.flush()
        source_evidence_storage.ensure_source_evidence_subdirs(
            project_id=project_id,
            run_id=record.id,
        )
        for resource in resources or []:
            session.add(
                SourceEvidenceResourceRecord(
                    run_id=record.id,
                    project_id=project_id,
                    ref=resource["ref"],
                    resource_type=resource.get("type", "image"),
                    position=resource.get("position", ""),
                    filename=resource.get("filename", ""),
                    file_token=resource.get("file_token", "secret-file-token"),
                    status=resource.get("status", "unobserved"),
                    download_status=resource.get("download_status", "downloaded"),
                    local_path=resource.get("local_path", "D:/secret/source-evidence/ui.png"),
                    mime_type=resource.get("mime_type", "image/png"),
                    metadata_json=json.dumps(
                        resource.get(
                            "metadata",
                            {"provider_response": "provider raw must not leak"},
                        ),
                        ensure_ascii=False,
                    ),
                )
            )
        source_evidence_storage.write_source_evidence_json(
            project_id,
            record.id,
            "raw/parsed_source.json",
            parsed_source,
        )
        await session.commit()
        return record.id


@pytest.mark.anyio
async def test_source_evidence_snapshot_is_planning_snapshot_compatible(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """snapshot 接口输出固定兼容列，可被现有 brief/generate schema 接收。"""

    async def _read_source(*_args, **_kwargs) -> ParsedFeishuSource:
        return _parsed_sheet_source()

    async def _download_fail(*_args, **_kwargs) -> str:
        raise RuntimeError("download failed")

    monkeypatch.setattr(source_evidence, "read_feishu_parsed_source", _read_source, raising=False)
    monkeypatch.setattr(
        source_evidence,
        "download_source_evidence_resource_file",
        _download_fail,
        raising=False,
    )

    create_response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs",
        json={
            "source_type": "feishu",
            "source_url": "https://demo.feishu.cn/sheets/shtcnabc123",
        },
    )
    assert create_response.status_code == 200
    run_id = create_response.json()["data"]["id"]
    assert create_response.json()["data"]["source_identifier"].startswith("sha256:")
    assert create_response.json()["data"]["source_summary"] == "飞书 sheets：富表格"

    snapshot_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/snapshot"
    )

    assert snapshot_response.status_code == 200
    snapshot = PlanningSnapshotResponse.model_validate(snapshot_response.json()["data"])
    assert snapshot.source_summary == "飞书 sheets：富表格"
    assert snapshot.columns == ["来源类型", "位置", "标题/页签", "内容", "证据状态"]
    assert any(
        cell.column_name == "证据状态" and cell.value == "pending_visual"
        for row in snapshot.rows
        for cell in row.cells
    )
    PlanningSnapshotBriefRequest(planning_snapshot=snapshot)
    TestCaseGenerationRequest(planning_snapshot=snapshot)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "expires_at"),
    [
        ("cleaned", datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)),
        ("ready", datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1)),
    ],
)
async def test_expired_or_cleaned_run_rejects_snapshot(
    auth_client: AsyncClient,
    test_project_id: int,
    status: str,
    expires_at: datetime.datetime,
) -> None:
    """过期或已清理 run 不能再转换 snapshot。"""
    async with async_session_factory() as session:
        record = SourceEvidenceRunRecord(
            project_id=test_project_id,
            source_type="feishu",
            source_identifier="doccnabc123",
            source_title="已失效证据",
            status=status,
            expires_at=expires_at,
            raw_manifest_json=json.dumps({"files": {}}, ensure_ascii=False),
        )
        session.add(record)
        await session.commit()
        run_id = record.id

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/snapshot"
    )

    assert response.status_code == 409
    assert "重新读取来源" in response.json()["detail"]


@pytest.mark.anyio
async def test_docx_snapshot_uses_neutral_resource_rows_without_marker_content(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    parsed = ParsedSource(
        source_type="feishu",
        title="活动需求文档",
        doc_type="docx",
        token="doccn-secret-token",
        url="https://demo.feishu.cn/docx/doccn-secret-token",
        markdown=(
            "正文规则：每日可领取一次。\n"
            '<image ref="docx_img_001" position="docx:block:img" />\n'
        ),
        source_units=[
            ParsedSourceUnit(
                unit_id="docx_doccn_secret",
                kind="docx",
                title="活动需求文档",
            )
        ],
        raw_manifest={
            "raw_content": "raw provider response must not leak",
            "token": "doccn-secret-token",
        },
    ).model_dump(mode="json")
    run_id = await _seed_generic_source_evidence_run(
        test_project_id,
        source_type="feishu",
        doc_type="docx",
        title="活动需求文档",
        parsed_source=parsed,
        resources=[
            {
                "ref": "docx_img_001",
                "type": "image",
                "position": "docx:block:img",
                "filename": "ui.png",
                "download_status": "downloaded",
                "local_path": "D:/runtime/source-evidence/secret/ui.png",
            }
        ],
    )

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/snapshot"
    )

    assert response.status_code == 200, response.text
    snapshot_text = json.dumps(response.json()["data"], ensure_ascii=False)
    values = _cell_values(response.json()["data"])
    assert "正文规则：每日可领取一次。" in values
    assert any("资源 docx_img_001" in value for value in values)
    assert "<image" not in snapshot_text
    assert "doccn-secret-token" not in snapshot_text
    assert "raw provider response" not in snapshot_text
    assert "D:/runtime" not in snapshot_text


@pytest.mark.anyio
async def test_svn_xls_snapshot_uses_doc_type_source_and_hides_sensitive_payload(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    run_id = await _seed_generic_source_evidence_run(
        test_project_id,
        source_type="svn_file",
        doc_type="xls",
        title="source.xls",
        parsed_source=ParsedSource(
            source_type="svn_file",
            title="source.xls",
            doc_type="xls",
            token="sha256:file",
            url="https://samosvn/game/design/source.xls",
            markdown="",
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
            raw_manifest={
                "svn_password": "secret_password_should_not_leak",
                "local_path": "D:/runtime/source-evidence/cache/source.xls",
            },
        ).model_dump(mode="json"),
        manifest={
            "svn": {
                "url": "https://samosvn/game/design/source.xls",
                "root_alias": "design_docs",
            },
            "warnings": [],
        },
    )

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/snapshot"
    )

    assert response.status_code == 200, response.text
    snapshot = response.json()["data"]
    assert snapshot["source_summary"] == "svn_file：source.xls"
    values = _cell_values(snapshot)
    assert "SVN 活动" in values
    assert "svn_file:xls" in values
    snapshot_text = json.dumps(snapshot, ensure_ascii=False)
    assert "secret_password_should_not_leak" not in snapshot_text
    assert "D:/runtime" not in snapshot_text


@pytest.mark.anyio
async def test_local_xls_conversion_failure_snapshot_keeps_text_and_warning(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    warning_message = ".xls 图片转换失败：未配置 SOURCE_EVIDENCE_SOFFICE_EXECUTABLE。"
    run_id = await _seed_generic_source_evidence_run(
        test_project_id,
        source_type="local_file",
        doc_type="xls",
        title="legacy.xls",
        parsed_source=ParsedSource(
            source_type="local_file",
            title="legacy.xls",
            doc_type="xls",
            token="sha256:legacy",
            url="",
            markdown="",
            source_units=[
                ParsedSourceUnit(
                    unit_id="xls_s001",
                    kind="sheet",
                    title="旧表",
                    cells=[
                        ParsedSourceCell(coord="A1", row=1, col=1, text="本地 XLS 文本"),
                    ],
                )
            ],
            raw_manifest={"local_path": "D:/runtime/source-evidence/raw/legacy.xls"},
            warnings=[
                GenerationWarning(
                    source="local_file",
                    level="warning",
                    message=warning_message,
                )
            ],
        ).model_dump(mode="json"),
    )

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/snapshot"
    )

    assert response.status_code == 200, response.text
    snapshot = response.json()["data"]
    values = _cell_values(snapshot)
    assert "本地 XLS 文本" in values
    assert "local_file:xls" in values
    assert any(warning_message in warning["message"] for warning in snapshot["warnings"])
    assert "D:/runtime" not in json.dumps(snapshot, ensure_ascii=False)


@pytest.mark.anyio
async def test_textless_image_snapshot_does_not_fabricate_requirement_text(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    run_id = await _seed_generic_source_evidence_run(
        test_project_id,
        source_type="local_file",
        doc_type="image",
        title="ui.png",
        parsed_source=ParsedSource(
            source_type="local_file",
            title="ui.png",
            doc_type="image",
            token="sha256:image",
            url="",
            markdown='<image ref="local_img_001" position="local:image=1" />',
            source_units=[],
            raw_manifest={"provider_response": "must not leak"},
            warnings=[
                GenerationWarning(
                    source="local_file",
                    level="warning",
                    message="独立图片缺少文本主体；生成前需要先观察并采纳视觉证据。",
                )
            ],
        ).model_dump(mode="json"),
        resources=[
            {
                "ref": "local_img_001",
                "type": "image",
                "position": "local:image=1",
                "filename": "local_img_001.png",
            }
        ],
    )

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/snapshot"
    )

    assert response.status_code == 200, response.text
    snapshot = response.json()["data"]
    values = _cell_values(snapshot)
    assert any("无文本主体" in value for value in values)
    assert not any(value == "text" or value == "table" for value in values)
    snapshot_text = json.dumps(snapshot, ensure_ascii=False)
    assert "<image" not in snapshot_text
    assert "provider_response" not in snapshot_text


@pytest.mark.anyio
async def test_snapshot_warning_merge_deduplicates_by_source_level_and_message(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    shared_message = "同名 warning 来自不同来源。"
    duplicate = {
        "source": "reader",
        "level": "warning",
        "message": shared_message,
    }
    run_id = await _seed_generic_source_evidence_run(
        test_project_id,
        source_type="local_file",
        doc_type="xls",
        title="source.xls",
        parsed_source=ParsedSource(
            source_type="local_file",
            title="source.xls",
            doc_type="xls",
            token="sha256:xls",
            url="",
            markdown="",
            source_units=[],
            warnings=[
                GenerationWarning(source="reader", level="warning", message=shared_message),
                GenerationWarning(source="reader", level="warning", message=shared_message),
            ],
        ).model_dump(mode="json"),
        manifest={
            "warnings": [
                duplicate,
                duplicate,
                {
                    "source": "manifest",
                    "level": "warning",
                    "message": shared_message,
                },
            ]
        },
    )

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/snapshot"
    )

    assert response.status_code == 200, response.text
    warnings = response.json()["data"]["warnings"]
    matching = [warning for warning in warnings if warning["message"] == shared_message]
    assert matching == [
        {"source": "reader", "level": "warning", "message": shared_message},
        {"source": "manifest", "level": "warning", "message": shared_message},
    ]
