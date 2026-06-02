// @vitest-environment happy-dom

import { mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { reactive } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { checkFeishuSourcePermission } from '../../src/api/workbench'
import DataSourcePanel from '../../src/components/workbench/DataSourcePanel.vue'
import type { SourceManagementStoreLike } from '../../src/types/panelStores'
import type { DataSource } from '../../src/types/workbench'

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}))

vi.mock('../../src/api/workbench', () => ({
  checkFeishuSourcePermission: vi.fn(),
  sendFeishuSourceAuthorizationCard: vi.fn(),
  pickLocalSourcePath: vi.fn(),
  uploadSourceFile: vi.fn(),
  executeTaskTree: vi.fn(),
  exportExecutionResults: vi.fn(),
  fetchColumnPreview: vi.fn(),
  fetchCompositePreview: vi.fn(),
  fetchExecutionResults: vi.fn(),
  fetchSourceCapabilities: vi.fn(),
  fetchSourceMetadata: vi.fn(),
  triggerWorkbenchSvnUpdate: vi.fn(),
}))

vi.mock('../../src/api/svn', () => ({
  ensureTrailingSlash: (value: string) => (value.endsWith('/') ? value : `${value}/`),
  fetchSvnCredential: vi.fn(),
  getDefaultSvnCredentialTestDirUrl: vi.fn(() => ''),
  isHttpDirUrl: (value: string) => /^https?:\/\//i.test(value),
  parseSvnHost: vi.fn(() => ''),
  listSvnCredentialHosts: vi.fn().mockResolvedValue({ data: { items: [] } }),
}))

const checkFeishuSourcePermissionMock = vi.mocked(checkFeishuSourcePermission)

const FEISHU_URL_OLD = 'https://demo.feishu.cn/sheets/shtcnold123?sheet=gid001'
const FEISHU_URL_NEW = 'https://demo.feishu.cn/sheets/shtcnnew456?sheet=gid002'

const globalStubs = {
  EmptyState: true,
  SvnPickerDialog: true,
  SvnCredentialDialog: true,
  'el-table': {
    template: '<div><slot /></div>',
  },
  'el-table-column': true,
  'el-dialog': {
    props: ['modelValue', 'title'],
    template:
      '<section v-if="modelValue"><h2>{{ title }}</h2><slot /><footer><slot name="footer" /></footer></section>',
  },
  'el-input': {
    props: ['modelValue', 'placeholder'],
    emits: ['update:modelValue', 'input'],
    template: `
      <input
        :value="modelValue"
        :placeholder="placeholder"
        @input="$emit('update:modelValue', $event.target.value); $emit('input', $event.target.value)"
      />
    `,
  },
  'el-select': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div><slot /></div>',
  },
  'el-option': {
    props: ['label', 'value'],
    template: '<div :data-value="value">{{ label }}</div>',
  },
  'el-tag': {
    template: '<span><slot /></span>',
  },
  'el-autocomplete': {
    props: ['modelValue', 'placeholder'],
    emits: ['update:modelValue', 'input', 'clear', 'select'],
    template: `
      <input
        :value="modelValue"
        :placeholder="placeholder"
        @input="$emit('update:modelValue', $event.target.value); $emit('input', $event.target.value)"
      />
    `,
  },
  'el-radio-group': {
    template: '<div><slot /></div>',
  },
  'el-radio-button': {
    props: ['label'],
    template: '<button type="button">{{ label }}</button>',
  },
}

function createStore(sources: DataSource[] = []): SourceManagementStoreLike {
  return reactive({
    sources: [...sources],
    capabilities: ['local_excel', 'feishu', 'svn'],
    preferredSourceId: null,
    sourceMetadataMap: {},
    svnPathReplacementPresets: [],
    selectedSvnPathReplacementPreset: null,
    upsertSource(source: DataSource, originalId?: string) {
      const index = this.sources.findIndex((item) => item.id === (originalId ?? source.id))
      if (index >= 0) {
        this.sources.splice(index, 1, source)
        return
      }
      this.sources.unshift(source)
    },
    removeSource(sourceId: string) {
      this.sources = this.sources.filter((source) => source.id !== sourceId)
    },
    useSampleSource() {},
  }) as SourceManagementStoreLike
}

function mountPanel(store = createStore()): VueWrapper {
  return mount(DataSourcePanel, {
    props: {
      store,
    },
    global: {
      stubs: globalStubs,
    },
  })
}

function findButton(wrapper: VueWrapper, text: string) {
  return wrapper.findAll('button').find((button) => button.text().includes(text))
}

async function flushPromises(): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
}

function authorizedResponse(sheetUrl = FEISHU_URL_OLD) {
  return {
    code: 200,
    msg: 'ok',
    data: {
      status: 'authorized' as const,
      sheet_url: sheetUrl,
      title: '已授权表',
    },
  }
}

