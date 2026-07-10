"""Source Evidence 视觉候选包和用户选择。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import datetime
import json
import math
import re
from typing import Any

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.credentials import (
    VisionAiProviderInvalid,
    VisionAiProviderNotConfigured,
    decrypt_vision_credential_key,
    load_project_vision_credential,
    parse_extra_headers,
    sanitize_ai_error,
)
from backend.app.ai.providers import ProviderConnectionError, call_provider_vision_json
from backend.app.models import (
    SourceEvidenceResourceRecord,
    SourceEvidenceRunRecord,
    SourceEvidenceVisualObservationRecord,
)
from backend.app.test_cases import source_evidence_storage
from backend.app.test_cases.schemas import (
    GenerationWarning,
    ParsedSourceUnit,
    SourceEvidenceObservationListResponse,
    SourceEvidenceObservationResponse,
    SourceEvidenceVisualCandidateResponse,
    SourceEvidenceVisualCandidatesResponse,
)
from backend.app.test_cases.source_evidence import (
    SourceEvidenceError,
    _build_source_evidence_sheet_options,
    _filter_resources_for_sheet,
    _find_sheet_unit,
    _load_parsed_source_for_context,
    _resolve_snapshot_sheet_name,
    is_source_evidence_expired,
    source_evidence_now,
)


VISUAL_EVIDENCE_DIR = "visual_evidence"
VISUAL_IMAGES_DIR = "visual_evidence/images"
VISUAL_CANDIDATES_PATH = "visual_evidence/visual_candidates.json"
VISUAL_SELECTIONS_PATH = "visual_evidence/visual_selections.json"
VISUAL_OBSERVATIONS_DIR = "visual_evidence/observations"
ADOPTED_VISUAL_EVIDENCE_PATH = "visual_evidence/adopted_visual_evidence.json"
MAX_IMAGE_LONG_EDGE = 1280

VISUAL_KEYWORDS = (
    "见图",
    "如下图",
    "截图",
    "图示",
    "图片",
    "界面",
    "入口",
    "按钮",
    "流程",
    "奖励",
)
IMAGE_FILENAME_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff")


@dataclass(frozen=True)
class VisualSelectionState:
    """视觉候选选择文件的兼容读取结果。"""

    selected_refs: list[str]
    selection_source: str
    sheet_name: str | None
    exists: bool


async def prepare_visual_evidence_for_run(
    db: AsyncSession,
    *,
    run: SourceEvidenceRunRecord,
) -> SourceEvidenceVisualCandidatesResponse:
    """为一个 ready Source Evidence Run 准备视觉候选和默认选择。"""
    resources = await _list_run_resources(db, project_id=run.project_id, run_id=run.id)
    manifest_items = _load_resource_manifest(project_id=run.project_id, run_id=run.id)
    manifest_by_ref = {str(item.get("ref") or ""): item for item in manifest_items}
    source_evidence_storage.resolve_source_evidence_path(run.project_id, run.id, VISUAL_EVIDENCE_DIR).mkdir(
        parents=True,
        exist_ok=True,
    )
    source_evidence_storage.resolve_source_evidence_path(run.project_id, run.id, VISUAL_IMAGES_DIR).mkdir(
        parents=True,
        exist_ok=True,
    )

    duplicate_counts = Counter(
        _resource_duplicate_key(resource)
        for resource in resources
        if resource.resource_type == "image"
    )
    candidates: list[dict[str, Any]] = []
    for resource in resources:
        manifest_item = manifest_by_ref.get(resource.ref, {})
        candidate = _build_candidate(
            run=run,
            resource=resource,
            manifest_item=manifest_item,
            duplicate_count=duplicate_counts.get(_resource_duplicate_key(resource), 1),
        )
        candidates.append(candidate)

    ready_candidates = [candidate for candidate in candidates if candidate["selectable"]]
    recommendation_budget = _recommendation_budget(len(ready_candidates))
    recommended_refs = [
        candidate["ref"]
        for candidate in sorted(
            ready_candidates,
            key=lambda item: (-int(item.get("rank_score") or 0), str(item.get("ref") or "")),
        )[:recommendation_budget]
    ]
    selectable_refs = {candidate["ref"] for candidate in ready_candidates}
    selected_refs = [ref for ref in recommended_refs if ref in selectable_refs]

    for candidate in candidates:
        candidate["recommended"] = candidate["ref"] in recommended_refs
        candidate["selected"] = candidate["ref"] in selected_refs

    source_evidence_storage.write_source_evidence_json(
        run.project_id,
        run.id,
        VISUAL_CANDIDATES_PATH,
        candidates,
    )
    source_evidence_storage.write_source_evidence_json(
        run.project_id,
        run.id,
        VISUAL_SELECTIONS_PATH,
        {
            "selected_refs": selected_refs,
            "selection_source": "auto",
            "sheet_name": None,
        },
    )
    _update_resource_visual_packets(resources, candidates)
    await db.flush()
    return _response_from_candidates(candidates, selected_refs=selected_refs)


async def build_visual_candidates_response(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    sheet_name: str | None = None,
) -> SourceEvidenceVisualCandidatesResponse:
    """读取视觉候选；候选文件缺失时对未过期 run 懒生成。"""
    run = await _get_project_run(db, project_id=project_id, run_id=run_id)
    if run.status == "cleaned":
        return SourceEvidenceVisualCandidatesResponse(
            items=[],
            recommended_refs=[],
            selected_refs=[],
            run_status="cleaned",
            warnings=[
                GenerationWarning(
                    source="source_evidence",
                    level="warning",
                    message="证据已清理，请重新读取来源。",
                )
            ],
        )
    _ensure_run_can_prepare_visual(run)
    try:
        candidates = _read_candidates(project_id=project_id, run_id=run_id)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        await prepare_visual_evidence_for_run(db, run=run)
        candidates = _read_candidates(project_id=project_id, run_id=run_id)

    resources: list[SourceEvidenceResourceRecord] | None = None
    resolved_sheet_name, selected_unit = _resolve_visual_sheet_scope(run, sheet_name)
    if selected_unit is not None and resolved_sheet_name is not None:
        resources = await _list_run_resources(db, project_id=project_id, run_id=run_id)
        fallback_refs = _sheet_default_selected_refs(
            candidates,
            resources,
            selected_unit=selected_unit,
            sheet_name=resolved_sheet_name,
        )
    else:
        fallback_refs = [candidate["ref"] for candidate in candidates if candidate.get("recommended")]

    selection_state = _load_visual_selection_state(
        project_id=project_id,
        run_id=run_id,
        fallback=fallback_refs,
        fallback_sheet_name=resolved_sheet_name,
    )
    selected_refs, should_persist_selection = _resolve_selected_refs_for_scope(
        selection_state,
        fallback_refs=fallback_refs,
        sheet_name=resolved_sheet_name,
    )
    selectable_refs = {candidate["ref"] for candidate in candidates if candidate.get("selectable")}
    selected_refs = [ref for ref in selected_refs if ref in selectable_refs]
    for candidate in candidates:
        candidate["selected"] = candidate["ref"] in selected_refs
    if should_persist_selection:
        _write_visual_selection_state(
            project_id=project_id,
            run_id=run_id,
            selected_refs=selected_refs,
            selection_source="auto",
            sheet_name=resolved_sheet_name,
        )
        source_evidence_storage.write_source_evidence_json(
            project_id,
            run_id,
            VISUAL_CANDIDATES_PATH,
            candidates,
        )
        if resources is None:
            resources = await _list_run_resources(db, project_id=project_id, run_id=run_id)
        _update_resource_visual_packets(resources, candidates)
        await db.flush()
    return _response_from_candidates(candidates, selected_refs=selected_refs)


async def save_visual_selections(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    selected_refs: list[str],
    sheet_name: str | None = None,
) -> SourceEvidenceVisualCandidatesResponse:
    """替换式保存用户选择。"""
    run = await _get_project_run(db, project_id=project_id, run_id=run_id)
    _ensure_run_can_prepare_visual(run)
    resolved_sheet_name, _selected_unit = _resolve_visual_sheet_scope(run, sheet_name)
    try:
        candidates = _read_candidates(project_id=project_id, run_id=run_id)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        await prepare_visual_evidence_for_run(db, run=run)
        candidates = _read_candidates(project_id=project_id, run_id=run_id)

    selectable_refs = {candidate["ref"] for candidate in candidates if candidate.get("selectable")}
    clean_selected_refs = [
        ref for ref in dict.fromkeys(selected_refs) if ref in selectable_refs
    ]
    for candidate in candidates:
        candidate["selected"] = candidate["ref"] in clean_selected_refs
    source_evidence_storage.write_source_evidence_json(
        project_id,
        run_id,
        VISUAL_SELECTIONS_PATH,
        {
            "selected_refs": clean_selected_refs,
            "selection_source": "manual",
            "sheet_name": resolved_sheet_name,
        },
    )
    source_evidence_storage.write_source_evidence_json(
        project_id,
        run_id,
        VISUAL_CANDIDATES_PATH,
        candidates,
    )
    resources = await _list_run_resources(db, project_id=project_id, run_id=run_id)
    _update_resource_visual_packets(resources, candidates)
    await db.flush()
    return _response_from_candidates(candidates, selected_refs=clean_selected_refs)


async def create_visual_observations(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    created_by: int | None,
) -> SourceEvidenceObservationListResponse:
    """对已保存选择的视觉候选生成 observation。"""
    run = await _get_project_run(db, project_id=project_id, run_id=run_id)
    _ensure_run_can_prepare_visual(run)
    try:
        credential = await load_project_vision_credential(db, project_id)
        api_key = decrypt_vision_credential_key(credential)
    except (VisionAiProviderInvalid, VisionAiProviderNotConfigured) as error:
        raise SourceEvidenceError(400, str(error)) from error

    try:
        candidates = _read_candidates(project_id=project_id, run_id=run_id)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        response = await prepare_visual_evidence_for_run(db, run=run)
        candidates = [item.model_dump(mode="json") for item in response.items]
        candidates = _read_candidates(project_id=project_id, run_id=run_id)

    selected_refs = _load_selected_refs(
        project_id=project_id,
        run_id=run_id,
        fallback=[],
    )
    if not selected_refs:
        raise SourceEvidenceError(400, "请先选择需要观察的图片资源。")

    resources = await _list_run_resources(db, project_id=project_id, run_id=run_id)
    resources_by_ref = {resource.ref: resource for resource in resources}
    selected_candidates = [
        candidate
        for candidate in candidates
        if candidate.get("ref") in selected_refs
        and candidate.get("selectable")
        and candidate.get("status") == "ready"
    ]
    if not selected_candidates:
        raise SourceEvidenceError(400, "已选择资源中没有可观察图片。")

    existing = await _list_visual_observation_records(
        db,
        project_id=project_id,
        run_id=run_id,
    )
    existing_by_ref = {record.ref: record for record in existing}
    for candidate in selected_candidates:
        ref = str(candidate.get("ref") or "")
        resource = resources_by_ref.get(ref)
        if resource is None:
            continue
        existing_record = existing_by_ref.get(ref)
        if existing_record is not None and existing_record.status == "adopted":
            continue
        observation_payload = await _observe_candidate(
            candidate=candidate,
            run=run,
            resource=resource,
            provider_preset=credential.provider_preset,  # type: ignore[arg-type]
            base_url=credential.base_url,
            model=credential.model,
            api_key=api_key,
            extra_headers=parse_extra_headers(credential.extra_headers_json),
        )
        record = await _upsert_observation_record(
            db,
            run=run,
            resource=resource,
            existing_record=existing_record,
            payload=observation_payload,
            created_by=created_by,
        )
        existing_by_ref[ref] = record

    await db.flush()
    await _sync_visual_candidate_adoption_status(
        db,
        project_id=project_id,
        run_id=run_id,
    )
    return await build_visual_observations_response(
        db,
        project_id=project_id,
        run_id=run_id,
    )


async def build_visual_observations_response(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> SourceEvidenceObservationListResponse:
    """读取 Source Evidence Run 的视觉 observation 安全响应。"""
    run = await _get_project_run(db, project_id=project_id, run_id=run_id)
    if run.status == "cleaned":
        return SourceEvidenceObservationListResponse(
            items=[],
            run_status="cleaned",
            warnings=[
                GenerationWarning(
                    source="source_evidence",
                    level="warning",
                    message="证据已清理，请重新读取来源。",
                )
            ],
        )
    _ensure_run_can_prepare_visual(run)
    records = await _list_visual_observation_records(
        db,
        project_id=project_id,
        run_id=run_id,
    )
    resources = await _list_run_resources(db, project_id=project_id, run_id=run_id)
    resource_by_id = {resource.id: resource for resource in resources}
    return SourceEvidenceObservationListResponse(
        items=[
            _observation_response(
                record,
                project_id=project_id,
                run_id=run_id,
                resource=resource_by_id.get(record.resource_id or 0),
            )
            for record in records
        ],
        warnings=[],
    )


async def adopt_visual_evidence(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    observation_ids: list[int],
    adopted_by: int | None,
) -> SourceEvidenceObservationListResponse:
    """将已观察 observation 显式采纳为 Adopted Visual Evidence。"""
    run = await _get_project_run(db, project_id=project_id, run_id=run_id)
    _ensure_run_can_prepare_visual(run)
    clean_ids = list(dict.fromkeys(int(item) for item in observation_ids if int(item) > 0))
    if not clean_ids:
        raise SourceEvidenceError(400, "请选择要采纳的视觉观察结果。")

    records = await _get_observation_records_by_ids(
        db,
        project_id=project_id,
        run_id=run_id,
        observation_ids=clean_ids,
    )
    now = source_evidence_now()
    resources = await _list_run_resources(db, project_id=project_id, run_id=run_id)
    resources_by_id = {resource.id: resource for resource in resources}
    for record in records:
        if record.status not in {"observed", "adopted"}:
            raise SourceEvidenceError(400, "只有已观察的视觉证据可以采纳。")
        record.status = "adopted"
        record.adopted_by = adopted_by
        record.adopted_at = now
        record.revoked_by = None
        record.revoked_at = None
        _update_observation_file_adoption(
            record,
            project_id=project_id,
            run_id=run_id,
            status="adopted",
            adopted_by=adopted_by,
            adopted_at=now,
            revoked_at=None,
        )
        resource = resources_by_id.get(record.resource_id or 0)
        if resource is not None:
            resource.status = "adopted"
            _write_resource_observation_index(resource, record)

    await db.flush()
    await _write_adopted_visual_evidence_index(db, project_id=project_id, run_id=run_id)
    await _sync_visual_candidate_adoption_status(db, project_id=project_id, run_id=run_id)
    return await build_visual_observations_response(
        db,
        project_id=project_id,
        run_id=run_id,
    )


async def revoke_adopted_visual_evidence(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    evidence_id: int,
    revoked_by: int | None,
) -> SourceEvidenceObservationListResponse:
    """撤销已采纳视觉证据，保留 observation 但不再进入生成。"""
    run = await _get_project_run(db, project_id=project_id, run_id=run_id)
    _ensure_run_can_prepare_visual(run)
    records = await _get_observation_records_by_ids(
        db,
        project_id=project_id,
        run_id=run_id,
        observation_ids=[evidence_id],
    )
    record = records[0]
    if record.status != "adopted":
        raise SourceEvidenceError(400, "该视觉证据尚未采纳。")

    now = source_evidence_now()
    record.status = "observed"
    record.revoked_by = revoked_by
    record.revoked_at = now
    record.adopted_by = None
    record.adopted_at = None
    _update_observation_file_adoption(
        record,
        project_id=project_id,
        run_id=run_id,
        status="observed",
        adopted_by=None,
        adopted_at=None,
        revoked_at=now,
    )

    if record.resource_id is not None:
        resource = await db.get(SourceEvidenceResourceRecord, record.resource_id)
        if resource is not None and resource.project_id == project_id and resource.run_id == run_id:
            resource.status = "observed"
            _write_resource_observation_index(resource, record)

    await db.flush()
    await _write_adopted_visual_evidence_index(db, project_id=project_id, run_id=run_id)
    await _sync_visual_candidate_adoption_status(db, project_id=project_id, run_id=run_id)
    return await build_visual_observations_response(
        db,
        project_id=project_id,
        run_id=run_id,
    )


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
    from backend.app.test_cases.source_evidence_cleanup import (
        ensure_run_not_expired_or_cleanup,
    )

    await ensure_run_not_expired_or_cleanup(db, run)
    return run


async def _list_run_resources(
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
        .order_by(SourceEvidenceResourceRecord.created_at.asc(), SourceEvidenceResourceRecord.id.asc())
    )
    return list(result.scalars().all())


async def _list_visual_observation_records(
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


async def _get_observation_records_by_ids(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    observation_ids: list[int],
) -> list[SourceEvidenceVisualObservationRecord]:
    result = await db.execute(
        select(SourceEvidenceVisualObservationRecord).where(
            SourceEvidenceVisualObservationRecord.project_id == project_id,
            SourceEvidenceVisualObservationRecord.run_id == run_id,
            SourceEvidenceVisualObservationRecord.id.in_(observation_ids),
        )
    )
    records = list(result.scalars().all())
    by_id = {record.id: record for record in records}
    if set(by_id) != set(observation_ids):
        raise SourceEvidenceError(404, "视觉证据不存在。")
    return [by_id[item] for item in observation_ids]


def _ensure_run_can_prepare_visual(run: SourceEvidenceRunRecord) -> None:
    if run.status in {"cleaned", "expired"} or is_source_evidence_expired(run):
        raise SourceEvidenceError(409, "证据已过期或已清理，请重新读取来源。")


def _load_resource_manifest(*, project_id: int, run_id: int) -> list[dict[str, Any]]:
    try:
        payload = source_evidence_storage.read_source_evidence_json(project_id, run_id, "resources.json")
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _read_candidates(*, project_id: int, run_id: int) -> list[dict[str, Any]]:
    payload = source_evidence_storage.read_source_evidence_json(project_id, run_id, VISUAL_CANDIDATES_PATH)
    if not isinstance(payload, list):
        raise ValueError("visual_candidates.json must contain a list")
    return [item for item in payload if isinstance(item, dict)]


def _load_selected_refs(
    *,
    project_id: int,
    run_id: int,
    fallback: list[str],
) -> list[str]:
    return _load_visual_selection_state(
        project_id=project_id,
        run_id=run_id,
        fallback=fallback,
        fallback_sheet_name=None,
    ).selected_refs


def _load_visual_selection_state(
    *,
    project_id: int,
    run_id: int,
    fallback: list[str],
    fallback_sheet_name: str | None,
) -> VisualSelectionState:
    try:
        payload = source_evidence_storage.read_source_evidence_json(project_id, run_id, VISUAL_SELECTIONS_PATH)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return VisualSelectionState(
            selected_refs=list(fallback),
            selection_source="auto",
            sheet_name=fallback_sheet_name,
            exists=False,
        )
    selected_refs = payload.get("selected_refs") if isinstance(payload, dict) else None
    if not isinstance(selected_refs, list):
        return VisualSelectionState(
            selected_refs=list(fallback),
            selection_source="auto",
            sheet_name=fallback_sheet_name,
            exists=True,
        )
    selection_source = str(payload.get("selection_source") or "auto")
    if selection_source not in {"auto", "manual"}:
        selection_source = "auto"
    return VisualSelectionState(
        selected_refs=[str(ref) for ref in selected_refs if isinstance(ref, str) and ref],
        selection_source=selection_source,
        sheet_name=_clean_sheet_name(payload.get("sheet_name")),
        exists=True,
    )


def _write_visual_selection_state(
    *,
    project_id: int,
    run_id: int,
    selected_refs: list[str],
    selection_source: str,
    sheet_name: str | None,
) -> None:
    source_evidence_storage.write_source_evidence_json(
        project_id,
        run_id,
        VISUAL_SELECTIONS_PATH,
        {
            "selected_refs": selected_refs,
            "selection_source": selection_source if selection_source in {"auto", "manual"} else "auto",
            "sheet_name": _clean_sheet_name(sheet_name),
        },
    )


def _resolve_visual_sheet_scope(
    run: SourceEvidenceRunRecord,
    sheet_name: str | None,
) -> tuple[str | None, ParsedSourceUnit | None]:
    requested_sheet_name = _clean_sheet_name(sheet_name)
    if requested_sheet_name is None:
        return None, None
    parsed = _load_parsed_source_for_context(
        project_id=run.project_id,
        run_id=run.id,
        source_type=run.source_type,
    )
    if parsed is None or not _build_source_evidence_sheet_options(parsed):
        return None, None
    resolved_sheet_name = _resolve_snapshot_sheet_name(parsed, requested_sheet_name)
    return resolved_sheet_name, _find_sheet_unit(parsed, resolved_sheet_name)


def _sheet_default_selected_refs(
    candidates: list[dict[str, Any]],
    resources: list[SourceEvidenceResourceRecord],
    *,
    selected_unit: ParsedSourceUnit,
    sheet_name: str,
) -> list[str]:
    sheet_resources = _filter_resources_for_sheet(
        resources,
        selected_unit=selected_unit,
        sheet_name=sheet_name,
    )
    sheet_refs = {resource.ref for resource in sheet_resources}
    return [
        str(candidate.get("ref") or "")
        for candidate in candidates
        if str(candidate.get("ref") or "") in sheet_refs
        and candidate.get("selectable")
        and candidate.get("status") == "ready"
    ]


def _resolve_selected_refs_for_scope(
    selection_state: VisualSelectionState,
    *,
    fallback_refs: list[str],
    sheet_name: str | None,
) -> tuple[list[str], bool]:
    if sheet_name is None:
        return selection_state.selected_refs, not selection_state.exists
    if (
        selection_state.selection_source == "manual"
        and selection_state.exists
        and selection_state.sheet_name in {None, sheet_name}
    ):
        return selection_state.selected_refs, False
    return list(fallback_refs), True


def _clean_sheet_name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_candidate(
    *,
    run: SourceEvidenceRunRecord,
    resource: SourceEvidenceResourceRecord,
    manifest_item: dict[str, Any],
    duplicate_count: int,
) -> dict[str, Any]:
    metadata = _json_object(resource.metadata_json)
    base = {
        "ref": resource.ref,
        "type": resource.resource_type,
        "position": resource.position,
        "filename": resource.filename,
        "download_status": resource.download_status,
        "adoption_status": resource.status,
        "mime_type": resource.mime_type,
        "status": "pending",
        "selectable": False,
        "recommended": False,
        "selected": False,
        "rank_score": 0,
        "recommendation_reasons": [],
        "dimensions": {},
        "context": _safe_context(metadata),
        "packet": {},
    }
    if resource.download_status == "pending_permission":
        return {**base, "status": "pending_permission"}
    if resource.download_status == "download_failed":
        return {**base, "status": "download_failed"}
    if resource.download_status != "downloaded":
        return {**base, "status": "pending"}
    if not _resource_is_visual_type(resource):
        return {**base, "status": "unsupported_attachment"}

    local_path = resource.local_path or str(manifest_item.get("local_path") or "")
    if not local_path:
        return {**base, "status": "missing"}
    source_path = source_evidence_storage.resolve_source_evidence_path(run.project_id, run.id, local_path)
    if not source_path.is_file():
        return {**base, "status": "missing"}

    try:
        packet = _optimize_image(
            project_id=run.project_id,
            run_id=run.id,
            ref=resource.ref,
            source_relative_path=local_path,
        )
    except (UnidentifiedImageError, OSError, ValueError):
        return {**base, "status": "invalid_image"}

    reasons, score = _recommendation_reasons(
        resource=resource,
        metadata=metadata,
        dimensions=packet["dimensions"],
        duplicate_count=duplicate_count,
    )
    return {
        **base,
        "status": "ready",
        "selectable": True,
        "rank_score": score,
        "recommendation_reasons": reasons,
        "dimensions": packet["dimensions"],
        "packet": packet,
    }


async def _observe_candidate(
    *,
    candidate: dict[str, Any],
    run: SourceEvidenceRunRecord,
    resource: SourceEvidenceResourceRecord,
    provider_preset: str,
    base_url: str,
    model: str,
    api_key: str,
    extra_headers: dict[str, str],
) -> dict[str, Any]:
    packet = candidate.get("packet") if isinstance(candidate.get("packet"), dict) else {}
    optimized_image = str(packet.get("optimized_image") or "")
    if not optimized_image:
        raise SourceEvidenceError(400, f"资源 {resource.ref} 缺少可观察图片包。")
    image_path = source_evidence_storage.resolve_source_evidence_path(
        run.project_id,
        run.id,
        optimized_image,
    )
    if not image_path.is_file():
        raise SourceEvidenceError(400, f"资源 {resource.ref} 的优化图片不存在。")

    try:
        image_bytes = image_path.read_bytes()
    except OSError as exc:
        raise SourceEvidenceError(400, f"资源 {resource.ref} 的优化图片无法读取。") from exc

    schema = _observation_json_schema()
    try:
        payload, _meta = await call_provider_vision_json(
            provider_preset=provider_preset,  # type: ignore[arg-type]
            base_url=base_url,
            model=model,
            api_key=api_key,
            system_prompt="你是测试需求视觉观察助手。只返回 JSON，不要输出 Markdown。",
            user_prompt=_build_observation_prompt(candidate=candidate, resource=resource),
            image_bytes=image_bytes,
            image_mime_type="image/jpeg",
            json_schema=schema,
            extra_headers=extra_headers,
            timeout_seconds=60.0,
        )
    except ProviderConnectionError as error:
        raise SourceEvidenceError(
            error.status_code,
            sanitize_ai_error(error.message, api_key),
        ) from error
    return _normalize_observation_payload(
        payload,
        provider_preset=provider_preset,
        model=model,
    )


async def _upsert_observation_record(
    db: AsyncSession,
    *,
    run: SourceEvidenceRunRecord,
    resource: SourceEvidenceResourceRecord,
    existing_record: SourceEvidenceVisualObservationRecord | None,
    payload: dict[str, Any],
    created_by: int | None,
) -> SourceEvidenceVisualObservationRecord:
    now = source_evidence_now()
    record = existing_record
    if record is None:
        record = SourceEvidenceVisualObservationRecord(
            run_id=run.id,
            project_id=run.project_id,
            resource_id=resource.id,
            ref=resource.ref,
            position=resource.position,
            filename=resource.filename,
            status="observed",
            created_by=created_by,
        )
        db.add(record)
        await db.flush()
    else:
        record.resource_id = resource.id
        record.position = resource.position
        record.filename = resource.filename
        record.status = "observed"
        record.created_by = created_by
        record.adopted_by = None
        record.adopted_at = None
    observation_path = f"{VISUAL_OBSERVATIONS_DIR}/{record.id}.json"
    observation_payload = {
        "id": record.id,
        "run_id": run.id,
        "resource_id": resource.id,
        "ref": resource.ref,
        "type": resource.resource_type,
        "position": resource.position,
        "summary": payload["summary"],
        "visible_text": payload["visible_text"],
        "confidence": payload["confidence"],
        "limitations": payload["limitations"],
        "source": payload["source"],
        "created_by": created_by,
        "created_at": _datetime_to_iso(now),
        "status": "observed",
    }
    source_evidence_storage.write_source_evidence_json(
        run.project_id,
        run.id,
        observation_path,
        observation_payload,
    )
    record.observation_path = observation_path
    resource.status = "observed"
    _write_resource_observation_index(resource, record, payload=observation_payload)
    return record


def _resource_is_visual_type(resource: SourceEvidenceResourceRecord) -> bool:
    if resource.resource_type == "image":
        return True
    if resource.resource_type != "attachment":
        return False
    return resource.mime_type.startswith("image/") or resource.filename.lower().endswith(IMAGE_FILENAME_SUFFIXES)


def _optimize_image(
    *,
    project_id: int,
    run_id: int,
    ref: str,
    source_relative_path: str,
) -> dict[str, Any]:
    source_path = source_evidence_storage.resolve_source_evidence_path(project_id, run_id, source_relative_path)
    output_relative_path = f"{VISUAL_IMAGES_DIR}/{_safe_stem(ref)}.jpg"
    output_path = source_evidence_storage.resolve_source_evidence_path(project_id, run_id, output_relative_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as image:
        original_width, original_height = image.size
        optimized = image.convert("RGB")
        optimized_width, optimized_height = _scaled_size(
            original_width,
            original_height,
            max_long_edge=MAX_IMAGE_LONG_EDGE,
        )
        if (optimized_width, optimized_height) != optimized.size:
            optimized = optimized.resize(
                (optimized_width, optimized_height),
                Image.Resampling.LANCZOS,
            )
        optimized.save(output_path, format="JPEG", quality=90, optimize=True, progressive=True)

    return {
        "optimized_image": output_relative_path,
        "source_image": source_relative_path,
        "dimensions": {
            "original_width": original_width,
            "original_height": original_height,
            "optimized_width": optimized_width,
            "optimized_height": optimized_height,
        },
    }


def _recommendation_reasons(
    *,
    resource: SourceEvidenceResourceRecord,
    metadata: dict[str, Any],
    dimensions: dict[str, int],
    duplicate_count: int,
) -> tuple[list[str], int]:
    reasons: list[str] = []
    score = 0
    context_text = "\n".join(
        str(value)
        for value in _safe_context(metadata).values()
        if isinstance(value, str) and value.strip()
    )
    filename_text = resource.filename or ""
    if any(keyword in context_text for keyword in VISUAL_KEYWORDS):
        reasons.append("附近文本包含视觉关键词")
        score += 40
    if any(keyword in filename_text for keyword in VISUAL_KEYWORDS):
        reasons.append("文件名包含视觉关键词")
        score += 20
    if _position_rank(resource.position) <= 3:
        reasons.append("文档位置靠前")
        score += 15
    if dimensions.get("original_width", 0) * dimensions.get("original_height", 0) >= 800 * 600:
        reasons.append("图片尺寸较大")
        score += 20
    if duplicate_count > 1:
        reasons.append("存在相似或重复资源，仅推荐代表图")
        score -= 5
    if not reasons:
        reasons.append("可观察图片资源")
        score += 5
    return reasons, score


def _recommendation_budget(ready_count: int) -> int:
    if ready_count <= 0:
        return 0
    if ready_count == 1:
        return 1
    return max(1, min(3, math.ceil(ready_count / 2)))


def _update_resource_visual_packets(
    resources: list[SourceEvidenceResourceRecord],
    candidates: list[dict[str, Any]],
) -> None:
    by_ref = {candidate["ref"]: candidate for candidate in candidates}
    for resource in resources:
        candidate = by_ref.get(resource.ref)
        if not candidate:
            continue
        resource.visual_packet_path = VISUAL_CANDIDATES_PATH
        metadata = _json_object(resource.metadata_json)
        metadata["visual_packet"] = {
                "ref": candidate["ref"],
                "status": candidate["status"],
                "selectable": candidate["selectable"],
                "recommended": candidate.get("recommended", False),
                "selected": candidate.get("selected", False),
                "recommendation_reasons": candidate.get("recommendation_reasons", []),
                "dimensions": candidate.get("dimensions", {}),
            }
        resource.metadata_json = json.dumps(metadata, ensure_ascii=False)


async def _sync_visual_candidate_adoption_status(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> None:
    try:
        candidates = _read_candidates(project_id=project_id, run_id=run_id)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return
    resources = await _list_run_resources(db, project_id=project_id, run_id=run_id)
    status_by_ref = {resource.ref: resource.status for resource in resources}
    for candidate in candidates:
        ref = str(candidate.get("ref") or "")
        if ref in status_by_ref:
            candidate["adoption_status"] = status_by_ref[ref]
    source_evidence_storage.write_source_evidence_json(
        project_id,
        run_id,
        VISUAL_CANDIDATES_PATH,
        candidates,
    )


def _observation_response(
    record: SourceEvidenceVisualObservationRecord,
    *,
    project_id: int,
    run_id: int,
    resource: SourceEvidenceResourceRecord | None,
) -> SourceEvidenceObservationResponse:
    detail = _read_observation_detail(
        project_id=project_id,
        run_id=run_id,
        observation_path=record.observation_path,
    )
    source = detail.get("source") if isinstance(detail.get("source"), dict) else {}
    return SourceEvidenceObservationResponse(
        id=record.id,
        ref=record.ref,
        resource_id=record.resource_id,
        type=resource.resource_type if resource is not None else str(detail.get("type") or ""),
        position=record.position,
        filename=record.filename,
        status=record.status,
        summary=str(detail.get("summary") or ""),
        visible_text=_coerce_text(detail.get("visible_text")),
        confidence=_coerce_confidence(detail.get("confidence")),
        limitations=_coerce_string_list(detail.get("limitations")),
        source={key: str(value) for key, value in source.items() if key in {"provider", "model", "protocol"}},
        created_by=record.created_by,
        created_at=_datetime_to_iso(record.created_at),
        adopted_by=record.adopted_by,
        adopted_at=_datetime_to_iso(record.adopted_at),
        revoked_at=_datetime_to_iso(record.revoked_at),
    )


async def _write_adopted_visual_evidence_index(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> None:
    records = await _list_visual_observation_records(db, project_id=project_id, run_id=run_id)
    resources = await _list_run_resources(db, project_id=project_id, run_id=run_id)
    resource_by_id = {resource.id: resource for resource in resources}
    adopted = [
        _observation_response(
            record,
            project_id=project_id,
            run_id=run_id,
            resource=resource_by_id.get(record.resource_id or 0),
        ).model_dump(mode="json")
        for record in records
        if record.status == "adopted"
    ]
    source_evidence_storage.write_source_evidence_json(
        project_id,
        run_id,
        ADOPTED_VISUAL_EVIDENCE_PATH,
        {"items": adopted},
    )


def _update_observation_file_adoption(
    record: SourceEvidenceVisualObservationRecord,
    *,
    project_id: int,
    run_id: int,
    status: str,
    adopted_by: int | None,
    adopted_at: datetime.datetime | None,
    revoked_at: datetime.datetime | None,
) -> None:
    detail = _read_observation_detail(
        project_id=project_id,
        run_id=run_id,
        observation_path=record.observation_path,
    )
    if not detail:
        return
    detail["status"] = status
    detail["adopted_by"] = adopted_by
    detail["adopted_at"] = _datetime_to_iso(adopted_at)
    detail["revoked_at"] = _datetime_to_iso(revoked_at)
    source_evidence_storage.write_source_evidence_json(
        project_id,
        run_id,
        record.observation_path,
        detail,
    )


def _write_resource_observation_index(
    resource: SourceEvidenceResourceRecord,
    record: SourceEvidenceVisualObservationRecord,
    *,
    payload: dict[str, Any] | None = None,
) -> None:
    detail = payload or {}
    resource.observation_json = json.dumps(
        {
            "observation_id": record.id,
            "status": record.status,
            "ref": record.ref,
            "summary": str(detail.get("summary") or "")[:500],
            "observation_path": record.observation_path,
        },
        ensure_ascii=False,
    )


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


def _build_observation_prompt(
    *,
    candidate: dict[str, Any],
    resource: SourceEvidenceResourceRecord,
) -> str:
    context = candidate.get("context") if isinstance(candidate.get("context"), dict) else {}
    context_lines = [
        f"- {key}: {value}"
        for key, value in context.items()
        if isinstance(value, str) and value.strip()
    ]
    if not context_lines:
        context_lines = ["- 无"]
    return "\n".join(
        [
            "请只根据图片中可见内容生成视觉观察 JSON。",
            f"资源 ref: {resource.ref}",
            f"文档位置: {resource.position}",
            "附近文本仅用于定位，不得替代图片可见事实，也不得把文件名或附近文字当作需求依据。",
            "附近文本：",
            *context_lines,
            "返回字段：summary、visible_text、confidence、limitations。",
            "summary 只描述图片可见 UI、流程或文字；limitations 说明无法从图片确认的内容。",
        ]
    )


def _observation_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "visible_text": {"type": "string"},
            "confidence": {"type": "number"},
            "limitations": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "visible_text", "confidence", "limitations"],
    }


def _normalize_observation_payload(
    payload: dict[str, Any],
    *,
    provider_preset: str,
    model: str,
) -> dict[str, Any]:
    return {
        "summary": _coerce_text(payload.get("summary"))[:1200],
        "visible_text": _coerce_text(payload.get("visible_text"))[:1200],
        "confidence": _coerce_confidence(payload.get("confidence")),
        "limitations": _coerce_string_list(payload.get("limitations"))[:10],
        "source": {
            "provider": provider_preset,
            "model": model,
            "protocol": "openai_compatible",
        },
    }


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
    return [_coerce_text(value)] if _coerce_text(value) else []


def _coerce_confidence(value: Any) -> float | None:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, confidence))


def _response_from_candidates(
    candidates: list[dict[str, Any]],
    *,
    selected_refs: list[str],
) -> SourceEvidenceVisualCandidatesResponse:
    safe_items = []
    for candidate in candidates:
        safe_items.append(
            SourceEvidenceVisualCandidateResponse(
                ref=str(candidate.get("ref") or ""),
                type=str(candidate.get("type") or ""),
                position=str(candidate.get("position") or ""),
                filename=str(candidate.get("filename") or ""),
                status=str(candidate.get("status") or ""),
                selectable=bool(candidate.get("selectable")),
                recommended=bool(candidate.get("recommended")),
                selected=bool(candidate.get("selected")),
                recommendation_reasons=[
                    str(reason)
                    for reason in candidate.get("recommendation_reasons", [])
                    if isinstance(reason, str)
                ],
                download_status=str(candidate.get("download_status") or "pending"),
                adoption_status=str(candidate.get("adoption_status") or "unobserved"),
                dimensions={
                    str(key): int(value)
                    for key, value in (candidate.get("dimensions") or {}).items()
                    if isinstance(value, int)
                },
            )
        )
    return SourceEvidenceVisualCandidatesResponse(
        items=safe_items,
        recommended_refs=[
            item.ref for item in safe_items if item.recommended
        ],
        selected_refs=selected_refs,
        warnings=_candidate_warnings(safe_items),
    )


def _candidate_warnings(
    items: list[SourceEvidenceVisualCandidateResponse],
) -> list[GenerationWarning]:
    warnings: list[GenerationWarning] = []
    blocked_count = sum(1 for item in items if item.status in {"pending_permission", "download_failed", "missing"})
    if blocked_count:
        warnings.append(
            GenerationWarning(
                source="source_evidence",
                level="warning",
                message=f"{blocked_count} 个资源因权限、下载或本地文件缺失暂不可观察。",
            )
        )
    unsupported_count = sum(1 for item in items if item.status == "unsupported_attachment")
    if unsupported_count:
        warnings.append(
            GenerationWarning(
                source="source_evidence",
                level="info",
                message=f"{unsupported_count} 个非图片附件已保留在资源清单中，暂不进入视觉观察。",
            )
        )
    if any(item.selectable for item in items):
        warnings.append(
            GenerationWarning(
                source="visual_evidence",
                level="info",
                message="未采纳资源不作为需求事实，需观察并显式采纳后才可进入生成。",
            )
        )
    return warnings


def _safe_context(metadata: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = (
        "nearby_heading",
        "nearby_text_before",
        "nearby_text_after",
        "row_context",
        "column_context",
        "sheet_title",
        "anchor",
    )
    return {key: metadata[key] for key in allowed_keys if key in metadata}


def _resource_duplicate_key(resource: SourceEvidenceResourceRecord) -> str:
    return f"{resource.filename}|{resource.mime_type}"


def _position_rank(position: str) -> int:
    numbers = [int(match) for match in re.findall(r"\d+", position)]
    return min(numbers) if numbers else 9999


def _scaled_size(width: int, height: int, *, max_long_edge: int) -> tuple[int, int]:
    long_edge = max(width, height)
    if long_edge <= 0 or long_edge <= max_long_edge:
        return width, height
    scale = max_long_edge / long_edge
    return max(1, round(width * scale)), max(1, round(height * scale))


def _safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "image"


def _datetime_to_iso(value: datetime.datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.UTC)
    return value.isoformat()


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}
