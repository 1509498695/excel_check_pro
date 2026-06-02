import type { FixedRuleDefinition, FixedRuleGroup } from '../../types/fixedRules'
import type { TaskTree, ValidationRule, VariableTag } from '../../types/workbench'
import {
  ensureDefaultGroup,
  isCompositeVariable,
  isSingleVariable,
  isValidCompositeConfig,
  isValidMultiCompositeMappingConfig,
  isValidMultiCompositePipelineConfig,
  normalizeExpectedValue,
  RULE_ORCHESTRATION_PAGE_SIZE,
} from '../../utils/ruleOrchestrationModel'
import { buildTaskTreePayload as buildTaskTreePayloadFromParts } from '../../utils/taskTree'
import { orchestrationRulesToValidationRules } from '../../utils/workbenchOrchestrationRules'
import {
  isValidDualCompositeRule,
  isValidSequenceStartValue,
  isValidSequenceStep,
} from './rules'
import type { WorkbenchState } from './state'

export function selectEngineValidationRules(state: WorkbenchState): ValidationRule[] {
  return orchestrationRulesToValidationRules(state.variables, state.orchestrationRules)
}

export function selectTaskTree(state: WorkbenchState): TaskTree {
  return {
    sources: state.sources,
    variables: state.variables,
    rules: selectEngineValidationRules(state),
  }
}

export function selectAllRuleGroups(state: WorkbenchState): FixedRuleGroup[] {
  return ensureDefaultGroup(state.ruleGroups)
}

export function selectFilteredRuleGroups(state: WorkbenchState): FixedRuleGroup[] {
  const keyword = state.groupKeyword.trim().toLowerCase()
  const groups = selectAllRuleGroups(state)
  if (!keyword) {
    return groups
  }
  return groups.filter((group) => group.group_name.toLowerCase().includes(keyword))
}

export function selectSelectedRuleGroup(state: WorkbenchState): FixedRuleGroup {
  const groups = selectAllRuleGroups(state)
  return groups.find((group) => group.group_id === state.selectedGroupId) ?? groups[0]
}

export function selectGroupOrchestrationCounts(
  state: WorkbenchState,
): Record<string, number> {
  return state.orchestrationRules.reduce<Record<string, number>>((accumulator, rule) => {
    accumulator[rule.group_id] = (accumulator[rule.group_id] ?? 0) + 1
    return accumulator
  }, {})
}

export function selectCurrentOrchestrationGroupRules(
  state: WorkbenchState,
): FixedRuleDefinition[] {
  const groupId = selectSelectedRuleGroup(state).group_id
  return state.orchestrationRules.filter((rule) => rule.group_id === groupId)
}

export function selectPagedCurrentOrchestrationGroupRules(
  state: WorkbenchState,
): FixedRuleDefinition[] {
  const start = (state.orchestrationCurrentPage - 1) * RULE_ORCHESTRATION_PAGE_SIZE
  return selectCurrentOrchestrationGroupRules(state).slice(
    start,
    start + RULE_ORCHESTRATION_PAGE_SIZE,
  )
}

export function selectCurrentOrchestrationGroupRuleTotal(state: WorkbenchState): number {
  return selectCurrentOrchestrationGroupRules(state).length
}

export function selectCurrentOrchestrationGroupPageCount(state: WorkbenchState): number {
  return Math.max(
    1,
    Math.ceil(selectCurrentOrchestrationGroupRuleTotal(state) / RULE_ORCHESTRATION_PAGE_SIZE),
  )
}

export function selectInvalidOrchestrationRuleIds(state: WorkbenchState): string[] {
  const validGroupIds = new Set(selectAllRuleGroups(state).map((group) => group.group_id))
  const variableMap = new Map(state.variables.map((variable) => [variable.tag, variable] as const))

  return state.orchestrationRules
    .filter((rule) => isInvalidOrchestrationRule(rule, validGroupIds, variableMap))
    .map((rule) => rule.rule_id)
}

function isInvalidOrchestrationRule(
  rule: FixedRuleDefinition,
  validGroupIds: Set<string>,
  variableMap: Map<string, VariableTag>,
): boolean {
  if (!validGroupIds.has(rule.group_id) || !rule.rule_name.trim()) {
    return true
  }
  if (rule.rule_type === 'multi_composite_pipeline_check') {
    return !isValidMultiCompositePipelineConfig(rule.pipeline_config, variableMap)
  }
  if (rule.rule_type === 'multi_composite_mapping_check') {
    return !isValidMultiCompositeMappingConfig(rule.mapping_config, variableMap)
  }
  if (rule.rule_type === 'package_items_compare') {
    return isInvalidPackageItemsRule(rule, variableMap)
  }

  const targetTag = rule.target_variable_tag.trim()
  const variable = variableMap.get(targetTag)
  if (!targetTag || !variable) {
    return true
  }

  if (isSingleVariable(variable)) {
    return isInvalidSingleVariableRule(rule, variableMap)
  }
  if (!isCompositeVariable(variable)) {
    return true
  }
  if (rule.rule_type === 'composite_condition_check') {
    return !isValidCompositeConfig(rule.composite_config)
  }
  if (rule.rule_type === 'dual_composite_compare') {
    return !isValidDualCompositeRule(rule, variableMap)
  }
  return true
}

