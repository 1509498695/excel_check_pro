import type { AiRuleWorkflowHints } from '../types/ai'
import type { FixedRuleType } from '../types/fixedRules'
import type { VariableTag } from '../types/workbench'

export type AiRuleTemplateVariableKind = 'single' | 'composite' | 'dual_composite' | 'multi_composite' | 'any'
export type AiRuleTemplateCategory = 'basic' | 'compare' | 'format' | 'mapping' | 'composite' | 'auto_complete'
export type AiRuleTemplateSource = 'template' | 'recommendation'

export interface AiRuleTemplate {
  id: string
  source: AiRuleTemplateSource
  title: string
  summary: string
  recommendReason?: string
  category: AiRuleTemplateCategory
  categoryLabel: string
  variableKind: AiRuleTemplateVariableKind
  variableKindLabel: string
  ruleType: FixedRuleType
  ruleTypeLabel: string
  descriptionTemplate: string
  workflowHints: AiRuleWorkflowHints
  minSelectedVariables?: number
  requiresAutoComplete?: boolean
  priority?: number
}

export interface AiRuleTemplateFilterOptions {
  selectedVariables: VariableTag[]
  allowAutoComplete: boolean
}

export interface AiRuleTemplateApplyResult {
  description: string
  workflowHints: AiRuleWorkflowHints
  allowAutoComplete: boolean
}

const TEMPLATE_LABELS: Record<FixedRuleType, string> = {
  not_null: '非空校验',
  unique: '唯一校验',
  fixed_value_compare: '固定值比较',
  regex_check: '正则校验',
  sequence_order_check: '顺序校验',
  cross_table_mapping: '包含(in)',
  composite_condition_check: '组合分支校验',
  dual_composite_compare: '跨组变量校验',
  multi_composite_pipeline_check: '多组串行校验',
  multi_composite_mapping_check: '多组映射校验',
  package_items_compare: 'IAP礼包校验',
  event_task_reward: '节日任务奖励校验',
  event_task_validation: '节日任务奖励校验（兼容）',
}

const CATEGORY_LABELS: Record<AiRuleTemplateCategory, string> = {
  basic: '基础',
  compare: '比较',
  format: '格式',
  mapping: '映射',
  composite: '组合',
  auto_complete: '自动补齐',
}

const VARIABLE_KIND_LABELS: Record<AiRuleTemplateVariableKind, string> = {
  single: '单变量',
  composite: '组合变量',
  dual_composite: '双组合变量',
  multi_composite: '多组合变量',
  any: '任意变量',
}

function buildShortRuleDescription(options: {
  ruleType: FixedRuleType
  targetField?: string
  filterCondition?: string
  keyField?: string
  referenceObject?: string
  compareFields?: string
  validationRule: string
  ruleParams?: string
}): string {
  const targetText = options.targetField?.trim()
  const filterText = options.filterCondition && options.filterCondition !== '无' ? options.filterCondition : '无'
  const keyText = options.keyField && options.keyField !== '无' ? options.keyField : '无'
  const assertion = targetText && !options.validationRule.includes(targetText)
    ? `${targetText} ${options.validationRule}`
    : options.validationRule
  const extraItems = [
    options.referenceObject && options.referenceObject !== '无' ? `引用对象=${options.referenceObject}` : '',
    options.compareFields && options.compareFields !== '无' ? `比较字段=${options.compareFields}` : '',
    options.ruleParams && options.ruleParams !== '无' ? options.ruleParams : '',
  ].filter(Boolean)
  return [
    '筛选：',
    `- ${filterText}`,
    keyText !== '无' ? `- ${keyText} 唯一` : '',
    '',
    `Key值选择：${keyText}`,
    '',
    `判定：${assertion}`,
    '',
    extraItems.length ? `补充说明：${extraItems.join('；')}` : '',
  ].filter((line, index, array) => line || (array[index - 1] && array[index + 1])).join('\n')
}

