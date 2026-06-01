// @vitest-environment happy-dom

import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import FixedRulesResultPanel from '../../src/components/fixed-rules/FixedRulesResultPanel.vue'
import { useFixedRulesStore } from '../../src/store/fixedRules'

const globalStubs = {
  'el-alert': {
    props: ['title', 'description', 'type'],
    template: '<div><strong>{{ title }}</strong><p>{{ description }}</p><slot name="title" /><slot /></div>',
  },
  'el-progress': true,
  'el-button': { template: '<button type="button"><slot /></button>' },
  'el-tag': { template: '<span><slot /></span>' },
  'el-table': { template: '<div><slot /></div>' },
  'el-table-column': true,
  CircleCheckFilled: true,
}

function mountPanel() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useFixedRulesStore()
  const wrapper = mount(FixedRulesResultPanel, {
    global: {
      plugins: [pinia],
      stubs: globalStubs,
    },
  })
  return { wrapper, store }
}

describe('FixedRulesResultPanel package items summary', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders package parse metadata without hiding normal result summary', async () => {
    const { wrapper, store } = mountPanel()
    store.config.rules = [
      {
        rule_id: 'rule-package',
        group_id: 'ungrouped',
        rule_name: '礼包校验',
        target_variable_tag: '[package-detail]',
        reference_variable_tag: '[package-config]',
        rule_type: 'package_items_compare',
      },
    ]
    store.executionMeta = {
      execution_time_ms: 12,
      total_rows_scanned: 10,
      failed_sources: [],
      package_items_parse: [
        {
          rule_id: 'rule-package',
          parse_mode: 'ai',
          ai_used: true,
          cache_hit: true,
          confidence: 0.92,
          header_rows: [3],
          package_ids: ['26042411', '26042412'],
          detail_row_count: 4,
          warnings: ['识别到非标准表头'],
          errors: ['演示错误'],
        },
      ],
    }

    await wrapper.vm.$nextTick()
    const text = wrapper.text()

    expect(text).toContain('礼包规划解析概览')
    expect(text).toContain('rule-package')
    expect(text).toContain('AI 辅助解析')
    expect(text).toContain('置信度 0.92')
    expect(text).toContain('AI 参与 是')
    expect(text).toContain('明细 4 行')
    expect(text).toContain('礼包 26042411、26042412')
    expect(text).toContain('识别到非标准表头')
    expect(text).toContain('演示错误')
    expect(text).toContain('异常结果明细')
  })

  it('does not render package parse block for ordinary rule results', async () => {
    const { wrapper, store } = mountPanel()
    store.config.rules = [
      {
        rule_id: 'rule-normal',
        group_id: 'ungrouped',
        rule_name: '普通规则',
        target_variable_tag: '[items-id]',
        rule_type: 'not_null',
      },
    ]
    store.executionMeta = {
      execution_time_ms: 8,
      total_rows_scanned: 2,
      failed_sources: [],
    }

    await wrapper.vm.$nextTick()
    const text = wrapper.text()

    expect(text).not.toContain('礼包规划解析概览')
    expect(text).toContain('异常结果明细')
    expect(text).toContain('项目校验结果总览')
  })
})
