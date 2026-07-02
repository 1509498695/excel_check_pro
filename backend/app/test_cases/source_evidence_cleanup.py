"""Source Evidence Run TTL 清理和最小审计。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import datetime
import hashlib
import json
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import (
    SourceEvidenceResourceRecord,
    SourceEvidenceRunRecord,
    SourceEvidenceVisualObservationRecord,
)
from backend.app.test_cases import source_evidence_storage
from backend.app.test_cases.source_evidence import (
    SourceEvidenceError,
    is_source_evidence_expired,
    source_evidence_now,
)


SOURCE_EVIDENCE_CLEANED_MESSAGE = "证据已过期或已清理，请重新读取来源。"
_WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"']+")
_UNIX_PATH_RE = re.compile(r"(?<!\w)/(?:[^\s\"']+/){1,}[^\s\"']*")
_URL_RE = re.compile(r"https?://[^\s\"']+", re.IGNORECASE)


@dataclass(frozen=True)
class SourceEvidenceCleanupRuns:
    """runtime cleanup 报告中的 Source Evidence 清理摘要。"""

    run_ids: list[int] = field(default_factory=list)
    resource_count: int = 0
    observation_count: int = 0
    cleaned_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def cleanup_source_evidence_run(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    cleaned_by: int | None,
    cleaned_at: datetime.datetime | None = None,
) -> dict[str, Any]:
    """清理单个 run 的敏感文件和敏感 DB 字段，保留最小审计。"""
    run = await _get_project_run(db, project_id=project_id, run_id=run_id)
    resources = await _list_resources(db, project_id=project_id, run_id=run_id)
    observations = await _list_observations(db, project_id=project_id, run_id=run_id)
    cleaned_at_value = _as_aware_utc(cleaned_at or source_evidence_now())

    if run.status == "cleaned" and run.minimal_audit_json:
        return _json_object(run.minimal_audit_json)

    summary = _build_minimal_audit(
        run=run,
        resources=resources,
        observations=observations,
        cleaned_by=cleaned_by,
        cleaned_at=cleaned_at_value,
    )
    cleanup_error = _delete_run_sensitive_files(project_id=project_id, run_id=run_id)
    if cleanup_error:
        summary["error_summary"] = _merge_error_summary(
            summary.get("error_summary"),
            f"清理文件失败：{cleanup_error}",
        )
    _scrub_run(run, summary=summary, cleaned_by=cleaned_by, cleaned_at=cleaned_at_value)
    _scrub_resources(resources, cleaned_at=cleaned_at_value)
    _scrub_observations(observations, cleaned_at=cleaned_at_value)
    await db.flush()
    return summary


async def collect_expired_source_evidence_runs(
    db: AsyncSession,
    *,
    now: datetime.datetime | None = None,
) -> SourceEvidenceCleanupRuns:
    """收集已过期但尚未 cleaned 的 Source Evidence Run。"""
    run_ids = await _expired_run_ids(db, now=now)
    if not run_ids:
        return SourceEvidenceCleanupRuns()
    resource_count = await _count_records(
        db,
        SourceEvidenceResourceRecord,
        SourceEvidenceResourceRecord.run_id.in_(run_ids),
    )
    observation_count = await _count_records(
        db,
        SourceEvidenceVisualObservationRecord,
        SourceEvidenceVisualObservationRecord.run_id.in_(run_ids),
    )
    return SourceEvidenceCleanupRuns(
        run_ids=run_ids,
        resource_count=resource_count,
        observation_count=observation_count,
    )


async def cleanup_expired_source_evidence_runs(
    db: AsyncSession,
    *,
    now: datetime.datetime | None = None,
    cleaned_by: int | None = None,
) -> SourceEvidenceCleanupRuns:
    """批量清理已过期 Source Evidence Run。"""
    collected = await collect_expired_source_evidence_runs(db, now=now)
    if not collected.run_ids:
        return collected
    cleaned_count = 0
    for run_id in collected.run_ids:
        result = await db.execute(
            select(SourceEvidenceRunRecord.project_id).where(
                SourceEvidenceRunRecord.id == run_id
            )
        )
        project_id = result.scalar_one_or_none()
        if project_id is None:
            continue
        await cleanup_source_evidence_run(
            db,
            project_id=project_id,
            run_id=run_id,
            cleaned_by=cleaned_by,
            cleaned_at=now,
        )
        cleaned_count += 1
    await db.flush()
    return SourceEvidenceCleanupRuns(
        run_ids=collected.run_ids,
        resource_count=collected.resource_count,
        observation_count=collected.observation_count,
        cleaned_count=cleaned_count,
    )


async def ensure_run_not_expired_or_cleanup(
    db: AsyncSession,
    run: SourceEvidenceRunRecord,
    *,
    cleaned_by: int | None = None,
    now: datetime.datetime | None = None,
    commit: bool = True,
) -> bool:
    """若 run 已过期则立即清理；返回 True 表示本次触发了清理。"""
    if run.status == "cleaned":
        return False
    if run.status != "expired" and not is_source_evidence_expired(run, now=now):
        return False
    await cleanup_source_evidence_run(
        db,
        project_id=run.project_id,
        run_id=run.id,
        cleaned_by=cleaned_by,
        cleaned_at=now,
    )
    if commit:
        await db.commit()
        await db.refresh(run)
    return True


async def list_source_evidence_cleanup_audits(
    db: AsyncSession,
    *,
    project_id: int,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """列出项目内 Source Evidence Cleanup Audit Summary。"""
    bounded_limit = max(1, min(200, limit))
    bounded_offset = max(0, offset)
    count_result = await db.execute(
        select(func.count(SourceEvidenceRunRecord.id)).where(
            SourceEvidenceRunRecord.project_id == project_id,
            SourceEvidenceRunRecord.status == "cleaned",
        )
    )
    total = int(count_result.scalar_one() or 0)
    result = await db.execute(
        select(SourceEvidenceRunRecord)
        .where(
            SourceEvidenceRunRecord.project_id == project_id,
            SourceEvidenceRunRecord.status == "cleaned",
        )
        .order_by(
            SourceEvidenceRunRecord.cleaned_at.desc(),
            SourceEvidenceRunRecord.id.desc(),
        )
        .limit(bounded_limit)
        .offset(bounded_offset)
    )
    items = []
    for run in result.scalars().all():
        payload = _json_object(run.minimal_audit_json)
        if not payload:
            payload = _fallback_audit(run)
        items.append(payload)
    return items, total


async def _get_project_run(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> SourceEvidenceRunRecord:
    result = await db.execute(
        select(SourceEvidenceRunRecord).where(
            SourceEvidenceRunRecord.id == run_id,
            SourceEvidenceRunRecord.project_id == project_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise SourceEvidenceError(404, "Source Evidence Run 不存在。")
    return run


async def _list_resources(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> list[SourceEvidenceResourceRecord]:
    result = await db.execute(
        select(SourceEvidenceResourceRecord)
        .where(
            SourceEvidenceResourceRecord.project_id == project_id,
            SourceEvidenceResourceRecord.run_id == run_id,
        )
        .order_by(
            SourceEvidenceResourceRecord.created_at.asc(),
            SourceEvidenceResourceRecord.id.asc(),
        )
    )
    return list(result.scalars().all())


async def _list_observations(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> list[SourceEvidenceVisualObservationRecord]:
    result = await db.execute(
        select(SourceEvidenceVisualObservationRecord)
        .where(
            SourceEvidenceVisualObservationRecord.project_id == project_id,
            SourceEvidenceVisualObservationRecord.run_id == run_id,
        )
        .order_by(
            SourceEvidenceVisualObservationRecord.created_at.asc(),
            SourceEvidenceVisualObservationRecord.id.asc(),
        )
    )
    return list(result.scalars().all())


async def _expired_run_ids(
    db: AsyncSession,
    *,
    now: datetime.datetime | None,
) -> list[int]:
    cutoff = _as_aware_utc(now or source_evidence_now()).replace(tzinfo=None)
    result = await db.execute(
        select(SourceEvidenceRunRecord.id)
        .where(
            SourceEvidenceRunRecord.status != "cleaned",
            SourceEvidenceRunRecord.expires_at <= cutoff,
        )
        .order_by(SourceEvidenceRunRecord.expires_at.asc(), SourceEvidenceRunRecord.id.asc())
    )
    return list(result.scalars().all())


async def _count_records(db: AsyncSession, model: type[Any], where_clause: Any) -> int:
    result = await db.execute(select(func.count(model.id)).where(where_clause))
    return int(result.scalar_one() or 0)


def _build_minimal_audit(
    *,
    run: SourceEvidenceRunRecord,
    resources: list[SourceEvidenceResourceRecord],
    observations: list[SourceEvidenceVisualObservationRecord],
    cleaned_by: int | None,
    cleaned_at: datetime.datetime,
) -> dict[str, Any]:
    source_identifier = _source_identifier_fingerprint(run)
    error_summary = _minimal_error_summary(run.error_summary or _manifest_error_summary(run))
    return {
        "run_id": run.id,
        "project_id": run.project_id,
        "source_type": run.source_type,
        "source_identifier": source_identifier,
        "source_title": run.source_title,
        "status_before": run.status,
        "status_after": "cleaned",
        "created_by": run.created_by,
        "cleaned_by": cleaned_by,
        "created_at": _datetime_to_iso(run.created_at),
        "expires_at": _datetime_to_iso(run.expires_at),
        "cleaned_at": _datetime_to_iso(cleaned_at),
        "error_summary": error_summary,
        "counts": {
            "resource_count": len(resources),
            "observation_count": len(observations),
            "adopted_observation_count": sum(
                1 for observation in observations if observation.status == "adopted"
            ),
        },
        "resources": [
            {
                "resource_id": resource.id,
                "run_id": resource.run_id,
                "project_id": resource.project_id,
                "ref": resource.ref,
                "type": resource.resource_type,
                "filename": resource.filename,
                "status": resource.status,
                "download_status": resource.download_status,
                "created_at": _datetime_to_iso(resource.created_at),
                "cleaned_at": _datetime_to_iso(cleaned_at),
            }
            for resource in resources
        ],
    }


def _delete_run_sensitive_files(*, project_id: int, run_id: int) -> str:
    try:
        source_evidence_storage.clear_source_evidence_run_dir(
            project_id=project_id,
            run_id=run_id,
        )
    except (OSError, source_evidence_storage.SourceEvidenceStorageError) as exc:
        return _minimal_error_summary(str(exc))
    return ""


def _scrub_run(
    run: SourceEvidenceRunRecord,
    *,
    summary: dict[str, Any],
    cleaned_by: int | None,
    cleaned_at: datetime.datetime,
) -> None:
    run.status = "cleaned"
    run.source_url = ""
    run.source_token = ""
    run.source_identifier = str(summary.get("source_identifier") or "")
    run.storage_path = ""
    run.error_summary = ""
    run.raw_manifest_json = "{}"
    run.minimal_audit_json = json.dumps(summary, ensure_ascii=False)
    run.cleaned_by = cleaned_by
    run.cleaned_at = cleaned_at


def _scrub_resources(
    resources: list[SourceEvidenceResourceRecord],
    *,
    cleaned_at: datetime.datetime,
) -> None:
    for resource in resources:
        resource.file_token = ""
        resource.local_path = ""
        resource.observation_json = ""
        resource.visual_packet_path = ""
        resource.metadata_json = "{}"
        resource.status = "expired"
        resource.download_status = "expired"
        resource.cleaned_at = cleaned_at


def _scrub_observations(
    observations: list[SourceEvidenceVisualObservationRecord],
    *,
    cleaned_at: datetime.datetime,
) -> None:
    for observation in observations:
        observation.status = "cleaned"
        observation.observation_path = ""
        observation.cleaned_at = cleaned_at


def _source_identifier_fingerprint(run: SourceEvidenceRunRecord) -> str:
    raw = (run.source_identifier or run.source_token or run.source_url or "").strip()
    if not raw:
        return ""
    if raw.startswith("sha256:"):
        return raw
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"sha256:{digest}"


def _minimal_error_summary(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = _URL_RE.sub("[url已脱敏]", text)
    text = _WINDOWS_PATH_RE.sub("[本地路径已脱敏]", text)
    text = _UNIX_PATH_RE.sub("[本地路径已脱敏]", text)
    text = re.sub(
        r"(?i)\b(app_secret|tenant_access_token|user_access_token|authorization|api[_-]?key|oauth[_ -]?code|code)\s*[:=]\s*\S+",
        "[redacted]",
        text,
    )
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "[redacted]", text)
    return text[:300]


def _merge_error_summary(existing: object, addition: str) -> str:
    parts = [str(existing or "").strip(), str(addition or "").strip()]
    return _minimal_error_summary("；".join(part for part in parts if part))


def _manifest_error_summary(run: SourceEvidenceRunRecord) -> str:
    payload = _json_object(run.raw_manifest_json)
    warnings = payload.get("warnings")
    if not isinstance(warnings, list):
        return ""
    messages = [
        str(item.get("message") or "")
        for item in warnings
        if isinstance(item, dict) and item.get("message")
    ]
    return "；".join(messages[:3])


def _fallback_audit(run: SourceEvidenceRunRecord) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "project_id": run.project_id,
        "source_type": run.source_type,
        "source_identifier": run.source_identifier,
        "source_title": run.source_title,
        "status_before": "",
        "status_after": run.status,
        "created_by": run.created_by,
        "cleaned_by": run.cleaned_by,
        "created_at": _datetime_to_iso(run.created_at),
        "expires_at": _datetime_to_iso(run.expires_at),
        "cleaned_at": _datetime_to_iso(run.cleaned_at),
        "error_summary": "",
        "counts": {},
        "resources": [],
    }


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
