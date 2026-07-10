"""Generation Run blueprint generation from merged official Requirement Atoms."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.credentials import (
    decrypt_credential_key,
    load_project_credential,
    parse_extra_headers,
    sanitize_ai_error,
)
from backend.app.ai.providers import ProviderConnectionError, call_provider_json
from backend.app.models import (
    TestCaseGenerationRunRecord,
    TestCaseRequirementAtomRecord,
)
from backend.app.test_cases.generation import (
    TestCaseGenerationPayloadError,
    validate_test_case_blueprint_payload,
)
from backend.app.test_cases.generation_runs import (
    get_project_generation_run,
    update_generation_run_stage,
)
from backend.app.test_cases.qa_case_method import (
    BLUEPRINT_DIMENSIONS,
    COMPLETENESS_MATRIX,
    SCENARIO_LIBRARY,
    SELF_CHECK_RULES,
    WARNING_TEMPLATES,
    build_method_context,
    get_internal_knowledge_context,
)
from backend.app.test_cases.schemas import GenerationWarning, TestCaseBlueprint


NO_BLUEPRINT_ATOMS_MESSAGE = "Generation Run 没有可生成需求的 official Requirement Atom。"

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
class _OfficialAtom:
    id: int
    atom_id: str
    atom_type: str
    text: str
    source_sheet_name: str
    source_row_start: int | None
    source_row_end: int | None
    source_columns: list[str]
    source_excerpt: str
    visual_evidence_refs: list[str]
    confidence: float | None
    warnings: list[str]
    merge_group_id: str


async def generate_test_case_blueprint_for_run(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    source_summary: str = "",
    context_warnings: Sequence[Any] = (),
) -> TestCaseBlueprint:
    """Generate and persist a TestCaseBlueprint from official Requirement Atoms only."""
    run = await get_project_generation_run(db, project_id=project_id, run_id=run_id)
    await update_generation_run_stage(
        db,
        project_id=project_id,
        run_id=run.id,
        status="blueprinting",
        stage_payload={
            "blueprint_generation": {
                "status": "started",
                "source": "official_requirement_atoms",
            }
        },
    )

    atom_records = await _load_atoms(db, project_id=project_id, run_id=run.id)
    official_atoms = [_official_atom_from_record(atom) for atom in atom_records if _is_official_atom(atom)]
    if not official_atoms:
        await update_generation_run_stage(
            db,
            project_id=project_id,
            run_id=run.id,
            status="failed",
            error_summary=NO_BLUEPRINT_ATOMS_MESSAGE,
            stage_payload={
                "blueprint_generation": {
                    "status": "failed",
                    "official_atom_count": 0,
                    "message": NO_BLUEPRINT_ATOMS_MESSAGE,
                }
            },
        )
        return TestCaseBlueprint(
            warnings=[
                GenerationWarning(
                    source="blueprint",
                    level="error",
                    message=NO_BLUEPRINT_ATOMS_MESSAGE,
                )
            ]
        )

    credential = await load_project_credential(db, project_id)
    api_key = decrypt_credential_key(credential)
    extra_headers = parse_extra_headers(credential.extra_headers_json)
    prompt = _build_blueprint_prompt(
        official_atoms,
        source_summary=source_summary,
        context_warnings=context_warnings,
        run=run,
    )
    try:
        payload, provider_meta = await call_provider_json(
            provider_preset=credential.provider_preset,  # type: ignore[arg-type]
            base_url=credential.base_url,
            model=credential.model,
            api_key=api_key,
            system_prompt=_build_system_prompt(),
            user_prompt=prompt,
            json_schema=TestCaseBlueprint.model_json_schema(),
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
                "blueprint_generation": {
                    "status": "failed",
                    "official_atom_count": len(official_atoms),
                    "error_summary": message,
                }
            },
        )
        raise ProviderConnectionError(error.category, message, error.status_code) from error

    try:
        raw_blueprint = validate_test_case_blueprint_payload(payload)
    except TestCaseGenerationPayloadError as error:
        await update_generation_run_stage(
            db,
            project_id=project_id,
            run_id=run.id,
            status="failed",
            error_summary=str(error),
            stage_payload={
                "blueprint_generation": {
                    "status": "failed",
                    "official_atom_count": len(official_atoms),
                    "error_summary": str(error),
                }
            },
        )
        raise

    forbidden_visual_refs = _forbidden_visual_refs(atom_records)
    blueprint, validation_warnings = _normalize_blueprint_against_atoms(
        raw_blueprint,
        official_atoms=official_atoms,
        forbidden_visual_refs=forbidden_visual_refs,
    )
    warnings = _merge_warnings(
        _run_warnings(run),
        _context_warning_messages(context_warnings),
        [warning.message for warning in blueprint.warnings],
        validation_warnings,
    )
    blueprint.warnings = [
        GenerationWarning(source="blueprint", level="warning", message=message)
        for message in warnings
        if message
    ]

    await update_generation_run_stage(
        db,
        project_id=project_id,
        run_id=run.id,
        status="blueprinting",
        warning_count=len(warnings),
        stage_payload={
            "blueprint_generation": {
                "status": "completed",
                "official_atom_count": len(official_atoms),
                "warning_count": len(warnings),
                "provider_meta": _safe_payload(provider_meta),
            },
            "blueprint": _safe_payload(blueprint.model_dump(mode="json")),
        },
    )
    run_record = await db.get(TestCaseGenerationRunRecord, run.id)
    if run_record is not None:
        run_record.warnings_json = json.dumps(
            [
                {"source": "blueprint", "level": "warning", "message": message}
                for message in warnings
                if message
            ],
            ensure_ascii=False,
        )
    await db.flush()
    return blueprint


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


def _is_official_atom(atom: TestCaseRequirementAtomRecord) -> bool:
    return atom.coverage_status != "unfounded_candidate" and atom.atom_id.startswith("ATOM-")


def _official_atom_from_record(atom: TestCaseRequirementAtomRecord) -> _OfficialAtom:
    return _OfficialAtom(
        id=atom.id,
        atom_id=atom.atom_id,
        atom_type=atom.atom_type,
        text=_safe_text(atom.requirement_text),
        source_sheet_name=_safe_text(atom.source_sheet_name),
        source_row_start=atom.source_row_start,
        source_row_end=atom.source_row_end,
        source_columns=[str(item) for item in _json_list(atom.source_columns_json)],
        source_excerpt=_safe_text(atom.cell_excerpt),
        visual_evidence_refs=[str(item) for item in _json_list(atom.visual_evidence_refs_json)],
        confidence=atom.confidence,
        warnings=[_safe_text(str(item)) for item in _json_list(atom.warnings_json)],
        merge_group_id=_safe_text(atom.merge_group_id),
    )


def _build_system_prompt() -> str:
    return (
        "你是资深测试设计专家。只返回符合给定 JSON Schema 的 JSON 对象，"
        "不要输出 Markdown、解释文本或模型统计。"
    )


def _build_blueprint_prompt(
    official_atoms: list[_OfficialAtom],
    *,
    source_summary: str,
    context_warnings: Sequence[Any],
    run: TestCaseGenerationRunRecord,
) -> str:
    method_context = build_method_context()
    knowledge_context = get_internal_knowledge_context()
    lines = [
        "任务：基于 merged official Requirement Atoms 生成只读 Test Case Blueprint。",
        "只能从 official atoms、source summary 和已提供 warnings 推导蓝图。",
        "不得读取或补充 Planning Sheet Snapshot、raw sheet 全文、参考案例、常识或旧知识。",
        "Reference Test Case Library 不参与 blueprint facts；不要使用 reference_id、历史用例或参考案例补需求。",
        f"Sheet：{run.planning_sheet_name}",
        f"方法：{method_context.method_name} {method_context.method_version}",
        f"项目级 QA 知识库：{knowledge_context['note']}",
        f"蓝图维度：{', '.join(BLUEPRINT_DIMENSIONS)}",
        f"完整性矩阵：{', '.join(COMPLETENESS_MATRIX)}",
        f"具体场景库：{', '.join(SCENARIO_LIBRARY)}",
        f"自检规则：{', '.join(SELF_CHECK_RULES)}",
        f"warning 模板：{', '.join(WARNING_TEMPLATES)}",
        "输出必须包含 modules、flows、requirement_traces、coverage_dimensions、risks、"
        "unmapped_requirements、unsupported_or_unfounded_test_points、open_questions、warnings。",
        "每个 modules/flows/coverage_dimensions/risks 条目必须能追踪到 atom_ids；无依据内容写入 unsupported_or_unfounded_test_points。",
        "requirement_traces 必须包含 atom_id 或 atom_ids，并把 atom id 写入 source_fragment。",
    ]
    if _safe_text(source_summary):
        lines.extend(["Source summary：", _safe_text(source_summary)])
    warning_messages = _context_warning_messages(context_warnings)
    if warning_messages:
        lines.append("已有 warnings：")
        lines.extend(f"- {_safe_text(message)}" for message in warning_messages)
    lines.append("Official Requirement Atoms：")
    for atom in official_atoms:
        lines.append(json.dumps(_atom_prompt_payload(atom), ensure_ascii=False))
    return "\n".join(lines)


def _atom_prompt_payload(atom: _OfficialAtom) -> dict[str, Any]:
    return {
        "atom_id": atom.atom_id,
        "atom_type": atom.atom_type,
        "text": atom.text,
        "source_sheet": atom.source_sheet_name,
        "source_rows": _source_rows(atom),
        "source_columns": atom.source_columns,
        "source_excerpt": atom.source_excerpt,
        "visual_evidence_refs": atom.visual_evidence_refs,
        "confidence": atom.confidence,
        "warnings": atom.warnings,
        "merge_group_id": atom.merge_group_id,
    }


def _normalize_blueprint_against_atoms(
    blueprint: TestCaseBlueprint,
    *,
    official_atoms: list[_OfficialAtom],
    forbidden_visual_refs: set[str],
) -> tuple[TestCaseBlueprint, list[str]]:
    atom_by_id = {atom.atom_id: atom for atom in official_atoms}
    trace_records, trace_warnings = _normalize_requirement_traces(
        blueprint.requirement_traces,
        atom_by_id=atom_by_id,
        forbidden_visual_refs=forbidden_visual_refs,
    )
    node_atom_ids: dict[str, list[str]] = {}
    for trace in trace_records:
        node = _safe_text(trace.get("blueprint_node"))
        if node:
            node_atom_ids[node] = _merge_lists(
                node_atom_ids.get(node, []),
                [str(item) for item in trace.get("atom_ids", [])],
            )

    warnings = list(trace_warnings)
    unsupported = [
        _sanitize_forbidden_refs(item, forbidden_visual_refs)
        for item in blueprint.unsupported_or_unfounded_test_points
    ]
    modules, moved = _filter_traceable_items(
        blueprint.modules,
        field_name="modules",
        atom_by_id=atom_by_id,
        node_atom_ids=node_atom_ids,
        forbidden_visual_refs=forbidden_visual_refs,
    )
    unsupported.extend(moved)
    flows, moved = _filter_traceable_items(
        blueprint.flows,
        field_name="flows",
        atom_by_id=atom_by_id,
        node_atom_ids=node_atom_ids,
        forbidden_visual_refs=forbidden_visual_refs,
    )
    unsupported.extend(moved)
    coverage_dimensions, moved = _filter_traceable_items(
        blueprint.coverage_dimensions,
        field_name="coverage_dimensions",
        atom_by_id=atom_by_id,
        node_atom_ids=node_atom_ids,
        forbidden_visual_refs=forbidden_visual_refs,
    )
    unsupported.extend(moved)
    risks, moved = _filter_traceable_items(
        blueprint.risks,
        field_name="risks",
        atom_by_id=atom_by_id,
        node_atom_ids=node_atom_ids,
        forbidden_visual_refs=forbidden_visual_refs,
    )
    unsupported.extend(moved)

    for item in moved:
        name = _safe_text(_sanitize_forbidden_refs(_item_name(item), forbidden_visual_refs))
        if name:
            warnings.append(f"{name} 缺少有效 Requirement Atom trace，已移入 unsupported/unfounded。")

    for moved_item in unsupported:
        if isinstance(moved_item, dict) and moved_item.get("reason"):
            name = _safe_text(_sanitize_forbidden_refs(_item_name(moved_item), forbidden_visual_refs))
            if name:
                warnings.append(f"{name} 缺少有效 Requirement Atom trace，已移入 unsupported/unfounded。")

    normalized = blueprint.model_copy(
        update={
            "modules": modules,
            "flows": flows,
            "requirement_traces": trace_records,
            "coverage_dimensions": coverage_dimensions,
            "risks": risks,
            "unmapped_requirements": _sanitize_forbidden_refs(
                blueprint.unmapped_requirements,
                forbidden_visual_refs,
            ),
            "unsupported_or_unfounded_test_points": unsupported,
            "open_questions": _sanitize_forbidden_refs(
                blueprint.open_questions,
                forbidden_visual_refs,
            ),
            "warnings": [
                GenerationWarning(
                    source="blueprint",
                    level="warning",
                    message=_safe_text(_sanitize_forbidden_refs(warning.message, forbidden_visual_refs)),
                )
                for warning in blueprint.warnings
                if _safe_text(warning.message)
            ],
        }
    )
    return normalized, _dedupe_strings(warnings)


def _normalize_requirement_traces(
    traces: list[dict[str, Any]],
    *,
    atom_by_id: dict[str, _OfficialAtom],
    forbidden_visual_refs: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    normalized: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_keys: set[tuple[str, str]] = set()
    for trace in traces:
        if not isinstance(trace, dict):
            continue
        atom_ids = _trace_atom_ids(trace, atom_by_id=atom_by_id)
        if not atom_ids:
            node = _safe_text(trace.get("blueprint_node") or trace.get("node") or trace.get("module"))
            if node:
                warnings.append(f"{node} 缺少有效 Requirement Atom trace。")
            continue
        node = _safe_text(
            trace.get("blueprint_node")
            or trace.get("node")
            or trace.get("module")
            or trace.get("name")
        )
        for atom_id in atom_ids:
            key = (node, atom_id)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            atom = atom_by_id[atom_id]
            source_fragment = f"{atom.atom_id}: {atom.text}"
            normalized.append(
                _sanitize_forbidden_refs(
                    {
                        **trace,
                        "atom_id": atom.atom_id,
                        "atom_ids": [atom.atom_id],
                        "source_row_index": trace.get("source_row_index")
                        if trace.get("source_row_index") is not None
                        else atom.source_row_start,
                        "source_fragment": source_fragment,
                        "source_sheet": atom.source_sheet_name,
                        "source_rows": _source_rows(atom),
                        "visual_evidence_refs": atom.visual_evidence_refs,
                        "blueprint_node": node,
                    },
                    forbidden_visual_refs,
                )
            )
    return normalized, _dedupe_strings(warnings)


def _filter_traceable_items(
    items: list[dict[str, Any] | str],
    *,
    field_name: str,
    atom_by_id: dict[str, _OfficialAtom],
    node_atom_ids: dict[str, list[str]],
    forbidden_visual_refs: set[str],
) -> tuple[list[dict[str, Any] | str], list[dict[str, Any]]]:
    kept: list[dict[str, Any] | str] = []
    unsupported: list[dict[str, Any]] = []
    for item in items:
        atom_ids = _item_atom_ids(item, atom_by_id=atom_by_id)
        name = _item_name(item)
        if not atom_ids and name:
            atom_ids = [atom_id for atom_id in node_atom_ids.get(name, []) if atom_id in atom_by_id]
        if atom_ids:
            sanitized = _sanitize_forbidden_refs(item, forbidden_visual_refs)
            if isinstance(sanitized, dict):
                sanitized["atom_ids"] = atom_ids
            kept.append(sanitized)
            continue
        unsupported.append(
            {
                "field": field_name,
                "item": _sanitize_forbidden_refs(item, forbidden_visual_refs),
                "name": _sanitize_forbidden_refs(name, forbidden_visual_refs),
                "reason": "缺少有效 Requirement Atom trace，已标记为 unsupported/unfounded。",
            }
        )
    return kept, unsupported


def _trace_atom_ids(trace: dict[str, Any], *, atom_by_id: dict[str, _OfficialAtom]) -> list[str]:
    candidates: list[str] = []
    raw_atom_ids = trace.get("atom_ids") or trace.get("requirement_atom_ids")
    if isinstance(raw_atom_ids, list):
        candidates.extend(str(item) for item in raw_atom_ids)
    elif raw_atom_ids not in (None, ""):
        candidates.append(str(raw_atom_ids))
    if trace.get("atom_id") not in (None, ""):
        candidates.append(str(trace.get("atom_id")))

    fragment = _safe_text(
        trace.get("source_fragment")
        or trace.get("source")
        or trace.get("requirement")
        or trace.get("requirement_id")
    )
    for atom_id, atom in atom_by_id.items():
        if atom_id in fragment or (atom.text and atom.text in fragment):
            candidates.append(atom_id)
    return _dedupe_strings([atom_id for atom_id in candidates if atom_id in atom_by_id])


def _item_atom_ids(item: dict[str, Any] | str, *, atom_by_id: dict[str, _OfficialAtom]) -> list[str]:
    if not isinstance(item, dict):
        return []
    candidates: list[str] = []
    for key in ("atom_ids", "atom_id", "requirement_atom_ids"):
        raw = item.get(key)
        if isinstance(raw, list):
            candidates.extend(str(value) for value in raw)
        elif raw not in (None, ""):
            candidates.append(str(raw))
    return _dedupe_strings([atom_id for atom_id in candidates if atom_id in atom_by_id])


def _item_name(item: Any) -> str:
    if isinstance(item, dict):
        return _safe_text(
            item.get("name")
            or item.get("title")
            or item.get("key")
            or item.get("description")
            or item.get("item")
        )
    return _safe_text(item)


def _forbidden_visual_refs(atoms: list[TestCaseRequirementAtomRecord]) -> set[str]:
    refs: set[str] = set()
    for atom in atoms:
        if _is_official_atom(atom):
            continue
        refs.update(str(item) for item in _json_list(atom.visual_evidence_refs_json) if str(item))
    return refs


def _sanitize_forbidden_refs(value: Any, forbidden_visual_refs: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_forbidden_refs(item, forbidden_visual_refs)
            for key, item in value.items()
        }
    if isinstance(value, list):
        cleaned: list[Any] = []
        for item in value:
            sanitized = _sanitize_forbidden_refs(item, forbidden_visual_refs)
            if sanitized in ("", None, [], {}):
                continue
            cleaned.append(sanitized)
        return cleaned
    if isinstance(value, tuple):
        return [_sanitize_forbidden_refs(item, forbidden_visual_refs) for item in value]
    if isinstance(value, str):
        text = _safe_text(value)
        for ref in sorted(forbidden_visual_refs, key=len, reverse=True):
            if ref:
                text = text.replace(ref, "[未采纳视觉证据]")
        return text
    return value


def _run_warnings(run: TestCaseGenerationRunRecord) -> list[str]:
    messages: list[str] = []
    for item in _json_list(run.warnings_json):
        if isinstance(item, dict):
            message = _safe_text(item.get("message"))
        else:
            message = _safe_text(item)
        if message:
            messages.append(message)
    return messages


def _context_warning_messages(context_warnings: Sequence[Any]) -> list[str]:
    messages: list[str] = []
    for warning in context_warnings:
        if isinstance(warning, GenerationWarning):
            message = warning.message
        elif isinstance(warning, dict):
            message = str(warning.get("message") or "")
        else:
            message = str(warning)
        message = _safe_text(message)
        if message:
            messages.append(message)
    return messages


def _merge_warnings(*groups: Iterable[str]) -> list[str]:
    warnings: list[str] = []
    for group in groups:
        warnings.extend(_safe_text(message) for message in group if _safe_text(message))
    return _dedupe_strings(warnings)


def _source_rows(atom: _OfficialAtom) -> list[int]:
    if atom.source_row_start is None:
        return []
    if atom.source_row_end is None or atom.source_row_end < atom.source_row_start:
        return [atom.source_row_start]
    return list(range(atom.source_row_start, atom.source_row_end + 1))


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


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


def _merge_lists(left: list[str], right: list[str]) -> list[str]:
    return _dedupe_strings([*left, *right])


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
