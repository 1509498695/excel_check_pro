// @vitest-environment happy-dom

import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessage } from 'element-plus'

import PackageItemsRuleDialog, {
  type PackageItemsFeishuAuthorizationState,
  type PackageItemsRuleDialogDraft,
  type PackageItemsRuleDialogPreview,
} from '../../src/components/fixed-rules/PackageItemsRuleDialog.vue'
import type { FixedRuleGroup } from '../../src/types/fixedRules'
import type { DataSource, SourceMetadata, VariableTag } from '../../src/types/workbench'

vi.mock('element-plus', () => ({
  ElMessage: {
    warning: vi.fn(),
    info: vi.fn(),
  },
}))

const ElementButtonStub = {
  template: '<button type="button" v-bind="$attrs"><slot /></button>',
}

const ElementPaginationStub = {
  props: ['currentPage'],
  emits: ['current-change'],
  template: `
    <nav data-testid="preview-pagination">
      <button type="button" data-testid="preview-prev" @click="$emit('current-change', currentPage - 1)">上一页</button>
      <span>第{{ currentPage }}页</span>
      <button type="button" data-testid="preview-next" @click="$emit('current-change', currentPage + 1)">下一页</button>
    </nav>
  `,
}

const globalStubs = {
  'el-dialog': {
    props: ['modelValue', 'title'],
    template: '<section v-if="modelValue"><h2>{{ title }}</h2><slot /><footer><slot name="footer" /></footer></section>',
  },
  'el-select': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div class="select-stub"><slot /></div>',
  },
  'el-option': {
    props: ['label', 'value'],
    template: '<div class="option-stub" :data-value="value">{{ label }}</div>',
  },
  'el-input': {
    props: ['modelValue', 'placeholder', 'type'],
    emits: ['update:modelValue'],
    template: `
      <textarea
        v-if="type === 'textarea'"
        :value="modelValue"
        :placeholder="placeholder"
        @input="$emit('update:modelValue', $event.target.value)"
      />
      <input
        v-else
        :value="modelValue"
        :placeholder="placeholder"
        @input="$emit('update:modelValue', $event.target.value)"
      />
    `,
  },
  'el-button': ElementButtonStub,
  'el-pagination': ElementPaginationStub,
  'el-switch': {
    props: ['modelValue'],
    template: '<button type="button">启用开关</button>',
  },
  'el-segmented': {
    props: ['options', 'modelValue'],
    emits: ['update:modelValue'],
    template: `
      <div>
        <button
          v-for="option in options"
          :key="option.value"
          type="button"
          @click="$emit('update:modelValue', option.value)"
        >
          {{ option.label }}
        </button>
      </div>
    `,
  },
  'el-radio-group': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    provide() {
      return {
        updateRadioGroup: (value: string) => this.$emit('update:modelValue', value),
      }
    },
    template: '<div><slot /></div>',
  },
  'el-radio-button': {
    props: ['label'],
    inject: ['updateRadioGroup'],
    template: '<button type="button" @click="updateRadioGroup(label)"><slot />{{ label }}</button>',
  },
  'el-radio': {
    props: ['label'],
    inject: ['updateRadioGroup'],
    template: '<button type="button" @click="updateRadioGroup(label)"><slot />{{ label }}</button>',
  },
}

const groups: FixedRuleGroup[] = [
  { group_id: 'ungrouped', group_name: '未分组', builtin: true },
]

const feishuSources: DataSource[] = [
  {
    id: 'feishu-plan',
    type: 'feishu',
    pathOrUrl: 'https://demo.feishu.cn/sheets/shtcnabc123',
  },
]

const sourceMetadataMap: Record<string, SourceMetadata> = {
  'feishu-plan': {
    source_id: 'feishu-plan',
    source_type: 'feishu',
    sheets: [{ name: '礼包规划', sheet_id: 'gid_plan', columns: ['礼包id', '道具ID', '个数'] }],
  },
}

const detailVariables: VariableTag[] = [
  {
    tag: '[package-detail]',
    source_id: 'feishu-plan',
    sheet: '礼包规划',
    variable_kind: 'composite',
    columns: ['礼包id', '道具ID', '个数'],
    key_column: '礼包id',
  },
  {
    tag: '[other-package-detail]',
    source_id: 'other-feishu',
    sheet: '其他礼包规划',
    variable_kind: 'composite',
    columns: ['礼包id', '道具ID', '个数'],
    key_column: '礼包id',
  },
]

