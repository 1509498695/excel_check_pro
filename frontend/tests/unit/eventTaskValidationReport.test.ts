import { describe, expect, it } from 'vitest'

import type { EventTaskRewardValidationResult } from '../../src/types/fixedRules'
import {
  buildEventTaskErrorDetailText,
  buildEventTaskValidationCsv,
  buildEventTaskValidationCsvFilename,
  formatEventTaskRewards,
  isEventTaskResultUnmatched,
} from '../../src/utils/eventTaskValidationReport'

function createResult(
  overrides: Partial<EventTaskRewardValidationResult> = {},
): EventTaskRewardValidationResult {
  return {
    taskGroupId: '26051802',
    task_group_id: '26051802',
    taskDesc: '累计登陆1天',
    task_desc: '累计登陆1天',
    feishuRowIndex: 3,
    feishu_row_index: 3,
    variableKey: '26051802_4476',
    variable_key: '26051802_4476',
    variableTaskId: '1',
    variable_task_id: '1',
    matchStrategy: 'groupId_desc',
    match_strategy: 'groupId_desc',
    status: 'fail',
    expectedRewards: [
      { type: 'item', item_id: 1502, itemId: 1502, count: 2, name: '体力回复' },
    ],
    expected_rewards: [
      { type: 'item', item_id: 1502, itemId: 1502, count: 2, name: '体力回复' },
    ],
    actualRewards: [{ type: 'res', item_id: 16, itemId: 16, count: 200 }],
    actual_rewards: [{ type: 'res', item_id: 16, itemId: 16, count: 200 }],
    missingRewards: [{ type: 'item', item_id: 1502, itemId: 1502, count: 2 }],
    missing_rewards: [{ type: 'item', item_id: 1502, itemId: 1502, count: 2 }],
    extraRewards: [{ type: 'res', item_id: 16, itemId: 16, count: 200 }],
    extra_rewards: [{ type: 'res', item_id: 16, itemId: 16, count: 200 }],
    countMismatches: [
      {
        item_id: 2087,
        itemId: 2087,
        expected_count: 1,
        expectedCount: 1,
        actual_count: 2,
        actualCount: 2,
      },
    ],
    count_mismatches: [
      {
        item_id: 2087,
        itemId: 2087,
        expected_count: 1,
        expectedCount: 1,
        actual_count: 2,
        actualCount: 2,
      },
    ],
    duplicateWarnings: ['重复奖励 itemId=1502'],
    duplicate_warnings: ['重复奖励 itemId=1502'],
    parseWarnings: ['STR_Loot 为空。'],
    parse_warnings: ['STR_Loot 为空。'],
    errorMessage: '奖励不一致',
    error_message: '奖励不一致',
    ...overrides,
  }
}

describe('eventTaskValidationReport', () => {
  it('formats item and res rewards for planner-facing text', () => {
    expect(
      formatEventTaskRewards([
        { type: 'item', item_id: 1502, itemId: 1502, count: 2 },
        { type: 'res', item_id: 16, itemId: 16, count: 200 },
      ]),
    ).toBe('itemId=1502 count=2；res id=16 count=200')
  })

  it('builds copyable error detail with core location and diff fields', () => {
    const text = buildEventTaskErrorDetailText(createResult())

    expect(text).toContain('任务组ID：26051802')
    expect(text).toContain('任务描述：累计登陆1天')
    expect(text).toContain('飞书行号：3')
    expect(text).toContain('组合变量：26051802_4476')
    expect(text).toContain('问题：组合变量缺少奖励 itemId=1502 count=2')
    expect(text).toContain('多余配置：res id=16 count=200')
    expect(text).toContain('奖励数量不一致 itemId=2087 expected=1 actual=2')
    expect(text).toContain('Warning：重复奖励 itemId=1502；STR_Loot 为空。')
  })

  it('builds UTF-8 BOM CSV with expected columns and escaped cells', () => {
    const csv = buildEventTaskValidationCsv([
      createResult({
        taskDesc: '累计登陆1天,"换行\n检查"',
        task_desc: '累计登陆1天,"换行\n检查"',
      }),
    ])

    expect(csv.charCodeAt(0)).toBe(0xfeff)
    expect(csv).toContain('任务组ID,任务描述,飞书行号,组合变量key,校验状态')
    expect(csv).toContain('"累计登陆1天,""换行\n检查"""')
    expect(csv).toContain('itemId=1502 count=2')
    expect(csv).toContain('res id=16 count=200')
    expect(csv).toContain('itemId=2087 expected=1 actual=2')
  })

  it('builds stable export filenames from mode and timestamp', () => {
    expect(buildEventTaskValidationCsvFilename('failed', new Date('2026-06-05T07:08:09'))).toBe(
      'event-task-validation-failed-20260605-070809.csv',
    )
  })

  it('detects unmatched failed rows', () => {
    expect(
      isEventTaskResultUnmatched(
        createResult({
          variableKey: null,
          variable_key: null,
          errorMessage: '未找到对应组合变量任务',
          error_message: '未找到对应组合变量任务',
        }),
      ),
    ).toBe(true)
  })
})
