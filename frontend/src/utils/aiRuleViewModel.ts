import type { AiMissingItem, AiRuleDraft, AiRuleDraftPayload } from '../types/ai'
import type { FixedRuleDefinition, FixedRuleType } from '../types/fixedRules'
import type { DataSource, VariableTag } from '../types/workbench'
import { getSourceTypeLabel } from './workbenchMeta'

export type AiRuleUiStatus =
  | 'ready'
  | 'duplicate'
  | 'needs_input'
  | 'rejected'
  | 'applied'
  | 'loading'
  | 'empty'
  | 'error'

export type AiRuleExplanationTone = 'neutral' | 'success' | 'warning' | 'danger' | 'primary'

export interface AiRuleExplanationItem {
  label: string
  text: string
  tone?: AiRuleExplanationTone
}

export interface AiRuleResultViewModel {
  id: string
  status: AiRuleUiStatus
  title: string
  ruleTypeLabel: string
  sourceLabel: string
  sheetLabel: string
  fieldLabel: string
  variableLabel: string
  groupLabel: string
  metaText: string
  missingText: string
  reasonText: string
  explanationTitle: string
  explanationItems: AiRuleExplanationItem[]
  nextActionText: string
  rewriteHintText: string
  resolveActionText: string
  rule?: FixedRuleDefinition
  missing?: AiMissingItem
}

export interface PendingConfigPreviewViewModel {
  sources: string[]
  variables: string[]
  rules: string[]
}

export interface AiResultSummaryViewModel {
  total: number
  ready: number
  needsInput: number
  rejected: number
  applied: number
  text: string
  label: string
  tone: 'success' | 'warning' | 'danger' | 'primary' | 'neutral'
}

export interface DraftHistoryViewModel {
  id: string
  title: string
  ruleCount: number
  timeLabel: string
  status: AiRuleUiStatus
  statusLabel: string
  draft: AiRuleDraft
}

const ruleTypeLabelMap: Record<FixedRuleType, string> = {
  fixed_value_compare: '常量比较',
  regex_check: '正则校验',
  not_null: '非空校验',
  unique: '唯一校验',
  sequence_order_check: '顺序校验',
  cross_table_mapping: '跨表映射',
  composite_condition_check: '组合分支',
  dual_composite_compare: '跨组变量',
  multi_composite_pipeline_check: '多组串行',
  multi_composite_mapping_check: '多组映射',
  package_items_compare: 'IAP礼包校验',
}

export function getAiRuleTypeLabel(ruleType?: FixedRuleType | null): string {
  return ruleType ? ruleTypeLabelMap[ruleType] ?? ruleType : '-'
}

export function normalizeRuleStatus(draft: AiRuleDraft | null | undefined): AiRuleUiStatus {
  if (!draft) return 'empty'
  if (draft.applied) return 'applied'
  return draft.verdict
}

export function getStatusLabel(status: AiRuleUiStatus): string {
  const labels: Record<AiRuleUiStatus, string> = {
    ready: 'ready / 可添加',
    duplicate: '已有规则 / 不用添加',
    needs_input: 'needs_input / 需补充',
    rejected: 'rejected / 不可添加',
    applied: 'applied / 已添加',
    loading: 'loading',
    empty: 'empty',
    error: 'error',
  }
  return labels[status]
}

function formatText(value: unknown, fallback = '-'): string {
  if (value === null || value === undefined || value === '') return fallback
  if (Array.isArray(value)) return value.length ? value.map((item) => formatText(item)).join('、') : fallback
  return typeof value === 'string' ? value : JSON.stringify(value)
}

