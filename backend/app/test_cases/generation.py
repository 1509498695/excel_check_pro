"""用例生成 V1 无参考 AI 编排。"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.credentials import (
    decrypt_credential_key,
    load_project_credential,
    parse_extra_headers,
    sanitize_ai_error,
)
from backend.app.ai.providers import ProviderConnectionError, call_provider_json
from backend.app.test_cases.constants import STANDARD_CASE_FIELDS
from backend.app.test_cases.exporter import resolve_export_fields_from_reference_profile
from backend.app.test_cases.qa_case_method import (
    BLUEPRINT_DIMENSIONS,
    COMPLETENESS_MATRIX,
    SCENARIO_LIBRARY,
    SELF_CHECK_RULES,
    WARNING_TEMPLATES,
    build_method_context,
    get_internal_knowledge_context,
)
from backend.app.test_cases.reference_library import (
    ReferenceGenerationContext,
    resolve_generation_reference_context,
)
from backend.app.test_cases.schemas import (
    GeneratedCaseStats,
    GeneratedTestCase,
    GenerationWarning,
    PlanningSnapshotResponse,
    RequirementTrace,
    TestCaseBlueprint,
    TestCaseGenerationRequest,
    TestCaseGenerationResponse,
)


class TestCaseGenerationPayloadError(ValueError):
    """AI 返回结构无法通过用例生成契约校验。"""


class _CaseGenerationStagePayload(BaseModel):
    """用例生成阶段 AI 返回结构；模型附带 stats 时忽略。"""

    model_config = ConfigDict(extra="ignore")

    cases: list[GeneratedTestCase] = Field(default_factory=list)
    warnings: list[GenerationWarning] = Field(default_factory=list)
    requirement_trace: list[RequirementTrace] = Field(default_factory=list)


async def generate_test_case_response(
    payload: TestCaseGenerationRequest,
    *,
    db: AsyncSession,
    project_id: int,
) -> TestCaseGenerationResponse:
    """按 QA Case Method 执行蓝图先行、再生成用例的无参考主链路。"""
    method_context = build_method_context()
    reference_context = await resolve_generation_reference_context(
        db,
        project_id=project_id,
        reference_ids=payload.reference_ids,
        primary_reference_id=payload.primary_reference_id,
        primary_reference_sheet_name=payload.primary_reference_sheet_name,
    )
    credential = await load_project_credential(db, project_id)
    api_key = decrypt_credential_key(credential)
    extra_headers = parse_extra_headers(credential.extra_headers_json)

    blueprint_payload = await _call_generation_provider(
        credential=credential,
        api_key=api_key,
        system_prompt=_build_system_prompt(),
        user_prompt=_build_blueprint_prompt(payload, reference_context),
        json_schema=TestCaseBlueprint.model_json_schema(),
        extra_headers=extra_headers,
    )
    blueprint = _validate_blueprint_payload(blueprint_payload)

    case_payload = await _call_generation_provider(
        credential=credential,
        api_key=api_key,
        system_prompt=_build_system_prompt(),
        user_prompt=_build_cases_prompt(payload, blueprint, reference_context),
        json_schema=_CaseGenerationStagePayload.model_json_schema(),
        extra_headers=extra_headers,
    )
    case_stage = _validate_case_payload(case_payload)
    cases = _normalize_cases(case_stage.cases)
    warnings = [
        *payload.planning_snapshot.warnings,
        *blueprint.warnings,
        *case_stage.warnings,
    ]
    requirement_trace = _normalize_requirement_trace(
        case_stage.requirement_trace,
        cases=cases,
        snapshot=payload.planning_snapshot,
    )

    return TestCaseGenerationResponse(
        blueprint=blueprint,
        cases=cases,
        warnings=warnings,
        stats=_compute_stats(cases, warnings),
        export_columns=resolve_export_fields_from_reference_profile(
            reference_context.export_profile
        ),
        requirement_trace=requirement_trace,
        method_context=method_context,
        primary_reference_profile=reference_context.primary_reference_profile,
        reference_context=reference_context.model_dump(),
    )


async def _call_generation_provider(
    *,
    credential,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    json_schema: dict[str, Any],
    extra_headers: dict[str, str],
) -> dict[str, Any]:
    try:
        result, _meta = await call_provider_json(
            provider_preset=credential.provider_preset,  # type: ignore[arg-type]
            base_url=credential.base_url,
            model=credential.model,
            api_key=api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=json_schema,
            extra_headers=extra_headers,
            timeout_seconds=60.0,
        )
    except ProviderConnectionError as error:
        raise ProviderConnectionError(
            error.category,
            sanitize_ai_error(error.message, api_key),
            error.status_code,
        ) from error
    return result


def _validate_blueprint_payload(payload: dict[str, Any]) -> TestCaseBlueprint:
    try:
        return TestCaseBlueprint.model_validate(
            _normalize_provider_warnings(payload, default_source="blueprint")
        )
    except ValidationError as error:
        raise TestCaseGenerationPayloadError(
            f"AI 蓝图返回结构不符合用例生成契约：{error.errors()[0]['msg']}"
        ) from error


def _validate_case_payload(payload: dict[str, Any]) -> _CaseGenerationStagePayload:
    try:
        return _CaseGenerationStagePayload.model_validate(
            _normalize_case_stage_payload(payload)
        )
    except ValidationError as error:
        raise TestCaseGenerationPayloadError(
            f"AI 用例返回结构不符合用例生成契约：{error.errors()[0]['msg']}"
        ) from error


def _normalize_provider_warnings(
    payload: dict[str, Any],
    *,
    default_source: str,
) -> dict[str, Any]:
    """兼容 provider 将 warnings 返回为字符串列表的常见形态。"""
    normalized = dict(payload)
    warnings = normalized.get("warnings")
    if not isinstance(warnings, list):
        normalized["warnings"] = []
        return normalized

    normalized_warnings: list[Any] = []
    for warning in warnings:
        if isinstance(warning, str):
            message = warning.strip()
            if message:
                normalized_warnings.append(
                    {
                        "source": default_source,
                        "level": "warning",
                        "message": message,
                    }
                )
            continue
        normalized_warnings.append(warning)
    normalized["warnings"] = normalized_warnings
    return normalized


def _normalize_case_stage_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """归一化 AI 用例阶段常见返回形态，再交给严格契约校验。"""
    normalized = _normalize_provider_warnings(payload, default_source="cases")
    normalized["cases"] = _normalize_provider_cases(normalized.get("cases"))
    normalized["requirement_trace"] = _normalize_provider_requirement_trace(
        normalized.get("requirement_trace")
    )
    return normalized


def _normalize_provider_cases(cases: Any) -> Any:
    if cases is None:
        return []
    if not isinstance(cases, list):
        return cases

    normalized_cases: list[Any] = []
    string_fields = set(GeneratedTestCase.model_fields)
    for item in cases:
        if not isinstance(item, dict):
            normalized_cases.append(item)
            continue
        normalized_item = dict(item)
        for field_name in string_fields:
            if field_name in normalized_item:
                normalized_item[field_name] = _coerce_provider_string(
                    normalized_item[field_name]
                )
        normalized_cases.append(normalized_item)
    return normalized_cases


def _normalize_provider_requirement_trace(traces: Any) -> Any:
    if traces is None:
        return []
    if not isinstance(traces, list):
        return traces

    normalized_traces: list[dict[str, Any]] = []
    for item in traces:
        if not isinstance(item, dict):
            normalized_traces.append(item)
            continue
        source_fragment = _coerce_provider_string(
            item.get("source_fragment")
            or item.get("requirement_id")
            or item.get("requirement")
            or item.get("source")
        )
        blueprint_node = _coerce_provider_string(
            item.get("blueprint_node") or item.get("module") or item.get("node")
        )
        source_row_index = item.get("source_row_index")
        case_ids = _resolve_trace_case_ids(item)
        for case_id in case_ids:
            normalized_traces.append(
                {
                    "source_row_index": source_row_index,
                    "source_fragment": source_fragment,
                    "blueprint_node": blueprint_node,
                    "case_id": case_id,
                }
            )
    return normalized_traces


def _resolve_trace_case_ids(item: dict[str, Any]) -> list[str]:
    case_id = item.get("case_id")
    if case_id not in (None, ""):
        return [_coerce_provider_string(case_id)]

    cases = item.get("cases")
    if isinstance(cases, list):
        resolved = [
            _coerce_provider_string(value)
            for value in cases
            if _coerce_provider_string(value)
        ]
        return resolved or [""]
    if cases not in (None, ""):
        return [_coerce_provider_string(cases)]
    return [""]


def _coerce_provider_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(
            text for text in (_coerce_provider_string(item).strip() for item in value) if text
        )
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _build_system_prompt() -> str:
    return (
        "你是资深测试设计专家。只返回符合给定 JSON Schema 的 JSON 对象，"
        "不要输出 Markdown、解释文本或模型统计。"
    )


def _build_blueprint_prompt(
    payload: TestCaseGenerationRequest,
    reference_context: ReferenceGenerationContext,
) -> str:
    snapshot = payload.planning_snapshot
    method_context = build_method_context()
    knowledge_context = get_internal_knowledge_context()
    snapshot_brief_context = _build_snapshot_brief_context(payload)
    lines = [
        "任务：先基于 Planning Sheet Snapshot 形成只读 Test Case Blueprint。",
        "不要直接堆测试用例行；必须蓝图先行。",
        _build_reference_policy(reference_context),
        f"方法：{method_context.method_name} {method_context.method_version}",
        f"项目级 QA 知识库：{knowledge_context['note']}",
        f"蓝图维度：{', '.join(BLUEPRINT_DIMENSIONS)}",
        f"完整性矩阵：{', '.join(COMPLETENESS_MATRIX)}",
        f"具体场景库：{', '.join(SCENARIO_LIBRARY)}",
        f"自检规则：{', '.join(SELF_CHECK_RULES)}",
        f"warning 模板：{', '.join(WARNING_TEMPLATES)}",
        "必须输出 modules、flows、requirement_traces、coverage_dimensions、risks、"
        "unmapped_requirements、unsupported_or_unfounded_test_points、open_questions、warnings。",
        "图片、附件、批注或评论语义未读取；相关判断必须写入 warnings 或 open_questions。",
    ]
    if snapshot_brief_context:
        lines.append(snapshot_brief_context)
    lines.extend(
        [
            "Planning Sheet Snapshot：",
            _render_snapshot_text(snapshot),
        ]
    )
    return "\n".join(lines)


def _build_snapshot_brief_context(payload: TestCaseGenerationRequest) -> str:
    brief = (payload.snapshot_brief_markdown or "").strip()
    if not brief:
        return ""
    return "\n".join(
        [
            "AI 快照整理稿（辅助上下文）：",
            "以下 Markdown 只用于帮助理解和组织输入，不是需求事实来源。",
            "需求来源只能来自 Planning Sheet Snapshot；如整理稿与原始快照冲突，以 Planning Sheet Snapshot 为准。",
            brief,
        ]
    )


def _build_cases_prompt(
    payload: TestCaseGenerationRequest,
    blueprint: TestCaseBlueprint,
    reference_context: ReferenceGenerationContext,
) -> str:
    method_context = build_method_context()
    snapshot_brief_context = _build_snapshot_brief_context(payload)
    lines = [
        "任务：基于只读 Test Case Blueprint 生成标准测试用例行。",
        _build_reference_policy(reference_context),
        f"方法：{method_context.method_name} {method_context.method_version}",
        f"项目级 QA 知识库：{method_context.knowledge_library_note}",
        f"标准字段顺序：{', '.join(STANDARD_CASE_FIELDS)}",
        "不得生成或声称已保存历史记录。",
        "不得输出最终统计；total、priority_counts、module_counts 由后端代码计算。",
        "每条用例必须尽量填写 source_requirement；无法定位来源时在 remarks 或 warnings 说明。",
        "优先使用快照中的原始需求片段，不确定解释写入 remarks。",
        "steps、expected_results、preconditions、remarks 等用例字段必须是字符串；多步骤使用换行分隔。",
        "只返回 cases、warnings、requirement_trace；不要返回 Markdown。",
    ]
    if snapshot_brief_context:
        lines.append(snapshot_brief_context)
    lines.extend(
        [
            "Planning Sheet Snapshot：",
            _render_snapshot_text(payload.planning_snapshot),
            "只读 Test Case Blueprint：",
            json.dumps(blueprint.model_dump(mode="json"), ensure_ascii=False),
        ]
    )
    return "\n".join(lines)


def _build_reference_policy(reference_context: ReferenceGenerationContext) -> str:
    base_lines = [
        "参考案例边界：参考案例不是需求来源；不得从参考案例推导新增需求、规则、"
        "测试点或 source_requirement。",
        "参考案例只作为字段顺序、层级、粒度、命名和历史风格参考；"
        "需求来源只能来自 Planning Sheet Snapshot。",
    ]
    if not reference_context.reference_ids:
        return "\n".join(
            [
                "参考案例：未选择参考案例增强；不要自动选择最新、第一条或推荐主参考。",
                *base_lines,
            ]
        )

    if reference_context.primary_reference_profile is None:
        return "\n".join(
            [
                "参考案例：已选择附加参考案例，但未指定主参考；"
                "不要自动选择最新、第一条或推荐主参考。",
                *base_lines,
                "附加参考摘要：",
                _format_reference_summaries(reference_context.supplementary_references),
            ]
        )

    primary_profile = reference_context.primary_reference_profile
    selected_sheet_name = primary_profile.get("selected_sheet_name") or "无 Sheet"
    reference_case_count = primary_profile.get("reference_case_count")
    recognized_fields = primary_profile.get("recognized_fields") or []
    lines = [
        "参考案例：已指定主参考；只允许学习输出形态，不允许补充或替代策划案需求。",
        *base_lines,
        (
            "主参考摘要："
            f"ID={reference_context.primary_reference_id}；"
            f"文件={primary_profile.get('original_filename') or primary_profile.get('source_name')}；"
            f"类型={primary_profile.get('source_type')}；"
            f"Sheet={selected_sheet_name}；"
            f"参考用例数量：{reference_case_count}；"
            f"可识别字段顺序：{', '.join(recognized_fields) if recognized_fields else '无'}。"
        ),
    ]
    if reference_context.supplementary_references:
        lines.extend(
            [
                "附加参考摘要：",
                _format_reference_summaries(reference_context.supplementary_references),
            ]
        )
    return "\n".join(lines)


def _format_reference_summaries(summaries: list[dict[str, object]]) -> str:
    if not summaries:
        return "- 无"
    lines: list[str] = []
    for item in summaries:
        recognized_fields = item.get("recognized_fields") or []
        recognized_text = (
            ", ".join(recognized_fields)
            if isinstance(recognized_fields, list) and recognized_fields
            else "无"
        )
        lines.append(
            "- "
            f"ID={item.get('id')}；"
            f"文件={item.get('original_filename')}；"
            f"类型={item.get('source_type')}；"
            f"默认 Sheet={item.get('default_sheet_name') or '无'}；"
            f"参考用例数量={item.get('reference_case_count')}；"
            f"可识别字段={recognized_text}"
        )
    return "\n".join(lines)


def _render_snapshot_text(snapshot: PlanningSnapshotResponse) -> str:
    lines = [
        f"来源：{snapshot.source_summary}",
        f"Sheet：{snapshot.sheet_name}",
        f"列：{', '.join(snapshot.columns)}",
        f"非空单元格：{snapshot.non_empty_cell_count}",
    ]
    for row in snapshot.rows:
        fragments = []
        for cell in row.cells:
            if not cell.value.strip():
                continue
            column_name = cell.column_name or f"Column {cell.column_index}"
            fragments.append(f"{column_name}={cell.value}")
        if fragments:
            lines.append(f"行 {row.row_index}: " + " | ".join(fragments))
    if snapshot.warnings:
        lines.append("快照 warnings：")
        lines.extend(f"- {warning.message}" for warning in snapshot.warnings)
    return "\n".join(lines)


def _normalize_cases(cases: list[GeneratedTestCase]) -> list[GeneratedTestCase]:
    normalized: list[GeneratedTestCase] = []
    used_ids: set[str] = set()
    for index, case in enumerate(cases, start=1):
        case_id = case.case_id.strip() or f"TC-{index:03d}"
        if case_id in used_ids:
            case_id = f"TC-{index:03d}"
        used_ids.add(case_id)
        normalized.append(case.model_copy(update={"case_id": case_id}))
    return normalized


def _normalize_requirement_trace(
    traces: list[RequirementTrace],
    *,
    cases: list[GeneratedTestCase],
    snapshot: PlanningSnapshotResponse,
) -> list[RequirementTrace]:
    if traces:
        return traces

    row_fragments = _snapshot_row_fragments(snapshot)
    normalized: list[RequirementTrace] = []
    for case in cases:
        source_requirement = case.source_requirement.strip()
        matched_row_index: int | None = None
        matched_fragment = source_requirement
        if source_requirement:
            for row_index, fragment in row_fragments:
                if source_requirement in fragment or fragment in source_requirement:
                    matched_row_index = row_index
                    matched_fragment = fragment
                    break
        normalized.append(
            RequirementTrace(
                source_row_index=matched_row_index,
                source_fragment=matched_fragment,
                blueprint_node=case.module or case.feature or case.title,
                case_id=case.case_id,
            )
        )
    return normalized


def _snapshot_row_fragments(
    snapshot: PlanningSnapshotResponse,
) -> list[tuple[int, str]]:
    fragments: list[tuple[int, str]] = []
    for row in snapshot.rows:
        values = [cell.value.strip() for cell in row.cells if cell.value.strip()]
        if values:
            fragments.append((row.row_index, " | ".join(values)))
    return fragments


def _compute_stats(
    cases: list[GeneratedTestCase],
    warnings: list[GenerationWarning],
) -> GeneratedCaseStats:
    priority_counts = Counter(case.priority or "P2" for case in cases)
    module_counts = Counter(case.module or "未分类" for case in cases)
    case_type_counts = Counter(
        case.case_type for case in cases if case.case_type.strip()
    )
    return GeneratedCaseStats(
        total=len(cases),
        priority_counts=dict(priority_counts),
        module_counts=dict(module_counts),
        case_type_counts=dict(case_type_counts),
        warning_count=len(warnings),
    )
