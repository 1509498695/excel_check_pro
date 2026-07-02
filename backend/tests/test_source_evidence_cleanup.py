"""Source Evidence TTL 清理和最小审计测试。"""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import AsyncClient

from backend.app.database import async_session_factory
from backend.app.models import (
    Project,
    SourceEvidenceResourceRecord,
    SourceEvidenceRunRecord,
    SourceEvidenceVisualObservationRecord,
    User,
)
from backend.app.test_cases import source_evidence_cleanup, source_evidence_storage


@pytest.fixture(autouse=True)
def _source_evidence_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    root = tmp_path / "runtime" / "source-evidence"
    monkeypatch.setattr(
        source_evidence_storage,
        "settings",
        SimpleNamespace(source_evidence_dir=root),
    )
    return root


async def _seed_sensitive_run(
    *,
    project_id: int | None = None,
    expires_at: datetime.datetime | None = None,
) -> tuple[int, int, int, int]:
    now = datetime.datetime.now(datetime.UTC)
    async with async_session_factory() as session:
        if project_id is None:
            project = Project(name=f"cleanup-{uuid4().hex[:8]}", description="")
            session.add(project)
            await session.flush()
            project_id = project.id
        user = User(
            username=f"cleanup-user-{uuid4().hex[:8]}",
            hashed_password="x",
            is_super_admin=False,
            primary_project_id=project_id,
        )
        session.add(user)
        await session.flush()

        run = SourceEvidenceRunRecord(
            project_id=project_id,
            source_type="feishu",
            source_url="https://demo.feishu.cn/docx/doccn-secret-token",
            source_token="doccn-secret-token",
            source_identifier="doccn-secret-token",
            source_title="清理需求",
            status="ready",
            storage_path="D:/outside/should-not-drive-cleanup",
            error_summary="下载失败：tenant_access_token=secret",
            raw_manifest_json=json.dumps(
                {
                    "raw_content": "不能保留的需求原文",
                    "prompt": "不能保留的 prompt",
                    "provider_response": "不能保留的 provider response",
                    "warnings": [{"source": "x", "level": "warning", "message": "最小错误"}],
                },
                ensure_ascii=False,
            ),
            created_by=user.id,
            expires_at=expires_at or now - datetime.timedelta(seconds=1),
        )
        session.add(run)
        await session.flush()
        resource = SourceEvidenceResourceRecord(
            run_id=run.id,
            project_id=project_id,
            ref="docx_img_001",
            resource_type="image",
            position="docx:block:1",
            filename="ui.png",
            file_token="file-secret-token",
            status="adopted",
            download_status="downloaded",
            local_path="images/ui.png",
            mime_type="image/png",
            observation_json=json.dumps(
                {
                    "summary": "不能保留的 observation 摘要",
                    "visible_text": "不能保留的可见文字",
                    "observation_path": "visual_evidence/observations/1.json",
                },
                ensure_ascii=False,
            ),
            visual_packet_path="visual_evidence/visual_candidates.json",
            metadata_json=json.dumps(
                {"nearby_text": "不能保留的附近文本", "visual_packet": {"optimized_image": "x"}},
                ensure_ascii=False,
            ),
        )
        session.add(resource)
        await session.flush()
        observation = SourceEvidenceVisualObservationRecord(
            run_id=run.id,
            project_id=project_id,
            resource_id=resource.id,
            ref=resource.ref,
            position=resource.position,
            filename=resource.filename,
            status="adopted",
            observation_path="visual_evidence/observations/1.json",
            created_by=user.id,
            adopted_by=user.id,
            adopted_at=now,
        )
        session.add(observation)
        await session.commit()

        run_dir = source_evidence_storage.ensure_source_evidence_run_dir(
            project_id=project_id,
            run_id=run.id,
        )
        (run_dir / "source.md").write_text("不能保留的 source.md 原文", encoding="utf-8")
        (run_dir / "raw").mkdir(parents=True, exist_ok=True)
        (run_dir / "raw" / "parsed_source.json").write_text(
            json.dumps({"raw": "不能保留的 raw"}),
            encoding="utf-8",
        )
        (run_dir / "images").mkdir(parents=True, exist_ok=True)
        (run_dir / "images" / "ui.png").write_bytes(b"image")
        (run_dir / "attachments").mkdir(parents=True, exist_ok=True)
        (run_dir / "attachments" / "spec.pdf").write_bytes(b"pdf")
        (run_dir / "visual_evidence" / "observations").mkdir(parents=True, exist_ok=True)
        (run_dir / "visual_evidence" / "visual_candidates.json").write_text("[]", encoding="utf-8")
        (run_dir / "visual_evidence" / "adopted_visual_evidence.json").write_text(
            json.dumps({"items": [{"summary": "不能保留的 adopted 详情"}]}),
            encoding="utf-8",
        )
        (run_dir / "visual_evidence" / "observations" / "1.json").write_text(
            json.dumps({"summary": "不能保留的 observation 详情"}),
            encoding="utf-8",
        )

        return project_id, run.id, resource.id, observation.id


