"""Source Evidence Run API 闭环测试。"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from backend.app.database import async_session_factory
from backend.app.integrations.feishu_client import (
    FEISHU_DOCUMENT_PERMISSION_DENIED,
    FeishuClientError,
)
from backend.app.models import (
    FeishuBotConfigRecord,
    SourceEvidenceAuthorizationRecord,
    SourceEvidenceRunRecord,
)
from backend.app.security.crypto import encrypt_secret
from backend.app.test_cases import source_evidence, source_evidence_storage
from backend.app.test_cases import source_evidence_authorization as authz
from backend.app.test_cases.schemas import (
    GenerationWarning,
    ParsedFeishuSource,
    ParsedSourceCell,
    ParsedSourceResource,
    ParsedSourceUnit,
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


async def _seed_bot_config(project_id: int) -> None:
    async with async_session_factory() as session:
        session.add(
            FeishuBotConfigRecord(
                project_id=project_id,
                app_id="cli_source_evidence",
                app_secret_cipher=encrypt_secret("secret_unit"),
                default_chat_id="oc_default",
            )
        )
        await session.commit()


async def _seed_authorized_record(
    project_id: int,
    *,
    source_token: str = "doccnabc123",
    status: str = authz.STATUS_AUTHORIZED,
    expires_delta: datetime.timedelta = datetime.timedelta(days=90),
) -> int:
    async with async_session_factory() as session:
        record = SourceEvidenceAuthorizationRecord(
            project_id=project_id,
            app_id="cli_source_evidence",
            doc_type="docx",
            permission="edit",
            source_token_hash=authz.hash_source_token(source_token),
            source_token_alias_hashes_json="[]",
            status=status,
            target_mode=authz.TARGET_DEFAULT_CHAT,
            sent_targets_count=1,
            failed_targets_count=0,
            authorized_by_open_id="ou_owner",
            authorized_at=datetime.datetime.now(datetime.UTC),
            expires_at=datetime.datetime.now(datetime.UTC) + expires_delta,
        )
        session.add(record)
        await session.commit()
        return record.id


def _parsed_docx_source() -> ParsedFeishuSource:
    return ParsedFeishuSource(
        title="活动需求文档",
        doc_type="docx",
        token="doccnabc123",
        url="https://demo.feishu.cn/docx/doccnabc123",
        markdown=(
            "# Source: 活动需求文档\n\n"
            "正文第一段\n"
            '<image ref="docx_img_001" position="docx:block:img" />\n'
            '<attachment ref="docx_att_001" position="docx:block:file" />\n'
        ),
        source_units=[
            ParsedSourceUnit(
                unit_id="docx_doccnabc123",
                kind="docx",
                title="活动需求文档",
                metadata={"block_count": 3},
            )
        ],
        resources=[
            ParsedSourceResource(
                ref="docx_img_001",
                type="image",
                source_id="img_token",
                position="docx:block:img",
                filename="ui.png",
                file_token="img_token",
                mime_type="image/png",
            ),
            ParsedSourceResource(
                ref="docx_att_001",
                type="attachment",
                source_id="att_token",
                position="docx:block:file",
                filename="spec.pdf",
                file_token="att_token",
                mime_type="application/pdf",
            ),
        ],
        raw_manifest={"doc_type": "docx", "docx_block_count": 3},
        warnings=[
            GenerationWarning(source="feishu", level="warning", message="图片待观察。")
        ],
    )


def _parsed_multi_sheet_source() -> ParsedFeishuSource:
    return ParsedFeishuSource(
        title="活动多页表",
        doc_type="sheets",
        token="shtcnmulti123",
        url="https://demo.feishu.cn/sheets/shtcnmulti123",
        markdown="# Source: 活动多页表\n",
        source_units=[
            ParsedSourceUnit(
                unit_id="sheet_gid001",
                kind="sheet",
                title="第一页",
                cells=[
                    ParsedSourceCell(coord="A1", row=1, col=1, text="模块"),
                    ParsedSourceCell(coord="B2", row=2, col=2, text="入口规则"),
                ],
                metadata={"sheet_id": "gid001", "resource_count": 2},
            ),
            ParsedSourceUnit(
                unit_id="sheet_gid002",
                kind="sheet",
                title="第二页",
                cells=[
                    ParsedSourceCell(coord="A1", row=1, col=1, text="奖励"),
                ],
                metadata={"sheet_id": "gid002", "resource_count": 1},
            ),
        ],
        resources=[],
        raw_manifest={"doc_type": "sheets"},
        warnings=[],
    )


@pytest.mark.anyio
async def test_create_docx_source_evidence_run_and_read_resources(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """项目成员创建 docx run 后可读取摘要和资源清单。"""

    async def _read_source(*_args, **_kwargs) -> ParsedFeishuSource:
        return _parsed_docx_source()

    async def _download_fail(*_args, **_kwargs) -> str:
        raise RuntimeError("download failed")

    monkeypatch.setattr(source_evidence, "read_feishu_parsed_source", _read_source, raising=False)
    monkeypatch.setattr(
        source_evidence,
        "download_source_evidence_resource_file",
        _download_fail,
        raising=False,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs",
        json={
            "source_type": "feishu",
            "source_url": "https://demo.feishu.cn/docx/doccnabc123",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ready"
    assert data["source_summary"] == "飞书 docx：活动需求文档"
    assert data["resource_count"] == 2
    assert data["expires_at"]
    assert data["source_identifier"].startswith("sha256:")
    assert "doccnabc123" not in data["source_identifier"]
    assert any("download failed" in item["message"] for item in data["warnings"])
    assert data["sheet_options"] == []

    run_id = data["id"]
    source_meta = source_evidence_storage.read_source_evidence_json(
        test_project_id,
        run_id,
        "source.meta.json",
    )
    manifest = source_evidence_storage.read_source_evidence_json(
        test_project_id,
        run_id,
        "manifest.json",
    )
    async with async_session_factory() as session:
        run = await session.get(SourceEvidenceRunRecord, run_id)
    assert run is not None
    safe_payload_text = json.dumps(
        {
            "source_meta": source_meta,
            "manifest": manifest,
            "raw_manifest_json": json.loads(run.raw_manifest_json),
        },
        ensure_ascii=False,
    )
    assert "doccnabc123" not in safe_payload_text
    assert "https://demo.feishu.cn/docx/doccnabc123" not in safe_payload_text
    assert source_meta["source_identifier"].startswith("sha256:")
    assert manifest["source_identifier"].startswith("sha256:")

    run_response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}"
    )
    assert run_response.status_code == 200
    assert run_response.json()["data"]["resource_count"] == 2

    resources_response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/resources"
    )
    assert resources_response.status_code == 200
    resources = resources_response.json()["data"]["items"]
    assert [
        {
            "ref": item["ref"],
            "type": item["type"],
            "position": item["position"],
            "filename": item["filename"],
            "download_status": item["download_status"],
            "adoption_status": item["adoption_status"],
        }
        for item in resources
    ] == [
        {
            "ref": "docx_img_001",
            "type": "image",
            "position": "docx:block:img",
            "filename": "ui.png",
            "download_status": "download_failed",
            "adoption_status": "unobserved",
        },
        {
            "ref": "docx_att_001",
            "type": "attachment",
            "position": "docx:block:file",
            "filename": "spec.pdf",
            "download_status": "download_failed",
            "adoption_status": "unobserved",
        },
    ]

    snapshot_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/snapshot"
    )
    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["data"]["non_empty_cell_count"] > 0


@pytest.mark.anyio
async def test_create_sheet_source_evidence_run_returns_sheet_options(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """多 Sheet parsed source 的 run response 暴露安全 Sheet 摘要。"""

    async def _read_source(*_args, **_kwargs) -> ParsedFeishuSource:
        return _parsed_multi_sheet_source()

    monkeypatch.setattr(source_evidence, "read_feishu_parsed_source", _read_source, raising=False)

    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs",
        json={
            "source_type": "feishu",
            "source_url": "https://demo.feishu.cn/sheets/shtcnmulti123",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["sheet_options"] == [
        {
            "name": "第一页",
            "kind": "sheet",
            "cell_count": 2,
            "resource_count": 2,
            "is_default": True,
        },
        {
            "name": "第二页",
            "kind": "sheet",
            "cell_count": 1,
            "resource_count": 1,
            "is_default": False,
        },
    ]


@pytest.mark.anyio
async def test_pending_permission_run_can_retry(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pending_permission run 可在权限补齐后 retry 并变为 ready。"""
    calls = {"count": 0}

    async def _read_source(*_args, **_kwargs) -> ParsedFeishuSource:
        calls["count"] += 1
        if calls["count"] == 1:
            raise FeishuClientError(
                FEISHU_DOCUMENT_PERMISSION_DENIED,
                "飞书应用无权访问该文档。",
            )
        return _parsed_docx_source()

    async def _download_ok(*_args, **_kwargs) -> str:
        return "images/docx_img_001.bin"

    monkeypatch.setattr(source_evidence, "read_feishu_parsed_source", _read_source, raising=False)
    monkeypatch.setattr(
        source_evidence,
        "download_source_evidence_resource_file",
        _download_ok,
        raising=False,
    )

    create_response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs",
        json={
            "source_type": "feishu",
            "source_url": "https://demo.feishu.cn/docx/doccnabc123",
        },
    )
    assert create_response.status_code == 200
    assert create_response.json()["data"]["status"] == "pending_permission"

    run_id = create_response.json()["data"]["id"]
    await _seed_bot_config(test_project_id)
    await _seed_authorized_record(test_project_id)
    retry_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/retry"
    )

    assert retry_response.status_code == 200
    assert retry_response.json()["data"]["status"] == "ready"
    assert retry_response.json()["data"]["resource_count"] == 2


