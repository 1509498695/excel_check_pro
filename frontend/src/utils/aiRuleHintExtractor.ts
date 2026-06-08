export const SERVER_CONFIG_EXAMPLE_REGEX =
  '^(?:(?:all|\\d+(?:-\\d+)?):[01](;(?:all|\\d+(?:-\\d+)?):[01])*)?$'

const SUPPORTED_RULE_TYPES = [
  'not_null',
  'unique',
  'regex_check',
  'sequence_order_check',
  'fixed_value_compare',
  'cross_table_mapping',
  'composite_condition_check',
  'dual_composite_compare',
  'multi_composite_pipeline_check',
  'multi_composite_mapping_check',
  'package_items_compare',
  'event_task_reward',
  'event_task_validation',
]

const RULE_TYPE_ALIASES: Record<string, string> = {
  非空: 'not_null',
  非空校验: 'not_null',
  不能为空: 'not_null',
  必填: 'not_null',
  唯一: 'unique',
  唯一校验: 'unique',
  不能重复: 'unique',
  不可重复: 'unique',
  固定值: 'fixed_value_compare',
  固定值比较: 'fixed_value_compare',
  枚举: 'fixed_value_compare',
  枚举校验: 'fixed_value_compare',
  正则: 'regex_check',
  正则校验: 'regex_check',
  格式: 'regex_check',
  格式校验: 'regex_check',
  顺序: 'sequence_order_check',
  顺序校验: 'sequence_order_check',
  连续: 'sequence_order_check',
  引用: 'cross_table_mapping',
  引用存在: 'cross_table_mapping',
  包含: 'cross_table_mapping',
  '包含(in)': 'cross_table_mapping',
  字典: 'cross_table_mapping',
  组合分支: 'composite_condition_check',
  组合分支校验: 'composite_condition_check',
  条件分支: 'composite_condition_check',
  跨组变量: 'dual_composite_compare',
  跨组变量校验: 'dual_composite_compare',
  按key对比: 'dual_composite_compare',
  双组合变量: 'dual_composite_compare',
  多组串行: 'multi_composite_pipeline_check',
  多组串行校验: 'multi_composite_pipeline_check',
  多节点串行: 'multi_composite_pipeline_check',
  多组映射: 'multi_composite_mapping_check',
  多组映射校验: 'multi_composite_mapping_check',
  多节点映射: 'multi_composite_mapping_check',
  IAP礼包校验: 'package_items_compare',
  'IAP 礼包校验': 'package_items_compare',
  礼包校验: 'package_items_compare',
  礼包道具校验: 'package_items_compare',
  节日任务校验: 'event_task_reward',
  节日任务奖励校验: 'event_task_reward',
  EventTask校验: 'event_task_reward',
  EventTask奖励校验: 'event_task_reward',
}

const TEMPLATE_LABELS = [
  '数据源',
  '配置表链接',
  '配置表路径',
  'sheet分页',
  'Sheet分页',
  'sheet',
  'Sheet',
  '变量选择',
  '规则类型',
  'rule_type',
  '目标字段',
  '目标',
  '目标列名',
  '校验字段',
  '筛选条件',
  '筛选',
  '左侧筛选',
  '右侧筛选',
  'Key字段',
  'Key 字段',
  'Key值选择',
  'Key选择',
  'Key值',
  '选择Key',
  'Key',
  '关联Key',
  '引用对象',
  '比较字段',
  '筛选规则1',
  '筛选规则2',
  '校验规则',
  '最终判定',
  '校验判定',
  '判定',
  '断言',
  '规则参数',
  '规则是',
  '补充说明',
]

const TEMPLATE_PLACEHOLDERS = [
  '配置表链接',
  'sheet名',
  '变量1,变量2',
  '目标字段',
  '从 not_null / unique / fixed_value_compare / regex_check / sequence_order_check / cross_table_mapping / composite_condition_check / dual_composite_compare / multi_composite_pipeline_check / multi_composite_mapping_check / package_items_compare 中选择',
  '字段或内容',
  '全部数据 / 满足 xxx 的数据',
  '字段名',
  '不能为空 / 不能重复 / 只能是 A,B,C / 必须等于字段 X / 必须存在于引用表 / 匹配正则 xxx',
  '可选，比如排序方向、正则、引用表、比较字段',
]

export interface ExtractedSmartRuleHints {
  ruleTypeHint?: string
  targetVariableTag?: string
  referenceVariableTag?: string
  leftVariableTag?: string
  rightVariableTag?: string
  sourceId?: string
  sourceUrl?: string
  sheet?: string
  targetField?: string
  filterField?: string
  filterOperator?: string
  filterValue?: string
  assertionField?: string
  assertionOperator?: string
  assertionValue?: string
  assertionValueSource?: string
  assertionExpectedField?: string
  operator?: string
  expectedValue?: string
  expectedValueMode?: string
  displayField?: string
  regexPattern?: string
  sequenceDirection?: string
  sequenceStep?: string
  sequenceStartMode?: string
  sequenceStartValue?: string
  keyColumn?: string
  compositeColumns?: string
  leftFilterField?: string
  leftFilterOperator?: string
  leftFilterValue?: string
  rightFilterField?: string
  rightFilterOperator?: string
  rightFilterValue?: string
  leftKeyField?: string
  rightKeyField?: string
  compareOperator?: string
  keyCheckMode?: string
  compareFields?: string
}