const AI_RULE_TEMPLATES: AiRuleTemplate[] = [
  template({
    id: 'single-not-null',
    title: '字段不能为空',
    summary: '检查目标字段是否存在空值。',
    category: 'basic',
    variableKind: 'single',
    ruleType: 'not_null',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'not_null',
      targetField: '{targetField}',
      validationRule: '{targetField} 不能为空',
    }),
    workflowHints: {
      rule_type_hint: 'not_null',
    },
  }),
  template({
    id: 'single-unique',
    title: '字段不能重复',
    summary: '检查 ID、名称等字段是否唯一。',
    category: 'basic',
    variableKind: 'single',
    ruleType: 'unique',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'unique',
      targetField: '{targetField}',
      validationRule: '{targetField} 不能重复',
    }),
    workflowHints: {
      rule_type_hint: 'unique',
    },
  }),
  template({
    id: 'single-fixed-set',
    title: '只能取固定值',
    summary: '适合状态、开关、枚举字段。',
    category: 'compare',
    variableKind: 'single',
    ruleType: 'fixed_value_compare',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'fixed_value_compare',
      targetField: '{targetField}',
      validationRule: '{targetField} 只能是 0,1,2',
      ruleParams: '期望值=0,1,2；期望值模式=set',
    }),
    workflowHints: {
      rule_type_hint: 'fixed_value_compare',
      operator: 'eq',
      expected_value: '0,1,2',
      expected_value_mode: 'set',
    },
  }),
  template({
    id: 'single-regex',
    title: '字段格式匹配',
    summary: '适合编码、Key、资源名格式。',
    category: 'format',
    variableKind: 'single',
    ruleType: 'regex_check',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'regex_check',
      targetField: '{targetField}',
      validationRule: '{targetField} 匹配正则',
      ruleParams: '正则=^[A-Za-z0-9_]+$',
    }),
    workflowHints: {
      rule_type_hint: 'regex_check',
      regex_pattern: '^[A-Za-z0-9_]+$',
    },
  }),
  template({
    id: 'single-sequence',
    title: '字段连续递增',
    summary: '检查等级、序号等字段是否连续。',
    category: 'compare',
    variableKind: 'single',
    ruleType: 'sequence_order_check',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'sequence_order_check',
      targetField: '{targetField}',
      validationRule: '{targetField} 按升序连续',
      ruleParams: '方向=升序；步长=1；起始=自动',
    }),
    workflowHints: {
      rule_type_hint: 'sequence_order_check',
      sequence_direction: 'asc',
      sequence_step: '1',
      sequence_start_mode: 'auto',
    },
  }),
  template({
    id: 'single-cross-table-mapping',
    title: '必须包含在字典中',
    summary: '检查目标字段是否存在于另一个变量。',
    category: 'mapping',
    variableKind: 'single',
    ruleType: 'cross_table_mapping',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'cross_table_mapping',
      targetField: '{targetField}',
      referenceObject: '{referenceTag}',
      validationRule: '{targetField} 必须存在于引用对象',
    }),
    workflowHints: {
      rule_type_hint: 'cross_table_mapping',
    },
    minSelectedVariables: 2,
  }),
  template({
    id: 'composite-condition-not-null',
    title: '筛选后字段非空',
    summary: '适合“满足条件的行，某字段必填”。',
    category: 'composite',
    variableKind: 'composite',
    ruleType: 'composite_condition_check',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'composite_condition_check',
      targetField: '{assertionField}',
      filterCondition: '{filterField}=示例值',
      keyField: '{keyColumn}',
      validationRule: '{assertionField} 不能为空',
    }),
    workflowHints: {
      rule_type_hint: 'composite_condition_check',
      filter_operator: 'eq',
      filter_value: '示例值',
      assertion_operator: 'not_null',
    },
  }),
  template({
    id: 'composite-condition-duplicate-required',
    title: '筛选后字段必须重复',
    summary: '适合“命中条件的数据里，某字段至少出现一组重复值”。',
    category: 'composite',
    variableKind: 'composite',
    ruleType: 'composite_condition_check',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'composite_condition_check',
      targetField: '{assertionField}',
      filterCondition: '{filterField}!=示例值',
      keyField: '{keyColumn}',
      validationRule: '{assertionField} 必须重复',
    }),
    workflowHints: {
      rule_type_hint: 'composite_condition_check',
      filter_operator: 'ne',
      filter_value: '示例值',
      assertion_operator: 'duplicate_required',
    },
  }),
  template({
    id: 'composite-condition-regex',
    title: '筛选后字段格式匹配',
    summary: '适合“满足条件后，字段必须符合正则格式”。',
    category: 'format',
    variableKind: 'composite',
    ruleType: 'composite_condition_check',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'composite_condition_check',
      targetField: '{assertionField}',
      filterCondition: '{filterField}=示例值',
      keyField: '{keyColumn}',
      validationRule: '{assertionField} 匹配正则',
      ruleParams: '正则=^[A-Za-z0-9_]+$',
    }),
    workflowHints: {
      rule_type_hint: 'composite_condition_check',
      filter_operator: 'eq',
      filter_value: '示例值',
      assertion_operator: 'regex',
      regex_pattern: '^[A-Za-z0-9_]+$',
    },
  }),
  template({
    id: 'composite-condition-compare',
    title: '筛选后字段比较',
    summary: '适合“命中条件后，字段需要大于/小于/不等于某值”。',
    category: 'compare',
    variableKind: 'composite',
    ruleType: 'composite_condition_check',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'composite_condition_check',
      targetField: '{assertionField}',
      filterCondition: '{filterField}>示例值',
      keyField: '{keyColumn}',
      validationRule: '{assertionField} 不等于 0',
    }),
    workflowHints: {
      rule_type_hint: 'composite_condition_check',
      filter_operator: 'gt',
      filter_value: '示例值',
      assertion_operator: 'ne',
      assertion_value: '0',
    },
  }),
  template({
    id: 'dual-composite-compare',
    title: '两组配置按 Key 对比',
    summary: '适合同表不同筛选结果或两张表字段对齐。',
    category: 'composite',
    variableKind: 'dual_composite',
    ruleType: 'dual_composite_compare',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'dual_composite_compare',
      filterCondition: '左侧 {leftFilterField}=示例A；右侧 {rightFilterField}=示例B',
      keyField: '{keyColumn}',
      compareFields: '{compareFields}',
      validationRule: '左右两组按 Key 对齐后比较字段必须相等',
    }),
    workflowHints: {
      rule_type_hint: 'dual_composite_compare',
      left_filter_operator: 'eq',
      left_filter_value: '示例A',
      right_filter_operator: 'eq',
      right_filter_value: '示例B',
    },
    minSelectedVariables: 2,
  }),
  template({
    id: 'dual-composite-not-equal',
    title: '两组配置按 Key 不等值对比',
    summary: '适合左右筛选后按 Key 对齐，字段必须不相等的场景。',
    category: 'composite',
    variableKind: 'dual_composite',
    ruleType: 'dual_composite_compare',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'dual_composite_compare',
      filterCondition: '左侧 {leftFilterField}=示例A；右侧 {rightFilterField}=示例B',
      keyField: '{keyColumn}',
      compareFields: '{compareFields}',
      validationRule: '左右两组按 Key 对齐后比较字段必须不相等',
      ruleParams: 'Key检查=双向检查',
    }),
    workflowHints: {
      rule_type_hint: 'dual_composite_compare',
      left_filter_operator: 'eq',
      left_filter_value: '示例A',
      right_filter_operator: 'eq',
      right_filter_value: '示例B',
      compare_operator: 'ne',
      key_check_mode: 'bidirectional',
    },
    minSelectedVariables: 2,
  }),
  template({
    id: 'multi-composite-pipeline',
    title: '多组串行检查',
    summary: '按节点顺序检查多个组合变量。',
    category: 'composite',
    variableKind: 'multi_composite',
    ruleType: 'multi_composite_pipeline_check',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'multi_composite_pipeline_check',
      targetField: '目标字段',
      validationRule: '按多组串行节点执行筛选和断言',
      ruleParams: '节点1 -> 节点2 -> 节点3；每个节点填写变量、筛选和断言',
    }),
    workflowHints: {
      rule_type_hint: 'multi_composite_pipeline_check',
    },
  }),
  template({
    id: 'multi-composite-mapping',
    title: '多组映射检查',
    summary: '适合多个组合变量分别按筛选条件检查。',
    category: 'mapping',
    variableKind: 'multi_composite',
    ruleType: 'multi_composite_mapping_check',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'multi_composite_mapping_check',
      targetField: '目标字段',
      validationRule: '按多组映射节点独立筛选和判断',
      ruleParams: '节点1：变量={targetTag}；筛选=...；断言=...；排除范围=无',
    }),
    workflowHints: {
      rule_type_hint: 'multi_composite_mapping_check',
    },
  }),
  template({
    id: 'auto-complete-source-variable',
    title: '从描述补齐配置',
    summary: '未建变量时，先写清路径、Sheet、字段和规则。',
    category: 'auto_complete',
    variableKind: 'any',
    ruleType: 'composite_condition_check',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'composite_condition_check',
      targetField: '请填写字段',
      filterCondition: '请填写条件',
      keyField: '无',
      validationRule: '请填写字段不能为空',
    }),
    workflowHints: {
      rule_type_hint: 'composite_condition_check',
      filter_operator: 'eq',
      assertion_operator: 'not_null',
    },
    requiresAutoComplete: true,
  }),
]