@pytest.mark.anyio
async def test_cleanup_deletes_sensitive_files_and_keeps_minimal_audit(test_db) -> None:
    """TTL 清理删除敏感文件，DB 只保留最小审计元数据。"""
    project_id, run_id, resource_id, observation_id = await _seed_sensitive_run()

    async with async_session_factory() as session:
        summary = await source_evidence_cleanup.cleanup_source_evidence_run(
            session,
            project_id=project_id,
            run_id=run_id,
            cleaned_by=99,
        )
        await session.commit()

    run_dir = source_evidence_storage.run_source_evidence_dir(
        project_id=project_id,
        run_id=run_id,
    )
    assert run_dir.exists()
    assert list(run_dir.iterdir()) == []

    async with async_session_factory() as session:
        run = await session.get(SourceEvidenceRunRecord, run_id)
        resource = await session.get(SourceEvidenceResourceRecord, resource_id)
        observation = await session.get(SourceEvidenceVisualObservationRecord, observation_id)

        assert run is not None and resource is not None and observation is not None
        assert run.status == "cleaned"
        assert run.source_url == ""
        assert run.source_token == ""
        assert run.source_identifier.startswith("sha256:")
        assert run.storage_path == ""
        assert run.raw_manifest_json == "{}"
        assert run.error_summary == ""
        assert run.cleaned_by == 99
        assert run.cleaned_at is not None

        assert resource.file_token == ""
        assert resource.local_path == ""
        assert resource.observation_json == ""
        assert resource.visual_packet_path == ""
        assert resource.metadata_json == "{}"
        assert resource.status == "expired"
        assert resource.cleaned_at is not None

        assert observation.status == "cleaned"
        assert observation.observation_path == ""
        assert observation.cleaned_at is not None

        audit = json.loads(run.minimal_audit_json)

    assert summary == audit
    audit_text = json.dumps(audit, ensure_ascii=False)
    assert audit["run_id"] == run_id
    assert audit["project_id"] == project_id
    assert audit["source_identifier"] == run.source_identifier
    assert audit["status_before"] == "ready"
    assert audit["status_after"] == "cleaned"
    assert audit["resources"][0]["filename"] == "ui.png"
    assert audit["resources"][0]["download_status"] == "downloaded"
    assert "tenant_access_token" not in audit_text
    for forbidden in (
        "https://demo.feishu.cn",
        "doccn-secret-token",
        "file-secret-token",
        "D:/outside",
        "不能保留",
        "prompt",
        "provider_response",
        "observation_path",
        "visual_candidates",
    ):
        assert forbidden not in audit_text


