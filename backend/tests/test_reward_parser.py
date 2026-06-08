from backend.app.services.reward_parser import (
    RewardItem,
    compareRewardSets,
    mergeDuplicateRewards,
    normalizeRewards,
    parseLootString,
)


def _triples(rewards: list[RewardItem]) -> list[tuple[str | None, int, int]]:
    return [(reward.type, reward.item_id, reward.count) for reward in rewards]


def test_parse_loot_string_parses_item_rewards() -> None:
    result = parseLootString("[{item,2087,1},{item,39,2}]")

    assert result.warnings == []
    assert result.errors == []
    assert _triples(result.rewards) == [("item", 2087, 1), ("item", 39, 2)]


def test_parse_loot_string_parses_res_rewards() -> None:
    result = parseLootString("[{res,5,100},{item,2087,3},{item,40,7}]")

    assert result.warnings == []
    assert result.errors == []
    assert _triples(result.rewards) == [
        ("res", 5, 100),
        ("item", 2087, 3),
        ("item", 40, 7),
    ]


def test_parse_loot_string_empty_value_returns_warning() -> None:
    result = parseLootString("")

    assert result.rewards == []
    assert result.errors == []
    assert [warning.error_type for warning in result.warnings] == ["empty_reward"]


def test_parse_loot_string_format_error_returns_error() -> None:
    result = parseLootString("[item,2087,1]")

    assert result.rewards == []
    assert result.warnings == []
    assert [error.error_type for error in result.errors] == ["reward_format_error"]


def test_normalize_rewards_converts_values_and_warns_invalid_entries() -> None:
    result = normalizeRewards(
        [
            {"type": "item", "itemId": "2087", "count": "2"},
            {"type": "item", "itemId": "", "count": "1"},
            {"type": "item", "itemId": "39", "count": ""},
            {"type": "item", "itemId": "bad", "count": "1"},
            {"type": "item", "itemId": "40", "count": "bad"},
        ]
    )

    assert result.errors == []
    assert _triples(result.rewards) == [("item", 2087, 2)]
    assert [warning.error_type for warning in result.warnings] == [
        "empty_item_id",
        "empty_count",
        "invalid_item_id",
        "invalid_count",
    ]


def test_merge_duplicate_rewards_sums_counts_and_warns_type_mismatch() -> None:
    result = mergeDuplicateRewards(
        [
            RewardItem(type="item", item_id=2087, count=1),
            RewardItem(type="item", item_id=2087, count=3),
            RewardItem(type="res", item_id=2087, count=2),
        ]
    )

    assert result.rewards == [RewardItem(type="item", item_id=2087, count=6)]
    assert [warning.error_type for warning in result.duplicate_warnings] == [
        "duplicate_reward",
        "duplicate_reward",
        "duplicate_type_mismatch",
    ]


def test_compare_reward_sets_passes_when_order_differs() -> None:
    result = compareRewardSets(
        [
            RewardItem(type="item", item_id=2087, count=1),
            RewardItem(type="item", item_id=39, count=2),
        ],
        [
            RewardItem(type="item", item_id=39, count=2),
            RewardItem(type="item", item_id=2087, count=1),
        ],
    )

    assert result.status == "pass"
    assert result.missing_rewards == []
    assert result.extra_rewards == []
    assert result.count_mismatches == []


def test_compare_reward_sets_reports_missing_rewards() -> None:
    result = compareRewardSets(
        [
            RewardItem(type="item", item_id=2087, count=1),
            RewardItem(type="item", item_id=39, count=2),
        ],
        [RewardItem(type="item", item_id=2087, count=1)],
    )

    assert result.status == "fail"
    assert result.missing_rewards == [RewardItem(type="item", item_id=39, count=2)]
    assert result.extra_rewards == []
    assert result.count_mismatches == []


def test_compare_reward_sets_reports_extra_rewards() -> None:
    result = compareRewardSets(
        [RewardItem(type="item", item_id=2087, count=1)],
        [
            RewardItem(type="item", item_id=2087, count=1),
            RewardItem(type="item", item_id=39, count=2),
        ],
    )

    assert result.status == "fail"
    assert result.missing_rewards == []
    assert result.extra_rewards == [RewardItem(type="item", item_id=39, count=2)]
    assert result.count_mismatches == []


def test_compare_reward_sets_reports_count_mismatches() -> None:
    result = compareRewardSets(
        [RewardItem(type="item", item_id=2087, count=1)],
        [RewardItem(type="item", item_id=2087, count=3)],
    )

    assert result.status == "fail"
    assert result.missing_rewards == []
    assert result.extra_rewards == []
    assert len(result.count_mismatches) == 1
    mismatch = result.count_mismatches[0]
    assert mismatch.item_id == 2087
    assert mismatch.expected_count == 1
    assert mismatch.actual_count == 3