export function getAiRuleTemplates(): AiRuleTemplate[] {
  return AI_RULE_TEMPLATES.map(cloneTemplate)
}

export function getAvailableAiRuleTemplates(options: AiRuleTemplateFilterOptions): AiRuleTemplate[] {
  const selectedVariables = options.selectedVariables.filter(Boolean)
  const singleCount = selectedVariables.filter(isSingleVariable).length
  const compositeCount = selectedVariables.filter(isCompositeVariable).length

  return AI_RULE_TEMPLATES.filter((item) => {
    if (item.requiresAutoComplete && !options.allowAutoComplete) {
      return false
    }
    if (!selectedVariables.length) {
      return true
    }
    if (item.variableKind === 'any') {
      return true
    }
    const minSelectedVariables = item.minSelectedVariables ?? 1
    if (item.variableKind === 'single') {
      return singleCount >= minSelectedVariables
    }
    if (item.variableKind === 'composite') {
      return compositeCount >= minSelectedVariables
    }
    if (item.variableKind === 'dual_composite') {
      return compositeCount >= Math.max(2, minSelectedVariables)
    }
    if (item.variableKind === 'multi_composite') {
      return compositeCount >= minSelectedVariables
    }
    return false
  }).map(cloneTemplate)
}

export function getRecommendedAiRuleTemplates(selectedVariables: VariableTag[]): AiRuleTemplate[] {
  const variables = selectedVariables.filter(Boolean)
  const singleVariables = variables.filter(isSingleVariable)
  const compositeVariables = variables.filter(isCompositeVariable)
  const recommendations: AiRuleTemplate[] = []

  singleVariables.forEach((variable) => {
    recommendations.push(...buildSingleVariableRecommendations(variable))
  })

  if (singleVariables.length >= 2) {
    recommendations.push(buildCrossTableRecommendation(singleVariables[0], singleVariables[1]))
  }

  compositeVariables.forEach((variable) => {
    recommendations.push(buildCompositeConditionRecommendation(variable))
  })

  if (compositeVariables.length >= 2) {
    recommendations.push(buildDualCompositeRecommendation(compositeVariables[0], compositeVariables[1]))
    recommendations.push(buildMultiCompositePipelineRecommendation(compositeVariables))
    recommendations.push(buildMultiCompositeMappingRecommendation(compositeVariables))
  }

  return recommendations
    .sort((left, right) => getTemplatePriority(right) - getTemplatePriority(left))
    .map(cloneTemplate)
}

