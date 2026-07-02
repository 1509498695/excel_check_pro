"""Source Evidence Run 基础领域 helper。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
import datetime
import hashlib
import inspect
import json
import mimetypes
import re
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from backend.app.ai.credentials import (
    VisionAiProviderInvalid,
    VisionAiProviderNotConfigured,
    decrypt_vision_credential_key,
    load_project_vision_credential,
)
from backend.app.integrations.feishu_client import (
    FEISHU_DOCUMENT_PERMISSION_DENIED,
    FeishuClientError,
    download_feishu_media,
)
from backend.app.models import (
    SourceEvidenceResourceRecord,
    SourceEvidenceRunRecord,
    SourceEvidenceVisualObservationRecord,
)
from backend.app.test_cases import source_evidence_storage
from backend.app.test_cases.feishu_rich_reader import read_feishu_parsed_source
from backend.app.test_cases.local_source_reader import (
    SUPPORTED_LOCAL_SOURCE_SUFFIXES,
    read_local_uploaded_source,
)
from backend.app.test_cases.schemas import (
    GenerationWarning,
    ParsedSource,
    ParsedSourceResource,
    PlanningSnapshotCell,
    PlanningSnapshotResponse,
    PlanningSnapshotRow,
    SourceEvidenceResourceListResponse,
    SourceEvidenceResourceResponse,
    SourceEvidenceRunCreateRequest,
    SourceEvidenceRunResponse,
)
from backend.config import settings


DEFAULT_SOURCE_EVIDENCE_TTL_DAYS = 7

SOURCE_EVIDENCE_RUN_STATUSES = frozenset(
    {
        "reading",
        "ready",
        "pending_permission",
        "vision_pending",
        "failed",
        "expired",
        "cleaned",
    }
)

SOURCE_EVIDENCE_RESOURCE_STATUSES = frozenset(
    {
        "pending",
        "downloaded",
        "download_failed",
        "pending_permission",
        "unobserved",
        "observed",
        "adopted",
        "rejected",
        "expired",
    }
)

SOURCE_EVIDENCE_SNAPSHOT_COLUMNS = [
    "来源类型",
    "位置",
    "标题/页签",
    "内容",
    "证据状态",
]

TEXTLESS_SOURCE_WARNING_MESSAGE = "无文本主体，需先观察并采纳视觉证据后才能作为需求事实。"

SOURCE_EVIDENCE_RETRYABLE_STATUSES = {"pending_permission", "failed"}


@dataclass(frozen=True)
class SourceEvidenceSafeContext:
    """生成和导出可用的安全 Source Evidence 摘要。"""

    run_id: int
    source_summary: str
    ttl_status: str
    prompt_context: str
    export_summary: str
    warnings: list[GenerationWarning]
    adopted_visual_refs: frozenset[str] = frozenset()
    forbidden_visual_refs: frozenset[str] = frozenset()
    visual_validate_warnings: list[GenerationWarning] = field(default_factory=list)


@dataclass(frozen=True)
class AdoptedVisualEvidenceContext:
    """生成/导出可用的已采纳视觉证据安全摘要。"""

    id: int
    ref: str
    position: str
    summary: str
    visible_text: str
    confidence: float | None
    limitations: list[str]


@dataclass(frozen=True)
class VisualValidateResult:
    """生成/导出前的视觉证据校验结果。"""

    adopted_evidence: list[AdoptedVisualEvidenceContext]
    warnings: list[GenerationWarning]
    adopted_visual_refs: frozenset[str]
    forbidden_visual_refs: frozenset[str]


class SourceEvidenceError(RuntimeError):
    """Source Evidence service 错误，API 层按 status_code 转 HTTPException。"""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def source_evidence_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def calculate_source_evidence_expires_at(
    *,
    created_at: datetime.datetime | None = None,
    ttl_days: int | None = None,
) -> datetime.datetime:
    """按 created_at + ttl_days 计算 run 过期时间。"""
    base_time = _as_aware_utc(created_at or source_evidence_now())
    days = settings.source_evidence_ttl_days if ttl_days is None else ttl_days
    if days < 0:
        days = DEFAULT_SOURCE_EVIDENCE_TTL_DAYS
    return base_time + datetime.timedelta(days=days)


def is_source_evidence_expired(
    expires_at: datetime.datetime | SourceEvidenceRunRecord,
    *,
    now: datetime.datetime | None = None,
) -> bool:
    """TTL 是否已到期，只根据 expires_at 判断。"""
    value = expires_at.expires_at if isinstance(expires_at, SourceEvidenceRunRecord) else expires_at
    return _as_aware_utc(value) <= _as_aware_utc(now or source_evidence_now())


async def create_source_evidence_run(
    db: AsyncSession,
    *,
    project_id: int,
    created_by: int | None,
    source_type: str,
    source_identifier: str = "",
    source_title: str = "",
    source_url: str = "",
    source_token: str = "",
    now: datetime.datetime | None = None,
    ttl_days: int | None = None,
) -> SourceEvidenceRunRecord:
    """创建 Source Evidence run，不读取外部来源。"""
    created_at = _as_aware_utc(now or source_evidence_now())
    run = SourceEvidenceRunRecord(
        project_id=project_id,
        source_type=source_type,
        source_url=source_url,
        source_token=source_token,
        source_identifier=source_identifier,
        source_title=source_title,
        status="reading",
        created_by=created_by,
        expires_at=calculate_source_evidence_expires_at(
            created_at=created_at,
            ttl_days=ttl_days,
        ),
    )
    db.add(run)
    await db.flush()
    run.storage_path = str(
        source_evidence_storage.ensure_source_evidence_run_dir(
            project_id=project_id,
            run_id=run.id,
        )
    )
    return run


async def list_project_source_evidence_runs(
    db: AsyncSession,
    *,
    project_id: int,
) -> list[SourceEvidenceRunRecord]:
    result = await db.execute(
        select(SourceEvidenceRunRecord)
        .where(SourceEvidenceRunRecord.project_id == project_id)
        .order_by(SourceEvidenceRunRecord.created_at.asc(), SourceEvidenceRunRecord.id.asc())
    )
    return list(result.scalars().all())


async def list_project_source_evidence_resources(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int | None = None,
) -> list[SourceEvidenceResourceRecord]:
    statement = select(SourceEvidenceResourceRecord).where(
        SourceEvidenceResourceRecord.project_id == project_id,
    )
    if run_id is not None:
        statement = statement.where(SourceEvidenceResourceRecord.run_id == run_id)
    statement = statement.order_by(
        SourceEvidenceResourceRecord.created_at.asc(),
        SourceEvidenceResourceRecord.id.asc(),
    )
    result = await db.execute(statement)
    return list(result.scalars().all())


async def create_source_evidence_run_from_request(
    db: AsyncSession,
    *,
    project_id: int,
    created_by: int | None,
    payload: SourceEvidenceRunCreateRequest,
) -> SourceEvidenceRunResponse:
    """创建 run，同步读取富来源并返回摘要。"""
    run: SourceEvidenceRunRecord | None = await create_source_evidence_run(
        db,
        project_id=project_id,
        created_by=created_by,
        source_type=payload.source_type,
        source_url=payload.source_url,
    )
    try:
        await read_and_persist_source_evidence_run(db, run)
    except SourceEvidenceError:
        await db.rollback()
        if run is not None:
            source_evidence_storage.clear_source_evidence_run_dir(
                project_id=project_id,
                run_id=run.id,
            )
        raise
    await db.commit()
    await db.refresh(run)
    return await build_source_evidence_run_response(db, project_id=project_id, run_id=run.id)


async def create_source_evidence_run_from_upload(
    db: AsyncSession,
    *,
    project_id: int,
    created_by: int | None,
    file: UploadFile,
) -> SourceEvidenceRunResponse:
    """通过上传入口创建 local_file run 并读取 run-local 上传文件。"""
    clean_filename = _safe_upload_filename(file.filename or "")
    suffix = Path(clean_filename).suffix.lower()
    if suffix not in SUPPORTED_LOCAL_SOURCE_SUFFIXES:
        raise SourceEvidenceError(400, f"不支持的本地文件类型：{suffix or '无后缀'}。")

    content = await file.read(settings.max_upload_bytes + 1)
    if not content:
        raise SourceEvidenceError(400, "上传文件不能为空。")
    if len(content) > settings.max_upload_bytes:
        raise SourceEvidenceError(413, f"上传文件超过大小限制：{settings.max_upload_mb} MB。")

    source_sha256 = hashlib.sha256(content).hexdigest()
    upload_relative_path = f"raw/upload/{clean_filename}"
    run: SourceEvidenceRunRecord | None = None
    run = await create_source_evidence_run(
        db,
        project_id=project_id,
        created_by=created_by,
        source_type="local_file",
        source_title=clean_filename,
        source_identifier=f"sha256:{source_sha256}",
        source_token=f"sha256:{source_sha256}",
    )
    source_evidence_storage.write_source_evidence_bytes(
        project_id,
        run.id,
        upload_relative_path,
        content,
    )
    run.raw_manifest_json = json.dumps(
        {
            "upload": {
                "relative_path": upload_relative_path,
                "filename": clean_filename,
                "size": len(content),
                "sha256": source_sha256,
            }
        },
        ensure_ascii=False,
    )
    try:
        await read_and_persist_source_evidence_run(db, run)
    except SourceEvidenceError:
        await db.rollback()
        if run is not None:
            source_evidence_storage.clear_source_evidence_run_dir(
                project_id=project_id,
                run_id=run.id,
            )
        raise
    await db.commit()
    await db.refresh(run)
    return await build_source_evidence_run_response(db, project_id=project_id, run_id=run.id)


async def _read_and_persist_local_file_source(
    db: AsyncSession,
    run: SourceEvidenceRunRecord,
) -> None:
    upload = _local_upload_manifest(run)
    source_manifest = _json_object(run.raw_manifest_json)
    extra_manifest = {
        key: value
        for key, value in source_manifest.items()
        if key in {"svn"} and isinstance(value, dict)
    }
    source_evidence_storage.ensure_source_evidence_subdirs(
        project_id=run.project_id,
        run_id=run.id,
    )
    try:
        parsed = read_local_uploaded_source(
            project_id=run.project_id,
            run_id=run.id,
            upload_relative_path=upload["relative_path"],
            original_filename=upload["filename"],
            source_sha256=upload["sha256"],
            origin=run.source_type,
        )
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        source_evidence_storage.SourceEvidenceStorageError,
    ) as error:
        message = str(error)
        if "读取本地上传文件失败" not in message and "不支持的本地文件类型" not in message:
            message = f"读取本地上传文件失败：{message}"
        raise SourceEvidenceError(400, message) from error

    parsed = _ensure_parsed_source_type(parsed, run.source_type)
    warnings = list(parsed.warnings)
    run.source_title = parsed.title
    run.source_token = parsed.token
    run.source_identifier = _source_identifier_fingerprint(parsed.token)
    run.error_summary = ""

    source_evidence_storage.write_source_evidence_text(
        run.project_id,
        run.id,
        "source.md",
        parsed.markdown,
    )
    source_evidence_storage.write_source_evidence_json(
        run.project_id,
        run.id,
        "raw/parsed_source.json",
        parsed.model_dump(mode="json"),
    )
    source_evidence_storage.write_source_evidence_json(
        run.project_id,
        run.id,
        "raw/raw_manifest.json",
        {
            **parsed.raw_manifest,
            "upload": upload,
            **extra_manifest,
        },
    )
    source_evidence_storage.write_source_evidence_json(
        run.project_id,
        run.id,
        "tables.json",
        [unit.model_dump(mode="json") for unit in parsed.source_units],
    )

    resource_rows: list[SourceEvidenceResourceRecord] = []
    for resource in parsed.resources:
        metadata = dict(resource.metadata)
        local_path = str(metadata.pop("local_path", "") or "")
        row = SourceEvidenceResourceRecord(
            run_id=run.id,
            project_id=run.project_id,
            ref=resource.ref,
            resource_type=resource.type,
            position=resource.position,
            filename=resource.filename,
            file_token=resource.file_token,
            status="unobserved",
            download_status="downloaded" if local_path else "download_failed",
            local_path=local_path,
            mime_type=resource.mime_type,
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        db.add(row)
        resource_rows.append(row)
    await db.flush()

    source_evidence_storage.write_source_evidence_json(
        run.project_id,
        run.id,
        "resources.json",
        [_resource_manifest_item(record) for record in sorted(resource_rows, key=lambda item: item.id)],
    )

    files = {
        "source": "source.md",
        "source_meta": "source.meta.json",
        "manifest": "manifest.json",
        "resources": "resources.json",
        "tables": "tables.json",
        "parsed_source": "raw/parsed_source.json",
        "raw_manifest": "raw/raw_manifest.json",
        "uploaded_source": upload["relative_path"],
    }
    run.status = "ready"
    try:
        from backend.app.test_cases.visual_evidence import prepare_visual_evidence_for_run

        await prepare_visual_evidence_for_run(db, run=run)
        files["visual_candidates"] = "visual_evidence/visual_candidates.json"
        files["visual_selections"] = "visual_evidence/visual_selections.json"
    except Exception as error:  # pragma: no cover - best-effort packet preparation
        warnings.append(
            GenerationWarning(
                source="source_evidence",
                level="warning",
                message=f"视觉候选准备失败：{error}",
            )
        )

    manifest = _light_manifest(
        run=run,
        parsed=parsed,
        files=files,
        warnings=warnings,
        resource_rows=resource_rows,
    )
    manifest["upload"] = upload
    manifest.update(extra_manifest)
    source_evidence_storage.write_source_evidence_json(
        run.project_id,
        run.id,
        "source.meta.json",
        {
            "title": parsed.title,
            "doc_type": parsed.doc_type,
            "source_identifier": _source_identifier_fingerprint(parsed.token),
            "status": "ready",
            "resource_count": len(resource_rows),
            "warnings": [warning.model_dump(mode="json") for warning in warnings],
        },
    )
    source_evidence_storage.write_source_evidence_json(
        run.project_id,
        run.id,
        "manifest.json",
        manifest,
    )
    run.raw_manifest_json = json.dumps(manifest, ensure_ascii=False)


def _local_upload_manifest(run: SourceEvidenceRunRecord) -> dict[str, Any]:
    manifest = _json_object(run.raw_manifest_json)
    upload = manifest.get("upload")
    if not isinstance(upload, dict):
        raise SourceEvidenceError(400, "本地上传源文件缺失，请重新上传。")
    relative_path = str(upload.get("relative_path") or "")
    filename = _safe_upload_filename(str(upload.get("filename") or "uploaded-source"))
    sha256 = str(upload.get("sha256") or "")
    if not relative_path or not filename or not sha256:
        raise SourceEvidenceError(400, "本地上传源文件信息不完整，请重新上传。")
    resolved = source_evidence_storage.resolve_source_evidence_path(
        run.project_id,
        run.id,
        relative_path,
    )
    if not resolved.is_file():
        raise SourceEvidenceError(400, "本地上传源文件不存在，请重新上传。")
    return {
        "relative_path": relative_path,
        "filename": filename,
        "size": int(upload.get("size") or resolved.stat().st_size),
        "sha256": sha256,
    }


async def read_and_persist_source_evidence_run(
    db: AsyncSession,
    run: SourceEvidenceRunRecord,
) -> None:
    """按 Source Evidence 来源类型分发到对应 reader adapter。"""
    if run.source_type == "feishu":
        await _read_and_persist_feishu_source(db, run)
        return
    if run.source_type == "local_file":
        await _read_and_persist_local_file_source(db, run)
        return
    if run.source_type == "svn_file":
        await _read_and_persist_svn_file_source(db, run)
        return
    raise SourceEvidenceError(400, f"暂不支持的 Source Evidence 来源：{run.source_type}")


async def _read_and_persist_svn_file_source(
    db: AsyncSession,
    run: SourceEvidenceRunRecord,
) -> None:
    from backend.app.test_cases.svn_source_reader import (
        prepare_svn_source_evidence_file,
    )

    manifest = await prepare_svn_source_evidence_file(db, run)
    run.raw_manifest_json = json.dumps(manifest, ensure_ascii=False)
    await _read_and_persist_local_file_source(db, run)


async def build_source_evidence_run_response(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> SourceEvidenceRunResponse:
    """读取项目内 run 摘要，跨项目不可见。"""
    run = await get_project_source_evidence_run(db, project_id=project_id, run_id=run_id)
    resources = await list_project_source_evidence_resources(
        db,
        project_id=project_id,
        run_id=run.id,
    )
    return _run_response(run, resource_count=len(resources))


async def build_source_evidence_resources_response(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> SourceEvidenceResourceListResponse:
    """读取项目内 run 的资源清单。"""
    run = await get_project_source_evidence_run(db, project_id=project_id, run_id=run_id)
    resources = await list_project_source_evidence_resources(
        db,
        project_id=project_id,
        run_id=run_id,
    )
    warnings = []
    if run.status == "cleaned":
        warnings.append(
            GenerationWarning(
                source="source_evidence",
                level="warning",
                message="证据已清理，请重新读取来源。",
            )
        )
    return SourceEvidenceResourceListResponse(
        items=[_resource_response(resource) for resource in resources],
        run_status=run.status,
        warnings=warnings,
    )


async def retry_source_evidence_run(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> SourceEvidenceRunResponse:
    """重试 pending_permission/failed 或资源下载失败的 ready run。"""
    run = await get_project_source_evidence_run(db, project_id=project_id, run_id=run_id)
    _ensure_run_can_be_used(run)
    resources = await list_project_source_evidence_resources(
        db,
        project_id=project_id,
        run_id=run.id,
    )
    has_failed_resource = any(
        resource.download_status in {"download_failed", "pending_permission"}
        for resource in resources
    )
    if run.status not in SOURCE_EVIDENCE_RETRYABLE_STATUSES and not has_failed_resource:
        raise SourceEvidenceError(409, "当前 Source Evidence Run 无需重试。")

    if run.source_type == "local_file":
        _clear_local_file_derived_files(project_id=project_id, run_id=run.id)
    else:
        source_evidence_storage.clear_source_evidence_run_dir(
            project_id=project_id,
            run_id=run.id,
        )
    await db.execute(
        delete(SourceEvidenceResourceRecord).where(
            SourceEvidenceResourceRecord.project_id == project_id,
            SourceEvidenceResourceRecord.run_id == run.id,
        )
    )
    run.status = "reading"
    run.error_summary = ""
    if run.source_type != "local_file":
        run.raw_manifest_json = "{}"
    try:
        await read_and_persist_source_evidence_run(db, run)
    except SourceEvidenceError:
        await db.rollback()
        raise
    await db.commit()
    await db.refresh(run)
    return await build_source_evidence_run_response(db, project_id=project_id, run_id=run.id)


def _clear_local_file_derived_files(*, project_id: int, run_id: int) -> None:
    """清理 local_file 派生文件，但保留 raw/upload 下的原始上传。"""
    for relative_path in (
        "source.md",
        "source.meta.json",
        "manifest.json",
        "resources.json",
        "tables.json",
        "images",
        "attachments",
        "visual_evidence",
        "raw/converted",
        "raw/parsed_source.json",
        "raw/raw_manifest.json",
    ):
        source_evidence_storage.delete_source_evidence_path(
            project_id,
            run_id,
            relative_path,
        )


async def build_source_evidence_snapshot(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> PlanningSnapshotResponse:
    """把 Source Evidence Run 转成兼容 PlanningSnapshotResponse 的快照。"""
    run = await get_project_source_evidence_run(db, project_id=project_id, run_id=run_id)
    _ensure_run_can_be_used(run)
    if run.status not in {"ready", "vision_pending"}:
        raise SourceEvidenceError(409, "Source Evidence Run 尚未 ready，不能生成快照。")

    parsed = _load_parsed_source_for_snapshot(run)
    resources = await list_project_source_evidence_resources(
        db,
        project_id=project_id,
        run_id=run_id,
    )
    rows = _build_snapshot_rows(run.source_type, parsed, resources)
    warnings = _merge_snapshot_warnings(
        parsed.warnings,
        resources,
        _manifest_warnings(run),
        textless_source=_is_textless_source(parsed),
        source_type=parsed.source_type or run.source_type,
    )
    return PlanningSnapshotResponse(
        source_summary=_source_summary(run, parsed),
        sheet_name="Source Evidence",
        rows=rows,
        columns=SOURCE_EVIDENCE_SNAPSHOT_COLUMNS,
        non_empty_cell_count=sum(1 for row in rows for cell in row.cells if cell.value.strip()),
        truncated=False,
        warnings=warnings,
    )


async def build_source_evidence_safe_context(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    planning_snapshot: PlanningSnapshotResponse | None = None,
    adopted_visual_evidence_ids: list[int] | None = None,
) -> SourceEvidenceSafeContext:
    """构造生成/导出用安全摘要，不返回原文、token、路径或 prompt。"""
    run = await get_project_source_evidence_run(db, project_id=project_id, run_id=run_id)
    _ensure_run_can_be_used(run)
    if run.status not in {"ready", "vision_pending"}:
        raise SourceEvidenceError(409, "Source Evidence Run 尚未 ready，不能用于生成或导出。")

    parsed = _load_parsed_source_for_context(
        project_id=project_id,
        run_id=run_id,
        source_type=run.source_type,
    )
    source_summary = _source_summary(run, parsed)
    if planning_snapshot is not None:
        _ensure_snapshot_matches_source_evidence(
            planning_snapshot,
            source_summary=source_summary,
        )

    resources = await list_project_source_evidence_resources(
        db,
        project_id=project_id,
        run_id=run_id,
    )
    manifest = _json_object(run.raw_manifest_json)
    base_warnings = _deduplicate_warnings(
        [
            *_manifest_warnings(run),
            *((parsed.warnings if parsed is not None else [])),
        ]
    )
    visual_validate = await validate_source_evidence_for_generation(
        db,
        project_id=project_id,
        run=run,
        parsed=parsed,
        resources=resources,
        adopted_visual_evidence_ids=adopted_visual_evidence_ids or [],
        existing_warnings=base_warnings,
    )
    warnings = _sanitize_warnings_for_visual_refs(
        _deduplicate_warnings([*base_warnings, *visual_validate.warnings]),
        visual_validate.forbidden_visual_refs,
    )
    ttl_status = f"有效，expires_at={_datetime_to_iso(run.expires_at)}"
    prompt_context = _build_source_evidence_prompt_context(
        run=run,
        source_summary=source_summary,
        ttl_status=ttl_status,
        parsed=parsed,
        resources=resources,
        adopted_evidence=visual_validate.adopted_evidence,
        manifest=manifest,
        warnings=warnings,
    )
    export_summary = _build_source_evidence_export_summary(
        run=run,
        source_summary=source_summary,
        ttl_status=ttl_status,
        parsed=parsed,
        resources=resources,
        adopted_evidence=visual_validate.adopted_evidence,
        warnings=warnings,
    )
    return SourceEvidenceSafeContext(
        run_id=run.id,
        source_summary=source_summary,
        ttl_status=ttl_status,
        prompt_context=prompt_context,
        export_summary=export_summary,
        warnings=warnings,
        adopted_visual_refs=visual_validate.adopted_visual_refs,
        forbidden_visual_refs=visual_validate.forbidden_visual_refs,
        visual_validate_warnings=visual_validate.warnings,
    )


async def get_project_source_evidence_run(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> SourceEvidenceRunRecord:
    """按 project_id + run_id 查询 run，避免泄漏跨项目存在性。"""
    result = await db.execute(
        select(SourceEvidenceRunRecord).where(
            SourceEvidenceRunRecord.id == run_id,
            SourceEvidenceRunRecord.project_id == project_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise SourceEvidenceError(404, "Source Evidence Run 不存在。")
    from backend.app.test_cases.source_evidence_cleanup import (
        ensure_run_not_expired_or_cleanup,
    )

    await ensure_run_not_expired_or_cleanup(db, run)
    return run


async def download_source_evidence_resource_file(
    db: AsyncSession,
    *,
    project_id: int,
    run: SourceEvidenceRunRecord,
    resource: ParsedSourceResource,
) -> str:
    """下载飞书资源文件并返回 run 内相对路径。"""
    if not resource.file_token:
        raise SourceEvidenceError(400, "资源缺少 file_token，无法下载。")
    content, content_type = await download_feishu_media(
        db,
        project_id,
        resource.file_token,
    )
    subdir = "images" if resource.type == "image" else "attachments"
    filename = _safe_resource_filename(
        resource.filename or resource.ref,
        content_type=content_type,
        resource_type=resource.type,
    )
    relative_path = f"{subdir}/{filename}"
    source_evidence_storage.write_source_evidence_bytes(
        project_id,
        run.id,
        relative_path,
        content,
    )
    return relative_path


async def _read_and_persist_feishu_source(
    db: AsyncSession,
    run: SourceEvidenceRunRecord,
) -> None:
    warnings: list[GenerationWarning] = []
    reusable_authorization = await _find_reusable_authorization_for_run(db, run)
    try:
        parsed = await _maybe_await(
            read_feishu_parsed_source(db, run.project_id, run.source_url)
        )
    except FeishuClientError as error:
        status = "pending_permission" if error.code == FEISHU_DOCUMENT_PERMISSION_DENIED else "failed"
        message = (
            _permission_error_with_authorization_context(error.message)
            if status == "pending_permission" and reusable_authorization is not None
            else error.message
        )
        run.status = status
        run.error_summary = message
        run.raw_manifest_json = json.dumps(
            _light_manifest(
                run=run,
                files={},
                warnings=[
                    GenerationWarning(
                        source="feishu",
                        level="warning" if status == "pending_permission" else "error",
                        message=message,
                    )
                ],
                parsed=None,
            ),
            ensure_ascii=False,
        )
        return
    except Exception as error:  # pragma: no cover - defensive service boundary
        run.status = "failed"
        run.error_summary = str(error)
        run.raw_manifest_json = json.dumps(
            _light_manifest(
                run=run,
                files={},
                warnings=[
                    GenerationWarning(
                        source="source_evidence",
                        level="error",
                        message=str(error),
                    )
                ],
                parsed=None,
            ),
            ensure_ascii=False,
        )
        return

    parsed = _ensure_parsed_source_type(parsed, run.source_type)
    source_evidence_storage.ensure_source_evidence_subdirs(
        project_id=run.project_id,
        run_id=run.id,
    )
    run.source_title = parsed.title
    run.source_token = parsed.token
    run.source_identifier = _source_identifier_fingerprint(parsed.token)
    run.error_summary = ""

    warnings.extend(parsed.warnings)
    source_evidence_storage.write_source_evidence_text(
        run.project_id,
        run.id,
        "source.md",
        parsed.markdown,
    )
    source_evidence_storage.write_source_evidence_json(
        run.project_id,
        run.id,
        "raw/parsed_source.json",
        parsed.model_dump(mode="json"),
    )
    source_evidence_storage.write_source_evidence_json(
        run.project_id,
        run.id,
        "raw/raw_manifest.json",
        parsed.raw_manifest,
    )
    source_evidence_storage.write_source_evidence_json(
        run.project_id,
        run.id,
        "tables.json",
        [unit.model_dump(mode="json") for unit in parsed.source_units],
    )

    resource_rows: list[SourceEvidenceResourceRecord] = []
    for resource in parsed.resources:
        row = SourceEvidenceResourceRecord(
            run_id=run.id,
            project_id=run.project_id,
            ref=resource.ref,
            resource_type=resource.type,
            position=resource.position,
            filename=resource.filename,
            file_token=resource.file_token,
            status="unobserved",
            download_status="pending",
            mime_type=resource.mime_type,
            metadata_json=json.dumps(resource.metadata, ensure_ascii=False),
        )
        db.add(row)
        await db.flush()
        await _best_effort_download_resource(
            db,
            run=run,
            parsed_resource=resource,
            record=row,
            warnings=warnings,
            reusable_authorization_found=reusable_authorization is not None,
        )
        resource_rows.append(row)

    resources_payload = [
        _resource_manifest_item(record) for record in sorted(resource_rows, key=lambda item: item.id)
    ]
    source_evidence_storage.write_source_evidence_json(
        run.project_id,
        run.id,
        "resources.json",
        resources_payload,
    )
    files = {
        "source": "source.md",
        "source_meta": "source.meta.json",
        "manifest": "manifest.json",
        "resources": "resources.json",
        "tables": "tables.json",
        "parsed_source": "raw/parsed_source.json",
        "raw_manifest": "raw/raw_manifest.json",
    }
    run.status = "ready"
    try:
        from backend.app.test_cases.visual_evidence import prepare_visual_evidence_for_run

        await prepare_visual_evidence_for_run(db, run=run)
        files["visual_candidates"] = "visual_evidence/visual_candidates.json"
        files["visual_selections"] = "visual_evidence/visual_selections.json"
    except Exception as error:  # pragma: no cover - best-effort packet preparation
        warnings.append(
            GenerationWarning(
                source="source_evidence",
                level="warning",
                message=f"视觉候选准备失败：{error}",
            )
        )
    manifest = _light_manifest(
        run=run,
        parsed=parsed,
        files=files,
        warnings=warnings,
        resource_rows=resource_rows,
    )
    source_evidence_storage.write_source_evidence_json(
        run.project_id,
        run.id,
        "source.meta.json",
        {
            "title": parsed.title,
            "doc_type": parsed.doc_type,
            "source_identifier": _source_identifier_fingerprint(parsed.token),
            "status": "ready",
            "resource_count": len(resource_rows),
            "warnings": [warning.model_dump(mode="json") for warning in warnings],
        },
    )
    source_evidence_storage.write_source_evidence_json(
        run.project_id,
        run.id,
        "manifest.json",
        manifest,
    )
    run.raw_manifest_json = json.dumps(manifest, ensure_ascii=False)


async def _best_effort_download_resource(
    db: AsyncSession,
    *,
    run: SourceEvidenceRunRecord,
    parsed_resource: ParsedSourceResource,
    record: SourceEvidenceResourceRecord,
    warnings: list[GenerationWarning],
    reusable_authorization_found: bool = False,
) -> None:
    try:
        local_path = await _maybe_await(
            download_source_evidence_resource_file(
                db,
                project_id=run.project_id,
                run=run,
                resource=parsed_resource,
            )
        )
    except FeishuClientError as error:
        if error.code == FEISHU_DOCUMENT_PERMISSION_DENIED:
            record.download_status = "pending_permission"
            message = (
                _permission_error_with_authorization_context(error.message)
                if reusable_authorization_found
                else error.message
            )
        else:
            record.download_status = "download_failed"
            message = error.message
        warnings.append(
            GenerationWarning(
                source="feishu",
                level="warning",
                message=f"资源 {parsed_resource.ref} 下载失败：{message}",
            )
        )
        return
    except SourceEvidenceError as error:
        record.download_status = "download_failed"
        warnings.append(
            GenerationWarning(
                source="source_evidence",
                level="warning",
                message=f"资源 {parsed_resource.ref} 下载失败：{error.message}",
            )
        )
        return
    except Exception as error:  # pragma: no cover - defensive best-effort boundary
        record.download_status = "download_failed"
        warnings.append(
            GenerationWarning(
                source="source_evidence",
                level="warning",
                message=f"资源 {parsed_resource.ref} 下载失败：{error}",
            )
        )
        return

    record.download_status = "downloaded"
    record.local_path = str(local_path or "")


def scrub_source_evidence_sensitive_fields(
    run: SourceEvidenceRunRecord,
    resources: Iterable[SourceEvidenceResourceRecord],
    *,
    cleaned_by: int | None,
    cleaned_at: datetime.datetime | None = None,
) -> dict[str, Any]:
    """清空敏感字段并把最小审计摘要写回 run。"""
    cleaned_at_value = _as_aware_utc(cleaned_at or source_evidence_now())
    resource_list = list(resources)
    from backend.app.test_cases.source_evidence_cleanup import (
        _build_minimal_audit,
        _scrub_resources,
        _scrub_run,
    )

    summary = _build_minimal_audit(
        run=run,
        resources=resource_list,
        observations=[],
        cleaned_by=cleaned_by,
        cleaned_at=cleaned_at_value,
    )
    _scrub_run(
        run,
        summary=summary,
        cleaned_by=cleaned_by,
        cleaned_at=cleaned_at_value,
    )
    _scrub_resources(resource_list, cleaned_at=cleaned_at_value)

    return summary


def build_minimal_source_evidence_audit(
    run: SourceEvidenceRunRecord,
    resources: Iterable[SourceEvidenceResourceRecord],
    *,
    cleaned_by: int | None,
    cleaned_at: datetime.datetime,
) -> dict[str, Any]:
    """构造不含原文、路径、观察详情、prompt 的最小审计摘要。"""
    return {
        "run_id": run.id,
        "project_id": run.project_id,
        "source_type": run.source_type,
        "source_identifier": _source_identifier_fingerprint(run.source_identifier),
        "source_title": run.source_title,
        "status": run.status,
        "created_by": run.created_by,
        "cleaned_by": cleaned_by,
        "created_at": _datetime_to_iso(run.created_at),
        "cleaned_at": _datetime_to_iso(cleaned_at),
        "resources": [
            {
                "resource_id": resource.id,
                "run_id": resource.run_id,
                "project_id": resource.project_id,
                "ref": resource.ref,
                "filename": resource.filename,
                "status": resource.status,
                "created_at": _datetime_to_iso(resource.created_at),
                "cleaned_at": _datetime_to_iso(cleaned_at),
            }
            for resource in resources
        ],
    }


def _run_response(
    run: SourceEvidenceRunRecord,
    *,
    resource_count: int,
) -> SourceEvidenceRunResponse:
    manifest_warnings = _manifest_warnings(run)
    status = "expired" if run.status != "cleaned" and is_source_evidence_expired(run) else run.status
    return SourceEvidenceRunResponse(
        id=run.id,
        status=status,
        source_type=run.source_type,
        source_summary=_source_summary(run),
        source_title=run.source_title,
        source_identifier=run.source_identifier,
        created_at=_datetime_to_iso(run.created_at),
        expires_at=_datetime_to_iso(run.expires_at),
        warnings=manifest_warnings,
        resource_count=resource_count,
    )


def _resource_response(
    resource: SourceEvidenceResourceRecord,
) -> SourceEvidenceResourceResponse:
    return SourceEvidenceResourceResponse(
        id=resource.id,
        ref=resource.ref,
        type=resource.resource_type,
        position=resource.position,
        filename=resource.filename,
        download_status=resource.download_status,
        adoption_status=resource.status,
        mime_type=resource.mime_type,
    )


def _resource_manifest_item(resource: SourceEvidenceResourceRecord) -> dict[str, Any]:
    return {
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


async def _find_reusable_authorization_for_run(
    db: AsyncSession,
    run: SourceEvidenceRunRecord,
) -> Any | None:
    """Best-effort reusable authorization lookup; never blocks reading/retry."""
    try:
        from backend.app.test_cases.source_evidence_authorization import (
            find_reusable_source_evidence_authorization_for_run,
        )

        return await find_reusable_source_evidence_authorization_for_run(
            db,
            project_id=run.project_id,
            run=run,
        )
    except Exception:
        return None


def _permission_error_with_authorization_context(message: str) -> str:
    return (
        f"{message} 已检测到有效 Source Evidence 授权记录，但项目 App/Bot 仍无法读取；"
        "不会自动重新发送授权卡，请显式重新申请授权或确认飞书协作者权限已生效。"
    )


def _source_identifier_fingerprint(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith("sha256:"):
        return raw
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"sha256:{digest}"


def _light_manifest(
    *,
    run: SourceEvidenceRunRecord,
    files: dict[str, str],
    warnings: list[GenerationWarning],
    parsed: ParsedSource | None,
    resource_rows: list[SourceEvidenceResourceRecord] | None = None,
) -> dict[str, Any]:
    """DB 只保存轻量 manifest，不保存原文、blocks、prompt 或 provider response。"""
    resources = resource_rows or []
    return {
        "run_id": run.id,
        "project_id": run.project_id,
        "source_type": run.source_type,
        "source_identifier": _source_identifier_fingerprint(
            parsed.token if parsed is not None else run.source_identifier
        ),
        "source_title": parsed.title if parsed is not None else run.source_title,
        "doc_type": parsed.doc_type if parsed is not None else "",
        "status": run.status,
        "files": files,
        "counts": {
            "source_unit_count": len(parsed.source_units) if parsed is not None else 0,
            "resource_count": len(resources),
            "downloaded_resource_count": sum(
                1 for resource in resources if resource.download_status == "downloaded"
            ),
            "failed_resource_count": sum(
                1
                for resource in resources
                if resource.download_status in {"download_failed", "pending_permission"}
            ),
            "warning_count": len(warnings),
        },
        "warnings": [warning.model_dump(mode="json") for warning in warnings],
        "created_by": run.created_by,
        "created_at": _datetime_to_iso(run.created_at),
        "expires_at": _datetime_to_iso(run.expires_at),
    }


def _manifest_warnings(run: SourceEvidenceRunRecord) -> list[GenerationWarning]:
    payload = _json_object(run.raw_manifest_json)
    warnings = payload.get("warnings")
    if not isinstance(warnings, list):
        return []
    result: list[GenerationWarning] = []
    for item in warnings:
        if isinstance(item, dict):
            try:
                result.append(GenerationWarning.model_validate(item))
            except ValueError:
                continue
    return result


def _source_summary(
    run: SourceEvidenceRunRecord,
    parsed: ParsedSource | None = None,
) -> str:
    title = (parsed.title if parsed is not None else run.source_title) or run.source_identifier or "未命名来源"
    doc_type = parsed.doc_type if parsed is not None else _json_object(run.raw_manifest_json).get("doc_type")
    doc_type_text = str(doc_type or run.source_type or "source")
    if run.source_type == "feishu":
        return f"飞书 {doc_type_text}：{title}"
    return f"{run.source_type}：{title}"


def _ensure_run_can_be_used(run: SourceEvidenceRunRecord) -> None:
    if run.status in {"cleaned", "expired"} or is_source_evidence_expired(run):
        raise SourceEvidenceError(409, "证据已过期或已清理，请重新读取来源。")


def _build_snapshot_rows(
    run_source_type: str,
    parsed: ParsedSource,
    resources: list[SourceEvidenceResourceRecord],
) -> list[PlanningSnapshotRow]:
    rows: list[PlanningSnapshotRow] = []
    rendered_resource_refs: set[str] = set()
    source_type = parsed.source_type or run_source_type
    content_source_type = _snapshot_content_source_type(source_type, parsed.doc_type)
    next_row_index = 1
    fact_row_count = 0

    for unit in parsed.source_units:
        if unit.kind == "sheet":
            for cell in unit.cells:
                content = str(cell.text or "").strip()
                if not content:
                    continue
                position = f"{unit.title}!{cell.coord}"
                rows.append(
                    _snapshot_row(
                        row_index=next_row_index,
                        source_type=content_source_type,
                        position=position,
                        title=unit.title,
                        content=content,
                        evidence_status="table",
                    )
                )
                next_row_index += 1
                fact_row_count += 1
            continue

        if unit.kind == "bitable":
            for row in unit.rows:
                record_id = str(row.get("record_id") or next_row_index)
                rows.append(
                    _snapshot_row(
                        row_index=next_row_index,
                        source_type=content_source_type,
                        position=f"{unit.title}/{record_id}",
                        title=unit.title,
                        content=json.dumps(row.get("fields", row), ensure_ascii=False),
                        evidence_status="table",
                    )
                )
                next_row_index += 1
                fact_row_count += 1
            continue

        for row in unit.rows:
            rows.append(
                _snapshot_row(
                    row_index=next_row_index,
                    source_type=content_source_type,
                    position=unit.path or unit.title or f"{unit.kind}:row:{next_row_index}",
                    title=unit.title or parsed.title,
                    content=json.dumps(row, ensure_ascii=False),
                    evidence_status="table",
                )
            )
            next_row_index += 1
            fact_row_count += 1

        for cell in unit.cells:
            content = str(cell.text or "").strip()
            if not content:
                continue
            rows.append(
                _snapshot_row(
                    row_index=next_row_index,
                    source_type=content_source_type,
                    position=f"{unit.path or unit.title or unit.kind}:{cell.coord}",
                    title=unit.title or parsed.title,
                    content=content,
                    evidence_status="table",
                )
            )
            next_row_index += 1
            fact_row_count += 1

    for line in _iter_snapshot_text_lines(parsed.markdown):
        rows.append(
            _snapshot_row(
                row_index=next_row_index,
                source_type=content_source_type,
                position=f"{parsed.doc_type}:line:{next_row_index}",
                title=parsed.title,
                content=line,
                evidence_status="text",
            )
        )
        next_row_index += 1
        fact_row_count += 1

    if fact_row_count == 0 and _is_textless_source(parsed):
        rows.append(
            _snapshot_row(
                row_index=next_row_index,
                source_type=content_source_type,
                position=f"{parsed.doc_type or 'source'}:textless",
                title=parsed.title,
                content=TEXTLESS_SOURCE_WARNING_MESSAGE,
                evidence_status="pending_visual",
            )
        )
        next_row_index += 1

    for resource in resources:
        if resource.resource_type not in {"image", "attachment"}:
            continue
        resource_ref = resource.ref or f"{resource.resource_type}:{resource.id}"
        if resource_ref in rendered_resource_refs:
            continue
        rows.append(
            _snapshot_row(
                row_index=next_row_index,
                source_type=_snapshot_resource_source_type(source_type, resource.resource_type),
                position=resource.position or f"{resource.resource_type}:{resource.ref}",
                title=parsed.title,
                content=_resource_snapshot_content(resource),
                evidence_status="pending_visual",
            )
        )
        rendered_resource_refs.add(resource_ref)
        next_row_index += 1

    return rows


def _snapshot_content_source_type(source_type: str, doc_type: str) -> str:
    return f"{source_type or 'source'}:{doc_type or 'source'}"


def _snapshot_resource_source_type(source_type: str, resource_type: str) -> str:
    return f"{source_type or 'source'}:{resource_type or 'resource'}"


def _snapshot_row(
    *,
    row_index: int,
    source_type: str,
    position: str,
    title: str,
    content: str,
    evidence_status: str,
) -> PlanningSnapshotRow:
    values = [source_type, position, title, content, evidence_status]
    return PlanningSnapshotRow(
        row_index=row_index,
        cells=[
            PlanningSnapshotCell(
                row_index=row_index,
                column_index=column_index,
                column_name=column_name,
                value=value,
            )
            for column_index, (column_name, value) in enumerate(
                zip(SOURCE_EVIDENCE_SNAPSHOT_COLUMNS, values, strict=True),
                start=1,
            )
        ],
    )


def _resource_snapshot_content(resource: SourceEvidenceResourceRecord) -> str:
    parts = [f"资源 {resource.ref}"]
    if resource.filename:
        parts.append(resource.filename)
    if resource.mime_type:
        parts.append(resource.mime_type)
    if resource.download_status:
        parts.append(f"download_status={resource.download_status}")
    return "；".join(parts)


def _iter_snapshot_text_lines(markdown: str) -> Iterable[str]:
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# Source:") or line.startswith("URL:") or line.startswith("Type:"):
            continue
        if _is_resource_marker(line):
            continue
        yield line


def _is_resource_marker(line: str) -> bool:
    return "<image " in line or "<attachment " in line


def _is_textless_source(parsed: ParsedSource) -> bool:
    if parsed.doc_type == "image":
        return True
    if any(unit.cells or unit.rows for unit in parsed.source_units):
        return False
    return not any(_iter_snapshot_text_lines(parsed.markdown)) and bool(parsed.resources)


def _merge_snapshot_warnings(
    parsed_warnings: list[GenerationWarning],
    resources: list[SourceEvidenceResourceRecord],
    manifest_warnings: list[GenerationWarning],
    *,
    textless_source: bool = False,
    source_type: str = "",
) -> list[GenerationWarning]:
    warnings: list[GenerationWarning] = []
    existing_keys: set[tuple[str, str, str]] = set()

    def append_warning(warning: GenerationWarning) -> None:
        key = (warning.source, warning.level, warning.message)
        if key in existing_keys:
            return
        warnings.append(warning)
        existing_keys.add(key)

    for warning in [*manifest_warnings, *parsed_warnings]:
        append_warning(warning)

    for resource in resources:
        if resource.download_status in {"download_failed", "pending_permission"}:
            message = f"资源 {resource.ref} 状态为 {resource.download_status}，快照保留文本/表格内容。"
            append_warning(
                GenerationWarning(
                    source="source_evidence",
                    level="warning",
                    message=message,
                )
            )
    if textless_source:
        append_warning(
            GenerationWarning(
                source=source_type or "source_evidence",
                level="warning",
                message=TEXTLESS_SOURCE_WARNING_MESSAGE,
            )
        )
    return warnings


def _load_parsed_source_for_snapshot(run: SourceEvidenceRunRecord) -> ParsedSource:
    return _load_parsed_source_from_storage(
        project_id=run.project_id,
        run_id=run.id,
        source_type=run.source_type,
    )


def _load_parsed_source_from_storage(
    *,
    project_id: int,
    run_id: int,
    source_type: str = "",
) -> ParsedSource:
    payload = source_evidence_storage.read_source_evidence_json(
        project_id,
        run_id,
        "raw/parsed_source.json",
    )
    if isinstance(payload, dict) and not payload.get("source_type"):
        payload = {**payload, "source_type": source_type}
    return _ensure_parsed_source_type(ParsedSource.model_validate(payload), source_type)


def _ensure_parsed_source_type(parsed: ParsedSource, source_type: str) -> ParsedSource:
    clean_source_type = str(parsed.source_type or source_type or "")
    if parsed.source_type == clean_source_type:
        return parsed
    return parsed.model_copy(update={"source_type": clean_source_type})


def _load_parsed_source_for_context(
    *,
    project_id: int,
    run_id: int,
    source_type: str = "",
) -> ParsedSource | None:
    try:
        return _load_parsed_source_from_storage(
            project_id=project_id,
            run_id=run_id,
            source_type=source_type,
        )
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return None


def _ensure_snapshot_matches_source_evidence(
    snapshot: PlanningSnapshotResponse,
    *,
    source_summary: str,
) -> None:
    if snapshot.columns != SOURCE_EVIDENCE_SNAPSHOT_COLUMNS:
        raise SourceEvidenceError(
            400,
            "source_evidence_run_id 必须搭配 Source Evidence Snapshot 使用。",
        )
    if snapshot.source_summary != source_summary:
        raise SourceEvidenceError(
            400,
            "Source Evidence Snapshot 与 source_evidence_run_id 不匹配。",
        )


async def validate_source_evidence_for_generation(
    db: AsyncSession,
    *,
    project_id: int,
    run: SourceEvidenceRunRecord,
    parsed: ParsedSource | None,
    resources: list[SourceEvidenceResourceRecord],
    adopted_visual_evidence_ids: list[int],
    existing_warnings: list[GenerationWarning],
) -> VisualValidateResult:
    """生成/导出前执行视觉证据硬校验和安全 warning 汇总。"""
    _ensure_run_can_be_used(run)
    resources_by_id = {resource.id: resource for resource in resources}
    adopted_evidence = await _load_adopted_visual_evidence_context(
        db,
        project_id=project_id,
        run_id=run.id,
        evidence_ids=adopted_visual_evidence_ids,
        resources_by_id=resources_by_id,
    )
    adopted_refs = frozenset(item.ref for item in adopted_evidence if item.ref)
    resource_refs = {
        resource.ref
        for resource in resources
        if resource.ref and _resource_can_be_visual_evidence(resource)
    }
    forbidden_refs = frozenset(sorted(resource_refs - set(adopted_refs)))

    if parsed is not None and _is_textless_source(parsed) and not adopted_evidence:
        raise SourceEvidenceError(
            409,
            "独立图片 Source Evidence 需要先观察并采纳视觉证据后才能生成或导出。",
        )

    visual_warnings: list[GenerationWarning] = []
    image_resources = [
        resource for resource in resources if _resource_is_image_like(resource)
    ]
    unobserved_count = sum(
        1
        for resource in image_resources
        if resource.ref not in adopted_refs
        and resource.status in {"unobserved", "observed", "pending"}
    )
    if unobserved_count:
        visual_warnings.append(
            GenerationWarning(
                source="visual_validate",
                level="warning",
                message=f"{unobserved_count} 个图片资源未观察或未采纳，未参与生成或导出。",
            )
        )

    failed_count = sum(
        1
        for resource in image_resources
        if resource.download_status in {"download_failed", "pending_permission"}
    )
    if failed_count:
        visual_warnings.append(
            GenerationWarning(
                source="visual_validate",
                level="warning",
                message=f"{failed_count} 个图片资源提取或下载失败，未参与生成或导出。",
            )
        )

    if _has_xls_conversion_failure(existing_warnings):
        visual_warnings.append(
            GenerationWarning(
                source="visual_validate",
                level="warning",
                message=".xls 图片转换失败，相关图片未参与生成或导出。",
            )
        )

    if image_resources and any(resource.ref not in adopted_refs for resource in image_resources):
        if await _vision_ai_unavailable(db, project_id=project_id):
            visual_warnings.append(
                GenerationWarning(
                    source="visual_validate",
                    level="warning",
                    message="Vision AI 未配置或不可用，未采纳图片不会参与生成或导出。",
                )
            )

    return VisualValidateResult(
        adopted_evidence=adopted_evidence,
        warnings=_deduplicate_warnings(visual_warnings),
        adopted_visual_refs=adopted_refs,
        forbidden_visual_refs=forbidden_refs,
    )


async def _load_adopted_visual_evidence_context(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    evidence_ids: list[int],
    resources_by_id: dict[int, SourceEvidenceResourceRecord] | None = None,
) -> list[AdoptedVisualEvidenceContext]:
    clean_ids = list(dict.fromkeys(int(item) for item in evidence_ids if int(item) > 0))
    if not clean_ids:
        return []
    result = await db.execute(
        select(SourceEvidenceVisualObservationRecord).where(
            SourceEvidenceVisualObservationRecord.project_id == project_id,
            SourceEvidenceVisualObservationRecord.run_id == run_id,
            SourceEvidenceVisualObservationRecord.id.in_(clean_ids),
        )
    )
    records = list(result.scalars().all())
    by_id = {record.id: record for record in records}
    if set(by_id) != set(clean_ids):
        raise SourceEvidenceError(404, "已采纳视觉证据不存在。")

    contexts: list[AdoptedVisualEvidenceContext] = []
    for evidence_id in clean_ids:
        record = by_id[evidence_id]
        if record.status != "adopted":
            raise SourceEvidenceError(400, "只有已采纳视觉证据可以进入生成。")
        if record.resource_id is None:
            raise SourceEvidenceError(409, "已采纳视觉证据缺少关联资源，请重新观察并采纳。")
        if resources_by_id is not None:
            resource = resources_by_id.get(record.resource_id)
            if resource is None or resource.ref != record.ref:
                raise SourceEvidenceError(409, "已采纳视觉证据与当前资源清单不一致，请重新观察并采纳。")
        detail = _read_observation_detail(
            project_id=project_id,
            run_id=run_id,
            observation_path=record.observation_path,
        )
        if not detail:
            raise SourceEvidenceError(409, "已采纳视觉证据详情已不可用，请重新观察并采纳。")
        contexts.append(
            AdoptedVisualEvidenceContext(
                id=record.id,
                ref=record.ref,
                position=record.position,
                summary=_coerce_text(detail.get("summary")),
                visible_text=_coerce_text(detail.get("visible_text")),
                confidence=_coerce_confidence(detail.get("confidence")),
                limitations=_coerce_string_list(detail.get("limitations")),
            )
        )
    return contexts


def _resource_can_be_visual_evidence(resource: SourceEvidenceResourceRecord) -> bool:
    return resource.resource_type in {"image", "attachment"}


def _resource_is_image_like(resource: SourceEvidenceResourceRecord) -> bool:
    if resource.resource_type == "image":
        return True
    if resource.resource_type != "attachment":
        return False
    filename = (resource.filename or "").lower()
    return resource.mime_type.startswith("image/") or filename.endswith(
        (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff")
    )


def _has_xls_conversion_failure(warnings: list[GenerationWarning]) -> bool:
    for warning in warnings:
        message = warning.message.lower()
        if ".xls" in message and "转换失败" in warning.message:
            return True
    return False


async def _vision_ai_unavailable(db: AsyncSession, *, project_id: int) -> bool:
    try:
        credential = await load_project_vision_credential(db, project_id)
        decrypt_vision_credential_key(credential)
    except (VisionAiProviderInvalid, VisionAiProviderNotConfigured):
        return True
    return False


def find_forbidden_visual_refs(
    value: Any,
    forbidden_refs: Iterable[str],
) -> list[str]:
    text = _visual_ref_scan_text(value)
    return [
        ref
        for ref in sorted({str(item) for item in forbidden_refs if str(item)}, key=len, reverse=True)
        if ref in text
    ]


def ensure_no_forbidden_visual_refs(
    value: Any,
    *,
    forbidden_refs: Iterable[str],
    status_code: int,
    message: str,
) -> None:
    hits = find_forbidden_visual_refs(value, forbidden_refs)
    if hits:
        raise SourceEvidenceError(
            status_code,
            f"{message} 未采纳视觉证据 ref：{', '.join(hits[:5])}。",
        )


def sanitize_forbidden_visual_refs(
    value: str,
    forbidden_refs: Iterable[str],
) -> str:
    sanitized = str(value or "")
    for ref in sorted({str(item) for item in forbidden_refs if str(item)}, key=len, reverse=True):
        sanitized = sanitized.replace(ref, "[未采纳视觉证据]")
    return sanitized


def _visual_ref_scan_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if hasattr(value, "model_dump"):
        try:
            value = value.model_dump(mode="json")
        except TypeError:
            value = value.model_dump()
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)


def _sanitize_warnings_for_visual_refs(
    warnings: list[GenerationWarning],
    forbidden_refs: Iterable[str],
) -> list[GenerationWarning]:
    return [
        warning.model_copy(
            update={
                "message": sanitize_forbidden_visual_refs(
                    warning.message,
                    forbidden_refs,
                )
            }
        )
        for warning in warnings
    ]


def _build_source_evidence_prompt_context(
    *,
    run: SourceEvidenceRunRecord,
    source_summary: str,
    ttl_status: str,
    parsed: ParsedSource | None,
    resources: list[SourceEvidenceResourceRecord],
    adopted_evidence: list[AdoptedVisualEvidenceContext],
    manifest: dict[str, Any],
    warnings: list[GenerationWarning],
) -> str:
    lines = [
        "Source Evidence 读取上下文：",
        f"- Run ID: {run.id}",
        f"- 来源摘要：{source_summary}",
        f"- TTL 状态：{ttl_status}",
        "读取范围：",
        *_source_scope_lines(parsed=parsed, manifest=manifest),
        "排除/限制：",
        *_source_exclusion_lines(warnings),
        "资源清单摘要：",
        *_source_resource_lines(resources),
        "已采纳视觉证据：",
        *_adopted_visual_evidence_lines(adopted_evidence),
        "未观察/未采纳限制：",
        (
            "- PlanningSnapshotResponse 中证据状态为 text/table 的文本/表格内容"
            "可以作为需求事实；pending_visual 只表示待观察资源位置。"
        ),
        (
            "- 图片/附件资源清单、文件名、位置、附近文字、download 状态、"
            "unobserved/observed-but-not-adopted 状态都不是已确认需求事实。"
        ),
        "- 不得把文件名、附近文字或未观察资源写成已确认需求依据。",
        "- 已观察但未出现在“已采纳视觉证据”列表中的 observation 不得作为需求事实。",
        "- 未观察/未采纳图片或附件只能写入 warnings、open_questions、remarks。",
    ]
    return "\n".join(lines)


def _build_source_evidence_export_summary(
    *,
    run: SourceEvidenceRunRecord,
    source_summary: str,
    ttl_status: str,
    parsed: ParsedSource | None,
    resources: list[SourceEvidenceResourceRecord],
    adopted_evidence: list[AdoptedVisualEvidenceContext],
    warnings: list[GenerationWarning],
) -> str:
    resource_counts = _resource_counts(resources)
    warning_text = "；".join(warning.message for warning in warnings[:5]) or "无"
    scope_text = "；".join(_source_scope_lines(parsed=parsed, manifest={})) or "未记录结构化读取范围"
    return "\n".join(
        [
            f"Source Evidence 摘要：Run ID={run.id}；{source_summary}",
            f"TTL 状态：{ttl_status}",
            (
                "读取范围："
                f"{scope_text}"
            ),
            (
                "资源统计："
                f"资源总数={resource_counts['total']}；"
                f"图片={resource_counts['image']}；"
                f"附件={resource_counts['attachment']}；"
                f"已下载={resource_counts['downloaded']}；"
                f"下载失败/待授权={resource_counts['failed_or_permission']}；"
                f"未观察/未采纳={resource_counts['unobserved']}"
            ),
            (
                "已采纳视觉证据："
                f"{_adopted_visual_evidence_export_text(adopted_evidence)}"
            ),
            "限制：未观察/未采纳的图片或附件不作为已确认需求事实。",
            f"warnings：{warning_text}",
        ]
    )


def _source_scope_lines(
    *,
    parsed: ParsedSource | None,
    manifest: dict[str, Any],
) -> list[str]:
    if parsed is None:
        doc_type = str(manifest.get("doc_type") or "unknown")
        counts = manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {}
        unit_count = counts.get("source_unit_count", 0) if isinstance(counts, dict) else 0
        return [f"- 类型={doc_type}；结构化片段数={unit_count}"]

    lines: list[str] = [f"- 类型={parsed.doc_type}；标题={parsed.title}"]
    for unit in parsed.source_units[:20]:
        metadata = unit.metadata if isinstance(unit.metadata, dict) else {}
        safe_parts = [
            f"kind={unit.kind}",
            f"title={unit.title or '无标题'}",
        ]
        for key in (
            "block_count",
            "row_count",
            "col_count",
            "non_empty_cell_count",
            "resource_count",
            "record_count",
        ):
            if metadata.get(key) not in (None, ""):
                safe_parts.append(f"{key}={metadata[key]}")
        if unit.cells:
            safe_parts.append(f"cells={len(unit.cells)}")
        if unit.rows:
            safe_parts.append(f"rows={len(unit.rows)}")
        lines.append("- " + "；".join(safe_parts))
    if len(parsed.source_units) > 20:
        lines.append(f"- 其余片段 {len(parsed.source_units) - 20} 个未展开。")
    return lines


def _source_exclusion_lines(warnings: list[GenerationWarning]) -> list[str]:
    if not warnings:
        return ["- 无额外排除项；仍按未观察/未采纳限制处理资源。"]
    return [f"- {warning.message}" for warning in warnings[:20]]


def _source_resource_lines(
    resources: list[SourceEvidenceResourceRecord],
) -> list[str]:
    counts = _resource_counts(resources)
    return [
        (
            "- "
            f"资源总数={counts['total']}；"
            f"图片={counts['image']}；"
            f"附件={counts['attachment']}；"
            f"已下载={counts['downloaded']}；"
            f"下载失败/待授权={counts['failed_or_permission']}；"
            f"未观察/未采纳={counts['unobserved']}"
        ),
        "- 未采纳图片/附件资源只参与状态统计，不展开 ref、文件名或位置。",
    ]


def _adopted_visual_evidence_lines(
    adopted_evidence: list[AdoptedVisualEvidenceContext],
) -> list[str]:
    if not adopted_evidence:
        return ["- 无。已观察但未采纳的 observation 不进入需求事实。"]
    lines: list[str] = []
    for item in adopted_evidence[:20]:
        limitation_text = "；".join(item.limitations) or "无"
        visible_text = item.visible_text or "未识别可见文字"
        confidence = "" if item.confidence is None else f"；confidence={item.confidence:.2f}"
        lines.append(
            "- "
            f"id={item.id}；"
            f"ref={item.ref}；"
            f"position={item.position}；"
            f"summary={item.summary or '无摘要'}；"
            f"visible_text={visible_text}{confidence}；"
            f"limitations={limitation_text}"
        )
    if len(adopted_evidence) > 20:
        lines.append(f"- 其余已采纳视觉证据 {len(adopted_evidence) - 20} 个未展开。")
    return lines


def _adopted_visual_evidence_export_text(
    adopted_evidence: list[AdoptedVisualEvidenceContext],
) -> str:
    if not adopted_evidence:
        return "无"
    parts = []
    for item in adopted_evidence[:10]:
        limitation_text = "；".join(item.limitations) or "无"
        parts.append(
            f"id={item.id}；ref={item.ref}；position={item.position}；"
            f"summary={item.summary or '无摘要'}；limitations={limitation_text}"
        )
    if len(adopted_evidence) > 10:
        parts.append(f"其余 {len(adopted_evidence) - 10} 个未展开")
    return "；".join(parts)


def _resource_counts(resources: list[SourceEvidenceResourceRecord]) -> dict[str, int]:
    return {
        "total": len(resources),
        "image": sum(1 for resource in resources if resource.resource_type == "image"),
        "attachment": sum(
            1 for resource in resources if resource.resource_type == "attachment"
        ),
        "downloaded": sum(
            1 for resource in resources if resource.download_status == "downloaded"
        ),
        "failed_or_permission": sum(
            1
            for resource in resources
            if resource.download_status in {"download_failed", "pending_permission"}
        ),
        "unobserved": sum(
            1
            for resource in resources
            if resource.status in {"unobserved", "observed", "pending"}
        ),
    }


def _deduplicate_warnings(
    warnings: list[GenerationWarning],
) -> list[GenerationWarning]:
    seen: set[tuple[str, str, str]] = set()
    result: list[GenerationWarning] = []
    for warning in warnings:
        key = (warning.source, warning.level, warning.message)
        if key in seen:
            continue
        seen.add(key)
        result.append(warning)
    return result


def _safe_resource_filename(
    filename: str,
    *,
    content_type: str,
    resource_type: str,
) -> str:
    safe_name = re.sub(r'[\\/:*?"<>|\s]+', "_", filename.strip()).strip("._ ")
    safe_name = safe_name or "resource"
    if "." in safe_name.rsplit("/", 1)[-1]:
        return safe_name[:180]
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    extension = mimetypes.guess_extension(mime) or (".png" if resource_type == "image" else ".bin")
    return f"{safe_name[:160]}{extension}"


def _safe_upload_filename(filename: str) -> str:
    raw_name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    safe_name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", raw_name).strip("._ ")
    return (safe_name or "uploaded-source")[:180]


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _read_observation_detail(
    *,
    project_id: int,
    run_id: int,
    observation_path: str,
) -> dict[str, Any]:
    if not observation_path:
        return {}
    try:
        payload = source_evidence_storage.read_source_evidence_json(
            project_id,
            run_id,
            observation_path,
        )
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(_coerce_text(item) for item in value if _coerce_text(item))
    return str(value).strip()


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [
            text
            for text in (_coerce_text(item) for item in value)
            if text
        ]
    text = _coerce_text(value)
    return [text] if text else []


def _coerce_confidence(value: Any) -> float | None:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, confidence))


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_aware_utc(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.UTC)
    return value.astimezone(datetime.UTC)


def _datetime_to_iso(value: datetime.datetime | None) -> str | None:
    if value is None:
        return None
    return _as_aware_utc(value).isoformat()