@pytest.mark.anyio
async def test_cleanup_deletes_v2_local_xls_svn_and_visual_artifacts(
    test_db,
    tmp_path: Path,
) -> None:
    """TTL 清理覆盖 V2 local/xls/SVN/visual 目录，但不碰 run 外全局缓存。"""
    project_id, run_id, _resource_id, _observation_id = await _seed_sensitive_run()
    run_dir = source_evidence_storage.run_source_evidence_dir(
        project_id=project_id,
        run_id=run_id,
    )
    (run_dir / "raw" / "upload").mkdir(parents=True, exist_ok=True)
    (run_dir / "raw" / "upload" / "source.xlsx").write_bytes(b"xlsx")
    (run_dir / "raw" / "converted" / "profile").mkdir(parents=True, exist_ok=True)
    (run_dir / "raw" / "converted" / "source.xlsx").write_bytes(b"converted")
    (run_dir / "raw" / "converted" / "profile" / "registrymodifications.xcu").write_text(
        "profile",
        encoding="utf-8",
    )
    (run_dir / "raw" / "svn-cache" / "abc").mkdir(parents=True, exist_ok=True)
    (run_dir / "raw" / "svn-cache" / "abc" / "QuestReward.xls").write_bytes(b"svn-copy")
    (run_dir / "visual_evidence" / "images").mkdir(parents=True, exist_ok=True)
    (run_dir / "visual_evidence" / "images" / "img_001.png").write_bytes(b"optimized")

    global_svn_cache_file = tmp_path / "runtime" / "svn-cache" / "samosvn" / "abc" / "QuestReward.xls"
    global_svn_cache_file.parent.mkdir(parents=True, exist_ok=True)
    global_svn_cache_file.write_bytes(b"global-cache-must-stay")

    async with async_session_factory() as session:
        run = await session.get(SourceEvidenceRunRecord, run_id)
        assert run is not None
        run.source_type = "svn_file"
        run.raw_manifest_json = json.dumps(
            {
                "upload": {"relative_path": "raw/svn-cache/abc/QuestReward.xls"},
                "converted": {"relative_path": "raw/converted/source.xlsx"},
                "warnings": [{"source": "xls", "level": "warning", "message": ".xls 图片转换失败"}],
            },
            ensure_ascii=False,
        )
        await source_evidence_cleanup.cleanup_source_evidence_run(
            session,
            project_id=project_id,
            run_id=run_id,
            cleaned_by=None,
        )
        await session.commit()

    assert run_dir.exists()
    assert list(run_dir.iterdir()) == []
    assert global_svn_cache_file.read_bytes() == b"global-cache-must-stay"