export function applyAiRuleTemplate(
  templateId: string,
  templates: AiRuleTemplate[],
  selectedVariables: VariableTag[],
): AiRuleTemplateApplyResult {
  const selectedTemplate = templates.find((item) => item.id === templateId)
  if (!selectedTemplate) {
    throw new Error(`未找到规则模板：${templateId}`)
  }
  if (selectedTemplate.source === 'recommendation') {
    return {
      description: selectedTemplate.descriptionTemplate,
      workflowHints: cloneWorkflowHints(selectedTemplate.workflowHints),
      allowAutoComplete: Boolean(selectedTemplate.requiresAutoComplete),
    }
  }

  const selectedSingleVariables = selectedVariables.filter(isSingleVariable)
  const selectedCompositeVariables = selectedVariables.filter(isCompositeVariable)
  const targetVariable = selectedVariables[0]
  const referenceVariable = selectedVariables[1]
  const firstSingleVariable = selectedSingleVariables[0]
  const secondSingleVariable = selectedSingleVariables[1]
  const firstCompositeVariable = selectedCompositeVariables[0]
  const secondCompositeVariable = selectedCompositeVariables[1]
  const mainVariable =
    selectedTemplate.variableKind === 'single'
      ? firstSingleVariable
      : firstCompositeVariable ?? targetVariable

  const renderContext = buildRenderContext({
    targetVariable: mainVariable,
    referenceVariable:
      selectedTemplate.variableKind === 'single'
        ? secondSingleVariable ?? referenceVariable
        : secondCompositeVariable ?? referenceVariable,
    selectedCompositeVariables,
  })
  const workflowHints = mergeTemplateHints(selectedTemplate, {
    targetVariable: mainVariable,
    referenceVariable:
      selectedTemplate.variableKind === 'single'
        ? secondSingleVariable ?? referenceVariable
        : secondCompositeVariable ?? referenceVariable,
    firstCompositeVariable,
    secondCompositeVariable,
    selectedCompositeVariables,
  })

  return {
    description: renderTemplateText(selectedTemplate.descriptionTemplate, renderContext),
    workflowHints,
    allowAutoComplete: Boolean(selectedTemplate.requiresAutoComplete),
  }
}

function template(
  input: Omit<AiRuleTemplate, 'categoryLabel' | 'variableKindLabel' | 'ruleTypeLabel' | 'source'>,
): AiRuleTemplate {
  return {
    source: 'template',
    ...input,
    categoryLabel: CATEGORY_LABELS[input.category],
    variableKindLabel: VARIABLE_KIND_LABELS[input.variableKind],
    ruleTypeLabel: TEMPLATE_LABELS[input.ruleType],
  }
}

function recommendation(
  input: Omit<AiRuleTemplate, 'categoryLabel' | 'variableKindLabel' | 'ruleTypeLabel' | 'source'>,
): AiRuleTemplate {
  return {
    ...input,
    source: 'recommendation',
    categoryLabel: CATEGORY_LABELS[input.category],
    variableKindLabel: VARIABLE_KIND_LABELS[input.variableKind],
    ruleTypeLabel: TEMPLATE_LABELS[input.ruleType],
  }
}

function cloneTemplate(templateItem: AiRuleTemplate): AiRuleTemplate {
  return {
    ...templateItem,
    workflowHints: cloneWorkflowHints(templateItem.workflowHints),
  }
}

function cloneWorkflowHints(hints: AiRuleWorkflowHints): AiRuleWorkflowHints {
  return JSON.parse(JSON.stringify(hints)) as AiRuleWorkflowHints
}

function isSingleVariable(variable?: VariableTag): boolean {
  return Boolean(variable) && (variable?.variable_kind ?? 'single') === 'single'
}

function isCompositeVariable(variable?: VariableTag): boolean {
  return Boolean(variable) && (variable?.variable_kind ?? 'single') === 'composite'
}