export function extractSmartRuleWorkflowHints(text: string): ExtractedSmartRuleHints {
  const normalizedText = normalizeText(text)
  const templateSections = extractTemplateSections(text)
  const naturalTargetText = extractNaturalTargetText(normalizedText)
  const naturalFilterText = extractNaturalFilterText(normalizedText)
  const naturalRuleText = extractNaturalRuleText(normalizedText)
  const naturalExtraText = extractNaturalExtraText(normalizedText)
  const explicitRuleSemanticText = [
    templateSections['规则类型'],
    templateSections['校验规则'],
    templateSections['规则是'],
    templateSections['判定'],
    templateSections['最终判定'],
    templateSections['校验判定'],
    templateSections['断言'],
    templateSections['规则参数'],
    templateSections['补充说明'],
    naturalRuleText,
    naturalExtraText,
  ].filter(Boolean).join(' ')
  const ruleSemanticText = explicitRuleSemanticText || normalizedText
  const sourceValue = extractSourceValue(normalizedText)
  const sourceUrl =
    sourceValue && looksLikeSourcePathOrUrl(sourceValue)
      ? sourceValue
      : extractSourceUrl(normalizedText)
  const sourceId = sourceUrl ? deriveSourceId(sourceUrl) : sourceValue
  const sheet = extractSheet(normalizedText)
  const templateColumns = extractTemplateVariableColumns(normalizedText)
  const explicitRuleTypeHint = normalizeRuleType(templateSections['规则类型'] ?? templateSections.rule_type)
  let ruleTypeHint = explicitRuleTypeHint ?? extractRuleTypeHint(templateSections, ruleSemanticText || normalizedText)
  const targetVariableTag = extractLabeledVariableTag(normalizedText, ['目标变量', '变量'])
  const referenceVariableTag = extractLabeledVariableTag(normalizedText, ['引用变量', '字典变量'])
  const leftVariableTag = extractLabeledVariableTag(normalizedText, ['左侧变量', '基准变量'])
  const rightVariableTag = extractLabeledVariableTag(normalizedText, ['右侧变量', '对比变量'])
  const dualFilters = extractDualFilters(normalizedText)
  const templateKeyColumn = extractTemplateKeyColumn(templateSections)
  const naturalKeyColumn = extractNaturalKeyColumn(normalizedText)
  const templateFilter = extractTemplateFilter(templateSections)
  const naturalFilter = naturalFilterText ? parseFilterExpressionWithOperator(naturalFilterText) : {}
  const filter = templateFilter.filterField ? templateFilter : extractFilter(normalizedText)
  const activeFilter = templateFilter.filterField ? templateFilter : naturalFilter.filterField ? naturalFilter : filter
  const filterOperator =
    activeFilter.filterOperator || extractFilterOperator(naturalFilterText || normalizedText, activeFilter.filterField)
  let displayField = extractDisplayField(normalizedText)
  let keyColumn = templateKeyColumn ?? naturalKeyColumn ?? extractKeyColumn(normalizedText)
  const compareFields = extractCompareFields(normalizedText, {
    keyColumn,
    filterFields: [activeFilter.filterField, dualFilters.leftFilterField, dualFilters.rightFilterField],
    displayField,
  }).filter((field) => ![sheet, sourceId, sourceUrl ? deriveSourceId(sourceUrl) : undefined].includes(field))
  if (
    looksLikeDualCompareShape(normalizedText, {
      leftFilterField: dualFilters.leftFilterField,
      leftFilterValue: dualFilters.leftFilterValue,
      rightFilterField: dualFilters.rightFilterField,
      rightFilterValue: dualFilters.rightFilterValue,
      keyColumn,
      compareFields,
    })
  ) {
    ruleTypeHint = 'dual_composite_compare'
  }
  const templateTargetField = extractTemplateFieldValue(
    templateSections['目标字段'] ?? templateSections['目标'] ?? templateSections['目标列名'] ?? templateSections['校验字段'],
  )
  const naturalTargetField = extractTemplateFieldValue(naturalTargetText)
  const targetField = templateTargetField || naturalTargetField || extractTargetField(normalizedText, {
    filterField: activeFilter.filterField,
    displayField,
    keyColumn: ruleTypeHint === 'dual_composite_compare' ? undefined : keyColumn,
    compareFields,
  }) || templateColumns[0]
  const ruleParameterText = [
    templateSections['校验规则'],
    templateSections['规则是'],
    templateSections['判定'],
    templateSections['最终判定'],
    templateSections['校验判定'],
    templateSections['断言'],
    templateSections['规则参数'],
    templateSections['补充说明'],
    naturalRuleText,
    naturalExtraText,
  ].filter(Boolean).join('\n') || normalizedText
  let regexPattern = extractRegexPattern(ruleParameterText)
  const compareOperator = extractDualCompareOperator(ruleParameterText)
  const keyCheckMode = extractKeyCheckMode(normalizedText)
  let filterField = ruleTypeHint === 'dual_composite_compare' ? undefined : activeFilter.filterField
  let filterValue = ruleTypeHint === 'dual_composite_compare' ? undefined : activeFilter.filterValue
  let normalizedFilterOperator = ruleTypeHint === 'dual_composite_compare' ? undefined : filterOperator
  const fixedValue = extractFixedValueCompare(ruleParameterText)
  let assertion = extractAssertionCompare(
    ruleParameterText,
    {
    filterField,
    candidateFields: [...templateColumns, keyColumn ?? '', targetField ?? ''],
    },
  )
  if (!assertion.assertionField && targetField) {
    assertion = extractTargetBasedAssertion(
      [
        naturalRuleText,
        naturalExtraText,
        templateSections['校验规则'],
        templateSections['规则是'],
        templateSections['判定'],
        templateSections['最终判定'],
        templateSections['校验判定'],
        templateSections['断言'],
      ].filter(Boolean).join('\n'),
      targetField,
    ) ?? assertion
  }
  if (
    filterField === assertion.assertionField &&
    normalizedFilterOperator === 'not_null' &&
    assertion.assertionOperator === 'not_null' &&
    !templateFilter.filterField &&
    !naturalFilter.filterField
  ) {
    filterField = undefined
    filterValue = undefined
    normalizedFilterOperator = undefined
  }
  if (
    assertion.assertionValueSource === 'field' &&
    assertion.assertionExpectedField &&
    (!explicitRuleTypeHint || explicitRuleTypeHint === 'composite_condition_check')
  ) {
    ruleTypeHint = 'composite_condition_check'
  }
  if (
    ruleTypeHint !== 'dual_composite_compare' &&
    (!explicitRuleTypeHint || explicitRuleTypeHint === 'composite_condition_check') &&
    filterField &&
    filterValue &&
    assertion.assertionField &&
    (assertion.assertionValue || assertion.assertionExpectedField || assertion.assertionOperator)
  ) {
    ruleTypeHint = 'composite_condition_check'
  }
  const sequence = extractSequence(ruleParameterText)

  if (sourceId === 'server_config' && sheet === 'switch' && targetField === 'STR_ServersParam') {
    ruleTypeHint = 'composite_condition_check'
    keyColumn ||= 'INT_Id'
    displayField ||= 'STR_Func'
    filterField ||= 'DES'
    filterValue ||= '废弃'
    normalizedFilterOperator = 'not_contains'
    regexPattern ||= SERVER_CONFIG_EXAMPLE_REGEX
  }

  const compositeColumns = [
    ...buildCompositeColumns({
      keyColumn,
      displayField,
      targetField,
      filterField,
      leftFilterField: dualFilters.leftFilterField,
      rightFilterField: dualFilters.rightFilterField,
      assertionField: assertion.assertionField,
      compareFields,
    }),
    ...templateColumns,
  ].filter((value, index, array) => value && array.indexOf(value) === index).join(',')

  return compactHints({
    ruleTypeHint,
    targetVariableTag: targetVariableTag || leftVariableTag,
    referenceVariableTag: referenceVariableTag || rightVariableTag,
    leftVariableTag,
    rightVariableTag,
    sourceId,
    sourceUrl,
    sheet,
    targetField: ruleTypeHint === 'dual_composite_compare' ? targetField || keyColumn : targetField,
    filterField,
    filterOperator: normalizedFilterOperator,
    filterValue,
    assertionField: assertion.assertionField,
    assertionOperator: assertion.assertionOperator,
    assertionValue: assertion.assertionValue,
    assertionValueSource: assertion.assertionValueSource,
    assertionExpectedField: assertion.assertionExpectedField,
    displayField,
    operator: fixedValue.operator,
    expectedValue: fixedValue.expectedValue,
    expectedValueMode: fixedValue.expectedValueMode,
    regexPattern,
    sequenceDirection: sequence.sequenceDirection,
    sequenceStep: sequence.sequenceStep,
    sequenceStartMode: sequence.sequenceStartMode,
    sequenceStartValue: sequence.sequenceStartValue,
    keyColumn,
    compositeColumns,
    leftFilterField: dualFilters.leftFilterField,
    leftFilterOperator: dualFilters.leftFilterOperator,
    leftFilterValue: dualFilters.leftFilterValue,
    rightFilterField: dualFilters.rightFilterField,
    rightFilterOperator: dualFilters.rightFilterOperator,
    rightFilterValue: dualFilters.rightFilterValue,
    leftKeyField: ruleTypeHint === 'dual_composite_compare' ? keyColumn : undefined,
    rightKeyField: ruleTypeHint === 'dual_composite_compare' ? keyColumn : undefined,
    compareOperator: ruleTypeHint === 'dual_composite_compare' ? compareOperator : undefined,
    keyCheckMode,
    compareFields: compareFields.join(','),
  })
}

