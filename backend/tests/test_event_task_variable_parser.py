from backend.app.services.event_task_variable_parser import (
    buildEventTaskVariableIndex,
    parseEventTaskVariables,
)
from backend.app.services.reward_parser import RewardItem


def _reward_triples(rewards: list[RewardItem]) -> list[tuple[str | None, int, int]]:
    return [(reward.type, reward.item_id, reward.count) for reward in rewards]


def _warning_types(warnings: list[object]) -> list[str]:
    return [getattr(warning, "warning_type") for warning in warnings]


def test_parse_event_task_variables_extracts_group_id_and_suffix() -> None:
    tasks = parseEventTaskVariables(
        {
            "2021041901_0": {
                "INT_TaskID": 1,
                "STR_Title": "开服战力提升活动",
                "STR_Desc": "战力达到2w",
                "STR_Loot": "[{item,2087,1},{item,39,2}]",
            }
        }
    )

    assert len(tasks) == 1
    task = tasks[0]
    assert task.task_group_id == "2021041901"
    assert task.taskGroupId == "2021041901"
    assert task.sort_suffix == "0"
    assert task.sortSuffix == "0"
    assert task.variable_key == "2021041901_0"
    assert task.variableKey == "2021041901_0"
    assert task.task_id == 1
    assert task.taskId == 1
    assert task.title == "开服战力提升活动"
    assert task.desc == "战力达到2w"
    assert task.raw_loot == "[{item,2087,1},{item,39,2}]"
    assert task.rawLoot == "[{item,2087,1},{item,39,2}]"
    assert task.warnings == []


def test_parse_event_task_variables_accepts_key_without_delimiter() -> None:
    tasks = parseEventTaskVariables(
        {
            "2021041901": {
                "INT_TaskID": 1,
                "STR_Desc": "战力达到2w",
                "STR_Loot": "[{item,2087,1}]",
            }
        }
    )

    assert tasks[0].task_group_id == "2021041901"
    assert tasks[0].sort_suffix is None
    assert _warning_types(tasks[0].warnings) == ["missing_key_delimiter"]


def test_parse_event_task_variables_parses_item_rewards() -> None:
    tasks = parseEventTaskVariables(
        {
            "2021041901_0": {
                "INT_TaskID": 1,
                "STR_Desc": "战力达到2w",
                "STR_Loot": "[{item,2087,1},{item,39,2}]",
            }
        }
    )

    assert _reward_triples(tasks[0].rewards) == [("item", 2087, 1), ("item", 39, 2)]


def test_parse_event_task_variables_parses_res_rewards() -> None:
    tasks = parseEventTaskVariables(
        {
            "2021041901_0": {
                "INT_TaskID": 1,
                "STR_Desc": "战力达到2w",
                "STR_Loot": "[{res,5,100},{item,2087,3}]",
            }
        }
    )

    assert _reward_triples(tasks[0].rewards) == [("res", 5, 100), ("item", 2087, 3)]


def test_parse_event_task_variables_records_empty_loot_warning() -> None:
    tasks = parseEventTaskVariables(
        {
            "2021041901_0": {
                "INT_TaskID": 1,
                "STR_Desc": "战力达到2w",
                "STR_Loot": "",
            }
        }
    )

    assert tasks[0].rewards == []
    assert _warning_types(tasks[0].warnings) == ["loot_empty_reward"]


def test_parse_event_task_variables_records_loot_format_warning() -> None:
    tasks = parseEventTaskVariables(
        {
            "2021041901_0": {
                "INT_TaskID": 1,
                "STR_Desc": "战力达到2w",
                "STR_Loot": "[item,2087,1]",
            }
        }
    )

    assert tasks[0].rewards == []
    assert _warning_types(tasks[0].warnings) == ["loot_reward_format_error"]


def test_parse_event_task_variables_records_missing_required_fields() -> None:
    tasks = parseEventTaskVariables(
        {
            "2021041901_0": {
                "STR_Title": "开服战力提升活动",
                "STR_Loot": "[{item,2087,1}]",
            }
        }
    )

    assert tasks[0].task_id is None
    assert tasks[0].desc == ""
    assert _warning_types(tasks[0].warnings) == ["missing_task_id", "missing_desc"]


def test_build_event_task_variable_index_builds_expected_indexes() -> None:
    tasks = parseEventTaskVariables(
        {
            "2021041901_0": {
                "INT_TaskID": 1,
                "STR_Desc": "战力达到2w",
                "STR_Loot": "[{item,2087,1}]",
            },
            "2021041901_1": {
                "INT_TaskID": 2,
                "STR_Desc": "战力达到5w",
                "STR_Loot": "[{item,2102,1}]",
            },
        }
    )

    index = buildEventTaskVariableIndex(tasks)

    assert index.by_group_id_and_desc["2021041901::战力达到2w"] is tasks[0]
    assert index.byGroupIdAndDesc["2021041901::战力达到5w"] is tasks[1]
    assert index.by_group_id_and_task_id["2021041901::1"] is tasks[0]
    assert index.byGroupIdAndTaskId["2021041901::2"] is tasks[1]
    assert index.warnings == []


def test_build_event_task_variable_index_warns_duplicate_keys_without_overwrite() -> None:
    tasks = parseEventTaskVariables(
        {
            "2021041901_0": {
                "INT_TaskID": 1,
                "STR_Desc": "战力达到2w",
                "STR_Loot": "[{item,2087,1}]",
            },
            "2021041901_1": {
                "INT_TaskID": 1,
                "STR_Desc": "战力达到2w",
                "STR_Loot": "[{item,2102,1}]",
            },
        }
    )

    index = buildEventTaskVariableIndex(tasks)

    assert index.by_group_id_and_desc["2021041901::战力达到2w"] is tasks[0]
    assert index.by_group_id_and_task_id["2021041901::1"] is tasks[0]
    assert _warning_types(index.warnings) == [
        "duplicate_group_desc_index",
        "duplicate_group_task_id_index",
    ]
    assert [warning.index_key for warning in index.warnings] == [
        "2021041901::战力达到2w",
        "2021041901::1",
    ]
