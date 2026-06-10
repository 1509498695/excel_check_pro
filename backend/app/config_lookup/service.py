"""配置表查询核心服务。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
from backend.app.rule_configs.service import load_published_rule_config


async def lookup_config_table(
    db: AsyncSession,
    request: ConfigLookupRequest,
    *,
    parsed_config_override: dict[str, Any] | None = None,
    file_resolver: ConfigLookupFileResolver | None = None,
    ai_matcher: ConfigLookupAiMatcher | None = None,
) -> ConfigLookupResponse:
    """执行配置表查询，不接飞书命令或 HTTP API。"""

    parsed_config = (
        parsed_config_override
        if parsed_config_override is not None
        else await load_published_rule_config(db, project_id=request.project_id)
    )
    if parsed_config_override is None and not parsed_config:
        return _not_found("当前项目尚未发布配置表查询规则，请先在规则配置页发布")

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
        page_hits, candidates = _find_main_hits_and_candidates(
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

    return await _run_ai_name_match(
        db,
        request=request,
        query_config=query_config,
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
    queries = parsed_config.get("queries")
    if not isinstance(queries, list):
        return None
    for item in queries:
        if isinstance(item, dict) and str(item.get("query_type") or "") == query_type:
            return item
    return None


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
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], list[ConfigLookupCandidate]]:
    normalized_input = normalize_cell_value(lookup_input)
    is_numeric_input = normalized_input.isdigit()
    hits: list[tuple[dict[str, Any], dict[str, Any]]] = []
    candidates: list[ConfigLookupCandidate] = []

    for page_config in _list_page_configs(query_config):
        page_name = str(page_config.get("name") or "")
        rows = _read_cached_sheet(sheet_cache, main_file_path, page_name)
        id_field = str(page_config.get("id_field") or "")
        name_field = str(page_config.get("name_field") or "")
        for row_index, row in enumerate(rows):
            id_value = normalize_cell_value(get_cell(row, id_field))
            name_value = normalize_cell_value(get_cell(row, name_field))
            if is_numeric_input and id_value == normalized_input:
                hits.append((page_config, row))
            if name_value:
                candidates.append(
                    ConfigLookupCandidate(
                        key=f"{page_name}:{row_index}:{id_value}",
                        page=page_name,
                        id_value=id_value,
                        name_value=name_value,
                        row=row,
                        page_config=page_config,
                    )
                )
    return hits, candidates


def _build_results(
    *,
    query_config: dict[str, Any],
    query_type: str,
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
    query_root_url: str,
    version_folder: str,
    display_folder: str,
    file_resolver: ConfigLookupFileResolver | None,
    page_config: dict[str, Any],
    row: dict[str, Any],
    sheet_cache: dict[tuple[str, str], list[dict[str, Any]]],
    query_root_alias: str,
) -> ConfigLookupResultItem:
    id_field = str(page_config.get("id_field") or "")
    name_field = str(page_config.get("name_field") or "")
    id_value = normalize_cell_value(get_cell(row, id_field))
    name_value = normalize_cell_value(get_cell(row, name_field))
    fields = [_field_value(row, output_field) for output_field in _list_output_fields(page_config)]
    warnings: list[str] = []

    for reference in _list_reference_configs(query_config):
        ref_file_path = _resolve_file(
            file_resolver=file_resolver,
            query_root_url=query_root_url,
            version_folder=version_folder,
            file_name=str(reference.get("file") or ""),
            query_root_alias=query_root_alias,
            display_folder=display_folder,
        )
        ref_rows = _read_cached_sheet(sheet_cache, ref_file_path, str(reference.get("page") or ""))
        left_field, right_field = _parse_join(str(reference.get("join") or ""))
        left_value = normalize_cell_value(get_cell(row, left_field))
        matched_ref = next(
            (
                ref_row
                for ref_row in ref_rows
                if normalize_cell_value(get_cell(ref_row, right_field)) == left_value
            ),
            None,
        )
        if matched_ref is None:
            warnings.append(f"引用 {reference.get('name') or ''} 未命中：{left_field}={left_value}")
            fields.extend(
                ConfigLookupFieldValue(
                    field=str(output_field.get("field") or ""),
                    label=str(output_field.get("display_name") or output_field.get("field") or ""),
                    value="",
                )
                for output_field in _list_output_fields(reference)
            )
            continue
        fields.extend(_field_value(matched_ref, output_field) for output_field in _list_output_fields(reference))

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
        candidates=qualifying,
        ai=ai_info,
    )


class _AiSettings:
    def __init__(self, *, available: bool, thresholds: ConfigLookupThresholds) -> None:
        self.available = available
        self.thresholds = thresholds


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


def _field_value(row: dict[str, Any], output_field: dict[str, Any]) -> ConfigLookupFieldValue:
    field_name = str(output_field.get("field") or "")
    label = str(output_field.get("display_name") or field_name)
    return ConfigLookupFieldValue(
        field=field_name,
        label=label,
        value=normalize_cell_value(get_cell(row, field_name)),
    )


def _parse_join(join: str) -> tuple[str, str]:
    parts = [part.strip() for part in join.split("=", 1)]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ConfigLookupExcelError(f"关联格式不合法：{join}")
    return parts[0], parts[1]


def _list_page_configs(query_config: dict[str, Any]) -> list[dict[str, Any]]:
    pages = query_config.get("pages")
    return [page for page in pages if isinstance(page, dict)] if isinstance(pages, list) else []


def _list_reference_configs(query_config: dict[str, Any]) -> list[dict[str, Any]]:
    references = query_config.get("references")
    return [ref for ref in references if isinstance(ref, dict)] if isinstance(references, list) else []


def _list_output_fields(config: dict[str, Any]) -> list[dict[str, Any]]:
    output_fields = config.get("output_fields")
    if not isinstance(output_fields, list):
        return []
    return [field for field in output_fields if isinstance(field, dict)]


def _not_found(message: str, *, ai: ConfigLookupAiInfo | None = None) -> ConfigLookupResponse:
    return ConfigLookupResponse(status="not_found", message=message, ai=ai or ConfigLookupAiInfo())
