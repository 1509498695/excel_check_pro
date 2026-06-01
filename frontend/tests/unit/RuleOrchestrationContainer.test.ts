// @vitest-environment happy-dom

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import RuleOrchestrationContainer from '../../src/features/rule-orchestration/components/RuleOrchestrationContainer.vue'
import type { FixedRuleGroup } from '../../src/types/fixedRules'

const groups: FixedRuleGroup[] = [
  { group_id: 'ungrouped', group_name: '未分组', builtin: true },
]

const globalStubs = {
  RuleGroupList: {
    template: '<aside>规则组</aside>',
  },
  DataTable: {
    template: '<table><thead><slot name="head" /></thead><tbody><slot name="body" /></tbody></table>',
  },
  EmptyState: {
    props: ['title', 'description'],
    template: '<div>{{ title }}{{ description }}</div>',
  },
  RuleCard: true,
  'el-checkbox': true,
  'el-pagination': true,
  Plus: true,
}

function mountContainer(options: { showPackageItemsRuleButton?: boolean; canCreateRule?: boolean } = {}) {
  return mount(RuleOrchestrationContainer, {
    props: {
      groups,
      selectedGroupId: 'ungrouped',
      selectedGroupName: '未分组',
      selectedGroupBuiltin: true,
      keyword: '',
      counts: {},
      invalidGroupIds: [],
      invalidRuleIds: [],
      selectedRuleIds: [],
      canCreateRule: options.canCreateRule ?? true,
      currentGroupRules: [],
      pagedRules: [],
      currentGroupRuleTotal: 0,
      currentPage: 1,
      currentGroupCount: 0,
      currentGroupVariableCount: 2,
      tableLabel: '项目校验规则列表',
      showPackageItemsRuleButton: options.showPackageItemsRuleButton ?? false,
      buildRuleCondition: () => '',
      buildRuleVariableSummary: () => '',
      buildRuleSourcePathSummary: () => '',
      buildRuleSelectionSummary: () => '',
      buildRuleCompareValueSummary: () => '',
    },
    global: {
      stubs: globalStubs,
    },
  })
}

describe('RuleOrchestrationContainer package items entry', () => {
  it('renders an independent package button and emits separate create events', async () => {
    const wrapper = mountContainer({ showPackageItemsRuleButton: true })
    const buttons = wrapper.findAll('button')
    const packageButton = buttons.find((button) => button.text().includes('IAP礼包校验'))
    const createButton = buttons.find((button) => button.text().includes('新增规则'))

    expect(packageButton?.exists()).toBe(true)
    expect(createButton?.exists()).toBe(true)
    expect(wrapper.text()).toContain('IAP礼包校验')
    expect(wrapper.text()).not.toContain('普通规则')
    expect(wrapper.text()).not.toContain('礼包校验规则')

    await packageButton?.trigger('click')
    await createButton?.trigger('click')

    expect(wrapper.emitted('create-package-items-rule')).toHaveLength(1)
    expect(wrapper.emitted('create-rule')).toHaveLength(1)
  })

  it('keeps the package button hidden for pages that do not opt in', () => {
    const wrapper = mountContainer()

    expect(wrapper.text()).not.toContain('IAP礼包校验')
    expect(wrapper.text()).toContain('新增规则')
  })
})