const compositeVariables: VariableTag[] = [
  {
    tag: '[package-config]',
    source_id: 'config-src',
    sheet: 'package_config',
    variable_kind: 'composite',
    columns: ['INT_PackageId', 'STR_Items'],
    key_column: 'INT_PackageId',
  },
]

function baseDraft(
  overrides: Partial<PackageItemsRuleDialogDraft> = {},
): Partial<PackageItemsRuleDialogDraft> {
  return {
    group_id: 'ungrouped',
    rule_name: '礼包道具配置校验',
    feishu_source_id: 'feishu-plan',
    feishu_sheet_id: 'gid_plan',
    feishu_sheet_name: '礼包规划',
    detail_variable_tag: '[package-detail]',
    config_variable_tag: '[package-config]',
    parse_strategy: 'auto',
    ai_parse_mode: 'auto',
    validation_scope: 'all',
    package_id_filter: '',
    ...overrides,
  }
}

function mountDialog(options: {
  draft?: Partial<PackageItemsRuleDialogDraft>
  preview?: PackageItemsRuleDialogPreview
  previewing?: boolean
  sourceMetadataMap?: Record<string, SourceMetadata>
  feishuAuthorizationMap?: Record<string, PackageItemsFeishuAuthorizationState>
  refreshingSheets?: boolean
  backendReady?: boolean
} = {}) {
  return mount(PackageItemsRuleDialog, {
    props: {
      visible: true,
      mode: 'create',
      draft: options.draft ?? baseDraft(),
      groups,
      feishuSources,
      sourceMetadataMap: options.sourceMetadataMap ?? sourceMetadataMap,
      feishuAuthorizationMap: options.feishuAuthorizationMap ?? {},
      detailVariables,
      compositeVariables,
      preview: options.preview ?? { status: 'idle' },
      previewing: options.previewing ?? false,
      refreshingSheets: options.refreshingSheets ?? false,
      backendReady: options.backendReady ?? true,
    },
    global: {
      stubs: globalStubs,
    },
  })
}