function normalizeText(text: string): string {
  return text
    .replaceAll('\r', ' ')
    .replaceAll('\n', ' ')
    .replaceAll('“', '"')
    .replaceAll('”', '"')
    .replaceAll('‘', "'")
    .replaceAll('’', "'")
    .trim()
}

function unwrapNaturalValue(value?: string): string | undefined {
  const text = value
    ?.trim()
    .replace(/^【|】$/g, '')
    .replace(/[；;。]$/, '')
    .trim()
  if (!text || TEMPLATE_PLACEHOLDERS.includes(text) || /【|】/.test(text)) return undefined
  return text
}

function extractNaturalTargetText(text: string): string | undefined {
  const value = firstMatch(text, [/我想检查\s*([^。；;\n\r]+)/i])
  return unwrapNaturalValue(value)
}

function extractNaturalFilterText(text: string): string | undefined {
  const value = unwrapNaturalValue(firstMatch(text, [/只检查\s*([^。；;\n\r]+)/i]))
  if (!value || /^(全部数据|所有数据|无|不限制)$/i.test(value)) return undefined
  return value.replace(/^满足\s*/, '').replace(/(?:的)?数据$/, '').trim()
}

function extractNaturalRuleText(text: string): string | undefined {
  return unwrapNaturalValue(firstMatch(text, [/(?:规则是|判定|最终判定|校验判定)\s*[：:=]?\s*([^。；;\n\r]+)/i]))
}

function extractNaturalExtraText(text: string): string | undefined {
  const value = unwrapNaturalValue(firstMatch(text, [/补充说明\s*[：:=]?\s*([^。；;\n\r]+)/i]))
  return value && !/^(无|可选|无需)$/i.test(value) ? value : undefined
}

function extractNaturalKeyColumn(text: string): string | undefined {
  const value = firstMatch(text, [
    /(?:Key值选择|Key选择|Key值|选择Key)\s*[：:=]?\s*([A-Za-z][A-Za-z0-9_]*)/i,
    /用\s*([A-Za-z][A-Za-z0-9_]*)\s*(?:字段)?\s*作为\s*(?:Key|key|主键|唯一键)/i,
  ])
  return value && !isPlaceholderKeyColumn(value) ? value : undefined
}

