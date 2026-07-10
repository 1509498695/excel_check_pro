"""Automatic deterministic artifact bundle for V3 Generation Runs."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import (
    TestCaseCoverageAuditRecord,
    TestCaseGenerationCaseRecord,
    TestCaseGenerationRunRecord,
    TestCaseRequirementAtomRecord,
)
from backend.app.test_cases.artifact_renderer import build_canonical_test_case_workbook
from backend.app.test_cases.case_contract import canonical_case_fields
from backend.app.test_cases.generation_artifact_storage import (
    ARTIFACT_FILE_NAMES,
    generation_artifact_path,
    write_generation_artifact_bytes,
    write_generation_artifact_text,
)
from backend.app.test_cases.generation_runs import (
    GENERATION_RUN_COMPLETED_STATUSES,
    RUN_NOT_EXPORTABLE_MESSAGE,
    GenerationRunError,
    get_project_generation_run,
    update_generation_run_stage,
)
from backend.app.test_cases.schemas import (
    TestCaseGenerationArtifactListResponse,
    TestCaseGenerationArtifactResponse,
)


ARTIFACT_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "key": "workbook",
        "label": "测试用例 Excel",
        "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "preview_kind": "cases",
    },
    {
        "key": "blueprint",
        "label": "用例蓝图",
        "media_type": "text/markdown; charset=utf-8",
        "preview_kind": "markdown",
    },
    {
        "key": "stats",
        "label": "用例统计",
        "media_type": "application/json; charset=utf-8",
        "preview_kind": "json",
    },
    {
        "key": "coverage_audit",
        "label": "覆盖审计",
        "media_type": "application/json; charset=utf-8",
        "preview_kind": "json",
    },
    {
        "key": "quality_audit",
        "label": "质量审计",
        "media_type": "application/json; charset=utf-8",
        "preview_kind": "json",
    },
)


async def render_generation_run_artifacts(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    allow_terminal: bool = False,
) -> TestCaseGenerationArtifactListResponse:
    """Render and persist the whole artifact bundle; no AI or external system calls."""
    run = await get_project_generation_run(db, project_id=project_id, run_id=run_id)
    if run.status in {"expired", "cancelled", "failed"}:
        raise GenerationRunError(409, RUN_NOT_EXPORTABLE_MESSAGE)
    terminal_on_entry = run.status in GENERATION_RUN_COMPLETED_STATUSES
    if terminal_on_entry and not allow_terminal:
        raise GenerationRunError(409, "Generation Run 已完成，不能重复自动渲染。")
    stage_payload = _json_object(run.stage_payload_json)
    quality_audit = _json_object(stage_payload.get("quality_audit"))
    coverage_record = await _load_coverage_audit(
        db,
        project_id=project_id,
        run_id=run.id,
    )
    cases = await _load_cases(db, project_id=project_id, run_id=run.id)
    atoms = await _load_atoms(db, project_id=project_id, run_id=run.id)
    case_payloads = [
        {
            "case_id": record.case_id,
            "fields": _json_object(record.fields_json),
            "atom_refs": [str(item) for item in _json_list(record.atom_refs_json)],
        }
        for record in cases
    ]
    atom_payloads = [
        {
            "atom_id": atom.atom_id,
            "atom_type": atom.atom_type,
            "requirement_text": atom.requirement_text,
            "source_sheet_name": atom.source_sheet_name,
            "source_row_start": atom.source_row_start,
            "source_row_end": atom.source_row_end,
            "coverage_status": atom.coverage_status,
        }
        for atom in atoms
    ]
    coverage_audit = _coverage_payload(coverage_record)
    blueprint = _json_object(stage_payload.get("blueprint"))
    stats = _stats_payload(case_payloads)
    blueprint_markdown = _blueprint_markdown(
        title=run.planning_sheet_name,
        blueprint=blueprint,
        quality_audit=quality_audit,
    )
    write_generation_artifact_text(
        project_id=project_id,
        run_id=run.id,
        key="blueprint",
        content=blueprint_markdown,
    )
    for key, payload in (
        ("stats", stats),
        ("coverage_audit", coverage_audit),
        ("quality_audit", quality_audit),
    ):
        write_generation_artifact_text(
            project_id=project_id,
            run_id=run.id,
            key=key,
            content=json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        )

    blocks_export = _blocks_export(run=run, coverage=coverage_audit, quality=quality_audit)
    workbook_message = ""
    if not blocks_export:
        workbook = build_canonical_test_case_workbook(
            cases=case_payloads,
            title=run.planning_sheet_name,
            source_summary=(
                f"Planning Sheet：{run.planning_sheet_name}；"
                f"Source Evidence Run：{run.source_evidence_run_id}"
            ),
            blueprint=blueprint,
            atoms=atom_payloads,
            coverage_audit=coverage_audit,
            quality_audit=quality_audit,
            metadata={
                "title": run.planning_sheet_name,
                "run_id": run.id,
                "status": quality_audit.get("recommended_run_status", run.status),
                "strict_mode": run.strict_mode,
            },
        )
        write_generation_artifact_bytes(
            project_id=project_id,
            run_id=run.id,
            key="workbook",
            content=workbook.getvalue(),
        )
    else:
        workbook_path = generation_artifact_path(
            project_id=project_id,
            run_id=run.id,
            key="workbook",
        )
        workbook_path.unlink(missing_ok=True)
        workbook_message = "严格模式下存在阻塞问题，未生成可下载 Excel。"

    items = _artifact_items(
        project_id=project_id,
        run_id=run.id,
        workbook_blocked=blocks_export,
        workbook_message=workbook_message,
    )
    rendering_payload = {
        "status": "completed" if not blocks_export else "partial_completed",
        "items": [item.model_dump(mode="json") for item in items],
        "blocks_export": blocks_export,
    }
    final_status = str(quality_audit.get("recommended_run_status") or "completed")
    if final_status not in {"completed", "partial_completed", "failed"}:
        final_status = "partial_completed"
    if blocks_export and final_status == "completed":
        final_status = "partial_completed"

    if terminal_on_entry:
        run_record = await db.get(TestCaseGenerationRunRecord, run.id)
        if run_record is not None:
            run_record.stage_payload_json = json.dumps(
                {
                    **stage_payload,
                    "rendering_artifacts": rendering_payload,
                },
                ensure_ascii=False,
            )
            await db.flush()
    else:
        await update_generation_run_stage(
            db,
            project_id=project_id,
            run_id=run.id,
            status=final_status,
            case_count=len(cases),
            stage_payload={
                **stage_payload,
                "rendering_artifacts": rendering_payload,
            },
        )
    return TestCaseGenerationArtifactListResponse(items=items, total=len(items))


async def list_generation_run_artifacts(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> TestCaseGenerationArtifactListResponse:
    run = await get_project_generation_run(db, project_id=project_id, run_id=run_id)
    rendering = _json_object(_json_object(run.stage_payload_json).get("rendering_artifacts"))
    raw_items = rendering.get("items")
    if not isinstance(raw_items, list):
        return TestCaseGenerationArtifactListResponse(items=[], total=0)
    items: list[TestCaseGenerationArtifactResponse] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        item = TestCaseGenerationArtifactResponse.model_validate(raw)
        if item.status == "ready":
            path = generation_artifact_path(
                project_id=project_id,
                run_id=run.id,
                key=item.key,
            )
            if not path.is_file():
                item = item.model_copy(
                    update={
                        "status": "missing",
                        "message": "产物文件已缺失，请重试渲染。",
                    }
                )
        items.append(item)
    return TestCaseGenerationArtifactListResponse(items=items, total=len(items))


async def get_generation_run_artifact_path(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    artifact_key: str,
) -> tuple[Path, TestCaseGenerationArtifactResponse]:
    listing = await list_generation_run_artifacts(
        db,
        project_id=project_id,
        run_id=run_id,
    )
    item = next((candidate for candidate in listing.items if candidate.key == artifact_key), None)
    if item is None:
        raise GenerationRunError(404, "Generation Run 产物不存在。")
    if item.status != "ready":
        raise GenerationRunError(409, item.message or "Generation Run 产物不可用。")
    path = generation_artifact_path(
        project_id=project_id,
        run_id=run_id,
        key=artifact_key,
    )
    if not path.is_file():
        raise GenerationRunError(409, "Generation Run 产物文件已缺失，请重试渲染。")
    return path, item


def _artifact_items(
    *,
    project_id: int,
    run_id: int,
    workbook_blocked: bool,
    workbook_message: str,
) -> list[TestCaseGenerationArtifactResponse]:
    items: list[TestCaseGenerationArtifactResponse] = []
    for definition in ARTIFACT_DEFINITIONS:
        key = definition["key"]
        blocked = key == "workbook" and workbook_blocked
        path = generation_artifact_path(project_id=project_id, run_id=run_id, key=key)
        content = path.read_bytes() if path.is_file() else b""
        items.append(
            TestCaseGenerationArtifactResponse(
                key=key,
                label=definition["label"],
                file_name=ARTIFACT_FILE_NAMES[key],
                media_type=definition["media_type"],
                preview_kind=definition["preview_kind"],
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest() if content else "",
                status="blocked" if blocked else ("ready" if content else "missing"),
                message=workbook_message if blocked else "",
            )
        )
    return items


def _stats_payload(cases: list[dict[str, Any]]) -> dict[str, Any]:
    canonical = [
        canonical_case_fields(
            _json_object(case.get("fields")),
            case_id=str(case.get("case_id") or ""),
        )
        for case in cases
    ]
    return {
        "status": "ok",
        "cases": len(canonical),
        "by_priority": dict(Counter(case["priority"] for case in canonical)),
        "by_module": dict(Counter(case["primary_module"] for case in canonical)),
    }


def _coverage_payload(audit: TestCaseCoverageAuditRecord | None) -> dict[str, Any]:
    if audit is None:
        return {
            "status": "missing",
            "total_atoms": 0,
            "covered_atoms": 0,
            "uncovered_atoms": 0,
            "uncovered_atom_ids": [],
            "export_limitations": [],
        }
    return {
        "status": audit.status,
        "total_atoms": audit.total_atoms,
        "covered_atoms": audit.covered_atoms,
        "uncovered_atoms": audit.uncovered_atoms,
        "unfounded_case_count": audit.unfounded_case_count,
        "failed_chunk_count": audit.failed_chunk_count,
        "uncovered_atom_ids": _json_list(audit.uncovered_atom_ids_json),
        "supplement_summary": _json_object(audit.supplement_summary_json),
        "export_limitations": _json_list(audit.export_limitations_json),
        "warnings": _json_list(audit.warnings_json),
    }


def _blocks_export(
    *,
    run: TestCaseGenerationRunRecord,
    coverage: dict[str, Any],
    quality: dict[str, Any],
) -> bool:
    if not run.strict_mode:
        return False
    if quality.get("blocks_export"):
        return True
    return any(
        isinstance(item, dict) and bool(item.get("blocks_export"))
        for item in coverage.get("export_limitations", [])
    )


def _blueprint_markdown(
    *,
    title: str,
    blueprint: dict[str, Any],
    quality_audit: dict[str, Any],
) -> str:
    lines = [f"# {title}：用例蓝图", ""]
    if not blueprint:
        lines.extend(["未生成结构化蓝图。", ""])
    for key, value in blueprint.items():
        lines.extend([f"## {key}", "", _markdown_value(value), ""])
    lines.extend(
        [
            "## Case Quality Audit",
            "",
            f"- 状态：{quality_audit.get('status', 'unknown')}",
            f"- 阻塞问题：{quality_audit.get('blocking_count', 0)}",
            f"- 警告：{quality_audit.get('warning_count', 0)}",
            f"- 已执行修复：{quality_audit.get('repair_attempted', False)}",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _markdown_value(value: Any) -> str:
    if isinstance(value, list):
        if not value:
            return "- 无"
        return "\n".join(
            f"- {json.dumps(item, ensure_ascii=False) if isinstance(item, (dict, list)) else item}"
            for item in value
        )
    if isinstance(value, dict):
        return "~~~json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n~~~"
    return str(value)


async def _load_coverage_audit(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> TestCaseCoverageAuditRecord | None:
    return (
        await db.execute(
            select(TestCaseCoverageAuditRecord).where(
                TestCaseCoverageAuditRecord.project_id == project_id,
                TestCaseCoverageAuditRecord.run_id == run_id,
            )
        )
    ).scalar_one_or_none()


async def _load_cases(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> list[TestCaseGenerationCaseRecord]:
    return list(
        (
            await db.execute(
                select(TestCaseGenerationCaseRecord)
                .where(
                    TestCaseGenerationCaseRecord.project_id == project_id,
                    TestCaseGenerationCaseRecord.run_id == run_id,
                    TestCaseGenerationCaseRecord.status == "official",
                )
                .order_by(TestCaseGenerationCaseRecord.id)
            )
        ).scalars()
    )


async def _load_atoms(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> list[TestCaseRequirementAtomRecord]:
    return list(
        (
            await db.execute(
                select(TestCaseRequirementAtomRecord)
                .where(
                    TestCaseRequirementAtomRecord.project_id == project_id,
                    TestCaseRequirementAtomRecord.run_id == run_id,
                )
                .order_by(TestCaseRequirementAtomRecord.id)
            )
        ).scalars()
    )


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        loaded = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        loaded = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return []
    return loaded if isinstance(loaded, list) else []
