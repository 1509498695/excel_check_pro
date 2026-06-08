// @vitest-environment happy-dom

import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessage } from 'element-plus'

import EventTaskRuleDialog, {
  type EventTaskFeishuAuthorizationState,
  type EventTaskRuleDialogDraft,
  type EventTaskRuleDialogPreview,
  type EventTaskRuleDialogValidation,
} from '../../src/components/fixed-rules/EventTaskRuleDialog.vue'
import type { EventTaskRewardValidationResult, FixedRuleGroup } from '../../src/types/fixedRules'
import type { DataSource, SourceMetadata, VariableTag } from '../../src/types/workbench'

vi.mock('element-plus', () => ({
  ElMessage: {
    warning: vi.fn(),
    info: vi.fn(),
    success: vi.fn(),
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
    template:
      '<section v-if="modelValue"><h2>{{ title }}</h2><slot /><footer><slot name="footer" /></footer></section>',
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
  'el-table': {
    props: ['data'],
    provide() {
      return {
        getTableRows: () => this.data ?? [],
      }
    },
    template: '<div class="table-stub"><slot /></div>',
  },
  'el-table-column': {
    inject: ['getTableRows'],
    computed: {
      rows() {
        return this.getTableRows()
      },
    },
    template:
      '<div class="table-column-stub"><div v-for="(row, index) in rows" :key="index"><slot :row="row" /></div></div>',
  },
  'el-switch': {
    props: ['modelValue'],
    template: '<button type="button">启用开关</button>',
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
  'el-radio': {
    props: ['label'],
    inject: ['updateRadioGroup'],
    template: '<button type="button" @click="updateRadioGroup(label)"><slot />{{ label }}</button>',
  },
}

const groups: FixedRuleGroup[] = [
  { group_id: 'ungrouped', group_name: '未分组', builtin: true },
  { group_id: 'activity-validation', group_name: '活动校验', builtin: false },
]

const feishuSources: DataSource[] = [
  {
    id: 'feishu-real',
    type: 'feishu',
    pathOrUrl: 'https://demo.feishu.cn/sheets/event-task-real',
  },
]

const sourceMetadataMap: Record<string, SourceMetadata> = {
  'feishu-real': {
    source_id: 'feishu-real',
    source_type: 'feishu',
    authorization_status: 'authorized',
    sheets: [
      {
        name: 'EventTask_SourceSheet',
        sheet_id: 'sheet_event_july',
        columns: ['INT_ID', 'STR_Desc', 'STR_Loot'],
      },
    ],
  },
}

const feishuAuthorizationMap: Record<string, EventTaskFeishuAuthorizationState> = {
  'feishu-real': { status: 'authorized', message: '已授权' },
}

const compositeVariables: VariableTag[] = [
  {
    tag: '[event-task-real]',
    source_id: 'config-src',
    sheet: 'EventTask',
    variable_kind: 'composite',
    columns: ['INT_ID', 'STR_Desc', 'STR_Loot'],
    key_column: 'INT_ID',
  },
]

function baseDraft(
  overrides: Partial<EventTaskRuleDialogDraft> = {},
): Partial<EventTaskRuleDialogDraft> {
  return {
    enabled: true,
    parse_strategy: 'group_desc',
    ai_parse_mode: 'auto',
    ai_assist_mode: 'auto',
    match_strategy: 'groupId_desc_then_taskId',
    validation_scope: 'all',
    task_group_id_filter: '',
    key_delimiter: '_',
    fallback_match_field: 'INT_TaskID',
    ...overrides,
  }
}

function mountDialog(
  options: {
    draft?: Partial<EventTaskRuleDialogDraft>
    preview?: EventTaskRuleDialogPreview
    validation?: EventTaskRuleDialogValidation
    previewing?: boolean
    aiSuggesting?: boolean
    sourceMetadataMap?: Record<string, SourceMetadata>
    feishuAuthorizationMap?: Record<string, EventTaskFeishuAuthorizationState>
    backendReady?: boolean
  } = {},
) {
  return mount(EventTaskRuleDialog, {
    props: {
      visible: true,
      mode: 'create',
      draft: options.draft ?? baseDraft(),
      groups,
      feishuSources,
      sourceMetadataMap: options.sourceMetadataMap ?? sourceMetadataMap,
      feishuAuthorizationMap: options.feishuAuthorizationMap ?? feishuAuthorizationMap,
      taskVariables: compositeVariables,
      compositeVariables,
      preview: options.preview ?? { status: 'idle' },
      validation: options.validation ?? { status: 'idle' },
      previewing: options.previewing ?? false,
      validating: false,
      aiSuggesting: options.aiSuggesting ?? false,
      saving: false,
      refreshingSheets: false,
      backendReady: options.backendReady ?? true,
    },
    global: {
      stubs: globalStubs,
    },
  })
}

function createValidationResult(
  overrides: Partial<EventTaskRewardValidationResult> = {},
): EventTaskRewardValidationResult {
  return {
    taskGroupId: '26051802',
    task_group_id: '26051802',
    taskDesc: '累计登陆1天',
    task_desc: '累计登陆1天',
    feishuRowIndex: 3,
    feishu_row_index: 3,
    variableKey: '26051802_0',
    variable_key: '26051802_0',
    variableTaskId: '1',
    variable_task_id: '1',
    matchStrategy: 'groupId_desc',
    match_strategy: 'groupId_desc',
    status: 'fail',
    expectedRewards: [{ type: 'item', item_id: 2087, itemId: 2087, count: 1 }],
    expected_rewards: [{ type: 'item', item_id: 2087, itemId: 2087, count: 1 }],
    actualRewards: [{ type: 'item', item_id: 2087, itemId: 2087, count: 2 }],
    actual_rewards: [{ type: 'item', item_id: 2087, itemId: 2087, count: 2 }],
    missingRewards: [],
    missing_rewards: [],
    extraRewards: [],
    extra_rewards: [],
    countMismatches: [
      {
        item_id: 2087,
        itemId: 2087,
        expected_count: 1,
        expectedCount: 1,
        actual_count: 2,
        actualCount: 2,
      },
    ],
    count_mismatches: [
      {
        item_id: 2087,
        itemId: 2087,
        expected_count: 1,
        expectedCount: 1,
        actual_count: 2,
        actualCount: 2,
      },
    ],
    duplicateWarnings: [],
    duplicate_warnings: [],
    parseWarnings: ['STR_Loot 为空。'],
    parse_warnings: ['STR_Loot 为空。'],
    errorMessage: '奖励不一致',
    error_message: '奖励不一致',
    ...overrides,
  }
}

function createValidation(
  results: EventTaskRewardValidationResult[],
  overrides: Partial<EventTaskRuleDialogValidation> = {},
): EventTaskRuleDialogValidation {
  return {
    status: 'success',
    sourceId: 'feishu-real',
    sheetId: 'sheet_event_july',
    configVariableTag: '[event-task-real]',
    matchStrategy: 'groupId_desc_then_taskId',
    validationScope: 'all',
    taskGroupIdFilter: '',
    warnings: [],
    errors: [],
    total: results.length,
    passCount: results.filter((row) => row.status === 'pass').length,
    failCount: results.filter((row) => row.status === 'fail').length,
    unmatchedCount: results.filter(
      (row) => row.errorMessage?.includes('未找到对应组合变量任务') || !row.variableKey,
    ).length,
    warningCount: results.filter(
      (row) => (row.duplicateWarnings?.length ?? 0) + (row.parseWarnings?.length ?? 0) > 0,
    ).length,
    results,
    extraVariableTasks: [],
    ...overrides,
  }
}

describe('EventTaskRuleDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(globalThis.navigator, 'clipboard', {
      value: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
      configurable: true,
    })
    Object.defineProperty(URL, 'createObjectURL', {
      value: vi.fn(() => 'blob:event-task-validation'),
      configurable: true,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      value: vi.fn(),
      configurable: true,
    })
    Object.defineProperty(HTMLAnchorElement.prototype, 'click', {
      value: vi.fn(),
      configurable: true,
    })
  })

  it('renders event task fields from current groups, sources, sheets, and variable pool', () => {
    const wrapper = mountDialog()
    const text = wrapper.text()
    const ruleNameInput = wrapper.find(
      'input[placeholder="例如：26年7月节日任务奖励 vs 配置表校验"]',
    )

    expect(text).toContain('新增节日任务校验规则')
    expect(text).toContain('基本信息')
    expect(text).toContain('规则归属、命名与启用状态')
    expect(text).toContain('未分组')
    expect(text).toContain('活动校验')
    expect(text).toContain('任务数据源（飞书）')
    expect(text).toContain('飞书数据源')
    expect(text).toContain('feishu-real')
    expect(text).toContain('Sheet 页')
    expect(text).toContain('EventTask_SourceSheet')
    expect(text).toContain('授权状态')
    expect(text).toContain('已授权')
    expect(text).toContain('文档地址')
    expect(text).toContain('https://demo.feishu.cn/sheets/event-task-real')
    expect(text).toContain('刷新 Sheet 列表')
    expect(text).toContain('任务配置组合变量')
    expect(text).toContain('[event-task-real] · EventTask · INT_ID / STR_Desc / STR_Loot')
    expect(text).toContain('EventTask · INT_ID / STR_Desc / STR_Loot')
    expect(text).toContain('匹配策略')
    expect(text).toContain('任务组ID + 描述，失败后按任务ID兜底')
    expect(text).toContain('任务组ID + INT_TaskID')
    expect(text).toContain('AI 辅助解析')
    expect(text).toContain('自动')
    expect(text).toContain('开启')
    expect(text).toContain('关闭')
    expect(text).toContain('key 分隔符：_')
    expect(text).toContain('任务组ID：取 key 前缀')
    expect(text).toContain('备用匹配：INT_TaskID')
    expect(text).toContain('校验范围')
    expect(text).toContain('全部任务')
    expect(text).toContain('指定任务组 ID')
    expect(text).toContain('解析预览')
    expect(text).toContain('生成预览')
    expect(text).toContain('尚未生成当前配置的解析预览。')
    expect(text).toContain('规则说明')
    expect(text).toContain('/ 500')
    expect(text).toContain('取消')
    expect(text).toContain('保存规则')
    expect(ruleNameInput.exists()).toBe(true)
    expect((ruleNameInput.element as HTMLInputElement).value).toBe('节日任务校验')
    expect(wrapper.find('textarea').element.value).toBe(
      '节日任务表与项目任务配置表一致性校验规则，校验任务组ID、任务描述及 STR_Loot 奖励内容是否一致。',
    )
  })

  it('emits a front-end refresh event without preview or backend behavior', async () => {
    const wrapper = mountDialog()

    await wrapper.findAll('button').find((button) => button.text().includes('刷新 Sheet 列表'))?.trigger('click')

    expect(wrapper.emitted('refresh-sheets')?.[0]).toEqual(['feishu-real', true])
    expect(wrapper.emitted('preview')).toBeUndefined()
  })

  it('emits preview payload when current Feishu sheet is authorized', async () => {
    const wrapper = mountDialog()

    await wrapper.findAll('button').find((button) => button.text().includes('生成预览'))?.trigger('click')

    expect(wrapper.emitted('preview')?.[0][0]).toMatchObject({
      feishu_source_id: 'feishu-real',
      feishu_sheet_id: 'sheet_event_july',
      feishu_sheet_name: 'EventTask_SourceSheet',
      config_variable_tag: '[event-task-real]',
      parse_strategy: 'group_desc',
      ai_parse_mode: 'auto',
      ai_assist_mode: 'auto',
      match_strategy: 'groupId_desc_then_taskId',
      validation_scope: 'all',
      task_group_id_filter: '',
      key_delimiter: '_',
      fallback_match_field: 'INT_TaskID',
    })
  })

  it('emits validation payload when current Feishu sheet is authorized', async () => {
    const wrapper = mountDialog()

    await wrapper.findAll('button').find((button) => button.text().includes('执行校验'))?.trigger('click')

    expect(wrapper.emitted('validate')?.[0][0]).toMatchObject({
      feishu_source_id: 'feishu-real',
      feishu_sheet_id: 'sheet_event_july',
      feishu_sheet_name: 'EventTask_SourceSheet',
      config_variable_tag: '[event-task-real]',
      parse_strategy: 'group_desc',
      ai_parse_mode: 'auto',
      ai_assist_mode: 'auto',
      match_strategy: 'groupId_desc_then_taskId',
      validation_scope: 'all',
      task_group_id_filter: '',
      key_delimiter: '_',
      fallback_match_field: 'INT_TaskID',
    })
  })

  it('renders validation summary and reward details from props', () => {
    const wrapper = mountDialog({
      validation: {
        status: 'success',
        sourceId: 'feishu-real',
        sheetId: 'sheet_event_july',
        configVariableTag: '[event-task-real]',
        matchStrategy: 'groupId_desc_then_taskId',
        validationScope: 'all',
        taskGroupIdFilter: '',
        total: 1,
        passCount: 0,
        failCount: 1,
        unmatchedCount: 0,
        warningCount: 1,
        warnings: ['第5行道具ID 39 不为空但数量为空。'],
        results: [
          {
            taskGroupId: '26051802',
            task_group_id: '26051802',
            taskDesc: '累计登陆1天',
            task_desc: '累计登陆1天',
            feishuRowIndex: 3,
            feishu_row_index: 3,
            variableKey: '26051802_0',
            variable_key: '26051802_0',
            variableTaskId: '1',
            variable_task_id: '1',
            matchStrategy: 'groupId_desc',
            match_strategy: 'groupId_desc',
            status: 'fail',
            expectedRewards: [{ type: 'item', item_id: 2087, itemId: 2087, count: 1 }],
            expected_rewards: [{ type: 'item', item_id: 2087, itemId: 2087, count: 1 }],
            actualRewards: [{ type: 'item', item_id: 2087, itemId: 2087, count: 2 }],
            actual_rewards: [{ type: 'item', item_id: 2087, itemId: 2087, count: 2 }],
            missingRewards: [],
            missing_rewards: [],
            extraRewards: [],
            extra_rewards: [],
            countMismatches: [
              {
                item_id: 2087,
                itemId: 2087,
                expected_count: 1,
                expectedCount: 1,
                actual_count: 2,
                actualCount: 2,
              },
            ],
            count_mismatches: [
              {
                item_id: 2087,
                itemId: 2087,
                expected_count: 1,
                expectedCount: 1,
                actual_count: 2,
                actualCount: 2,
              },
            ],
            duplicateWarnings: [],
            duplicate_warnings: [],
            parseWarnings: ['STR_Loot 为空。'],
            parse_warnings: ['STR_Loot 为空。'],
            errorMessage: '奖励不一致',
            error_message: '奖励不一致',
          },
        ],
        extraVariableTasks: [],
      },
    })

    const text = wrapper.text()

    expect(text).toContain('总任务数：1')
    expect(text).toContain('失败数：1')
    expect(text).toContain('未匹配数：0')
    expect(text).toContain('Warning 数：1')
    expect(text).toContain('数量不一致任务数：1')
    expect(text).toContain('第5行道具ID 39 不为空但数量为空。')
    expect(text).toContain('Expected：itemId=2087 count=1')
    expect(text).toContain('Actual：itemId=2087 count=2')
  })

  it('filters validation rows by status, warning, group id, and description keyword', async () => {
    const passRow = createValidationResult({
      taskGroupId: '26051802',
      task_group_id: '26051802',
      taskDesc: '累计登陆1天',
      task_desc: '累计登陆1天',
      status: 'pass',
      missingRewards: [],
      missing_rewards: [],
      extraRewards: [],
      extra_rewards: [],
      countMismatches: [],
      count_mismatches: [],
      duplicateWarnings: [],
      duplicate_warnings: [],
      parseWarnings: [],
      parse_warnings: [],
      errorMessage: null,
      error_message: null,
    })
    const failRow = createValidationResult({
      taskGroupId: '26051803',
      task_group_id: '26051803',
      taskDesc: '累计充值1天',
      task_desc: '累计充值1天',
      variableKey: '26051803_0',
      variable_key: '26051803_0',
      parseWarnings: [],
      parse_warnings: [],
    })
    const warningRow = createValidationResult({
      taskGroupId: '26051804',
      task_group_id: '26051804',
      taskDesc: '野外采集',
      task_desc: '野外采集',
      status: 'pass',
      countMismatches: [],
      count_mismatches: [],
      errorMessage: null,
      error_message: null,
      duplicateWarnings: ['重复奖励 itemId=39'],
      duplicate_warnings: ['重复奖励 itemId=39'],
      parseWarnings: [],
      parse_warnings: [],
    })
    const wrapper = mountDialog({
      validation: createValidation([passRow, failRow, warningRow]),
    })

    expect(wrapper.text()).toContain('累计登陆1天')
    expect(wrapper.text()).toContain('累计充值1天')
    expect(wrapper.text()).toContain('野外采集')

    await wrapper.findAll('button').find((button) => button.text().trim() === '只看失败fail')?.trigger('click')
    expect(wrapper.text()).not.toContain('累计登陆1天')
    expect(wrapper.text()).toContain('累计充值1天')
    expect(wrapper.text()).not.toContain('野外采集')

    await wrapper
      .findAll('button')
      .find((button) => button.text().trim() === '只看 warningwarning')
      ?.trigger('click')
    expect(wrapper.text()).not.toContain('累计登陆1天')
    expect(wrapper.text()).not.toContain('累计充值1天')
    expect(wrapper.text()).toContain('野外采集')

    await wrapper.findAll('button').find((button) => button.text().trim() === '全部all')?.trigger('click')
    await wrapper.find('input[placeholder="按任务组ID筛选"]').setValue('26051803')
    expect(wrapper.text()).not.toContain('累计登陆1天')
    expect(wrapper.text()).toContain('累计充值1天')
    expect(wrapper.text()).not.toContain('野外采集')

    await wrapper.find('input[placeholder="按任务组ID筛选"]').setValue('')
    await wrapper.find('input[placeholder="按任务描述关键词搜索"]').setValue('采集')
    expect(wrapper.text()).not.toContain('累计登陆1天')
    expect(wrapper.text()).not.toContain('累计充值1天')
    expect(wrapper.text()).toContain('野外采集')
  })

  it('shows an empty state when validation filters have no matches', async () => {
    const wrapper = mountDialog({
      validation: createValidation([createValidationResult()]),
    })

    await wrapper.find('input[placeholder="按任务组ID筛选"]').setValue('not-found')

    expect(wrapper.text()).toContain('暂无符合筛选条件的校验结果')
  })

  it('copies a single failed validation detail', async () => {
    const wrapper = mountDialog({
      validation: createValidation([
        createValidationResult({
          missingRewards: [{ type: 'item', item_id: 1502, itemId: 1502, count: 2 }],
          missing_rewards: [{ type: 'item', item_id: 1502, itemId: 1502, count: 2 }],
          extraRewards: [{ type: 'res', item_id: 16, itemId: 16, count: 200 }],
          extra_rewards: [{ type: 'res', item_id: 16, itemId: 16, count: 200 }],
        }),
      ]),
    })

    await wrapper.findAll('button').find((button) => button.text().includes('复制详情'))?.trigger('click')

    const writeText = vi.mocked(globalThis.navigator.clipboard.writeText)
    expect(writeText).toHaveBeenCalledTimes(1)
    expect(writeText.mock.calls[0][0]).toContain('任务组ID：26051802')
    expect(writeText.mock.calls[0][0]).toContain('组合变量缺少奖励 itemId=1502 count=2')
    expect(writeText.mock.calls[0][0]).toContain('多余配置：res id=16 count=200')
    expect(ElMessage.success).toHaveBeenCalledWith('已复制错误详情。')
  })

  it('exports all validation results as CSV', async () => {
    const wrapper = mountDialog({
      validation: createValidation([
        createValidationResult({
          taskDesc: '累计登陆1天',
          task_desc: '累计登陆1天',
        }),
        createValidationResult({
          taskGroupId: '26051803',
          task_group_id: '26051803',
          taskDesc: '累计充值1天',
          task_desc: '累计充值1天',
          status: 'pass',
          countMismatches: [],
          count_mismatches: [],
          parseWarnings: [],
          parse_warnings: [],
          errorMessage: null,
          error_message: null,
        }),
      ]),
    })

    await wrapper.findAll('button').find((button) => button.text().includes('导出全部'))?.trigger('click')

    const createObjectURL = vi.mocked(URL.createObjectURL)
    const blob = createObjectURL.mock.calls[0][0] as Blob
    const csv = await blob.text()
    expect(csv).toContain('累计登陆1天')
    expect(csv).toContain('累计充值1天')
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1)
    expect(ElMessage.success).toHaveBeenCalledWith('已导出全部校验结果。')
  })

  it('exports failed validation results only', async () => {
    const wrapper = mountDialog({
      validation: createValidation([
        createValidationResult({
          taskDesc: '失败任务',
          task_desc: '失败任务',
        }),
        createValidationResult({
          taskGroupId: '26051803',
          task_group_id: '26051803',
          taskDesc: '通过任务',
          task_desc: '通过任务',
          status: 'pass',
          countMismatches: [],
          count_mismatches: [],
          parseWarnings: [],
          parse_warnings: [],
          errorMessage: null,
          error_message: null,
        }),
      ]),
    })

    await wrapper.findAll('button').find((button) => button.text().includes('导出失败'))?.trigger('click')

    const createObjectURL = vi.mocked(URL.createObjectURL)
    const blob = createObjectURL.mock.calls[0][0] as Blob
    const csv = await blob.text()
    expect(csv).toContain('失败任务')
    expect(csv).not.toContain('通过任务')
    expect(ElMessage.success).toHaveBeenCalledWith('已导出失败校验结果。')
  })

  it('renders an empty validation result state', () => {
    const wrapper = mountDialog({
      validation: createValidation([]),
    })

    expect(wrapper.text()).toContain('暂无校验明细')
  })

  it('renders real preview summary, sample rows, and warnings from props', () => {
    const wrapper = mountDialog({
      preview: {
        status: 'success',
        parseStatus: 'success',
        sourceId: 'feishu-real',
        sheetId: 'sheet_event_july',
        parseStrategy: 'group_desc',
        aiParseMode: 'auto',
        validationScope: 'all',
        taskGroupIdFilter: '',
        taskGroupIds: ['26051802', '26051803'],
        totalRows: 36,
        parsedRows: 34,
        rewardGroupCount: 4,
        sampleRows: [
          {
            rowIndex: 3,
            taskGroupId: '26051802',
            taskId: null,
            day: 1,
            desc: '累计登陆1天',
            rawLoot: '{item,2087,1},{item,3,1}',
            rewards: [
              { type: 'item', item_id: 2087, itemId: 2087, count: 1, name: '金色箱子钥匙' },
              { type: 'item', item_id: 3, itemId: 3, count: 1, name: '黄金+150000' },
            ],
            warnings: [],
          },
        ],
        warnings: ['第5行道具ID 39 不为空但数量为空。'],
      },
    })

    const text = wrapper.text()

    expect(text).toContain('识别到任务组ID：26051802、26051803')
    expect(text).toContain('识别到任务明细数：34 行')
    expect(text).toContain('识别到奖励字段组：4 组')
    expect(text).toContain('第3行 / 26051802 / 累计登陆1天 / 奖励 2087x1（金色箱子钥匙）, 3x1（黄金+150000）')
    expect(text).toContain('Warning：第5行道具ID 39 不为空但数量为空。')
  })

  it('paginates preview rows with five rows per page', async () => {
    const previewRows = Array.from({ length: 6 }, (_, index) => ({
      row_index: index + 3,
      task_group_id: '26051802',
      task_desc: `累计登陆${index + 1}天`,
      task_id: String(index + 1),
      day: index + 1,
      loot: `{item,${2087 + index},${index + 1}}`,
      rewards: [
        {
          type: 'item',
          item_id: 2087 + index,
          itemId: 2087 + index,
          count: index + 1,
          name: `奖励${index + 1}`,
        },
      ],
      warnings: [],
    }))
    const wrapper = mountDialog({
      preview: {
        status: 'success',
        parseStatus: 'success',
        sourceId: 'feishu-real',
        sheetId: 'sheet_event_july',
        parseStrategy: 'group_desc',
        aiParseMode: 'auto',
        validationScope: 'all',
        taskGroupIdFilter: '',
        taskGroupIds: ['26051802'],
        totalRows: 8,
        parsedRows: 6,
        rewardGroupCount: 1,
        sampleRows: [],
        previewRows,
      },
    })

    expect(wrapper.text()).toContain('第3行 / 26051802 / 累计登陆1天 / 奖励 2087x1（奖励1）')
    expect(wrapper.text()).toContain('第7行 / 26051802 / 累计登陆5天 / 奖励 2091x5（奖励5）')
    expect(wrapper.text()).not.toContain('第8行 / 26051802 / 累计登陆6天 / 奖励 2092x6（奖励6）')

    await wrapper.get('[data-testid="preview-next"]').trigger('click')

    expect(wrapper.text()).toContain('第8行 / 26051802 / 累计登陆6天 / 奖励 2092x6（奖励6）')
    expect(wrapper.text()).not.toContain('第3行 / 26051802 / 累计登陆1天 / 奖励 2087x1（奖励1）')
  })

  it('does not emit preview when sheet is missing', async () => {
    const wrapper = mountDialog({
      draft: baseDraft({
        feishu_source_id: 'feishu-real',
        feishu_sheet_id: '',
      }),
      sourceMetadataMap: {
        'feishu-real': {
          ...sourceMetadataMap['feishu-real'],
          sheets: [],
        },
      },
    })

    await wrapper.findAll('button').find((button) => button.text().includes('生成预览'))?.trigger('click')

    expect(ElMessage.warning).toHaveBeenCalledWith('请选择任务 Sheet。')
    expect(wrapper.emitted('preview')).toBeUndefined()
  })

  it('does not emit preview before Feishu authorization', async () => {
    const wrapper = mountDialog({
      feishuAuthorizationMap: {
        'feishu-real': { status: 'pending_authorization', message: '机器人暂无该表格权限。' },
      },
    })

    await wrapper.findAll('button').find((button) => button.text().includes('生成预览'))?.trigger('click')

    expect(ElMessage.warning).toHaveBeenCalledWith('请先完成飞书授权。')
    expect(wrapper.emitted('preview')).toBeUndefined()
  })

  it('defaults to ungrouped and current source selections when saving', async () => {
    const wrapper = mountDialog()

    await wrapper.findAll('button').find((button) => button.text().includes('保存规则'))?.trigger('click')

    expect(wrapper.emitted('save')?.[0][0]).toMatchObject({
      group_id: 'ungrouped',
      rule_name: '节日任务校验',
      feishu_source_id: 'feishu-real',
      feishu_sheet_id: 'sheet_event_july',
      feishu_sheet_name: 'EventTask_SourceSheet',
      config_variable_tag: '[event-task-real]',
    })
  })

  it('validates required rule name before save after the user clears the default', async () => {
    const wrapper = mountDialog()

    await wrapper
      .find('input[placeholder="例如：26年7月节日任务奖励 vs 配置表校验"]')
      .setValue('')
    await wrapper.findAll('button').find((button) => button.text().includes('保存规则'))?.trigger('click')

    expect(ElMessage.warning).toHaveBeenCalledWith('规则名称不能为空。')
    expect(wrapper.emitted('save')).toBeUndefined()
  })

  it('switches to specified task group mode and emits normalized save payload', async () => {
    const wrapper = mountDialog()

    await wrapper.findAll('button').find((button) => button.text().includes('指定任务组 ID'))?.trigger('click')
    await wrapper.find('input[placeholder="请输入任务组ID，多个用英文逗号分隔"]').setValue('26051802，26051803')
    await wrapper.findAll('button').find((button) => button.text().includes('保存规则'))?.trigger('click')

    expect(wrapper.emitted('save')?.[0][0]).toMatchObject({
      group_id: 'ungrouped',
      rule_name: '节日任务校验',
      feishu_source_id: 'feishu-real',
      feishu_sheet_id: 'sheet_event_july',
      config_variable_tag: '[event-task-real]',
      parse_strategy: 'group_desc',
      ai_parse_mode: 'auto',
      ai_assist_mode: 'auto',
      match_strategy: 'groupId_desc_then_taskId',
      validation_scope: 'specified',
      task_group_id_filter: '26051802, 26051803',
      key_delimiter: '_',
      fallback_match_field: 'INT_TaskID',
    })
  })

  it('hides AI suggestion section when AI assist is off', () => {
    const wrapper = mountDialog({
      draft: baseDraft({ ai_assist_mode: 'off', ai_parse_mode: 'disabled' }),
    })

    expect(wrapper.text()).not.toContain('AI 建议，仅供参考')
  })

  it('shows backend AI suggestions in auto mode', () => {
    const wrapper = mountDialog({
      preview: {
        status: 'failed',
        parseStatus: 'failed',
        sourceId: 'feishu-real',
        sheetId: 'sheet_event_july',
        parseStrategy: 'group_desc',
        aiParseMode: 'auto',
        validationScope: 'all',
        taskGroupIdFilter: '',
        errors: ['任务表头缺少字段：task_group_id'],
        aiSuggestions: [
          {
            type: 'field_mapping_suggestion',
            confidence: 0.86,
            suggestions: [{ event_task_field_mapping: { header_row_index: 2, task_group_id: '活动ID' } }],
            reason: '识别到非标准活动ID表头。',
            requiresUserConfirm: true,
            requires_user_confirm: true,
          },
        ],
        aiSuggestionUsed: true,
      },
    })

    expect(wrapper.text()).toContain('AI 建议，仅供参考')
    expect(wrapper.text()).toContain('字段映射建议')
    expect(wrapper.text()).toContain('识别到非标准活动ID表头。')
    expect(wrapper.text()).toContain('AI 建议未参与最终校验结果。')
  })

  it('emits manual AI analysis request only in on mode', async () => {
    const wrapper = mountDialog({
      draft: baseDraft({ ai_assist_mode: 'on', ai_parse_mode: 'enabled' }),
    })

    await wrapper
      .findAll('button')
      .find((button) => button.text().includes('AI 分析当前结果'))
      ?.trigger('click')

    expect(wrapper.emitted('ai-analyze')?.[0][0]).toMatchObject({
      ai_assist_mode: 'on',
      ai_parse_mode: 'enabled',
      feishu_source_id: 'feishu-real',
      feishu_sheet_id: 'sheet_event_july',
    })
  })

  it('applies field mapping suggestion only after user confirmation and sends it in preview payload', async () => {
    const wrapper = mountDialog({
      preview: {
        status: 'failed',
        parseStatus: 'failed',
        sourceId: 'feishu-real',
        sheetId: 'sheet_event_july',
        parseStrategy: 'group_desc',
        aiParseMode: 'auto',
        validationScope: 'all',
        taskGroupIdFilter: '',
        errors: ['任务表头缺少字段：task_group_id'],
        aiSuggestions: [
          {
            type: 'field_mapping_suggestion',
            confidence: 0.9,
            suggestions: [
              {
                event_task_field_mapping: {
                  header_row_index: 2,
                  task_group_id: '活动ID',
                  task_id: '序号',
                  task_desc: '条件',
                  loot_groups: [{ item_id: '奖励ID', count: '奖励数量', name: '奖励名称' }],
                },
              },
            ],
            reason: '建议人工确认字段映射。',
            requiresUserConfirm: true,
            requires_user_confirm: true,
          },
        ],
      },
    })

    await wrapper
      .findAll('button')
      .find((button) => button.text().includes('应用字段映射建议'))
      ?.trigger('click')
    await wrapper.findAll('button').find((button) => button.text().includes('生成预览'))?.trigger('click')

    expect(ElMessage.success).toHaveBeenCalledWith('已应用字段映射建议，请重新生成预览或执行校验。')
    expect(wrapper.emitted('preview')?.[0][0]).toMatchObject({
      event_task_field_mapping: {
        header_row_index: 2,
        task_group_id: '活动ID',
        task_id: '序号',
        task_desc: '条件',
        loot_groups: [{ item_id: '奖励ID', count: '奖励数量', name: '奖励名称' }],
      },
    })
  })

  it('emits close when clicking cancel', async () => {
    const wrapper = mountDialog()

    await wrapper.findAll('button').find((button) => button.text().includes('取消'))?.trigger('click')

    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
