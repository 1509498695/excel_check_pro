import type { CreatableSourceType, ExpectedType, SourceType } from '../types/workbench'

export const DEFAULT_SOURCE_TYPE: CreatableSourceType = 'svn'

export const SOURCE_TYPE_OPTIONS: Array<{ label: string; value: CreatableSourceType; disabled?: boolean }> = [
  { label: 'SVN（推荐 HTTP 链接）', value: 'svn' },
  { label: '本地 Excel (.xlsx / .xls)', value: 'local_excel' },
  { label: '飞书电子表格', value: 'feishu' },
]

export const EXPECTED_TYPE_OPTIONS: Array<{ label: string; value: ExpectedType }> = [
  { label: '字符串 (str)', value: 'str' },
  { label: 'JSON (json)', value: 'json' },
]

/** 供结果区等处的规则类型中文展示；主工作台步骤 3 已改为规则组编排，不再使用模板列表。 */
export const STATIC_RULE_TEMPLATES = [
  {
    ruleType: 'not_null',
    title: '非空校验',
    description: '检查目标字段是否存在空值、空字符串或仅包含空白符的内容。',
    level: 'error',
  },
  {
    ruleType: 'unique',
    title: '唯一校验',
    description: '检查目标字段是否存在重复值，空值默认不参与重复判断。',
    level: 'warning',
  },
  {
    ruleType: 'fixed_value_compare',
    title: '常量比较',
    description: '将列值与给定常量按等于、不等于、大于或小于比较。',
    level: 'error',
  },
  {
    ruleType: 'composite_condition_check',
    title: '组合变量条件分支',
    description: '对组合变量按全局筛选与分支条件做校验。',
    level: 'error',
  },
  {
    ruleType: 'dual_composite_compare',
    title: '双组合变量比对',
    description: '按外层 Key 关联两个组合变量，再比较内部字段值。',
    level: 'error',
  },
  {
    ruleType: 'cross_table_mapping',
    title: '跨表映射校验',
    description: '历史规则类型，工作台 UI 已不再配置；引擎仍支持。',
    level: 'error',
  },
] as const

export const SAMPLE_SOURCE_PATH = 'D:/project/excel-check/backend/tests/data/minimal_rules.xlsx'

export function getSourceTypeLabel(type: SourceType): string {
  if (type === 'local_csv') return 'CSV（已不支持）'
  return SOURCE_TYPE_OPTIONS.find((item) => item.value === type)?.label ?? type
}

export function getRuleTitle(ruleType: string): string {
  return STATIC_RULE_TEMPLATES.find((item) => item.ruleType === ruleType)?.title ?? ruleType
}

export function getRuleLevelTone(ruleType: string): 'danger' | 'warning' | 'primary' {
  if (
    ruleType === 'not_null' ||
    ruleType === 'cross_table_mapping' ||
    ruleType === 'fixed_value_compare' ||
    ruleType === 'composite_condition_check' ||
    ruleType === 'dual_composite_compare'
  ) {
    return 'danger'
  }

  if (ruleType === 'unique') {
    return 'warning'
  }

  return 'primary'
}
