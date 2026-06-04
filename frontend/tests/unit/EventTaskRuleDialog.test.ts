// @vitest-environment happy-dom

import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessage } from 'element-plus'

import EventTaskRuleDialog, {
  type EventTaskFeishuAuthorizationState,
  type EventTaskRuleDialogDraft,
} from '../../src/components/fixed-rules/EventTaskRuleDialog.vue'
import type { FixedRuleGroup } from '../../src/types/fixedRules'
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
    validation_scope: 'all',
    task_group_id_filter: '',
    key_delimiter: '_',
    fallback_match_field: 'INT_TaskID',
    ...overrides,
  }
}

function mountDialog(options: { draft?: Partial<EventTaskRuleDialogDraft> } = {}) {
  return mount(EventTaskRuleDialog, {
    props: {
      visible: true,
      mode: 'create',
      draft: options.draft ?? baseDraft(),
      groups,
      feishuSources,
      sourceMetadataMap,
      feishuAuthorizationMap,
      taskVariables: compositeVariables,
      compositeVariables,
      saving: false,
      refreshingSheets: false,
    },
    global: {
      stubs: globalStubs,
    },
  })
}

describe('EventTaskRuleDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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
    expect(text).toContain('任务组ID + 任务描述双重匹配（推荐）')
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
    expect(text).toContain('识别到任务组 ID（预览）：26051802，26051803，26051804')
    expect(text).toContain('识别到任务明细数：34 行')
    expect(text).toContain('示例匹配：26051802_4476 → 任务组ID 26051802 / 任务描述 累计登陆1天')
    expect(text).toContain('规则说明')
    expect(text).toContain('/ 500')
    expect(text).toContain('取消')
    expect(text).toContain('保存规则')
    expect(text).not.toContain('生成预览')
    expect(text).not.toContain('尚未生成当前配置的解析预览')
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
      validation_scope: 'specified',
      task_group_id_filter: '26051802, 26051803',
      key_delimiter: '_',
      fallback_match_field: 'INT_TaskID',
    })
  })

  it('emits close when clicking cancel', async () => {
    const wrapper = mountDialog()

    await wrapper.findAll('button').find((button) => button.text().includes('取消'))?.trigger('click')

    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
