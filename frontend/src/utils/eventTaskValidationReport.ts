import type {
  EventTaskRewardValidationResult,
  RewardCountMismatchData,
  RewardValidationItem,
} from '../types/fixedRules'

export type EventTaskValidationExportMode = 'all' | 'failed'

const CSV_HEADERS = [
  '任务组ID',
  '任务描述',
  '飞书行号',
  '组合变量key',
  '校验状态',
  '飞书奖励',
  '组合变量奖励',
  '缺失奖励',
  '多余奖励',
  '数量不一致',
  'warning',
  '错误信息',
]

type RewardLike = {
  item_id?: number | string | null
  itemId?: number | string | null
  count?: number | string | null
  type?: string | null
  name?: string | null
}

export function getEventTaskResultTaskGroupId(row: EventTaskRewardValidationResult): string {
  return row.taskGroupId || row.task_group_id || ''
}

export function getEventTaskResultTaskDesc(row: EventTaskRewardValidationResult): string {
  return row.taskDesc || row.task_desc || ''
}

export function getEventTaskResultVariableKey(row: EventTaskRewardValidationResult): string {
  return row.variableKey || row.variable_key || ''
}

export function getEventTaskResultExpectedRewards(
  row: EventTaskRewardValidationResult,
): RewardValidationItem[] {
  return row.expectedRewards ?? row.expected_rewards ?? []
}

export function getEventTaskResultActualRewards(
  row: EventTaskRewardValidationResult,
): RewardValidationItem[] {
  return row.actualRewards ?? row.actual_rewards ?? []
}

export function getEventTaskResultMissingRewards(
  row: EventTaskRewardValidationResult,
): RewardValidationItem[] {
  return row.missingRewards ?? row.missing_rewards ?? []
}

export function getEventTaskResultExtraRewards(
  row: EventTaskRewardValidationResult,
): RewardValidationItem[] {
  return row.extraRewards ?? row.extra_rewards ?? []
}

export function getEventTaskResultCountMismatches(
  row: EventTaskRewardValidationResult,
): RewardCountMismatchData[] {
  return row.countMismatches ?? row.count_mismatches ?? []
}

export function getEventTaskResultWarnings(row: EventTaskRewardValidationResult): string[] {
  return [
    ...(row.duplicateWarnings ?? row.duplicate_warnings ?? []),
    ...(row.parseWarnings ?? row.parse_warnings ?? []),
  ].filter((warning) => warning.trim().length > 0)
}

export function getEventTaskResultErrorMessage(row: EventTaskRewardValidationResult): string {
  return row.errorMessage || row.error_message || ''
}

export function hasEventTaskResultWarning(row: EventTaskRewardValidationResult): boolean {
  return getEventTaskResultWarnings(row).length > 0
}

export function isEventTaskResultUnmatched(row: EventTaskRewardValidationResult): boolean {
  if (row.status !== 'fail') {
    return false
  }
  const errorMessage = getEventTaskResultErrorMessage(row)
  return errorMessage.includes('未找到对应组合变量任务') || !getEventTaskResultVariableKey(row)
}

export function formatEventTaskRewardForReport(reward: RewardLike): string {
  const type = reward.type?.trim() || 'item'
  const itemId = reward.itemId ?? reward.item_id ?? ''
  const count = reward.count ?? ''
  const name = reward.name?.trim() ? ` name=${reward.name.trim()}` : ''
  if (type === 'item') {
    return `itemId=${itemId} count=${count}${name}`
  }
  return `${type} id=${itemId} count=${count}${name}`
}

export function formatEventTaskRewards(rewards: RewardLike[] | undefined | null): string {
  if (!rewards?.length) {
    return '无'
  }
  return rewards.map(formatEventTaskRewardForReport).join('；')
}

export function formatEventTaskCountMismatches(
  mismatches: RewardCountMismatchData[] | undefined | null,
): string {
  if (!mismatches?.length) {
    return '无'
  }
  return mismatches
    .map((item) => {
      const itemId = item.itemId ?? item.item_id
      const expectedCount = item.expectedCount ?? item.expected_count
      const actualCount = item.actualCount ?? item.actual_count
      return `itemId=${itemId} expected=${expectedCount} actual=${actualCount}`
    })
    .join('；')
}

