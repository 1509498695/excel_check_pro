"""EventTask 奖励一致性校验核心逻辑。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any, Literal

from backend.app.services.reward_parser import (
    RewardCountMismatch,
    RewardItem,
    RewardIssue,
    compareRewardSets,
    mergeDuplicateRewards,
)


EventTaskRewardMatchStrategy = Literal[
    "groupId_desc",
    "groupId_taskId",
    "groupId_desc_then_taskId",
]
EventTaskRewardStatus = Literal["pass", "fail"]

_SUPPORTED_MATCH_STRATEGIES: set[str] = {
    "groupId_desc",
    "groupId_taskId",
    "groupId_desc_then_taskId",
}
_DUPLICATE_WARNING_TYPES = {"duplicate_reward", "duplicate_type_mismatch"}


@dataclass(frozen=True)
class EventTaskRewardValidationTaskResult:
    """单条飞书节日任务与 EventTask 组合变量任务的奖励校验结果。"""

    task_group_id: str
    task_desc: str
    feishu_row_index: int | None
    variable_key: str | None
    variable_task_id: str | None
    match_strategy: str
    status: EventTaskRewardStatus
    expected_rewards: list[RewardItem]
    actual_rewards: list[RewardItem]
    missing_rewards: list[RewardItem]
    extra_rewards: list[RewardItem]
    count_mismatches: list[RewardCountMismatch]
    duplicate_warnings: list[str]
    parse_warnings: list[str]
    error_message: str | None = None

    @property
    def taskGroupId(self) -> str:
        return self.task_group_id

    @property
    def taskDesc(self) -> str:
        return self.task_desc

    @property
    def feishuRowIndex(self) -> int | None:
        return self.feishu_row_index

    @property
    def variableKey(self) -> str | None:
        return self.variable_key

    @property
    def variableTaskId(self) -> str | None:
        return self.variable_task_id

    @property
    def matchStrategy(self) -> str:
        return self.match_strategy

    @property
    def expectedRewards(self) -> list[RewardItem]:
        return self.expected_rewards

    @property
    def actualRewards(self) -> list[RewardItem]:
        return self.actual_rewards

    @property
    def missingRewards(self) -> list[RewardItem]:
        return self.missing_rewards

    @property
    def extraRewards(self) -> list[RewardItem]:
        return self.extra_rewards

    @property
    def countMismatches(self) -> list[RewardCountMismatch]:
        return self.count_mismatches

    @property
    def duplicateWarnings(self) -> list[str]:
        return self.duplicate_warnings

    @property
    def parseWarnings(self) -> list[str]:
        return self.parse_warnings

    @property
    def errorMessage(self) -> str | None:
        return self.error_message


@dataclass(frozen=True)
class EventTaskExtraVariableTask:
    """EventTask 组合变量中存在，但飞书侧没有匹配到的任务。"""

    task_group_id: str
    task_desc: str
    variable_key: str
    variable_task_id: str | None
    actual_rewards: list[RewardItem]
    parse_warnings: list[str]

    @property
    def taskGroupId(self) -> str:
        return self.task_group_id

    @property
    def taskDesc(self) -> str:
        return self.task_desc

    @property
    def variableKey(self) -> str:
        return self.variable_key

    @property
    def variableTaskId(self) -> str | None:
        return self.variable_task_id

    @property
    def actualRewards(self) -> list[RewardItem]:
        return self.actual_rewards

    @property
    def parseWarnings(self) -> list[str]:
        return self.parse_warnings


@dataclass(frozen=True)
class EventTaskRewardValidationSummary:
    """节日任务奖励校验汇总。"""

    total: int
    pass_count: int
    fail_count: int
    unmatched_count: int
    warning_count: int
    results: list[EventTaskRewardValidationTaskResult]
    extra_variable_tasks: list[EventTaskExtraVariableTask]

    @property
    def passCount(self) -> int:
        return self.pass_count

    @property
    def failCount(self) -> int:
        return self.fail_count

    @property
    def unmatchedCount(self) -> int:
        return self.unmatched_count

    @property
    def warningCount(self) -> int:
        return self.warning_count

    @property
    def extraVariableTasks(self) -> list[EventTaskExtraVariableTask]:
        return self.extra_variable_tasks


@dataclass(frozen=True)
class _FeishuTask:
    task_group_id: str
    task_id: str | None
    task_desc: str
    row_index: int | None
    rewards: Any
    warnings: list[str]


@dataclass(frozen=True)
class _VariableTask:
    task_group_id: str
    task_id: str | None
    desc: str
    variable_key: str
    rewards: Any
    warnings: list[str]


def validateEventTaskRewards(payload: Mapping[str, Any]) -> EventTaskRewardValidationSummary:
    """兼容需求中的 camelCase dict 入参。"""

    if not isinstance(payload, Mapping):
        raise TypeError("validateEventTaskRewards 入参必须是 mapping。")
    return validate_event_task_rewards(
        feishu_tasks=_read_mapping_value(payload, "feishuTasks", "feishu_tasks") or [],
        variable_tasks=_read_mapping_value(payload, "variableTasks", "variable_tasks") or [],
        match_strategy=(
            _read_mapping_value(payload, "matchStrategy", "match_strategy")
            or "groupId_desc_then_taskId"
        ),
        scope=_read_mapping_value(payload, "scope", "scope"),
    )


def validate_event_task_rewards(
    *,
    feishu_tasks: Any,
    variable_tasks: Any,
    match_strategy: str = "groupId_desc_then_taskId",
    scope: Any = None,
) -> EventTaskRewardValidationSummary:
    """校验飞书节日任务奖励与 EventTask 组合变量 STR_Loot 奖励是否一致。"""

    if match_strategy not in _SUPPORTED_MATCH_STRATEGIES:
        supported = "、".join(sorted(_SUPPORTED_MATCH_STRATEGIES))
        raise ValueError(f"不支持的节日任务匹配策略：{match_strategy}。支持：{supported}")

    scoped_group_ids = _normalize_scope(scope)
    normalized_feishu_tasks = [
        task
        for task in [_to_feishu_task(raw_task) for raw_task in _as_list(feishu_tasks)]
        if _is_in_scope(task.task_group_id, scoped_group_ids)
    ]
    normalized_variable_tasks = [
        task
        for task in [_to_variable_task(raw_task) for raw_task in _as_list(variable_tasks)]
        if _is_in_scope(task.task_group_id, scoped_group_ids)
    ]

    variable_index = _build_variable_match_index(normalized_variable_tasks)
    referenced_variable_keys: set[str] = set()
    results: list[EventTaskRewardValidationTaskResult] = []

    for feishu_task in normalized_feishu_tasks:
        result, referenced_keys = _validate_one_task(
            feishu_task,
            variable_index=variable_index,
            match_strategy=match_strategy,
        )
        referenced_variable_keys.update(referenced_keys)
        results.append(result)

    extra_variable_tasks = [
        _build_extra_variable_task(variable_task)
        for variable_task in normalized_variable_tasks
        if variable_task.variable_key not in referenced_variable_keys
    ]
    pass_count = sum(1 for result in results if result.status == "pass")
    fail_count = len(results) - pass_count
    unmatched_count = sum(
        1 for result in results if result.error_message == "未找到对应组合变量任务"
    )
    warning_count = sum(
        len(result.duplicate_warnings) + len(result.parse_warnings) for result in results
    ) + sum(len(task.parse_warnings) for task in extra_variable_tasks)

    return EventTaskRewardValidationSummary(
        total=len(results),
        pass_count=pass_count,
        fail_count=fail_count,
        unmatched_count=unmatched_count,
        warning_count=warning_count,
        results=results,
        extra_variable_tasks=extra_variable_tasks,
    )


def _validate_one_task(
    feishu_task: _FeishuTask,
    *,
    variable_index: dict[str, dict[tuple[str, str], list[_VariableTask]]],
    match_strategy: str,
) -> tuple[EventTaskRewardValidationTaskResult, set[str]]:
    parse_warnings = list(feishu_task.warnings)
    expected_rewards = _merged_rewards(feishu_task.rewards)

    if not feishu_task.task_group_id:
        parse_warnings.append("任务组ID为空，无法匹配组合变量任务。")
        return (
            _build_failed_result(
                feishu_task,
                match_strategy=match_strategy,
                expected_rewards=expected_rewards,
                parse_warnings=parse_warnings,
                error_message="未找到对应组合变量任务",
            ),
            set(),
        )

    if match_strategy == "groupId_desc" and not _normalize_desc(feishu_task.task_desc):
        parse_warnings.append("任务描述为空，无法按 groupId_desc 匹配组合变量任务。")
        return (
            _build_failed_result(
                feishu_task,
                match_strategy=match_strategy,
                expected_rewards=expected_rewards,
                parse_warnings=parse_warnings,
                error_message="未找到对应组合变量任务",
            ),
            set(),
        )

    candidates, used_strategy = _find_variable_candidates(
        feishu_task,
        variable_index=variable_index,
        match_strategy=match_strategy,
    )
    if not candidates:
        return (
            _build_failed_result(
                feishu_task,
                match_strategy=used_strategy,
                expected_rewards=expected_rewards,
                parse_warnings=parse_warnings,
                error_message="未找到对应组合变量任务",
            ),
            set(),
        )

    candidate_keys = {candidate.variable_key for candidate in candidates}
    if len(candidates) > 1:
        candidate_text = "、".join(candidate.variable_key for candidate in candidates)
        parse_warnings.append(f"匹配到多个组合变量任务：{candidate_text}。")
        return (
            _build_failed_result(
                feishu_task,
                match_strategy=used_strategy,
                expected_rewards=expected_rewards,
                parse_warnings=parse_warnings,
                error_message="匹配到多个组合变量任务",
            ),
            candidate_keys,
        )

    variable_task = candidates[0]
    actual_rewards = _merged_rewards(variable_task.rewards)
    compare_result = compareRewardSets(feishu_task.rewards, variable_task.rewards)
    duplicate_warnings = _issue_messages(
        issue for issue in compare_result.warnings if issue.error_type in _DUPLICATE_WARNING_TYPES
    )
    parse_warnings.extend(variable_task.warnings)
    parse_warnings.extend(
        _issue_messages(
            issue
            for issue in compare_result.warnings
            if issue.error_type not in _DUPLICATE_WARNING_TYPES
        )
    )

    return (
        EventTaskRewardValidationTaskResult(
            task_group_id=feishu_task.task_group_id,
            task_desc=feishu_task.task_desc,
            feishu_row_index=feishu_task.row_index,
            variable_key=variable_task.variable_key,
            variable_task_id=variable_task.task_id,
            match_strategy=used_strategy,
            status=compare_result.status,
            expected_rewards=expected_rewards,
            actual_rewards=actual_rewards,
            missing_rewards=list(compare_result.missing_rewards),
            extra_rewards=list(compare_result.extra_rewards),
            count_mismatches=list(compare_result.count_mismatches),
            duplicate_warnings=duplicate_warnings,
            parse_warnings=parse_warnings,
            error_message=None if compare_result.status == "pass" else "奖励不一致",
        ),
        candidate_keys,
    )


def _find_variable_candidates(
    feishu_task: _FeishuTask,
    *,
    variable_index: dict[str, dict[tuple[str, str], list[_VariableTask]]],
    match_strategy: str,
) -> tuple[list[_VariableTask], str]:
    desc_key = (feishu_task.task_group_id, _normalize_desc(feishu_task.task_desc))
    task_id_key = (feishu_task.task_group_id, feishu_task.task_id or "")
    if match_strategy == "groupId_desc":
        if not desc_key[1]:
            return [], "groupId_desc"
        return variable_index["group_desc"].get(desc_key, []), "groupId_desc"
    if match_strategy == "groupId_taskId":
        if not task_id_key[1]:
            return [], "groupId_taskId"
        return variable_index["group_task_id"].get(task_id_key, []), "groupId_taskId"

    if desc_key[1]:
        desc_candidates = variable_index["group_desc"].get(desc_key, [])
        if desc_candidates:
            return desc_candidates, "groupId_desc"
    if task_id_key[1]:
        return variable_index["group_task_id"].get(task_id_key, []), "groupId_taskId"
    return [], "groupId_taskId"


def _build_variable_match_index(
    variable_tasks: list[_VariableTask],
) -> dict[str, dict[tuple[str, str], list[_VariableTask]]]:
    group_desc: dict[tuple[str, str], list[_VariableTask]] = {}
    group_task_id: dict[tuple[str, str], list[_VariableTask]] = {}
    for task in variable_tasks:
        normalized_desc = _normalize_desc(task.desc)
        if task.task_group_id and normalized_desc:
            group_desc.setdefault((task.task_group_id, normalized_desc), []).append(task)
        if task.task_group_id and task.task_id:
            group_task_id.setdefault((task.task_group_id, task.task_id), []).append(task)
    return {"group_desc": group_desc, "group_task_id": group_task_id}


def _build_failed_result(
    feishu_task: _FeishuTask,
    *,
    match_strategy: str,
    expected_rewards: list[RewardItem],
    parse_warnings: list[str],
    error_message: str,
) -> EventTaskRewardValidationTaskResult:
    return EventTaskRewardValidationTaskResult(
        task_group_id=feishu_task.task_group_id,
        task_desc=feishu_task.task_desc,
        feishu_row_index=feishu_task.row_index,
        variable_key=None,
        variable_task_id=None,
        match_strategy=match_strategy,
        status="fail",
        expected_rewards=expected_rewards,
        actual_rewards=[],
        missing_rewards=list(expected_rewards) if error_message == "未找到对应组合变量任务" else [],
        extra_rewards=[],
        count_mismatches=[],
        duplicate_warnings=[],
        parse_warnings=parse_warnings,
        error_message=error_message,
    )


def _build_extra_variable_task(variable_task: _VariableTask) -> EventTaskExtraVariableTask:
    return EventTaskExtraVariableTask(
        task_group_id=variable_task.task_group_id,
        task_desc=variable_task.desc,
        variable_key=variable_task.variable_key,
        variable_task_id=variable_task.task_id,
        actual_rewards=_merged_rewards(variable_task.rewards),
        parse_warnings=list(variable_task.warnings),
    )


def _merged_rewards(rewards: Any) -> list[RewardItem]:
    return list(mergeDuplicateRewards(rewards).rewards)


def _to_feishu_task(raw_task: Any) -> _FeishuTask:
    return _FeishuTask(
        task_group_id=_normalize_id_text(_read_value(raw_task, "task_group_id", "taskGroupId")) or "",
        task_id=_normalize_id_text(_read_value(raw_task, "task_id", "taskId")),
        task_desc=_stringify(_read_value(raw_task, "task_desc", "desc")) or "",
        row_index=_normalize_optional_int(_read_value(raw_task, "row_index", "rowIndex")),
        rewards=_read_value(raw_task, "rewards", "rewards") or [],
        warnings=_string_list(_read_value(raw_task, "warnings", "warnings")),
    )


def _to_variable_task(raw_task: Any) -> _VariableTask:
    return _VariableTask(
        task_group_id=_normalize_id_text(_read_value(raw_task, "task_group_id", "taskGroupId")) or "",
        task_id=_normalize_id_text(_read_value(raw_task, "task_id", "taskId")),
        desc=_stringify(_read_value(raw_task, "desc", "task_desc", "taskDesc")) or "",
        variable_key=_stringify(_read_value(raw_task, "variable_key", "variableKey")) or "",
        rewards=_read_value(raw_task, "rewards", "rewards") or [],
        warnings=_variable_warning_messages(_read_value(raw_task, "warnings", "warnings")),
    )


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (str, bytes)):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _read_mapping_value(mapping: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _read_value(value: Any, *names: str) -> Any:
    if isinstance(value, Mapping):
        return _read_mapping_value(value, *names)
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _variable_warning_messages(value: Any) -> list[str]:
    messages: list[str] = []
    for warning in _as_list(value):
        message = _read_value(warning, "message", "message")
        if message is not None:
            messages.append(str(message))
        elif warning is not None:
            messages.append(str(warning))
    return messages


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value) if item is not None]


def _issue_messages(issues: Any) -> list[str]:
    messages: list[str] = []
    for issue in issues:
        if isinstance(issue, RewardIssue):
            messages.append(issue.message)
        elif issue is not None:
            messages.append(str(issue))
    return messages


def _normalize_scope(scope: Any) -> set[str] | None:
    if scope is None or scope == "all":
        return None
    if isinstance(scope, Mapping):
        raw_ids = _read_mapping_value(scope, "taskGroupIds", "task_group_ids")
    else:
        raw_ids = scope
    if raw_ids is None:
        return None
    return {
        normalized
        for normalized in (_normalize_id_text(item) for item in _as_list(raw_ids))
        if normalized
    }


def _is_in_scope(task_group_id: str, scoped_group_ids: set[str] | None) -> bool:
    return scoped_group_ids is None or task_group_id in scoped_group_ids


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


def _normalize_optional_int(value: Any) -> int | None:
    normalized = _normalize_id_text(value)
    if normalized is None or not re.fullmatch(r"[+-]?\d+", normalized):
        return None
    return int(normalized)


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