function buildSingleVariableRecommendations(variable: VariableTag): AiRuleTemplate[] {
  const field = variable.column || '目标字段'
  const baseHints = buildSingleVariableHints(variable)
  const identityLike = isIdentityField(field)
  const enumLike = isEnumLikeField(field)
  const sequenceLike = isSequenceLikeField(field) || variable.expected_type === 'int'
  const formatLike = identityLike || isCodeLikeField(field)
  const expectedSet = enumLike ? '0,1' : '0,1,2'

  return [
    recommendation({
      id: `recommended-single-not-null-${toTemplateId(variable.tag)}`,
      title: `${field} 不能为空`,
      summary: '基于已选单变量生成非空检查。',
      recommendReason: `已选变量 ${variable.tag} 绑定字段 ${field}，适合先保护必填值。`,
      category: 'basic',
      variableKind: 'single',
      ruleType: 'not_null',
      descriptionTemplate: buildShortRuleDescription({
        ruleType: 'not_null',
        targetField: field,
        validationRule: `${field} 不能为空`,
      }),
      workflowHints: {
        ...baseHints,
        rule_type_hint: 'not_null',
      },
      priority: identityLike ? 98 : 72,
    }),
    recommendation({
      id: `recommended-single-unique-${toTemplateId(variable.tag)}`,
      title: `${field} 不能重复`,
      summary: '适合 ID、Key、Code、名称等唯一标识。',
      recommendReason: identityLike
        ? `${field} 看起来像标识字段，推荐检查唯一性。`
        : `可用于确认 ${field} 是否存在重复值。`,
      category: 'basic',
      variableKind: 'single',
      ruleType: 'unique',
      descriptionTemplate: buildShortRuleDescription({
        ruleType: 'unique',
        targetField: field,
        validationRule: `${field} 不能重复`,
      }),
      workflowHints: {
        ...baseHints,
        rule_type_hint: 'unique',
      },
      priority: identityLike ? 96 : 50,
    }),
    recommendation({
      id: `recommended-single-regex-${toTemplateId(variable.tag)}`,
      title: `${field} 格式检查`,
      summary: '按常见配置字段格式生成正则检查线索。',
      recommendReason: formatLike
        ? `${field} 看起来像编码或标识字段，推荐校验字符格式。`
        : `可用于限制 ${field} 的文本格式。`,
      category: 'format',
      variableKind: 'single',
      ruleType: 'regex_check',
      descriptionTemplate: buildShortRuleDescription({
        ruleType: 'regex_check',
        targetField: field,
        validationRule: `${field} 匹配正则`,
        ruleParams: '正则=^[A-Za-z0-9_]+$',
      }),
      workflowHints: {
        ...baseHints,
        rule_type_hint: 'regex_check',
        regex_pattern: '^[A-Za-z0-9_]+$',
      },
      priority: formatLike ? 90 : 44,
    }),
    recommendation({
      id: `recommended-single-fixed-set-${toTemplateId(variable.tag)}`,
      title: `${field} 固定取值`,
      summary: '适合开关、状态、类型、枚举字段。',
      recommendReason: enumLike
        ? `${field} 看起来像状态/开关/类型字段，推荐限制固定取值。`
        : `可用于把 ${field} 限定在允许值集合内。`,
      category: 'compare',
      variableKind: 'single',
      ruleType: 'fixed_value_compare',
      descriptionTemplate: buildShortRuleDescription({
        ruleType: 'fixed_value_compare',
        targetField: field,
        validationRule: `${field} 只能是 ${expectedSet}`,
        ruleParams: `期望值=${expectedSet}；期望值模式=set`,
      }),
      workflowHints: {
        ...baseHints,
        rule_type_hint: 'fixed_value_compare',
        operator: 'eq',
        expected_value: expectedSet,
        expected_value_mode: 'set',
      },
      priority: enumLike ? 94 : 42,
    }),
    recommendation({
      id: `recommended-single-sequence-${toTemplateId(variable.tag)}`,
      title: `${field} 连续递增`,
      summary: '适合等级、序号、索引等数值字段。',
      recommendReason: sequenceLike
        ? `${field} 看起来像数值序列字段，推荐检查连续性。`
        : `可用于检查 ${field} 是否按行递增。`,
      category: 'compare',
      variableKind: 'single',
      ruleType: 'sequence_order_check',
      descriptionTemplate: buildShortRuleDescription({
        ruleType: 'sequence_order_check',
        targetField: field,
        validationRule: `${field} 按升序连续`,
        ruleParams: '方向=升序；步长=1；起始=自动',
      }),
      workflowHints: {
        ...baseHints,
        rule_type_hint: 'sequence_order_check',
        sequence_direction: 'asc',
        sequence_step: '1',
        sequence_start_mode: 'auto',
      },
      priority: sequenceLike ? 92 : 38,
    }),
  ]
}

