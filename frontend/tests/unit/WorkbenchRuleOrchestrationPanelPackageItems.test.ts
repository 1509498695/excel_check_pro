// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessage } from 'element-plus'

import { checkFeishuSourcePermission, previewWorkbenchPackageItems } from '../../src/api/workbench'
import WorkbenchRuleOrchestrationPanel from '../../src/components/workbench/WorkbenchRuleOrchestrationPanel.vue'
import { useWorkbenchStore } from '../../src/store/workbench'
import type { EventTaskRuleDialogDraft } from '../../src/components/fixed-rules/EventTaskRuleDialog.vue'
import type { PackageItemsRuleDialogDraft } from '../../src/components/fixed-rules/PackageItemsRuleDialog.vue'
import type { DataSource, SourceMetadata, VariableTag } from '../../src/types/workbench'

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
  ElMessageBox: {
    confirm: vi.fn(),
    prompt: vi.fn(),
  },
}))

vi.mock('../../src/api/workbench', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/api/workbench')>()
  return {
    ...actual,
    checkFeishuSourcePermission: vi.fn(),
    previewWorkbenchPackageItems: vi.fn(),
  }
})

const feishuSource: DataSource = {
  id: 'feishu-plan',
  type: 'feishu',
  pathOrUrl: 'https://demo.feishu.cn/sheets/shtcnabc123',
}

const feishuSourceMetadata: SourceMetadata = {
  source_id: 'feishu-plan',
  source_type: 'feishu',
  sheets: [{ name: '礼包规划', sheet_id: 'gid_plan', columns: [] }],
  authorization_status: 'authorized',
}

const configVariable: VariableTag = {
  tag: '[package-config]',
  source_id: 'config-src',
  sheet: 'package_config',
  variable_kind: 'composite',
  columns: ['INT_PackageId', 'STR_Items'],
  key_column: 'INT_PackageId',
}

const detailVariable: VariableTag = {
  tag: '[package-detail]',
  source_id: 'feishu-plan',
  sheet: '礼包规划',
  variable_kind: 'composite',
  columns: ['礼包id', '道具ID', '个数'],
  key_column: '礼包id',
}