@pytest.mark.anyio
async def test_cleanup_scrubs_db_when_storage_rejects_unsafe_path(
    test_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """存储层拒绝不安全路径时，cleanup 仍进入 cleaned 状态且错误摘要脱敏。"""
    project_id, run_id, _resource_id, _observation_id = await _seed_sensitive_run()

    def reject_unsafe_path(*, project_id: int, run_id: int) -> None:
        raise source_evidence_storage.SourceEvidenceStorageError(
            f"Source Evidence 路径必须位于根目录内：D:/secret/source-evidence/{project_id}/{run_id}"
        )

    monkeypatch.setattr(
        source_evidence_cleanup.source_evidence_storage,
        "clear_source_evidence_run_dir",
        reject_unsafe_path,
    )

    async with async_session_factory() as session:
        summary = await source_evidence_cleanup.cleanup_source_evidence_run(
            session,
            project_id=project_id,
            run_id=run_id,
            cleaned_by=99,
        )
        await session.commit()

    async with async_session_factory() as session:
        run = await session.get(SourceEvidenceRunRecord, run_id)
        assert run is not None
        audit = json.loads(run.minimal_audit_json)

    assert run.status == "cleaned"
    assert summary == audit
    assert "清理文件失败" in audit["error_summary"]
    audit_text = json.dumps(audit, ensure_ascii=False)
    assert "D:/secret" not in audit_text
    assert "source-evidence" not in audit_text


@pytest.mark.anyio
async def test_cleanup_unlinks_directory_symlink_without_deleting_target(
    test_db,
    tmp_path: Path,
) -> None:
    """run 内目录 symlink/junction 只能删除链接本身，不能跟随删除目标。"""
    project_id, run_id, _resource_id, _observation_id = await _seed_sensitive_run()
    run_dir = source_evidence_storage.run_source_evidence_dir(
        project_id=project_id,
        run_id=run_id,
    )
    outside_dir = tmp_path / "outside-target"
    outside_dir.mkdir(parents=True, exist_ok=True)
    outside_file = outside_dir / "must-stay.txt"
    outside_file.write_text("outside must stay", encoding="utf-8")
    symlink_dir = run_dir / "linked-dir"
    try:
        os.symlink(outside_dir, symlink_dir, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"当前环境不支持目录 symlink：{exc}")

    async with async_session_factory() as session:
        await source_evidence_cleanup.cleanup_source_evidence_run(
            session,
            project_id=project_id,
            run_id=run_id,
            cleaned_by=None,
        )
        await session.commit()

    assert outside_file.read_text(encoding="utf-8") == "outside must stay"
    assert not symlink_dir.exists()
    assert list(run_dir.iterdir()) == []


@pytest.mark.anyio
async def test_cleanup_preserves_existing_source_identifier_fingerprint(test_db) -> None:
    """已脱敏的 source_identifier 不应在清理审计中被二次 hash。"""
    project_id, run_id, _resource_id, _observation_id = await _seed_sensitive_run()
    existing_fingerprint = "sha256:alreadyfingerprinted"
    async with async_session_factory() as session:
        run = await session.get(SourceEvidenceRunRecord, run_id)
        assert run is not None
        run.source_identifier = existing_fingerprint
        await session.commit()

    async with async_session_factory() as session:
        summary = await source_evidence_cleanup.cleanup_source_evidence_run(
            session,
            project_id=project_id,
            run_id=run_id,
            cleaned_by=99,
        )
        await session.commit()

    async with async_session_factory() as session:
        run = await session.get(SourceEvidenceRunRecord, run_id)
        assert run is not None
        audit = json.loads(run.minimal_audit_json)

    assert summary["source_identifier"] == existing_fingerprint
    assert run.source_identifier == existing_fingerprint
    assert audit["source_identifier"] == existing_fingerprint


@pytest.mark.anyio
async def test_lazy_cleanup_on_expired_run_blocks_sensitive_api(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """访问过期 run 时先清理；摘要可见，敏感操作被拒绝。"""
    _project_id, run_id, _resource_id, _observation_id = await _seed_sensitive_run(
        project_id=test_project_id
    )

    run_response = await auth_client.get(f"/api/v1/test-cases/source-evidence-runs/{run_id}")
    assert run_response.status_code == 200
    assert run_response.json()["data"]["status"] == "cleaned"

    resources_response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/resources"
    )
    assert resources_response.status_code == 200
    resources_payload = resources_response.json()["data"]
    assert resources_payload["run_status"] == "cleaned"
    assert "local_path" not in json.dumps(resources_payload)
    assert "file-secret-token" not in json.dumps(resources_payload)

    candidates_response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/visual-candidates"
    )
    assert candidates_response.status_code == 200
    assert candidates_response.json()["data"]["run_status"] == "cleaned"
    assert candidates_response.json()["data"]["items"] == []

    observations_response = await auth_client.get(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/observations"
    )
    assert observations_response.status_code == 200
    observations_payload = observations_response.json()["data"]
    assert observations_payload["run_status"] == "cleaned"
    assert observations_payload["items"] == []
    assert "不能保留" not in json.dumps(observations_payload, ensure_ascii=False)

    for method, suffix, kwargs in (
        ("post", "snapshot", {}),
        ("post", "retry", {}),
        ("post", "visual-selections", {"json": {"selected_refs": []}}),
        ("post", "observations", {"json": {}}),
        ("post", "adopted-visual-evidence", {"json": {"observation_ids": [1]}}),
    ):
        response = await getattr(auth_client, method)(
            f"/api/v1/test-cases/source-evidence-runs/{run_id}/{suffix}",
            **kwargs,
        )
        assert response.status_code == 409
        assert "重新读取来源" in response.json()["detail"]


@pytest.mark.anyio
async def test_cleanup_ignores_storage_path_and_does_not_delete_reference_files(
    test_db,
    tmp_path: Path,
) -> None:
    """清理只能删除 source_evidence_dir 内部内容，不能误删参考案例库或外部路径。"""
    project_id, run_id, _resource_id, _observation_id = await _seed_sensitive_run()
    reference_file = tmp_path / "runtime" / "test-case-references" / "1" / "case.xlsx"
    reference_file.parent.mkdir(parents=True, exist_ok=True)
    reference_file.write_text("reference must stay", encoding="utf-8")
    outside_file = tmp_path / "outside-source-evidence.txt"
    outside_file.write_text("outside must stay", encoding="utf-8")

    async with async_session_factory() as session:
        run = await session.get(SourceEvidenceRunRecord, run_id)
        assert run is not None
        run.storage_path = str(reference_file.parent)
        await session.commit()

    async with async_session_factory() as session:
        await source_evidence_cleanup.cleanup_source_evidence_run(
            session,
            project_id=project_id,
            run_id=run_id,
            cleaned_by=None,
        )
        await session.commit()

    assert reference_file.read_text(encoding="utf-8") == "reference must stay"
    assert outside_file.read_text(encoding="utf-8") == "outside must stay"