function getRuleTypeMatchReason(rule: FixedRuleDefinition, fieldLabel: string): string {
  switch (rule.rule_type) {
    case 'not_null':
      return `描述要求目标字段有值，当前规则库可用非空校验直接检查 ${fieldLabel} 是否为空。`
    case 'unique':
      return `描述要求字段不重复，唯一校验会按 ${fieldLabel} 聚合检查重复值。`
    case 'fixed_value_compare':
      return `描述包含固定值、阈值或规则集判断，常量比较可表达 ${fieldLabel} ${formatText(rule.operator, '')} ${formatText(rule.expected_value, '')}。`
    case 'regex_check':
      return `描述包含格式约束，正则校验可用表达式 ${formatText(rule.expected_value)} 检查 ${fieldLabel}。`
    case 'sequence_order_check':
      return `描述包含连续、递增或递减关系，顺序校验会按表格行序检查 ${fieldLabel}。`
    case 'cross_table_mapping':
      return `描述需要字段在另一张表或字典中存在，跨表映射会把目标变量和引用变量做包含关系校验。`
    case 'composite_condition_check':
      return `描述包含筛选条件和断言字段，组合分支校验可以先过滤数据，再校验命中行的字段。`
    case 'dual_composite_compare':
      return `描述包含左右两组数据按 Key 对齐再比较，跨组变量校验可以保留左右筛选、Key 和比较字段。`
    case 'multi_composite_pipeline_check':
      return `描述包含多节点串行检查，多组串行会按节点顺序过滤和判定，首个失败节点输出异常。`
    case 'multi_composite_mapping_check':
      return `描述包含多组独立映射检查，多组映射可分别校验每个节点的筛选条件和排除范围。`
    default:
      return `AI 将描述匹配到 ${getAiRuleTypeLabel(rule.rule_type)}，请查看配置确认字段和参数。`
  }
}

function getRuleParamSummary(rule: FixedRuleDefinition): string {
  if (rule.rule_type === 'fixed_value_compare') {
    return `操作符 ${formatText(rule.operator)}，期望值 ${formatText(rule.expected_value)}。`
  }
  if (rule.rule_type === 'regex_check') {
    return `正则表达式 ${formatText(rule.expected_value)}。`
  }
  if (rule.rule_type === 'sequence_order_check') {
    return `方向 ${formatText(rule.sequence_direction)}，步长 ${formatText(rule.sequence_step)}，起点 ${formatText(rule.sequence_start_mode)}。`
  }
  if (rule.rule_type === 'cross_table_mapping') {
    return `引用变量 ${formatText(rule.reference_variable_tag)}。`
  }
  if (rule.rule_type === 'dual_composite_compare') {
    return `Key ${formatText(rule.left_key_field)} / ${formatText(rule.right_key_field)}，比较项 ${formatText(rule.comparisons)}。`
  }
  if (rule.rule_type === 'multi_composite_pipeline_check') {
    return `串行节点 ${formatText(rule.pipeline_config)}。`
  }
  if (rule.rule_type === 'multi_composite_mapping_check') {
    return `映射节点 ${formatText(rule.mapping_config)}。`
  }
  return rule.display_field ? `结果显示字段 ${rule.display_field}。` : '使用规则默认参数。'
}

function buildReadyExplanation(input: {
  rule: FixedRuleDefinition
  ruleTypeLabel: string
  sourceLabel: string
  sheetLabel: string
  fieldLabel: string
  variableLabel: string
  reasoningSummary?: string
  applied?: boolean
}): Pick<
  AiRuleResultViewModel,
  'explanationTitle' | 'explanationItems' | 'nextActionText' | 'rewriteHintText' | 'resolveActionText'
> {
  const items: AiRuleExplanationItem[] = [
    {
      label: '匹配依据',
      text:
        input.reasoningSummary?.trim() ||
        getRuleTypeMatchReason(input.rule, input.fieldLabel),
      tone: 'success',
    },
    {
      label: '规则对象',
      text: `目标变量 ${input.variableLabel}，字段 ${input.fieldLabel}，数据源 ${input.sourceLabel}，Sheet ${input.sheetLabel}。`,
    },
    {
      label: '关键参数',
      text: getRuleParamSummary(input.rule),
    },
  ]
  return {
    explanationTitle: `为什么匹配为${input.ruleTypeLabel}`,
    explanationItems: items,
    nextActionText: input.applied
      ? '规则已添加到个人校验，可在手动规则编排中继续查看或执行。'
      : '先点“查看配置”确认变量、字段和参数，再看预校验结果决定是否添加。',
    rewriteHintText: '',
    resolveActionText: '',
  }
}

