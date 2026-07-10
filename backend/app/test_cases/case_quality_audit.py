"""Deterministic case-quality audit with one safe targeted repair pass."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import (
    TestCaseGenerationCaseRecord,
    TestCaseGenerationRunRecord,
    TestCaseRequirementAtomRecord,
)
from backend.app.test_cases.case_contract import canonical_case_fields
from backend.app.test_cases.constants import CANONICAL_PRIMARY_MODULES
from backend.app.test_cases.generation_runs import (
    get_project_generation_run,
    update_generation_run_stage,
)


_GENERIC_EXPECTATIONS = (
    "与配置一致",
    "按配置展示",
    "显示正确",
    "结果正确",
    "功能正常",
    "符合预期",
    "获得对应",
)
_NUMERIC_RULE_RE = re.compile(
    r"\d|%|％|小时|分钟|秒|等级|级|上限|下限|概率|权重|消耗|返还|ID|id|公式"
)


async def run_case_quality_audit_for_run(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> dict[str, Any]:
    """Audit official cases, run one safe repair pass, and queue artifact rendering."""
    run = await get_project_generation_run(db, project_id=project_id, run_id=run_id)
    stage_payload = _json_object(run.stage_payload_json)
    await update_generation_run_stage(
        db,
        project_id=project_id,
        run_id=run.id,
        status="auditing_quality",
        stage_payload={
            **stage_payload,
            "quality_audit": {"status": "started"},
        },
    )
    cases = await _load_cases(db, project_id=project_id, run_id=run.id)
    atoms = await _load_atoms(db, project_id=project_id, run_id=run.id)
    atom_text = {atom.atom_id: atom.requirement_text for atom in atoms}

    existing_quality = _json_object(stage_payload.get("quality_audit"))
    repair_attempted = bool(existing_quality.get("repair_attempted"))
    repaired_case_count = 0
    if not repair_attempted:
        await update_generation_run_stage(
            db,
            project_id=project_id,
            run_id=run.id,
            status="repairing_cases",
            stage_payload={
                **stage_payload,
                "quality_audit": {
                    "status": "repairing",
                    "repair_attempted": True,
                },
            },
        )
        for record in cases:
            fields = _json_object(record.fields_json)
            repaired = _safe_repair_fields(
                fields,
                case_id=record.case_id,
                atom_refs=[str(item) for item in _json_list(record.atom_refs_json)],
            )
            if repaired != fields:
                record.fields_json = json.dumps(repaired, ensure_ascii=False)
                repaired_case_count += 1
        await db.flush()

    issues = _audit_cases(cases, atom_text=atom_text)
    blocking_count = sum(1 for item in issues if item["severity"] == "blocking")
    warning_count = sum(1 for item in issues if item["severity"] == "warning")
    coverage = _json_object(stage_payload.get("coverage_audit"))
    coverage_status = str(coverage.get("recommended_run_status") or "completed")
    recommended_run_status = _recommended_run_status(
        case_count=len(cases),
        blocking_count=blocking_count,
        coverage_status=coverage_status,
    )
    blocks_export = bool(run.strict_mode and blocking_count)
    quality_payload = {
        "status": "completed" if not blocking_count else "partial_completed",
        "case_count": len(cases),
        "blocking_count": blocking_count,
        "warning_count": warning_count,
        "issues": issues,
        "repair_attempted": True,
        "repaired_case_count": repaired_case_count,
        "blocks_export": blocks_export,
        "recommended_run_status": recommended_run_status,
    }
    run_record = await db.get(TestCaseGenerationRunRecord, run.id)
    if run_record is not None:
        current_warnings = [
            item
            for item in _json_list(run_record.warnings_json)
            if isinstance(item, dict)
        ]
        quality_warnings = [
            {
                "source": "quality",
                "level": "error" if issue["severity"] == "blocking" else "warning",
                "message": issue["message"],
            }
            for issue in issues
        ]
        run_record.warnings_json = json.dumps(
            _dedupe_warnings([*current_warnings, *quality_warnings]),
            ensure_ascii=False,
        )

    latest_run = await get_project_generation_run(
        db,
        project_id=project_id,
        run_id=run.id,
    )
    latest_payload = _json_object(latest_run.stage_payload_json)
    await update_generation_run_stage(
        db,
        project_id=project_id,
        run_id=run.id,
        status="rendering_artifacts",
        case_count=len(cases),
        warning_count=len(_json_list(run_record.warnings_json)) if run_record else len(issues),
        stage_payload={
            **latest_payload,
            "quality_audit": quality_payload,
            "rendering_artifacts": {"status": "queued", "items": []},
        },
    )
    return quality_payload


def _safe_repair_fields(
    fields: dict[str, Any],
    *,
    case_id: str,
    atom_refs: list[str],
) -> dict[str, Any]:
    canonical = canonical_case_fields(fields, case_id=case_id)
    repaired = dict(fields)
    repaired.update(canonical)
    repaired["case_id"] = case_id
    repaired["module"] = str(repaired.get("module") or canonical["primary_module"])
    repaired["feature"] = str(repaired.get("feature") or canonical["secondary_module"])
    repaired["scenario"] = str(repaired.get("scenario") or canonical["checkpoint"])
    repaired["title"] = str(repaired.get("title") or canonical["checkpoint"])
    repaired["preconditions"] = canonical["preconditions"]
    repaired["steps"] = canonical["steps"]
    repaired["priority"] = canonical["priority"]
    if not canonical["remarks"] and atom_refs:
        repaired["remarks"] = f"来源 Requirement Atom：{'、'.join(atom_refs)}"
    return repaired


def _audit_cases(
    cases: list[TestCaseGenerationCaseRecord],
    *,
    atom_text: dict[str, str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    signatures: dict[tuple[str, str, str], str] = {}
    for record in cases:
        fields = _json_object(record.fields_json)
        canonical = canonical_case_fields(fields, case_id=record.case_id)
        for field in (
            "primary_module",
            "secondary_module",
            "checkpoint",
            "preconditions",
            "steps",
            "expected_results",
            "priority",
            "remarks",
        ):
            if canonical.get(field):
                continue
            issues.append(
                _issue(
                    record.case_id,
                    "blocking",
                    f"MISSING_{field.upper()}",
                    f"{record.case_id} 缺少必填字段 {field}。",
                )
            )
        if canonical["primary_module"] not in CANONICAL_PRIMARY_MODULES:
            issues.append(
                _issue(
                    record.case_id,
                    "blocking",
                    "INVALID_PRIMARY_MODULE",
                    f"{record.case_id} 的一级模块不在固定执行视角枚举中。",
                )
            )
        expected = canonical["expected_results"]
        if expected and any(term in expected for term in _GENERIC_EXPECTATIONS) and len(expected) <= 24:
            issues.append(
                _issue(
                    record.case_id,
                    "blocking",
                    "GENERIC_EXPECTATION",
                    f"{record.case_id} 的预期结果过于笼统，需要改成可观察判定。",
                )
            )
        refs = [str(item) for item in _json_list(record.atom_refs_json)]
        source_text = " ".join(atom_text.get(ref, "") for ref in refs)
        if _NUMERIC_RULE_RE.search(source_text) and not _NUMERIC_RULE_RE.search(expected):
            issues.append(
                _issue(
                    record.case_id,
                    "warning",
                    "NUMERIC_EXPECTATION_MISSING",
                    f"{record.case_id} 的来源含数值/配置规则，预期结果未保留明确数值。",
                )
            )
        signature = (
            canonical["checkpoint"],
            canonical["steps"],
            canonical["expected_results"],
        )
        if all(signature):
            previous = signatures.get(signature)
            if previous:
                issues.append(
                    _issue(
                        record.case_id,
                        "warning",
                        "DUPLICATE_CASE",
                        f"{record.case_id} 与 {previous} 的检查点、步骤和预期重复。",
                    )
                )
            else:
                signatures[signature] = record.case_id
    return issues


def _issue(case_id: str, severity: str, code: str, message: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "severity": severity,
        "code": code,
        "message": message,
    }


def _recommended_run_status(
    *,
    case_count: int,
    blocking_count: int,
    coverage_status: str,
) -> str:
    if not case_count:
        return "failed"
    if blocking_count or coverage_status != "completed":
        return "partial_completed"
    return "completed"


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
                select(TestCaseRequirementAtomRecord).where(
                    TestCaseRequirementAtomRecord.project_id == project_id,
                    TestCaseRequirementAtomRecord.run_id == run_id,
                )
            )
        ).scalars()
    )


def _dedupe_warnings(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for value in values:
        item = {
            "source": str(value.get("source") or "quality"),
            "level": str(value.get("level") or "warning"),
            "message": str(value.get("message") or ""),
        }
        key = (item["source"], item["level"], item["message"])
        if item["message"] and key not in seen:
            seen.add(key)
            result.append(item)
    return result


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
