"""通用奖励解析与奖励集合比较工具。"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Literal

from backend.app.rules.domain.value import is_empty_value


_BRACED_TOKEN_PATTERN = re.compile(r"\{([^{}]*)\}")
_PERMITTED_OUTER_PATTERN = re.compile(r"^[\s,\[\]]*$")


@dataclass(frozen=True)
class RewardItem:
    """规范化后的奖励项。"""

    type: str | None
    item_id: int
    count: int
    name: str | None = None
    source: str | None = None

    @property
    def itemId(self) -> int:
        return self.item_id


@dataclass(frozen=True)
class RewardIssue:
    """奖励解析、规范化或比较过程中的问题。"""

    error_type: str
    message: str
    item_id: int | None = None
    raw_value: Any = None
    right_value: Any = None

    @property
    def itemId(self) -> int | None:
        return self.item_id


@dataclass(frozen=True)
class RewardParseResult:
    """奖励解析或规范化结果。"""

    rewards: list[RewardItem]
    warnings: list[RewardIssue]
    errors: list[RewardIssue]

    @property
    def duplicate_warnings(self) -> list[str]:
        return [
            issue.message
            for issue in self.warnings
            if issue.error_type in {"duplicate_reward", "duplicate_type_mismatch"}
        ]

    def as_count_map(self) -> dict[int, int]:
        result: dict[int, int] = {}
        for reward in self.rewards:
            result[reward.item_id] = result.get(reward.item_id, 0) + reward.count
        return result


@dataclass(frozen=True)
class RewardMergeResult:
    """奖励重复项合并结果。"""

    rewards: list[RewardItem]
    duplicate_warnings: list[RewardIssue]

    @property
    def duplicateWarnings(self) -> list[RewardIssue]:
        return self.duplicate_warnings


@dataclass(frozen=True)
class RewardCountMismatch:
    """同一奖励 ID 在两侧数量不一致。"""

    item_id: int
    expected_count: int
    actual_count: int

    @property
    def itemId(self) -> int:
        return self.item_id

    @property
    def expectedCount(self) -> int:
        return self.expected_count

    @property
    def actualCount(self) -> int:
        return self.actual_count


@dataclass(frozen=True)
class RewardCompareResult:
    """奖励集合无序比较结果。"""

    status: Literal["pass", "fail"]
    missing_rewards: list[RewardItem]
    extra_rewards: list[RewardItem]
    count_mismatches: list[RewardCountMismatch]
    warnings: list[RewardIssue]

    @property
    def missingRewards(self) -> list[RewardItem]:
        return self.missing_rewards

    @property
    def extraRewards(self) -> list[RewardItem]:
        return self.extra_rewards

    @property
    def countMismatches(self) -> list[RewardCountMismatch]:
        return self.count_mismatches


ParsedRewardItem = RewardItem
RewardParseIssue = RewardIssue


def parseLootString(
    value: Any,
    *,
    field_label: str = "STR_Loot",
    include_types: Iterable[str] = ("item", "res"),
    ignore_other_types: bool = False,
) -> RewardParseResult:
    """兼容需求中的 camelCase 命名入口。"""

    return parse_loot_string(
        value,
        field_label=field_label,
        include_types=include_types,
        ignore_other_types=ignore_other_types,
    )


def parse_loot_string(
    value: Any,
    *,
    field_label: str = "STR_Loot",
    include_types: Iterable[str] = ("item", "res"),
    ignore_other_types: bool = False,
) -> RewardParseResult:
    """解析 ``[{item,2087,1},{res,5,100}]`` 形式的奖励字符串。"""

    if is_empty_value(value):
        return RewardParseResult(
            rewards=[],
            warnings=[
                RewardIssue(
                    error_type="empty_reward",
                    message=f"{field_label} 为空。",
                    raw_value=value,
                    right_value=value,
                )
            ],
            errors=[],
        )

    text = str(value).strip()
    if _is_empty_reward_array(text):
        return RewardParseResult(rewards=[], warnings=[], errors=[])

    matches = list(_BRACED_TOKEN_PATTERN.finditer(text))
    if not matches:
        return RewardParseResult(
            rewards=[],
            warnings=[],
            errors=[
                RewardIssue(
                    error_type="reward_format_error",
                    message=f"{field_label} 格式错误：{text}",
                    raw_value=value,
                    right_value=value,
                )
            ],
        )

    errors: list[RewardIssue] = []
    outer_text = _BRACED_TOKEN_PATTERN.sub("", text)
    if not _PERMITTED_OUTER_PATTERN.fullmatch(outer_text):
        errors.append(
            RewardIssue(
                error_type="reward_format_error",
                message=f"{field_label} 格式错误：{text}",
                raw_value=value,
                right_value=value,
            )
        )

    allowed_types = {_normalize_type(item_type) for item_type in include_types}
    allowed_types.discard("")
    rewards: list[RewardItem] = []

    for match in matches:
        token = match.group(0)
        parts = [part.strip() for part in match.group(1).split(",")]
        if len(parts) != 3:
            errors.append(
                RewardIssue(
                    error_type="reward_format_error",
                    message=f"{field_label} 片段格式错误：{token}",
                    raw_value=token,
                    right_value=token,
                )
            )
            continue

        reward_type = _normalize_type(parts[0])
        if reward_type not in allowed_types:
            if ignore_other_types:
                continue
            errors.append(
                RewardIssue(
                    error_type="unsupported_reward_type",
                    message=f"{field_label} 不支持奖励类型：{parts[0] or '<空>'}",
                    raw_value=token,
                    right_value=token,
                )
            )
            continue

        item_id, item_error = _normalize_integer(parts[1], "奖励 ID")
        count, count_error = _normalize_integer(parts[2], "奖励数量")
        if item_error:
            errors.append(
                RewardIssue(
                    error_type="invalid_item_id",
                    message=f"{field_label} 片段 {token} 的{item_error}",
                    raw_value=parts[1],
                    right_value=parts[1],
                )
            )
            continue
        if count_error:
            errors.append(
                RewardIssue(
                    error_type="invalid_count",
                    message=f"{field_label} 片段 {token} 的{count_error}",
                    item_id=item_id,
                    raw_value=parts[2],
                    right_value=parts[2],
                )
            )
            continue

        assert item_id is not None
        assert count is not None
        rewards.append(RewardItem(type=reward_type, item_id=item_id, count=count))

    return RewardParseResult(rewards=rewards, warnings=[], errors=errors)


def normalizeRewards(
    rewards: Any,
    *,
    source: str | None = None,
    field_label: str = "奖励",
) -> RewardParseResult:
    """兼容需求中的 camelCase 命名入口。"""

    return normalize_rewards(rewards, source=source, field_label=field_label)


def normalize_rewards(
    rewards: Any,
    *,
    source: str | None = None,
    field_label: str = "奖励",
) -> RewardParseResult:
    """将不同来源的奖励数据规范成 ``RewardItem`` 列表。"""

    if rewards is None:
        return RewardParseResult(rewards=[], warnings=[], errors=[])
    if isinstance(rewards, RewardParseResult):
        return RewardParseResult(
            rewards=list(rewards.rewards),
            warnings=list(rewards.warnings),
            errors=list(rewards.errors),
        )
    if isinstance(rewards, RewardItem):
        rewards = [rewards]
    elif isinstance(rewards, (str, bytes)):
        return RewardParseResult(
            rewards=[],
            warnings=[
                RewardIssue(
                    error_type="invalid_reward_collection",
                    message=f"{field_label} 必须是奖励列表。",
                    raw_value=rewards,
                    right_value=rewards,
                )
            ],
            errors=[],
        )

    normalized: list[RewardItem] = []
    warnings: list[RewardIssue] = []

    try:
        iterable_rewards = list(rewards)
    except TypeError:
        return RewardParseResult(
            rewards=[],
            warnings=[
                RewardIssue(
                    error_type="invalid_reward_collection",
                    message=f"{field_label} 必须是奖励列表。",
                    raw_value=rewards,
                    right_value=rewards,
                )
            ],
            errors=[],
        )

    for index, raw_reward in enumerate(iterable_rewards, start=1):
        item_id_raw = _read_reward_value(raw_reward, "item_id", "itemId")
        count_raw = _read_reward_value(raw_reward, "count", "count")
        item_type = _read_reward_value(raw_reward, "type", "type")
        name = _read_reward_value(raw_reward, "name", "name")
        reward_source = _read_reward_value(raw_reward, "source", "source") or source

        if is_empty_value(item_id_raw):
            warnings.append(
                RewardIssue(
                    error_type="empty_item_id",
                    message=f"{field_label} 第 {index} 项奖励 ID 为空，已忽略。",
                    raw_value=raw_reward,
                    right_value=item_id_raw,
                )
            )
            continue

        item_id, item_error = _normalize_integer(item_id_raw, "奖励 ID")
        if item_error:
            warnings.append(
                RewardIssue(
                    error_type="invalid_item_id",
                    message=f"{field_label} 第 {index} 项的{item_error}，已忽略。",
                    raw_value=raw_reward,
                    right_value=item_id_raw,
                )
            )
            continue

        if is_empty_value(count_raw):
            warnings.append(
                RewardIssue(
                    error_type="empty_count",
                    message=f"{field_label} 第 {index} 项奖励数量为空，已忽略。",
                    item_id=item_id,
                    raw_value=raw_reward,
                    right_value=count_raw,
                )
            )
            continue

        count, count_error = _normalize_integer(count_raw, "奖励数量")
        if count_error:
            warnings.append(
                RewardIssue(
                    error_type="invalid_count",
                    message=f"{field_label} 第 {index} 项的{count_error}，已忽略。",
                    item_id=item_id,
                    raw_value=raw_reward,
                    right_value=count_raw,
                )
            )
            continue

        assert item_id is not None
        assert count is not None
        normalized.append(
            RewardItem(
                type=_normalize_optional_type(item_type),
                item_id=item_id,
                count=count,
                name=None if is_empty_value(name) else str(name),
                source=None if is_empty_value(reward_source) else str(reward_source),
            )
        )

    return RewardParseResult(rewards=normalized, warnings=warnings, errors=[])


def mergeDuplicateRewards(rewards: Any) -> RewardMergeResult:
    """兼容需求中的 camelCase 命名入口。"""

    return merge_duplicate_rewards(rewards)


def merge_duplicate_rewards(rewards: Any) -> RewardMergeResult:
    """按 ``item_id`` 合并同一集合内的重复奖励。"""

    normalized = normalize_rewards(rewards)
    merged_by_id: dict[int, RewardItem] = {}
    ordered_ids: list[int] = []
    duplicate_warnings: list[RewardIssue] = []

    for reward in normalized.rewards:
        existing = merged_by_id.get(reward.item_id)
        if existing is None:
            merged_by_id[reward.item_id] = reward
            ordered_ids.append(reward.item_id)
            continue

        duplicate_warnings.append(
            RewardIssue(
                error_type="duplicate_reward",
                message=f"奖励 ID {reward.item_id} 重复，数量已合并。",
                item_id=reward.item_id,
                raw_value=reward,
                right_value=existing,
            )
        )
        if existing.type != reward.type:
            duplicate_warnings.append(
                RewardIssue(
                    error_type="duplicate_type_mismatch",
                    message=(
                        f"奖励 ID {reward.item_id} 存在不同 type："
                        f"{existing.type or '<空>'} / {reward.type or '<空>'}，已按 itemId 合并。"
                    ),
                    item_id=reward.item_id,
                    raw_value=reward,
                    right_value=existing,
                )
            )

        merged_by_id[reward.item_id] = RewardItem(
            type=existing.type,
            item_id=existing.item_id,
            count=existing.count + reward.count,
            name=existing.name,
            source=existing.source,
        )

    return RewardMergeResult(
        rewards=[merged_by_id[item_id] for item_id in ordered_ids],
        duplicate_warnings=[*normalized.warnings, *duplicate_warnings],
    )


def compareRewardSets(expectedRewards: Any, actualRewards: Any) -> RewardCompareResult:
    """兼容需求中的 camelCase 命名入口。"""

    return compare_reward_sets(expectedRewards, actualRewards)


def compare_reward_sets(expected_rewards: Any, actual_rewards: Any) -> RewardCompareResult:
    """无序比较两组奖励，重复项会先按 ``item_id`` 合并。"""

    expected_normalized = normalize_rewards(expected_rewards, field_label="expectedRewards")
    actual_normalized = normalize_rewards(actual_rewards, field_label="actualRewards")
    expected_merged = merge_duplicate_rewards(expected_normalized.rewards)
    actual_merged = merge_duplicate_rewards(actual_normalized.rewards)

    expected_by_id = {reward.item_id: reward for reward in expected_merged.rewards}
    actual_by_id = {reward.item_id: reward for reward in actual_merged.rewards}

    missing_rewards = [
        reward for reward in expected_merged.rewards if reward.item_id not in actual_by_id
    ]
    extra_rewards = [reward for reward in actual_merged.rewards if reward.item_id not in expected_by_id]
    count_mismatches = [
        RewardCountMismatch(
            item_id=item_id,
            expected_count=expected_reward.count,
            actual_count=actual_by_id[item_id].count,
        )
        for item_id, expected_reward in expected_by_id.items()
        if item_id in actual_by_id and expected_reward.count != actual_by_id[item_id].count
    ]
    status: Literal["pass", "fail"] = (
        "pass" if not missing_rewards and not extra_rewards and not count_mismatches else "fail"
    )

    return RewardCompareResult(
        status=status,
        missing_rewards=missing_rewards,
        extra_rewards=extra_rewards,
        count_mismatches=count_mismatches,
        warnings=[
            *expected_normalized.warnings,
            *expected_normalized.errors,
            *actual_normalized.warnings,
            *actual_normalized.errors,
            *expected_merged.duplicate_warnings,
            *actual_merged.duplicate_warnings,
        ],
    )


def _is_empty_reward_array(text: str) -> bool:
    return bool(re.fullmatch(r"\[\s*\]", text))


def _normalize_type(value: Any) -> str:
    if is_empty_value(value):
        return ""
    return str(value).strip().lower()


def _normalize_optional_type(value: Any) -> str | None:
    normalized = _normalize_type(value)
    return normalized or None


def _normalize_integer(value: Any, field_label: str) -> tuple[int | None, str | None]:
    if is_empty_value(value):
        return None, f"{field_label} 为空"
    if isinstance(value, bool):
        return None, f"{field_label} 必须是整数"
    if isinstance(value, int):
        return value, None
    text = str(value).strip()
    if re.fullmatch(r"[+-]?\d+", text):
        return int(text), None
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        return int(float(text)), None
    return None, f"{field_label} 必须是整数"


def _read_reward_value(raw_reward: Any, snake_key: str, camel_key: str) -> Any:
    if isinstance(raw_reward, dict):
        if snake_key in raw_reward:
            return raw_reward[snake_key]
        return raw_reward.get(camel_key)
    if hasattr(raw_reward, snake_key):
        return getattr(raw_reward, snake_key)
    if hasattr(raw_reward, camel_key):
        return getattr(raw_reward, camel_key)
    return None
