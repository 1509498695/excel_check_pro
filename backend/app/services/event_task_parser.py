"""节日任务表规则预解析服务。"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.fixed_rules_schemas import (
    EventTaskAiParseMode,
    EventTaskFieldMapping,
    EventTaskParseStrategy,
    EventTaskPlanRow,
    EventTaskPreviewDetailRow,
    EventTaskPreviewRewardItem,
    EventTaskPreviewResult,
)
from backend.app.api.schemas import DataSource, VariableTag
from backend.app.loaders.feishu_reader import parse_feishu_sheet_url, preview_feishu_composite_variable
from backend.app.loaders.local_reader import load_variables_by_source
from backend.app.services.reward_parser import RewardItem, mergeDuplicateRewards, parseLootString


_FIELD_ALIASES: dict[str, set[str]] = {
    "task_group_id": {
        "任务组id",
        "任务组ID",
        "任务id",
        "任务ID",
        "任务组",
        "taskgroupid",
        "groupid",
        "intgroupid",
        "int_groupid",
        "int_id",
        "intid",
    },
    "task_id": {
        "int_task_id",
        "int_taskID",
        "taskid",
        "inttaskid",
        "int_taskid",
    },
    "day": {
        "天数",
        "day",
        "days",
        "intday",
        "int_day",
    },
    "task_desc": {
        "任务描述",
        "任务要求",
        "描述",
        "desc",
        "description",
        "strdesc",
        "str_desc",
    },
    "loot": {
        "奖励",
        "奖励内容",
        "loot",
        "reward",
        "strloot",
        "str_loot",
    },
}
_REQUIRED_FIELDS = ("task_group_id", "task_desc")
_LOOT_ITEM_ID_HEADERS = {"道具id", "itemid", "intitemid", "intitemid"}
_LOOT_NAME_HEADERS = {"道具名称", "itemname", "stritemname", "name"}
_LOOT_COUNT_HEADERS = {"数量", "个数", "count", "num"}
_LOOT_VALUE_TYPE_HEADERS = {"价值类型", "valuetype", "value_type"}


@dataclass(frozen=True)
class _HeaderDetection:
    row_index: int
    mapping: dict[str, int]
    loot_groups: list[_LootColumnGroup]

    @property
    def missing_fields(self) -> list[str]:
        return [field_name for field_name in _REQUIRED_FIELDS if field_name not in self.mapping]

    @property
    def is_complete(self) -> bool:
        return not self.missing_fields


@dataclass(frozen=True)
class _ConfigTaskRow:
    config_key: str
    task_group_id: str
    task_id: str | None
    task_desc: str
    loot: str | None
    row_index: int


@dataclass(frozen=True)
class _LootColumnGroup:
    item_id_index: int
    count_index: int
    name_index: int | None = None
    value_type_index: int | None = None


async def preview_event_tasks_from_feishu(
    source: DataSource,
    *,
    sheet_id: str,
    config_source: DataSource | None = None,
    config_variable: VariableTag | None = None,
    parse_strategy: EventTaskParseStrategy = "group_desc",
    ai_parse_mode: EventTaskAiParseMode = "auto",
    key_delimiter: str = "_",
    fallback_match_field: str = "INT_TaskID",
    db: AsyncSession,
    project_id: int,
    event_task_field_mapping: EventTaskFieldMapping | dict[str, Any] | None = None,
) -> EventTaskPreviewResult:
    """读取飞书 Sheet 显示值并执行节日任务解析与配置变量轻量匹配。"""
    del parse_strategy, ai_parse_mode
    from backend.app.integrations.feishu_client import read_sheet_values

    locator = parse_feishu_sheet_url(source.pathOrUrl or source.url or source.path or "")
    table = await read_sheet_values(
        db,
        project_id,
        locator,
        sheet_id=sheet_id,
        value_render_option="FormattedValue",
    )
    result = parse_feishu_event_task_sheet(
        table.raw_values,
        event_task_field_mapping=event_task_field_mapping,
    )
    result.raw_sheet_name = table.sheet_title
    result.raw_values = table.raw_values
    if result.parse_status != "success":
        return result

    if config_source is None or config_variable is None:
        return result

    config_frame = await load_event_task_config_frame(
        config_source,
        config_variable,
        db=db,
        project_id=project_id,
    )
    config_rows, config_warnings = build_event_task_config_rows(
        config_frame,
        key_delimiter=key_delimiter or "_",
        fallback_match_field=fallback_match_field or "INT_TaskID",
    )
    result.warnings.extend(config_warnings)
    result.detail_rows = build_event_task_preview_rows(
        result.rows,
        config_rows,
        fallback_match_field=fallback_match_field or "INT_TaskID",
    )
    return result


def parseFeishuEventTaskSheet(
    sheetRows: list[list[Any]],
    eventTaskFieldMapping: EventTaskFieldMapping | dict[str, Any] | None = None,
) -> EventTaskPreviewResult:
    """兼容需求中的 camelCase 命名入口。"""

    return parse_feishu_event_task_sheet(
        sheetRows,
        event_task_field_mapping=eventTaskFieldMapping,
    )


def parse_feishu_event_task_sheet(
    sheet_rows: list[list[Any]],
    *,
    event_task_field_mapping: EventTaskFieldMapping | dict[str, Any] | None = None,
) -> EventTaskPreviewResult:
    """从飞书二维数组中解析节日任务宽表，保留原始 Sheet 行号。"""
    if not sheet_rows:
        return EventTaskPreviewResult(
            parse_status="failed",
            parse_mode="rule",
            ai_used=False,
            errors=["Sheet 为空"],
            total_rows=0,
        )

    warnings: list[str] = []
    rows: list[EventTaskPlanRow] = []
    task_group_ids: list[str] = []
    seen_task_group_ids: set[str] = set()
    active_header: _HeaderDetection | None = None
    partial_headers: list[_HeaderDetection] = []
    reward_group_count = 0
    manual_header, manual_header_errors = _detect_manual_header(
        sheet_rows,
        event_task_field_mapping,
    )
    if manual_header_errors:
        return EventTaskPreviewResult(
            parse_status="failed",
            parse_mode="rule",
            errors=manual_header_errors,
            total_rows=len(sheet_rows),
        )

    for row_offset, row in enumerate(sheet_rows):
        row_index = row_offset + 1
        if manual_header is not None:
            header_detection = manual_header if row_index == manual_header.row_index else None
        else:
            header_detection = _detect_header(row, row_index=row_index)
        if header_detection is not None:
            if header_detection.is_complete:
                active_header = header_detection
                partial_headers = []
                reward_group_count = max(reward_group_count, len(header_detection.loot_groups))
            else:
                active_header = None
                partial_headers.append(header_detection)
            continue

        if active_header is None:
            continue
        if _is_empty_row(row):
            continue

        parsed_row = _parse_feishu_task_row(
            row,
            row_index=row_index,
            header=active_header,
        )
        rows.append(parsed_row)
        warnings.extend(parsed_row.warnings)
        if parsed_row.task_group_id and parsed_row.task_group_id not in seen_task_group_ids:
            seen_task_group_ids.add(parsed_row.task_group_id)
            task_group_ids.append(parsed_row.task_group_id)

    if not rows:
        if partial_headers:
            missing = "、".join(partial_headers[0].missing_fields)
            return EventTaskPreviewResult(
                parse_status="failed",
                parse_mode="rule",
                warnings=warnings,
                errors=[f"任务表头缺少字段：{missing}"],
                total_rows=len(sheet_rows),
                reward_group_count=reward_group_count,
            )
        return EventTaskPreviewResult(
            parse_status="failed",
            parse_mode="rule",
            warnings=warnings,
            errors=["未识别到任务明细"],
            total_rows=len(sheet_rows),
            reward_group_count=reward_group_count,
        )

    return EventTaskPreviewResult(
        parse_status="success",
        parse_mode="rule",
        ai_used=False,
        task_group_ids=task_group_ids,
        total_rows=len(sheet_rows),
        parsed_rows=len(rows),
        detail_row_count=len(rows),
        reward_group_count=reward_group_count,
        rows=rows,
        detail_rows=[_build_preview_detail_row(row) for row in rows],
        warnings=warnings,
    )


def parse_event_task_sheet(raw_values: list[list[Any]]) -> EventTaskPreviewResult:
    """兼容旧入口：从二维数组中扫描节日任务明细区域。"""

    return parse_feishu_event_task_sheet(raw_values)


async def load_event_task_config_frame(
    source: DataSource,
    variable: VariableTag,
    *,
    db: AsyncSession,
    project_id: int,
) -> pd.DataFrame:
    """加载 EventTask 组合变量供预览匹配使用。"""
    if source.type == "feishu":
        preview = await preview_feishu_composite_variable(
            source,
            sheet_name=variable.sheet,
            columns=variable.columns or [],
            key_column=variable.key_column or "",
            append_index_to_key=variable.append_index_to_key,
            db=db,
            project_id=project_id,
        )
        rows: list[dict[str, Any]] = []
        for index, (config_key, mapping) in enumerate(preview.get("mapping", {}).items()):
            rows.append(
                {
                    "__key__": config_key,
                    **dict(mapping),
                    "_row_index": index + 2,
                }
            )
        return pd.DataFrame(rows, dtype=object)

    loaded = load_variables_by_source(source, [variable])
    frame = loaded.get(variable.tag)
    if frame is None:
        raise ValueError(f"未能加载任务配置组合变量：{variable.tag}")
    return frame


def build_event_task_config_rows(
    frame: pd.DataFrame,
    *,
    key_delimiter: str = "_",
    fallback_match_field: str = "INT_TaskID",
) -> tuple[list[_ConfigTaskRow], list[str]]:
    """从 EventTask 组合变量行中抽取任务匹配字段。"""
    required_fields = ["INT_ID", fallback_match_field, "STR_Desc", "STR_Loot"]
    missing_fields = [field for field in required_fields if field not in frame.columns]
    if missing_fields:
        missing_text = "、".join(missing_fields)
        raise ValueError(f"任务配置组合变量缺少字段：{missing_text}")

    warnings: list[str] = []
    rows: list[_ConfigTaskRow] = []
    for index, row in frame.iterrows():
        config_key = _stringify(row.get("__key__")) or _stringify(row.get("INT_ID")) or ""
        task_group_id = _extract_task_group_id(
            config_key=config_key,
            fallback_value=row.get("INT_ID"),
            key_delimiter=key_delimiter,
        )
        task_desc = _stringify(row.get("STR_Desc")) or ""
        if not task_group_id or not task_desc:
            continue
        task_id = _normalize_id_text(row.get(fallback_match_field))
        row_index = int(row.get("_row_index", index + 2))
        rows.append(
            _ConfigTaskRow(
                config_key=config_key or f"{task_group_id}_{row_index}",
                task_group_id=task_group_id,
                task_id=task_id,
                task_desc=task_desc,
                loot=_stringify(row.get("STR_Loot")),
                row_index=row_index,
            )
        )

    seen_config_keys: dict[tuple[str, str, str], int] = {}
    for config_row in rows:
        if not config_row.task_id:
            continue
        key = (
            config_row.task_group_id,
            config_row.task_id,
            _normalize_desc(config_row.task_desc),
        )
        previous_row = seen_config_keys.get(key)
        if previous_row is not None:
            warnings.append(
                f"任务配置重复：任务组 {config_row.task_group_id} 的任务 {config_row.task_id} "
                f"描述 {config_row.task_desc} 在第 {previous_row} 行和第 {config_row.row_index} 行重复。"
            )
        else:
            seen_config_keys[key] = config_row.row_index
    return rows, warnings


def build_event_task_preview_rows(
    task_rows: list[EventTaskPlanRow],
    config_rows: list[_ConfigTaskRow],
    *,
    fallback_match_field: str = "INT_TaskID",
) -> list[EventTaskPreviewDetailRow]:
    """构造任务预览匹配结果。"""
    del fallback_match_field
    by_group_desc: dict[tuple[str, str], list[_ConfigTaskRow]] = {}
    by_task_id: dict[str, list[_ConfigTaskRow]] = {}
    for config_row in config_rows:
        by_group_desc.setdefault(
            (config_row.task_group_id, _normalize_desc(config_row.task_desc)),
            [],
        ).append(config_row)
        if config_row.task_id:
            by_task_id.setdefault(config_row.task_id, []).append(config_row)

    preview_rows: list[EventTaskPreviewDetailRow] = []
    for task_row in task_rows:
        match_type = "unmatched"
        matched_config: _ConfigTaskRow | None = None
        candidates = by_group_desc.get(
            (task_row.task_group_id, _normalize_desc(task_row.task_desc)),
            [],
        )
        if candidates:
            matched_config = candidates[0]
            match_type = "group_desc"
        elif task_row.task_id:
            fallback_candidates = by_task_id.get(task_row.task_id, [])
            if fallback_candidates:
                matched_config = fallback_candidates[0]
                match_type = "task_id"

        preview_rows.append(
            EventTaskPreviewDetailRow(
                row_index=task_row.row_index,
                task_group_id=task_row.task_group_id,
                task_id=task_row.task_id,
                day=task_row.day,
                task_desc=task_row.task_desc,
                loot=task_row.loot,
                rewards=list(task_row.rewards),
                warnings=list(task_row.warnings),
                config_key=matched_config.config_key if matched_config else None,
                config_task_desc=matched_config.task_desc if matched_config else None,
                config_task_id=matched_config.task_id if matched_config else None,
                config_loot=matched_config.loot if matched_config else None,
                match_type=match_type,
                match_status="matched" if match_type != "unmatched" else "missing_config",
            )
        )
    return preview_rows


def _detect_manual_header(
    sheet_rows: list[list[Any]],
    raw_mapping: EventTaskFieldMapping | dict[str, Any] | None,
) -> tuple[_HeaderDetection | None, list[str]]:
    if raw_mapping is None:
        return None, []
    mapping = (
        raw_mapping
        if isinstance(raw_mapping, EventTaskFieldMapping)
        else EventTaskFieldMapping.model_validate(raw_mapping)
    )
    if mapping.header_row_index is None:
        return None, []
    if mapping.header_row_index < 1 or mapping.header_row_index > len(sheet_rows):
        return None, [f"人工字段映射表头行越界：{mapping.header_row_index}。"]

    header_row = sheet_rows[mapping.header_row_index - 1]
    column_mapping: dict[str, int] = {}
    for field_name in ("task_group_id", "task_id", "day", "task_desc", "loot"):
        header_text = getattr(mapping, field_name)
        if not header_text:
            continue
        column_index = _find_header_column_by_text(header_row, header_text)
        if column_index is not None:
            column_mapping[field_name] = column_index

    loot_groups: list[_LootColumnGroup] = []
    for group in mapping.loot_groups:
        item_id_index = _find_header_column_by_text(header_row, group.item_id)
        count_index = _find_header_column_by_text(header_row, group.count)
        if item_id_index is None or count_index is None:
            continue
        name_index = _find_header_column_by_text(header_row, group.name) if group.name else None
        value_type_index = (
            _find_header_column_by_text(header_row, group.value_type)
            if group.value_type
            else None
        )
        loot_groups.append(
            _LootColumnGroup(
                item_id_index=item_id_index,
                count_index=count_index,
                name_index=name_index,
                value_type_index=value_type_index,
            )
        )

    return (
        _HeaderDetection(
            row_index=mapping.header_row_index,
            mapping=column_mapping,
            loot_groups=loot_groups,
        ),
        [],
    )


def _find_header_column_by_text(row: list[Any], header_text: str | None) -> int | None:
    expected = _stringify(header_text)
    if expected is None:
        return None
    for index, value in enumerate(row):
        if _stringify(value) == expected:
            return index
    normalized_expected = _normalize_header(expected)
    for index, value in enumerate(row):
        if _normalize_header(value) == normalized_expected:
            return index
    return None


def _detect_header(row: list[Any], *, row_index: int) -> _HeaderDetection | None:
    mapping: dict[str, int] = {}
    for index, cell in enumerate(row):
        normalized_header = _normalize_header(cell)
        if not normalized_header:
            continue
        for field_name, aliases in _FIELD_ALIASES.items():
            if field_name in mapping:
                continue
            if normalized_header in {_normalize_header(alias) for alias in aliases}:
                mapping[field_name] = index
                break
    if not mapping:
        return None
    return _HeaderDetection(
        row_index=row_index,
        mapping=mapping,
        loot_groups=_detect_loot_column_groups(row),
    )


def _parse_feishu_task_row(
    row: list[Any],
    *,
    row_index: int,
    header: _HeaderDetection,
) -> EventTaskPlanRow:
    def _value(field_name: str) -> Any:
        column_index = header.mapping.get(field_name)
        if column_index is None or column_index >= len(row):
            return None
        return row[column_index]

    warnings: list[str] = []
    task_group_id = _normalize_id_text(_value("task_group_id")) or ""
    task_id = _normalize_id_text(_value("task_id"))
    task_desc = _stringify(_value("task_desc")) or ""
    day, day_warning = _normalize_optional_int(_value("day"), "天数")
    if day_warning:
        warnings.append(f"第 {row_index} 行{day_warning}")
    if not task_group_id:
        warnings.append(f"第 {row_index} 行任务组 ID 为空。")
    if not task_desc:
        warnings.append(f"第 {row_index} 行任务描述为空。")

    rewards, reward_warnings = _build_reward_items(row, row_index, header.loot_groups)
    warnings.extend(reward_warnings)
    raw_loot = _stringify(_value("loot"))
    if rewards:
        loot = _build_loot_from_rewards(rewards)
    elif raw_loot:
        loot_parse_result = parseLootString(raw_loot, field_label=f"第 {row_index} 行 STR_Loot")
        rewards = [
            _to_event_task_reward_item(reward)
            for reward in loot_parse_result.rewards
        ]
        warnings.extend(
            issue.message
            for issue in [*loot_parse_result.warnings, *loot_parse_result.errors]
        )
        loot = raw_loot
    else:
        loot = None

    return EventTaskPlanRow(
        row_index=row_index,
        task_group_id=task_group_id,
        task_id=task_id,
        day=day,
        task_desc=task_desc,
        loot=loot,
        rewards=rewards,
        warnings=warnings,
        raw_row=list(row),
    )


def _build_preview_detail_row(row: EventTaskPlanRow) -> EventTaskPreviewDetailRow:
    return EventTaskPreviewDetailRow(
        row_index=row.row_index,
        task_group_id=row.task_group_id,
        task_id=row.task_id,
        day=row.day,
        task_desc=row.task_desc,
        loot=row.loot,
        rewards=list(row.rewards),
        warnings=list(row.warnings),
    )


def _parse_task_row(
    row: list[Any],
    *,
    row_index: int,
    header: _HeaderDetection,
) -> tuple[EventTaskPlanRow | None, str | None]:
    def _value(field_name: str) -> Any:
        column_index = header.mapping.get(field_name)
        if column_index is None or column_index >= len(row):
            return None
        return row[column_index]

    task_group_id = _normalize_id_text(_value("task_group_id"))
    task_id = _normalize_id_text(_value("task_id"))
    task_desc = _stringify(_value("task_desc")) or ""
    loot = _stringify(_value("loot")) or _build_loot_value(row, header.loot_groups)
    if not task_group_id or not task_desc:
        return None, f"跳过第 {row_index} 行：缺少任务组 ID 或任务描述。"
    return (
        EventTaskPlanRow(
            row_index=row_index,
            task_group_id=task_group_id,
            task_id=task_id,
            task_desc=task_desc,
            loot=loot,
            raw_row=list(row),
        ),
        None,
    )


def _detect_loot_column_groups(row: list[Any]) -> list[_LootColumnGroup]:
    groups: list[_LootColumnGroup] = []
    normalized_headers = [_normalize_header(cell) for cell in row]
    for index, normalized_header in enumerate(normalized_headers):
        if normalized_header not in _LOOT_ITEM_ID_HEADERS:
            continue
        next_item_index = next(
            (
                next_index
                for next_index in range(index + 1, len(normalized_headers))
                if normalized_headers[next_index] in _LOOT_ITEM_ID_HEADERS
            ),
            len(normalized_headers),
        )
        count_index = next(
            (
                count_candidate
                for count_candidate in range(index + 1, next_item_index)
                if normalized_headers[count_candidate] in _LOOT_COUNT_HEADERS
            ),
            None,
        )
        if count_index is None:
            continue
        name_index = next(
            (
                name_candidate
                for name_candidate in range(index + 1, next_item_index)
                if normalized_headers[name_candidate] in _LOOT_NAME_HEADERS
            ),
            None,
        )
        value_type_index = next(
            (
                value_type_candidate
                for value_type_candidate in range(index + 1, next_item_index)
                if normalized_headers[value_type_candidate] in _LOOT_VALUE_TYPE_HEADERS
            ),
            None,
        )
        groups.append(
            _LootColumnGroup(
                item_id_index=index,
                count_index=count_index,
                name_index=name_index,
                value_type_index=value_type_index,
            )
        )
    return groups


def _build_reward_items(
    row: list[Any],
    row_index: int,
    loot_groups: list[_LootColumnGroup],
) -> tuple[list[EventTaskPreviewRewardItem], list[str]]:
    rewards: list[RewardItem] = []
    warnings: list[str] = []
    for loot_group in loot_groups:
        raw_item_id = _row_value(row, loot_group.item_id_index)
        if _stringify(raw_item_id) is None:
            continue

        item_id, item_id_warning = _normalize_optional_int(raw_item_id, "道具ID")
        if item_id_warning or item_id is None:
            warnings.append(f"第 {row_index} 行{item_id_warning or '道具ID 必须是整数。'}")
            continue

        raw_count = _row_value(row, loot_group.count_index)
        if _stringify(raw_count) is None:
            warnings.append(f"第 {row_index} 行道具ID {item_id} 不为空但数量为空。")
            continue

        count, count_warning = _normalize_optional_int(raw_count, "数量")
        if count_warning or count is None:
            warnings.append(f"第 {row_index} 行道具ID {item_id} 的数量不是数字。")
            continue

        name = (
            _stringify(_row_value(row, loot_group.name_index))
            if loot_group.name_index is not None
            else None
        )
        rewards.append(
            RewardItem(
                type="item",
                item_id=item_id,
                count=count,
                name=name,
            )
        )

    merge_result = mergeDuplicateRewards(rewards)
    for duplicate_warning in merge_result.duplicate_warnings:
        warnings.append(f"第 {row_index} 行{duplicate_warning.message}")
    return (
        [_to_event_task_reward_item(reward) for reward in merge_result.rewards],
        warnings,
    )


def _to_event_task_reward_item(reward: RewardItem) -> EventTaskPreviewRewardItem:
    return EventTaskPreviewRewardItem(
        type=reward.type or "item",
        item_id=reward.item_id,
        itemId=reward.item_id,
        count=reward.count,
        name=reward.name,
    )


def _build_loot_from_rewards(rewards: list[EventTaskPreviewRewardItem]) -> str | None:
    if not rewards:
        return None
    return ",".join(f"{{item,{reward.item_id},{reward.count}}}" for reward in rewards)


def _build_loot_value(row: list[Any], loot_groups: list[_LootColumnGroup]) -> str | None:
    if not loot_groups:
        return None
    tokens: list[str] = []
    for loot_group in loot_groups:
        item_id = _normalize_id_text(_row_value(row, loot_group.item_id_index))
        count = _normalize_id_text(_row_value(row, loot_group.count_index))
        if item_id is None and count is None:
            continue
        if item_id is None or count is None:
            continue
        tokens.append(f"{{item,{item_id},{count}}}")
    if not tokens:
        return None
    return ",".join(tokens)


def _row_value(row: list[Any], index: int) -> Any:
    return row[index] if index < len(row) else None


def _extract_task_group_id(
    *,
    config_key: str,
    fallback_value: Any,
    key_delimiter: str,
) -> str:
    normalized_key = config_key.strip()
    if normalized_key and key_delimiter and key_delimiter in normalized_key:
        return normalized_key.split(key_delimiter, 1)[0].strip()
    return _normalize_id_text(fallback_value) or normalized_key


def _normalize_optional_int(value: Any, field_label: str) -> tuple[int | None, str | None]:
    if value is None or isinstance(value, bool):
        return None, None if value is None else f"{field_label} 必须是整数。"
    text = str(value).strip()
    if not text:
        return None, None
    if re.fullmatch(r"[+-]?\d+", text):
        return int(text), None
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        return int(float(text)), None
    return None, f"{field_label} 必须是整数。"


def _normalize_header(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[\s_]+", "", str(value).strip()).lower()


def _normalize_desc(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def _normalize_id_text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"[+-]?\d+", text):
        return str(int(text))
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        return str(int(float(text)))
    return text


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_empty_row(row: list[Any]) -> bool:
    return all(_stringify(value) is None for value in row)