function getMissingKindLabel(kind?: AiMissingItem['kind']): string {
  const labels: Record<AiMissingItem['kind'], string> = {
    source: '数据源',
    variable: '变量',
    rule: '规则',
    parameter: '规则参数',
    ability: '系统能力',
  }
  return kind ? labels[kind] : '输入信息'
}

function getMissingActionLabel(action?: AiMissingItem['suggested_action']): string {
  const labels: Record<AiMissingItem['suggested_action'], string> = {
    open_source_dialog: '选择/新增数据源',
    open_single_variable_dialog: '新增单变量',
    open_composite_variable_dialog: '新增组合变量',
    edit_description: '回到输入框改写',
    none: '查看缺口说明',
  }
  return action ? labels[action] : '补充描述后重试'
}

function getMissingActionGuide(missing?: AiMissingItem): string {
  if (!missing) return '在输入框补充数据源、Sheet、字段、Key 或判断条件后重新 AI 校验。'
  const guides: Record<AiMissingItem['suggested_action'], string> = {
    open_source_dialog: '点击“选择/新增数据源”打开数据源入口，补齐路径、Sheet 或文件来源。',
    open_single_variable_dialog: '点击“新增单变量”创建目标字段变量，再回到智能添加规则重试。',
    open_composite_variable_dialog: '点击“新增组合变量”补齐 Key、组合字段和筛选字段，再重新 AI 校验。',
    edit_description: '点击“回到输入框改写”，把缺少的字段、Key、筛选条件或判断值写进描述。',
    none: '先按缺口说明补充输入，再重新点击 AI 校验。',
  }
  return guides[missing.suggested_action]
}

function getMissingReasonCategory(missing?: AiMissingItem): string {
  const message = missing?.message ?? ''
  if (missing?.kind === 'source' || /数据源|配置表|路径/.test(message)) return '缺数据源'
  if (/Sheet|sheet|分页|页签/.test(message)) return '缺 Sheet'
  if (/字段不存在|不存在或无法唯一匹配|缺少列|缺列|缺少目标字段|列名/.test(message)) {
    return '缺字段或字段不存在'
  }
  if (/Key|key|主键|唯一键/.test(message)) return '需要 Key 字段'
  if (missing?.kind === 'ability' || /能力|不支持|无法表达/.test(message)) return '规则类型不支持'
  if (missing?.kind === 'parameter' || /参数|操作符|比较值|筛选值|正则/.test(message)) return '缺规则参数'
  if (missing?.kind === 'variable') return '缺变量'
  return '输入信息不足'
}

function getPrefillSummary(prefill?: Record<string, unknown>): string {
  const entries = Object.entries(prefill ?? {})
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .slice(0, 4)
  if (!entries.length) return '暂无可自动带入的线索。'
  return entries.map(([key, value]) => `${key}: ${formatText(value)}`).join('；')
}

function buildMissingExplanation(
  missing: AiMissingItem | undefined,
  ruleType: FixedRuleType | null | undefined,
): Pick<
  AiRuleResultViewModel,
  'explanationTitle' | 'explanationItems' | 'nextActionText' | 'rewriteHintText' | 'resolveActionText'