function buildCrossTableRecommendation(targetVariable: VariableTag, referenceVariable: VariableTag): AiRuleTemplate {
  const targetField = targetVariable.column || '目标字段'
  const referenceField = referenceVariable.column || '引用字段'
  return recommendation({
    id: `recommended-cross-${toTemplateId(targetVariable.tag)}-${toTemplateId(referenceVariable.tag)}`,
    title: `${targetField} 包含在 ${referenceField}`,
    summary: '用第二个单变量作为字典，校验第一个单变量。',
    recommendReason: `已选择两个单变量，推荐把 ${referenceVariable.tag} 作为字典引用。`,
    category: 'mapping',
    variableKind: 'single',
    ruleType: 'cross_table_mapping',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'cross_table_mapping',
      targetField,
      referenceObject: referenceVariable.tag,
      validationRule: `${targetField} 必须存在于引用对象`,
      ruleParams: `引用对象=${referenceVariable.tag}；引用字段=${referenceField}`,
    }),
    workflowHints: {
      ...buildSingleVariableHints(targetVariable),
      rule_type_hint: 'cross_table_mapping',
      reference_variable_tag: referenceVariable.tag,
      reference_field: referenceField,
    },
    priority: 88,
  })
}

function buildCompositeConditionRecommendation(variable: VariableTag): AiRuleTemplate {
  const fields = getCompositeMemberFields(variable)
  const filterField = fields[0] || variable.key_column || '筛选字段'
  const assertionField = fields.find((field) => field !== filterField) || fields[0] || variable.key_column || '断言字段'
  return recommendation({
    id: `recommended-composite-condition-${toTemplateId(variable.tag)}`,
    title: `${variable.tag} 条件必填`,
    summary: '基于组合变量字段生成筛选后非空检查。',
    recommendReason: `组合变量包含 Key=${variable.key_column || 'Key'} 和 ${fields.length} 个成员字段，适合做条件分支校验。`,
    category: 'composite',
    variableKind: 'composite',
    ruleType: 'composite_condition_check',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'composite_condition_check',
      targetField: assertionField,
      filterCondition: `${filterField}=示例值`,
      keyField: variable.key_column || '无',
      validationRule: `${assertionField} 不能为空`,
    }),
    workflowHints: {
      ...buildCompositeVariableHints(variable),
      rule_type_hint: 'composite_condition_check',
      filter_field: filterField,
      filter_operator: 'eq',
      filter_value: '示例值',
      assertion_field: assertionField,
      assertion_operator: 'not_null',
    },
    priority: 86,
  })
}

function buildDualCompositeRecommendation(leftVariable: VariableTag, rightVariable: VariableTag): AiRuleTemplate {
  const leftFields = getCompositeMemberFields(leftVariable)
  const rightFields = getCompositeMemberFields(rightVariable)
  const commonFields = leftFields.filter((field) => rightFields.includes(field))
  const compareFields = commonFields.length ? commonFields.slice(0, 3) : leftFields.slice(0, 3)
  const keyField = leftVariable.key_column || rightVariable.key_column || 'Key'
  const leftFilterField = leftFields[0] || keyField
  const rightFilterField = rightFields[0] || keyField
  return recommendation({
    id: `recommended-dual-composite-${toTemplateId(leftVariable.tag)}-${toTemplateId(rightVariable.tag)}`,
    title: `${leftVariable.tag} 对比 ${rightVariable.tag}`,
    summary: '按 Key 对齐两个组合变量并比较共同字段。',
    recommendReason: `两个组合变量可按 ${keyField} 对齐，比较 ${compareFields.join('、') || '共同字段'}。`,
    category: 'composite',
    variableKind: 'dual_composite',
    ruleType: 'dual_composite_compare',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'dual_composite_compare',
      filterCondition: `左侧 ${leftFilterField}=示例A；右侧 ${rightFilterField}=示例B`,
      keyField,
      compareFields: compareFields.join(',') || '共同字段',
      validationRule: '左右两组按 Key 对齐后比较字段必须相等',
    }),
    workflowHints: {
      ...buildCompositeVariableHints(leftVariable),
      rule_type_hint: 'dual_composite_compare',
      reference_variable_tag: rightVariable.tag,
      left_variable_tag: leftVariable.tag,
      right_variable_tag: rightVariable.tag,
      left_key_field: keyField,
      right_key_field: keyField,
      left_filter_field: leftFilterField,
      left_filter_operator: 'eq',
      left_filter_value: '示例A',
      right_filter_field: rightFilterField,
      right_filter_operator: 'eq',
      right_filter_value: '示例B',
      compare_fields: compareFields,
      reference_key_column: rightVariable.key_column,
      reference_composite_columns: [...(rightVariable.columns ?? [])],
    },
    priority: 84,
  })
}