export function formatEventTaskResultWarnings(row: EventTaskRewardValidationResult): string {
  const warnings = getEventTaskResultWarnings(row)
  return warnings.length ? warnings.join('；') : '无'
}

export function formatEventTaskResultStatus(row: EventTaskRewardValidationResult): string {
  return row.status === 'pass' ? '通过' : '失败'
}

export function buildEventTaskErrorDetailText(row: EventTaskRewardValidationResult): string {
  const missingRewards = getEventTaskResultMissingRewards(row)
  const extraRewards = getEventTaskResultExtraRewards(row)
  const countMismatches = getEventTaskResultCountMismatches(row)
  const warnings = getEventTaskResultWarnings(row)
  const errorMessage = getEventTaskResultErrorMessage(row)
  const problemParts: string[] = []

  if (missingRewards.length) {
    problemParts.push(`组合变量缺少奖励 ${formatEventTaskRewards(missingRewards)}`)
  }
  if (extraRewards.length) {
    problemParts.push(`组合变量多余奖励 ${formatEventTaskRewards(extraRewards)}`)
  }
  if (countMismatches.length) {
    problemParts.push(`奖励数量不一致 ${formatEventTaskCountMismatches(countMismatches)}`)
  }
  if (!problemParts.length && errorMessage) {
    problemParts.push(errorMessage)
  }

  const lines = [
    `任务组ID：${getEventTaskResultTaskGroupId(row) || '-'}`,
    `任务描述：${getEventTaskResultTaskDesc(row) || '-'}`,
    `飞书行号：${row.feishuRowIndex ?? row.feishu_row_index ?? '-'}`,
    `组合变量：${getEventTaskResultVariableKey(row) || '-'}`,
    `问题：${problemParts.length ? problemParts.join('；') : '无'}`,
  ]

  if (extraRewards.length) {
    lines.push(`多余配置：${formatEventTaskRewards(extraRewards)}`)
  }
  if (warnings.length) {
    lines.push(`Warning：${warnings.join('；')}`)
  }
  if (errorMessage && !problemParts.includes(errorMessage)) {
    lines.push(`错误信息：${errorMessage}`)
  }

  lines.push(
    `飞书奖励：${formatEventTaskRewards(getEventTaskResultExpectedRewards(row))}`,
    `组合变量奖励：${formatEventTaskRewards(getEventTaskResultActualRewards(row))}`,
  )

  return lines.join('\n')
}

export function buildEventTaskValidationCsv(rows: EventTaskRewardValidationResult[]): string {
  const lines = [
    CSV_HEADERS.map(escapeCsvCell).join(','),
    ...rows.map((row) =>
      [
        getEventTaskResultTaskGroupId(row),
        getEventTaskResultTaskDesc(row),
        row.feishuRowIndex ?? row.feishu_row_index ?? '',
        getEventTaskResultVariableKey(row),
        formatEventTaskResultStatus(row),
        formatEventTaskRewards(getEventTaskResultExpectedRewards(row)),
        formatEventTaskRewards(getEventTaskResultActualRewards(row)),
        formatEventTaskRewards(getEventTaskResultMissingRewards(row)),
        formatEventTaskRewards(getEventTaskResultExtraRewards(row)),
        formatEventTaskCountMismatches(getEventTaskResultCountMismatches(row)),
        formatEventTaskResultWarnings(row),
        getEventTaskResultErrorMessage(row),
      ]
        .map((value) => escapeCsvCell(String(value)))
        .join(','),
    ),
  ]
  return `\uFEFF${lines.join('\r\n')}\r\n`
}

export function buildEventTaskValidationCsvFilename(
  mode: EventTaskValidationExportMode,
  now = new Date(),
): string {
  return `event-task-validation-${mode}-${formatTimestamp(now)}.csv`
}

export function downloadCsv(filename: string, content: string): void {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function escapeCsvCell(value: string): string {
  if (/[",\r\n]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`
  }
  return value
}

function formatTimestamp(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(
    date.getHours(),
  )}${pad(date.getMinutes())}${pad(date.getSeconds())}`
}