function mountPanel() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useWorkbenchStore()
  store.sources = [feishuSource, { id: 'config-src', type: 'local_excel', path: 'D:/tmp/config.xlsx' }]
  store.variables = [detailVariable, configVariable]
  const saveSpy = vi.spyOn(store, 'saveConfigNow').mockResolvedValue(undefined)
  const loadMetadataSpy = vi
    .spyOn(store, 'loadSourceMetadata')
    .mockResolvedValue(feishuSourceMetadata)
  vi.mocked(checkFeishuSourcePermission).mockResolvedValue({
    code: 200,
    msg: 'ok',
    data: {
      status: 'authorized',
      sheet_url: feishuSource.pathOrUrl,
      message: '已授权',
    },
  })

  const wrapper = mount(WorkbenchRuleOrchestrationPanel, {
    props: {
      selectedRuleIds: [],
    },
    global: {
      plugins: [pinia],
      stubs: {
        RuleOrchestrationContainer: {
          emits: ['create-package-items-rule', 'create-event-task-rule'],
          template: `
            <section>
              <button type="button" data-testid="package-entry" @click="$emit('create-package-items-rule')">
                IAP礼包校验
              </button>
              <button type="button" data-testid="event-task-entry" @click="$emit('create-event-task-rule')">
                节日任务校验
              </button>
            </section>
          `,
        },
        PackageItemsRuleDialog: {
          props: ['visible', 'draft'],
          emits: ['save', 'close'],
          methods: {
            savePackageRule() {
              const draft = this.draft as Partial<PackageItemsRuleDialogDraft>
              this.$emit('save', {
                ...draft,
                group_id: draft.group_id || 'ungrouped',
                rule_name: draft.rule_name || 'IAP礼包配置校验',
                feishu_source_id: 'feishu-plan',
                feishu_sheet_id: 'gid_plan',
                feishu_sheet_name: '礼包规划',
                detail_variable_tag: '[package-detail]',
                config_variable_tag: '[package-config]',
                parse_strategy: 'auto',
                ai_parse_mode: 'auto',
                validation_scope: 'specified',
                package_id_filter: '26042411',
              })
            },
          },
          template: `
            <section v-if="visible" data-testid="package-dialog">
              <button type="button" data-testid="save-package" @click="savePackageRule">保存礼包规则</button>
            </section>
          `,
        },
        EventTaskRuleDialog: {
          props: [
            'visible',
            'draft',
            'groups',
            'feishuSources',
            'compositeVariables',
            'sourceMetadataMap',
            'feishuAuthorizationMap',
            'refreshingSheets',
          ],
          emits: ['save', 'close', 'refresh-sheets'],
          methods: {
            saveEventTaskRule() {
              const draft = this.draft as Partial<EventTaskRuleDialogDraft>
              const sourceId = this.feishuSources[0]?.id ?? ''
              const firstSheet = this.sourceMetadataMap[sourceId]?.sheets?.[0]
              const firstVariable = this.compositeVariables[0]
              this.$emit('save', {
                ...draft,
                group_id: draft.group_id || 'ungrouped',
                rule_name: draft.rule_name || '节日任务校验',
                enabled: true,
                description:
                  '节日任务表与项目任务配置表一致性校验规则，校验任务组ID、任务描述及 STR_Loot 奖励内容是否一致。',
                feishu_source_id: sourceId,
                feishu_sheet_id: firstSheet?.sheet_id ?? firstSheet?.name ?? '',
                feishu_sheet_name: firstSheet?.name ?? '',
                config_variable_tag: firstVariable?.tag ?? '',
                parse_strategy: 'group_desc',
                ai_parse_mode: 'auto',
                validation_scope: 'all',
                task_group_id_filter: '',
                key_delimiter: '_',
                fallback_match_field: 'INT_TaskID',
              })
            },
          },
          template: `
            <section v-if="visible" data-testid="event-task-dialog">
              <div data-testid="event-task-draft-name">{{ draft.rule_name }}</div>
              <div data-testid="event-task-groups">{{ groups.map((group) => group.group_name).join('|') }}</div>
              <div data-testid="event-task-sources">{{ feishuSources.map((source) => source.id).join('|') }}</div>
              <div data-testid="event-task-variables">{{ compositeVariables.map((variable) => variable.tag).join('|') }}</div>
              <button
                type="button"
                data-testid="refresh-event-task"
                @click="$emit('refresh-sheets', feishuSources[0]?.id || '', true)"
              >
                刷新节日任务 Sheet
              </button>
              <button type="button" data-testid="save-event-task" @click="saveEventTaskRule">
                保存节日任务规则
              </button>
            </section>
          `,
        },
        RuleConfigDialog: true,
        RuleGroupDialog: true,
        DualCompositeRuleDialog: true,
        CompositeRuleDialog: true,
        MultiCompositePipelineDialog: true,
        MultiCompositeMappingDialog: true,
      },
    },
  })

  return { wrapper, store, saveSpy, loadMetadataSpy }
}

