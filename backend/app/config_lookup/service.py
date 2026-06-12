"""配置表查询核心服务。"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config_lookup.ai_matcher import (
    AI_UNAVAILABLE_MESSAGE,
    AiMatcherUnavailable,
    ProjectAiMatcher,
)
from backend.app.config_lookup.excel_reader import (
    ConfigLookupExcelError,
    get_cell,
    normalize_cell_value,
    read_excel_sheet,
)
from backend.app.config_lookup.pathing import (
    ConfigLookupPathError,
    normalize_versioned_config_folder,
    resolve_config_file,
)
from backend.app.config_lookup.schemas import (
    ConfigLookupAiInfo,
    ConfigLookupAiMatcher,
    ConfigLookupCandidate,
    ConfigLookupFieldValue,
    ConfigLookupFileResolver,
    ConfigLookupRequest,
    ConfigLookupResponse,
    ConfigLookupResultItem,
    ConfigLookupThresholds,
)
from backend.app.models import ProjectAiCredentialRecord, ProjectQueryRootRecord
from backend.app.rule_configs.service import (
    has_any_published_rule_config,
    load_published_rule_config,
)

_DISPLAY_EXPR_RE = re.compile(r"^([^./\s]+)\.([^./\s]+)(?:/(\d+(?:\.\d+)?))?$")


async def lookup_config_table(
    db: AsyncSession,
    request: ConfigLookupRequest,
    *,
    parsed_config_override: dict[str, Any] | None = None,
    file_resolver: ConfigLookupFileResolver | None = None,
    ai_matcher: ConfigLookupAiMatcher | None = None,
) -> ConfigLookupResponse:
    """执行配置表查询，不接飞书命令或 HTTP API。"""

    parsed_config = parsed_config_override
    if parsed_config is None:
        parsed_config = await load_published_rule_config(
            db,
            project_id=request.project_id,
            query_type=request.query_type,
        )
        if not parsed_config:
            has_published = await has_any_published_rule_config(db, project_id=request.project_id)
            if not has_published:
                return _not_found("当前项目尚未发布配置表查询规则，请先在规则配置页发布")
            return _not_found(f"查询类型不存在：{request.query_type}")

    query_config = _find_query_config(parsed_config, request.query_type)
    if query_config is None:
        return _not_found(f"查询类型不存在：{request.query_type}")

    query_root_alias = str(query_config.get("query_root") or "")
    query_root = await _get_enabled_query_root(
        db,
        project_id=request.project_id,
        alias=query_root_alias,
    )
    if query_root is None:
        return _not_found(f"数据根不存在或未启用：{query_root_alias}")

    try:
        version_folder = normalize_versioned_config_folder(request.versioned_config_folder)
        main_file_path = _resolve_file(
            file_resolver=file_resolver,
            query_root_url=query_root.svn_root_url,
            version_folder=version_folder.relative,
            file_name=str(query_config.get("file") or ""),
            query_root_alias=query_root_alias,
            display_folder=version_folder.display,
        )
    except ConfigLookupPathError as exc:
        return _not_found(str(exc))
    except FileNotFoundError as exc:
        return _not_found(str(exc))

    sheet_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
    try:
        page_hits, candidates, partial_name_candidates = _find_main_hits_and_candidates(
            query_config=query_config,
            main_file_path=main_file_path,
            lookup_input=request.lookup_input,
            sheet_cache=sheet_cache,
        )
    except ConfigLookupExcelError as exc:
        return _not_found(str(exc))

    if page_hits:
        try:
            results = _build_results(
                query_config=query_config,
                query_type=request.query_type,
                main_file_path=main_file_path,
                query_root_url=query_root.svn_root_url,
                version_folder=version_folder.relative,
                display_folder=version_folder.display,
                file_resolver=file_resolver,
                page_hits=page_hits,
                sheet_cache=sheet_cache,
                query_root_alias=query_root_alias,
            )
        except (ConfigLookupExcelError, ConfigLookupPathError, FileNotFoundError) as exc:
            return _not_found(str(exc))
        return ConfigLookupResponse(status="hit", message="查询命中", results=results)

    if partial_name_candidates and _is_specific_partial_name(request.lookup_input):
        thresholds = (await _load_ai_settings(db, project_id=request.project_id)).thresholds
        candidate_reply = _candidate_reply(partial_name_candidates, thresholds.max_candidates)
        return ConfigLookupResponse(
            status="candidates",
            message=candidate_reply.message,
            candidates=candidate_reply.candidates,
            ai=ConfigLookupAiInfo(used=False),
        )

    return await _run_ai_name_match(
        db,
        request=request,
        query_config=query_config,
        main_file_path=main_file_path,
        query_root_url=query_root.svn_root_url,
        query_root_alias=query_root_alias,
        version_folder=version_folder.relative,
        display_folder=version_folder.display,
        file_resolver=file_resolver,
        candidates=candidates,
        sheet_cache=sheet_cache,
        ai_matcher=ai_matcher,
    )


def _find_query_config(parsed_config: dict[str, Any], query_type: str) -> dict[str, Any] | None:
    if str(parsed_config.get("query_type") or "") != query_type:
        return None
    return parsed_config


async def _get_enabled_query_root(
    db: AsyncSession,
    *,
    project_id: int,
    alias: str,
) -> ProjectQueryRootRecord | None:
    result = await db.execute(
        select(ProjectQueryRootRecord).where(
            ProjectQueryRootRecord.project_id == project_id,
            ProjectQueryRootRecord.alias == alias,
            ProjectQueryRootRecord.status == "enabled",
        )
    )
    return result.scalar_one_or_none()


def _resolve_file(
    *,
    file_resolver: ConfigLookupFileResolver | None,
    query_root_url: str,
    version_folder: str,
    file_name: str,
    query_root_alias: str,
    display_folder: str,
) -> Path:
    if file_resolver is not None:
        return Path(
            file_resolver.resolve(
                query_root_url=query_root_url,
                version_folder=version_folder,
                file_name=file_name,
            )
        )

    normalized = normalize_versioned_config_folder(version_folder)
    resolved = resolve_config_file(
        query_root_url=query_root_url,
        version_folder=normalized,
        file_name=file_name,
        query_root_alias=query_root_alias,
    )
    if resolved.missing_message:
        raise FileNotFoundError(resolved.missing_message)
    return resolved.path


def _find_main_hits_and_candidates(
    *,
    query_config: dict[str, Any],
    main_file_path: Path,
    lookup_input: str,
    sheet_cache: dict[tuple[str, str], list[dict[str, Any]]],
) -> tuple[
    list[tuple[dict[str, Any], dict[str, Any]]],
    list[ConfigLookupCandidate],
    list[ConfigLookupCandidate],
]:
    normalized_input = normalize_cell_value(lookup_input)
    is_numeric_input = normalized_input.isdigit()
    hits: list[tuple[dict[str, Any], dict[str, Any]]] = []
    candidates: list[ConfigLookupCandidate] = []
    partial_name_candidates: list[ConfigLookupCandidate] = []

    for page_config in _list_page_configs(query_config):
        page_name = str(page_config.get("name") or "")
        rows = _read_cached_sheet(sheet_cache, main_file_path, page_name)
        id_field = _id_match_field(page_config)
        text_match_fields = _text_match_fields(page_config)
        candidate_label_field = _candidate_label_field(page_config)
        for row_index, row in enumerate(rows):
            id_value = normalize_cell_value(get_cell(row, id_field))
            display_name_value = _candidate_display_name(
                row,
                candidate_label_field=candidate_label_field,
                fallback_fields=text_match_fields,
            )
            if is_numeric_input and id_value == normalized_input:
                hits.append((page_config, row))
            elif not is_numeric_input and _matches_any_text_field(
                row,
                text_match_fields=text_match_fields,
                lookup_input=normalized_input,
                exact=True,
            ):
                hits.append((page_config, row))
            if display_name_value:
                candidate = ConfigLookupCandidate(
                    key=f"{page_name}:{row_index}:{id_value}",
                    page=page_name,
                    id_value=id_value,
                    name_value=display_name_value,
                    row=row,
                    page_config=page_config,
                )
                candidates.append(candidate)
                if (
                    not is_numeric_input
                    and normalized_input
                    and _matches_any_text_field(
                        row,
                        text_match_fields=text_match_fields,
                        lookup_input=normalized_input,
                        exact=False,
                    )
                    and not _matches_any_text_field(
                        row,
                        text_match_fields=text_match_fields,
                        lookup_input=normalized_input,
                        exact=True,
                    )
                ):
                    partial_name_candidates.append(candidate)
    return hits, candidates, partial_name_candidates


def _build_results(
    *,
    query_config: dict[str, Any],
    query_type: str,
    main_file_path: Path,
    query_root_url: str,
    version_folder: str,
    display_folder: str,
    file_resolver: ConfigLookupFileResolver | None,
    page_hits: list[tuple[dict[str, Any], dict[str, Any]]],
    sheet_cache: dict[tuple[str, str], list[dict[str, Any]]],
    query_root_alias: str,
) -> list[ConfigLookupResultItem]:
    results: list[ConfigLookupResultItem] = []
    for page_config, row in page_hits:
        results.append(
            _build_result_item(
                query_config=query_config,
                query_type=query_type,
                main_file_path=main_file_path,
                query_root_url=query_root_url,
                version_folder=version_folder,
                display_folder=display_folder,
                file_resolver=file_resolver,
                page_config=page_config,
                row=row,
                sheet_cache=sheet_cache,
                query_root_alias=query_root_alias,
            )
        )
    return results


def _build_result_item(
    *,
    query_config: dict[str, Any],
    query_type: str,
    main_file_path: Path,
    query_root_url: str,
    version_folder: str,
    display_folder: str,
    file_resolver: ConfigLookupFileResolver | None,
    page_config: dict[str, Any],
    row: dict[str, Any],
    sheet_cache: dict[tuple[str, str], list[dict[str, Any]]],
    query_root_alias: str,
) -> ConfigLookupResultItem:
    id_field = _id_match_field(page_config)
    name_field = _candidate_label_field(page_config)
    id_value = normalize_cell_value(get_cell(row, id_field))
    name_value = _candidate_display_name(
        row,
        candidate_label_field=name_field,
        fallback_fields=_text_match_fields(page_config),
    )
    fields: list[ConfigLookupFieldValue] = []
    warnings: list[str] = []
    for output_field in _list_output_fields(page_config):
        field, warning = _field_value(
            row,
            output_field,
            current_page_name=str(page_config.get("name") or ""),
            main_file_path=main_file_path,
            sheet_cache=sheet_cache,
        )
        fields.append(field)
        if warning:
            warnings.append(warning)

    return ConfigLookupResultItem(
        query_type=query_type,
        page=str(page_config.get("name") or ""),
        id_value=id_value,
        name_value=name_value,
        fields=fields,
        warnings=warnings,
    )


async def _run_ai_name_match(
    db: AsyncSession,
    *,
    request: ConfigLookupRequest,
    query_config: dict[str, Any],
    main_file_path: Path,
    query_root_url: str,
    query_root_alias: str,
    version_folder: str,
    display_folder: str,
    file_resolver: ConfigLookupFileResolver | None,
    candidates: list[ConfigLookupCandidate],
    sheet_cache: dict[tuple[str, str], list[dict[str, Any]]],
    ai_matcher: ConfigLookupAiMatcher | None,
) -> ConfigLookupResponse:
    ai_settings = await _load_ai_settings(db, project_id=request.project_id)
    thresholds = ai_settings.thresholds
    ai_info = ConfigLookupAiInfo(used=True, thresholds=thresholds)
    if not candidates:
        return ConfigLookupResponse(
            status="not_found",
            message="未找到可用于名称匹配的候选",
            ai=ai_info,
        )
    if not ai_settings.available:
        return ConfigLookupResponse(
            status="ai_unavailable",
            message=AI_UNAVAILABLE_MESSAGE,
            ai=ConfigLookupAiInfo(
                used=True,
                unavailable_reason=AI_UNAVAILABLE_MESSAGE,
                thresholds=thresholds,
            ),
        )

    matcher = ai_matcher or ProjectAiMatcher(db, project_id=request.project_id)
    try:
        scores = await matcher.rank(lookup_input=request.lookup_input, candidates=candidates)
    except AiMatcherUnavailable as exc:
        return ConfigLookupResponse(
            status="ai_unavailable",
            message=AI_UNAVAILABLE_MESSAGE,
            ai=ConfigLookupAiInfo(
                used=True,
                unavailable_reason=str(exc) or AI_UNAVAILABLE_MESSAGE,
                thresholds=thresholds,
            ),
        )

    candidates_by_key = {candidate.key: candidate for candidate in candidates}
    scored_candidates = [
        ConfigLookupCandidate(
            key=candidate.key,
            page=candidate.page,
            id_value=candidate.id_value,
            name_value=candidate.name_value,
            score=max(0.0, min(1.0, score.score)),
            row=candidate.row,
            page_config=candidate.page_config,
        )
        for score in scores
        if (candidate := candidates_by_key.get(score.candidate_key)) is not None
    ]
    scored_candidates.sort(key=lambda item: item.score, reverse=True)
    qualifying = [
        candidate
        for candidate in scored_candidates
        if candidate.score >= thresholds.candidate_threshold
    ][: thresholds.max_candidates]

    if not qualifying:
        candidate_reply = _candidate_reply(scored_candidates, thresholds.max_candidates)
        if candidate_reply.candidates:
            return ConfigLookupResponse(
                status="candidates",
                message=candidate_reply.message,
                candidates=candidate_reply.candidates,
                ai=ai_info,
            )
        return ConfigLookupResponse(
            status="not_found",
            message="未找到高置信候选，请尝试输入更准确的名称或 ID",
            ai=ai_info,
        )

    top = qualifying[0]
    if top.score >= thresholds.auto_match_threshold and len(qualifying) == 1:
        try:
            result = _build_result_item(
                query_config=query_config,
                query_type=request.query_type,
                main_file_path=main_file_path,
                query_root_url=query_root_url,
                version_folder=version_folder,
                display_folder=display_folder,
                file_resolver=file_resolver,
                page_config=top.page_config,
                row=top.row,
                sheet_cache=sheet_cache,
                query_root_alias=query_root_alias,
            )
        except (ConfigLookupExcelError, ConfigLookupPathError, FileNotFoundError) as exc:
            return _not_found(str(exc), ai=ai_info)
        return ConfigLookupResponse(
            status="hit",
            message="AI 名称匹配命中",
            results=[result],
            ai=ai_info,
        )

    return ConfigLookupResponse(
        status="candidates",
        message="找到多个可能匹配的候选，请选择后查看详情",
        candidates=_dedupe_candidates(qualifying),
        ai=ai_info,
    )


class _AiSettings:
    def __init__(self, *, available: bool, thresholds: ConfigLookupThresholds) -> None:
        self.available = available
        self.thresholds = thresholds


def _dedupe_candidates(candidates: list[ConfigLookupCandidate]) -> list[ConfigLookupCandidate]:
    deduped: list[ConfigLookupCandidate] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        key = (candidate.id_value, candidate.name_value)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _id_match_field(page_config: dict[str, Any]) -> str:
    return str(page_config.get("id_match_field") or page_config.get("id_field") or "")


def _text_match_fields(page_config: dict[str, Any]) -> list[str]:
    raw_fields = page_config.get("text_match_fields")
    fields: list[str] = []
    if isinstance(raw_fields, list):
        for item in raw_fields:
            if isinstance(item, dict):
                field = str(item.get("field") or "").strip()
                if field:
                    fields.append(field)
    if fields:
        return fields
    legacy = str(page_config.get("name_field") or "").strip()
    return [legacy] if legacy else []


def _candidate_label_field(page_config: dict[str, Any]) -> str:
    label_field = str(page_config.get("candidate_label_field") or "").strip()
    if label_field:
        return label_field
    fields = _text_match_fields(page_config)
    return fields[0] if fields else ""


def _candidate_display_name(
    row: dict[str, Any],
    *,
    candidate_label_field: str,
    fallback_fields: list[str],
) -> str:
    primary = normalize_cell_value(get_cell(row, candidate_label_field))
    if primary:
        return primary
    for field in fallback_fields:
        value = normalize_cell_value(get_cell(row, field))
        if value:
            return value
    return ""


def _matches_any_text_field(
    row: dict[str, Any],
    *,
    text_match_fields: list[str],
    lookup_input: str,
    exact: bool,
) -> bool:
    for field in text_match_fields:
        value = normalize_cell_value(get_cell(row, field))
        if exact and value == lookup_input:
            return True
        if not exact and lookup_input in value:
            return True
    return False


class _CandidateReply:
    def __init__(self, *, message: str, candidates: list[ConfigLookupCandidate]) -> None:
        self.message = message
        self.candidates = candidates


def _candidate_reply(
    candidates: list[ConfigLookupCandidate],
    max_candidates: int,
) -> _CandidateReply:
    deduped = _dedupe_candidates(candidates)
    limit = max(1, max_candidates)
    limited = deduped[-limit:]
    total = len(deduped)
    if total > limit:
        message = (
            f"找到 {total} 个候选，仅展示最后 {limit} 个，"
            "请补充更具体的名称、价格、月份或直接使用 ID 查询。"
        )
    else:
        message = f"找到 {total} 个候选，请使用 ID 精确查询。"
    return _CandidateReply(message=message, candidates=limited)


def _is_specific_partial_name(value: str) -> bool:
    normalized = normalize_cell_value(value)
    return len(normalized) >= 4


async def _load_ai_settings(db: AsyncSession, *, project_id: int) -> _AiSettings:
    result = await db.execute(
        select(ProjectAiCredentialRecord).where(ProjectAiCredentialRecord.project_id == project_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return _AiSettings(available=False, thresholds=ConfigLookupThresholds())
    thresholds = ConfigLookupThresholds(
        auto_match_threshold=float(record.auto_match_threshold or 0.9),
        candidate_threshold=float(record.candidate_threshold or 0.6),
        max_candidates=max(1, min(20, int(record.max_candidates or 10))),
    )
    return _AiSettings(
        available=bool(record.enabled and record.encrypted_api_key and record.base_url and record.model),
        thresholds=thresholds,
    )


def _read_cached_sheet(
    sheet_cache: dict[tuple[str, str], list[dict[str, Any]]],
    file_path: Path,
    sheet_name: str,
) -> list[dict[str, Any]]:
    key = (str(file_path), sheet_name)
    if key not in sheet_cache:
        sheet_cache[key] = read_excel_sheet(file_path, sheet_name)
    return sheet_cache[key]


def _field_value(
    row: dict[str, Any],
    output_field: dict[str, Any],
    *,
    current_page_name: str,
    main_file_path: Path,
    sheet_cache: dict[tuple[str, str], list[dict[str, Any]]],
) -> tuple[ConfigLookupFieldValue, str | None]:
    field_name = str(output_field.get("field") or "")
    label = str(output_field.get("label") or field_name)
    raw_value = normalize_cell_value(get_cell(row, field_name))
    reference = output_field.get("reference")
    if isinstance(reference, dict):
        value, warning = _reference_field_value(
            row,
            reference,
            raw_value=raw_value,
            current_page_name=current_page_name,
            main_file_path=main_file_path,
            sheet_cache=sheet_cache,
        )
        return ConfigLookupFieldValue(field=field_name, label=label, value=value), warning

    formatter = output_field.get("formatter")
    if isinstance(formatter, dict):
        value = _apply_formatter(raw_value, formatter)
    else:
        value = _apply_value_map(raw_value, output_field.get("value_map"))
    return ConfigLookupFieldValue(
        field=field_name,
        label=label,
        value=value,
    ), None


def _reference_field_value(
    row: dict[str, Any],
    reference: dict[str, Any],
    *,
    raw_value: str,
    current_page_name: str,
    main_file_path: Path,
    sheet_cache: dict[tuple[str, str], list[dict[str, Any]]],
) -> tuple[str, str | None]:
    ref_page = str(reference.get("page") or "")
    left_page, left_field, right_page, right_field = _parse_join(str(reference.get("join") or ""))
    if left_page != current_page_name or right_page != ref_page:
        raise ConfigLookupExcelError(f"引用规则分页不匹配：{reference.get('join') or ''}")
    left_value = normalize_cell_value(get_cell(row, left_field))
    ref_rows = _read_cached_sheet(sheet_cache, main_file_path, ref_page)
    matched_ref = next(
        (
            ref_row
            for ref_row in ref_rows
            if normalize_cell_value(get_cell(ref_row, right_field)) == left_value
        ),
        None,
    )
    if matched_ref is None:
        return f"{raw_value}(引用未找到)", f"引用未找到：{left_page}.{left_field}={left_value}"
    value = _evaluate_display_expression(
        matched_ref,
        str(reference.get("display_expression") or ""),
        expected_page=ref_page,
    )
    return value, None


def _apply_value_map(raw_value: str, value_map: Any) -> str:
    if raw_value == "":
        return "未配置"
    if isinstance(value_map, dict):
        mapped = value_map.get(raw_value)
        if mapped is not None:
            return str(mapped)
        tail_value = _colon_tail(raw_value)
        if tail_value != raw_value:
            mapped = value_map.get(tail_value)
            if mapped is not None:
                return str(mapped)
    return raw_value


def _apply_formatter(raw_value: str, formatter: dict[str, Any]) -> str:
    if raw_value in {"", "0"}:
        return "未配置"

    formatter_type = str(formatter.get("type") or "")
    timezone_name = str(formatter.get("timezone") or "Asia/Shanghai")
    if formatter_type != "timestamp_seconds" or timezone_name != "Asia/Shanghai":
        raise ConfigLookupExcelError("输出字段格式配置只支持 时间戳秒 + Asia/Shanghai")
    if not raw_value.isdigit() or len(raw_value) != 10:
        return f"{raw_value}(时间格式错误)"

    try:
        timestamp = int(raw_value)
        formatted = datetime.fromtimestamp(timestamp, ZoneInfo(timezone_name))
    except (OverflowError, ValueError):
        return f"{raw_value}(时间格式错误)"
    return formatted.strftime("%Y/%m/%d %H:%M:%S")


def _colon_tail(raw_value: str) -> str:
    parts = re.split(r"[:：]", raw_value)
    return parts[-1].strip() if parts else raw_value


def _evaluate_display_expression(
    row: dict[str, Any],
    display_expression: str,
    *,
    expected_page: str,
) -> str:
    match = _DISPLAY_EXPR_RE.match(display_expression)
    if match is None:
        raise ConfigLookupExcelError(f"显示内容格式不合法：{display_expression}")
    page_name, field_name, divisor = match.groups()
    if page_name != expected_page:
        raise ConfigLookupExcelError(f"显示内容分页不匹配：{display_expression}")
    raw_value = normalize_cell_value(get_cell(row, field_name))
    if not divisor:
        return raw_value
    try:
        result = Decimal(raw_value) / Decimal(divisor)
    except (InvalidOperation, ZeroDivisionError) as exc:
        raise ConfigLookupExcelError(f"显示内容无法计算：{display_expression}") from exc
    normalized = result.normalize()
    return format(normalized, "f")


def _parse_join(join: str) -> tuple[str, str, str, str]:
    parts = [part.strip() for part in join.split("=", 1)]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ConfigLookupExcelError(f"关联格式不合法：{join}")
    left = parts[0].split(".", 1)
    right = parts[1].split(".", 1)
    if len(left) != 2 or len(right) != 2 or not all(left + right):
        raise ConfigLookupExcelError(f"关联格式不合法：{join}")
    return left[0], left[1], right[0], right[1]


def _list_page_configs(query_config: dict[str, Any]) -> list[dict[str, Any]]:
    pages = query_config.get("pages")
    return [page for page in pages if isinstance(page, dict)] if isinstance(pages, list) else []


def _list_output_fields(config: dict[str, Any]) -> list[dict[str, Any]]:
    output_fields = config.get("output_fields")
    if not isinstance(output_fields, list):
        return []
    return [field for field in output_fields if isinstance(field, dict)]


def _not_found(message: str, *, ai: ConfigLookupAiInfo | None = None) -> ConfigLookupResponse:
    return ConfigLookupResponse(status="not_found", message=message, ai=ai or ConfigLookupAiInfo())