function pendingResponse() {
  return {
    code: 200,
    msg: 'ok',
    data: {
      status: 'pending_authorization' as const,
      message: '机器人暂无该表格权限，请发送授权请求到群。',
    },
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((innerResolve) => {
    resolve = innerResolve
  })
  return { promise, resolve }
}

describe('DataSourcePanel Feishu authorization state', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('auto-checks an edited Feishu source and hides authorization button when already readable', async () => {
    checkFeishuSourcePermissionMock.mockResolvedValueOnce(authorizedResponse())
    const wrapper = mountPanel()

    ;(wrapper.vm as unknown as {
      openEditDialog: (source: DataSource) => void
    }).openEditDialog({
      id: 'feishu_items',
      type: 'feishu',
      pathOrUrl: FEISHU_URL_OLD,
    })
    await flushPromises()

    expect(checkFeishuSourcePermissionMock).toHaveBeenCalledWith({
      source_id: 'feishu_items',
      sheet_url: FEISHU_URL_OLD,
    })
    expect(wrapper.text()).toContain('已授权')
    expect(findButton(wrapper, '一键授权到群')).toBeUndefined()
  })

  it('auto-checks a prefilled new Feishu source and allows saving when authorized', async () => {
    checkFeishuSourcePermissionMock.mockResolvedValueOnce(authorizedResponse())
    const wrapper = mountPanel()

    ;(wrapper.vm as unknown as {
      openCreateDialog: (prefill: {
        id: string
        type: DataSource['type']
        pathOrUrl: string
      }) => void
    }).openCreateDialog({
      id: 'feishu_items',
      type: 'feishu',
      pathOrUrl: FEISHU_URL_OLD,
    })
    await flushPromises()

    const saveButton = findButton(wrapper, '保存数据源')
    expect(wrapper.text()).toContain('已授权')
    expect(findButton(wrapper, '一键授权到群')).toBeUndefined()
    expect(saveButton?.attributes('disabled')).toBeUndefined()
  })

  it('shows authorization button only after permission check reports pending authorization', async () => {
    checkFeishuSourcePermissionMock.mockResolvedValueOnce(pendingResponse())
    const wrapper = mountPanel()

    ;(wrapper.vm as unknown as {
      openCreateDialog: (prefill: {
        id: string
        type: DataSource['type']
        pathOrUrl: string
      }) => void
    }).openCreateDialog({
      id: 'feishu_items',
      type: 'feishu',
      pathOrUrl: FEISHU_URL_OLD,
    })
    await flushPromises()

    expect(wrapper.text()).toContain('待授权')
    expect(findButton(wrapper, '一键授权到群')?.exists()).toBe(true)
  })

  it('does not auto-check or show authorization button before source id is valid', async () => {
    const wrapper = mountPanel(createStore([{ id: 'dup_source', type: 'local_excel', pathOrUrl: 'C:/a.xlsx' }]))

    ;(wrapper.vm as unknown as {
      openCreateDialog: (prefill: {
        id: string
        type: DataSource['type']
        pathOrUrl: string
      }) => void
    }).openCreateDialog({
      id: 'dup_source',
      type: 'feishu',
      pathOrUrl: FEISHU_URL_OLD,
    })
    await flushPromises()

    expect(checkFeishuSourcePermissionMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('数据源标识已存在')
    expect(findButton(wrapper, '一键授权到群')).toBeUndefined()
  })

  it('does not show authorization button for app permission errors', async () => {
    checkFeishuSourcePermissionMock.mockResolvedValueOnce({
      code: 200,
      msg: 'ok',
      data: {
        status: 'app_permission_missing',
        message: '飞书应用缺少读取电子表格权限。',
      },
    })
    const wrapper = mountPanel()

    ;(wrapper.vm as unknown as {
      openCreateDialog: (prefill: {
        id: string
        type: DataSource['type']
        pathOrUrl: string
      }) => void
    }).openCreateDialog({
      id: 'feishu_items',
      type: 'feishu',
      pathOrUrl: FEISHU_URL_OLD,
    })
    await flushPromises()

    expect(wrapper.text()).toContain('应用权限不足')
    expect(findButton(wrapper, '一键授权到群')).toBeUndefined()
  })

  it('drops stale permission responses after the Feishu URL changes', async () => {
    const staleCheck = deferred<ReturnType<typeof authorizedResponse>>()
    checkFeishuSourcePermissionMock
      .mockReturnValueOnce(staleCheck.promise)
      .mockResolvedValueOnce(authorizedResponse(FEISHU_URL_NEW))
    const wrapper = mountPanel()

    ;(wrapper.vm as unknown as {
      openCreateDialog: (prefill: {
        id: string
        type: DataSource['type']
        pathOrUrl: string
      }) => void
    }).openCreateDialog({
      id: 'feishu_items',
      type: 'feishu',
      pathOrUrl: FEISHU_URL_OLD,
    })
    await flushPromises()
    expect(checkFeishuSourcePermissionMock).toHaveBeenCalledTimes(1)

    const urlInput = wrapper.findAll('input')[1]
    await urlInput.setValue(FEISHU_URL_NEW)
    expect(findButton(wrapper, '一键授权到群')).toBeUndefined()

    await vi.advanceTimersByTimeAsync(500)
    await flushPromises()
    expect(checkFeishuSourcePermissionMock).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('已授权')

    staleCheck.resolve(pendingResponse() as ReturnType<typeof authorizedResponse>)
    await flushPromises()

    expect(wrapper.text()).toContain('已授权')
    expect(findButton(wrapper, '一键授权到群')).toBeUndefined()
  })
})
