import type {
  CompositeAssertionOperator,
  CompositeFilterOperator,
  ExpectedValueMode,
  FixedRuleOperator,
  FixedRuleSelection,
  FixedRuleType,
  PipelineAssertionOperator,
} from '../types/fixedRules'

export type RuleEntryType =
  | 'single'
  | 'composite'
  | 'dual_composite'
  | 'multi_composite_pipeline'
  | 'multi_composite_mapping'

export const KEY_FIELD = '__key__'

export const RULE_SELECTION_OPTIONS: Array<{ label: string; value: FixedRuleSelection }> = [
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

export const RULE_ENTRY_TYPE_OPTIONS: Array<{ label: string; value: RuleEntryType }> = [
  { label: '单一变量校验', value: 'single' },
  { label: '组合分支校验', value: 'composite' },
  { label: '跨组变量校验', value: 'dual_composite' },
  { label: '多组串行校验', value: 'multi_composite_pipeline' },
  { label: '多组映射校验', value: 'multi_composite_mapping' },
]

export const DUAL_COMPOSITE_OPERATOR_OPTIONS: Array<{
  label: string
  value: FixedRuleOperator | 'not_null'
}> = [
  { label: '等于 (=)', value: 'eq' },
  { label: '不等于 (!=)', value: 'ne' },
  { label: '大于 (>)', value: 'gt' },
  { label: '小于 (<)', value: 'lt' },
  { label: '非空校验', value: 'not_null' },
]

export const COMPOSITE_FILTER_OPTIONS: Array<{
  label: string
  value: CompositeFilterOperator
}> = [
  { label: '等于 (=)', value: 'eq' },
  { label: '不等于 (!=)', value: 'ne' },
  { label: '大于 (>)', value: 'gt' },
  { label: '小于 (<)', value: 'lt' },
  { label: '非空校验', value: 'not_null' },
  { label: '包含', value: 'contains' },
  { label: '不包含', value: 'not_contains' },
]

export const COMPOSITE_ASSERTION_OPTIONS: Array<{
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

export const PIPELINE_ASSERTION_OPTIONS: Array<{
  label: string
  value: PipelineAssertionOperator
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

export const EXPECTED_VALUE_MODE_OPTIONS: Array<{ label: string; value: ExpectedValueMode }> = [
  { label: '固定值', value: 'single' },
  { label: '规则集', value: 'set' },
]

export const COMPARE_RULE_SELECTIONS = new Set<FixedRuleOperator>(['eq', 'ne', 'gt', 'lt'])

export const COMPOSITE_COMPARE_OPERATORS = new Set<
  CompositeFilterOperator | CompositeAssertionOperator
>(['eq', 'ne', 'gt', 'lt'])

export const RULE_SELECTION_NAME_MAP: Record<FixedRuleSelection, string> = {
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

export const RULE_TYPE_NAME_MAP: Record<FixedRuleType, string> = {
  fixed_value_compare: '固定值比较',
  regex_check: '正则校验',
  not_null: '非空校验',
  unique: '唯一校验',
  sequence_order_check: '顺序校验',
  cross_table_mapping: '包含校验',
  composite_condition_check: '组合分支校验',
  dual_composite_compare: '跨组变量校验',
  multi_composite_pipeline_check: '多组串行校验',
  multi_composite_mapping_check: '多组映射校验',
  package_items_compare: 'IAP礼包校验',
}

export const OPERATOR_SYMBOL_MAP: Record<FixedRuleOperator, string> = {
  eq: '=',
  ne: '!=',
  gt: '>',
  lt: '<',
}
