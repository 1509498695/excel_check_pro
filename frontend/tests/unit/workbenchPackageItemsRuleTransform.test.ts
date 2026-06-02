import { describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useWorkbenchStore } from '../../src/store/workbench'
import type { FixedRuleDefinition } from '../../src/types/fixedRules'
import type { DataSource, VariableTag } from '../../src/types/workbench'
import { buildTaskTreePayload } from '../../src/utils/taskTree'
import { orchestrationRulesToValidationRules } from '../../src/utils/workbenchOrchestrationRules'

const sources: DataSource[] = [
  {
    id: 'feishu-plan',
    type: 'feishu',
    pathOrUrl: 'https://demo.feishu.cn/sheets/shtcnabc123',
  },
  {
    id: 'config-src',
    type: 'local_excel',
    path: 'D:/tmp/package.xlsx',
  },
]

const variables: VariableTag[] = [
  {
    tag: '[package-config]',
    source_id: 'config-src',
    sheet: 'package_config',
    variable_kind: 'composite',
    columns: ['INT_PackageId', 'STR_Items'],
    key_column: 'INT_PackageId',
  },
]

function packageRule(overrides: Partial<FixedRuleDefinition> = {}): FixedRuleDefinition {
  return {
    rule_id: 'rule-package',
    group_id: 'ungrouped',
    rule_name: '礼包道具配置校验',
    target_variable_tag: '__runtime_package_plan__:rule-package',
    display_field: '礼包id',
    rule_type: 'package_items_compare',
    reference_variable_tag: '[package-config]',
    left_package_field: '礼包id',
    left_item_field: '道具ID',
    left_count_field: '个数',
    right_package_field: 'INT_PackageId',
    right_items_field: 'STR_Items',
    package_parse_config: {
      feishu_source_id: 'feishu-plan',
      feishu_sheet_id: 'gid_plan',
      feishu_sheet_name: '礼包规划',
      parse_strategy: 'auto',
      ai_parse_mode: 'auto',
      validation_scope: 'all',
    },
    ...overrides,
  }
}

describe('workbench package items rule transform', () => {
  it('keeps package fields when upserting orchestration rules', () => {
    setActivePinia(createPinia())
    const store = useWorkbenchStore()
    store.variables = variables

    store.upsertOrchestrationRule(packageRule())

    expect(store.orchestrationRules[0]).toMatchObject({
      rule_type: 'package_items_compare',
      target_variable_tag: '__runtime_package_plan__:rule-package',
      reference_variable_tag: '[package-config]',
      left_package_field: '礼包id',
      left_item_field: '道具ID',
      left_count_field: '个数',
      right_package_field: 'INT_PackageId',
      right_items_field: 'STR_Items',
      package_parse_config: {
        feishu_source_id: 'feishu-plan',
        feishu_sheet_id: 'gid_plan',
        validation_scope: 'all',
      },
    })
    expect(store.invalidOrchestrationRuleIds).toEqual([])
  })

  it('converts package orchestration rules to backend runtime params', () => {
    const validationRule = orchestrationRulesToValidationRules(variables, [packageRule()])[0]

    expect(validationRule).toMatchObject({
      rule_id: 'rule-package',
      rule_type: 'package_items_compare',
      params: {
        reference_variable_tag: '[package-config]',
        right_package_field: 'INT_PackageId',
        right_items_field: 'STR_Items',
        package_parse_config: {
          feishu_source_id: 'feishu-plan',
          feishu_sheet_id: 'gid_plan',
          validation_scope: 'all',
        },
      },
    })

    const taskTree = buildTaskTreePayload(sources, variables, [validationRule])
    expect(taskTree.rules[0].params.package_parse_config).not.toHaveProperty('package_id_filter')
    expect(taskTree.rules[0].params).not.toHaveProperty('package_id_filter')
  })

  it('preserves specified package filter in rule params and parse config', () => {
    const validationRule = orchestrationRulesToValidationRules(variables, [
      packageRule({
        package_id_filter: '26042411, 26042412',
        package_parse_config: {
          feishu_source_id: 'feishu-plan',
          feishu_sheet_id: 'gid_plan',
          feishu_sheet_name: '礼包规划',
          parse_strategy: 'auto',
          ai_parse_mode: 'auto',
          validation_scope: 'specified',
          package_id_filter: '26042411, 26042412',
        },
      }),
    ])[0]

    const taskTree = buildTaskTreePayload(sources, variables, [validationRule])

    expect(taskTree.rules[0].params.package_id_filter).toBe('26042411, 26042412')
    expect(taskTree.rules[0].params.package_parse_config).toMatchObject({
      validation_scope: 'specified',
      package_id_filter: '26042411, 26042412',
    })
  })
})
