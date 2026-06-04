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

function mountContainer(
  options: {
    showPackageItemsRuleButton?: boolean
    showEventTaskRuleButton?: boolean
    canCreateRule?: boolean
  } = {},
) {
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
      showEventTaskRuleButton: options.showEventTaskRuleButton ?? false,
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
  it('renders dedicated package and event task buttons in the expected order', async () => {
    const wrapper = mountContainer({
      showPackageItemsRuleButton: true,
      showEventTaskRuleButton: true,
    })
    const buttons = wrapper.findAll('button')
    const packageButton = buttons.find((button) => button.text().includes('IAP礼包校验'))
    const eventTaskButton = buttons.find((button) => button.text().includes('节日任务校验'))
    const createButton = buttons.find((button) => button.text().includes('新增规则'))
    const buttonTexts = buttons.map((button) => button.text())

    expect(packageButton?.exists()).toBe(true)
    expect(eventTaskButton?.exists()).toBe(true)
    expect(createButton?.exists()).toBe(true)
    expect(buttonTexts.indexOf('IAP礼包校验')).toBeLessThan(buttonTexts.indexOf('节日任务校验'))
    expect(buttonTexts.indexOf('节日任务校验')).toBeLessThan(buttonTexts.indexOf('新增规则'))
    expect(wrapper.text()).toContain('IAP礼包校验')
    expect(wrapper.text()).toContain('节日任务校验')
    expect(wrapper.text()).not.toContain('普通规则')
    expect(wrapper.text()).not.toContain('礼包校验规则')

    await packageButton?.trigger('click')
    await eventTaskButton?.trigger('click')
    await createButton?.trigger('click')

    expect(wrapper.emitted('create-package-items-rule')).toHaveLength(1)
    expect(wrapper.emitted('create-event-task-rule')).toHaveLength(1)
    expect(wrapper.emitted('create-rule')).toHaveLength(1)
  })

  it('keeps dedicated rule buttons hidden for pages that do not opt in', () => {
    const wrapper = mountContainer()

    expect(wrapper.text()).not.toContain('IAP礼包校验')
    expect(wrapper.text()).not.toContain('节日任务校验')
    expect(wrapper.text()).toContain('新增规则')
  })
})
