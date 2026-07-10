"""Orchestrator for V3 full Generation Runs."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.credentials import AiProviderInvalid, AiProviderNotConfigured
from backend.app.ai.providers import ProviderConnectionError
from backend.app.database import async_session_factory
from backend.app.models import TestCaseGenerationRunRecord
from backend.app.test_cases.coverage_audit import run_coverage_audit_for_run
from backend.app.test_cases.case_quality_audit import run_case_quality_audit_for_run
from backend.app.test_cases.full_generation_blueprint import (
    generate_test_case_blueprint_for_run,
)
from backend.app.test_cases.full_generation_cases import generate_test_cases_for_run
from backend.app.test_cases.generation_artifacts import render_generation_run_artifacts
from backend.app.test_cases.full_generation_context import (
    FullPlanningSheetContext,
    build_full_planning_sheet_context,
)
from backend.app.test_cases.generation import TestCaseGenerationPayloadError
from backend.app.test_cases.generation_chunking import (
    chunk_full_planning_sheet_context_for_run,
)
from backend.app.test_cases.generation_runs import (
    GENERATION_RUN_TERMINAL_STATUSES,
    GenerationRunError,
    get_project_generation_run,
    update_generation_run_stage,
)
from backend.app.test_cases.requirement_atoms import (
    extract_and_merge_requirement_atoms_for_run,
    retry_failed_requirement_atoms_for_run,
)
from backend.app.test_cases.source_evidence import SourceEvidenceError


_STOP_STATUSES = frozenset({"cancelled", "expired", "failed", "completed", "partial_completed"})
_WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"']+")
_UNIX_PATH_RE = re.compile(r"(?<!\w)/(?:[^\s\"']+/){1,}[^\s\"']*")
_URL_RE = re.compile(r"https?://[^\s\"']+", re.IGNORECASE)
_SENSITIVE_TERMS = (
    "provider_response",
    "provider response",
    "raw_response",
    "raw response",
    "prompt",
    "api_key",
    "token",
    "secret",
    "password",
    "authorization",
)


async def run_generation_run_orchestrator(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    retry_failed_chunks_only: bool = False,
    _commit_after_stage: bool = False,
) -> None:
    """Run a V3 Generation Run through all implemented full-generation stages."""
    context: FullPlanningSheetContext | None = None
    try:
        if await _should_stop(db, project_id=project_id, run_id=run_id):
            return

        if retry_failed_chunks_only:
            context = await _build_context_for_run(db, project_id=project_id, run_id=run_id)
            await retry_failed_requirement_atoms_for_run(
                db,
                project_id=project_id,
                run_id=run_id,
                context=context,
            )
            await _commit_if_needed(db, _commit_after_stage)
        else:
            await update_generation_run_stage(
                db,
                project_id=project_id,
                run_id=run_id,
                status="reading",
                stage_payload={"reading": {"status": "started"}},
            )
            await _commit_if_needed(db, _commit_after_stage)

            context = await _build_context_for_run(db, project_id=project_id, run_id=run_id)
            await update_generation_run_stage(
                db,
                project_id=project_id,
                run_id=run_id,
                status="reading",
                warning_count=len(context.warnings),
                stage_payload={
                    "reading": {
                        "status": "completed",
                        "sheet_name": context.sheet_name,
                        "fact_row_count": len(context.all_fact_rows),
                        "visual_evidence_count": len(context.adopted_visual_evidence_summaries),
                        "warning_count": len(context.warnings),
                    }
                },
            )
            await _commit_if_needed(db, _commit_after_stage)
            if await _should_stop(db, project_id=project_id, run_id=run_id):
                return

            await chunk_full_planning_sheet_context_for_run(
                db,
                project_id=project_id,
                run_id=run_id,
                context=context,
            )
            await _commit_if_needed(db, _commit_after_stage)
            if await _should_stop(db, project_id=project_id, run_id=run_id):
                return

            await extract_and_merge_requirement_atoms_for_run(
                db,
                project_id=project_id,
                run_id=run_id,
                context=context,
            )
            await _commit_if_needed(db, _commit_after_stage)

        if await _should_stop(db, project_id=project_id, run_id=run_id):
            return
        if context is None:
            context = await _build_context_for_run(db, project_id=project_id, run_id=run_id)

        await generate_test_case_blueprint_for_run(
            db,
            project_id=project_id,
            run_id=run_id,
            source_summary=context.source_summary,
            context_warnings=context.warnings,
        )
        await _commit_if_needed(db, _commit_after_stage)
        if await _should_stop(db, project_id=project_id, run_id=run_id):
            return

        await generate_test_cases_for_run(db, project_id=project_id, run_id=run_id)
        await _commit_if_needed(db, _commit_after_stage)
        if await _should_stop(db, project_id=project_id, run_id=run_id):
            return

        await run_coverage_audit_for_run(
            db,
            project_id=project_id,
            run_id=run_id,
            finalize_run=False,
        )
        await _commit_if_needed(db, _commit_after_stage)
        if await _should_stop(db, project_id=project_id, run_id=run_id):
            return

        await run_case_quality_audit_for_run(
            db,
            project_id=project_id,
            run_id=run_id,
        )
        await _commit_if_needed(db, _commit_after_stage)
        if await _should_stop(db, project_id=project_id, run_id=run_id):
            return

        await render_generation_run_artifacts(
            db,
            project_id=project_id,
            run_id=run_id,
        )
        await _commit_if_needed(db, _commit_after_stage)
    except Exception as exc:
        await db.rollback()
        await _mark_run_failed(
            db,
            project_id=project_id,
            run_id=run_id,
            error=exc,
        )
        await _commit_if_needed(db, _commit_after_stage)


async def run_generation_run_background_task(
    *,
    project_id: int,
    run_id: int,
    retry_failed_chunks_only: bool = False,
) -> None:
    """Run a Generation Run in a FastAPI BackgroundTasks worker with its own DB session."""
    async with async_session_factory() as db:
        await run_generation_run_orchestrator(
            db,
            project_id=project_id,
            run_id=run_id,
            retry_failed_chunks_only=retry_failed_chunks_only,
            _commit_after_stage=True,
        )


async def _build_context_for_run(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> FullPlanningSheetContext:
    run = await get_project_generation_run(db, project_id=project_id, run_id=run_id)
    return await build_full_planning_sheet_context(
        db,
        project_id=project_id,
        source_evidence_run_id=run.source_evidence_run_id,
        planning_sheet_name=run.planning_sheet_name,
    )


async def _should_stop(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> bool:
    run = await get_project_generation_run(db, project_id=project_id, run_id=run_id)
    return run.status in _STOP_STATUSES


async def _mark_run_failed(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    error: BaseException,
) -> None:
    try:
        run = await get_project_generation_run(db, project_id=project_id, run_id=run_id)
    except GenerationRunError:
        return
    if run.status in GENERATION_RUN_TERMINAL_STATUSES and run.status != "failed":
        return
    message = _error_message(error)
    if run.status == "failed":
        record = await db.get(TestCaseGenerationRunRecord, run.id)
        if record is not None and not record.error_summary:
            record.error_summary = message
        await db.flush()
        return
    await update_generation_run_stage(
        db,
        project_id=project_id,
        run_id=run.id,
        status="failed",
        error_summary=message,
        stage_payload={
            **_json_object(run.stage_payload_json),
            "orchestrator": {
                "status": "failed",
                "error_summary": message,
            },
        },
    )


def _error_message(error: BaseException) -> str:
    if isinstance(error, ProviderConnectionError):
        return _safe_text(error.message)
    if isinstance(
        error,
        (
            SourceEvidenceError,
            AiProviderInvalid,
            AiProviderNotConfigured,
            TestCaseGenerationPayloadError,
            GenerationRunError,
            ValueError,
        ),
    ):
        return _safe_text(str(error))
    return _safe_text(str(error) or error.__class__.__name__)


async def _commit_if_needed(db: AsyncSession, commit: bool) -> None:
    if commit:
        await db.commit()
    else:
        await db.flush()


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _safe_text(value: Any) -> str:
    text = str(value or "")
    text = _URL_RE.sub("[url]", text)
    text = _WINDOWS_PATH_RE.sub("[path]", text)
    text = _UNIX_PATH_RE.sub("[path]", text)
    text = re.sub(
        r"(?i)\b[\w.-]*(token|secret|password|api_key)[\w.-]*\s*=\s*[^\s,;]+",
        "[redacted]",
        text,
    )
    for term in _SENSITIVE_TERMS:
        text = re.sub(re.escape(term), "[redacted]", text, flags=re.IGNORECASE)
    return text[:500]