@pytest.mark.anyio
async def test_svn_file_create_requires_source_evidence_root_and_rolls_back_run(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """svn_file 创建走 V2 dispatcher；缺 Source Evidence Root 时不留下不可用 run。"""
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
            "source_url": "https://samosvn/design/source.xlsx",
        },
    )

    assert response.status_code == 400
    assert "Source Evidence SVN Root" in response.json()["detail"]
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
async def test_local_file_upload_endpoint_rejects_invalid_workbook_without_persisting_run(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """local_file 上传入口已注册；无法解析的 workbook 不留下不可用 run。"""
    async with async_session_factory() as session:
        before_count = (
            await session.execute(
                select(func.count(SourceEvidenceRunRecord.id)).where(
                    SourceEvidenceRunRecord.project_id == test_project_id
                )
            )
        ).scalar_one()

    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs/upload",
        files={
            "file": (
                "source.xlsx",
                b"not-a-real-workbook-yet",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 400
    assert "读取本地上传文件失败" in response.json()["detail"]
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
async def test_retry_uses_source_evidence_dispatcher(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """retry 不再直接调用 Feishu 私有 reader，而是统一走 dispatcher。"""
    async with async_session_factory() as session:
        run = SourceEvidenceRunRecord(
            project_id=test_project_id,
            source_type="feishu",
            source_url="https://demo.feishu.cn/docx/doccnabc123",
            source_identifier="doccnabc123",
            source_title="待重试证据",
            status="failed",
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
            raw_manifest_json=json.dumps({"warnings": []}, ensure_ascii=False),
        )
        session.add(run)
        await session.commit()
        run_id = run.id

    calls = {"dispatcher": 0}

    async def _dispatcher(_db, run: SourceEvidenceRunRecord) -> None:
        calls["dispatcher"] += 1
        run.status = "ready"
        run.error_summary = ""
        run.source_identifier = "sha256:retry"
        run.source_title = "重试后证据"
        run.raw_manifest_json = json.dumps({"warnings": []}, ensure_ascii=False)

    async def _fail_private_reader(*_args, **_kwargs) -> None:
        raise AssertionError("retry path must use dispatcher")

    monkeypatch.setattr(
        source_evidence,
        "read_and_persist_source_evidence_run",
        _dispatcher,
        raising=False,
    )
    monkeypatch.setattr(
        source_evidence,
        "_read_and_persist_feishu_source",
        _fail_private_reader,
        raising=False,
    )

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/retry"
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ready"
    assert calls["dispatcher"] == 1


@pytest.mark.anyio
async def test_local_file_json_create_is_rejected_by_schema(
    auth_client: AsyncClient,
) -> None:
    """local_file 不属于 JSON 创建契约，只能走 upload endpoint。"""
    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs",
        json={"source_type": "local_file", "source_url": "source.xlsx"},
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_initial_permission_failure_does_not_auto_send_authorization_card(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首次读取权限不足只进入 pending_permission，不自动发送授权卡。"""
    await _seed_bot_config(test_project_id)

    async def _read_source(*_args, **_kwargs) -> ParsedFeishuSource:
        raise FeishuClientError(
            FEISHU_DOCUMENT_PERMISSION_DENIED,
            "飞书应用无权访问该文档。",
        )

    async def _fail_if_send(*_args, **_kwargs):
        raise AssertionError("read path must not send authorization card")

    monkeypatch.setattr(source_evidence, "read_feishu_parsed_source", _read_source, raising=False)
    monkeypatch.setattr(authz, "send_card_to_open_id", _fail_if_send)
    monkeypatch.setattr(authz, "send_card_to_chat", _fail_if_send)

    response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs",
        json={
            "source_type": "feishu",
            "source_url": "https://demo.feishu.cn/docx/doccnabc123",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending_permission"
    async with async_session_factory() as session:
        total = (
            await session.execute(
                select(func.count(SourceEvidenceAuthorizationRecord.id))
            )
        ).scalar_one()
    assert total == 0


@pytest.mark.anyio
async def test_retry_with_authorized_record_still_does_not_auto_resend_on_failure(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已有授权但读取仍失败时，retry 保持权限态且不自动重发卡。"""
    calls = {"count": 0}

    async def _read_source(*_args, **_kwargs) -> ParsedFeishuSource:
        calls["count"] += 1
        raise FeishuClientError(
            FEISHU_DOCUMENT_PERMISSION_DENIED,
            "飞书应用无权访问该文档。",
        )

    async def _fail_if_send(*_args, **_kwargs):
        raise AssertionError("retry path must not send authorization card")

    monkeypatch.setattr(source_evidence, "read_feishu_parsed_source", _read_source, raising=False)
    monkeypatch.setattr(authz, "send_card_to_open_id", _fail_if_send)
    monkeypatch.setattr(authz, "send_card_to_chat", _fail_if_send)

    create_response = await auth_client.post(
        "/api/v1/test-cases/source-evidence-runs",
        json={
            "source_type": "feishu",
            "source_url": "https://demo.feishu.cn/docx/doccnabc123",
        },
    )
    assert create_response.status_code == 200
    assert create_response.json()["data"]["status"] == "pending_permission"
    await _seed_bot_config(test_project_id)
    await _seed_authorized_record(test_project_id)

    run_id = create_response.json()["data"]["id"]
    retry_response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/retry"
    )

    assert retry_response.status_code == 200
    data = retry_response.json()["data"]
    assert data["status"] == "pending_permission"
    assert any(
        "不会自动重新发送授权卡" in item["message"]
        for item in data["warnings"]
    )
    async with async_session_factory() as session:
        sent_count = (
            await session.execute(
                select(func.count(SourceEvidenceAuthorizationRecord.id)).where(
                    SourceEvidenceAuthorizationRecord.status
                    == authz.STATUS_AUTHORIZATION_SENT
                )
            )
        ).scalar_one()
    assert sent_count == 0
    assert calls["count"] == 2


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["cleaned", "expired"])
async def test_expired_or_cleaned_run_rejects_retry(
    auth_client: AsyncClient,
    test_project_id: int,
    status: str,
) -> None:
    """expired/cleaned run 不允许 retry 继续使用旧 source token。"""
    async with async_session_factory() as session:
        run = SourceEvidenceRunRecord(
            project_id=test_project_id,
            source_type="feishu",
            source_url="https://demo.feishu.cn/docx/doccnabc123",
            source_token="doccnabc123",
            source_identifier="doccnabc123",
            source_title="已失效证据",
            status=status,
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(run)
        await session.commit()
        run_id = run.id

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/retry"
    )

    assert response.status_code == 409
