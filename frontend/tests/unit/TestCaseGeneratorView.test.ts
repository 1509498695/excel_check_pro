// @vitest-environment happy-dom

import { mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

import TestCaseGeneratorView from '../../src/views/TestCaseGeneratorView.vue'

const globalStubs = {
  DataSourcePanel: {
    props: ['store'],
    emits: ['saved'],
    template: `
      <div class="data-source-panel-stub">
        <div v-for="source in store.sources" :key="source.id" class="source-row">{{ source.id }}</div>
        <button
          type="button"
          @click="
            store.upsertSource({ id: 'new_plan', type: 'local_excel', pathOrUrl: 'D:/plan/new-plan.xlsx' });
            store.sourceMetadataMap.new_plan = {
              source_id: 'new_plan',
              source_type: 'local_excel',
              sheets: [{ name: '新增Sheet', columns: ['模块', '需求点'] }]
            };
            $emit('saved', 'new_plan')
          "
        >
          模拟保存策划案来源
        </button>
      </div>
    `,
    setup(_props: unknown, { expose }: { expose: (exposed: { openCreateDialog: () => void }) => void }) {
      expose({ openCreateDialog: () => undefined })
    },
  },
  'el-dialog': {
    props: ['modelValue', 'title'],
    template: `
      <section v-if="modelValue" class="el-dialog-stub">
        <h2>{{ title }}</h2>
        <slot />
        <slot name="footer" />
      </section>
    `,
  },
  'el-icon': {
    template: '<i><slot /></i>',
  },
  'el-input': {
    props: ['modelValue'],
    template: '<div class="el-input-stub">{{ modelValue }}</div>',
  },
  'el-select': {
    props: ['modelValue', 'disabled'],
    emits: ['update:modelValue', 'change'],
    template: '<div class="el-select-stub" :data-disabled="disabled ? \'true\' : \'false\'"><slot /></div>',
  },
  'el-option': {
    props: ['label', 'value'],
    template: '<span class="el-option-stub" :data-value="value">{{ label }}</span>',
  },
  'el-tag': {
    template: '<span class="el-tag-stub"><slot /></span>',
  },
  'el-table': {
    props: ['data'],
    template: `
      <table>
        <tbody>
          <tr v-for="row in data" :key="row.id">
            <td>{{ row.id }}</td>
            <td>{{ row.module }}</td>
            <td>{{ row.checkpoint }}</td>
            <td>{{ row.title }}</td>
            <td>{{ row.priority }}</td>
            <td>{{ row.status }}</td>
            <td>{{ row.remarks }}</td>
          </tr>
        </tbody>
      </table>
    `,
  },
  'el-table-column': true,
}

function mountView(): VueWrapper {
  return mount(TestCaseGeneratorView, {
    global: {
      stubs: globalStubs,
    },
  })
}

function findButton(wrapper: VueWrapper | DOMWrapper<Element>, text: string) {
  return wrapper.findAll('button').find((button) => button.text().includes(text))
}

function findReferenceRow(wrapper: VueWrapper, referenceId: string): DOMWrapper<Element> {
  return wrapper.find(`[data-test="reference-file-row"][data-reference-id="${referenceId}"]`)
}

async function selectCategory(wrapper: VueWrapper, categoryName: string): Promise<void> {
  await findButton(wrapper, categoryName)?.trigger('click')
}

describe('TestCaseGeneratorView', () => {
  it('renders the static V1 test case generation workspace', () => {
    const wrapper = mountView()

    expect(wrapper.text()).toContain('用例生成')
    expect(wrapper.text()).toContain('策划案来源')
    expect(wrapper.text()).toContain('参考案例库')
    expect(wrapper.text()).toContain('生成设置')
    expect(wrapper.text()).toContain('项目 AI 已配置')
    expect(wrapper.text()).toContain('活动回归模板.xlsx')
    expect(wrapper.text()).toContain('参考用例数量')
    expect(wrapper.text()).toContain('约 120 条')
    expect(wrapper.text()).toContain('TC-001')
    expect(wrapper.text()).toContain('活动入口按配置开放')
    expect(wrapper.text()).toContain('本次结果仅保留在当前页面预览，不保存生成历史。')
  })

  it('renders the planning source data module and selector', () => {
    const wrapper = mountView()

    expect(wrapper.text()).toContain('01')
    expect(wrapper.text()).toContain('数据源')
    expect(wrapper.text()).toContain('新增策划案来源')
    expect(wrapper.text()).toContain('策划案来源')
    expect(wrapper.text()).toContain('plan_feishu')
    expect(wrapper.text()).toContain('活动策划案 / Sheet1')
    expect(wrapper.text()).toContain('奖励配置 / Sheet2')
  })

  it('adds a planning source through the embedded source panel store', async () => {
    const wrapper = mountView()

    await findButton(wrapper, '模拟保存策划案来源')?.trigger('click')

    expect(wrapper.text()).toContain('new_plan')
    expect(wrapper.text()).toContain('新增Sheet')
  })

  it('renders generation input and preview as full-width modules', () => {
    const wrapper = mountView()

    expect(wrapper.find('.tcg-content > [data-test="generation-input-module"]').exists()).toBe(true)
    expect(wrapper.find('.tcg-setup').exists()).toBe(false)
    expect(wrapper.find('.tcg-workspace').exists()).toBe(false)
    expect(wrapper.find('[data-test="generation-input-module"]').text()).toContain('策划案来源')
    expect(wrapper.find('[data-test="generation-input-module"]').text()).toContain('生成设置')
    expect(wrapper.find('.tcg-content > .tcg-preview').exists()).toBe(true)
  })

  it('keeps the preview module on the page scroll flow instead of clipping it internally', () => {
    const source = readFileSync('src/views/TestCaseGeneratorView.vue', 'utf-8')

    expect(source).not.toMatch(/\.tcg-preview\s*\{[^}]*max-height/s)
    expect(source).not.toMatch(/\.tcg-preview\s*\{[^}]*overflow:\s*hidden/s)
    expect(source).toMatch(/\.tcg-content\s*\{[^}]*overflow-y:\s*auto/s)
  })

  it('renders reference category pills with file counts', () => {
    const wrapper = mountView()

    const categoryPills = wrapper.findAll('[data-test="reference-category-pill"]').map((pill) => pill.text())

    expect(wrapper.find('.tcg-content > [data-test="reference-library"]').exists()).toBe(true)
    expect(wrapper.find('.tcg-setup [data-test="reference-library"]').exists()).toBe(false)
    expect(categoryPills).toEqual(expect.arrayContaining(['活动用例3', '礼包用例24', 'UI 通用2', '未分类1']))
  })

  it('clears selected references and primary reference when switching to a category without recommended primary', async () => {
    const wrapper = mountView()

    await selectCategory(wrapper, '礼包用例')

    const primarySelect = wrapper.find('[data-test="primary-reference-select"]')
    expect(primarySelect.attributes('data-disabled')).toBe('true')
    expect(primarySelect.text()).toContain('先在参考案例库选择参考案例')
    expect(wrapper.text()).toContain('当前分类未选择参考案例')
    expect(wrapper.text()).toContain('参考案例分类已切换，请先选择参考案例和主参考案例。')
  })

  it('selects the recommended primary reference by default when switching to a category that has one', async () => {
    const wrapper = mountView()

    await selectCategory(wrapper, '礼包用例')
    await selectCategory(wrapper, 'UI 通用')

    const uiPrimaryRow = findReferenceRow(wrapper, 'ui-common-checklist')
    const primarySelect = wrapper.find('[data-test="primary-reference-select"]')

    expect((uiPrimaryRow.find('[data-test="reference-checkbox"]').element as HTMLInputElement).checked).toBe(true)
    expect(uiPrimaryRow.classes()).toContain('is-primary')
    expect(primarySelect.attributes('data-disabled')).toBe('false')
    expect(primarySelect.text()).toContain('UI 通用冒烟.xlsx')
  })

  it('allows selecting multiple references within the same category', async () => {
    const wrapper = mountView()
    const markdownRow = findReferenceRow(wrapper, 'activity-boundary-md')
    const txtRow = findReferenceRow(wrapper, 'activity-ui-checklist')

    await markdownRow.find('[data-test="reference-checkbox"]').setValue(true)
    await txtRow.find('[data-test="reference-checkbox"]').setValue(true)

    expect((markdownRow.find('[data-test="reference-checkbox"]').element as HTMLInputElement).checked).toBe(true)
    expect((txtRow.find('[data-test="reference-checkbox"]').element as HTMLInputElement).checked).toBe(true)
    expect(wrapper.find('[data-test="primary-reference-select"]').text()).toContain('活动回归模板.xlsx')
    expect(wrapper.find('[data-test="primary-reference-select"]').text()).toContain('礼包活动边界.md')
    expect(wrapper.find('[data-test="primary-reference-select"]').text()).toContain('UI 通用检查.txt')
  })

  it('setting a file as primary reference automatically selects it', async () => {
    const wrapper = mountView()
    const txtRow = findReferenceRow(wrapper, 'activity-ui-checklist')

    await findButton(txtRow, '设为主参考')?.trigger('click')

    expect((txtRow.find('[data-test="reference-checkbox"]').element as HTMLInputElement).checked).toBe(true)
    expect(txtRow.classes()).toContain('is-primary')
    expect(wrapper.find('[data-test="primary-reference-select"]').text()).toContain('UI 通用检查.txt')
    expect(wrapper.text()).toContain('主参考案例已切换，需要重新生成。')
  })

  it('only lists selected references in the primary reference select', async () => {
    const wrapper = mountView()

    expect(wrapper.find('[data-test="primary-reference-select"]').text()).toContain('活动回归模板.xlsx')
    expect(wrapper.find('[data-test="primary-reference-select"]').text()).not.toContain('礼包活动边界.md')

    await findReferenceRow(wrapper, 'activity-boundary-md').find('[data-test="reference-checkbox"]').setValue(true)

    expect(wrapper.find('[data-test="primary-reference-select"]').text()).toContain('活动回归模板.xlsx')
    expect(wrapper.find('[data-test="primary-reference-select"]').text()).toContain('礼包活动边界.md')
    expect(wrapper.find('[data-test="primary-reference-select"]').text()).not.toContain('UI 通用检查.txt')
  })

  it('shows sheet options for Excel primary reference and disables sheet selection for Markdown/TXT', async () => {
    const wrapper = mountView()

    expect(wrapper.find('[data-test="primary-reference-sheet-select"]').attributes('data-disabled')).toBe('false')
    expect(wrapper.text()).toContain('测试用例')
    expect(wrapper.text()).toContain('历史回归')

    await findButton(findReferenceRow(wrapper, 'activity-boundary-md'), '设为主参考')?.trigger('click')

    const sheetSelect = wrapper.find('[data-test="primary-reference-sheet-select"]')
    expect(sheetSelect.attributes('data-disabled')).toBe('true')
    expect(sheetSelect.text()).toContain('当前参考案例无 Sheet')
  })

  it('shows empty state when search has no reference matches', async () => {
    const wrapper = mountView()

    await wrapper.find('[data-test="reference-search"]').setValue('不存在的画像')

    expect(wrapper.text()).toContain('没有匹配的参考案例')
    expect(wrapper.text()).toContain('清空筛选')
  })

  it('paginates reference files in pages of five', async () => {
    const wrapper = mountView()

    await selectCategory(wrapper, '礼包用例')

    expect(wrapper.findAll('[data-test="reference-file-row"]')).toHaveLength(5)
    expect(wrapper.text()).toContain('第 1-5 条 / 共 24 条')
    expect(wrapper.findAll('[data-test="reference-page-number"]').map((button) => button.text())).toEqual([
      '1',
      '2',
      '3',
      '4',
      '5',
    ])

    await wrapper.find('[data-test="reference-page-next"]').trigger('click')

    expect(wrapper.findAll('[data-test="reference-file-row"]')).toHaveLength(5)
    expect(wrapper.text()).toContain('第 6-10 条 / 共 24 条')
  })
})