function isInvalidPackageItemsRule(
  rule: FixedRuleDefinition,
  variableMap: Map<string, VariableTag>,
): boolean {
  if (!rule.rule_name.trim()) {
    return true
  }
  const referenceTag = rule.reference_variable_tag?.trim() ?? ''
  if (!referenceTag || !isCompositeVariable(variableMap.get(referenceTag))) {
    return true
  }
  if (
    !rule.left_package_field?.trim() ||
    !rule.left_item_field?.trim() ||
    !rule.left_count_field?.trim() ||
    !rule.right_package_field?.trim() ||
    !rule.right_items_field?.trim()
  ) {
    return true
  }
  const parseConfig = rule.package_parse_config
  if (!parseConfig?.feishu_source_id?.trim() || !parseConfig.feishu_sheet_id?.trim()) {
    return true
  }
  if (!['auto', 'rule', 'ai'].includes(parseConfig.parse_strategy ?? 'auto')) {
    return true
  }
  if (!['auto', 'enabled', 'disabled'].includes(parseConfig.ai_parse_mode ?? 'auto')) {
    return true
  }
  const validationScope = parseConfig.validation_scope ?? 'all'
  if (!['all', 'specified'].includes(validationScope)) {
    return true
  }
  return validationScope === 'specified' && !parseConfig.package_id_filter?.trim()
}

function isInvalidSingleVariableRule(
  rule: FixedRuleDefinition,
  variableMap: Map<string, VariableTag>,
): boolean {
  if (
    rule.rule_type === 'composite_condition_check' ||
    rule.rule_type === 'dual_composite_compare'
  ) {
    return true
  }
  if (rule.rule_type === 'cross_table_mapping') {
    const referenceTag = rule.reference_variable_tag?.trim() ?? ''
    if (!referenceTag) {
      return true
    }
    return !isSingleVariable(variableMap.get(referenceTag))
  }
  if (rule.rule_type === 'sequence_order_check') {
    return (
      !rule.sequence_direction ||
      !['asc', 'desc'].includes(rule.sequence_direction) ||
      !rule.sequence_start_mode ||
      !['auto', 'manual'].includes(rule.sequence_start_mode) ||
      !isValidSequenceStep(rule.sequence_step) ||
      (rule.sequence_start_mode === 'manual' &&
        !isValidSequenceStartValue(rule.sequence_start_value))
    )
  }
  if (rule.rule_type === 'regex_check') {
    return !normalizeExpectedValue(rule.expected_value)
  }
  if (rule.rule_type !== 'fixed_value_compare') {
    return false
  }
  if (!rule.operator) {
    return true
  }
  const expectedValue = normalizeExpectedValue(rule.expected_value)
  if (!expectedValue) {
    return true
  }
  return (
    (rule.operator === 'gt' || rule.operator === 'lt') &&
    Number.isNaN(Number(expectedValue))
  )
}

export function selectInvalidOrchestrationGroupIds(state: WorkbenchState): string[] {
  const invalidRuleIds = new Set(selectInvalidOrchestrationRuleIds(state))
  const invalidGroupIds = new Set<string>()
  state.orchestrationRules.forEach((rule) => {
    if (invalidRuleIds.has(rule.rule_id)) {
      invalidGroupIds.add(rule.group_id)
    }
  })
  return [...invalidGroupIds]
}

export function selectCanExecuteOrchestration(state: WorkbenchState): boolean {
  return (
    state.orchestrationRules.length > 0 &&
    selectInvalidOrchestrationRuleIds(state).length === 0 &&
    !selectHasBlockingSourceIssues(state)
  )
}

export function selectHasBlockingSourceIssues(state: WorkbenchState): boolean {
  return Object.keys(state.sourceIssues).length > 0
}

export function selectSingleVariables(state: WorkbenchState): VariableTag[] {
  return state.variables.filter((variable) => (variable.variable_kind ?? 'single') === 'single')
}

export function selectResultPageCount(state: WorkbenchState): number {
  return Math.max(1, Math.ceil(state.abnormalResultTotal / state.resultPageSize))
}

export function buildWorkbenchTaskTreePayload(
  state: WorkbenchState,
  selectedRuleIds?: string[],
  page?: number,
  size?: number,
): TaskTree {
  return buildTaskTreePayloadFromParts(
    state.sources,
    state.variables,
    selectEngineValidationRules(state),
    selectedRuleIds,
    page,
    size,
  )
}