> {
  const kindLabel = getMissingKindLabel(missing?.kind)
  const actionText = getMissingActionLabel(missing?.suggested_action)
  const category = getMissingReasonCategory(missing)
  return {
    explanationTitle: `还缺${kindLabel}`,
    explanationItems: [
      {
        label: '失败归类',
        text: category,
        tone: 'warning',
      },
      {
        label: '缺口说明',
        text: missing?.message || '当前输入还不足以生成可预校验的规则草稿。',
        tone: 'warning',
      },
      {
        label: '为什么需要',
        text: `生成 ${getAiRuleTypeLabel(ruleType)} 前，需要明确数据源、变量、Key、筛选条件或判断参数，避免 AI 编造配置。`,
      },
      {
        label: '可带入线索',
        text: getPrefillSummary(missing?.prefill),
      },
    ],
    nextActionText: getMissingActionGuide(missing),
    rewriteHintText: '',
    resolveActionText: actionText,
  }
}

function buildRejectedExplanation(draft: AiRuleDraft): Pick<
  AiRuleResultViewModel,
  'explanationTitle' | 'explanationItems' | 'nextActionText' | 'rewriteHintText' | 'resolveActionText'
> {
  const suggestions = draft.extension_suggestions.length
    ? draft.extension_suggestions.join('；')
    : '暂无后端扩展建议。'
  return {
    explanationTitle: '为什么当前不可添加',
    explanationItems: [
      {
        label: '拒绝原因',
        text: draft.rejection_reason || '当前支持的规则类型无法可靠表达该需求。',
        tone: 'danger',
      },
      {
        label: '模型判断',
        text: draft.reasoning_summary || `未匹配到可直接保存的 ${getAiRuleTypeLabel(draft.rule_type)} 草稿。`,
      },
      {
        label: '扩展建议',
        text: suggestions,
      },
    ],
    nextActionText: '点击“改写规则”回到输入框，把需求拆成当前规则库可表达的字段校验、筛选条件或 Key 对比。',
    rewriteHintText:
      '可尝试改写成：非空、唯一、固定值比较、正则格式、顺序连续、跨表包含、组合分支、跨组 Key 对比、多组串行或多组映射，并明确目标变量、筛选字段、Key 和判断值。',
    resolveActionText: '',
  }
}

export function markAiRuleResultDuplicate(item: AiRuleResultViewModel): AiRuleResultViewModel {
  return {
    ...item,
    status: 'duplicate',
    reasonText: '当前个人校验中已有相同规则，无需重复添加。',
    explanationTitle: '当前个人校验中已有相同规则',
    explanationItems: [
      {
        label: '判定依据',
        text: '系统根据规则类型、目标变量和关键参数判断这条草稿与已有规则重复。',
        tone: 'primary',
      },
      {
        label: '处理方式',
        text: '不会重复添加，避免同一规则在后续校验中产生重复结果。',
      },
    ],
    nextActionText: '如需新增差异规则，请调整规则描述、目标变量或判断条件后重新 AI 校验。',
    rewriteHintText: '',
    resolveActionText: '',
  }
}

function getRuleSourceId(rule: FixedRuleDefinition): string {
  return (
    rule.target_variable_tag?.match(/^\[?([^-_\]]+)/)?.[1] ??
    rule.reference_variable_tag?.match(/^\[?([^-_\]]+)/)?.[1] ??
    '-'
  )
}

function getRuleTargetField(rule: FixedRuleDefinition): string {
  const tag = rule.target_variable_tag ?? ''
  const normalized = tag.replace(/^\[/, '').replace(/\]$/, '')
  const segments = normalized.split('-').filter(Boolean)
  return segments.at(-1) ?? rule.display_field ?? '-'
}

function getRuleTitle(rule: FixedRuleDefinition): string {
  const target = rule.target_variable_tag?.replace(/^\[/, '').replace(/\]$/, '') ?? ''
  if (rule.rule_name?.trim()) return rule.rule_name.trim()
  return target || getAiRuleTypeLabel(rule.rule_type)
}

function getVariableByTag(
  payload: AiRuleDraftPayload,
  rule: FixedRuleDefinition,
): VariableTag | undefined {
  const targetTag = rule.target_variable_tag?.trim()
  return payload.variables_to_add.find((variable) => variable.tag === targetTag)
}