function buildMultiCompositePipelineRecommendation(variables: VariableTag[]): AiRuleTemplate {
  const tags = variables.map((variable) => variable.tag).join('、')
  return recommendation({
    id: `recommended-multi-pipeline-${variables.map((variable) => toTemplateId(variable.tag)).join('-')}`,
    title: '多组串行检查',
    summary: '按已选组合变量顺序生成多节点检查。',
    recommendReason: `已选择 ${variables.length} 个组合变量，可按顺序做串行校验。`,
    category: 'composite',
    variableKind: 'multi_composite',
    ruleType: 'multi_composite_pipeline_check',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'multi_composite_pipeline_check',
      targetField: '目标字段',
      validationRule: '按多组串行节点执行筛选和断言',
      ruleParams: `节点1 -> 节点2；变量=${tags}；每个节点填写筛选和断言`,
    }),
    workflowHints: {
      ...buildCompositeVariableHints(variables[0]),
      rule_type_hint: 'multi_composite_pipeline_check',
      pipeline_nodes: buildPipelineNodes(variables),
    },
    priority: 72,
  })
}

function buildMultiCompositeMappingRecommendation(variables: VariableTag[]): AiRuleTemplate {
  const tags = variables.map((variable) => variable.tag).join('、')
  return recommendation({
    id: `recommended-multi-mapping-${variables.map((variable) => toTemplateId(variable.tag)).join('-')}`,
    title: '多组映射检查',
    summary: '按已选组合变量生成独立映射检查节点。',
    recommendReason: `已选择 ${variables.length} 个组合变量，可分别检查筛选映射条件。`,
    category: 'mapping',
    variableKind: 'multi_composite',
    ruleType: 'multi_composite_mapping_check',
    descriptionTemplate: buildShortRuleDescription({
      ruleType: 'multi_composite_mapping_check',
      targetField: '目标字段',
      validationRule: '按多组映射节点独立筛选和判断',
      ruleParams: `变量=${tags}；每个节点填写筛选、断言和排除范围`,
    }),
    workflowHints: {
      ...buildCompositeVariableHints(variables[0]),
      rule_type_hint: 'multi_composite_mapping_check',
      mapping_nodes: buildMappingNodes(variables),
    },
    priority: 70,
  })
}

function buildSingleVariableHints(variable: VariableTag): AiRuleWorkflowHints {
  return {
    target_variable_tag: variable.tag,
    source_id: variable.source_id,
    sheet: variable.sheet,
    target_field: variable.column,
  }
}

function buildCompositeVariableHints(variable: VariableTag): AiRuleWorkflowHints {
  return {
    target_variable_tag: variable.tag,
    source_id: variable.source_id,
    sheet: variable.sheet,
    target_field: getCompositeMemberFields(variable)[0] || variable.key_column || '',
    key_column: variable.key_column,
    composite_columns: [...(variable.columns ?? [])],
  }
}

function getTemplatePriority(templateItem: AiRuleTemplate): number {
  return templateItem.priority ?? 0
}

