"""Requirement Atom extraction and merge for V3 Generation Runs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import re
from difflib import SequenceMatcher
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.credentials import (
    decrypt_credential_key,
    load_project_credential,
    parse_extra_headers,
    sanitize_ai_error,
)
from backend.app.ai.providers import ProviderConnectionError, call_provider_json
from backend.app.models import (
    TestCaseGenerationChunkRecord,
    TestCaseGenerationRunRecord,
    TestCaseRequirementAtomRecord,
)
from backend.app.test_cases.full_generation_context import (
    FullPlanningSheetContext,
    FullPlanningSheetFactRow,
    FullPlanningSheetVisualEvidence,
)
from backend.app.test_cases.generation_runs import (
    GenerationRunError,
    update_generation_run_stage,
)


ATOM_TYPES = frozenset(
    {
        "rule",
        "entry",
        "state",
        "timing",
        "config",
        "reward",
        "role",
        "ui_text",
        "visual_fact",
        "open_question",
        "limitation",
    }
)
DEFAULT_ATOM_EXTRACTION_CONCURRENCY = 2
DEFAULT_ATOM_TEXT_SIMILARITY_THRESHOLD = 0.92

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
    "prompt",
    "tenant_access_token",
    "access_token",
    "api_key",
    "token",
    "secret",
)


class RequirementAtomItemPayload(BaseModel):
    """AI 返回的单个 Requirement Atom 候选。"""

    model_config = ConfigDict(extra="ignore")

    atom_type: str
    text: str
    source_sheet: str = ""
    source_rows: list[int] = Field(default_factory=list)
    source_columns: list[str] = Field(default_factory=list)
    source_excerpt: str = ""
    visual_evidence_ids: list[int | str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    warnings: list[Any] = Field(default_factory=list)
    merge_key: str = ""
    is_unfounded_candidate: bool = False


class RequirementAtomExtractionPayload(BaseModel):
    """AI chunk extraction response."""

    model_config = ConfigDict(extra="ignore")

    atoms: list[RequirementAtomItemPayload]
    warnings: list[Any] = Field(default_factory=list)


@dataclass(frozen=True)
class _ChunkInput:
    record_id: int
    chunk_index: int
    chunk_key: str
    sheet_name: str
    row_start: int | None
    row_end: int | None
    column_start: int | None
    column_end: int | None
    title_hints: list[str]
    resource_refs: list[str]
    covered_row_indexes: list[int]
    previous_overlap_hint: dict[str, Any] | None
    next_overlap_hint: dict[str, Any] | None
    facts: list[FullPlanningSheetFactRow]
    visual_evidence: list[FullPlanningSheetVisualEvidence]
    structure_hints: dict[str, Any]


@dataclass
class _NormalizedAtom:
    atom_type: str
    text: str
    source_sheet: str
    source_row_start: int | None
    source_row_end: int | None
    source_columns: list[str]
    source_excerpt: str
    visual_evidence_refs: list[str]
    confidence: float | None
    warnings: list[str]
    merge_key: str
    is_unfounded_candidate: bool
    chunk_id: int | None
    chunk_index: int
    order: int


@dataclass(frozen=True)
class _ChunkExtractionResult:
    chunk_id: int
    chunk_index: int
    status: str
    atoms: list[_NormalizedAtom] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_summary: str = ""
    provider_meta: dict[str, Any] = field(default_factory=dict)
    raw_atom_count: int = 0


async def extract_and_merge_requirement_atoms_for_run(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    context: FullPlanningSheetContext,
    max_concurrency: int = DEFAULT_ATOM_EXTRACTION_CONCURRENCY,
) -> list[TestCaseRequirementAtomRecord]:
    """Extract Requirement Atoms for each persisted chunk and persist merged atoms."""
    await update_generation_run_stage(
        db,
        project_id=project_id,
        run_id=run_id,
        status="extracting_atoms",
    )
    credential = await load_project_credential(db, project_id)
    api_key = decrypt_credential_key(credential)
    extra_headers = parse_extra_headers(credential.extra_headers_json)
    chunk_inputs = await _load_chunk_inputs(
        db,
        project_id=project_id,
        run_id=run_id,
        context=context,
    )
    if not chunk_inputs:
        raise GenerationRunError(409, "Generation Run 尚无 chunk，不能抽取 Requirement Atom。")

    semaphore = asyncio.Semaphore(max(1, int(max_concurrency)))

    async def _extract(chunk_input: _ChunkInput) -> _ChunkExtractionResult:
        async with semaphore:
            return await _extract_chunk_atoms(
                chunk_input,
                context=context,
                credential=credential,
                api_key=api_key,
                extra_headers=extra_headers,
            )

    results = await asyncio.gather(*(_extract(chunk_input) for chunk_input in chunk_inputs))
    persisted = await _persist_extraction_results(
        db,
        project_id=project_id,
        run_id=run_id,
        context=context,
        chunk_inputs=chunk_inputs,
        results=results,
    )
    return persisted


async def retry_failed_requirement_atoms_for_run(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    context: FullPlanningSheetContext,
    max_concurrency: int = DEFAULT_ATOM_EXTRACTION_CONCURRENCY,
) -> list[TestCaseRequirementAtomRecord]:
    """Retry atom extraction only for chunks reopened by retry-failed-chunks."""
    await update_generation_run_stage(
        db,
        project_id=project_id,
        run_id=run_id,
        status="extracting_atoms",
    )
    credential = await load_project_credential(db, project_id)
    api_key = decrypt_credential_key(credential)
    extra_headers = parse_extra_headers(credential.extra_headers_json)
    chunk_inputs = await _load_chunk_inputs(
        db,
        project_id=project_id,
        run_id=run_id,
        context=context,
        retry_only=True,
    )
    if not chunk_inputs:
        raise GenerationRunError(409, "Generation Run 没有可重试的 failed chunk。")

    retry_chunk_ids = {chunk_input.record_id for chunk_input in chunk_inputs}
    preserved_atoms = await _load_existing_normalized_atoms(
        db,
        project_id=project_id,
        run_id=run_id,
        exclude_chunk_ids=retry_chunk_ids,
    )
    semaphore = asyncio.Semaphore(max(1, int(max_concurrency)))

    async def _extract(chunk_input: _ChunkInput) -> _ChunkExtractionResult:
        async with semaphore:
            return await _extract_chunk_atoms(
                chunk_input,
                context=context,
                credential=credential,
                api_key=api_key,
                extra_headers=extra_headers,
            )

    results = await asyncio.gather(*(_extract(chunk_input) for chunk_input in chunk_inputs))
    return await _persist_extraction_results(
        db,
        project_id=project_id,
        run_id=run_id,
        context=context,
        chunk_inputs=chunk_inputs,
        results=results,
        preserved_atoms=preserved_atoms,
    )


async def _load_chunk_inputs(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    context: FullPlanningSheetContext,
    retry_only: bool = False,
) -> list[_ChunkInput]:
    stmt = select(TestCaseGenerationChunkRecord).where(
        TestCaseGenerationChunkRecord.project_id == project_id,
        TestCaseGenerationChunkRecord.run_id == run_id,
    )
    if retry_only:
        stmt = stmt.where(
            TestCaseGenerationChunkRecord.status == "queued",
            TestCaseGenerationChunkRecord.retry_count > 0,
        )
    result = await db.execute(stmt.order_by(TestCaseGenerationChunkRecord.chunk_index))
    chunk_records = list(result.scalars())
    return [_chunk_input_from_record(record, context=context) for record in chunk_records]


def _chunk_input_from_record(
    record: TestCaseGenerationChunkRecord,
    *,
    context: FullPlanningSheetContext,
) -> _ChunkInput:
    hints = _json_object(record.structure_hints_json)
    covered_row_indexes = [
        int(row)
        for row in hints.get("covered_row_indexes", [])
        if isinstance(row, int) or (isinstance(row, str) and row.isdigit())
    ]
    if not covered_row_indexes and record.source_row_start is not None and record.source_row_end is not None:
        covered_row_indexes = list(range(record.source_row_start, record.source_row_end + 1))
    covered_rows = set(covered_row_indexes)
    facts = [
        row
        for row in context.all_fact_rows
        if row.row_index in covered_rows
    ]
    resource_refs = [
        _safe_text(str(item))
        for item in hints.get("resource_refs", [])
        if _safe_text(str(item))
    ]
    visuals = [
        item
        for item in context.adopted_visual_evidence_summaries
        if item.ref in set(resource_refs)
    ]
    return _ChunkInput(
        record_id=record.id,
        chunk_index=record.chunk_index,
        chunk_key=_safe_text(str(hints.get("chunk_key") or f"chunk-{record.chunk_index}")),
        sheet_name=_safe_text(str(hints.get("sheet_name") or context.sheet_name)),
        row_start=record.source_row_start,
        row_end=record.source_row_end,
        column_start=record.source_column_start,
        column_end=record.source_column_end,
        title_hints=[
            _safe_text(str(item))
            for item in hints.get("title_hints", [])
            if _safe_text(str(item))
        ],
        resource_refs=resource_refs,
        covered_row_indexes=covered_row_indexes,
        previous_overlap_hint=_json_object_or_none(hints.get("previous_overlap_hint")),
        next_overlap_hint=_json_object_or_none(hints.get("next_overlap_hint")),
        facts=facts,
        visual_evidence=visuals,
        structure_hints=hints,
    )


async def _extract_chunk_atoms(
    chunk_input: _ChunkInput,
    *,
    context: FullPlanningSheetContext,
    credential: Any,
    api_key: str,
    extra_headers: dict[str, str],
) -> _ChunkExtractionResult:
    try:
        payload, provider_meta = await call_provider_json(
            provider_preset=credential.provider_preset,  # type: ignore[arg-type]
            base_url=credential.base_url,
            model=credential.model,
            api_key=api_key,
            system_prompt=_build_atom_system_prompt(),
            user_prompt=_build_atom_chunk_prompt(chunk_input, context=context),
            json_schema=RequirementAtomExtractionPayload.model_json_schema(),
            extra_headers=extra_headers,
            timeout_seconds=60.0,
        )
    except ProviderConnectionError as error:
        return _failed_chunk_result(
            chunk_input,
            sanitize_ai_error(error.message, api_key),
        )

    if not isinstance(payload.get("atoms"), list):
        return _failed_chunk_result(chunk_input, "Requirement Atom 抽取返回缺少 atoms 数组。")

    try:
        extraction_payload = RequirementAtomExtractionPayload.model_validate(
            _normalize_extraction_payload(payload)
        )
    except ValidationError as error:
        return _failed_chunk_result(
            chunk_input,
            f"Requirement Atom 抽取返回结构不符合契约：{error.errors()[0]['msg']}",
        )

    chunk_warnings = _normalize_warning_messages(extraction_payload.warnings)
    if not extraction_payload.atoms:
        chunk_warnings.append("当前 chunk 未抽取到 Requirement Atom。")

    atoms: list[_NormalizedAtom] = []
    for order, atom_payload in enumerate(extraction_payload.atoms):
        atom, warnings = _normalize_atom_payload(
            atom_payload,
            chunk_input=chunk_input,
            context=context,
            order=order,
        )
        chunk_warnings.extend(warnings)
        if atom is not None:
            atoms.append(atom)

    return _ChunkExtractionResult(
        chunk_id=chunk_input.record_id,
        chunk_index=chunk_input.chunk_index,
        status="completed",
        atoms=atoms,
        warnings=_deduplicate_strings(chunk_warnings),
        provider_meta=_safe_payload(provider_meta),
        raw_atom_count=len(extraction_payload.atoms),
    )


def _failed_chunk_result(chunk_input: _ChunkInput, message: str) -> _ChunkExtractionResult:
    return _ChunkExtractionResult(
        chunk_id=chunk_input.record_id,
        chunk_index=chunk_input.chunk_index,
        status="failed",
        warnings=[],
        error_summary=_safe_text(message)[:500],
    )


async def _persist_extraction_results(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    context: FullPlanningSheetContext,
    chunk_inputs: list[_ChunkInput],
    results: list[_ChunkExtractionResult],
    preserved_atoms: list[_NormalizedAtom] | None = None,
) -> list[TestCaseRequirementAtomRecord]:
    chunk_map = {
        chunk.id: chunk
        for chunk in (
            await db.execute(
                select(TestCaseGenerationChunkRecord).where(
                    TestCaseGenerationChunkRecord.project_id == project_id,
                    TestCaseGenerationChunkRecord.run_id == run_id,
                )
            )
        ).scalars()
    }
    all_warnings: list[str] = []
    all_atoms: list[_NormalizedAtom] = list(preserved_atoms or [])
    for result in results:
        chunk_record = chunk_map.get(result.chunk_id)
        if chunk_record is None:
            continue
        chunk_record.status = result.status
        chunk_record.error_summary = result.error_summary
        hints = _json_object(chunk_record.structure_hints_json)
        hints["atom_extraction_provider_meta"] = _safe_payload(result.provider_meta)
        hints["atom_extraction_warning_count"] = len(result.warnings)
        hints["raw_atom_count"] = result.raw_atom_count
        if result.warnings:
            hints["atom_extraction_warnings"] = _deduplicate_strings(result.warnings)
        chunk_record.structure_hints_json = json.dumps(
            _safe_payload(hints),
            ensure_ascii=False,
        )
        all_warnings.extend(result.warnings)
        if result.error_summary:
            all_warnings.append(result.error_summary)
        all_atoms.extend(result.atoms)

    await db.execute(
        delete(TestCaseRequirementAtomRecord).where(
            TestCaseRequirementAtomRecord.project_id == project_id,
            TestCaseRequirementAtomRecord.run_id == run_id,
        )
    )

    official_atoms = [atom for atom in all_atoms if not atom.is_unfounded_candidate]
    unfounded_candidates = [atom for atom in all_atoms if atom.is_unfounded_candidate]
    merged_official = _merge_official_atoms(official_atoms)
    persisted_records = _build_atom_records(
        project_id=project_id,
        run_id=run_id,
        official_atoms=merged_official,
        unfounded_candidates=unfounded_candidates,
    )
    db.add_all(persisted_records)

    completed_chunks = sum(1 for chunk in chunk_map.values() if chunk.status == "completed")
    failed_chunks = sum(1 for chunk in chunk_map.values() if chunk.status == "failed")
    for atom in [*merged_official, *unfounded_candidates]:
        all_warnings.extend(atom.warnings)
    await update_generation_run_stage(
        db,
        project_id=project_id,
        run_id=run_id,
        status="merging_atoms",
        completed_chunks=completed_chunks,
        failed_chunks=failed_chunks,
        atom_count=len(merged_official),
        warning_count=len(_deduplicate_strings(all_warnings)),
        stage_payload={
            "atom_extraction": {
                "sheet_name": context.sheet_name,
                "chunk_count": len(chunk_inputs),
                "completed_chunks": completed_chunks,
                "failed_chunks": failed_chunks,
                "official_atom_count": len(merged_official),
                "unfounded_candidate_count": len(unfounded_candidates),
                "warning_count": len(_deduplicate_strings(all_warnings)),
            }
        },
    )
    run = await db.get(TestCaseGenerationRunRecord, run_id)
    if run is not None:
        run.warnings_json = json.dumps(
            [
                {"source": "requirement_atoms", "level": "warning", "message": message}
                for message in _deduplicate_strings(all_warnings)
            ],
            ensure_ascii=False,
        )
    await db.flush()
    for record in persisted_records:
        await db.refresh(record)
    return persisted_records


def _build_atom_records(
    *,
    project_id: int,
    run_id: int,
    official_atoms: list[_NormalizedAtom],
    unfounded_candidates: list[_NormalizedAtom],
) -> list[TestCaseRequirementAtomRecord]:
    records: list[TestCaseRequirementAtomRecord] = []
    for index, atom in enumerate(official_atoms, start=1):
        records.append(
            _atom_record(
                project_id=project_id,
                run_id=run_id,
                atom=atom,
                atom_id=f"ATOM-{index:04d}",
                coverage_status="unmapped",
            )
        )
    for index, atom in enumerate(unfounded_candidates, start=1):
        records.append(
            _atom_record(
                project_id=project_id,
                run_id=run_id,
                atom=atom,
                atom_id=f"CAND-{index:04d}",
                coverage_status="unfounded_candidate",
            )
        )
    return records


async def _load_existing_normalized_atoms(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    exclude_chunk_ids: set[int],
) -> list[_NormalizedAtom]:
    result = await db.execute(
        select(TestCaseRequirementAtomRecord)
        .where(
            TestCaseRequirementAtomRecord.project_id == project_id,
            TestCaseRequirementAtomRecord.run_id == run_id,
        )
        .order_by(TestCaseRequirementAtomRecord.id)
    )
    atoms: list[_NormalizedAtom] = []
    for index, record in enumerate(result.scalars()):
        if record.chunk_id in exclude_chunk_ids:
            continue
        atoms.append(_normalized_atom_from_record(record, order=index))
    return atoms


def _normalized_atom_from_record(
    record: TestCaseRequirementAtomRecord,
    *,
    order: int,
) -> _NormalizedAtom:
    return _NormalizedAtom(
        atom_type=record.atom_type,
        text=_safe_text(record.requirement_text),
        source_sheet=_safe_text(record.source_sheet_name),
        source_row_start=record.source_row_start,
        source_row_end=record.source_row_end,
        source_columns=_safe_list([str(item) for item in _json_list(record.source_columns_json)]),
        source_excerpt=_safe_text(record.cell_excerpt),
        visual_evidence_refs=_safe_list(
            [str(item) for item in _json_list(record.visual_evidence_refs_json)]
        ),
        confidence=record.confidence,
        warnings=_safe_list([str(item) for item in _json_list(record.warnings_json)]),
        merge_key=_safe_text(record.merge_group_id),
        is_unfounded_candidate=record.coverage_status == "unfounded_candidate",
        chunk_id=record.chunk_id,
        chunk_index=-1,
        order=order,
    )


def _atom_record(
    *,
    project_id: int,
    run_id: int,
    atom: _NormalizedAtom,
    atom_id: str,
    coverage_status: str,
) -> TestCaseRequirementAtomRecord:
    return TestCaseRequirementAtomRecord(
        project_id=project_id,
        run_id=run_id,
        chunk_id=atom.chunk_id,
        atom_id=atom_id,
        atom_type=atom.atom_type,
        requirement_text=_safe_text(atom.text),
        source_sheet_name=_safe_text(atom.source_sheet),
        source_row_start=atom.source_row_start,
        source_row_end=atom.source_row_end,
        source_columns_json=json.dumps(_safe_list(atom.source_columns), ensure_ascii=False),
        cell_excerpt=_safe_text(atom.source_excerpt),
        visual_evidence_refs_json=json.dumps(
            _safe_list(atom.visual_evidence_refs),
            ensure_ascii=False,
        ),
        confidence=atom.confidence,
        warnings_json=json.dumps(_safe_list(atom.warnings), ensure_ascii=False),
        coverage_status=coverage_status,
        merge_group_id=_safe_text(atom.merge_key)[:64],
    )


def _normalize_extraction_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["atoms"] = [
        _normalize_atom_dict(item)
        for item in normalized.get("atoms", [])
        if isinstance(item, dict)
    ]
    normalized["warnings"] = normalized.get("warnings") or []
    return normalized


def _normalize_atom_dict(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized["text"] = _provider_string(
        normalized.get("text")
        or normalized.get("requirement_text")
        or normalized.get("requirement")
        or normalized.get("content")
    )
    normalized["source_sheet"] = _provider_string(
        normalized.get("source_sheet")
        or normalized.get("source_sheet_name")
        or normalized.get("sheet")
    )
    normalized["source_rows"] = _normalize_source_rows(
        normalized.get("source_rows")
        or normalized.get("source_row_range")
        or normalized.get("rows")
    )
    normalized["source_columns"] = _normalize_string_list(
        normalized.get("source_columns")
        or normalized.get("columns")
        or normalized.get("source_column_names")
    )
    normalized["source_excerpt"] = _provider_string(
        normalized.get("source_excerpt")
        or normalized.get("cell_excerpt")
        or normalized.get("excerpt")
    )
    normalized["visual_evidence_ids"] = _normalize_visual_ids(
        normalized.get("visual_evidence_ids")
        or normalized.get("visual_evidence_refs")
        or normalized.get("visual_refs")
    )
    normalized["warnings"] = normalized.get("warnings") or []
    normalized["merge_key"] = _provider_string(normalized.get("merge_key"))
    normalized["is_unfounded_candidate"] = bool(
        normalized.get("is_unfounded_candidate")
        or normalized.get("unfounded")
        or normalized.get("is_unfounded")
    )
    return normalized


def _normalize_atom_payload(
    payload: RequirementAtomItemPayload,
    *,
    chunk_input: _ChunkInput,
    context: FullPlanningSheetContext,
    order: int,
) -> tuple[_NormalizedAtom | None, list[str]]:
    warnings = _normalize_warning_messages(payload.warnings)
    atom_type = payload.atom_type.strip()
    text = _safe_text(payload.text)
    if atom_type not in ATOM_TYPES:
        return None, [f"chunk {chunk_input.chunk_index} 返回了不支持的 atom_type：{atom_type}。"]
    if not text:
        return None, [f"chunk {chunk_input.chunk_index} 返回了缺少 text 的 atom，已跳过。"]

    visual_refs, visual_warnings = _normalize_visual_refs_for_chunk(
        payload.visual_evidence_ids,
        chunk_input=chunk_input,
        context=context,
    )
    warnings.extend(visual_warnings)
    source_start, source_end = _source_row_range(payload.source_rows)
    has_source_basis = _has_current_source_basis(
        source_sheet=payload.source_sheet,
        source_start=source_start,
        source_end=source_end,
        chunk_input=chunk_input,
        context=context,
    )
    is_unfounded_candidate = payload.is_unfounded_candidate
    if atom_type == "visual_fact" and not visual_refs:
        is_unfounded_candidate = True
        warnings.append("visual_fact 引用了未采纳或非当前 chunk 视觉证据，已降级为 unfounded candidate。")
    if not is_unfounded_candidate and not has_source_basis and not visual_refs:
        return None, [f"chunk {chunk_input.chunk_index} 返回了无当前来源依据的 atom，已跳过。"]
    if not is_unfounded_candidate and payload.source_sheet.strip() != context.sheet_name:
        return None, [f"chunk {chunk_input.chunk_index} 返回了跨 Sheet atom，已跳过。"]

    merge_key = _safe_text(payload.merge_key) or _default_merge_key(atom_type, text)
    return (
        _NormalizedAtom(
            atom_type=atom_type,
            text=text,
            source_sheet=_safe_text(payload.source_sheet or context.sheet_name),
            source_row_start=source_start,
            source_row_end=source_end,
            source_columns=_safe_list(payload.source_columns),
            source_excerpt=_safe_text(payload.source_excerpt),
            visual_evidence_refs=visual_refs,
            confidence=payload.confidence,
            warnings=_deduplicate_strings(warnings),
            merge_key=merge_key,
            is_unfounded_candidate=is_unfounded_candidate,
            chunk_id=chunk_input.record_id,
            chunk_index=chunk_input.chunk_index,
            order=order,
        ),
        [],
    )


def _merge_official_atoms(atoms: list[_NormalizedAtom]) -> list[_NormalizedAtom]:
    merged: list[_NormalizedAtom] = []
    for atom in atoms:
        duplicate = _find_duplicate_atom(merged, atom)
        if duplicate is None:
            merged.append(atom)
            continue
        _merge_atom_into(duplicate, atom)
    return merged


def _find_duplicate_atom(
    merged: list[_NormalizedAtom],
    atom: _NormalizedAtom,
) -> _NormalizedAtom | None:
    for existing in merged:
        if existing.merge_key and atom.merge_key and existing.merge_key == atom.merge_key:
            return existing
        if _ranges_overlap(existing, atom) and _text_similarity(existing.text, atom.text) >= DEFAULT_ATOM_TEXT_SIMILARITY_THRESHOLD:
            return existing
    return None


def _merge_atom_into(target: _NormalizedAtom, duplicate: _NormalizedAtom) -> None:
    similarity = _text_similarity(target.text, duplicate.text)
    target.source_row_start = _min_optional(target.source_row_start, duplicate.source_row_start)
    target.source_row_end = _max_optional(target.source_row_end, duplicate.source_row_end)
    target.source_columns = _merge_lists(target.source_columns, duplicate.source_columns)
    target.visual_evidence_refs = _merge_lists(
        target.visual_evidence_refs,
        duplicate.visual_evidence_refs,
    )
    if target.confidence is None:
        target.confidence = duplicate.confidence
    elif duplicate.confidence is not None:
        target.confidence = max(target.confidence, duplicate.confidence)
    target.warnings = _deduplicate_strings(
        [
            *target.warnings,
            *duplicate.warnings,
            f"与 chunk {duplicate.chunk_index} 的重复 Requirement Atom 已合并。",
        ]
    )
    if similarity < DEFAULT_ATOM_TEXT_SIMILARITY_THRESHOLD:
        target.warnings = _deduplicate_strings(
            [
                *target.warnings,
                "相同 merge_key 存在冲突解释，已保留首个解释并记录警告。",
            ]
        )
    if target.atom_type != duplicate.atom_type:
        target.warnings = _deduplicate_strings(
            [
                *target.warnings,
                f"重复 atom 的类型冲突：{target.atom_type} / {duplicate.atom_type}。",
            ]
        )


def _build_atom_system_prompt() -> str:
    return (
        "你是资深测试需求分析助手。只返回符合 JSON Schema 的 JSON 对象，"
        "不要输出 Markdown、解释文本、统计、原始 prompt 或 provider 响应。"
    )


def _build_atom_chunk_prompt(
    chunk_input: _ChunkInput,
    *,
    context: FullPlanningSheetContext,
) -> str:
    lines = [
        "任务：从当前 Generation Chunk 抽取 Requirement Atom。",
        "只能从当前 chunk facts 和已采纳视觉证据抽取；不能从参考案例、常识或旧知识补需求。",
        "无当前来源依据的内容只能标记 is_unfounded_candidate=true，不能作为 official atom。",
        f"Sheet：{context.sheet_name}",
        f"Chunk：{chunk_input.chunk_key}",
        f"行范围：{chunk_input.row_start}-{chunk_input.row_end}",
        f"列范围：{chunk_input.column_start}-{chunk_input.column_end}",
        f"标题提示：{', '.join(chunk_input.title_hints) if chunk_input.title_hints else '无'}",
        "Atom types：rule, entry, state, timing, config, reward, role, ui_text, visual_fact, open_question, limitation。",
        "当前 chunk facts：",
    ]
    lines.extend(_render_fact_rows(chunk_input.facts))
    if chunk_input.visual_evidence:
        lines.append("当前 chunk 已采纳视觉证据：")
        for item in chunk_input.visual_evidence:
            lines.append(
                "- "
                f"id={item.id}; ref={_safe_text(item.ref)}; position={_safe_text(item.position)}; "
                f"summary={_safe_text(item.summary)}; visible_text={_safe_text(item.visible_text)}; "
                f"confidence={item.confidence}"
            )
    else:
        lines.append("当前 chunk 已采纳视觉证据：无")
    if chunk_input.previous_overlap_hint:
        lines.append(
            "previous_overlap_hint："
            + json.dumps(_safe_payload(chunk_input.previous_overlap_hint), ensure_ascii=False)
        )
    if chunk_input.next_overlap_hint:
        lines.append(
            "next_overlap_hint："
            + json.dumps(_safe_payload(chunk_input.next_overlap_hint), ensure_ascii=False)
        )
    lines.append(
        "返回 JSON：{atoms:[{atom_type,text,source_sheet,source_rows,source_columns,"
        "source_excerpt,visual_evidence_ids,confidence,warnings,merge_key,"
        "is_unfounded_candidate}], warnings:[]}。"
    )
    return "\n".join(lines)


def _render_fact_rows(rows: list[FullPlanningSheetFactRow]) -> list[str]:
    rendered: list[str] = []
    for row in rows:
        fragments = [
            f"{_safe_text(cell.column_name)}={_safe_text(cell.value)}"
            for cell in row.cells
            if _safe_text(cell.value)
        ]
        if fragments:
            rendered.append(
                f"- row={row.row_index}; unit={_safe_text(row.source_unit_title)}; "
                f"status={_safe_text(row.evidence_status)}; "
                + " | ".join(fragments)
            )
    return rendered


def _normalize_visual_refs_for_chunk(
    values: list[int | str],
    *,
    chunk_input: _ChunkInput,
    context: FullPlanningSheetContext,
) -> tuple[list[str], list[str]]:
    visual_ref_by_id = {
        str(item.id): item.ref for item in context.adopted_visual_evidence_summaries
    }
    visual_ref_by_ref = {
        item.ref: item.ref for item in context.adopted_visual_evidence_summaries
    }
    allowed_refs = set(chunk_input.resource_refs)
    refs: list[str] = []
    warnings: list[str] = []
    for value in values:
        raw = str(value)
        ref = visual_ref_by_id.get(raw) or visual_ref_by_ref.get(raw)
        if not ref or ref not in allowed_refs:
            warnings.append(f"视觉证据 {raw} 未采纳或不属于当前 chunk，已剔除。")
            continue
        if ref not in refs:
            refs.append(ref)
    return refs, _deduplicate_strings(warnings)


def _has_current_source_basis(
    *,
    source_sheet: str,
    source_start: int | None,
    source_end: int | None,
    chunk_input: _ChunkInput,
    context: FullPlanningSheetContext,
) -> bool:
    if _safe_text(source_sheet) != context.sheet_name:
        return False
    if source_start is None or source_end is None:
        return False
    if source_start > source_end:
        return False
    if not chunk_input.covered_row_indexes:
        return False
    min_row = min(chunk_input.covered_row_indexes)
    max_row = max(chunk_input.covered_row_indexes)
    return min_row <= source_start <= max_row and min_row <= source_end <= max_row


def _source_row_range(rows: list[int]) -> tuple[int | None, int | None]:
    normalized = [int(row) for row in rows if int(row) > 0]
    if not normalized:
        return None, None
    return min(normalized), max(normalized)


def _normalize_source_rows(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, dict):
        return [
            int(item)
            for item in (value.get("start"), value.get("end"))
            if isinstance(item, int) or (isinstance(item, str) and item.isdigit())
        ]
    if isinstance(value, list):
        return [
            int(item)
            for item in value
            if isinstance(item, int) or (isinstance(item, str) and item.isdigit())
        ]
    return []


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [_provider_string(item) for item in value if _provider_string(item)]
    return [_provider_string(value)] if _provider_string(value) else []


def _normalize_visual_ids(value: Any) -> list[int | str]:
    if value is None:
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [
            item
            for item in value
            if isinstance(item, int) or (isinstance(item, str) and item.strip())
        ]
    return []


def _normalize_warning_messages(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    messages: list[str] = []
    for value in values:
        if isinstance(value, str):
            message = _safe_text(value)
        elif isinstance(value, dict):
            message = _safe_text(
                _provider_string(
                    value.get("message")
                    or value.get("description")
                    or value.get("detail")
                    or value.get("text")
                )
            )
        else:
            message = _safe_text(_provider_string(value))
        if message:
            messages.append(message)
    return _deduplicate_strings(messages)


def _provider_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(
            text
            for text in (_provider_string(item).strip() for item in value)
            if text
        )
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _json_object(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _json_list(raw: str | None) -> list[Any]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _json_object_or_none(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _default_merge_key(atom_type: str, text: str) -> str:
    normalized = re.sub(r"\s+", "", text.lower())
    return f"{atom_type}:{normalized[:48]}"


def _ranges_overlap(left: _NormalizedAtom, right: _NormalizedAtom) -> bool:
    if (
        left.source_row_start is None
        or left.source_row_end is None
        or right.source_row_start is None
        or right.source_row_end is None
    ):
        return False
    return left.source_row_start <= right.source_row_end and right.source_row_start <= left.source_row_end


def _text_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def _min_optional(left: int | None, right: int | None) -> int | None:
    values = [value for value in (left, right) if value is not None]
    return min(values) if values else None


def _max_optional(left: int | None, right: int | None) -> int | None:
    values = [value for value in (left, right) if value is not None]
    return max(values) if values else None


def _merge_lists(left: list[str], right: list[str]) -> list[str]:
    merged = list(left)
    for item in right:
        if item not in merged:
            merged.append(item)
    return merged


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


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(term in normalized for term in _SENSITIVE_KEY_TERMS)


def _safe_list(values: list[str]) -> list[str]:
    return [_safe_text(value) for value in values if _safe_text(value)]


def _safe_text(value: str) -> str:
    text = str(value or "")
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
    return text.strip()[:1000]


def _deduplicate_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        text = _safe_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        deduplicated.append(text)
    return deduplicated