function getSourceById(payload: AiRuleDraftPayload, sourceId?: string): DataSource | undefined {
  if (!sourceId) return undefined
  return payload.sources_to_add.find((source) => source.id === sourceId)
}

function formatSource(source: DataSource | undefined, fallback: string): string {
  if (!source) return fallback || '-'
  return `${source.id}（${getSourceTypeLabel(source.type)}）`
}

function buildRuleMeta(
  rule: FixedRuleDefinition,
  payload: AiRuleDraftPayload,
  reasoningSummary?: string,
  applied = false,
): AiRuleResultViewModel {
  const variable = getVariableByTag(payload, rule)
  const source = getSourceById(payload, variable?.source_id)
  const sourceLabel = formatSource(source, variable?.source_id ?? getRuleSourceId(rule))
  const sheetLabel = variable?.sheet ?? '-'
  const fieldLabel =
    variable?.variable_kind === 'composite'
      ? (variable.columns ?? []).join('、') || '-'
      : variable?.column ?? getRuleTargetField(rule)
  const variableLabel = variable?.tag ?? rule.target_variable_tag ?? '-'
  const groupLabel = rule.group_id || 'AI生成规则组'
  const ruleTypeLabel = getAiRuleTypeLabel(rule.rule_type)
  const metaParts = [
    `规则类型 ${ruleTypeLabel}`,
    `数据源 ${sourceLabel}`,
    `Sheet ${sheetLabel}`,
    `字段 ${fieldLabel}`,
    `变量 ${variableLabel}`,
    `规则组 ${groupLabel}`,
  ]
  const explanation = buildReadyExplanation({
    rule,
    ruleTypeLabel,
    sourceLabel,
    sheetLabel,
    fieldLabel,
    variableLabel,
    reasoningSummary,
    applied,
  })

  return {
    id: rule.rule_id,
    status: applied ? 'applied' : 'ready',
    title: getRuleTitle(rule),
    ruleTypeLabel,
    sourceLabel,
    sheetLabel,
    fieldLabel,
    variableLabel,
    groupLabel,
    metaText: metaParts.join('   '),
    missingText: '',
    reasonText: '',
    ...explanation,
    rule,
  }
}

export function mapAiDraftToResultItems(draft: AiRuleDraft | null): AiRuleResultViewModel[] {
  if (!draft) return []

  const readyItems = draft.draft.rules_to_add.map((rule) =>
    buildRuleMeta(rule, draft.draft, draft.reasoning_summary, draft.applied),
  )

  const missingItems: AiRuleResultViewModel[] = draft.missing.map((item, index) => ({
    id: `missing-${item.kind}-${index}`,
    status: 'needs_input' as const,
    title: `${getMissingReasonCategory(item)}，暂不能自动添加`,
    ruleTypeLabel: getAiRuleTypeLabel(draft.rule_type),
    sourceLabel: '-',
    sheetLabel: '-',
    fieldLabel: '-',
    variableLabel: '-',
    groupLabel: 'AI生成规则组',
    metaText: `缺口类型 ${item.kind} / ${getMissingReasonCategory(item)}`,
    missingText: item.message,
    reasonText: '',
    ...buildMissingExplanation(item, draft.rule_type),
    missing: item,
  }))

  const rejectedItems: AiRuleResultViewModel[] =
    draft.verdict === 'rejected'
      ? [
          {
            id: `rejected-${draft.draft_id ?? draft.created_at ?? 'current'}`,
            status: 'rejected' as const,
            title: draft.reasoning_summary || '当前规则不可添加',
            ruleTypeLabel: getAiRuleTypeLabel(draft.rule_type),
            sourceLabel: '-',
            sheetLabel: '-',
            fieldLabel: '-',
            variableLabel: '-',
            groupLabel: 'AI生成规则组',
            metaText: `规则类型 ${getAiRuleTypeLabel(draft.rule_type)}`,
            missingText: draft.missing.map((item) => item.message).join('；'),
            reasonText: [
              draft.rejection_reason || '当前支持的规则类型无法表达该需求。',
              ...(draft.extension_suggestions ?? []).map((item) => `扩展建议：${item}`),
            ].join('；'),
            ...buildRejectedExplanation(draft),
          },
        ]
      : []

  if (draft.verdict === 'needs_input' && !missingItems.length) {
    missingItems.push({
      id: `needs-input-${draft.draft_id ?? 'current'}`,
      status: 'needs_input',
      title: draft.reasoning_summary || '需要补充规则线索',
      ruleTypeLabel: getAiRuleTypeLabel(draft.rule_type),
      sourceLabel: '-',
      sheetLabel: '-',
      fieldLabel: '-',
      variableLabel: '-',
      groupLabel: 'AI生成规则组',
      metaText: `规则类型 ${getAiRuleTypeLabel(draft.rule_type)}`,
      missingText: '请补充数据源、Sheet、列名或规则参数后重新校验。',
      reasonText: '',
      ...buildMissingExplanation(undefined, draft.rule_type),
    })
  }

  return [...readyItems, ...missingItems, ...rejectedItems]
}

