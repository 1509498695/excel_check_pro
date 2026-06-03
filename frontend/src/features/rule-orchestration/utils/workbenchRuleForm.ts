import type {
  CompositeAssertionOperator,
  CompositeBranch,
  CompositeCondition,
  CompositeFilterOperator,
  CompositeRuleConfig,
  DualCompositeComparison,
  ExpectedValueMode,
  FixedRuleDefinition,
  FixedRuleOperator,
  FixedRuleSelection,
  MultiCompositeMappingConfig,
  MultiCompositeMappingExclusionRange,
  MultiCompositeMappingFilter,
  MultiCompositeMappingNode,
  MultiCompositePipelineConfig,
  MultiCompositePipelineNode,
  PipelineAssertionOperator,
} from '../../../types/fixedRules'
import type { DataSource, VariableTag } from '../../../types/workbench'

export type ConditionMode = 'filter' | 'assertion'
export type WorkbenchRuleEntryType =
  | 'single'
  | 'composite'
  | 'dual_composite'
  | 'multi_composite_pipeline'
  | 'multi_composite_mapping'

export interface FieldOption {
  label: string
  value: string
}

export interface WorkbenchRuleFormState {
  rule_id: string
  group_id: string
  rule_name: string
  rule_entry_type: WorkbenchRuleEntryType
  target_variable_tag: string
  display_field: string
  selected_rule: FixedRuleSelection
  expected_value: string
  expected_value_mode: ExpectedValueMode
  reference_variable_tag: string
  sequence_direction: 'asc' | 'desc'
  sequence_step: string
  sequence_start_mode: 'auto' | 'manual'
  sequence_start_value: string
  key_check_mode: 'baseline_only' | 'bidirectional'
  left_key_field: string
  right_key_field: string
}

export interface WorkbenchRuleDialogStateSnapshot {
  form: WorkbenchRuleFormState
  compositeConfig?: CompositeRuleConfig
  dualComparisons?: DualCompositeComparison[]
  dualLeftFilters?: CompositeCondition[]
  dualRightFilters?: CompositeCondition[]
  pipelineConfig?: MultiCompositePipelineConfig
  mappingConfig?: MultiCompositeMappingConfig
}

export interface WorkbenchRuleFormValidationResult {
  valid: boolean
  message?: string
  normalizedTargetTag?: string
}

export type WorkbenchRuleUpsertPayload = Omit<FixedRuleDefinition, 'rule_id'> & {
  rule_id?: string
}

export interface WorkbenchRuleBuildResult {
  rule: WorkbenchRuleUpsertPayload
  normalizedTargetTag?: string
}

export const KEY_FIELD = '__key__'

export const ruleSelectionOptions: Array<{ label: string; value: FixedRuleSelection }> = [
  { label: '等于 (=)', value: 'eq' },
  { label: '不等于 (!=)', value: 'ne' },
  { label: '大于 (>)', value: 'gt' },
  { label: '小于 (<)', value: 'lt' },
  { label: '正则校验', value: 'regex_check' },
  { label: '非空校验', value: 'not_null' },
  { label: '唯一校验', value: 'unique' },
  { label: '顺序校验', value: 'sequence_order_check' },
  { label: '包含 (in)', value: 'in' },
]

export const ruleEntryTypeOptions: Array<{ label: string; value: WorkbenchRuleEntryType }> = [
  { label: '单一变量校验', value: 'single' },
  { label: '组合分支校验', value: 'composite' },
  { label: '跨组变量校验', value: 'dual_composite' },
  { label: '多组串行校验', value: 'multi_composite_pipeline' },
  { label: '多组映射校验', value: 'multi_composite_mapping' },
]

export const dualCompositeOperatorOptions: Array<{
  label: string
  value: FixedRuleOperator | 'not_null'
}> = [
  { label: '等于 (=)', value: 'eq' },
  { label: '不等于 (!=)', value: 'ne' },
  { label: '大于 (>)', value: 'gt' },
  { label: '小于 (<)', value: 'lt' },
  { label: '非空校验', value: 'not_null' },
]

export const compositeFilterOptions: Array<{ label: string; value: CompositeFilterOperator }> = [
  { label: '等于 (=)', value: 'eq' },
  { label: '不等于 (!=)', value: 'ne' },
  { label: '大于 (>)', value: 'gt' },
  { label: '小于 (<)', value: 'lt' },
  { label: '非空校验', value: 'not_null' },
  { label: '包含', value: 'contains' },
  { label: '不包含', value: 'not_contains' },
]

export const compositeAssertionOptions: Array<{
  label: string
  value: CompositeAssertionOperator
}> = [
  { label: '等于 (=)', value: 'eq' },
  { label: '不等于 (!=)', value: 'ne' },
  { label: '大于 (>)', value: 'gt' },
  { label: '小于 (<)', value: 'lt' },
  { label: '正则校验', value: 'regex' },
  { label: '非空校验', value: 'not_null' },
  { label: '唯一校验', value: 'unique' },
  { label: '必须重复', value: 'duplicate_required' },
]

export const pipelineAssertionOptions: Array<{
  label: string
  value: PipelineAssertionOperator
}> = [
  { label: '等于 (=)', value: 'eq' },
  { label: '不等于 (!=)', value: 'ne' },
  { label: '大于 (>)', value: 'gt' },
  { label: '小于 (<)', value: 'lt' },
  { label: '正则校验', value: 'regex' },
  { label: '非空校验', value: 'not_null' },
]

export const expectedValueModeOptions: Array<{ label: string; value: ExpectedValueMode }> = [
  { label: '固定值', value: 'single' },
  { label: '规则集', value: 'set' },
]

const compareRuleSelections = new Set<FixedRuleOperator>(['eq', 'ne', 'gt', 'lt'])
const compositeCompareOperators = new Set<CompositeFilterOperator | CompositeAssertionOperator>([
  'eq',
  'ne',
  'gt',
  'lt',
])
const ruleSelectionNameMap: Record<FixedRuleSelection, string> = {
  eq: '等于',
  ne: '不等于',
  gt: '大于',
  lt: '小于',
  regex_check: '正则校验',
  not_null: '非空校验',
  unique: '唯一校验',
  sequence_order_check: '顺序校验',
  in: '包含',
  composite_condition_check: '组合分支校验',
  dual_composite_compare: '跨组变量校验',
  multi_composite_pipeline_check: '多组串行校验',
  multi_composite_mapping_check: '多组映射校验',
}
const operatorSymbolMap: Record<FixedRuleOperator, string> = {
  eq: '=',
  ne: '!=',
  gt: '>',
  lt: '<',
}

export function isCompareRuleSelection(value: FixedRuleSelection): value is FixedRuleOperator {
  return compareRuleSelections.has(value as FixedRuleOperator)
}

export function isCompositeCompareOperator(
  value: CompositeFilterOperator | CompositeAssertionOperator,
): value is FixedRuleOperator {
  return compositeCompareOperators.has(value)
}

export function isCompositeContainsOperator(
  value: CompositeFilterOperator | CompositeAssertionOperator,
): value is 'contains' | 'not_contains' {
  return value === 'contains' || value === 'not_contains'
}

export function isCompositeRegexOperator(
  value: CompositeFilterOperator | CompositeAssertionOperator,
): value is 'regex' {
  return value === 'regex'
}

export function normalizeExpectedValueMode(value: ExpectedValueMode | undefined): ExpectedValueMode {
  return value === 'set' ? 'set' : 'single'
}

