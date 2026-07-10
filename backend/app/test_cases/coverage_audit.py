"""Coverage Audit and one-pass supplement for V3 Generation Runs."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import (
    TestCaseCoverageAuditRecord,
    TestCaseGenerationCaseRecord,
    TestCaseGenerationChunkRecord,
    TestCaseGenerationRunRecord,
    TestCaseRequirementAtomRecord,
)
from backend.app.test_cases.full_generation_cases import generate_supplement_cases_for_run
from backend.app.test_cases.generation_runs import (
    GENERATION_RUN_TERMINAL_STATUSES,
    get_project_generation_run,
    update_generation_run_stage,
)


STRICT_EXPORT_COVERAGE_GAP_MESSAGE = "严格模式下存在覆盖缺口，不能导出。"

_SENSITIVE_TEXT_TERMS = (
    "provider_response",
    "raw_response",
    "api_key",
    "prompt",
    "token",
    "secret",
)
_WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"']+")
_UNIX_PATH_RE = re.compile(r"(?<!\w)/(?:[^\s\"']+/){1,}[^\s\"']*")
_URL_RE = re.compile(r"https?://[^\s\"']+", re.IGNORECASE)


@dataclass(frozen=True)
class _AuditSnapshot:
    total_atoms: int
    covered_atoms: int
    uncovered_atom_ids: list[str]
    failed_chunk_count: int
    case_count: int
    unfounded_candidates: list[Any]


async def run_coverage_audit_for_run(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    finalize_run: bool = True,
) -> TestCaseCoverageAuditRecord:
    """Compute coverage, run at most one supplement pass, and persist audit state."""
    run = await get_project_generation_run(db, project_id=project_id, run_id=run_id)
    terminal_on_entry = run.status in GENERATION_RUN_TERMINAL_STATUSES
    audit = await _get_or_create_audit(db, project_id=project_id, run_id=run.id)
    supplement_summary = _json_object(audit.supplement_summary_json)

    if not terminal_on_entry and run.status != "supplementing":
        await update_generation_run_stage(
            db,
            project_id=project_id,
            run_id=run.id,
            status="auditing_coverage",
            stage_payload={
                **_json_object(run.stage_payload_json),
                "coverage_audit": {"status": "started"},
            },
        )
        run = await db.get(TestCaseGenerationRunRecord, run.id) or run

    snapshot = await _collect_audit_snapshot(db, project_id=project_id, run_id=run.id, audit=audit)
    initial_uncovered = list(snapshot.uncovered_atom_ids)

    if (
        initial_uncovered
        and not bool(supplement_summary.get("attempted"))
        and not terminal_on_entry
    ):
        await update_generation_run_stage(
            db,
            project_id=project_id,
            run_id=run.id,
            status="supplementing",
            stage_payload={
                **_json_object(run.stage_payload_json),
                "coverage_audit": {
                    "status": "supplementing",
                    "uncovered_atom_ids": initial_uncovered,
                },
            },
        )
        generated_cases = await generate_supplement_cases_for_run(
            db,
            project_id=project_id,
            run_id=run.id,
            uncovered_atom_ids=initial_uncovered,
        )
        snapshot = await _collect_audit_snapshot(db, project_id=project_id, run_id=run.id, audit=audit)
        supplement_summary = {
            "attempted": True,
            "requested_atom_ids": initial_uncovered,
            "generated_case_count": len(generated_cases),
            "remaining_uncovered_atom_ids": list(snapshot.uncovered_atom_ids),
            "status": "covered" if not snapshot.uncovered_atom_ids else "partial",
        }

    export_limitations = _build_export_limitations(run, snapshot)
    warnings = _build_warnings(snapshot, export_limitations, _json_list(audit.warnings_json))
    final_status = _final_run_status(snapshot, export_limitations)
    audit_status = "completed" if final_status == "completed" else "partial_completed"

    _write_audit(
        audit,
        status=audit_status,
        snapshot=snapshot,
        supplement_summary=supplement_summary,
        export_limitations=export_limitations,
        warnings=warnings,
    )

    if not terminal_on_entry:
        stage_payload = {
            **_json_object(run.stage_payload_json),
            "coverage_audit": {
                "status": audit_status,
                "total_atoms": snapshot.total_atoms,
                "covered_atoms": snapshot.covered_atoms,
                "uncovered_atoms": len(snapshot.uncovered_atom_ids),
                "failed_chunk_count": snapshot.failed_chunk_count,
                "supplement": supplement_summary,
                "export_limitations": export_limitations,
                "recommended_run_status": final_status,
            },
        }
        await update_generation_run_stage(
            db,
            project_id=project_id,
            run_id=run.id,
            status=final_status if finalize_run else "auditing_quality",
            case_count=snapshot.case_count,
            warning_count=len(warnings),
            error_summary=(
                "Coverage Audit 没有可导出的 official cases。"
                if final_status == "failed"
                else None
            ),
            stage_payload=stage_payload,
        )
    else:
        run_record = await db.get(TestCaseGenerationRunRecord, run.id)
        if run_record is not None:
            run_record.case_count = snapshot.case_count
            run_record.warning_count = len(warnings)

    await db.flush()
    await db.refresh(audit)
    return audit


async def _get_or_create_audit(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> TestCaseCoverageAuditRecord:
    audit = (
        await db.execute(
            select(TestCaseCoverageAuditRecord).where(
                TestCaseCoverageAuditRecord.project_id == project_id,
                TestCaseCoverageAuditRecord.run_id == run_id,
            )
        )
    ).scalar_one_or_none()
    if audit is None:
        audit = TestCaseCoverageAuditRecord(project_id=project_id, run_id=run_id)
        db.add(audit)
        await db.flush()
    return audit


async def _collect_audit_snapshot(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    audit: TestCaseCoverageAuditRecord,
) -> _AuditSnapshot:
    atoms = list(
        (
            await db.execute(
                select(TestCaseRequirementAtomRecord).where(
                    TestCaseRequirementAtomRecord.project_id == project_id,
                    TestCaseRequirementAtomRecord.run_id == run_id,
                )
            )
        ).scalars()
    )
    official_atom_ids = [
        atom.atom_id
        for atom in atoms
        if (
            atom.coverage_status != "unfounded_candidate"
            and atom.atom_type not in {"open_question", "limitation"}
            and atom.atom_id.startswith("ATOM-")
        )
    ]
    official_atom_id_set = set(official_atom_ids)
    cases = list(
        (
            await db.execute(
                select(TestCaseGenerationCaseRecord).where(
                    TestCaseGenerationCaseRecord.project_id == project_id,
                    TestCaseGenerationCaseRecord.run_id == run_id,
                    TestCaseGenerationCaseRecord.status == "official",
                )
            )
        ).scalars()
    )
    covered = sorted(
        {
            str(atom_id)
            for case in cases
            for atom_id in _json_list(case.atom_refs_json)
            if str(atom_id) in official_atom_id_set
        }
    )
    uncovered = [atom_id for atom_id in official_atom_ids if atom_id not in set(covered)]
    failed_chunk_count = sum(
        1
        for status in (
            await db.execute(
                select(TestCaseGenerationChunkRecord.status).where(
                    TestCaseGenerationChunkRecord.project_id == project_id,
                    TestCaseGenerationChunkRecord.run_id == run_id,
                )
            )
        ).scalars()
        if status == "failed"
    )
    return _AuditSnapshot(
        total_atoms=len(official_atom_ids),
        covered_atoms=len(covered),
        uncovered_atom_ids=uncovered,
        failed_chunk_count=failed_chunk_count,
        case_count=len(cases),
        unfounded_candidates=_json_list(audit.unfounded_candidates_json),
    )


def _build_export_limitations(
    run: TestCaseGenerationRunRecord,
    snapshot: _AuditSnapshot,
) -> list[dict[str, Any]]:
    limitations: list[dict[str, Any]] = []
    if snapshot.uncovered_atom_ids:
        limitations.append(
            {
                "type": "uncovered_atoms",
                "level": "error" if run.strict_mode else "warning",
                "message": f"存在 {len(snapshot.uncovered_atom_ids)} 个未覆盖 Requirement Atom。",
                "atom_ids": snapshot.uncovered_atom_ids,
                "blocks_export": bool(run.strict_mode),
            }
        )
    if snapshot.failed_chunk_count:
        limitations.append(
            {
                "type": "failed_chunks",
                "level": "warning",
                "message": f"存在 {snapshot.failed_chunk_count} 个失败 chunk，可能有未知覆盖缺口。",
                "failed_chunk_count": snapshot.failed_chunk_count,
                "blocks_export": False,
            }
        )
    return [_safe_payload(item) for item in limitations]


def _build_warnings(
    snapshot: _AuditSnapshot,
    export_limitations: list[dict[str, Any]],
    existing_warnings: list[Any],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for item in existing_warnings:
        if isinstance(item, dict):
            message = _safe_text(item.get("message") or item.get("text") or item)
            source = _safe_text(item.get("source") or "coverage")
            level = _safe_text(item.get("level") or "warning")
        else:
            message = _safe_text(item)
            source = "coverage"
            level = "warning"
        if message:
            warnings.append({"source": source, "level": level, "message": message})
    for limitation in export_limitations:
        message = _safe_text(limitation.get("message"))
        if message:
            warnings.append(
                {
                    "source": "coverage",
                    "level": _safe_text(limitation.get("level") or "warning"),
                    "message": message,
                }
            )
    if snapshot.unfounded_candidates:
        warnings.append(
            {
                "source": "coverage",
                "level": "warning",
                "message": f"已剔除 {len(snapshot.unfounded_candidates)} 条无 Requirement Atom 支撑的候选用例。",
            }
        )
    return _dedupe_warning_items(warnings)


def _final_run_status(
    snapshot: _AuditSnapshot,
    export_limitations: list[dict[str, Any]],
) -> str:
    blocking_limitations = [
        limitation
        for limitation in export_limitations
        if limitation.get("level") == "error" and limitation.get("type") != "uncovered_atoms"
    ]
    if (
        snapshot.total_atoms > 0
        and snapshot.covered_atoms == snapshot.total_atoms
        and snapshot.failed_chunk_count == 0
        and not blocking_limitations
    ):
        return "completed"
    if snapshot.case_count > 0:
        return "partial_completed"
    return "failed"


def _write_audit(
    audit: TestCaseCoverageAuditRecord,
    *,
    status: str,
    snapshot: _AuditSnapshot,
    supplement_summary: dict[str, Any],
    export_limitations: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    audit.status = status
    audit.total_atoms = snapshot.total_atoms
    audit.covered_atoms = snapshot.covered_atoms
    audit.uncovered_atoms = len(snapshot.uncovered_atom_ids)
    audit.failed_chunk_count = snapshot.failed_chunk_count
    audit.uncovered_atom_ids_json = json.dumps(
        _safe_payload(snapshot.uncovered_atom_ids),
        ensure_ascii=False,
    )
    audit.unfounded_case_count = len(snapshot.unfounded_candidates)
    audit.unfounded_candidates_json = json.dumps(
        _safe_payload(snapshot.unfounded_candidates),
        ensure_ascii=False,
    )
    audit.supplement_summary_json = json.dumps(
        _safe_payload(supplement_summary),
        ensure_ascii=False,
    )
    audit.export_limitations_json = json.dumps(
        _safe_payload(export_limitations),
        ensure_ascii=False,
    )
    audit.warnings_json = json.dumps(_safe_payload(warnings), ensure_ascii=False)


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        loaded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return loaded if isinstance(loaded, list) else []


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _safe_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _safe_payload(item)
            for key, item in value.items()
            if not _is_sensitive_key(str(key))
        }
    if isinstance(value, list):
        return [_safe_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_safe_payload(item) for item in value]
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, int | float | bool) or value is None:
        return value
    return _safe_text(str(value))


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = _URL_RE.sub("[url]", text)
    text = _WINDOWS_PATH_RE.sub("[path]", text)
    text = _UNIX_PATH_RE.sub("[path]", text)
    text = re.sub(
        r"(?i)\b[\w.-]*(token|secret|password|api_key)[\w.-]*\s*=\s*[^\s,;]+",
        "[redacted]",
        text,
    )
    for term in _SENSITIVE_TEXT_TERMS:
        text = re.sub(re.escape(term), "[redacted]", text, flags=re.IGNORECASE)
    return text[:1000]


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(term in normalized for term in _SENSITIVE_TEXT_TERMS)


def _dedupe_warning_items(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for value in values:
        item = {
            "source": _safe_text(value.get("source") or "coverage"),
            "level": _safe_text(value.get("level") or "warning"),
            "message": _safe_text(value.get("message")),
        }
        key = (item["source"], item["level"], item["message"])
        if not item["message"] or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
