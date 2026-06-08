from backend.app.api.fixed_rules_schemas import EventTaskPlanRow, EventTaskPreviewRewardItem
from backend.app.services.event_task_reward_validator import (
    validateEventTaskRewards,
    validate_event_task_rewards,
)
from backend.app.services.event_task_variable_parser import parseEventTaskVariables


def _reward(item_id: int, count: int, name: str | None = None) -> EventTaskPreviewRewardItem:
    return EventTaskPreviewRewardItem(
        type="item",
        item_id=item_id,
        itemId=item_id,
        count=count,
        name=name,
    )


def _feishu_task(
    *,
    group_id: str = "26051802",
    task_id: str | None = "1",
    desc: str = "累计登陆1天",
    row_index: int = 3,
    rewards: list[tuple[int, int]] | None = None,
) -> EventTaskPlanRow:
    resolved_rewards = rewards or [(2087, 1), (39, 2)]
    return EventTaskPlanRow(
        row_index=row_index,
        task_group_id=group_id,
        task_id=task_id,
        task_desc=desc,
        loot=",".join(f"{{item,{item_id},{count}}}" for item_id, count in resolved_rewards),
        rewards=[_reward(item_id, count) for item_id, count in resolved_rewards],
        warnings=[],
        raw_row=[],
    )


def _variable_tasks(payload: dict[str, dict[str, object]]):
    return parseEventTaskVariables(payload)


def test_group_id_desc_match_passes() -> None:
    result = validate_event_task_rewards(
        feishu_tasks=[_feishu_task()],
        variable_tasks=_variable_tasks(
            {
                "26051802_0": {
                    "INT_TaskID": 1,
                    "STR_Desc": "累计登陆1天",
                    "STR_Loot": "[{item,2087,1},{item,39,2}]",
                }
            }
        ),
        match_strategy="groupId_desc",
    )

    assert result.total == 1
    assert result.pass_count == 1
    assert result.results[0].status == "pass"
    assert result.results[0].variable_key == "26051802_0"
    assert result.results[0].match_strategy == "groupId_desc"


def test_group_id_task_id_match_passes_when_desc_differs() -> None:
    result = validate_event_task_rewards(
        feishu_tasks=[_feishu_task(task_id="2", desc="累计登陆2天")],
        variable_tasks=_variable_tasks(
            {
                "26051802_1": {
                    "INT_TaskID": 2,
                    "STR_Desc": "配置侧描述不同",
                    "STR_Loot": "[{item,2087,1},{item,39,2}]",
                }
            }
        ),
        match_strategy="groupId_taskId",
    )

    assert result.pass_count == 1
    assert result.results[0].status == "pass"
    assert result.results[0].variable_task_id == "2"
    assert result.results[0].match_strategy == "groupId_taskId"


def test_desc_then_task_id_falls_back_to_task_id() -> None:
    result = validate_event_task_rewards(
        feishu_tasks=[_feishu_task(task_id="3", desc="累计登陆3天")],
        variable_tasks=_variable_tasks(
            {
                "26051802_2": {
                    "INT_TaskID": 3,
                    "STR_Desc": "累计登录3天",
                    "STR_Loot": "[{item,2087,1},{item,39,2}]",
                }
            }
        ),
    )

    assert result.pass_count == 1
    assert result.results[0].match_strategy == "groupId_taskId"


def test_reward_order_differs_but_passes() -> None:
    result = validate_event_task_rewards(
        feishu_tasks=[_feishu_task(rewards=[(2087, 1), (39, 2)])],
        variable_tasks=_variable_tasks(
            {
                "26051802_0": {
                    "INT_TaskID": 1,
                    "STR_Desc": "累计登陆1天",
                    "STR_Loot": "[{item,39,2},{item,2087,1}]",
                }
            }
        ),
    )

    assert result.results[0].status == "pass"


def test_count_mismatch_fails() -> None:
    result = validate_event_task_rewards(
        feishu_tasks=[_feishu_task(rewards=[(2087, 1)])],
        variable_tasks=_variable_tasks(
            {
                "26051802_0": {
                    "INT_TaskID": 1,
                    "STR_Desc": "累计登陆1天",
                    "STR_Loot": "[{item,2087,2}]",
                }
            }
        ),
    )

    row = result.results[0]
    assert row.status == "fail"
    assert row.error_message == "奖励不一致"
    assert row.count_mismatches[0].item_id == 2087
    assert row.count_mismatches[0].expected_count == 1
    assert row.count_mismatches[0].actual_count == 2