function extractSourceUrl(text: string): string | undefined {
  return text.match(/https?:\/\/[A-Za-z0-9_./:%?=&~#+-]+\.xls[xm]?/i)?.[0]
}

function extractSourceValue(text: string): string | undefined {
  return extractTemplateValue(text, ['数据源', '配置表链接', '配置表路径'])
}

function extractSheet(text: string): string | undefined {
  return extractTemplateValue(text, ['sheet分页', 'Sheet分页', 'sheet', 'Sheet']) ?? firstMatch(text, [
    /\$?\s*([A-Za-z][A-Za-z0-9_]*)\s*(?:分页|页签|工作表|sheet|Sheet)/i,
    /(?:Sheet|sheet)\s*[：:=为是]?\s*([A-Za-z][A-Za-z0-9_]*)/i,
  ])
}

function extractTemplateVariableColumns(text: string): string[] {
  const value = extractTemplateValue(text, ['变量选择', '变量'])
  if (!value) return []
  return value
    .replaceAll('，', ',')
    .split(',')
    .map((item) => item.trim())
    .filter((item) => /^[A-Za-z][A-Za-z0-9_]*$/.test(item))
}

function extractTemplateValue(text: string, labels: string[]): string | undefined {
  text = normalizeInlineTemplateLabels(text)
  const labelPattern = labels.map(escapeRegExp).join('|')
  const stopLabels = TEMPLATE_LABELS.map(escapeRegExp).join('|')
  const match = text.match(new RegExp(`(?:${labelPattern})\\s*[：:=]\\s*(.*?)(?=\\s*(?:${stopLabels})\\s*[：:=]|$)`, 'i'))
  const value = match?.[1]?.trim()
  if (!value || TEMPLATE_PLACEHOLDERS.includes(value)) {
    return undefined
  }
  return value.replace(/[；;。]$/, '').trim()
}

function extractTemplateSections(text: string): Record<string, string> {
  text = normalizeInlineTemplateLabels(text)
  const labelPattern = TEMPLATE_LABELS.map(escapeRegExp).join('|')
  const sections: Record<string, string[]> = {}
  let currentLabel = ''
  for (const rawLine of text.replaceAll('\r', '\n').split('\n')) {
    const line = rawLine.trim()
    if (!line) continue
    const match = line.match(new RegExp(`^(${labelPattern})\\s*[：:=]\\s*(.*)$`, 'i'))
    if (match?.[1]) {
      currentLabel = match[1]
      sections[currentLabel] = sections[currentLabel] ?? []
      sections[currentLabel].push(match[2]?.trim() ?? '')
    } else if (currentLabel) {
      sections[currentLabel].push(line)
    }
  }
  return Object.fromEntries(
    Object.entries(sections)
      .map(([label, values]) => [
        label,
        values
          .filter((value) => value.trim())
          .join('\n')
          .replace(/[；;。]$/, '')
          .trim(),
      ])
      .filter(([, value]) => value),
  )
}

function normalizeInlineTemplateLabels(text: string): string {
  const labelPattern = TEMPLATE_LABELS.map(escapeRegExp).join('|')
  return text.replace(new RegExp(`([,，；;]\\s*)(${labelPattern})\\s*[：:=]`, 'gi'), (_match, _prefix, label: string) => `\n${label}：`)
}

function extractRuleTypeHint(sections: Record<string, string>, text: string): string | undefined {
  return normalizeRuleType(sections['规则类型'] ?? sections.rule_type) ?? inferRuleType(text)
}

function normalizeRuleType(value?: string): string | undefined {
  if (!value?.trim() || TEMPLATE_PLACEHOLDERS.includes(value.trim())) return undefined
  const text = value.trim()
  for (const item of text.split(/[/,，、；;\s]+/)) {
    const candidate = item.trim()
    if (!candidate) continue
    if (SUPPORTED_RULE_TYPES.includes(candidate)) return candidate
    const alias = RULE_TYPE_ALIASES[candidate] ?? RULE_TYPE_ALIASES[candidate.toLowerCase()]
    if (alias) return alias
  }
  for (const [alias, ruleType] of Object.entries(RULE_TYPE_ALIASES)) {
    if (text.includes(alias)) return ruleType
  }
  return SUPPORTED_RULE_TYPES.find((ruleType) => text.includes(ruleType))
}

function extractTemplateFieldValue(value?: string): string | undefined {
  if (isEmptyTemplateSection(value)) return undefined
  const text = value?.trim().replace(/(?:字段|列名|列)$/, '').trim() ?? ''
  const field = text.match(/\b[A-Z][A-Za-z0-9]*_[A-Za-z0-9_]+\b/)?.[0]
  if (field) return field
  return /^[A-Za-z][A-Za-z0-9_]*$/.test(text) && !TEMPLATE_PLACEHOLDERS.includes(text) ? text : undefined
}

function extractTemplateKeyColumn(sections: Record<string, string>): string | undefined {
  const explicitKey = extractTemplateFieldValue(
    sections['Key字段']
      ?? sections['Key 字段']
      ?? sections['Key值选择']
      ?? sections['Key选择']
      ?? sections['Key值']
      ?? sections['选择Key']
      ?? sections.Key
      ?? sections['关联Key'],
  )
  if (explicitKey) return explicitKey
  for (const label of ['筛选', '筛选条件', '筛选规则1', '筛选规则2', '补充说明']) {
    const value = sections[label] ?? ''
    if (isEmptyTemplateSection(value)) continue
    const match = value.match(/([A-Za-z][A-Za-z0-9_]*)\s*(?:字段)?\s*(?:唯一|不能重复|不可重复|unique)/i)
    if (match?.[1]) return match[1].trim()
  }
  return undefined
}

function extractTemplateFilter(sections: Record<string, string>): { filterField?: string; filterValue?: string; filterOperator?: string } {
  for (const label of ['筛选', '筛选条件', '筛选规则1', '筛选规则2']) {
    const value = sections[label] ?? ''
    if (isEmptyTemplateSection(value)) continue
    if (label === '筛选条件' && /(?:左侧|右侧|left|right)/i.test(value)) continue
    for (const item of splitFilterItems(value)) {
      if (/(?:唯一|不能重复|不可重复|必须重复|需要重复|至少一组重复|unique|duplicate_required)/i.test(item)) continue
      const filter = parseFilterExpressionWithOperator(item)
      if (filter.filterField && filterValueIsPresent(filter.filterOperator, filter.filterValue)) return filter
    }
  }
  return {}
}

function splitFilterItems(value: string): string[] {
  const text = value.replaceAll('\r', '\n')
  const lines = text
    .split('\n')
    .map((line) => line.replace(/^\s*[-*]\s*/, '').trim())
    .filter(Boolean)
  if (lines.length > 1) return lines
  const commaItems = text
    .split(/[,，]\s*(?=[A-Za-z][A-Za-z0-9_]*\s*(?:字段)?\s*(?:唯一|不能重复|不可重复|unique|!=|=|>|<|等于|不等于|大于|小于|非空|不能为空|not\s*null|not_null))/i)
    .map((item) => item.trim())
    .filter(Boolean)
  if (commaItems.length > 1) return commaItems
  return text
    .split(/[；;]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function isEmptyTemplateSection(value?: string): boolean {
  if (!value?.trim()) return true
  return ['无', '空', 'none', 'null', '-'].includes(value.trim().toLowerCase())
}

function looksLikeSourcePathOrUrl(value: string): boolean {
  return (
    /^(https?:|svn:)/i.test(value) ||
    /^[A-Za-z]:[\\/]/.test(value) ||
    /^\\\\/.test(value) ||
    value.includes('/') ||
    value.includes('\\') ||
    /\.xls[xm]?($|[?#])/i.test(value)
  )
}

function extractFilter(text: string): { filterField?: string; filterValue?: string; filterOperator?: string } {
  const parsed = parseFilterExpressionWithOperator(text)
  if (parsed.filterField && filterValueIsPresent(parsed.filterOperator, parsed.filterValue)) return parsed
  const patterns = [
    /(?:筛选规则\d*)\s*[：:=]\s*([A-Za-z][A-Za-z0-9_]*)\s*=\s*([^。；;\n\r]+)/i,
    /(?:筛选|过滤)\s*([A-Za-z][A-Za-z0-9_]*)\s*=\s*([^。；;\n\r]+)/i,
    /(?:筛选|过滤)[^。；;\n\r]*?([A-Za-z][A-Za-z0-9_]*)\s*(?:等于|为|是)\s*([^。；;\n\r]+)/i,
    /(?:过滤掉|过滤|排除)[^，。；;]*?([A-Za-z][A-Za-z0-9_]*)\s*字段[^，。；;]*?(?:包含|含有)\s*["']?([^"'，。；;、\s]+)/i,
    /([A-Za-z][A-Za-z0-9_]*)\s*字段[^，。；;]*?(?:包含|含有)\s*["']?([^"'，。；;、\s]+)[^，。；;]*?(?:过滤|排除)/i,
    /([A-Za-z][A-Za-z0-9_]*)\s*=\s*([^,，。；;\s]+)/i,
  ]
  for (const pattern of patterns) {
    const match = text.match(pattern)
    if (match?.[1] && match[2]) {
      const filterValue = cleanFilterValue(trimFilterTail(match[2]))
      if (/^[A-Z][A-Za-z0-9]*_[A-Za-z0-9_]+$/.test(filterValue)) continue
      return {
        filterField: match[1].trim(),
        filterValue,
      }
    }
  }
  return {}
}

function extractFilterOperator(
  text: string,
  filterField?: string,
): string | undefined {
  if (!filterField) return undefined
  const lower = text.toLowerCase()
  if (text.includes('不包含') || text.includes('过滤掉') || text.includes('排除') || lower.includes('not_contains') || lower.includes('not contains')) return 'not_contains'
  if (text.includes('包含') || text.includes('含有') || lower.includes('contains')) return 'contains'
  if (text.includes('不等于') || text.includes('!=')) return 'ne'
  if (text.includes('大于') || text.includes('>')) return 'gt'
  if (text.includes('小于') || text.includes('<')) return 'lt'
  if (/(?:非空|不能为空|not\s*null|not_null)/i.test(text)) return 'not_null'
  return 'eq'
}

function cleanFilterValue(value: string): string {
  const cleaned = cleanSetValue(value)
  return cleaned.replace(/(?:的)?(?:字段|列|行|数据|记录|配置)$/, '').trim() || cleaned
}

function trimFilterTail(value: string): string {
  return value
    .trim()
    .split(/(?:[,，]\s*)?(?:以|按)\s*[A-Za-z][A-Za-z0-9_]*\s*(?:字段)?\s*(?:为|作为)?\s*(?:Key|key|主键|唯一键)/, 1)[0]
    .split(/(?:[,，]\s*)?(?:判断|比较|比对|校验|检查)\s*[：:]/, 1)[0]
    .split(/(?:[,，]\s*)?(?:Key值选择|Key选择|Key值|选择Key|最终判定|校验判定|判定|断言|校验规则)\s*[：:]/i, 1)[0]
    .split(/[,，]\s*[A-Za-z][A-Za-z0-9_]*\s*(?:=|!=|>|<|等于|不等于|大于|小于|必须等于字段|等于字段)/, 1)[0]
    .trim()
}

function extractAssertionCompare(
  text: string,
  options: {
    filterField?: string
    candidateFields?: string[]
  } = {},
): {
  assertionField?: string
  assertionOperator?: string
  assertionValue?: string
  assertionValueSource?: string
  assertionExpectedField?: string
} {
  const candidateFieldSet = new Set((options.candidateFields ?? []).filter(Boolean))
  const fieldComparePattern = /([A-Za-z][A-Za-z0-9_]*)\s*(?:字段)?\s*(=|等于字段|等于\s*字段|必须等于字段|不等于字段|大于字段|小于字段)\s*([A-Za-z][A-Za-z0-9_]*)\b/gi
  for (const fieldCompare of text.matchAll(fieldComparePattern)) {
    if (!fieldCompare?.[1] || !fieldCompare[2] || !fieldCompare[3]) continue
    const field = fieldCompare[1].trim()
    const expectedField = fieldCompare[3].trim()
    if (
      (!options.filterField || field !== options.filterField) &&
      (candidateFieldSet.has(field) || candidateFieldSet.has(expectedField) || /^[A-Z][A-Za-z0-9]*_[A-Za-z0-9_]+$/.test(expectedField))
    ) {
      return {
        assertionField: field,
        assertionOperator: operatorFromText(fieldCompare[2]),
        assertionValueSource: 'field',
        assertionExpectedField: expectedField,
      }
    }
  }
  const patterns = [
    /([A-Za-z][A-Za-z0-9_]*)\s*字段\s*(=|!=|>|<|等于|不等于|大于|小于)\s*([^。；;\n\r]+)/gi,
    /(?:校验|验证|检查)\s*([A-Za-z][A-Za-z0-9_]*)\s*字段\s*(等于|不等于|大于|小于|=|!=|>|<|为|是)\s*([^。；;\n\r]+)/gi,
    /([A-Za-z][A-Za-z0-9_]*)\s*字段\s*(等于|不等于|大于|小于|=|!=|>|<|为|是)\s*([^。；;\n\r]+)/gi,
    /([A-Za-z][A-Za-z0-9_]*)\s*(=|!=|>|<|等于|不等于|大于|小于)\s*([^。；;\n\r]+)/gi,
  ]
  for (const pattern of patterns) {
    for (const match of text.matchAll(pattern)) {
      if (!match?.[1] || !match[2] || !match[3]) continue
      const field = match[1].trim()
      if (options.filterField && field === options.filterField) continue
      const value = cleanSetValue(match[3])
      if (/^[A-Z][A-Za-z0-9]*_[A-Za-z0-9_]+$/.test(value)) {
        return {
          assertionField: field,
          assertionOperator: operatorFromText(match[2]),
          assertionValueSource: 'field',
          assertionExpectedField: value,
        }
      }
      return {
        assertionField: field,
        assertionOperator: operatorFromText(match[2]),
        assertionValue: value,
      }
    }
  }
  const setStyle = text.match(/([A-Za-z][A-Za-z0-9_]*)\s*(?:字段)?\s*(必须重复|需要重复|至少一组重复|至少重复|duplicate_required|唯一|不能重复|不可重复|unique)/i)
  if (setStyle?.[1] && setStyle[2]) {
    const operatorText = setStyle[2]
    return {
      assertionField: setStyle[1].trim(),
      assertionOperator:
        (/duplicate_required/i.test(operatorText) || (/重复/.test(operatorText) && !/(不能|不可|唯一)/.test(operatorText)))
          ? 'duplicate_required'
          : 'unique',
    }
  }
  const notNull = text.match(/([A-Za-z][A-Za-z0-9_]*)\s*(?:字段)?\s*(?:不能为空|非空|必填|not\s*null|not_null)/i)
  if (notNull?.[1]) {
    return {
      assertionField: notNull[1].trim(),
      assertionOperator: 'not_null',
    }
  }
  const regexMatch = text.match(/([A-Za-z][A-Za-z0-9_]*)\s*(?:字段)?\s*(?:匹配正则|正则|regex)\s*[：:=]?\s*([^。；;\n\r]+)/i)
  if (regexMatch?.[1] && regexMatch[2]) {
    return {
      assertionField: regexMatch[1].trim(),
      assertionOperator: 'regex',
      assertionValue: regexMatch[2].trim(),
    }
  }
  return {}
}

function extractTargetBasedAssertion(
  text: string,
  targetField: string,
):
  | {
      assertionField?: string
      assertionOperator?: string
      assertionValue?: string
      assertionValueSource?: string
      assertionExpectedField?: string
    }
  | undefined {
  if (!text.trim()) return undefined
  const expectedField = firstMatch(text, [
    /(?:=|等于字段|等于\s*字段|必须等于字段|必须\s*等于\s*字段)\s*([A-Za-z][A-Za-z0-9_]*)\b/i,
  ])
  if (expectedField) {
    return {
      assertionField: targetField,
      assertionOperator: 'eq',
      assertionValueSource: 'field',
      assertionExpectedField: expectedField,
    }
  }
  if (/(不能为空|非空|必填|not\s*null|not_null)/i.test(text)) {
    return {
      assertionField: targetField,
      assertionOperator: 'not_null',
    }
  }
  if (/(必须重复|需要重复|至少一组重复|至少重复|duplicate_required)/i.test(text)) {
    return {
      assertionField: targetField,
      assertionOperator: 'duplicate_required',
    }
  }
  if (/(唯一|不能重复|不可重复|unique)/i.test(text)) {
    return {
      assertionField: targetField,
      assertionOperator: 'unique',
    }
  }
  const regexPattern = extractRegexPattern(text)
  if (regexPattern) {
    return {
      assertionField: targetField,
      assertionOperator: 'regex',
      assertionValue: regexPattern,
    }
  }
  return undefined
}

function cleanSetValue(value: string): string {
  return value
    .trim()
    .replace(/^["']|["']$/g, '')
    .replace(/\s+(?:or|OR)\s+/g, ',')
    .replaceAll('，', ',')
    .replaceAll('、', ',')
    .replace(/(?:,\s*)?(?:两种类型|两个类型|两类|两种|这些类型|这几种类型|多个类型|多个值)$/, '')
    .replace(/\s+/g, '')
    .replace(/,+/g, ',')
    .replace(/^,|,$/g, '')
}

function extractDisplayField(text: string): string | undefined {
  return firstMatch(text, [
    /(?:结果显示|显示字段|展示字段|结果字段)\s*[：:=为是]?\s*([A-Za-z][A-Za-z0-9_]*)/i,
    /([A-Za-z][A-Za-z0-9_]*)\s*(?:作为|为)\s*(?:结果显示|展示字段)/i,
  ])
}

function extractTargetField(
  text: string,
  excluded: {
    filterField?: string
    displayField?: string
    keyColumn?: string
    compareFields?: string[]
  },
): string | undefined {
  const explicit = firstMatch(text, [
    /(?:校验|验证|检查)\s*([A-Za-z][A-Za-z0-9_]*)\s*字段/i,
    /([A-Za-z][A-Za-z0-9_]*)\s*字段[^，。；;]*?(?:配置数据格式|配置格式|格式)/i,
    /(?:目标字段|目标列名|校验字段)\s*[：:=为是]?\s*([A-Za-z][A-Za-z0-9_]*)/i,
  ])
  if (explicit) return explicit

  const excludedValues = new Set(
    [excluded.filterField, excluded.displayField, excluded.keyColumn, ...(excluded.compareFields ?? [])].filter(
      Boolean,
    ),
  )
  for (const match of text.matchAll(/([A-Za-z][A-Za-z0-9_]*)\s*字段/g)) {
    const candidate = match[1]
    if (!excludedValues.has(candidate)) return candidate
  }
  return undefined
}

function extractKeyColumn(text: string): string | undefined {
  const candidate =
    firstMatch(text, [
      /([A-Za-z][A-Za-z0-9_]*)\s*(?:字段)?\s*(?:唯一|不能重复|不可重复|unique)/i,
      /(?:Key|key|索引|主键|唯一键)\s*(?:列|字段)?\s*[：:=为是]?\s*([A-Za-z][A-Za-z0-9_]*)/i,
      /([A-Za-z][A-Za-z0-9_]*)\s*字段\s*(?:作为|为)\s*(?:Key|key|索引|主键|唯一键)/i,
      /([A-Za-z][A-Za-z0-9_]*)\s*(?:作为|为)\s*(?:Key|key|索引|主键|唯一键)/i,
    ]) ?? text.match(/\bINT_Id\b/)?.[0]
  return candidate && !isPlaceholderKeyColumn(candidate) ? candidate : undefined
}

function extractRegexPattern(text: string): string | undefined {
  const explicit = firstMatch(text, [
    /(?:正则|regex|pattern)\s*[：:=]\s*([^。；;\n\r]+)/i,
  ])
  if (explicit) return explicit.trim().replace(/^["']|["']$/g, '')
  if (text.includes('冒号') && (text.includes('只能配置 1 或 0') || text.includes('只能配置1或0'))) {
    return SERVER_CONFIG_EXAMPLE_REGEX
  }
  if ((text.includes('冒号') || text.includes(':')) && /(?:1\s*(?:或|or|\/)\s*0|0\s*(?:或|or|\/)\s*1)/i.test(text)) {
    return SERVER_CONFIG_EXAMPLE_REGEX
  }
  if (/\d+\s*:\s*[01](?:\s*;\s*\d+\s*:\s*[01])+/.test(text)) {
    return SERVER_CONFIG_EXAMPLE_REGEX
  }
  return undefined
}

function inferRuleType(text: string): string | undefined {
  for (const ruleType of SUPPORTED_RULE_TYPES) {
    if (new RegExp(`(^|\\s)${escapeRegExp(ruleType)}(\\s|$)`, 'i').test(text)) return ruleType
  }
  let rawExplicit = firstMatch(text, [
    /(?:规则类型|rule_type)\s*[：:=]\s*([^。；;\n\r]+)/i,
    /(?:规则类型|rule_type)\s+([^。；;\n\r]+)/i,
  ])
  if (rawExplicit) {
    for (const label of TEMPLATE_LABELS) {
      if (['规则类型', 'rule_type'].includes(label)) continue
      rawExplicit = rawExplicit.split(new RegExp(`\\s*${escapeRegExp(label)}\\s*[：:=]`, 'i'), 1)[0]
    }
  }
  const explicit = normalizeRuleType(rawExplicit)
  if (explicit) {
    return explicit
  }
  const lower = text.toLowerCase()
  if (/(公式|聚合|平均|求和|脚本|计算后|跨行统计)/.test(text)) return undefined
  if (/(两组|两个配置|两份配置|是不是相等|是否相等)/.test(text) && /(以|key|Key|筛选)/.test(text)) {
    return 'dual_composite_compare'
  }
  if (/(多组串行|多节点串行|多级链路|链路|pipeline)/.test(text)) return 'multi_composite_pipeline_check'
  if (/(多组映射|多节点映射|映射校验|mapping)/.test(text)) return 'multi_composite_mapping_check'
  if (/(存在于|字典表|字典变量|包含\(in\)| in )/.test(text) && /(另一|引用|字典|表)/.test(text)) {
    return 'cross_table_mapping'
  }
  if (/(筛选|过滤|当|如果)/.test(text) && /(校验|检查|判断|必须|格式|正则)/.test(text)) {
    return 'composite_condition_check'
  }
  if (/(不能为空|非空|必填|not null|not_null)/i.test(text)) return 'not_null'
  if (/(唯一|不能重复|不可重复|unique)/i.test(text)) return 'unique'
  if (/(升序|降序|递增|递减|连续|步长|顺序|sequence)/i.test(text)) return 'sequence_order_check'
  if (/(正则|格式|匹配|regex)/i.test(text)) return 'regex_check'
  if (/(等于|不等于|大于|小于|只能是|必须是|=|!=|>|<)/.test(text)) return 'fixed_value_compare'
  if (lower.includes('not_null')) return 'not_null'
  if (lower.includes('unique')) return 'unique'
  return undefined
}

function extractLabeledVariableTag(text: string, labels: string[]): string | undefined {
  const labelPattern = labels.map((label) => label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')
  return firstMatch(text, [
    new RegExp(`(?:${labelPattern})\\s*[：:=]\\s*(\\[[^\\]\\r\\n]+\\])`, 'i'),
  ])
}

function extractDualFilters(text: string): {
  leftFilterField?: string
  leftFilterOperator?: string
  leftFilterValue?: string
  rightFilterField?: string
  rightFilterOperator?: string
  rightFilterValue?: string
} {
  const leftSection = extractTemplateValue(text, ['筛选规则1'])
  const rightSection = extractTemplateValue(text, ['筛选规则2'])
  const leftFilter = parseFilterExpressionWithOperator(leftSection ?? '')
  const rightFilter = parseFilterExpressionWithOperator(rightSection ?? '')
  if (
    leftFilter.filterField &&
    filterValueIsPresent(leftFilter.filterOperator, leftFilter.filterValue) &&
    rightFilter.filterField &&
    filterValueIsPresent(rightFilter.filterOperator, rightFilter.filterValue) &&
    leftFilter.filterField === rightFilter.filterField
  ) {
    return {
      leftFilterField: leftFilter.filterField,
      leftFilterOperator: leftFilter.filterOperator ?? 'eq',
      leftFilterValue: leftFilter.filterValue,
      rightFilterField: rightFilter.filterField,
      rightFilterOperator: rightFilter.filterOperator ?? 'eq',
      rightFilterValue: rightFilter.filterValue,
    }
  }

  const filterSection = extractTemplateValue(text, ['筛选', '筛选条件'])
  if (filterSection) {
    const leftItem = firstMatch(filterSection, [/(?:左侧|left)\s*([^；;\n\r]+)/i])
    const rightItem = firstMatch(filterSection, [/(?:右侧|right)\s*([^；;\n\r]+)/i])
    const leftFilter = parseFilterExpressionWithOperator(leftItem ?? '')
    const rightFilter = parseFilterExpressionWithOperator(rightItem ?? '')
    if (
      leftFilter.filterField &&
      rightFilter.filterField &&
      leftFilter.filterField === rightFilter.filterField &&
      filterValueIsPresent(leftFilter.filterOperator, leftFilter.filterValue) &&
      filterValueIsPresent(rightFilter.filterOperator, rightFilter.filterValue)
    ) {
      return {
        leftFilterField: leftFilter.filterField,
        leftFilterOperator: leftFilter.filterOperator ?? 'eq',
        leftFilterValue: leftFilter.filterValue,
        rightFilterField: rightFilter.filterField,
        rightFilterOperator: rightFilter.filterOperator ?? 'eq',
        rightFilterValue: rightFilter.filterValue,
      }
    }
    const commonFilter = parseFilterExpressionWithOperator(filterSection)
    const splitValues = splitDualFilterValues(commonFilter.filterValue)
    if (
      hasDualCompareTextSignal(text) &&
      commonFilter.filterField &&
      (commonFilter.filterOperator ?? 'eq') === 'eq' &&
      splitValues
    ) {
      return {
        leftFilterField: commonFilter.filterField,
        leftFilterOperator: 'eq',
        leftFilterValue: splitValues[0],
        rightFilterField: commonFilter.filterField,
        rightFilterOperator: 'eq',
        rightFilterValue: splitValues[1],
      }
    }
  }

  const patterns = [
    /筛选\s*[：:]?\s*[-*]?\s*([A-Za-z][A-Za-z0-9_]*)\s*(=|!=|>|<|等于|不等于|大于|小于)\s*([^和，。；;\s]+)\s*和\s*\1\s*(=|!=|>|<|等于|不等于|大于|小于)\s*([^，。；;\s]+)/i,
    /筛选[^，。；;]*?([A-Za-z][A-Za-z0-9_]*)\s*(等于|不等于|大于|小于|=|!=|>|<)\s*([^和，。；;\s]+)\s*和\s*\1\s*(等于|不等于|大于|小于|=|!=|>|<)\s*([^，。；;\s]+)/i,
    /(?:筛选|过滤)\s*[：:]?\s*[-*]?\s*([A-Za-z][A-Za-z0-9_]*)\s*=\s*([^,，。；;\s]+)\s*[,，]\s*([^,，。；;\s]+)/i,
  ]
  for (const pattern of patterns) {
    const match = text.match(pattern)
    if (match?.[1] && match[2] && match[3] && match[4] && match[5]) {
      return {
        leftFilterField: match[1].trim(),
        leftFilterOperator: operatorFromText(match[2]),
        leftFilterValue: cleanFilterValue(match[3]),
        rightFilterField: match[1].trim(),
        rightFilterOperator: operatorFromText(match[4]),
        rightFilterValue: cleanFilterValue(match[5]),
      }
    }
    if (match?.[1] && match[2] && match[3] && !match[4] && hasDualCompareTextSignal(text)) {
      return {
        leftFilterField: match[1].trim(),
        leftFilterOperator: 'eq',
        leftFilterValue: cleanFilterValue(match[2]),
        rightFilterField: match[1].trim(),
        rightFilterOperator: 'eq',
        rightFilterValue: cleanFilterValue(match[3]),
      }
    }
  }
  const values = Array.from(text.matchAll(/([A-Za-z][A-Za-z0-9_]*)\s*(=|!=|>|<|等于|不等于|大于|小于)\s*([^和，。；;\s]+)/g))
  if (values.length >= 2 && values[0][1] === values[1][1]) {
    return {
      leftFilterField: values[0][1].trim(),
      leftFilterOperator: operatorFromText(values[0][2]),
      leftFilterValue: cleanFilterValue(values[0][3]),
      rightFilterField: values[1][1].trim(),
      rightFilterOperator: operatorFromText(values[1][2]),
      rightFilterValue: cleanFilterValue(values[1][3]),
    }
  }
  return {}
}

function splitDualFilterValues(value?: string): [string, string] | undefined {
  if (!value) return undefined
  const values = value
    .split(/[,，]/)
    .map((item) => item.trim())
    .filter(Boolean)
  return values.length === 2 ? [values[0], values[1]] : undefined
}

function hasDualCompareTextSignal(text: string): boolean {
  return /(两组|两个配置|两份配置|左右|相等|一致|相同)/.test(text) && /(Key|key|主键|唯一键|对齐)/.test(text)
}

function looksLikeDualCompareShape(
  text: string,
  options: {
    leftFilterField?: string
    leftFilterValue?: string
    rightFilterField?: string
    rightFilterValue?: string
    keyColumn?: string
    compareFields: string[]
  },
): boolean {
  if (
    !options.leftFilterField ||
    !options.leftFilterValue ||
    !options.rightFilterField ||
    !options.rightFilterValue ||
    options.leftFilterField !== options.rightFilterField ||
    !options.keyColumn ||
    !options.compareFields.length
  ) {
    return false
  }
  return /(相等|一致|相同|不相等|不一致)/.test(text) && /(判断|比较|比对|校验|检查|判定|断言)/.test(text)
}

function parseFilterExpressionWithOperator(text: string): { filterField?: string; filterValue?: string; filterOperator?: string } {
  const notNullMatch = text.match(/([A-Za-z][A-Za-z0-9_]*)\s*(?:字段)?\s*(?:非空|不能为空|not\s*null|not_null)/i)
  if (notNullMatch?.[1]) {
    return {
      filterField: notNullMatch[1].trim(),
      filterValue: '',
      filterOperator: 'not_null',
    }
  }
  const containsMatch = text.match(/([A-Za-z][A-Za-z0-9_]*)\s*(?:not_contains|not\s+contains|不包含|排除|过滤掉|contains|包含|含有)\s*([^。；;\n\r]+)/i)
  if (containsMatch?.[1] && containsMatch[2]) {
    const operatorText = containsMatch[0].toLowerCase()
    return {
      filterField: containsMatch[1].trim(),
      filterValue: cleanFilterValue(trimFilterTail(containsMatch[2])),
      filterOperator:
        operatorText.includes('not_contains') ||
        operatorText.includes('not contains') ||
        /(?:不包含|排除|过滤掉)/.test(containsMatch[0])
          ? 'not_contains'
          : 'contains',
    }
  }
  const match = text.match(/([A-Za-z][A-Za-z0-9_]*)\s*(?:!=|不等于|不能是|不可为|>|<|=|等于|为|是|大于|小于)\s*([^。；;\n\r]+)/i)
  if (!match?.[1] || !match[2]) return {}
  return {
    filterField: match[1].trim(),
    filterValue: cleanFilterValue(trimFilterTail(match[2])),
    filterOperator: operatorFromText(match[0]),
  }
}

function filterValueIsPresent(operator?: string, value?: string): boolean {
  return operator === 'not_null' || Boolean(value)
}

function operatorFromText(text: string): string {
  if (/(?:!=|不等于|不能是|不可为)/.test(text)) return 'ne'
  if (/(?:>|大于)/.test(text)) return 'gt'
  if (/(?:<|小于)/.test(text)) return 'lt'
  return 'eq'
}

function extractCompareFields(
  text: string,
  excluded: {
    keyColumn?: string
    filterFields?: Array<string | undefined>
    displayField?: string
  },
): string[] {
  const explicit = firstMatch(text, [
      /(?:比较字段|比对字段)\s*[：:=]\s*([^。；;]+)/i,
      /(?:判断|比较|比对|校验)([^。；;]*?)(?:这|的)?(?:四个|多个|这些)?字段/i,
      /(?:四个|多个|这些)字段[：:=为是]?\s*([^。；;]+)/i,
    ])
  const source = explicit ?? text
  const excludedValues = new Set(
    [excluded.keyColumn, excluded.displayField, ...(excluded.filterFields ?? [])].filter(Boolean),
  )
  const result: string[] = []
  const candidates = Array.from(source.matchAll(/\b[A-Z][A-Za-z0-9]*_[A-Za-z0-9_]+\b/g)).map((match) => match[0])
  if (explicit && candidates.length === 0) {
    candidates.push(
      ...explicit
        .split(/[,，、/\s]+/)
        .map((item) => item.trim())
        .filter((item) => /^[A-Za-z][A-Za-z0-9_]*$/.test(item)),
    )
  }
  for (const candidate of candidates) {
    if (!excludedValues.has(candidate) && !result.includes(candidate)) {
      result.push(candidate)
    }
  }
  return result
}

function extractFixedValueCompare(text: string): {
  operator?: string
  expectedValue?: string
  expectedValueMode?: string
} {
  if (/(等于\s*字段|必须\s*等于\s*字段)/i.test(text)) {
    return {}
  }
  if (/(不能为空|非空|必填|not\s*null|not_null)/i.test(text) && !/(期望值|比较值|固定值|只能是|必须是|等于|不等于|大于|小于|!=|>|<)/i.test(text)) {
    return {}
  }
  const patterns: Array<[RegExp, string]> = [
    [/(?:期望值|比较值|固定值)\s*[：:=]\s*["']?([^"'，。；;、\s]+)/i, 'eq'],
    [/(?:只能是|必须是|等于|为|是)\s*["']?([^"'，。；;、\s]+)/i, 'eq'],
    [/(?:不等于|不能是|不可为|!=)\s*["']?([^"'，。；;、\s]+)/i, 'ne'],
    [/(?:大于|>)\s*["']?([^"'，。；;、\s]+)/i, 'gt'],
    [/(?:小于|<)\s*["']?([^"'，。；;、\s]+)/i, 'lt'],
  ]
  for (const [pattern, operator] of patterns) {
    const match = text.match(pattern)
    if (match?.[1]) {
      const expectedValue = match[1].trim().replaceAll('，', ',')
      if (looksLikeMetaExpectedValue(expectedValue)) {
        continue
      }
      return {
        operator,
        expectedValue,
        expectedValueMode: /[,，或]/.test(match[1]) ? 'set' : 'single',
      }
    }
  }
  return {}
}

function extractDualCompareOperator(text: string): string | undefined {
  if (/(?:非空|不能为空|not\s*null|not_null)/i.test(text)) return 'not_null'
  if (/(?:不相等|不一致|不等于|!=)/.test(text)) return 'ne'
  if (/(?:大于|>)/.test(text)) return 'gt'
  if (/(?:小于|<)/.test(text)) return 'lt'
  if (/(?:相等|一致|相同|等于|=)/.test(text)) return 'eq'
  return undefined
}

function extractKeyCheckMode(text: string): string | undefined {
  if (/(?:双向检查|双向校验|双向对比|两边都要有|左右都要有|bidirectional)/i.test(text)) return 'bidirectional'
  if (/(?:基准变量为准|以左侧为准|以基准为准|baseline_only)/i.test(text)) return 'baseline_only'
  return undefined
}

function looksLikeMetaExpectedValue(value: string): boolean {
  return value.startsWith('更适合') || value.startsWith('适合') || ['AI', 'ai', '解析'].includes(value)
}

function extractSequence(text: string): {
  sequenceDirection?: string
  sequenceStep?: string
  sequenceStartMode?: string
  sequenceStartValue?: string
} {
  const sequenceDirection = /(降序|递减|方向\s*[：:=]\s*降序)/.test(text)
    ? 'desc'
    : /(升序|递增|连续|顺序|方向\s*[：:=]\s*升序)/.test(text)
      ? 'asc'
      : undefined
  const sequenceStep = text.match(/步长\s*[：:=为是]?\s*(\d+)/)?.[1]
  const sequenceStartValue = text.match(/(?:起始值|起始|从)\s*[：:=为是]?\s*(\d+)/)?.[1]
  const autoStart = /(?:起始值|起始)\s*[：:=为是]?\s*(?:自动|auto)/i.test(text)
  return {
    sequenceDirection,
    sequenceStep,
    sequenceStartMode: sequenceStartValue ? 'manual' : autoStart || sequenceDirection ? 'auto' : undefined,
    sequenceStartValue,
  }
}

function buildCompositeColumns(values: {
  keyColumn?: string
  displayField?: string
  targetField?: string
  filterField?: string
  leftFilterField?: string
  rightFilterField?: string
  assertionField?: string
  compareFields?: string[]
}): string[] {
  const result: string[] = []
  for (const value of [
    values.keyColumn,
    values.displayField,
    values.targetField,
    values.filterField,
    values.assertionField,
    values.leftFilterField,
    values.rightFilterField,
    ...(values.compareFields ?? []),
  ]) {
    if (value && !isPlaceholderKeyColumn(value) && !result.includes(value)) {
      result.push(value)
    }
  }
  return result
}

function isPlaceholderKeyColumn(value?: string): boolean {
  if (!value?.trim()) return false
  if (value.includes('未识别') || value.includes('需要用户确认')) return true
  const compact = value.replace(/[\s:：=为是列字段、，。；;]/g, '').toLowerCase()
  return ['key', '关联key', '业务key', '比对key', '对齐key', '主键', '唯一键', '索引'].includes(compact)
}

function firstMatch(text: string, patterns: RegExp[]): string | undefined {
  for (const pattern of patterns) {
    const match = text.match(pattern)
    if (match?.[1]) {
      return match[1].trim()
    }
  }
  return undefined
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function deriveSourceId(sourceUrl?: string): string | undefined {
  if (!sourceUrl) return undefined
  const fileName = sourceUrl.split(/[?#]/)[0].split('/').pop() ?? ''
  const stem = fileName.includes('.') ? fileName.slice(0, fileName.lastIndexOf('.')) : fileName
  const sourceId = stem.replace(/[^A-Za-z0-9_]+/g, '_').replace(/^_+|_+$/g, '')
  return sourceId || undefined
}

function compactHints(hints: ExtractedSmartRuleHints): ExtractedSmartRuleHints {
  return Object.fromEntries(
    Object.entries(hints).filter(([, value]) => typeof value === 'string' && value.trim()),
  ) as ExtractedSmartRuleHints
}
