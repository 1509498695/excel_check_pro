"""V3 Generation Run service skeleton.

本模块只登记、查询和维护异步生成运行状态，不调用 AI，也不生成真实测试用例。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import datetime
import json
import re
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import (
    SourceEvidenceRunRecord,
    TEST_CASE_GENERATION_RUN_STATUSES,
    TestCaseCoverageAuditRecord,
    TestCaseGenerationCaseRecord,
    TestCaseGenerationChunkRecord,
    TestCaseGenerationRunRecord,
    TestCaseRequirementAtomRecord,
)
from backend.app.test_cases.schemas import (
    TestCaseGenerationCaseListResponse,
    TestCaseGenerationCaseResponse,
    TestCaseGenerationRunCancelResponse,
    TestCaseGenerationRunCreateRequest,
    TestCaseGenerationRunResponse,
    TestCaseGenerationRunRetryFailedChunksResponse,
    TestCaseRequirementAtomListResponse,
    TestCaseRequirementAtomResponse,
)
from backend.app.test_cases.source_evidence import is_source_evidence_expired


GENERATION_RUN_ACTIVE_STATUSES = frozenset(
    {
        "queued",
        "reading",
        "chunking",
        "extracting_atoms",
        "merging_atoms",
        "blueprinting",
        "generating_cases",
        "auditing_coverage",
        "supplementing",
        "auditing_quality",
        "repairing_cases",
        "rendering_artifacts",
    }
)
GENERATION_RUN_TERMINAL_STATUSES = frozenset(
    {
        "completed",
        "partial_completed",
        "failed",
        "cancelled",
        "expired",
    }
)
GENERATION_RUN_COMPLETED_STATUSES = frozenset({"completed", "partial_completed"})
GENERATION_RUN_STAGE_ORDER = tuple(
    status
    for status in TEST_CASE_GENERATION_RUN_STATUSES
    if status in GENERATION_RUN_ACTIVE_STATUSES
)

NO_ATOMS_MESSAGE = "Generation Run 尚无需求原子结果。"
NO_CASES_MESSAGE = "Generation Run 尚无用例结果。"
NO_EXPORT_MESSAGE = "Generation Run 尚未生成可导出的用例结果。"
EXPIRED_DETAILS_MESSAGE = "Generation Run 已过期，详情已清理。"
CANNOT_CANCEL_MESSAGE = "当前 Generation Run 状态不允许取消。"
CANNOT_ADVANCE_MESSAGE = "当前 Generation Run 状态不允许继续推进。"
RUN_NOT_EXPORTABLE_MESSAGE = "当前 Generation Run 状态不可导出。"
NO_RETRY_CHUNKS_MESSAGE = "当前 Generation Run 没有可重试的失败 chunk。"
STRICT_EXPORT_COVERAGE_GAP_MESSAGE = "严格模式下存在覆盖缺口，不能导出。"

_WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"']+")
_UNIX_PATH_RE = re.compile(r"(?<!\w)/(?:[^\s\"']+/){1,}[^\s\"']*")
_URL_RE = re.compile(r"https?://[^\s\"']+", re.IGNORECASE)
_SENSITIVE_KEY_TERMS = (
    "prompt",
    "raw_response",
    "rawresponse",
    "provider_response",
    "providerresponse",
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "authorization",
)
_SENSITIVE_TEXT_TERMS = (
    "provider_response",
    "provider response",
    "raw_response",
    "raw response",
    "tenant_access_token",
    "access_token",
    "prompt",
)


@dataclass(frozen=True)
class GenerationRunCleanupRuns:
    """runtime cleanup 报告中的 Generation Run 清理摘要。"""

    run_ids: list[int] = field(default_factory=list)
    chunk_count: int = 0
    atom_count: int = 0
    case_count: int = 0
    audit_count: int = 0
    cleaned_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GenerationRunError(RuntimeError):
    """Generation Run service 错误，API 层按 status_code 转 HTTPException。"""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def generation_run_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _as_aware_utc(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.UTC)
    return value.astimezone(datetime.UTC)


def _datetime_to_iso(value: datetime.datetime | None) -> str | None:
    if value is None:
        return None
    return _as_aware_utc(value).isoformat()


def _json_value(value: str, default: Any) -> Any:
    if not value:
        return default
    try:
        loaded = json.loads(value)
    except (TypeError, ValueError):
        return default
    return loaded if isinstance(loaded, type(default)) else default


def _json_list(value: str) -> list[Any]:
    loaded = _json_value(value, [])
    return loaded if isinstance(loaded, list) else []


def _json_object(value: str) -> dict[str, Any]:
    loaded = _json_value(value, {})
    return loaded if isinstance(loaded, dict) else {}


def _is_run_expired(
    run: TestCaseGenerationRunRecord,
    *,
    now: datetime.datetime | None = None,
) -> bool:
    return _as_aware_utc(run.expires_at) <= _as_aware_utc(now or generation_run_now())


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(term in normalized for term in _SENSITIVE_KEY_TERMS)


def _minimal_error_summary(value: str | None) -> str:
    if not value:
        return ""
    sanitized = _URL_RE.sub("[url]", str(value))
    sanitized = _WINDOWS_PATH_RE.sub("[path]", sanitized)
    sanitized = _UNIX_PATH_RE.sub("[path]", sanitized)
    sanitized = re.sub(
        r"(?i)\b[\w.-]*(token|secret|password|api_key)[\w.-]*\s*=\s*[^\s,;]+",
        "[redacted]",
        sanitized,
    )
    for term in _SENSITIVE_TEXT_TERMS:
        sanitized = re.sub(re.escape(term), "[redacted]", sanitized, flags=re.IGNORECASE)
    return sanitized[:500]


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_payload(item)
            for key, item in value.items()
            if not _is_sensitive_key(str(key))
        }
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, str):
        return _minimal_error_summary(value)
    if isinstance(value, int | float | bool) or value is None:
        return value
    return _minimal_error_summary(str(value))


async def _count_records(db: AsyncSession, model: type[Any], where_clause: Any) -> int:
    result = await db.execute(select(func.count(model.id)).where(where_clause))
    return int(result.scalar_one() or 0)


async def _generation_run_detail_counts(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> dict[str, int]:
    return {
        "chunk_count": await _count_records(
            db,
            TestCaseGenerationChunkRecord,
            (TestCaseGenerationChunkRecord.project_id == project_id)
            & (TestCaseGenerationChunkRecord.run_id == run_id),
        ),
        "atom_detail_count": await _count_records(
            db,
            TestCaseRequirementAtomRecord,
            (TestCaseRequirementAtomRecord.project_id == project_id)
            & (TestCaseRequirementAtomRecord.run_id == run_id),
        ),
        "case_detail_count": await _count_records(
            db,
            TestCaseGenerationCaseRecord,
            (TestCaseGenerationCaseRecord.project_id == project_id)
            & (TestCaseGenerationCaseRecord.run_id == run_id),
        ),
        "audit_count": await _count_records(
            db,
            TestCaseCoverageAuditRecord,
            (TestCaseCoverageAuditRecord.project_id == project_id)
            & (TestCaseCoverageAuditRecord.run_id == run_id),
        ),
    }


def _build_minimal_audit(
    *,
    run: TestCaseGenerationRunRecord,
    status_before_expired: str | None,
    cleaned_at: datetime.datetime,
    detail_counts: dict[str, int],
) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "project_id": run.project_id,
        "source_evidence_run_id": run.source_evidence_run_id,
        "planning_sheet_name": run.planning_sheet_name,
        "status": run.status,
        "status_before_expired": status_before_expired,
        "created_by": run.created_by,
        "created_at": _datetime_to_iso(run.created_at),
        "completed_at": _datetime_to_iso(run.completed_at),
        "expired_at": _datetime_to_iso(run.expired_at),
        "cleaned_at": _datetime_to_iso(cleaned_at),
        "error_summary": _minimal_error_summary(run.error_summary),
        "counts": {
            "total_chunks": run.total_chunks,
            "completed_chunks": run.completed_chunks,
            "failed_chunks": run.failed_chunks,
            "atom_count": run.atom_count,
            "case_count": run.case_count,
            "warning_count": run.warning_count,
            **detail_counts,
        },
    }


async def cleanup_generation_run_details(
    db: AsyncSession,
    *,
    run: TestCaseGenerationRunRecord,
    cleaned_at: datetime.datetime | None = None,
    status_before_expired: str | None = None,
) -> dict[str, Any]:
    """清理单个 Generation Run 的详细数据，保留主表最小审计。"""
    from backend.app.test_cases.generation_artifact_storage import (
        clear_generation_run_artifacts,
    )

    cleaned_at_value = _as_aware_utc(cleaned_at or generation_run_now())
    if run.cleaned_at is not None and run.minimal_audit_json:
        return _json_object(run.minimal_audit_json)

    detail_counts = await _generation_run_detail_counts(
        db,
        project_id=run.project_id,
        run_id=run.id,
    )
    audit = _build_minimal_audit(
        run=run,
        status_before_expired=status_before_expired,
        cleaned_at=cleaned_at_value,
        detail_counts=detail_counts,
    )
    for model in (
        TestCaseRequirementAtomRecord,
        TestCaseGenerationCaseRecord,
        TestCaseCoverageAuditRecord,
        TestCaseGenerationChunkRecord,
    ):
        await db.execute(
            delete(model).where(
                model.project_id == run.project_id,
                model.run_id == run.id,
            )
        )
    clear_generation_run_artifacts(project_id=run.project_id, run_id=run.id)
    run.stage_payload_json = "{}"
    run.minimal_audit_json = json.dumps(audit, ensure_ascii=False)
    run.cleaned_at = cleaned_at_value
    run.error_summary = _minimal_error_summary(run.error_summary)
    await db.flush()
    return audit


async def mark_generation_run_expired_if_needed(
    db: AsyncSession,
    run: TestCaseGenerationRunRecord,
    *,
    now: datetime.datetime | None = None,
    cleanup: bool = True,
) -> bool:
    """TTL 到期后把任意非 expired run 暴露为 expired，并可立即清理详情。"""
    current_time = _as_aware_utc(now or generation_run_now())
    if run.status == "expired":
        if cleanup and run.cleaned_at is None:
            await cleanup_generation_run_details(
                db,
                run=run,
                cleaned_at=current_time,
                status_before_expired=None,
            )
        return False
    if not _is_run_expired(run, now=current_time):
        return False

    previous_status = run.status
    run.status = "expired"
    run.expired_at = run.expired_at or current_time
    if cleanup:
        await cleanup_generation_run_details(
            db,
            run=run,
            cleaned_at=current_time,
            status_before_expired=previous_status,
        )
    await db.flush()
    return True


def _run_response(run: TestCaseGenerationRunRecord) -> TestCaseGenerationRunResponse:
    reference_ids = [
        int(item)
        for item in _json_list(run.reference_ids_json)
        if isinstance(item, int) or (isinstance(item, str) and item.isdigit())
    ]
    return TestCaseGenerationRunResponse(
        id=run.id,
        project_id=run.project_id,
        source_evidence_run_id=run.source_evidence_run_id,
        created_by=run.created_by,
        cancelled_by=run.cancelled_by,
        status=run.status,
        planning_sheet_name=run.planning_sheet_name,
        reference_ids=reference_ids,
        primary_reference_id=run.primary_reference_id,
        primary_reference_sheet_name=run.primary_reference_sheet_name,
        strict_mode=run.strict_mode,
        total_chunks=run.total_chunks,
        completed_chunks=run.completed_chunks,
        failed_chunks=run.failed_chunks,
        atom_count=run.atom_count,
        case_count=run.case_count,
        warning_count=run.warning_count,
        error_summary=run.error_summary,
        warnings=_json_list(run.warnings_json),
        stage_payload=_json_object(run.stage_payload_json),
        artifacts=[
            item
            for item in (
                _json_object(run.stage_payload_json)
                .get("rendering_artifacts", {})
                .get("items", [])
                if isinstance(
                    _json_object(run.stage_payload_json).get("rendering_artifacts"),
                    dict,
                )
                else []
            )
            if isinstance(item, dict)
        ],
        expires_at=_datetime_to_iso(run.expires_at),
        completed_at=_datetime_to_iso(run.completed_at),
        cancelled_at=_datetime_to_iso(run.cancelled_at),
        expired_at=_datetime_to_iso(run.expired_at),
        cleaned_at=_datetime_to_iso(run.cleaned_at),
        created_at=_datetime_to_iso(run.created_at),
        updated_at=_datetime_to_iso(run.updated_at),
    )


async def get_project_generation_run(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    now: datetime.datetime | None = None,
    cleanup: bool = True,
) -> TestCaseGenerationRunRecord:
    result = await db.execute(
        select(TestCaseGenerationRunRecord).where(
            TestCaseGenerationRunRecord.project_id == project_id,
            TestCaseGenerationRunRecord.id == run_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise GenerationRunError(404, "Generation Run 不存在或不属于当前项目。")
    await mark_generation_run_expired_if_needed(db, run, now=now, cleanup=cleanup)
    await db.refresh(run)
    return run


async def _get_project_source_evidence_run(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> SourceEvidenceRunRecord:
    result = await db.execute(
        select(SourceEvidenceRunRecord).where(
            SourceEvidenceRunRecord.project_id == project_id,
            SourceEvidenceRunRecord.id == run_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise GenerationRunError(404, "Source Evidence Run 不存在或不属于当前项目。")
    if run.status in {"cleaned", "expired"} or is_source_evidence_expired(run):
        raise GenerationRunError(409, "证据已过期或已清理，请重新读取来源。")
    return run


async def create_generation_run(
    db: AsyncSession,
    *,
    project_id: int,
    created_by: int | None,
    payload: TestCaseGenerationRunCreateRequest,
) -> TestCaseGenerationRunResponse:
    """创建 queued Generation Run，不触发任何生成任务。"""
    await _get_project_source_evidence_run(
        db,
        project_id=project_id,
        run_id=payload.source_evidence_run_id,
    )
    run = TestCaseGenerationRunRecord(
        project_id=project_id,
        source_evidence_run_id=payload.source_evidence_run_id,
        created_by=created_by,
        status="queued",
        planning_sheet_name=payload.planning_sheet_name,
        reference_ids_json=json.dumps(payload.reference_ids, ensure_ascii=False),
        primary_reference_id=payload.primary_reference_id,
        primary_reference_sheet_name=payload.primary_reference_sheet_name,
        strict_mode=payload.strict_mode,
        stage_payload_json="{}",
        minimal_audit_json="{}",
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    return _run_response(run)


async def get_generation_run_response(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> TestCaseGenerationRunResponse:
    run = await get_project_generation_run(db, project_id=project_id, run_id=run_id)
    return _run_response(run)


async def cancel_generation_run(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    cancelled_by: int | None,
) -> TestCaseGenerationRunCancelResponse:
    run = await get_project_generation_run(db, project_id=project_id, run_id=run_id)
    if run.status in GENERATION_RUN_TERMINAL_STATUSES:
        raise GenerationRunError(409, CANNOT_CANCEL_MESSAGE)
    if run.status not in GENERATION_RUN_ACTIVE_STATUSES:
        raise GenerationRunError(409, CANNOT_CANCEL_MESSAGE)
    run.status = "cancelled"
    run.cancelled_by = cancelled_by
    run.cancelled_at = generation_run_now()
    await db.flush()
    await db.refresh(run)
    return TestCaseGenerationRunCancelResponse.model_validate(
        _run_response(run).model_dump(mode="json")
    )


def _status_index(status: str) -> int:
    try:
        return GENERATION_RUN_STAGE_ORDER.index(status)
    except ValueError:
        return -1


async def update_generation_run_stage(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    status: str,
    stage_payload: dict[str, Any] | None = None,
    error_summary: str | None = None,
    total_chunks: int | None = None,
    completed_chunks: int | None = None,
    failed_chunks: int | None = None,
    atom_count: int | None = None,
    case_count: int | None = None,
    warning_count: int | None = None,
) -> TestCaseGenerationRunResponse:
    """推进 run 状态或记录终态摘要，不触发任何 worker。"""
    if status not in TEST_CASE_GENERATION_RUN_STATUSES:
        raise GenerationRunError(400, "Generation Run 状态无效。")
    run = await get_project_generation_run(db, project_id=project_id, run_id=run_id)
    if run.status in GENERATION_RUN_TERMINAL_STATUSES:
        raise GenerationRunError(409, CANNOT_ADVANCE_MESSAGE)
    if status in GENERATION_RUN_ACTIVE_STATUSES:
        current_index = _status_index(run.status)
        target_index = _status_index(status)
        if target_index < current_index:
            raise GenerationRunError(409, "当前 Generation Run 状态不允许回退。")

    run.status = status
    if status in GENERATION_RUN_COMPLETED_STATUSES:
        run.completed_at = run.completed_at or generation_run_now()
    if status == "failed" and error_summary:
        run.error_summary = _minimal_error_summary(error_summary)
    elif error_summary is not None:
        run.error_summary = _minimal_error_summary(error_summary)
    if stage_payload is not None:
        run.stage_payload_json = json.dumps(_sanitize_payload(stage_payload), ensure_ascii=False)

    for attr_name, value in (
        ("total_chunks", total_chunks),
        ("completed_chunks", completed_chunks),
        ("failed_chunks", failed_chunks),
        ("atom_count", atom_count),
        ("case_count", case_count),
        ("warning_count", warning_count),
    ):
        if value is not None:
            setattr(run, attr_name, max(0, int(value)))

    await db.flush()
    await db.refresh(run)
    return _run_response(run)


async def retry_failed_generation_chunks(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> TestCaseGenerationRunRetryFailedChunksResponse:
    run = await get_project_generation_run(db, project_id=project_id, run_id=run_id)
    if run.status == "expired":
        raise GenerationRunError(409, EXPIRED_DETAILS_MESSAGE)
    if run.status in (GENERATION_RUN_TERMINAL_STATUSES - {"partial_completed"}):
        raise GenerationRunError(409, CANNOT_ADVANCE_MESSAGE)

    failed_chunks_result = await db.execute(
        select(TestCaseGenerationChunkRecord).where(
            TestCaseGenerationChunkRecord.project_id == project_id,
            TestCaseGenerationChunkRecord.run_id == run.id,
            TestCaseGenerationChunkRecord.status == "failed",
        )
    )
    failed_chunks = list(failed_chunks_result.scalars())
    if not failed_chunks:
        raise GenerationRunError(409, NO_RETRY_CHUNKS_MESSAGE)

    for chunk in failed_chunks:
        chunk.status = "queued"
        chunk.retry_count += 1
        chunk.error_summary = ""
    run.status = "chunking"
    run.completed_at = None
    run.failed_chunks = max(0, run.failed_chunks - len(failed_chunks))
    await db.flush()
    await db.refresh(run)
    return TestCaseGenerationRunRetryFailedChunksResponse(
        run_id=run.id,
        status=run.status,
        retried_chunk_count=len(failed_chunks),
    )


async def list_generation_run_atoms(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> TestCaseRequirementAtomListResponse:
    run = await get_project_generation_run(db, project_id=project_id, run_id=run_id)
    if run.status == "expired":
        raise GenerationRunError(409, EXPIRED_DETAILS_MESSAGE)
    result = await db.execute(
        select(TestCaseRequirementAtomRecord)
        .where(
            TestCaseRequirementAtomRecord.project_id == project_id,
            TestCaseRequirementAtomRecord.run_id == run.id,
        )
        .order_by(TestCaseRequirementAtomRecord.id)
    )
    atoms = list(result.scalars())
    if not atoms:
        raise GenerationRunError(409, NO_ATOMS_MESSAGE)
    items = [
        TestCaseRequirementAtomResponse(
            id=atom.id,
            atom_id=atom.atom_id,
            atom_type=atom.atom_type,
            requirement_text=atom.requirement_text,
            source_sheet_name=atom.source_sheet_name,
            source_row_start=atom.source_row_start,
            source_row_end=atom.source_row_end,
            source_columns=[str(item) for item in _json_list(atom.source_columns_json)],
            visual_evidence_refs=[
                str(item) for item in _json_list(atom.visual_evidence_refs_json)
            ],
            confidence=atom.confidence,
            coverage_status=atom.coverage_status,
        )
        for atom in atoms
    ]
    return TestCaseRequirementAtomListResponse(items=items, total=len(items))


async def list_generation_run_cases(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> TestCaseGenerationCaseListResponse:
    run = await get_project_generation_run(db, project_id=project_id, run_id=run_id)
    if run.status == "expired":
        raise GenerationRunError(409, EXPIRED_DETAILS_MESSAGE)
    result = await db.execute(
        select(TestCaseGenerationCaseRecord)
        .where(
            TestCaseGenerationCaseRecord.project_id == project_id,
            TestCaseGenerationCaseRecord.run_id == run.id,
        )
        .order_by(TestCaseGenerationCaseRecord.id)
    )
    cases = list(result.scalars())
    if not cases:
        raise GenerationRunError(409, NO_CASES_MESSAGE)
    items = [
        TestCaseGenerationCaseResponse(
            id=case.id,
            case_id=case.case_id,
            fields=_json_object(case.fields_json),
            atom_refs=[str(item) for item in _json_list(case.atom_refs_json)],
            status=case.status,
        )
        for case in cases
    ]
    return TestCaseGenerationCaseListResponse(items=items, total=len(items))


async def build_generation_run_export_placeholder(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> dict[str, Any]:
    run = await get_project_generation_run(db, project_id=project_id, run_id=run_id)
    if run.status == "expired":
        raise GenerationRunError(409, EXPIRED_DETAILS_MESSAGE)
    if run.status in {"cancelled", "failed"}:
        raise GenerationRunError(409, RUN_NOT_EXPORTABLE_MESSAGE)
    if run.status not in GENERATION_RUN_COMPLETED_STATUSES:
        raise GenerationRunError(409, NO_EXPORT_MESSAGE)
    audit = (
        await db.execute(
            select(TestCaseCoverageAuditRecord).where(
                TestCaseCoverageAuditRecord.project_id == project_id,
                TestCaseCoverageAuditRecord.run_id == run.id,
            )
        )
    ).scalar_one_or_none()
    if run.strict_mode and audit is not None and audit.uncovered_atoms > 0:
        raise GenerationRunError(409, STRICT_EXPORT_COVERAGE_GAP_MESSAGE)
    result = await db.execute(
        select(TestCaseGenerationCaseRecord.id).where(
            TestCaseGenerationCaseRecord.project_id == project_id,
            TestCaseGenerationCaseRecord.run_id == run.id,
        )
    )
    case_ids = list(result.scalars())
    if not case_ids:
        raise GenerationRunError(409, NO_EXPORT_MESSAGE)
    return {
        "run_id": run.id,
        "case_count": len(case_ids),
        "status": run.status,
        "audit_summary": _audit_summary_payload(audit),
        "export_limitations": _json_list(audit.export_limitations_json) if audit else [],
        "warnings": _json_list(audit.warnings_json) if audit else [],
    }


def _audit_summary_payload(audit: TestCaseCoverageAuditRecord | None) -> dict[str, Any]:
    if audit is None:
        return {}
    return {
        "status": audit.status,
        "total_atoms": audit.total_atoms,
        "covered_atoms": audit.covered_atoms,
        "uncovered_atoms": audit.uncovered_atoms,
        "failed_chunk_count": audit.failed_chunk_count,
        "unfounded_case_count": audit.unfounded_case_count,
    }


async def _expired_run_ids(
    db: AsyncSession,
    *,
    now: datetime.datetime | None = None,
) -> list[int]:
    cutoff = _as_aware_utc(now or generation_run_now()).replace(tzinfo=None)
    result = await db.execute(
        select(TestCaseGenerationRunRecord.id)
        .where(
            TestCaseGenerationRunRecord.cleaned_at.is_(None),
            TestCaseGenerationRunRecord.expires_at <= cutoff,
        )
        .order_by(
            TestCaseGenerationRunRecord.expires_at.asc(),
            TestCaseGenerationRunRecord.id.asc(),
        )
    )
    return list(result.scalars().all())


async def collect_expired_generation_runs(
    db: AsyncSession,
    *,
    now: datetime.datetime | None = None,
) -> GenerationRunCleanupRuns:
    """收集已过期但尚未清理详情的 Generation Run。"""
    run_ids = await _expired_run_ids(db, now=now)
    if not run_ids:
        return GenerationRunCleanupRuns()
    chunk_count = await _count_records(
        db,
        TestCaseGenerationChunkRecord,
        TestCaseGenerationChunkRecord.run_id.in_(run_ids),
    )
    atom_count = await _count_records(
        db,
        TestCaseRequirementAtomRecord,
        TestCaseRequirementAtomRecord.run_id.in_(run_ids),
    )
    case_count = await _count_records(
        db,
        TestCaseGenerationCaseRecord,
        TestCaseGenerationCaseRecord.run_id.in_(run_ids),
    )
    audit_count = await _count_records(
        db,
        TestCaseCoverageAuditRecord,
        TestCaseCoverageAuditRecord.run_id.in_(run_ids),
    )
    return GenerationRunCleanupRuns(
        run_ids=run_ids,
        chunk_count=chunk_count,
        atom_count=atom_count,
        case_count=case_count,
        audit_count=audit_count,
    )


async def cleanup_expired_generation_runs(
    db: AsyncSession,
    *,
    now: datetime.datetime | None = None,
) -> GenerationRunCleanupRuns:
    """批量过期并清理 Generation Run 详细数据。"""
    collected = await collect_expired_generation_runs(db, now=now)
    if not collected.run_ids:
        return collected
    current_time = _as_aware_utc(now or generation_run_now())
    cleaned_count = 0
    for run_id in collected.run_ids:
        result = await db.execute(
            select(TestCaseGenerationRunRecord).where(TestCaseGenerationRunRecord.id == run_id)
        )
        run = result.scalar_one_or_none()
        if run is None:
            continue
        await mark_generation_run_expired_if_needed(
            db,
            run,
            now=current_time,
            cleanup=True,
        )
        cleaned_count += 1
    await db.flush()
    return GenerationRunCleanupRuns(
        run_ids=collected.run_ids,
        chunk_count=collected.chunk_count,
        atom_count=collected.atom_count,
        case_count=collected.case_count,
        audit_count=collected.audit_count,
        cleaned_count=cleaned_count,
    )


def validate_generation_run_statuses() -> None:
    """启动期无需调用；给测试和维护者一个固定状态枚举对齐点。"""
    if set(TEST_CASE_GENERATION_RUN_STATUSES) != (
        GENERATION_RUN_ACTIVE_STATUSES | GENERATION_RUN_TERMINAL_STATUSES
    ):
        raise RuntimeError("Generation Run 状态枚举未对齐")