export function parseExpectedValueSet(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function shouldShowConditionExpectedValueMode(condition: CompositeCondition): boolean {
  return (
    (condition.operator === 'eq' || condition.operator === 'ne') &&
    (condition.value_source ?? 'literal') === 'literal'
  )
}

export function getExpectedValueModeHelpText(value: string): string {
  return value.trim() ? '' : '多个固定值请用英文逗号分隔，例如：0,1,2。'
}

export function createId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function createCondition(): CompositeCondition {
  return {
    condition_id: createId('condition'),
    field: '',
    operator: 'eq',
    value_source: 'literal',
    expected_value: '',
    expected_value_mode: 'single',
    expected_field: '',
  }
}

export function createBranch(): CompositeBranch {
  return {
    branch_id: createId('branch'),
    filters: [],
    assertions: [createCondition()],
  }
}

export function createDualCompositeComparison(): DualCompositeComparison {
  return {
    comparison_id: createId('comparison'),
    left_field: '',
    operator: 'eq',
    right_field: '',
  }
}

export function getDefaultCompositeVariableTag(
  compositeVariables: VariableTag[],
  preferred = '',
): string {
  const normalizedPreferred = preferred.trim()
  if (
    normalizedPreferred &&
    compositeVariables.some((variable) => variable.tag === normalizedPreferred)
  ) {
    return normalizedPreferred
  }
  return compositeVariables[0]?.tag ?? ''
}

export function createPipelineNode(
  compositeVariables: VariableTag[],
  preferredVariableTag = '',
): MultiCompositePipelineNode {
  return {
    node_id: createId('pipeline-node'),
    variable_tag: getDefaultCompositeVariableTag(compositeVariables, preferredVariableTag),
    display_field: '',
    filters: [],
    assertions: [createCondition()],
  }
}

export function createMappingExclusionRange(
  startRow = 2,
): MultiCompositeMappingExclusionRange {
  return {
    range_id: createId('mapping-range'),
    start_row: startRow,
    end_row: startRow,
    expected_value: '',
  }
}

export function createMappingFilter(): MultiCompositeMappingFilter {
  return {
    ...createCondition(),
    exclusion_ranges: [],
  }
}

export function createMappingNode(
  compositeVariables: VariableTag[],
  preferredVariableTag = '',
): MultiCompositeMappingNode {
  const variableTag = getDefaultCompositeVariableTag(compositeVariables, preferredVariableTag)
  return {
    node_id: createId('mapping-node'),
    variable_tag: variableTag,
    display_field: '',
    filters: [],
  }
}

export function normalizeCompositeConfig(config?: CompositeRuleConfig): CompositeRuleConfig {
  return {
    global_filters: (config?.global_filters ?? []).map((condition) => ({
      ...condition,
      condition_id: condition.condition_id || createId('condition'),
    })),
    branches: (config?.branches?.length ? config.branches : [createBranch()]).map((branch) => ({
      branch_id: branch.branch_id || createId('branch'),
      filters: (branch.filters ?? []).map((condition) => ({
        ...condition,
        condition_id: condition.condition_id || createId('condition'),
      })),
      assertions: (branch.assertions?.length ? branch.assertions : [createCondition()]).map(
        (condition) => ({
          ...condition,
          condition_id: condition.condition_id || createId('condition'),
        }),
      ),
    })),
  }
}

export function normalizeDualCompositeComparisons(
  comparisons?: DualCompositeComparison[],
): DualCompositeComparison[] {
  const nextComparisons = (
    comparisons?.length ? comparisons : [createDualCompositeComparison()]
  ).map((comparison) => ({
    comparison_id: comparison.comparison_id || createId('comparison'),
    left_field: comparison.left_field?.trim() ?? '',
    operator: comparison.operator ?? 'eq',
    right_field: comparison.right_field?.trim() ?? '',
  }))
  return nextComparisons.length ? nextComparisons : [createDualCompositeComparison()]
}

export function normalizeDualCompositeFilters(
  filters?: CompositeCondition[],
): CompositeCondition[] {
  return (filters ?? []).map((condition) => ({
    ...condition,
    condition_id: condition.condition_id || createId('condition'),
  }))
}

export function getRuleEntryTypeBySelection(
  selection: FixedRuleSelection,
): WorkbenchRuleEntryType {
  if (selection === 'dual_composite_compare') {
    return 'dual_composite'
  }
  if (selection === 'multi_composite_pipeline_check') {
    return 'multi_composite_pipeline'
  }
  if (selection === 'multi_composite_mapping_check') {
    return 'multi_composite_mapping'
  }
  if (selection === 'composite_condition_check') {
    return 'composite'
  }
  return 'single'
}

export function normalizePipelineConfig(
  config: MultiCompositePipelineConfig | undefined,
  compositeVariables: VariableTag[],
  preferredVariableTag = '',
): MultiCompositePipelineConfig {
  const fallbackVariableTag = getDefaultCompositeVariableTag(compositeVariables, preferredVariableTag)
  const nextNodes = (
    config?.nodes?.length ? config.nodes : [createPipelineNode(compositeVariables, fallbackVariableTag)]
  ).map((node, index) => ({
    node_id: node.node_id || createId('pipeline-node'),
    variable_tag: getDefaultCompositeVariableTag(
      compositeVariables,
      node.variable_tag || (index === 0 ? fallbackVariableTag : ''),
    ),
    display_field: node.display_field?.trim() ?? '',
    filters: (node.filters ?? []).map((condition) => ({
      ...condition,
      condition_id: condition.condition_id || createId('condition'),
    })),
    assertions: (node.assertions?.length ? node.assertions : [createCondition()]).map(
      (condition) => ({
        ...condition,
        condition_id: condition.condition_id || createId('condition'),
      }),
    ),
  }))
  return { nodes: nextNodes }
}

export function normalizeMappingConfig(
  config: MultiCompositeMappingConfig | undefined,
  compositeVariables: VariableTag[],
  preferredVariableTag = '',
): MultiCompositeMappingConfig {
  const fallbackVariableTag = getDefaultCompositeVariableTag(compositeVariables, preferredVariableTag)
  const nextNodes = (
    config?.nodes?.length ? config.nodes : [createMappingNode(compositeVariables, fallbackVariableTag)]
  ).map((node, index) => {
    const variableTag = getDefaultCompositeVariableTag(
      compositeVariables,
      node.variable_tag || (index === 0 ? fallbackVariableTag : ''),
    )
    return {
      node_id: node.node_id || createId('mapping-node'),
      variable_tag: variableTag,
      display_field: node.display_field?.trim() ?? '',
      filters: (node.filters ?? []).map((condition) => ({
        ...condition,
        condition_id: condition.condition_id || createId('condition'),
        exclusion_ranges: (condition.exclusion_ranges ?? []).map((range) => ({
          range_id: range.range_id || createId('mapping-range'),
          start_row: Number(range.start_row) || 1,
          end_row: Number(range.end_row) || 1,
          expected_value: range.expected_value?.trim() ?? '',
        })),
      })),
    }
  })
  return { nodes: nextNodes }
}

export function buildCompositeFieldOptions(variable: VariableTag | null): FieldOption[] {
  if (!variable || (variable.variable_kind ?? 'single') !== 'composite') {
    return []
  }

  const keyColumn = variable.key_column ?? ''
  const options: FieldOption[] = [
    {
      label: keyColumn ? `${keyColumn} (内部 Key)` : 'Key(映射键)',
      value: KEY_FIELD,
    },
  ]
  if (keyColumn.trim()) {
    options.push({ label: `${keyColumn} (原始字段)`, value: keyColumn })
  }
  ;(variable.columns ?? [])
    .filter((column) => column && column.trim() && column !== keyColumn)
    .forEach((column) => {
      options.push({ label: column, value: column })
    })
  return options
}

export function buildDisplayFieldOptions(variable: VariableTag | null): FieldOption[] {
  if (!variable) {
    return []
  }
  if ((variable.variable_kind ?? 'single') === 'composite') {
    return buildCompositeFieldOptions(variable)
  }
  const column = variable.column?.trim() ?? ''
  return column ? [{ label: column, value: column }] : []
}

export function resolveFieldOptionValue(options: FieldOption[], field: string): string | null {
  if (options.some((option) => option.value === field)) {
    return field
  }

  const normalizedField = field.trim()
  if (!normalizedField) {
    return null
  }

  const matchedOptions = options.filter((option) => option.value.trim() === normalizedField)
  return matchedOptions.length === 1 ? matchedOptions[0].value : null
}

export function normalizeDisplayField(value: string, options: FieldOption[]): string {
  return options.some((option) => option.value === value) ? value : ''
}

function isKnownCompositeField(field: string, options: FieldOption[]): boolean {
  return resolveFieldOptionValue(options, field) !== null
}

export function validateCompositeCondition(
  condition: CompositeCondition,
  mode: ConditionMode,
  label: string,
  options: FieldOption[],
  allowSetAssertions = true,
): string | null {
  if (!condition.field.trim()) {
    return `${label}缺少字段。`
  }
  if (!isKnownCompositeField(condition.field, options)) {
    return `${label}引用了当前组合变量中不存在的字段。`
  }
  if (mode === 'filter' && (condition.operator === 'unique' || condition.operator === 'duplicate_required')) {
    return `${label}的筛选条件不支持唯一或必须重复。`
  }
  if (
    mode === 'assertion' &&
    !allowSetAssertions &&
    (condition.operator === 'unique' || condition.operator === 'duplicate_required')
  ) {
    return `${label}不支持唯一或必须重复。`
  }
  if (isCompositeContainsOperator(condition.operator)) {
    if (condition.value_source === 'field') {
      return `${label}的${condition.operator === 'not_contains' ? '不包含' : '包含'}条件只支持固定值。`
    }
    if (!condition.expected_value?.trim()) {
      return `${label}缺少比较值。`
    }
    return null
  }
  if (isCompositeRegexOperator(condition.operator)) {
    if (mode !== 'assertion') {
      return `${label}的正则校验只能用于分支校验条件。`
    }
    if (!condition.expected_value?.trim()) {
      return `${label}缺少正则表达式。`
    }
    return null
  }
  if (!isCompositeCompareOperator(condition.operator)) {
    return null
  }

  if ((condition.value_source ?? 'literal') === 'field') {
    if (!condition.expected_field?.trim()) {
      return `${label}缺少右侧字段。`
    }
    if (!isKnownCompositeField(condition.expected_field, options)) {
      return `${label}引用了无效的右侧字段。`
    }
    return null
  }

  if (!condition.expected_value?.trim()) {
    return `${label}缺少比较值。`
  }
  if (
    shouldShowConditionExpectedValueMode(condition) &&
    condition.expected_value_mode === 'set' &&
    parseExpectedValueSet(condition.expected_value).length === 0
  ) {
    return `${label}的规则集至少需要一个固定值。`
  }
  if ((condition.operator === 'gt' || condition.operator === 'lt') && Number.isNaN(Number(condition.expected_value))) {
    return `${label}的大于/小于比较值必须是合法数字。`
  }
  return null
}

export function validateDualCompositeKeyField(
  field: string,
  sideLabel: string,
  options: FieldOption[],
): string | null {
  if (!field.trim()) {
    return `${sideLabel}关联 Key 字段不能为空。`
  }
  if (resolveFieldOptionValue(options, field) === null) {
    return `${sideLabel}关联 Key 字段不属于对应组合变量。`
  }
  return null
}

export function validateDualCompositeFilters(
  filters: CompositeCondition[],
  sideLabel: string,
  options: FieldOption[],
): string | null {
  for (let index = 0; index < filters.length; index += 1) {
    const error = validateCompositeCondition(
      filters[index],
      'filter',
      `${sideLabel}筛选条件 ${index + 1}`,
      options,
    )
    if (error) {
      return error
    }
  }
  return null
}

export function validateDualCompositeComparison(
  comparison: DualCompositeComparison,
  label: string,
  leftOptions: FieldOption[],
  rightOptions: FieldOption[],
): string | null {
  if (!comparison.left_field.trim()) {
    return `${label}缺少变量 1 字段。`
  }
  if (!isKnownCompositeField(comparison.left_field, leftOptions)) {
    return `${label}引用了基准变量中不存在的字段。`
  }
  if (!comparison.right_field.trim()) {
    return `${label}缺少变量 2 字段。`
  }
  if (!isKnownCompositeField(comparison.right_field, rightOptions)) {
    return `${label}引用了目标变量中不存在的字段。`
  }
  return null
}

export function getMappingRangeStartError(range: MultiCompositeMappingExclusionRange): string {
  if (range.start_row == null) {
    return '请输入起始行号'
  }
  const startRow = Number(range.start_row)
  if (!Number.isInteger(startRow) || startRow <= 0) {
    return '行号必须为正整数'
  }
  const endRow = Number(range.end_row)
  if (Number.isInteger(endRow) && endRow > 0 && startRow > endRow) {
    return '起始行号不能大于结束行号'
  }
  return ''
}

export function getMappingRangeEndError(range: MultiCompositeMappingExclusionRange): string {
  if (range.end_row == null) {
    return '请输入结束行号'
  }
  const endRow = Number(range.end_row)
  if (!Number.isInteger(endRow) || endRow <= 0) {
    return '行号必须为正整数'
  }
  const startRow = Number(range.start_row)
  if (Number.isInteger(startRow) && startRow > 0 && startRow > endRow) {
    return '起始行号不能大于结束行号'
  }
  return ''
}

export function getMappingRangeExpectedValueError(
  range: MultiCompositeMappingExclusionRange,
): string {
  const expectedValues = (range.expected_value ?? '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)
  return expectedValues.length ? '' : '请输入判定值，多个值用英文逗号分隔'
}

export function validateMappingExclusionRanges(
  ranges: MultiCompositeMappingExclusionRange[],
  label: string,
): string | null {
  for (let index = 0; index < ranges.length; index += 1) {
    const range = ranges[index]
    const startError = getMappingRangeStartError(range)
    if (startError) {
      return `${label}第 ${index + 1} 段排除范围：${startError}。`
    }
    const endError = getMappingRangeEndError(range)
    if (endError) {
      return `${label}第 ${index + 1} 段排除范围：${endError}。`
    }
    const expectedValueError = getMappingRangeExpectedValueError(range)
    if (expectedValueError) {
      return `${label}第 ${index + 1} 段排除范围：${expectedValueError}。`
    }
  }
  return null
}

export function createDefaultWorkbenchRuleFormState(
  groupId: string,
  targetVariableTag = '',
): WorkbenchRuleFormState {
  return {
    rule_id: '',
    group_id: groupId,
    rule_name: '',
    rule_entry_type: 'single',
    target_variable_tag: targetVariableTag,
    display_field: '',
    selected_rule: 'gt',
    expected_value: '0',
    expected_value_mode: 'single',
    reference_variable_tag: '',
    sequence_direction: 'asc',
    sequence_step: '1',
    sequence_start_mode: 'auto',
    sequence_start_value: '',
    key_check_mode: 'baseline_only',
    left_key_field: KEY_FIELD,
    right_key_field: KEY_FIELD,
  }
}

export function createEditWorkbenchRuleDialogState(
  rule: FixedRuleDefinition,
  compositeVariables: VariableTag[],
): WorkbenchRuleDialogStateSnapshot {
  const form = createDefaultWorkbenchRuleFormState(rule.group_id, rule.target_variable_tag ?? '')
  form.rule_id = rule.rule_id
  form.rule_name = rule.rule_name
  form.display_field = rule.display_field ?? ''
  form.rule_entry_type = getRuleEntryTypeBySelection(getRuleSelectionValue(rule))

  if (rule.rule_type === 'composite_condition_check') {
    form.selected_rule = 'composite_condition_check'
    return {
      form,
      compositeConfig: normalizeCompositeConfig(rule.composite_config),
      pipelineConfig: normalizePipelineConfig(undefined, compositeVariables, rule.target_variable_tag ?? ''),
      mappingConfig: normalizeMappingConfig(undefined, compositeVariables, rule.target_variable_tag ?? ''),
    }
  }

  if (rule.rule_type === 'dual_composite_compare') {
    form.selected_rule = 'dual_composite_compare'
    form.reference_variable_tag = rule.reference_variable_tag ?? ''
    form.key_check_mode = rule.key_check_mode ?? 'baseline_only'
    form.left_key_field = rule.left_key_field ?? KEY_FIELD
    form.right_key_field = rule.right_key_field ?? KEY_FIELD
    return {
      form,
      compositeConfig: normalizeCompositeConfig(undefined),
      dualComparisons: normalizeDualCompositeComparisons(rule.comparisons),
      dualLeftFilters: normalizeDualCompositeFilters(rule.left_filters),
      dualRightFilters: normalizeDualCompositeFilters(rule.right_filters),
      pipelineConfig: normalizePipelineConfig(undefined, compositeVariables, rule.target_variable_tag ?? ''),
      mappingConfig: normalizeMappingConfig(undefined, compositeVariables, rule.target_variable_tag ?? ''),
    }
  }

  if (rule.rule_type === 'multi_composite_pipeline_check') {
    form.selected_rule = 'multi_composite_pipeline_check'
    return {
      form,
      compositeConfig: normalizeCompositeConfig(undefined),
      dualComparisons: normalizeDualCompositeComparisons(undefined),
      dualLeftFilters: normalizeDualCompositeFilters(undefined),
      dualRightFilters: normalizeDualCompositeFilters(undefined),
      pipelineConfig: normalizePipelineConfig(
        rule.pipeline_config,
        compositeVariables,
        rule.target_variable_tag ?? '',
      ),
      mappingConfig: normalizeMappingConfig(undefined, compositeVariables, rule.target_variable_tag ?? ''),
    }
  }

  if (rule.rule_type === 'multi_composite_mapping_check') {
    form.selected_rule = 'multi_composite_mapping_check'
    return {
      form,
      compositeConfig: normalizeCompositeConfig(undefined),
      dualComparisons: normalizeDualCompositeComparisons(undefined),
      dualLeftFilters: normalizeDualCompositeFilters(undefined),
      dualRightFilters: normalizeDualCompositeFilters(undefined),
      pipelineConfig: normalizePipelineConfig(undefined, compositeVariables, rule.target_variable_tag ?? ''),
      mappingConfig: normalizeMappingConfig(
        rule.mapping_config,
        compositeVariables,
        rule.target_variable_tag ?? '',
      ),
    }
  }

  form.selected_rule = getRuleSelectionValue(rule)
  form.expected_value =
    rule.rule_type === 'fixed_value_compare' || rule.rule_type === 'regex_check'
      ? rule.expected_value ?? ''
      : ''
  form.expected_value_mode =
    rule.rule_type === 'fixed_value_compare' && (rule.operator === 'eq' || rule.operator === 'ne')
      ? normalizeExpectedValueMode(rule.expected_value_mode)
      : 'single'
  form.reference_variable_tag =
    rule.rule_type === 'cross_table_mapping' ? rule.reference_variable_tag ?? '' : ''
  form.sequence_direction = rule.rule_type === 'sequence_order_check' ? rule.sequence_direction ?? 'asc' : 'asc'
  form.sequence_step = rule.rule_type === 'sequence_order_check' ? rule.sequence_step ?? '1' : '1'
  form.sequence_start_mode =
    rule.rule_type === 'sequence_order_check' ? rule.sequence_start_mode ?? 'auto' : 'auto'
  form.sequence_start_value =
    rule.rule_type === 'sequence_order_check' ? rule.sequence_start_value ?? '' : ''
  return {
    form,
    compositeConfig: normalizeCompositeConfig(undefined),
    dualComparisons: normalizeDualCompositeComparisons(undefined),
    dualLeftFilters: normalizeDualCompositeFilters(undefined),
    dualRightFilters: normalizeDualCompositeFilters(undefined),
    pipelineConfig: normalizePipelineConfig(undefined, compositeVariables, rule.target_variable_tag ?? ''),
    mappingConfig: normalizeMappingConfig(undefined, compositeVariables, rule.target_variable_tag ?? ''),
  }
}

export function getSourcePath(source: DataSource | null | undefined): string {
  if (!source) {
    return ''
  }
  return source.pathOrUrl ?? source.path ?? source.url ?? ''
}

export function getCompositeFieldLabel(field: string, variable: VariableTag | null): string {
  const options = buildCompositeFieldOptions(variable)
  const resolvedField = resolveFieldOptionValue(options, field)
  const matchedOption = options.find((option) => option.value === resolvedField)
  if (matchedOption) {
    return matchedOption.label
  }
  return field === KEY_FIELD ? `${variable?.key_column || 'Key'} (Key)` : field
}

export function getOperatorLabel(value: FixedRuleOperator): string {
  return operatorSymbolMap[value]
}

export function getRuleSelectionLabel(value: FixedRuleSelection): string {
  return ruleSelectionOptions.find((item) => item.value === value)?.label ?? value
}

export function getRuleSelectionName(value: FixedRuleSelection): string {
  return ruleSelectionNameMap[value]
}

export function getRuleSelectionValue(rule: FixedRuleDefinition): FixedRuleSelection {
  if (rule.rule_type === 'fixed_value_compare') {
    return rule.operator ?? 'gt'
  }
  if (rule.rule_type === 'cross_table_mapping') {
    return 'in'
  }
  return rule.rule_type as FixedRuleSelection
}

export function getDualCompositeOperatorLabel(
  operator: FixedRuleOperator | 'not_null',
): string {
  if (operator === 'not_null') {
    return '都非空'
  }
  return operatorSymbolMap[operator]
}

export function getDualCompositeKeyCheckModeLabel(
  mode: 'baseline_only' | 'bidirectional' | undefined,
): string {
  return mode === 'bidirectional' ? '双向检查' : '基准变量为准'
}

export function getSequenceDirectionLabel(direction: 'asc' | 'desc' | undefined): string {
  return direction === 'desc' ? '降序' : '升序'
}

export function buildSequenceSummary(
  direction: 'asc' | 'desc' | undefined,
  step: string | undefined,
  startMode: 'auto' | 'manual' | undefined,
  startValue: string | undefined,
): string {
  const normalizedStep = step?.trim() || '1'
  if (startMode === 'manual') {
    return `顺序校验（${getSequenceDirectionLabel(direction)}，步长 ${normalizedStep}，起始值 ${startValue?.trim() || '0'}）`
  }
  return `顺序校验（${getSequenceDirectionLabel(direction)}，步长 ${normalizedStep}，自动起始）`
}

export function getVariableColumnSummary(variable: VariableTag | null | undefined): string {
  if (!variable) {
    return '未绑定变量'
  }
  if ((variable.variable_kind ?? 'single') === 'composite') {
    return `Key=${variable.key_column || 'Key'}；成员列：${
      (variable.columns ?? [])
        .filter((column) => column !== variable.key_column)
        .join(' / ') || '未配置'
    }`
  }
  return variable.column?.trim() || '未配置列'
}

export function buildVariableOptionLabel(variable: VariableTag): string {
  return variable.tag
}

export function buildDefaultRuleName(input: {
  variable: VariableTag | null
  selectedRule: FixedRuleSelection
  expectedValue: string
  referenceVariableTag?: string
  variableMap: Map<string, VariableTag>
  dualCompositeComparisons?: DualCompositeComparison[]
}): string {
  const {
    variable,
    selectedRule,
    expectedValue,
    referenceVariableTag = '',
    variableMap,
    dualCompositeComparisons = [],
  } = input
  if (!variable) {
    return ''
  }

  const normalizedSheet = variable.sheet.trim()
  if ((variable.variable_kind ?? 'single') === 'composite') {
    if (selectedRule === 'dual_composite_compare') {
      if (referenceVariableTag.trim() === variable.tag) {
        const firstComparison = dualCompositeComparisons[0]
        const leftField = firstComparison?.left_field
          ? getCompositeFieldLabel(firstComparison.left_field, variable)
          : '字段A'
        const rightField = firstComparison?.right_field
          ? getCompositeFieldLabel(firstComparison.right_field, variable)
          : '字段B'
        return `同变量筛选对比-${variable.tag}-${leftField} vs ${rightField}`
      }
      return `${normalizedSheet}-${variable.tag}-跨组变量校验`
    }
    if (selectedRule === 'multi_composite_pipeline_check') {
      return `${normalizedSheet}-${variable.tag}-多组串行校验`
    }
    if (selectedRule === 'multi_composite_mapping_check') {
      return `${normalizedSheet}-${variable.tag}-多组映射校验`
    }
    return `${normalizedSheet}-${variable.tag}-组合分支校验`
  }
  const normalizedColumn = variable.column?.trim() ?? ''
  if (!normalizedSheet || !normalizedColumn) {
    return ''
  }

  const baseName = `${normalizedSheet}-${normalizedColumn}-${getRuleSelectionName(selectedRule)}`
  if (selectedRule === 'in') {
    const referenceVariable = variableMap.get(referenceVariableTag.trim())
    const referenceLabel = referenceVariable?.column?.trim() || referenceVariableTag.trim()
    return referenceLabel ? `${baseName}-${referenceLabel}` : baseName
  }
  if (!isCompareRuleSelection(selectedRule)) {
    return baseName
  }

  const normalizedExpectedValue = expectedValue.trim()
  return normalizedExpectedValue ? `${baseName}-${normalizedExpectedValue}` : baseName
}

export function summarizeCondition(
  condition: CompositeCondition,
  variable: VariableTag | null,
): string {
  const fieldLabel = getCompositeFieldLabel(condition.field, variable)
  if (condition.operator === 'not_null') {
    return `${fieldLabel} 非空`
  }
  if (condition.operator === 'unique') {
    return `${fieldLabel} 唯一`
  }
  if (condition.operator === 'duplicate_required') {
    return `${fieldLabel} 必须重复`
  }
  if (condition.operator === 'regex') {
    return `${fieldLabel} 正则匹配 ${condition.expected_value ?? ''}`
  }
  if (condition.operator === 'contains') {
    return `${fieldLabel} 包含 ${condition.expected_value ?? ''}`
  }
  if (condition.operator === 'not_contains') {
    return `${fieldLabel} 不包含 ${condition.expected_value ?? ''}`
  }

  const operator = operatorSymbolMap[condition.operator as FixedRuleOperator]
  const expected =
    condition.value_source === 'field'
      ? getCompositeFieldLabel(condition.expected_field ?? '', variable)
      : condition.expected_value ?? ''
  return `${fieldLabel} ${operator} ${expected}`
}

export function buildRuleCondition(
  rule: FixedRuleDefinition,
  variableMap: Map<string, VariableTag>,
): string {
  const variable = variableMap.get(rule.target_variable_tag) ?? null
  const columnName =
    (variable?.variable_kind ?? 'single') === 'composite'
      ? variable?.tag ?? rule.target_variable_tag
      : variable?.column?.trim() || rule.target_variable_tag
  if (rule.rule_type === 'dual_composite_compare') {
    const referenceVariable = variableMap.get(rule.reference_variable_tag?.trim() ?? '')
    const comparisons = (rule.comparisons ?? []).map((comparison) => {
      const leftField = getCompositeFieldLabel(comparison.left_field, variable)
      const rightField = getCompositeFieldLabel(comparison.right_field, referenceVariable ?? null)
      if (comparison.operator === 'not_null') {
        return `${leftField} / ${rightField} 都非空`
      }
      return `${leftField} ${getDualCompositeOperatorLabel(comparison.operator)} ${rightField}`
    })
    const leftFilterSummary = rule.left_filters?.length
      ? `左侧筛选：${rule.left_filters.map((condition) => summarizeCondition(condition, variable)).join(' 且 ')}`
      : ''
    const rightFilterSummary = rule.right_filters?.length
      ? `右侧筛选：${rule.right_filters
          .map((condition) => summarizeCondition(condition, referenceVariable ?? null))
          .join(' 且 ')}`
      : ''
    const leftKey = getCompositeFieldLabel(rule.left_key_field ?? KEY_FIELD, variable)
    const rightKey = getCompositeFieldLabel(rule.right_key_field ?? KEY_FIELD, referenceVariable ?? null)
    const keySummary = `按 ${leftKey} ⇄ ${rightKey} 关联`
    const filterSummary = [leftFilterSummary, rightFilterSummary].filter(Boolean).join('；')
    return `${columnName} 对比 ${referenceVariable?.tag ?? rule.reference_variable_tag ?? '未绑定目标变量'}（${getDualCompositeKeyCheckModeLabel(rule.key_check_mode)}，${keySummary}）${filterSummary ? `；${filterSummary}` : ''}${comparisons.length ? `：${comparisons.join('；')}` : ''}`
  }
  if (rule.rule_type === 'composite_condition_check') {
    const segments: string[] = []
    if (rule.composite_config?.global_filters.length) {
      segments.push(
        `全局：${rule.composite_config.global_filters
          .map((condition) => summarizeCondition(condition, variable))
          .join(' 且 ')}`,
      )
    }
    rule.composite_config?.branches.forEach((branch, index) => {
      segments.push(
        `分支 ${index + 1}：${
          branch.filters.length
            ? branch.filters.map((condition) => summarizeCondition(condition, variable)).join(' 且 ')
            : '命中全部'
        } => ${branch.assertions.map((condition) => summarizeCondition(condition, variable)).join('，')}`,
      )
    })
    return segments.join('；')
  }
  if (rule.rule_type === 'multi_composite_pipeline_check') {
    const nodes = rule.pipeline_config?.nodes ?? []
    return nodes
      .map((node, index) => {
        const nodeVariable = variableMap.get(node.variable_tag) ?? null
        const filterSummary = node.filters.length
          ? node.filters.map((condition) => summarizeCondition(condition, nodeVariable)).join(' 且 ')
          : '命中全部'
        const assertionSummary = node.assertions.length
          ? node.assertions.map((condition) => summarizeCondition(condition, nodeVariable)).join('，')
          : '未配置判定'
        return `节点 ${index + 1}：${filterSummary} => ${assertionSummary}`
      })
      .join('；')
  }
  if (rule.rule_type === 'multi_composite_mapping_check') {
    const nodes = rule.mapping_config?.nodes ?? []
    return nodes
      .map((node, index) => {
        const exclusionRangeCount = node.filters.reduce(
          (total, condition) => total + (condition.exclusion_ranges?.length ?? 0),
          0,
        )
        return `映射节点 ${index + 1}：${node.filters.length} 条筛选，${exclusionRangeCount} 段排除范围`
      })
      .join('；')
  }
  if (rule.rule_type === 'not_null') {
    return `${columnName} 非空校验`
  }
  if (rule.rule_type === 'unique') {
    return `${columnName} 唯一校验`
  }
  if (rule.rule_type === 'cross_table_mapping') {
    const referenceVariable = variableMap.get(rule.reference_variable_tag?.trim() ?? '')
    const referenceLabel =
      referenceVariable?.column?.trim() || rule.reference_variable_tag?.trim() || '未绑定基础字典'
    return `${columnName} 包含于 ${referenceLabel}`
  }
  if (rule.rule_type === 'sequence_order_check') {
    return `${columnName} ${buildSequenceSummary(
      rule.sequence_direction,
      rule.sequence_step,
      rule.sequence_start_mode,
      rule.sequence_start_value,
    )}`
  }
  if (rule.rule_type === 'regex_check') {
    return `${columnName} 正则匹配 ${rule.expected_value ?? ''}`
  }
  return `${columnName} ${getOperatorLabel(rule.operator ?? 'gt')} ${rule.expected_value ?? ''}`
}

export function buildRuleSelectionSummary(rule: FixedRuleDefinition): string {
  if (rule.rule_type === 'dual_composite_compare') {
    return `跨组变量校验（${getDualCompositeKeyCheckModeLabel(rule.key_check_mode)}，${rule.comparisons?.length ?? 0} 条比较）`
  }
  if (rule.rule_type === 'multi_composite_pipeline_check') {
    const nodeCount = rule.pipeline_config?.nodes.length ?? 0
    return nodeCount <= 1 ? '1 个变量组' : `${nodeCount} 个变量组串行`
  }
  if (rule.rule_type === 'multi_composite_mapping_check') {
    const nodeCount = rule.mapping_config?.nodes.length ?? 0
    return nodeCount <= 1 ? '1 个映射节点' : `${nodeCount} 个映射节点`
  }
  if (rule.rule_type === 'composite_condition_check') {
    return '组合分支校验'
  }
  if (rule.rule_type === 'sequence_order_check') {
    return buildSequenceSummary(
      rule.sequence_direction,
      rule.sequence_step,
      rule.sequence_start_mode,
      rule.sequence_start_value,
    )
  }
  if (rule.rule_type === 'regex_check') {
    return '正则校验'
  }
  return getRuleSelectionLabel(getRuleSelectionValue(rule))
}

export function buildRuleVariableSummary(
  rule: FixedRuleDefinition,
  variableMap: Map<string, VariableTag>,
): string {
  const variable = variableMap.get(rule.target_variable_tag) ?? null
  if (!variable) {
    return '目标变量已失效，请重新选择变量。'
  }
  return `${variable.source_id} / ${variable.sheet} / ${getVariableColumnSummary(variable)}`
}

export function buildRuleSourcePathSummary(
  rule: FixedRuleDefinition,
  variableMap: Map<string, VariableTag>,
  sourceMap: Map<string, DataSource>,
): string {
  const variable = variableMap.get(rule.target_variable_tag) ?? null
  const source = variable ? sourceMap.get(variable.source_id) ?? null : null
  return getSourcePath(source) || '当前数据源未记录路径'
}

export function buildRuleCompareValueSummary(
  rule: FixedRuleDefinition,
  variableMap: Map<string, VariableTag>,
): string {
  if (rule.rule_type === 'fixed_value_compare') {
    return rule.expected_value ?? ''
  }
  if (rule.rule_type === 'regex_check') {
    return rule.expected_value ?? ''
  }
  if (rule.rule_type === 'cross_table_mapping') {
    const referenceVariable = variableMap.get(rule.reference_variable_tag?.trim() ?? '')
    return referenceVariable?.tag ?? rule.reference_variable_tag ?? '未绑定基础字典变量'
  }
  if (rule.rule_type === 'composite_condition_check') {
    return `${rule.composite_config?.branches.length ?? 0} 个分支`
  }
  if (rule.rule_type === 'dual_composite_compare') {
    return `${rule.comparisons?.length ?? 0} 条字段比较`
  }
  if (rule.rule_type === 'multi_composite_pipeline_check') {
    return `${rule.pipeline_config?.nodes.length ?? 0} 个节点`
  }
  if (rule.rule_type === 'multi_composite_mapping_check') {
    const nodes = rule.mapping_config?.nodes ?? []
    const filterCount = nodes.reduce((total, node) => total + node.filters.length, 0)
    const rangeCount = nodes.reduce(
      (total, node) =>
        total + node.filters.reduce(
          (subtotal, condition) => subtotal + (condition.exclusion_ranges?.length ?? 0),
          0,
        ),
      0,
    )
    return `${nodes.length} 个节点 / ${filterCount} 条筛选 / ${rangeCount} 段排除范围`
  }
  return '—'
}

export function validateWorkbenchRuleForm(input: {
  form: WorkbenchRuleFormState
  selectedRuleVariable: VariableTag | null
  selectedReferenceVariable: VariableTag | null
  shouldShowTopTargetVariable: boolean
  isSingleRuleEntry: boolean
  isCompositeRuleEntry: boolean
  isDualCompositeRule: boolean
  isSameDualCompositeVariable: boolean
  referenceVariableOptions: VariableTag[]
  compositeFieldOptions: FieldOption[]
  referenceCompositeFieldOptions: FieldOption[]
  compositeConfig: CompositeRuleConfig
  dualComparisons: DualCompositeComparison[]
  dualLeftFilters: CompositeCondition[]
  dualRightFilters: CompositeCondition[]
  pipelineConfig: MultiCompositePipelineConfig
  mappingConfig: MultiCompositeMappingConfig
  variableMap: Map<string, VariableTag>
}): WorkbenchRuleFormValidationResult {
  const {
    form,
    selectedRuleVariable,
    selectedReferenceVariable,
    shouldShowTopTargetVariable,
    isSingleRuleEntry,
    isCompositeRuleEntry,
    isDualCompositeRule,
    isSameDualCompositeVariable,
    referenceVariableOptions,
    compositeFieldOptions,
    referenceCompositeFieldOptions,
    compositeConfig,
    dualComparisons,
    dualLeftFilters,
    dualRightFilters,
    pipelineConfig,
    mappingConfig,
    variableMap,
  } = input

  if (!form.rule_name.trim()) {
    return { valid: false, message: '规则名称不能为空。' }
  }

  if (shouldShowTopTargetVariable) {
    if (!form.target_variable_tag.trim()) {
      return {
        valid: false,
        message: isDualCompositeRule ? '请先选择基准变量。' : '请先选择目标变量。',
      }
    }

    if (!selectedRuleVariable) {
      return {
        valid: false,
        message: isDualCompositeRule
          ? '当前基准变量不存在，请重新选择。'
          : '当前目标变量不存在，请重新选择。',
      }
    }

    if (isSingleRuleEntry && (selectedRuleVariable.variable_kind ?? 'single') !== 'single') {
      return { valid: false, message: '单一变量校验只能选择单变量。' }
    }

    if (isCompositeRuleEntry && (selectedRuleVariable.variable_kind ?? 'single') !== 'composite') {
      return { valid: false, message: '当前规则类型只能选择组合变量。' }
    }
  }

  if (form.rule_entry_type === 'dual_composite') {
    if (!form.reference_variable_tag.trim()) {
      return { valid: false, message: '请选择目标变量（变量 2）。' }
    }
    if (!selectedReferenceVariable) {
      return { valid: false, message: '当前目标变量（变量 2）不存在，请重新选择。' }
    }
    const leftKeyError = validateDualCompositeKeyField(
      form.left_key_field,
      '左侧',
      compositeFieldOptions,
    )
    if (leftKeyError) {
      return { valid: false, message: leftKeyError }
    }
    const rightKeyError = validateDualCompositeKeyField(
      form.right_key_field,
      '右侧',
      referenceCompositeFieldOptions,
    )
    if (rightKeyError) {
      return { valid: false, message: rightKeyError }
    }
    if (isSameDualCompositeVariable && (!dualLeftFilters.length || !dualRightFilters.length)) {
      return { valid: false, message: '同一组合变量筛选对比时，左右筛选条件都不能为空。' }
    }
    const leftFilterError = validateDualCompositeFilters(
      dualLeftFilters,
      '左侧',
      compositeFieldOptions,
    )
    if (leftFilterError) {
      return { valid: false, message: leftFilterError }
    }
    const rightFilterError = validateDualCompositeFilters(
      dualRightFilters,
      '右侧',
      referenceCompositeFieldOptions,
    )
    if (rightFilterError) {
      return { valid: false, message: rightFilterError }
    }
    if (!dualComparisons.length) {
      return { valid: false, message: '跨组变量校验至少需要一条字段比较规则。' }
    }
    for (let index = 0; index < dualComparisons.length; index += 1) {
      const error = validateDualCompositeComparison(
        dualComparisons[index],
        `字段比较 ${index + 1}`,
        compositeFieldOptions,
        referenceCompositeFieldOptions,
      )
      if (error) {
        return { valid: false, message: error }
      }
    }
    return { valid: true }
  }

  if (form.rule_entry_type === 'composite') {
    if (!compositeConfig.branches.length) {
      return { valid: false, message: '组合分支校验至少需要一个条件分支。' }
    }

    for (let index = 0; index < compositeConfig.global_filters.length; index += 1) {
      const error = validateCompositeCondition(
        compositeConfig.global_filters[index],
        'filter',
        `全局筛选条件 ${index + 1}`,
        compositeFieldOptions,
      )
      if (error) {
        return { valid: false, message: error }
      }
    }

    for (let branchIndex = 0; branchIndex < compositeConfig.branches.length; branchIndex += 1) {
      const branch = compositeConfig.branches[branchIndex]
      if (!branch.assertions.length) {
        return { valid: false, message: `分支 ${branchIndex + 1} 至少需要一条校验条件。` }
      }
      for (let filterIndex = 0; filterIndex < branch.filters.length; filterIndex += 1) {
        const error = validateCompositeCondition(
          branch.filters[filterIndex],
          'filter',
          `分支 ${branchIndex + 1} 的筛选条件 ${filterIndex + 1}`,
          compositeFieldOptions,
        )
        if (error) {
          return { valid: false, message: error }
        }
      }
      for (let assertionIndex = 0; assertionIndex < branch.assertions.length; assertionIndex += 1) {
        const error = validateCompositeCondition(
          branch.assertions[assertionIndex],
          'assertion',
          `分支 ${branchIndex + 1} 的校验条件 ${assertionIndex + 1}`,
          compositeFieldOptions,
        )
        if (error) {
          return { valid: false, message: error }
        }
      }
    }

    return { valid: true }
  }

  if (form.rule_entry_type === 'multi_composite_pipeline') {
    if (!pipelineConfig.nodes.length) {
      return { valid: false, message: '多组串行校验至少需要一个节点。' }
    }

    for (let nodeIndex = 0; nodeIndex < pipelineConfig.nodes.length; nodeIndex += 1) {
      const node = pipelineConfig.nodes[nodeIndex]
      if (!node.variable_tag.trim()) {
        return { valid: false, message: `节点 ${nodeIndex + 1} 缺少组合变量。` }
      }
      const nodeVariable = variableMap.get(node.variable_tag) ?? null
      if (!nodeVariable || (nodeVariable.variable_kind ?? 'single') !== 'composite') {
        return { valid: false, message: `节点 ${nodeIndex + 1} 只能选择组合变量。` }
      }
      const nodeFieldOptions = buildCompositeFieldOptions(nodeVariable)
      for (let filterIndex = 0; filterIndex < node.filters.length; filterIndex += 1) {
        const error = validateCompositeCondition(
          node.filters[filterIndex],
          'filter',
          `节点 ${nodeIndex + 1} 的前置过滤 ${filterIndex + 1}`,
          nodeFieldOptions,
        )
        if (error) {
          return { valid: false, message: error }
        }
      }
      if (!node.assertions.length) {
        return { valid: false, message: `节点 ${nodeIndex + 1} 至少需要一条最终判定。` }
      }
      for (let assertionIndex = 0; assertionIndex < node.assertions.length; assertionIndex += 1) {
        const error = validateCompositeCondition(
          node.assertions[assertionIndex],
          'assertion',
          `节点 ${nodeIndex + 1} 的最终判定 ${assertionIndex + 1}`,
          nodeFieldOptions,
          false,
        )
        if (error) {
          return { valid: false, message: error }
        }
      }
    }

    return {
      valid: true,
      normalizedTargetTag: pipelineConfig.nodes[0]?.variable_tag ?? '',
    }
  }

  if (form.rule_entry_type === 'multi_composite_mapping') {
    if (!mappingConfig.nodes.length) {
      return { valid: false, message: '多组映射校验至少需要一个节点。' }
    }

    for (let nodeIndex = 0; nodeIndex < mappingConfig.nodes.length; nodeIndex += 1) {
      const node = mappingConfig.nodes[nodeIndex]
      if (!node.variable_tag.trim()) {
        return { valid: false, message: `映射节点 ${nodeIndex + 1} 缺少组合变量。` }
      }
      const nodeVariable = variableMap.get(node.variable_tag) ?? null
      if (!nodeVariable || (nodeVariable.variable_kind ?? 'single') !== 'composite') {
        return { valid: false, message: `映射节点 ${nodeIndex + 1} 只能选择组合变量。` }
      }
      const nodeFieldOptions = buildCompositeFieldOptions(nodeVariable)
      if (!node.filters.length) {
        return { valid: false, message: `映射节点 ${nodeIndex + 1} 至少需要一条筛选条件。` }
      }
      for (let filterIndex = 0; filterIndex < node.filters.length; filterIndex += 1) {
        const filterLabel = `映射节点 ${nodeIndex + 1} 的筛选条件 ${filterIndex + 1}`
        const error = validateCompositeCondition(
          node.filters[filterIndex],
          'filter',
          filterLabel,
          nodeFieldOptions,
        )
        if (error) {
          return { valid: false, message: error }
        }
        const rangeError = validateMappingExclusionRanges(
          node.filters[filterIndex].exclusion_ranges,
          `${filterLabel} 的`,
        )
        if (rangeError) {
          return { valid: false, message: rangeError }
        }
      }
    }

    return {
      valid: true,
      normalizedTargetTag: mappingConfig.nodes[0]?.variable_tag ?? '',
    }
  }

  const shouldShowExpectedValue =
    isSingleRuleEntry &&
    (isCompareRuleSelection(form.selected_rule) || form.selected_rule === 'regex_check')

  if (!shouldShowExpectedValue) {
    if (form.selected_rule === 'sequence_order_check') {
      if (!form.sequence_step.trim()) {
        return { valid: false, message: '请填写步长。' }
      }
      if (Number.isNaN(Number(form.sequence_step)) || Number(form.sequence_step) <= 0) {
        return { valid: false, message: '步长必须是大于 0 的合法数字。' }
      }
      if (form.sequence_start_mode === 'manual') {
        if (!form.sequence_start_value.trim()) {
          return { valid: false, message: '请填写起始值。' }
        }
        if (Number.isNaN(Number(form.sequence_start_value))) {
          return { valid: false, message: '起始值必须是合法数字。' }
        }
      }
      return { valid: true }
    }
    if (form.selected_rule === 'in') {
      if (!form.reference_variable_tag.trim()) {
        return { valid: false, message: '请选择基础字典变量。' }
      }
      if (form.reference_variable_tag === form.target_variable_tag) {
        return { valid: false, message: '基础字典变量不能与目标变量相同。' }
      }
      if (!referenceVariableOptions.some((variable) => variable.tag === form.reference_variable_tag)) {
        return { valid: false, message: '当前基础字典变量不存在，请重新选择。' }
      }
    }
    return { valid: true }
  }
  if (!form.expected_value.trim()) {
    return {
      valid: false,
      message: form.selected_rule === 'regex_check' ? '请填写正则表达式。' : '请填写比较值。',
    }
  }
  if (
    (form.selected_rule === 'eq' || form.selected_rule === 'ne') &&
    form.expected_value_mode === 'set' &&
    parseExpectedValueSet(form.expected_value).length === 0
  ) {
    return { valid: false, message: '规则集至少需要填写一个固定值。' }
  }
  if (
    (form.selected_rule === 'gt' || form.selected_rule === 'lt') &&
    Number.isNaN(Number(form.expected_value))
  ) {
    return { valid: false, message: '大于/小于规则的比较值必须是合法数字。' }
  }

  return { valid: true }
}

export function buildWorkbenchRuleFromForm(input: {
  form: WorkbenchRuleFormState
  compositeConfig: CompositeRuleConfig
  dualComparisons: DualCompositeComparison[]
  dualLeftFilters: CompositeCondition[]
  dualRightFilters: CompositeCondition[]
  pipelineConfig: MultiCompositePipelineConfig
  mappingConfig: MultiCompositeMappingConfig
  compositeFieldOptions: FieldOption[]
  referenceCompositeFieldOptions: FieldOption[]
  compositeVariables: VariableTag[]
}): WorkbenchRuleBuildResult {
  const {
    form,
    compositeConfig,
    dualComparisons,
    dualLeftFilters,
    dualRightFilters,
    pipelineConfig,
    mappingConfig,
    compositeFieldOptions,
    referenceCompositeFieldOptions,
    compositeVariables,
  } = input

  if (form.rule_entry_type === 'dual_composite') {
    return {
      rule: {
        rule_id: form.rule_id || undefined,
        group_id: form.group_id,
        rule_name: form.rule_name,
        target_variable_tag: form.target_variable_tag,
        display_field: form.display_field,
        reference_variable_tag: form.reference_variable_tag,
        rule_type: 'dual_composite_compare',
        key_check_mode: form.key_check_mode,
        left_key_field: resolveFieldOptionValue(compositeFieldOptions, form.left_key_field) ?? KEY_FIELD,
        right_key_field:
          resolveFieldOptionValue(referenceCompositeFieldOptions, form.right_key_field) ?? KEY_FIELD,
        comparisons: normalizeDualCompositeComparisons(dualComparisons),
        left_filters: normalizeDualCompositeFilters(dualLeftFilters),
        right_filters: normalizeDualCompositeFilters(dualRightFilters),
      },
    }
  }

  if (form.rule_entry_type === 'composite') {
    return {
      rule: {
        rule_id: form.rule_id || undefined,
        group_id: form.group_id,
        rule_name: form.rule_name,
        target_variable_tag: form.target_variable_tag,
        display_field: form.display_field,
        rule_type: 'composite_condition_check',
        composite_config: normalizeCompositeConfig(compositeConfig),
      },
    }
  }

  if (form.rule_entry_type === 'multi_composite_pipeline') {
    const normalizedPipelineConfig = normalizePipelineConfig(
      pipelineConfig,
      compositeVariables,
      form.target_variable_tag,
    )
    const firstNodeVariableTag = normalizedPipelineConfig.nodes[0]?.variable_tag ?? ''
    return {
      normalizedTargetTag: firstNodeVariableTag,
      rule: {
        rule_id: form.rule_id || undefined,
        group_id: form.group_id,
        rule_name: form.rule_name,
        target_variable_tag: firstNodeVariableTag,
        display_field: '',
        rule_type: 'multi_composite_pipeline_check',
        pipeline_config: normalizedPipelineConfig,
      },
    }
  }

  if (form.rule_entry_type === 'multi_composite_mapping') {
    const normalizedMappingConfig = normalizeMappingConfig(
      mappingConfig,
      compositeVariables,
      form.target_variable_tag,
    )
    const firstNodeVariableTag = normalizedMappingConfig.nodes[0]?.variable_tag ?? ''
    return {
      normalizedTargetTag: firstNodeVariableTag,
      rule: {
        rule_id: form.rule_id || undefined,
        group_id: form.group_id,
        rule_name: form.rule_name,
        target_variable_tag: firstNodeVariableTag,
        display_field: '',
        rule_type: 'multi_composite_mapping_check',
        mapping_config: normalizedMappingConfig,
      },
    }
  }

  const selectedRule = form.selected_rule
  if (selectedRule === 'sequence_order_check') {
    return {
      rule: {
        rule_id: form.rule_id || undefined,
        group_id: form.group_id,
        rule_name: form.rule_name,
        target_variable_tag: form.target_variable_tag,
        display_field: form.display_field,
        rule_type: 'sequence_order_check',
        sequence_direction: form.sequence_direction,
        sequence_step: form.sequence_step,
        sequence_start_mode: form.sequence_start_mode,
        sequence_start_value: form.sequence_start_mode === 'manual' ? form.sequence_start_value : '',
      },
    }
  }
  if (selectedRule === 'in') {
    return {
      rule: {
        rule_id: form.rule_id || undefined,
        group_id: form.group_id,
        rule_name: form.rule_name,
        target_variable_tag: form.target_variable_tag,
        display_field: form.display_field,
        rule_type: 'cross_table_mapping',
        reference_variable_tag: form.reference_variable_tag,
      },
    }
  }
  if (selectedRule === 'regex_check') {
    return {
      rule: {
        rule_id: form.rule_id || undefined,
        group_id: form.group_id,
        rule_name: form.rule_name,
        target_variable_tag: form.target_variable_tag,
        display_field: form.display_field,
        rule_type: 'regex_check',
        expected_value: form.expected_value,
      },
    }
  }
  if (isCompareRuleSelection(selectedRule)) {
    return {
      rule: {
        rule_id: form.rule_id || undefined,
        group_id: form.group_id,
        rule_name: form.rule_name,
        target_variable_tag: form.target_variable_tag,
        display_field: form.display_field,
        rule_type: 'fixed_value_compare',
        operator: selectedRule,
        expected_value: form.expected_value,
        expected_value_mode:
          selectedRule === 'eq' || selectedRule === 'ne'
            ? normalizeExpectedValueMode(form.expected_value_mode)
            : undefined,
      },
    }
  }

  return {
    rule: {
      rule_id: form.rule_id || undefined,
      group_id: form.group_id,
      rule_name: form.rule_name,
      target_variable_tag: form.target_variable_tag,
      display_field: form.display_field,
      rule_type: selectedRule,
    },
  }
}