def test_expected_extra_reward_is_missing_from_actual() -> None:
    result = validate_event_task_rewards(
        feishu_tasks=[_feishu_task(rewards=[(2087, 1), (39, 2)])],
        variable_tasks=_variable_tasks(
            {
                "26051802_0": {
                    "INT_TaskID": 1,
                    "STR_Desc": "累计登陆1天",
                    "STR_Loot": "[{item,2087,1}]",
                }
            }
        ),
    )

    row = result.results[0]
    assert row.status == "fail"
    assert [(reward.item_id, reward.count) for reward in row.missing_rewards] == [(39, 2)]


def test_actual_extra_reward_fails() -> None:
    result = validate_event_task_rewards(
        feishu_tasks=[_feishu_task(rewards=[(2087, 1)])],
        variable_tasks=_variable_tasks(
            {
                "26051802_0": {
                    "INT_TaskID": 1,
                    "STR_Desc": "累计登陆1天",
                    "STR_Loot": "[{item,2087,1},{item,39,2}]",
                }
            }
        ),
    )

    row = result.results[0]
    assert row.status == "fail"
    assert [(reward.item_id, reward.count) for reward in row.extra_rewards] == [(39, 2)]


def test_missing_variable_task_fails_and_counts_unmatched() -> None:
    result = validate_event_task_rewards(
        feishu_tasks=[_feishu_task()],
        variable_tasks=[],
    )

    row = result.results[0]
    assert result.fail_count == 1
    assert result.unmatched_count == 1
    assert row.status == "fail"
    assert row.error_message == "未找到对应组合变量任务"
    assert [(reward.item_id, reward.count) for reward in row.missing_rewards] == [
        (2087, 1),
        (39, 2),
    ]


def test_duplicate_variable_match_warns_and_fails_without_silent_choice() -> None:
    result = validate_event_task_rewards(
        feishu_tasks=[_feishu_task()],
        variable_tasks=_variable_tasks(
            {
                "26051802_0": {
                    "INT_TaskID": 1,
                    "STR_Desc": "累计登陆1天",
                    "STR_Loot": "[{item,2087,1}]",
                },
                "26051802_1": {
                    "INT_TaskID": 2,
                    "STR_Desc": "累计登陆1天",
                    "STR_Loot": "[{item,39,2}]",
                },
            }
        ),
        match_strategy="groupId_desc",
    )

    row = result.results[0]
    assert row.status == "fail"
    assert row.error_message == "匹配到多个组合变量任务"
    assert row.parse_warnings == ["匹配到多个组合变量任务：26051802_0、26051802_1。"]
    assert result.warning_count == 1
    assert result.extra_variable_tasks == []


def test_scope_limits_checked_groups_and_extra_variable_tasks() -> None:
    result = validateEventTaskRewards(
        {
            "feishuTasks": [
                _feishu_task(group_id="26051802", desc="累计登陆1天", task_id="1"),
                _feishu_task(group_id="26051803", desc="累计登陆2天", task_id="2"),
            ],
            "variableTasks": _variable_tasks(
                {
                    "26051802_0": {
                        "INT_TaskID": 1,
                        "STR_Desc": "累计登陆1天",
                        "STR_Loot": "[{item,2087,1},{item,39,2}]",
                    },
                    "26051802_1": {
                        "INT_TaskID": 99,
                        "STR_Desc": "额外任务",
                        "STR_Loot": "[{item,2102,1}]",
                    },
                    "26051803_0": {
                        "INT_TaskID": 2,
                        "STR_Desc": "累计登陆2天",
                        "STR_Loot": "[{item,2087,1},{item,39,2}]",
                    },
                }
            ),
            "scope": {"taskGroupIds": ["26051802"]},
        }
    )

    assert result.total == 1
    assert result.passCount == 1
    assert [row.task_group_id for row in result.results] == ["26051802"]
    assert len(result.extraVariableTasks) == 1
    assert result.extraVariableTasks[0].task_group_id == "26051802"
    assert result.extraVariableTasks[0].variable_key == "26051802_1"
