"""礼包规划表规则预解析服务。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.fixed_rules_schemas import (
    PackageAiParseMode,
    PackageDetailRange,
    PackageFieldMapping,
    PackageItemsPreviewDetailRow,
    PackageItemsPreviewResult,
    PackageParseStrategy,
    PackagePlanItemRow,
    PackageSheetParseResult,
)
from backend.app.api.schemas import DataSource
from backend.app.loaders.feishu_reader import parse_feishu_sheet_url
from backend.app.services.package_items_ai_parse_cache import (
    PackageItemsAiParseCacheKey,
    build_sheet_matrix_hash,
    get_package_items_ai_parse_cache,
    set_package_items_ai_parse_cache,
)
from backend.app.services.package_items_ai_parser import (
    PackageAiParseError,
    PackageItemsAiClient,
    PROMPT_VERSION,
    parse_package_sheet_with_ai,
)


_PACKAGE_ALIASES = {"礼包id", "packageid"}
_ITEM_ALIASES = {"道具id", "itemid"}
_COUNT_ALIASES = {"个数", "数量", "count", "num"}
_FIELD_ALIASES: dict[str, set[str]] = {
    "package_id": _PACKAGE_ALIASES,
    "item_id": _ITEM_ALIASES,
    "count": _COUNT_ALIASES,
}
_REQUIRED_FIELDS = ("package_id", "item_id", "count")
_EXACT_CHINESE_HEADERS = {
    "package_id": "礼包id",
    "item_id": "道具id",
    "count": "个数",
}
_FIELD_LABELS = {
    "package_id": "礼包 ID",
    "item_id": "道具 ID",
    "count": "数量",
}
_RULE_HIGH_CONFIDENCE_THRESHOLD = 0.8


@dataclass(frozen=True)
class _HeaderDetection:
    row_index: int
    mapping: dict[str, int]
    field_mapping: dict[str, str]

    @property
    def missing_fields(self) -> list[str]:
        return [field_name for field_name in _REQUIRED_FIELDS if field_name not in self.mapping]

    @property
    def is_complete(self) -> bool:
        return not self.missing_fields


@dataclass
class _ActiveDetailRange:
    header_row: int
    start_row: int | None = None
    end_row: int | None = None

    def add_row(self, row_index: int) -> None:
        if self.start_row is None:
            self.start_row = row_index
        self.end_row = row_index

    def to_detail_range(self) -> PackageDetailRange | None:
        if self.start_row is None or self.end_row is None:
            return None
        return PackageDetailRange(
            header_row=self.header_row,
            start_row=self.start_row,
            end_row=self.end_row,
        )


@dataclass(frozen=True)
class PackageItemsAiParseCacheContext:
    """礼包规划表 AI 解析缓存上下文。"""

    feishu_source_id: str
    sheet_id: str
    sheet_revision_or_hash: str


async def preview_package_items_from_feishu(
    source: DataSource,
    *,
    sheet_id: str,
    parse_strategy: PackageParseStrategy,
    ai_parse_mode: PackageAiParseMode,
    db: AsyncSession,
    project_id: int,
    user_id: int | None = None,
) -> PackageItemsPreviewResult:
    """读取飞书 Sheet 显示值并执行礼包明细解析。"""
    from backend.app.integrations.feishu_client import read_sheet_values

    locator = parse_feishu_sheet_url(source.pathOrUrl or source.url or source.path or "")
    table = await read_sheet_values(
        db,
        project_id,
        locator,
        sheet_id=sheet_id,
        value_render_option="FormattedValue",
    )
    result = await parse_package_items_sheet_async(
        table.raw_values,
        sheet_name=table.sheet_title,
        parse_strategy=parse_strategy,
        ai_parse_mode=ai_parse_mode,
        db=db,
        user_id=user_id,
        ai_cache_context=PackageItemsAiParseCacheContext(
            feishu_source_id=source.id,
            sheet_id=table.sheet_id or sheet_id,
            sheet_revision_or_hash=build_sheet_matrix_hash(table.raw_values),
        ),
    )
    result.raw_sheet_name = table.sheet_title
    return result


async def parse_package_items_sheet_async(
    raw_values: list[list[Any]],
    *,
    sheet_name: str | None = None,
    parse_strategy: PackageParseStrategy = "auto",
    ai_parse_mode: PackageAiParseMode = "auto",
    db: AsyncSession | None = None,
    user_id: int | None = None,
    ai_client: PackageItemsAiClient | None = None,
    ai_cache_context: PackageItemsAiParseCacheContext | None = None,
) -> PackageItemsPreviewResult:
    """按解析策略编排规则解析与 AI 结构识别。"""
    if parse_strategy == "rule":
        return _as_preview_result(parse_package_items_sheet(raw_values))

    if parse_strategy == "ai":
        if ai_parse_mode == "disabled":
            return PackageItemsPreviewResult(
                parse_status="failed",
                parse_mode="ai",
                errors=["AI 辅助解析已关闭。"],
            )
        return await _parse_package_items_with_ai(
            raw_values,
            sheet_name=sheet_name,
            db=db,
            user_id=user_id,
            ai_client=ai_client,
            fallback_rule_result=None,
            cache_context=ai_cache_context,
            parse_strategy=parse_strategy,
            ai_parse_mode=ai_parse_mode,
        )

    rule_result = parse_package_items_sheet(raw_values)
    if rule_result.parse_status == "success" and (
        rule_result.confidence >= _RULE_HIGH_CONFIDENCE_THRESHOLD
    ):
        return _as_preview_result(rule_result)

    if ai_parse_mode == "disabled":
        next_result = _as_preview_result(rule_result)
        next_result.warnings.append("AI 辅助解析已关闭。")
        return next_result

    return await _parse_package_items_with_ai(
        raw_values,
        sheet_name=sheet_name,
        db=db,
        user_id=user_id,
        ai_client=ai_client,
        fallback_rule_result=rule_result,
        cache_context=ai_cache_context,
        parse_strategy=parse_strategy,
        ai_parse_mode=ai_parse_mode,
    )


def parse_package_items_sheet(
    raw_values: list[list[Any]],
    *,
    parse_strategy: PackageParseStrategy = "auto",
    ai_parse_mode: PackageAiParseMode = "auto",
) -> PackageItemsPreviewResult:
    """从二维数组中扫描礼包明细区域，保留原始 Sheet 行号。"""
    del parse_strategy, ai_parse_mode
    if not raw_values:
        return PackageItemsPreviewResult(
            parse_status="failed",
            parse_mode="rule",
            ai_used=False,
            confidence=0.0,
            errors=["Sheet 为空"],
        )

    warnings: list[str] = []
    errors: list[str] = []
    header_rows: list[int] = []
    detail_ranges: list[PackageDetailRange] = []
    preview_detail_rows: list[PackageItemsPreviewDetailRow] = []
    rows: list[PackagePlanItemRow] = []
    package_ids: list[str] = []
    seen_package_ids: set[str] = set()
    seen_item_rows: dict[tuple[str, str], int] = {}
    complete_headers: list[_HeaderDetection] = []
    partial_headers: list[_HeaderDetection] = []
    active_header: _HeaderDetection | None = None
    active_range: _ActiveDetailRange | None = None
    first_field_mapping: dict[str, str] = {}

    for row_offset, row in enumerate(raw_values):
        row_index = row_offset + 1
        header_detection = _detect_header(row, row_index=row_index)
        if header_detection is not None:
            completed_range = active_range.to_detail_range() if active_range else None
            if completed_range is not None:
                detail_ranges.append(completed_range)
            active_range = None

            header_rows.append(row_index)
            if header_detection.is_complete:
                active_header = header_detection
                active_range = _ActiveDetailRange(header_row=row_index)
                complete_headers.append(header_detection)
                if not first_field_mapping:
                    first_field_mapping = dict(header_detection.field_mapping)
            else:
                active_header = None
                partial_headers.append(header_detection)
            continue

        if active_header is None:
            continue
        if _is_empty_row(row):
            continue

        parsed_row, row_warning = _parse_detail_row(
            row,
            row_index=row_index,
            header=active_header,
        )
        if parsed_row is None:
            warnings.append(row_warning or f"跳过第 {row_index} 行：缺少礼包 ID、道具 ID 或数量字段。")
            continue

        _append_duplicate_item_warning(
            warnings,
            seen_item_rows=seen_item_rows,
            package_id=parsed_row.package_id,
            item_id=parsed_row.item_id,
            row_index=parsed_row.row_index,
        )
        rows.append(parsed_row)
        preview_detail_rows.append(
            PackageItemsPreviewDetailRow(
                row_index=parsed_row.row_index,
                package_id=parsed_row.package_id,
                item_id=parsed_row.item_id,
                count=str(parsed_row.count),
            )
        )
        assert active_range is not None
        active_range.add_row(row_index)
        if parsed_row.package_id not in seen_package_ids:
            seen_package_ids.add(parsed_row.package_id)
            package_ids.append(parsed_row.package_id)

    completed_range = active_range.to_detail_range() if active_range else None
    if completed_range is not None:
        detail_ranges.append(completed_range)

    field_mapping = _build_field_mapping(first_field_mapping, partial_headers)
    errors.extend(_build_parse_errors(complete_headers, partial_headers, rows))
    if rows and _has_unusually_few_rows(raw_values, complete_headers, rows):
        warnings.append("明细行数量异常：识别到的有效明细行明显偏少。")

    parse_status = "success" if complete_headers and rows and not errors else "failed"
    confidence = _estimate_rule_confidence(
        complete_headers=complete_headers,
        detail_ranges=detail_ranges,
        package_ids=package_ids,
        rows=rows,
    )
    return PackageItemsPreviewResult(
        parse_status=parse_status,
        parse_mode="rule",
        ai_used=False,
        confidence=confidence,
        header_rows=header_rows,
        detail_ranges=detail_ranges,
        field_mapping=field_mapping,
        package_ids=package_ids,
        package_count=len(package_ids),
        detail_row_count=len(rows),
        rows=rows,
        warnings=warnings,
        errors=errors,
        detail_rows=preview_detail_rows,
    )


def build_package_items_map(
    rows: list[PackagePlanItemRow],
) -> dict[str, dict[str, int]]:
    """将解析出的礼包明细行转换为 package_id -> item_id -> count。"""
    result: dict[str, dict[str, int]] = {}
    for row in rows:
        result.setdefault(row.package_id, {})[row.item_id] = row.count
    return result


def _append_duplicate_item_warning(
    warnings: list[str],
    *,
    seen_item_rows: dict[tuple[str, str], int],
    package_id: str,
    item_id: str,
    row_index: int,
) -> None:
    key = (package_id, item_id)
    first_row_index = seen_item_rows.get(key)
    if first_row_index is None:
        seen_item_rows[key] = row_index
        return
    warnings.append(
        f"识别到重复道具 ID：礼包 {package_id} 的道具 {item_id} "
        f"在第 {first_row_index} 行和第 {row_index} 行重复。"
    )


def extract_package_items_by_ai_suggestion(
    sheet_matrix: list[list[Any]],
    suggestion: Any,
) -> PackageSheetParseResult:
    """根据 AI 结构建议，从原始 Sheet 中确定性抽取礼包明细。"""
    confidence = _coerce_suggestion_confidence(suggestion)
    warnings = _coerce_suggestion_warnings(suggestion)
    errors: list[str] = []
    header_rows = _coerce_suggestion_header_rows(suggestion)
    detail_ranges = _coerce_suggestion_detail_ranges(suggestion)
    suggested_field_mapping = _coerce_suggestion_field_mapping(suggestion)
    field_mapping = _build_package_field_mapping(suggested_field_mapping)
    rows: list[PackagePlanItemRow] = []
    package_ids: list[str] = []
    seen_package_ids: set[str] = set()
    seen_item_rows: dict[tuple[str, str], int] = {}
    first_resolved_mapping: PackageFieldMapping | None = None

    if not header_rows:
        errors.append("AI 结构建议缺少 header_rows。")
    if not detail_ranges:
        errors.append("AI 结构建议缺少 detail_ranges。")

    for detail_range in detail_ranges:
        range_errors = _validate_ai_detail_range(detail_range, row_count=len(sheet_matrix))
        if range_errors:
            errors.extend(range_errors)
            continue

        header_row = sheet_matrix[detail_range.header_row - 1]
        column_mapping, resolved_field_mapping, mapping_errors = _resolve_ai_field_columns(
            header_row,
            header_row_index=detail_range.header_row,
            suggested_field_mapping=suggested_field_mapping,
        )
        if mapping_errors:
            errors.extend(mapping_errors)
            continue
        if first_resolved_mapping is None:
            first_resolved_mapping = resolved_field_mapping

        for row_index in range(detail_range.start_row, detail_range.end_row + 1):
            row = sheet_matrix[row_index - 1]
            if _is_empty_row(row):
                continue
            parsed_row, warning = _parse_ai_suggested_detail_row(
                row,
                row_index=row_index,
                column_mapping=column_mapping,
            )
            if warning:
                warnings.append(warning)
            if parsed_row is None:
                continue

            _append_duplicate_item_warning(
                warnings,
                seen_item_rows=seen_item_rows,
                package_id=parsed_row.package_id,
                item_id=parsed_row.item_id,
                row_index=parsed_row.row_index,
            )
            rows.append(parsed_row)
            if parsed_row.package_id not in seen_package_ids:
                seen_package_ids.add(parsed_row.package_id)
                package_ids.append(parsed_row.package_id)

    if first_resolved_mapping is not None:
        field_mapping = first_resolved_mapping
    if not rows and "未识别到有效明细行" not in errors:
        errors.append("未识别到有效明细行")

    return PackageSheetParseResult(
        parse_status="success" if rows and not errors else "failed",
        parse_mode="ai",
        ai_used=True,
        confidence=confidence,
        header_rows=header_rows,
        detail_ranges=detail_ranges,
        field_mapping=field_mapping,
        package_ids=package_ids,
        package_count=len(package_ids),
        detail_row_count=len(rows),
        rows=rows,
        warnings=warnings,
        errors=errors,
    )


async def _parse_package_items_with_ai(
    raw_values: list[list[Any]],
    *,
    sheet_name: str | None,
    db: AsyncSession | None,
    user_id: int | None,
    ai_client: PackageItemsAiClient | None,
    fallback_rule_result: PackageItemsPreviewResult | None,
    cache_context: PackageItemsAiParseCacheContext | None,
    parse_strategy: PackageParseStrategy,
    ai_parse_mode: PackageAiParseMode,
) -> PackageItemsPreviewResult:
    cache_key = _build_ai_parse_cache_key(
        cache_context,
        parse_strategy=parse_strategy,
        ai_parse_mode=ai_parse_mode,
    )
    if cache_key is not None:
        cached = get_package_items_ai_parse_cache(cache_key)
        if cached is not None:
            return cached.parse_result

    try:
        suggestion = await parse_package_sheet_with_ai(
            raw_values,
            sheet_name or "",
            {
                "db": db,
                "user_id": user_id,
                "ai_client": ai_client,
            },
        )
        ai_result = extract_package_items_by_ai_suggestion(raw_values, suggestion)
        preview_result = _as_preview_result(ai_result)
        if cache_key is not None and preview_result.parse_status == "success":
            set_package_items_ai_parse_cache(
                cache_key,
                suggestion=suggestion,
                parse_result=preview_result,
            )
        return preview_result
    except PackageAiParseError as exc:
        return _handle_ai_parse_failure(exc, fallback_rule_result=fallback_rule_result)


def _build_ai_parse_cache_key(
    cache_context: PackageItemsAiParseCacheContext | None,
    *,
    parse_strategy: PackageParseStrategy,
    ai_parse_mode: PackageAiParseMode,
) -> PackageItemsAiParseCacheKey | None:
    if cache_context is None:
        return None
    return PackageItemsAiParseCacheKey(
        feishu_source_id=cache_context.feishu_source_id,
        sheet_id=cache_context.sheet_id,
        sheet_revision_or_hash=cache_context.sheet_revision_or_hash,
        parse_strategy=parse_strategy,
        ai_parse_mode=ai_parse_mode,
        prompt_version=PROMPT_VERSION,
    )


def _handle_ai_parse_failure(
    exc: PackageAiParseError,
    *,
    fallback_rule_result: PackageItemsPreviewResult | None,
) -> PackageItemsPreviewResult:
    warning = f"AI 辅助解析失败：{exc}"
    if fallback_rule_result is not None and fallback_rule_result.rows:
        next_result = _as_preview_result(fallback_rule_result)
        next_result.ai_used = True
        next_result.warnings.append(f"{warning}，已回退为规则解析结果。")
        return next_result
    errors = []
    warnings: list[str] = []
    if fallback_rule_result is not None:
        errors.extend(fallback_rule_result.errors)
        warnings.extend(fallback_rule_result.warnings)
    errors.append(warning)
    return PackageItemsPreviewResult(
        parse_status="failed",
        parse_mode="ai",
        ai_used=True,
        warnings=warnings,
        errors=errors,
    )


def _as_preview_result(result: PackageSheetParseResult) -> PackageItemsPreviewResult:
    if isinstance(result, PackageItemsPreviewResult):
        return result
    return PackageItemsPreviewResult(
        parse_status=result.parse_status,
        parse_mode=result.parse_mode,
        ai_used=result.ai_used,
        cache_hit=result.cache_hit,
        confidence=result.confidence,
        header_rows=result.header_rows,
        detail_ranges=result.detail_ranges,
        field_mapping=result.field_mapping,
        package_ids=result.package_ids,
        package_count=result.package_count,
        detail_row_count=result.detail_row_count,
        rows=result.rows,
        warnings=list(result.warnings),
        errors=list(result.errors),
        detail_rows=[
            PackageItemsPreviewDetailRow(
                row_index=row.row_index,
                package_id=row.package_id,
                item_id=row.item_id,
                count=str(row.count),
            )
            for row in result.rows
        ],
    )


def _build_mode_warnings(
    parse_strategy: PackageParseStrategy,
    ai_parse_mode: PackageAiParseMode,
) -> list[str]:
    if parse_strategy == "ai":
        return ["AI 解析暂未接入主解析流程，本次已回退为规则解析。"]
    if ai_parse_mode == "enabled":
        return ["AI 辅助解析暂未接入主解析流程，本次仅使用规则解析。"]
    return []


def _detect_header(row: list[Any], *, row_index: int) -> _HeaderDetection | None:
    mapping: dict[str, int] = {}
    field_mapping: dict[str, str] = {}
    for column_index, value in enumerate(row):
        normalized = _normalize_header_text(value)
        if not normalized:
            continue
        for field_name, aliases in _FIELD_ALIASES.items():
            if field_name not in mapping and normalized in aliases:
                mapping[field_name] = column_index
                field_mapping[field_name] = _cell_text(value)
                break
    if not mapping:
        return None
    return _HeaderDetection(
        row_index=row_index,
        mapping=mapping,
        field_mapping=field_mapping,
    )


def _parse_detail_row(
    row: list[Any],
    *,
    row_index: int,
    header: _HeaderDetection,
) -> tuple[PackagePlanItemRow | None, str | None]:
    package_id, package_error = _parse_package_id(_get_cell(row, header.mapping["package_id"]))
    item_id, item_error = _parse_item_id(_get_cell(row, header.mapping["item_id"]))
    raw_count = _get_cell(row, header.mapping["count"])
    count, count_error = _parse_count(raw_count)
    if package_error:
        return None, f"跳过第 {row_index} 行：缺少礼包 ID 或道具 ID。"
    if item_error:
        if item_error == "道具 ID 为空。":
            return None, f"跳过第 {row_index} 行：缺少礼包 ID 或道具 ID。"
        return None, f"跳过第 {row_index} 行：{item_error}"
    if count_error:
        return None, f"跳过第 {row_index} 行：{count_error}"
    assert package_id is not None
    assert item_id is not None
    assert count is not None
    return (
        PackagePlanItemRow(
            package_id=package_id,
            item_id=item_id,
            count=count,
            row_index=row_index,
            raw_row=list(row),
        ),
        None,
    )


def _parse_ai_suggested_detail_row(
    row: list[Any],
    *,
    row_index: int,
    column_mapping: dict[str, int],
) -> tuple[PackagePlanItemRow | None, str | None]:
    package_id, package_error = _parse_package_id(_get_cell(row, column_mapping["package_id"]))
    item_id, item_error = _parse_item_id(_get_cell(row, column_mapping["item_id"]))
    raw_count = _get_cell(row, column_mapping["count"])
    count, count_error = _parse_count(raw_count)
    if package_error:
        return None, f"跳过第 {row_index} 行：缺少礼包 ID 或道具 ID。"
    if item_error:
        if item_error == "道具 ID 为空。":
            return None, f"跳过第 {row_index} 行：缺少礼包 ID 或道具 ID。"
        return None, f"跳过第 {row_index} 行：{item_error}"
    if count_error:
        return None, f"跳过第 {row_index} 行：{count_error}"
    assert package_id is not None
    assert item_id is not None
    assert count is not None
    return (
        PackagePlanItemRow(
            package_id=package_id,
            item_id=item_id,
            count=count,
            row_index=row_index,
            raw_row=list(row),
        ),
        None,
    )


def _build_field_mapping(
    first_field_mapping: dict[str, str],
    partial_headers: list[_HeaderDetection],
) -> PackageFieldMapping:
    values = dict(first_field_mapping)
    if not values and partial_headers:
        values.update(partial_headers[0].field_mapping)
    return PackageFieldMapping(
        package_id=values.get("package_id", ""),
        item_id=values.get("item_id", ""),
        count=values.get("count", ""),
    )


def _build_package_field_mapping(values: dict[str, str]) -> PackageFieldMapping:
    return PackageFieldMapping(
        package_id=values.get("package_id", ""),
        item_id=values.get("item_id", ""),
        count=values.get("count", ""),
    )


def _coerce_suggestion_confidence(suggestion: Any) -> float:
    value = _get_suggestion_value(suggestion, "confidence", 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _coerce_suggestion_warnings(suggestion: Any) -> list[str]:
    value = _get_suggestion_value(suggestion, "warnings", [])
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _coerce_suggestion_header_rows(suggestion: Any) -> list[int]:
    value = _get_suggestion_value(suggestion, "header_rows", [])
    if not isinstance(value, list):
        return []
    rows: list[int] = []
    for item in value:
        if isinstance(item, bool):
            continue
        try:
            rows.append(int(item))
        except (TypeError, ValueError):
            continue
    return rows


def _coerce_suggestion_detail_ranges(suggestion: Any) -> list[PackageDetailRange]:
    value = _get_suggestion_value(suggestion, "detail_ranges", [])
    if not isinstance(value, list):
        return []
    detail_ranges: list[PackageDetailRange] = []
    for item in value:
        item_dict = _model_or_mapping_to_dict(item)
        if not item_dict:
            continue
        detail_ranges.append(
            PackageDetailRange(
                header_row=_coerce_int(item_dict.get("header_row")),
                start_row=_coerce_int(item_dict.get("start_row")),
                end_row=_coerce_int(item_dict.get("end_row")),
            )
        )
    return detail_ranges


def _coerce_suggestion_field_mapping(suggestion: Any) -> dict[str, str]:
    value = _get_suggestion_value(suggestion, "field_mapping", {})
    value_dict = _model_or_mapping_to_dict(value)
    return {
        field_name: _cell_text(value_dict.get(field_name))
        for field_name in _REQUIRED_FIELDS
    }


def _get_suggestion_value(suggestion: Any, field_name: str, default: Any) -> Any:
    if isinstance(suggestion, dict):
        return suggestion.get(field_name, default)
    return getattr(suggestion, field_name, default)


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _model_or_mapping_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    if isinstance(value, dict):
        return value
    return {}


def _validate_ai_detail_range(
    detail_range: PackageDetailRange,
    *,
    row_count: int,
) -> list[str]:
    errors: list[str] = []
    if detail_range.header_row < 1 or detail_range.header_row > row_count:
        errors.append(f"AI 明细区域表头行越界：{detail_range.header_row}。")
    if detail_range.start_row < 1 or detail_range.end_row < 1:
        errors.append(
            f"AI 明细区域行号非法：{detail_range.start_row}-{detail_range.end_row}。"
        )
    if detail_range.start_row <= detail_range.header_row:
        errors.append("AI 明细区域 start_row 必须大于 header_row。")
    if detail_range.end_row < detail_range.start_row:
        errors.append("AI 明细区域 end_row 必须大于等于 start_row。")
    if detail_range.end_row > row_count:
        errors.append(f"AI 明细区域范围越界：{detail_range.start_row}-{detail_range.end_row}。")
    return errors


def _resolve_ai_field_columns(
    header_row: list[Any],
    *,
    header_row_index: int,
    suggested_field_mapping: dict[str, str],
) -> tuple[dict[str, int], PackageFieldMapping, list[str]]:
    column_mapping: dict[str, int] = {}
    resolved_field_mapping: dict[str, str] = {}
    errors: list[str] = []

    for field_name in _REQUIRED_FIELDS:
        column_index = _find_header_column(
            header_row,
            field_name=field_name,
            suggested_header=suggested_field_mapping.get(field_name, ""),
        )
        if column_index is None:
            errors.append(
                f"字段映射失败：第 {header_row_index} 行缺少 {_FIELD_LABELS[field_name]} 字段。"
            )
            continue
        column_mapping[field_name] = column_index
        resolved_field_mapping[field_name] = _cell_text(_get_cell(header_row, column_index))

    return column_mapping, _build_package_field_mapping(resolved_field_mapping), errors


def _find_header_column(
    header_row: list[Any],
    *,
    field_name: str,
    suggested_header: str,
) -> int | None:
    suggested_text = _cell_text(suggested_header)
    if suggested_text:
        for column_index, value in enumerate(header_row):
            if _cell_text(value) == suggested_text:
                return column_index
        normalized_suggested = _normalize_header_text(suggested_text)
        for column_index, value in enumerate(header_row):
            if _normalize_header_text(value) == normalized_suggested:
                return column_index

    aliases = _FIELD_ALIASES[field_name]
    for column_index, value in enumerate(header_row):
        if _normalize_header_text(value) in aliases:
            return column_index
    return None


def _build_parse_errors(
    complete_headers: list[_HeaderDetection],
    partial_headers: list[_HeaderDetection],
    rows: list[PackagePlanItemRow],
) -> list[str]:
    errors: list[str] = []
    if not complete_headers:
        if not partial_headers:
            return ["未识别到表头"]
        missing_fields = _collect_missing_fields(partial_headers)
        if "package_id" in missing_fields:
            errors.append("缺少礼包 ID 字段")
        if "item_id" in missing_fields:
            errors.append("缺少道具 ID 字段")
        if "count" in missing_fields:
            errors.append("缺少数量字段")
        return errors

    if not rows:
        errors.append("未识别到有效明细行")
    return errors


def _collect_missing_fields(partial_headers: list[_HeaderDetection]) -> set[str]:
    best_header = max(partial_headers, key=lambda header: len(header.mapping))
    return set(best_header.missing_fields)


def _has_unusually_few_rows(
    raw_values: list[list[Any]],
    complete_headers: list[_HeaderDetection],
    rows: list[PackagePlanItemRow],
) -> bool:
    if not complete_headers or not rows:
        return False
    non_empty_after_first_header = sum(
        1
        for row in raw_values[complete_headers[0].row_index :]
        if not _is_empty_row(row)
    )
    return non_empty_after_first_header >= 5 and len(rows) <= 1


def _estimate_rule_confidence(
    *,
    complete_headers: list[_HeaderDetection],
    detail_ranges: list[PackageDetailRange],
    package_ids: list[str],
    rows: list[PackagePlanItemRow],
) -> float:
    if not complete_headers:
        return 0.0

    confidence = 0.6
    if rows:
        confidence += 0.2
    if len(package_ids) > 1 or len(detail_ranges) > 1:
        confidence += 0.1
    if _has_exact_chinese_field_mapping(complete_headers[0].field_mapping):
        confidence += 0.1
    return min(round(confidence, 2), 1.0)


def _has_exact_chinese_field_mapping(field_mapping: dict[str, str]) -> bool:
    return all(
        _normalize_header_text(field_mapping.get(field_name)) == exact_header
        for field_name, exact_header in _EXACT_CHINESE_HEADERS.items()
    )


def _parse_package_id(value: Any) -> tuple[str | None, str | None]:
    if value is None or isinstance(value, bool):
        return None, "礼包 ID 为空。"
    text = _cell_text(value)
    if not text:
        return None, "礼包 ID 为空。"
    normalized = _try_normalize_integer_text(text)
    return normalized or text, None


def _parse_item_id(value: Any) -> tuple[str | None, str | None]:
    if value is None or isinstance(value, bool):
        return None, "道具 ID 为空。"
    text = _cell_text(value)
    if not text:
        return None, "道具 ID 为空。"
    normalized = _try_normalize_integer_text(text)
    if normalized is None:
        return None, "道具 ID 无法转换为整数。"
    return normalized, None


def _parse_count(value: Any) -> tuple[int | None, str | None]:
    if value is None or isinstance(value, bool):
        return None, "数量为空。"
    text = str(value).strip()
    if not text:
        return None, "数量为空。"
    normalized = _try_normalize_integer_text(text)
    if normalized is None:
        return None, "数量无法转换为整数。"
    return int(normalized), None


def _try_normalize_integer_text(text: str) -> str | None:
    if not text:
        return None
    if re.fullmatch(r"[+-]?\d+", text):
        return str(int(text))
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        return str(int(float(text)))
    return None


def _normalize_header_text(value: Any) -> str:
    return _cell_text(value).replace("_", "").replace("-", "").replace(" ", "").lower()


def _is_empty_row(row: list[Any]) -> bool:
    return not any(_cell_text(value) for value in row)


def _get_cell(row: list[Any], index: int) -> Any:
    return row[index] if index < len(row) else None


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
