import { describe, expect, it } from 'vitest'

import type { VariableTag } from '../../src/types/workbench'
import {
  KEY_FIELD,
  buildCompositeFieldOptions,
  createDefaultWorkbenchRuleFormState,
  createMappingFilter,
  createMappingExclusionRange,
  normalizeMappingConfig,
  validateWorkbenchRuleForm,
} from '../../src/features/rule-orchestration'

const compositeVariable: VariableTag = {
  tag: '[items-composite]',
  source_id: 'src_items',
  sheet: 'items',
  variable_kind: 'composite',
  key_column: 'ID',
  columns: ['ID', 'Type', 'Reward'],
  expected_type: 'json',
}

describe('rule orchestration form model', () => {
  it('exports shared form defaults and field option helpers from the feature boundary', () => {
    expect(createDefaultWorkbenchRuleFormState('group-a', '[items-composite]')).toMatchObject({
      group_id: 'group-a',
      target_variable_tag: '[items-composite]',
      rule_entry_type: 'single',
      left_key_field: KEY_FIELD,
      right_key_field: KEY_FIELD,
    })

    expect(buildCompositeFieldOptions(compositeVariable)).toEqual([
      { label: 'ID (内部 Key)', value: KEY_FIELD },
      { label: 'ID (原始字段)', value: 'ID' },
      { label: 'Type', value: 'Type' },
      { label: 'Reward', value: 'Reward' },
    ])
  })

  it('keeps mapping defaults and validation messages stable after extraction', () => {
    expect(createMappingExclusionRange(3)).toMatchObject({
      start_row: 3,
      end_row: 3,
      expected_value: '',
    })

    const form = {
      ...createDefaultWorkbenchRuleFormState('group-a', ''),
      rule_name: 'Bad mapping',
      rule_entry_type: 'multi_composite_mapping' as const,
      selected_rule: 'multi_composite_mapping_check' as const,
    }
    const variableMap = new Map([[compositeVariable.tag, compositeVariable]])
    const mappingConfig = normalizeMappingConfig(undefined, [compositeVariable])
    mappingConfig.nodes[0].filters = [
      {
        ...createMappingFilter(),
        field: 'Type',
        operator: 'eq',
        expected_value: 'skip',
      },
    ]
    mappingConfig.nodes[0].filters[0].exclusion_ranges = [
      {
        range_id: 'range-1',
        start_row: 4,
        end_row: 3,
        expected_value: 'skip',
      },
    ]

    expect(
      validateWorkbenchRuleForm({
        form,
        selectedRuleVariable: null,
        selectedReferenceVariable: null,
        shouldShowTopTargetVariable: false,
        isSingleRuleEntry: false,
        isCompositeRuleEntry: true,
        isDualCompositeRule: false,
        isSameDualCompositeVariable: false,
        referenceVariableOptions: [],
        compositeFieldOptions: [],
        referenceCompositeFieldOptions: [],
        compositeConfig: { global_filters: [], branches: [] },
        dualComparisons: [],
        dualLeftFilters: [],
        dualRightFilters: [],
        pipelineConfig: { nodes: [] },
        mappingConfig,
        variableMap,
      }),
    ).toMatchObject({
      valid: false,
      message: '映射节点 1 的筛选条件 1 的第 1 段排除范围：起始行号不能大于结束行号。',
    })
  })
})