export function buildAiResultSummary(draft: AiRuleDraft | null): AiResultSummaryViewModel {
  const items = mapAiDraftToResultItems(draft)
  const ready = items.filter((item) => item.status === 'ready').length
  const needsInput = items.filter((item) => item.status === 'needs_input').length
  const rejected = items.filter((item) => item.status === 'rejected').length
  const applied = items.filter((item) => item.status === 'applied').length
  const total = items.length
  const label =
    rejected && !ready && !applied
      ? '不可添加'
      : needsInput || rejected
      ? '部分可添加'
      : applied
      ? '已应用'
      : ready
      ? '可添加'
      : '待校验'
  const tone =
    rejected && !ready && !applied
      ? 'danger'
      : needsInput || rejected
      ? 'warning'
      : ready || applied
      ? 'success'
      : 'neutral'

  return {
    total,
    ready,
    needsInput,
    rejected,
    applied,
    label,
    tone,
    text: `共识别 ${total} 条规则：${ready} 条可添加，${needsInput} 条需补充，${rejected} 条不可添加`,
  }
}

export function buildPendingConfigPreview(draft: AiRuleDraft | null): PendingConfigPreviewViewModel {
  if (!draft || draft.verdict === 'rejected') {
    return { sources: [], variables: [], rules: [] }
  }

  return {
    sources: [
      ...draft.draft.sources_to_add.map((source) => `新增 ${source.id}`),
      ...(draft.draft.sources_to_add.length ? [] : ['复用当前数据源']),
    ],
    variables: [
      ...draft.draft.variables_to_add.map((variable) => `新增 ${variable.tag}`),
      ...draft.draft.reuse_variable_tags.map((tag) => `复用 ${tag}`),
    ],
    rules: draft.draft.rules_to_add.map((rule) => `新增 ${rule.rule_name || rule.rule_id}`),
  }
}

function formatHistoryTime(value?: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const now = new Date()
  const sameDay = date.toDateString() === now.toDateString()
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  if (sameDay) return `今天 ${time}`
  if (date.toDateString() === yesterday.toDateString()) return `昨天 ${time}`
  return date.toLocaleString()
}

export function mapDraftToHistoryViewModel(draft: AiRuleDraft): DraftHistoryViewModel {
  const status = normalizeRuleStatus(draft)
  const title =
    draft.draft.rules_to_add[0]?.rule_name ||
    draft.reasoning_summary ||
    (draft.verdict === 'rejected' ? '不可添加规则草稿' : 'AI 规则草稿')
  return {
    id: String(draft.draft_id ?? `${draft.created_at}-${title}`),
    title,
    ruleCount: draft.draft.rules_to_add.length,
    timeLabel: formatHistoryTime(draft.created_at),
    status,
    statusLabel: getStatusLabel(status),
    draft,
  }
}