function toTemplateId(value: string): string {
  return value
    .replace(/^\[|\]$/g, '')
    .replace(/[^a-zA-Z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase()
}

function normalizeFieldName(field: string): string {
  return field.replace(/[^a-zA-Z0-9]/g, '').toLowerCase()
}

function isIdentityField(field: string): boolean {
  const normalized = normalizeFieldName(field)
  return /(^id$|id$|key$|code$|name$)/i.test(normalized)
}

function isCodeLikeField(field: string): boolean {
  const normalized = normalizeFieldName(field)
  return /(code|key|name|type|param|resource|asset)/i.test(normalized)
}

function isEnumLikeField(field: string): boolean {
  const normalized = normalizeFieldName(field)
  return /(status|state|type|switch|flag|enable|enabled|mode|kind|category)/i.test(normalized)
}

function isSequenceLikeField(field: string): boolean {
  const normalized = normalizeFieldName(field)
  return /(level|index|idx|order|seq|sequence|rank|sort|step|no|num)$/i.test(normalized)
}

function buildRenderContext(options: {
  targetVariable?: VariableTag
  referenceVariable?: VariableTag
  selectedCompositeVariables: VariableTag[]
}): Record<string, string> {
  const targetField = getPrimaryField(options.targetVariable)
  const referenceField = getPrimaryField(options.referenceVariable)
  const keyColumn = getKeyColumn(options.targetVariable) || getKeyColumn(options.referenceVariable) || 'Key'
  const compositeFields = getCompositeMemberFields(options.targetVariable)
  const compareFields = compositeFields.slice(0, 2).join(',') || getCompositeMemberFields(options.referenceVariable).slice(0, 2).join(',') || '字段A,字段B'
  const filterField = compositeFields[0] || targetField
  const assertionField = compositeFields[1] || targetField
  return {
    targetTag: options.targetVariable?.tag ?? '目标变量',
    referenceTag: options.referenceVariable?.tag ?? '引用变量',
    targetField,
    referenceField,
    sheet: options.targetVariable?.sheet || options.referenceVariable?.sheet || 'Sheet',
    keyColumn,
    filterField,
    assertionField,
    leftFilterField: filterField,
    rightFilterField: filterField,
    compareFields,
    selectedCompositeTags: options.selectedCompositeVariables.map((variable) => variable.tag).join('、') || '组合变量',
  }
}

function mergeTemplateHints(
  templateItem: AiRuleTemplate,
  options: {
    targetVariable?: VariableTag
    referenceVariable?: VariableTag
    firstCompositeVariable?: VariableTag
    secondCompositeVariable?: VariableTag
    selectedCompositeVariables: VariableTag[]
  },
): AiRuleWorkflowHints {
  const hints = cloneWorkflowHints(templateItem.workflowHints)
  const targetVariable = options.targetVariable
  const referenceVariable = options.referenceVariable

  if (targetVariable) {
    hints.target_variable_tag = targetVariable.tag
    hints.source_id = targetVariable.source_id
    hints.sheet = targetVariable.sheet
    if (isCompositeVariable(targetVariable)) {
      hints.key_column = targetVariable.key_column
      hints.composite_columns = [...(targetVariable.columns ?? [])]
      hints.target_field = getCompositeMemberFields(targetVariable)[0] ?? targetVariable.key_column ?? ''
    } else {
      hints.target_field = targetVariable.column
    }
  }
  if (referenceVariable) {
    hints.reference_variable_tag = referenceVariable.tag
    if (isCompositeVariable(referenceVariable)) {
      hints.reference_key_column = referenceVariable.key_column
      hints.reference_composite_columns = [...(referenceVariable.columns ?? [])]
      hints.reference_field = getCompositeMemberFields(referenceVariable)[0] ?? referenceVariable.key_column ?? ''
    } else {
      hints.reference_field = referenceVariable.column
    }
  }

  if (templateItem.ruleType === 'composite_condition_check' && targetVariable) {
    const memberFields = getCompositeMemberFields(targetVariable)
    hints.filter_field = hints.filter_field || memberFields[0] || targetVariable.key_column || ''
    hints.assertion_field = hints.assertion_field || memberFields[1] || memberFields[0] || targetVariable.key_column || ''
  }

  if (templateItem.ruleType === 'dual_composite_compare') {
    const leftVariable = options.firstCompositeVariable
    const rightVariable = options.secondCompositeVariable ?? options.firstCompositeVariable
    const leftFields = getCompositeMemberFields(leftVariable)
    const rightFields = getCompositeMemberFields(rightVariable)
    const keyColumn = leftVariable?.key_column || rightVariable?.key_column || ''
    hints.left_variable_tag = leftVariable?.tag
    hints.right_variable_tag = rightVariable?.tag
    hints.left_key_field = keyColumn
    hints.right_key_field = keyColumn
    hints.left_filter_field = hints.left_filter_field || leftFields[0] || keyColumn
    hints.right_filter_field = hints.right_filter_field || rightFields[0] || keyColumn
    hints.compare_fields = leftFields.filter((field) => rightFields.includes(field)).slice(0, 2)
    if (!hints.compare_fields.length) {
      hints.compare_fields = leftFields.slice(0, 2)
    }
  }

  if (templateItem.ruleType === 'multi_composite_pipeline_check') {
    hints.pipeline_nodes = buildPipelineNodes(options.selectedCompositeVariables)
  }
  if (templateItem.ruleType === 'multi_composite_mapping_check') {
    hints.mapping_nodes = buildMappingNodes(options.selectedCompositeVariables)
  }

  return hints
}

function getPrimaryField(variable?: VariableTag): string {
  if (!variable) return '目标字段'
  if (isCompositeVariable(variable)) {
    return getCompositeMemberFields(variable)[0] ?? variable.key_column ?? '目标字段'
  }
  return variable.column || '目标字段'
}

function getKeyColumn(variable?: VariableTag): string {
  if (!variable || !isCompositeVariable(variable)) return ''
  return variable.key_column || ''
}

function getCompositeMemberFields(variable?: VariableTag): string[] {
  if (!variable || !isCompositeVariable(variable)) return []
  const keyColumn = variable.key_column ?? ''
  return (variable.columns ?? []).filter((column) => column && column !== keyColumn)
}

function renderTemplateText(text: string, context: Record<string, string>): string {
  return text.replace(/\{([a-zA-Z0-9_]+)\}/g, (_match, key: string) => context[key] ?? '')
}

function buildPipelineNodes(variables: VariableTag[]): Record<string, unknown>[] {
  return variables.map((variable, index) => ({
    node_id: `template-node-${index + 1}`,
    variable_tag: variable.tag,
    display_field: getPrimaryField(variable),
    filters: [],
    assertions: [
      {
        condition_id: `template-assert-${index + 1}`,
        field: getPrimaryField(variable),
        operator: 'not_null',
      },
    ],
  }))
}

function buildMappingNodes(variables: VariableTag[]): Record<string, unknown>[] {
  return variables.map((variable, index) => ({
    node_id: `template-node-${index + 1}`,
    variable_tag: variable.tag,
    display_field: getPrimaryField(variable),
    filters: [
      {
        condition_id: `template-filter-${index + 1}`,
        field: getPrimaryField(variable),
        operator: 'not_null',
        exclusion_ranges: [],
      },
    ],
  }))
}