describe('WorkbenchRuleOrchestrationPanel package items rule', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.sessionStorage.clear()
  })

  it('opens package items dialog from the dedicated entry', async () => {
    const { wrapper } = mountPanel()

    await wrapper.get('[data-testid="package-entry"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="package-dialog"]').exists()).toBe(true)
  })

  it('checks Feishu permission and loads lightweight sheets after authorization', async () => {
    const { wrapper, loadMetadataSpy } = mountPanel()

    await wrapper.get('[data-testid="package-entry"]').trigger('click')
    await flushPromises()

    expect(checkFeishuSourcePermission).toHaveBeenCalledWith({
      source_id: 'feishu-plan',
      sheet_url: feishuSource.pathOrUrl,
    })
    expect(loadMetadataSpy).toHaveBeenCalledWith('feishu-plan', false, {
      includeColumns: false,
    })
  })

  it('does not load sheet metadata when Feishu permission is pending', async () => {
    const { wrapper, loadMetadataSpy } = mountPanel()
    vi.mocked(checkFeishuSourcePermission).mockResolvedValueOnce({
      code: 200,
      msg: 'ok',
      data: {
        status: 'pending_authorization',
        message: '机器人暂无该表格权限。',
      },
    })

    await wrapper.get('[data-testid="package-entry"]').trigger('click')
    await flushPromises()

    expect(loadMetadataSpy).not.toHaveBeenCalled()
  })

  it('uses session cached sheet list before the background permission check finishes', async () => {
    const { wrapper, store, loadMetadataSpy } = mountPanel()
    window.sessionStorage.setItem(
      `excel-checkers:package-items-sheets:v1:${encodeURIComponent(
        `${feishuSource.id}\n${feishuSource.pathOrUrl}`,
      )}`,
      JSON.stringify({
        savedAt: Date.now(),
        sourceId: feishuSource.id,
        sheetUrl: feishuSource.pathOrUrl,
        metadata: feishuSourceMetadata,
      }),
    )

    await wrapper.get('[data-testid="package-entry"]').trigger('click')
    await flushPromises()

    expect(store.sourceMetadataMap['feishu-plan']).toEqual(feishuSourceMetadata)
    expect(checkFeishuSourcePermission).toHaveBeenCalled()
    expect(loadMetadataSpy).not.toHaveBeenCalled()
  })

  it('adds package_items_compare rule and persists workbench config after save', async () => {
    const { wrapper, store, saveSpy } = mountPanel()

    await wrapper.get('[data-testid="package-entry"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="save-package"]').trigger('click')

    expect(store.orchestrationRules).toHaveLength(1)
    expect(store.orchestrationRules[0]).toMatchObject({
      rule_type: 'package_items_compare',
      reference_variable_tag: '[package-config]',
      left_package_field: '礼包id',
      left_item_field: '道具ID',
      left_count_field: '个数',
      right_package_field: 'INT_PackageId',
      right_items_field: 'STR_Items',
      package_id_filter: '26042411',
      package_parse_config: {
        feishu_source_id: 'feishu-plan',
        feishu_sheet_id: 'gid_plan',
        feishu_sheet_name: '礼包规划',
        validation_scope: 'specified',
        package_id_filter: '26042411',
      },
    })
    expect(store.orchestrationRules[0].target_variable_tag).toBe(
      `__runtime_package_plan__:${store.orchestrationRules[0].rule_id}`,
    )
    expect(saveSpy).toHaveBeenCalledTimes(1)
  })

  it('opens event task dialog with store-backed selections and real sheet refresh flow', async () => {
    const { wrapper, store, saveSpy, loadMetadataSpy } = mountPanel()

    await wrapper.get('[data-testid="event-task-entry"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="event-task-dialog"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="event-task-draft-name"]').text()).toBe('节日任务校验')
    expect(wrapper.get('[data-testid="event-task-groups"]').text()).toContain('未分组')
    expect(wrapper.get('[data-testid="event-task-sources"]').text()).toContain('feishu-plan')
    expect(wrapper.get('[data-testid="event-task-variables"]').text()).toContain('[package-config]')
    expect(checkFeishuSourcePermission).toHaveBeenCalledWith({
      source_id: 'feishu-plan',
      sheet_url: feishuSource.pathOrUrl,
    })
    expect(loadMetadataSpy).toHaveBeenCalledWith('feishu-plan', false, {
      includeColumns: false,
    })
    expect(previewWorkbenchPackageItems).not.toHaveBeenCalled()

    vi.mocked(checkFeishuSourcePermission).mockClear()
    loadMetadataSpy.mockClear()
    await wrapper.get('[data-testid="refresh-event-task"]').trigger('click')
    await flushPromises()

    expect(ElMessage.info).not.toHaveBeenCalledWith('Sheet 列表已刷新（前端模拟）')
    expect(checkFeishuSourcePermission).toHaveBeenCalledWith({
      source_id: 'feishu-plan',
      sheet_url: feishuSource.pathOrUrl,
    })
    expect(loadMetadataSpy).toHaveBeenCalledWith('feishu-plan', true, {
      includeColumns: false,
    })
    expect(previewWorkbenchPackageItems).not.toHaveBeenCalled()

    await wrapper.get('[data-testid="save-event-task"]').trigger('click')
    await flushPromises()

    expect(ElMessage.success).toHaveBeenCalledWith('保存成功（前端模拟）')
    expect(wrapper.find('[data-testid="event-task-dialog"]').exists()).toBe(false)
    expect(store.orchestrationRules).toHaveLength(0)
    expect(saveSpy).not.toHaveBeenCalled()
  })
})
