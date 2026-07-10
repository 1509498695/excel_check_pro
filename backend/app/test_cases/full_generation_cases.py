"""Generation Run case generation from blueprint modules and official atoms."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Iterable

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
    TestCaseCoverageAuditRecord,
    TestCaseGenerationCaseRecord,
    TestCaseGenerationRunRecord,
    TestCaseRequirementAtomRecord,
)
from backend.app.test_cases.case_contract import canonical_case_fields
from backend.app.test_cases.constants import CANONICAL_CASE_FIELDS, STANDARD_CASE_FIELDS
from backend.app.test_cases.generation import TestCaseGenerationPayloadError
from backend.app.test_cases.generation_runs import (
    get_project_generation_run,
    update_generation_run_stage,
)
from backend.app.test_cases.reference_library import (
    ReferenceGenerationContext,
    resolve_generation_reference_context,
)
from backend.app.test_cases.schemas import GeneratedTestCase


NO_BLUEPRINT_MESSAGE = "Generation Run 尚无可生成用例的 Test Case Blueprint。"
NO_OFFICIAL_ATOMS_MESSAGE = "Generation Run 尚无可生成用例的 official Requirement Atom。"

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


class _ProviderCasePayload(BaseModel):
    """Provider case row with trace metadata."""

    model_config = ConfigDict(extra="ignore")

    case_id: str = ""
    primary_module: str = ""
    secondary_module: str = ""
    checkpoint: str = ""
    module: str = ""
    feature: str = ""
    scenario: str = ""
    title: str = ""
    preconditions: str = ""
    steps: str = ""
    expected_results: str = ""
    priority: str = "P2"
    case_type: str = ""
    source_requirement: str = ""
    config_source: str = ""
    planning_answer: str = ""
    initial_status: str = "未执行"
    bug_link: str = ""
    remarks: str = ""
    atom_ids: list[str] = Field(default_factory=list)
    warnings: list[Any] = Field(default_factory=list)


class _CaseGenerationPayload(BaseModel):
    """Provider response for one case-generation batch."""

    model_config = ConfigDict(extra="ignore")

    cases: list[_ProviderCasePayload] = Field(default_factory=list)
    warnings: list[Any] = Field(default_factory=list)


@dataclass(frozen=True)
class _OfficialAtom:
    atom_id: str
    atom_type: str
    text: str
    source_sheet_name: str
    source_rows: list[int]
    source_columns: list[str]
    source_excerpt: str
    visual_evidence_refs: list[str]
    merge_group_id: str


@dataclass(frozen=True)
class _CaseBatch:
    key: str
    title: str
    blueprint_nodes: list[dict[str, Any] | str]
    atom_ids: list[str]


@dataclass(frozen=True)
class _NormalizedCase:
    case: GeneratedTestCase
    atom_ids: list[str]


async def generate_test_cases_for_run(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> list[GeneratedTestCase]:
    """Generate official case rows for a Generation Run from official atoms."""
    run = await get_project_generation_run(db, project_id=project_id, run_id=run_id)
    stage_payload = _json_object(run.stage_payload_json)
    blueprint = _json_object(stage_payload.get("blueprint"))
    if not blueprint:
        await update_generation_run_stage(
            db,
            project_id=project_id,
            run_id=run.id,
            status="failed",
            error_summary=NO_BLUEPRINT_MESSAGE,
            stage_payload={
                **stage_payload,
                "case_generation": {"status": "failed", "message": NO_BLUEPRINT_MESSAGE},
            },
        )
        return []

    atom_records = await _load_atoms(db, project_id=project_id, run_id=run.id)
    official_atoms = [_official_atom_from_record(atom) for atom in atom_records if _is_official_atom(atom)]
    if not official_atoms:
        await update_generation_run_stage(
            db,
            project_id=project_id,
            run_id=run.id,
            status="failed",
            error_summary=NO_OFFICIAL_ATOMS_MESSAGE,
            stage_payload={
                **stage_payload,
                "case_generation": {"status": "failed", "message": NO_OFFICIAL_ATOMS_MESSAGE},
            },
        )
        return []

    reference_context = await _resolve_reference_context(db, project_id=project_id, run=run)
    export_columns = list(CANONICAL_CASE_FIELDS)
    batches = _build_case_batches(blueprint, official_atoms)
    await update_generation_run_stage(
        db,
        project_id=project_id,
        run_id=run.id,
        status="generating_cases",
        stage_payload={
            **stage_payload,
            "case_generation": {
                "status": "started",
                "batch_count": len(batches),
                "export_columns": export_columns,
            },
        },
    )

    credential = await load_project_credential(db, project_id)
    api_key = decrypt_credential_key(credential)
    extra_headers = parse_extra_headers(credential.extra_headers_json)
    atom_by_id = {atom.atom_id: atom for atom in official_atoms}
    forbidden_visual_refs = _forbidden_visual_refs(atom_records)
    all_cases: list[_ProviderCasePayload] = []
    warnings: list[str] = []
    provider_meta: list[dict[str, Any]] = []
    for batch in batches:
        try:
            payload, meta = await call_provider_json(
                provider_preset=credential.provider_preset,  # type: ignore[arg-type]
                base_url=credential.base_url,
                model=credential.model,
                api_key=api_key,
                system_prompt=_build_system_prompt(),
                user_prompt=_build_cases_prompt(
                    batch,
                    atom_by_id=atom_by_id,
                    blueprint=blueprint,
                    reference_context=reference_context,
                    export_columns=export_columns,
                ),
                json_schema=_CaseGenerationPayload.model_json_schema(),
                extra_headers=extra_headers,
                timeout_seconds=60.0,
            )
        except ProviderConnectionError as error:
            message = sanitize_ai_error(error.message, api_key)
            await update_generation_run_stage(
                db,
                project_id=project_id,
                run_id=run.id,
                status="failed",
                error_summary=message,
                stage_payload={
                    **stage_payload,
                    "case_generation": {
                        "status": "failed",
                        "error_summary": message,
                    },
                },
            )
            raise ProviderConnectionError(error.category, message, error.status_code) from error

        provider_meta.append(_safe_payload(meta))
        parsed = _validate_case_payload(payload)
        all_cases.extend(parsed.cases)
        warnings.extend(_normalize_warning_messages(parsed.warnings))

    normalized, unfounded, normalization_warnings = _normalize_provider_cases(
        all_cases,
        atom_by_id=atom_by_id,
        forbidden_visual_refs=forbidden_visual_refs,
    )
    warnings.extend(normalization_warnings)
    warnings = [
        _safe_text(_sanitize_forbidden_refs(message, forbidden_visual_refs))
        for message in warnings
        if _safe_text(_sanitize_forbidden_refs(message, forbidden_visual_refs))
    ]
    await _persist_cases_and_audit(
        db,
        project_id=project_id,
        run_id=run.id,
        cases=normalized,
        official_atoms=official_atoms,
        unfounded_candidates=unfounded,
        warnings=warnings,
    )
    await update_generation_run_stage(
        db,
        project_id=project_id,
        run_id=run.id,
        status="generating_cases",
        case_count=len(normalized),
        warning_count=len(_dedupe_strings(warnings)),
        stage_payload={
            **stage_payload,
            "case_generation": {
                "status": "completed",
                "batch_count": len(batches),
                "official_case_count": len(normalized),
                "unfounded_case_count": len(unfounded),
                "export_columns": export_columns,
                "provider_meta": provider_meta,
            },
            "blueprint": blueprint,
        },
    )
    run_record = await db.get(TestCaseGenerationRunRecord, run.id)
    if run_record is not None:
        run_record.warnings_json = json.dumps(
            [
                {"source": "cases", "level": "warning", "message": message}
                for message in _dedupe_strings(warnings)
            ],
            ensure_ascii=False,
        )
    await db.flush()
    return [item.case for item in normalized]


async def generate_supplement_cases_for_run(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    uncovered_atom_ids: list[str],
) -> list[GeneratedTestCase]:
    """Append one supplement pass for uncovered official atoms without replacing cases."""
    run = await get_project_generation_run(db, project_id=project_id, run_id=run_id)
    requested_atom_ids = set(_dedupe_strings(uncovered_atom_ids))
    if not requested_atom_ids:
        return []

    stage_payload = _json_object(run.stage_payload_json)
    blueprint = _json_object(stage_payload.get("blueprint"))
    atom_records = await _load_atoms(db, project_id=project_id, run_id=run.id)
    official_atoms = [
        _official_atom_from_record(atom)
        for atom in atom_records
        if _is_official_atom(atom) and atom.atom_id in requested_atom_ids
    ]
    if not official_atoms:
        return []

    reference_context = await _resolve_reference_context(db, project_id=project_id, run=run)
    export_columns = list(CANONICAL_CASE_FIELDS)
    batch = _CaseBatch(
        key="supplement-uncovered-atoms",
        title="Supplement uncovered official atoms",
        blueprint_nodes=[
            item
            for item in _list_items(blueprint.get("modules"))
            if set(_item_atom_ids(item)) & {atom.atom_id for atom in official_atoms}
        ],
        atom_ids=[atom.atom_id for atom in official_atoms],
    )

    credential = await load_project_credential(db, project_id)
    api_key = decrypt_credential_key(credential)
    extra_headers = parse_extra_headers(credential.extra_headers_json)
    atom_by_id = {atom.atom_id: atom for atom in official_atoms}
    forbidden_visual_refs = _forbidden_visual_refs(atom_records)
    payload, provider_meta = await call_provider_json(
        provider_preset=credential.provider_preset,  # type: ignore[arg-type]
        base_url=credential.base_url,
        model=credential.model,
        api_key=api_key,
        system_prompt=_build_system_prompt(),
        user_prompt=_build_cases_prompt(
            batch,
            atom_by_id=atom_by_id,
            blueprint=blueprint,
            reference_context=reference_context,
            export_columns=export_columns,
        )
        + "\n本次是 Coverage Audit 后的唯一自动 supplement pass；只补 uncovered atoms，不要生成其它需求。",
        json_schema=_CaseGenerationPayload.model_json_schema(),
        extra_headers=extra_headers,
        timeout_seconds=60.0,
    )
    parsed = _validate_case_payload(payload)
    existing_case_ids, existing_signatures = await _existing_case_context(
        db,
        project_id=project_id,
        run_id=run.id,
    )
    normalized, unfounded, warnings = _normalize_provider_cases(
        parsed.cases,
        atom_by_id=atom_by_id,
        forbidden_visual_refs=forbidden_visual_refs,
        used_case_ids=existing_case_ids,
        seen_signatures=existing_signatures,
        start_index=len(existing_case_ids) + 1,
    )
    warnings.extend(_normalize_warning_messages(parsed.warnings))
    warnings = [
        _safe_text(_sanitize_forbidden_refs(message, forbidden_visual_refs))
        for message in warnings
        if _safe_text(_sanitize_forbidden_refs(message, forbidden_visual_refs))
    ]
    await _append_cases_and_audit_candidates(
        db,
        project_id=project_id,
        run_id=run.id,
        cases=normalized,
        unfounded_candidates=unfounded,
        warnings=warnings,
    )
    run_record = await db.get(TestCaseGenerationRunRecord, run.id)
    if run_record is not None:
        supplement_payload = {
            **stage_payload,
            "supplement_generation": {
                "requested_atom_ids": [atom.atom_id for atom in official_atoms],
                "generated_case_count": len(normalized),
                "unfounded_case_count": len(unfounded),
                "provider_meta": [_safe_payload(provider_meta)],
            },
            "blueprint": blueprint,
        }
        run_record.stage_payload_json = json.dumps(
            _safe_payload(supplement_payload),
            ensure_ascii=False,
        )
    await db.flush()
    return [item.case for item in normalized]


async def _load_atoms(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> list[TestCaseRequirementAtomRecord]:
    result = await db.execute(
        select(TestCaseRequirementAtomRecord)
        .where(
            TestCaseRequirementAtomRecord.project_id == project_id,
            TestCaseRequirementAtomRecord.run_id == run_id,
        )
        .order_by(TestCaseRequirementAtomRecord.atom_id)
    )
    return list(result.scalars())


async def _resolve_reference_context(
    db: AsyncSession,
    *,
    project_id: int,
    run: TestCaseGenerationRunRecord,
) -> ReferenceGenerationContext:
    return await resolve_generation_reference_context(
        db,
        project_id=project_id,
        reference_ids=[
            int(item)
            for item in _json_list(run.reference_ids_json)
            if isinstance(item, int) or (isinstance(item, str) and str(item).isdigit())
        ],
        primary_reference_id=run.primary_reference_id,
        primary_reference_sheet_name=run.primary_reference_sheet_name,
    )


def _validate_case_payload(payload: dict[str, Any]) -> _CaseGenerationPayload:
    try:
        return _CaseGenerationPayload.model_validate(_normalize_case_payload(payload))
    except ValidationError as error:
        raise TestCaseGenerationPayloadError(
            f"AI 用例返回结构不符合 V3 Generation Run 契约：{error.errors()[0]['msg']}"
        ) from error


def _normalize_case_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["cases"] = [
        _normalize_case_dict(item)
        for item in normalized.get("cases", [])
        if isinstance(item, dict)
    ]
    normalized["warnings"] = normalized.get("warnings") or []
    return normalized


def _normalize_case_dict(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    for field_name in (*STANDARD_CASE_FIELDS, *CANONICAL_CASE_FIELDS):
        if field_name in normalized:
            normalized[field_name] = _provider_string(normalized[field_name])
    atom_ids = normalized.get("atom_ids") or normalized.get("requirement_atom_ids")
    if isinstance(atom_ids, list):
        normalized["atom_ids"] = [str(atom_id) for atom_id in atom_ids]
    elif atom_ids not in (None, ""):
        normalized["atom_ids"] = [str(atom_ids)]
    else:
        normalized["atom_ids"] = []
    return normalized


def _build_case_batches(
    blueprint: dict[str, Any],
    official_atoms: list[_OfficialAtom],
) -> list[_CaseBatch]:
    atom_by_id = {atom.atom_id: atom for atom in official_atoms}
    batches: list[_CaseBatch] = []
    used_atoms: set[str] = set()
    for index, module in enumerate(_list_items(blueprint.get("modules")), start=1):
        atom_ids = [atom_id for atom_id in _item_atom_ids(module) if atom_id in atom_by_id]
        if not atom_ids:
            continue
        used_atoms.update(atom_ids)
        batches.append(
            _CaseBatch(
                key=f"module-{index}",
                title=_item_name(module) or f"Module {index}",
                blueprint_nodes=[module],
                atom_ids=atom_ids,
            )
        )
    remaining = [atom for atom in official_atoms if atom.atom_id not in used_atoms]
    grouped: dict[str, list[str]] = {}
    for atom in remaining:
        key = atom.merge_group_id or atom.atom_type or "requirements"
        grouped.setdefault(key, []).append(atom.atom_id)
    for key, atom_ids in grouped.items():
        batches.append(
            _CaseBatch(
                key=f"atom-group-{key}",
                title=key,
                blueprint_nodes=[],
                atom_ids=atom_ids,
            )
        )
    if not batches:
        batches.append(
            _CaseBatch(
                key="all-official-atoms",
                title="Official Requirement Atoms",
                blueprint_nodes=[],
                atom_ids=[atom.atom_id for atom in official_atoms],
            )
        )
    return batches


def _build_system_prompt() -> str:
    return (
        "你是资深测试设计专家。只返回符合给定 JSON Schema 的 JSON 对象，"
        "不要输出 Markdown、解释文本或模型统计。"
    )


def _build_cases_prompt(
    batch: _CaseBatch,
    *,
    atom_by_id: dict[str, _OfficialAtom],
    blueprint: dict[str, Any],
    reference_context: ReferenceGenerationContext,
    export_columns: list[str],
) -> str:
    lines = [
        "任务：基于当前 atom group/module 生成标准测试用例行。",
        "只能从本批 official Requirement Atoms 和相关 Test Case Blueprint 节点生成用例。",
        "每条 official case 必须包含 atom_ids，且 atom_ids 必须来自本批 atoms。",
        "如果没有 Requirement Atom 支撑，不要把它作为 official case。",
        "Reference Test Case Library 只影响字段顺序、命名、层级、粒度和历史风格，不能生成新需求。",
        f"Batch：{batch.key} / {batch.title}",
        f"V3 固定字段顺序：{', '.join(export_columns)}",
        "primary_module 必须从以下执行视角枚举选择："
        "开关/入口、界面、按钮、功能、数值/配置、奖励/消耗、红点/提示、"
        "文本/多语言、兼容、特殊操作、常规测试点。",
        "Reference Test Case Library 只能影响命名和粒度，不能改变固定字段或一级模块枚举。",
        "priority 只允许 P0/P1/P2/P3；信息不足时使用 P2，并在 remarks 写明待确认。",
        "预期结果必须可观察、可执行。Requirement Atom 已提供数值、公式、范围、"
        "概率、消耗、返还、档位、键值或上限时，必须写出明确值，禁止只写“与配置一致”。",
        "核心属性默认覆盖配置映射、界面展示、实际生效；多入口需补一致性，"
        "反向规则需覆盖未达成不生效，刷新规则需写明重登/切场景/跨阶段行为。",
        "open_question 和 limitation 只保留在蓝图/审计，不生成 official case。",
        "steps、expected_results、preconditions、remarks 等字段必须是字符串；多步骤使用换行分隔。",
        "返回 JSON：{cases:[{V3固定字段..., case_id, atom_ids:[]}], warnings:[]}。",
    ]
    lines.extend(_reference_prompt_lines(reference_context))
    lines.append("相关 Blueprint 节点：")
    lines.append(json.dumps(_safe_payload(batch.blueprint_nodes), ensure_ascii=False))
    related_flows = [
        item
        for item in _list_items(blueprint.get("flows"))
        if set(_item_atom_ids(item)) & set(batch.atom_ids)
    ]
    if related_flows:
        lines.append("相关 Blueprint Flows：")
        lines.append(json.dumps(_safe_payload(related_flows), ensure_ascii=False))
    lines.append("本批 Official Requirement Atoms：")
    for atom_id in batch.atom_ids:
        atom = atom_by_id[atom_id]
        lines.append(json.dumps(_atom_prompt_payload(atom), ensure_ascii=False))
    return "\n".join(lines)


def _reference_prompt_lines(reference_context: ReferenceGenerationContext) -> list[str]:
    profile = reference_context.primary_reference_profile
    if profile is None:
        if reference_context.reference_ids:
            return [
                "参考案例：已选择附加参考案例但未指定主参考；不要自动选择最新、第一条或推荐主参考。",
                "附加参考只作为输出风格参考，不作为需求来源。",
            ]
        return [
            "参考案例：未选择参考案例增强；不要自动选择最新、第一条或推荐主参考。"
        ]
    selected_sheet_name = profile.get("selected_sheet_name") or "无 Sheet"
    reference_case_count = profile.get("reference_case_count")
    recognized_fields = [
        str(item)
        for item in profile.get("recognized_fields", [])
        if isinstance(item, str) and item
    ]
    return [
        "参考案例：已指定主参考；只允许学习输出形态，不允许补充或替代 Requirement Atom。",
        (
            "主参考摘要："
            f"ID={reference_context.primary_reference_id}；"
            f"文件={_safe_text(profile.get('original_filename') or profile.get('source_name'))}；"
            f"Sheet={_safe_text(selected_sheet_name)}；"
            f"参考用例数量：{reference_case_count if reference_case_count is not None else '未知'}；"
            f"可识别字段：{', '.join(recognized_fields) if recognized_fields else '无'}"
        ),
    ]


def _normalize_provider_cases(
    cases: list[_ProviderCasePayload],
    *,
    atom_by_id: dict[str, _OfficialAtom],
    forbidden_visual_refs: set[str],
    used_case_ids: set[str] | None = None,
    seen_signatures: set[tuple[str, str, str]] | None = None,
    start_index: int = 1,
) -> tuple[list[_NormalizedCase], list[dict[str, Any]], list[str]]:
    normalized_cases: list[_NormalizedCase] = []
    unfounded: list[dict[str, Any]] = []
    warnings: list[str] = []
    used_case_ids = set(used_case_ids or set())
    seen_signatures = set(seen_signatures or set())
    for index, payload in enumerate(cases, start=start_index):
        atom_ids = _valid_case_atom_ids(payload.atom_ids, atom_by_id)
        if not atom_ids:
            atom_ids = _match_case_atoms(payload, atom_by_id)
            if atom_ids:
                warnings.append(f"{payload.case_id or payload.title or index} 缺少 atom_ids，已根据 source_requirement 回填。")
        case = _case_from_payload(payload, forbidden_visual_refs=forbidden_visual_refs)
        if not atom_ids:
            unfounded.append(
                _safe_payload(
                    {
                        "case_id": case.case_id or f"UNFOUNDED-{index:03d}",
                        "title": case.title,
                        "module": case.module,
                        "source_requirement": case.source_requirement,
                        "reason": "缺少有效 Requirement Atom 支撑，未进入 official cases。",
                        "fields": case.model_dump(mode="json"),
                    }
                )
            )
            continue
        signature = (
            case.title.strip(),
            case.steps.strip(),
            case.expected_results.strip(),
        )
        if signature in seen_signatures:
            warnings.append(f"{case.title or case.case_id or index} 与已有用例重复，已剔除。")
            continue
        seen_signatures.add(signature)
        case_id = _normalize_case_id(case.case_id, index=index, used_case_ids=used_case_ids)
        normalized_cases.append(
            _NormalizedCase(
                case=case.model_copy(update={"case_id": case_id}),
                atom_ids=atom_ids,
            )
        )
    return normalized_cases, unfounded, _dedupe_strings(warnings)


def _case_from_payload(
    payload: _ProviderCasePayload,
    *,
    forbidden_visual_refs: set[str],
) -> GeneratedTestCase:
    legacy_data = {
        field: _sanitize_forbidden_refs(getattr(payload, field), forbidden_visual_refs)
        for field in STANDARD_CASE_FIELDS
    }
    new_data = {
        field: _sanitize_forbidden_refs(getattr(payload, field), forbidden_visual_refs)
        for field in CANONICAL_CASE_FIELDS
    }
    data = {**legacy_data, **new_data}
    data["priority"] = data["priority"] or "P2"
    data["initial_status"] = data["initial_status"] or "未执行"
    canonical = canonical_case_fields(data, case_id=str(data.get("case_id") or ""))
    data.update(canonical)
    data["module"] = data["module"] or canonical["primary_module"]
    data["feature"] = data["feature"] or canonical["secondary_module"]
    data["scenario"] = data["scenario"] or canonical["checkpoint"]
    data["title"] = data["title"] or canonical["checkpoint"]
    return GeneratedTestCase.model_validate(data)


def _normalize_case_id(
    case_id: str,
    *,
    index: int,
    used_case_ids: set[str],
) -> str:
    candidate = case_id.strip() or f"TC-{index:04d}"
    if candidate in used_case_ids:
        candidate = f"TC-{index:04d}"
        suffix = index
        while candidate in used_case_ids:
            suffix += 1
            candidate = f"TC-{suffix:04d}"
    used_case_ids.add(candidate)
    return candidate


def _valid_case_atom_ids(
    atom_ids: list[str],
    atom_by_id: dict[str, _OfficialAtom],
) -> list[str]:
    return _dedupe_strings([atom_id for atom_id in atom_ids if atom_id in atom_by_id])


def _match_case_atoms(
    payload: _ProviderCasePayload,
    atom_by_id: dict[str, _OfficialAtom],
) -> list[str]:
    haystack = " ".join(
        [
            payload.source_requirement,
            payload.title,
            payload.steps,
            payload.expected_results,
        ]
    )
    matched: list[str] = []
    for atom_id, atom in atom_by_id.items():
        if _text_matches_atom(haystack, atom):
            matched.append(atom_id)
    return _dedupe_strings(matched)


def _text_matches_atom(text: str, atom: _OfficialAtom) -> bool:
    normalized_text = _compact_text(text)
    for candidate in (atom.text, atom.source_excerpt):
        normalized_candidate = _compact_text(candidate)
        if len(normalized_candidate) < 4:
            continue
        if normalized_candidate in normalized_text or normalized_text in normalized_candidate:
            return True
        token_hits = [
            token
            for token in _tokens(normalized_candidate)
            if len(token) >= 2 and token in normalized_text
        ]
        if len(token_hits) >= 2:
            return True
    return False


async def _persist_cases_and_audit(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    cases: list[_NormalizedCase],
    official_atoms: list[_OfficialAtom],
    unfounded_candidates: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    await db.execute(
        delete(TestCaseGenerationCaseRecord).where(
            TestCaseGenerationCaseRecord.project_id == project_id,
            TestCaseGenerationCaseRecord.run_id == run_id,
        )
    )
    for item in cases:
        db.add(
            TestCaseGenerationCaseRecord(
                run_id=run_id,
                project_id=project_id,
                case_id=item.case.case_id,
                fields_json=json.dumps(
                    _safe_payload(item.case.model_dump(mode="json")),
                    ensure_ascii=False,
                ),
                atom_refs_json=json.dumps(_safe_payload(item.atom_ids), ensure_ascii=False),
                status="official",
            )
        )
    covered = sorted({atom_id for item in cases for atom_id in item.atom_ids})
    all_atom_ids = [atom.atom_id for atom in official_atoms]
    uncovered = [atom_id for atom_id in all_atom_ids if atom_id not in set(covered)]
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
    audit.status = "pending"
    audit.total_atoms = len(all_atom_ids)
    audit.covered_atoms = len(covered)
    audit.uncovered_atoms = len(uncovered)
    audit.unfounded_case_count = len(unfounded_candidates)
    audit.uncovered_atom_ids_json = json.dumps(uncovered, ensure_ascii=False)
    audit.unfounded_candidates_json = json.dumps(
        _safe_payload(unfounded_candidates),
        ensure_ascii=False,
    )
    audit.warnings_json = json.dumps(
        [
            {"source": "cases", "level": "warning", "message": message}
            for message in _dedupe_strings(warnings)
        ],
        ensure_ascii=False,
    )


async def _append_cases_and_audit_candidates(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    cases: list[_NormalizedCase],
    unfounded_candidates: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    for item in cases:
        db.add(
            TestCaseGenerationCaseRecord(
                run_id=run_id,
                project_id=project_id,
                case_id=item.case.case_id,
                fields_json=json.dumps(
                    _safe_payload(item.case.model_dump(mode="json")),
                    ensure_ascii=False,
                ),
                atom_refs_json=json.dumps(_safe_payload(item.atom_ids), ensure_ascii=False),
                status="official",
            )
        )
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
    existing_unfounded = _json_list(audit.unfounded_candidates_json)
    audit.unfounded_candidates_json = json.dumps(
        _safe_payload([*existing_unfounded, *unfounded_candidates]),
        ensure_ascii=False,
    )
    audit.unfounded_case_count = len(existing_unfounded) + len(unfounded_candidates)
    existing_warnings = _json_list(audit.warnings_json)
    warning_items = [
        {"source": "supplement", "level": "warning", "message": message}
        for message in _dedupe_strings(warnings)
    ]
    audit.warnings_json = json.dumps(
        _safe_payload([*existing_warnings, *warning_items]),
        ensure_ascii=False,
    )


async def _existing_case_context(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
) -> tuple[set[str], set[tuple[str, str, str]]]:
    result = await db.execute(
        select(TestCaseGenerationCaseRecord).where(
            TestCaseGenerationCaseRecord.project_id == project_id,
            TestCaseGenerationCaseRecord.run_id == run_id,
        )
    )
    used_ids: set[str] = set()
    signatures: set[tuple[str, str, str]] = set()
    for record in result.scalars():
        used_ids.add(record.case_id)
        fields = _json_object(record.fields_json)
        signatures.add(
            (
                _safe_text(fields.get("title")).strip(),
                _safe_text(fields.get("steps")).strip(),
                _safe_text(fields.get("expected_results")).strip(),
            )
        )
    return used_ids, signatures


def _is_official_atom(atom: TestCaseRequirementAtomRecord) -> bool:
    return (
        atom.coverage_status != "unfounded_candidate"
        and atom.atom_type not in {"open_question", "limitation"}
        and atom.atom_id.startswith("ATOM-")
    )


def _official_atom_from_record(atom: TestCaseRequirementAtomRecord) -> _OfficialAtom:
    return _OfficialAtom(
        atom_id=atom.atom_id,
        atom_type=atom.atom_type,
        text=_safe_text(atom.requirement_text),
        source_sheet_name=_safe_text(atom.source_sheet_name),
        source_rows=_source_rows(atom),
        source_columns=[str(item) for item in _json_list(atom.source_columns_json)],
        source_excerpt=_safe_text(atom.cell_excerpt),
        visual_evidence_refs=[str(item) for item in _json_list(atom.visual_evidence_refs_json)],
        merge_group_id=_safe_text(atom.merge_group_id),
    )


def _source_rows(atom: TestCaseRequirementAtomRecord) -> list[int]:
    if atom.source_row_start is None:
        return []
    if atom.source_row_end is None or atom.source_row_end < atom.source_row_start:
        return [atom.source_row_start]
    return list(range(atom.source_row_start, atom.source_row_end + 1))


def _atom_prompt_payload(atom: _OfficialAtom) -> dict[str, Any]:
    return {
        "atom_id": atom.atom_id,
        "atom_type": atom.atom_type,
        "text": atom.text,
        "source_sheet": atom.source_sheet_name,
        "source_rows": atom.source_rows,
        "source_columns": atom.source_columns,
        "source_excerpt": atom.source_excerpt,
        "visual_evidence_refs": atom.visual_evidence_refs,
        "merge_group_id": atom.merge_group_id,
    }


def _forbidden_visual_refs(atoms: list[TestCaseRequirementAtomRecord]) -> set[str]:
    refs: set[str] = set()
    for atom in atoms:
        if _is_official_atom(atom):
            continue
        refs.update(str(item) for item in _json_list(atom.visual_evidence_refs_json) if str(item))
    return refs


def _list_items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _item_atom_ids(item: Any) -> list[str]:
    if not isinstance(item, dict):
        return []
    candidates: list[str] = []
    for key in ("atom_ids", "atom_id", "requirement_atom_ids"):
        raw = item.get(key)
        if isinstance(raw, list):
            candidates.extend(str(value) for value in raw)
        elif raw not in (None, ""):
            candidates.append(str(raw))
    return _dedupe_strings(candidates)


def _item_name(item: Any) -> str:
    if isinstance(item, dict):
        return _safe_text(
            item.get("name")
            or item.get("title")
            or item.get("key")
            or item.get("description")
        )
    return _safe_text(item)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


def _normalize_warning_messages(values: list[Any]) -> list[str]:
    messages: list[str] = []
    for value in values:
        if isinstance(value, dict):
            message = _safe_text(value.get("message") or value.get("description") or value.get("text"))
        else:
            message = _safe_text(value)
        if message:
            messages.append(message)
    return _dedupe_strings(messages)


def _provider_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(
            text for text in (_provider_string(item).strip() for item in value) if text
        )
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _sanitize_forbidden_refs(value: Any, forbidden_visual_refs: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_forbidden_refs(item, forbidden_visual_refs)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_forbidden_refs(item, forbidden_visual_refs) for item in value]
    if isinstance(value, str):
        text = _safe_text(value)
        for ref in sorted(forbidden_visual_refs, key=len, reverse=True):
            if ref:
                text = text.replace(ref, "[未采纳视觉证据]")
        return text
    return value


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


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[|,，。；;、\s]+", value) if token]


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _safe_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
