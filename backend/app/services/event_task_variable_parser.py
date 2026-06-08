"""EventTask 组合变量解析工具。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any

from backend.app.rules.domain.value import is_empty_value
from backend.app.services.reward_parser import RewardItem, parseLootString


@dataclass(frozen=True)
class EventTaskVariableWarning:
    """EventTask 组合变量解析或索引构建过程中的警告。"""

    warning_type: str
    message: str
    variable_key: str | None = None
    field: str | None = None
    raw_value: Any = None
    index_key: str | None = None

    @property
    def warningType(self) -> str:
        return self.warning_type

    @property
    def variableKey(self) -> str | None:
        return self.variable_key

    @property
    def rawValue(self) -> Any:
        return self.raw_value

    @property
    def indexKey(self) -> str | None:
        return self.index_key


@dataclass(frozen=True)
class EventTaskVariableTask:
    """从 EventTask 组合变量中解析出的单个任务配置。"""

    task_group_id: str
    variable_key: str
    task_id: int | None
    title: str | None
    desc: str
    rewards: list[RewardItem]
    raw_loot: str | None
    warnings: list[EventTaskVariableWarning]
    sort_suffix: str | None = None

    @property
    def taskGroupId(self) -> str:
        return self.task_group_id

    @property
    def variableKey(self) -> str:
        return self.variable_key

    @property
    def taskId(self) -> int | None:
        return self.task_id

    @property
    def rawLoot(self) -> str | None:
        return self.raw_loot

    @property
    def sortSuffix(self) -> str | None:
        return self.sort_suffix


@dataclass(frozen=True)
class EventTaskVariableIndex:
    """EventTask 组合变量任务索引。"""

    by_group_id_and_desc: dict[str, EventTaskVariableTask]
    by_group_id_and_task_id: dict[str, EventTaskVariableTask]
    warnings: list[EventTaskVariableWarning]

    @property
    def byGroupIdAndDesc(self) -> dict[str, EventTaskVariableTask]:
        return self.by_group_id_and_desc

    @property
    def byGroupIdAndTaskId(self) -> dict[str, EventTaskVariableTask]:
        return self.by_group_id_and_task_id


def parseEventTaskVariables(variableData: Mapping[Any, Any]) -> list[EventTaskVariableTask]:
    """兼容需求中的 camelCase 命名入口。"""

    return parse_event_task_variables(variableData)


def parse_event_task_variables(variable_data: Mapping[Any, Any]) -> list[EventTaskVariableTask]:
    """解析 EventTask 组合变量 dict 数据。"""

    if not isinstance(variable_data, Mapping):
        raise TypeError("EventTask 组合变量数据必须是 mapping。")

    tasks: list[EventTaskVariableTask] = []
    for raw_key, raw_task in variable_data.items():
        variable_key = str(raw_key)
        task_group_id, sort_suffix, key_warnings = _parse_variable_key(variable_key)
        warnings = list(key_warnings)
        task_payload = raw_task if isinstance(raw_task, Mapping) else {}

        if not isinstance(raw_task, Mapping):
            warnings.append(
                EventTaskVariableWarning(
                    warning_type="invalid_variable_payload",
                    message=f"EventTask 组合变量 {variable_key} 的值不是对象，已按空对象解析。",
                    variable_key=variable_key,
                    raw_value=raw_task,
                )
            )

        task_id = _parse_task_id(task_payload.get("INT_TaskID"), variable_key, warnings)
        title = _stringify(task_payload.get("STR_Title"))
        desc = _stringify(task_payload.get("STR_Desc")) or ""
        if not desc:
            warnings.append(
                EventTaskVariableWarning(
                    warning_type="missing_desc",
                    message=f"EventTask 组合变量 {variable_key} 缺少 STR_Desc。",
                    variable_key=variable_key,
                    field="STR_Desc",
                    raw_value=task_payload.get("STR_Desc"),
                )
            )

        raw_loot = _stringify(task_payload.get("STR_Loot"))
        loot_result = parseLootString(raw_loot, field_label="STR_Loot")
        for issue in [*loot_result.warnings, *loot_result.errors]:
            warnings.append(
                EventTaskVariableWarning(
                    warning_type=f"loot_{issue.error_type}",
                    message=issue.message,
                    variable_key=variable_key,
                    field="STR_Loot",
                    raw_value=issue.raw_value,
                )
            )

        tasks.append(
            EventTaskVariableTask(
                task_group_id=task_group_id,
                variable_key=variable_key,
                task_id=task_id,
                title=title,
                desc=desc,
                rewards=list(loot_result.rewards),
                raw_loot=raw_loot,
                warnings=warnings,
                sort_suffix=sort_suffix,
            )
        )

    return tasks


def buildEventTaskVariableIndex(tasks: list[EventTaskVariableTask]) -> EventTaskVariableIndex:
    """兼容需求中的 camelCase 命名入口。"""

    return build_event_task_variable_index(tasks)


def build_event_task_variable_index(tasks: list[EventTaskVariableTask]) -> EventTaskVariableIndex:
    """构建 EventTask 组合变量任务索引，重复 key 保留第一条。"""

    by_group_id_and_desc: dict[str, EventTaskVariableTask] = {}
    by_group_id_and_task_id: dict[str, EventTaskVariableTask] = {}
    warnings: list[EventTaskVariableWarning] = []

    for task in tasks:
        if task.desc:
            desc_key = f"{task.task_group_id}::{task.desc}"
            if desc_key in by_group_id_and_desc:
                warnings.append(
                    EventTaskVariableWarning(
                        warning_type="duplicate_group_desc_index",
                        message=f"EventTask byGroupIdAndDesc 索引重复：{desc_key}。",
                        variable_key=task.variable_key,
                        index_key=desc_key,
                    )
                )
            else:
                by_group_id_and_desc[desc_key] = task

        if task.task_id is not None:
            task_id_key = f"{task.task_group_id}::{task.task_id}"
            if task_id_key in by_group_id_and_task_id:
                warnings.append(
                    EventTaskVariableWarning(
                        warning_type="duplicate_group_task_id_index",
                        message=f"EventTask byGroupIdAndTaskId 索引重复：{task_id_key}。",
                        variable_key=task.variable_key,
                        index_key=task_id_key,
                    )
                )
            else:
                by_group_id_and_task_id[task_id_key] = task

    return EventTaskVariableIndex(
        by_group_id_and_desc=by_group_id_and_desc,
        by_group_id_and_task_id=by_group_id_and_task_id,
        warnings=warnings,
    )


def _parse_variable_key(
    variable_key: str,
) -> tuple[str, str | None, list[EventTaskVariableWarning]]:
    if "_" not in variable_key:
        return (
            variable_key,
            None,
            [
                EventTaskVariableWarning(
                    warning_type="missing_key_delimiter",
                    message=f"EventTask 组合变量 key {variable_key} 不包含 '_'，已使用完整 key 作为任务组 ID。",
                    variable_key=variable_key,
                    raw_value=variable_key,
                )
            ],
        )

    task_group_id, sort_suffix = variable_key.split("_", 1)
    if task_group_id:
        return task_group_id, sort_suffix, []
    return (
        variable_key,
        sort_suffix,
        [
            EventTaskVariableWarning(
                warning_type="empty_task_group_id",
                message=f"EventTask 组合变量 key {variable_key} 的任务组 ID 为空，已使用完整 key。",
                variable_key=variable_key,
                raw_value=variable_key,
            )
        ],
    )


def _parse_task_id(
    value: Any,
    variable_key: str,
    warnings: list[EventTaskVariableWarning],
) -> int | None:
    if is_empty_value(value):
        warnings.append(
            EventTaskVariableWarning(
                warning_type="missing_task_id",
                message=f"EventTask 组合变量 {variable_key} 缺少 INT_TaskID。",
                variable_key=variable_key,
                field="INT_TaskID",
                raw_value=value,
            )
        )
        return None
    if isinstance(value, bool):
        warnings.append(_invalid_task_id_warning(variable_key, value))
        return None
    if isinstance(value, int):
        return value

    text = str(value).strip()
    if re.fullmatch(r"[+-]?\d+", text):
        return int(text)
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        return int(float(text))

    warnings.append(_invalid_task_id_warning(variable_key, value))
    return None


def _invalid_task_id_warning(variable_key: str, value: Any) -> EventTaskVariableWarning:
    return EventTaskVariableWarning(
        warning_type="invalid_task_id",
        message=f"EventTask 组合变量 {variable_key} 的 INT_TaskID 必须是整数。",
        variable_key=variable_key,
        field="INT_TaskID",
        raw_value=value,
    )


def _stringify(value: Any) -> str | None:
    if is_empty_value(value):
        return None
    return str(value).strip()