describe('PackageItemsRuleDialog', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.mocked(ElMessage.warning).mockClear()
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('renders package rule fields and keeps parser options focused', () => {
    const wrapper = mountDialog()
    const text = wrapper.text()

    expect(text).toContain('新增礼包校验规则')
    expect(text).toContain('基本信息')
    expect(text).toContain('规则归属、命名与启用状态')
    expect(text).toContain('启用状态')
    expect(text).toContain('礼包规划数据源（飞书）')
    expect(text).toContain('飞书数据源')
    expect(text).toContain('Sheet 页')
    expect(text).toContain('授权状态')
    expect(text).toContain('已授权')
    expect(text).toContain('刷新 Sheet 列表')
    expect(text).toContain('文档地址')
    expect(text).toContain('https://demo.feishu.cn/sheets/shtcnabc123')
    expect(text).toContain('feishu-plan')
    expect(text).toContain('礼包规划')
    expect(text).not.toContain('礼包明细组合变量')
    expect(text).not.toContain('当前 Sheet')
    expect(text).not.toContain('[package-detail]')
    expect(text).not.toContain('[other-package-detail]')
    expect(text).not.toContain('feishu-plan · 礼包规划 · 礼包id / 道具ID / 个数')
    expect(text).toContain('礼包配置组合变量')
    expect(text).toContain('组合变量')
    expect(text).toContain('[package-config] · package_config · INT_PackageId / STR_Items')
    expect(text).toContain('解析方式')
    expect(text).toContain('自动识别（规则优先，AI 辅助）')
    expect(text).toContain('仅规则解析')
    expect(text).toContain('仅 AI 解析')
    expect(text).toContain('AI 辅助解析')
    expect(text).toContain('自动')
    expect(text).toContain('开启')
    expect(text).toContain('关闭')
    expect(text).toContain('全部礼包')
    expect(text).toContain('指定礼包 ID')
    expect(text).toContain('解析预览')
    expect(text).toContain('尚未生成当前配置的解析预览。')
    expect(text).toContain('规则说明')
    expect(wrapper.find('textarea').element.value).toBe('登峰礼包规划表与项目礼包配置表一致性校验规则')
    expect(text).toContain('22 / 500')
    expect(text).toContain('取消')
    expect(text).toContain('保存规则')
    expect(wrapper.find('input[placeholder="例如：登峰礼包规划 vs 礼包配置校验"]').exists()).toBe(true)
    expect(text).not.toContain('模型')
    expect(text).not.toContain('超时')
    expect(text).not.toContain('最大行数')
    expect(text).not.toContain('用户确认')
  })

  it('emits preview payload when clicking generate preview', async () => {
    const wrapper = mountDialog()

    await wrapper.findAll('button').find((button) => button.text().includes('生成预览'))?.trigger('click')

    expect(wrapper.emitted('preview')?.[0][0]).toMatchObject({
      feishu_source_id: 'feishu-plan',
      feishu_sheet_id: 'gid_plan',
      feishu_sheet_name: '礼包规划',
      parse_strategy: 'auto',
      ai_parse_mode: 'auto',
      validation_scope: 'all',
      package_id_filter: '',
    })
  })

  it('shows loading, compact preview summary, warnings and errors', () => {
    const loadingWrapper = mountDialog({ previewing: true })
    expect(loadingWrapper.text()).toContain('正在解析飞书礼包规划表')

    const wrapper = mountDialog({
      preview: {
        status: 'success',
        parseStatus: 'success',
        sourceId: 'feishu-plan',
        sheetId: 'gid_plan',
        parseStrategy: 'auto',
        aiParseMode: 'auto',
        validationScope: 'all',
        packageIdFilter: '',
        parseMode: 'ai',
        aiUsed: true,
        confidence: 0.92,
        packageIds: ['26042411', '26042412'],
        detailRowCount: 3,
        warnings: ['识别到非标准表头'],
        errors: ['演示错误'],
        fieldMapping: {
          package_id_column: '礼包',
          item_id_column: '道具',
          count_column: '数量',
          header_row_index: 1,
          detail_start_row_index: 2,
          detail_end_row_index: 4,
        },
        previewRows: [
          { row_index: 2, package_id: '26042411', item_id: '39', count: '8' },
          { row_index: 3, package_id: '26042412', item_id: '48', count: '25' },
        ],
      },
    })
    const text = wrapper.text()

    expect(text).toContain('识别到礼包 ID（预览）：26042411、26042412')
    expect(text).toContain('识别到明细行数：3 行')
    expect(text).not.toContain('置信度')
    expect(text).not.toContain('是否使用 AI')
    expect(text).not.toContain('礼包 ID 列：礼包')
    expect(text).not.toContain('道具 ID 列：道具')
    expect(text).not.toContain('明细范围：2-4 行')
    expect(text).not.toContain('行号')
    expect(text).not.toContain('当前结果由 AI 辅助识别结构后，系统按识别区域重新抽取数据。')
    expect(text).toContain('识别到非标准表头')
    expect(text).toContain('演示错误')
  })

  it('paginates preview rows with five rows per page', async () => {
    const previewRows = Array.from({ length: 6 }, (_, index) => ({
      row_index: index + 2,
      package_id: `2604241${index + 1}`,
      item_id: String(39 + index),
      count: String(index + 1),
    }))
    const wrapper = mountDialog({
      preview: {
        status: 'success',
        parseStatus: 'success',
        sourceId: 'feishu-plan',
        sheetId: 'gid_plan',
        parseStrategy: 'auto',
        aiParseMode: 'auto',
        validationScope: 'all',
        packageIdFilter: '',
        parseMode: 'rule',
        aiUsed: false,
        packageIds: previewRows.map((row) => row.package_id),
        detailRowCount: previewRows.length,
        warnings: [],
        errors: [],
        previewRows,
      },
    })

    expect(wrapper.text()).toContain('第2行 / 礼包 26042411 / 道具 39 x 1')
    expect(wrapper.text()).toContain('第6行 / 礼包 26042415 / 道具 43 x 5')
    expect(wrapper.text()).not.toContain('第7行 / 礼包 26042416 / 道具 44 x 6')

    await wrapper.get('[data-testid="preview-next"]').trigger('click')

    expect(wrapper.text()).toContain('第7行 / 礼包 26042416 / 道具 44 x 6')
    expect(wrapper.text()).not.toContain('第2行 / 礼包 26042411 / 道具 39 x 1')
  })

  it('shows preview error and validates save payload', async () => {
    const failedWrapper = mountDialog({
      preview: {
        status: 'success',
        parseStatus: 'failed',
        sourceId: 'feishu-plan',
        sheetId: 'gid_plan',
        parseStrategy: 'auto',
        aiParseMode: 'auto',
        validationScope: 'all',
        packageIdFilter: '',
        errorMessage: '未识别到表头',
        errors: ['未识别到表头'],
      },
    })
    expect(failedWrapper.text()).toContain('未识别到表头')

    const invalidWrapper = mountDialog({ draft: baseDraft({ rule_name: '' }) })
    await invalidWrapper.findAll('button').find((button) => button.text().includes('保存规则'))?.trigger('click')

    expect(ElMessage.warning).toHaveBeenCalledWith('规则名称不能为空。')
    expect(invalidWrapper.emitted('save')).toBeUndefined()

    const validWrapper = mountDialog({
      draft: baseDraft({
        detail_variable_tag: '',
        validation_scope: 'specified',
        package_id_filter: '26042411,26042412',
      }),
    })
    expect(validWrapper.find('input[placeholder="请输入礼包 ID，多个用英文逗号分隔"]').exists()).toBe(true)

    await validWrapper.findAll('button').find((button) => button.text().includes('保存规则'))?.trigger('click')

    expect(validWrapper.emitted('save')?.[0][0]).toMatchObject({
      rule_name: '礼包道具配置校验',
      parse_strategy: 'auto',
      ai_parse_mode: 'auto',
      validation_scope: 'specified',
      package_id_filter: '26042411, 26042412',
      detail_variable_tag: '',
    })
    expect(validWrapper.emitted('save')?.[0][0]).not.toHaveProperty('enabled')
    expect(validWrapper.emitted('save')?.[0][0]).not.toHaveProperty('ruleDescription')

    const allWrapper = mountDialog({
      draft: baseDraft({ validation_scope: 'all', package_id_filter: '26042411' }),
    })
    await allWrapper.findAll('button').find((button) => button.text().includes('保存规则'))?.trigger('click')
    expect(allWrapper.emitted('save')?.[0][0]).toMatchObject({
      validation_scope: 'all',
      package_id_filter: '',
    })
  })

  it('switches between all packages and specified package id mode', async () => {
    const wrapper = mountDialog()

    await wrapper.findAll('button').find((button) => button.text().includes('指定礼包 ID'))?.trigger('click')
    await wrapper.find('input[placeholder="请输入礼包 ID，多个用英文逗号分隔"]').setValue('26042411，26042412')
    await wrapper.findAll('button').find((button) => button.text().includes('保存规则'))?.trigger('click')

    expect(wrapper.emitted('save')?.[0][0]).toMatchObject({
      validation_scope: 'specified',
      package_id_filter: '26042411, 26042412',
    })

    await wrapper.findAll('button').find((button) => button.text().includes('全部礼包'))?.trigger('click')
    await wrapper.findAll('button').find((button) => button.text().includes('保存规则'))?.trigger('click')

    expect(wrapper.emitted('save')?.[1][0]).toMatchObject({
      validation_scope: 'all',
      package_id_filter: '',
    })
  })

  it('requests Feishu sheet metadata and allows manual sheet refresh without package backend', async () => {
    const wrapper = mountDialog({
      sourceMetadataMap: {},
      backendReady: false,
    })

    expect(wrapper.emitted('refresh-sheets')?.[0]).toEqual(['feishu-plan', false])

    await wrapper.findAll('button').find((button) => button.text().includes('刷新 Sheet 列表'))?.trigger('click')

    expect(wrapper.emitted('refresh-sheets')?.at(-1)).toEqual(['feishu-plan', true])
    expect(ElMessage.info).not.toHaveBeenCalledWith('当前环境未启用 IAP礼包校验能力，无法刷新 Sheet 列表。')
  })

  it('shows checking instead of unauthorized while Feishu sheet metadata is loading', () => {
    const wrapper = mountDialog({
      sourceMetadataMap: {},
      refreshingSheets: true,
    })

    expect(wrapper.text()).toContain('检测中')
    expect(wrapper.text()).not.toContain('未授权')
  })

  it('emits close when clicking cancel', async () => {
    const wrapper = mountDialog()

    await wrapper.findAll('button').find((button) => button.text().includes('取消'))?.trigger('click')

    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
