// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { reactive } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchCompositePreview } from '../../src/api/workbench'
import VariablePoolPanel from '../../src/components/workbench/VariablePoolPanel.vue'
import { COMPOSITE_PREVIEW_PAGE_SIZE } from '../../src/store/workbench/variableActions'
import type { DataSource, SourceMetadata, VariableTag } from '../../src/types/workbench'

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}))

vi.mock('../../src/api/workbench', () => ({
  executeTaskTree: vi.fn(),
  exportExecutionResults: vi.fn(),
  fetchColumnPreview: vi.fn(),
  fetchCompositePreview: vi.fn(),
  fetchExecutionResults: vi.fn(),
  fetchSourceCapabilities: vi.fn(),
  fetchSourceMetadata: vi.fn(),
  fetchWorkbenchConfig: vi.fn(),
  saveWorkbenchConfig: vi.fn(),
  triggerWorkbenchSvnUpdate: vi.fn(),
}))

const fetchCompositePreviewMock = vi.mocked(fetchCompositePreview)

const source: DataSource = {
  id: 'src_items',
  type: 'local_excel',
  pathOrUrl: 'C:/data/items.xlsx',
}

const metadata: SourceMetadata = {
  source_id: 'src_items',
  source_type: 'local_excel',
  sheets: [{ name: 'items', columns: ['ID', 'Name', 'Env'] }],
}

const globalStubs = {
  EmptyState: true,
  'el-alert': true,
  'el-table': {
    template: '<div><slot /></div>',
  },
  'el-table-column': true,
  'el-dialog': {
    props: ['modelValue', 'title'],
    template: '<section v-if="modelValue"><slot /><footer><slot name="footer" /></footer></section>',
  },
  'el-select': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div><slot /></div>',
  },
  'el-option': true,
  'el-pagination': true,
  'el-input': {
    props: ['modelValue'],
    emits: ['update:modelValue', 'input', 'change'],
    template: '<input :value="modelValue" @change="$emit(\'change\', $event.target.value)" />',
  },
  'el-checkbox': true,
}

function createStore() {
  const store = reactive({
    sources: [source],
    capabilities: ['local_excel'] as Array<DataSource['type']>,
    variables: [] as VariableTag[],
    activeTag: null as string | null,
    sourceMetadataMap: {} as Record<string, SourceMetadata>,
    variablePreviewMap: {},
    preferredSourceId: 'src_items',
    loadSourceMetadata: vi.fn(async (sourceId: string) => {
      store.sourceMetadataMap[sourceId] = metadata
      return metadata
    }),
    upsertVariable: vi.fn(),
    removeVariable: vi.fn(),
    upsertSource: vi.fn(),
    removeSource: vi.fn(),
    useSampleSource: vi.fn(),
    setActiveTag: vi.fn(),
    loadVariablePreview: vi.fn(),
  })
  return store
}

function mockCompositePreviewResponse(): void {
  fetchCompositePreviewMock.mockResolvedValue({
    code: 200,
    msg: 'ok',
    data: {
      variable_kind: 'composite',
      source_id: 'src_items',
      source_type: 'local_excel',
      sheet: 'items',
      columns: ['ID', 'Name'],
      key_column: 'ID',
      append_index_to_key: false,
      has_duplicate_keys: false,
      duplicate_keys_preview: [],
      mapping: { '1': { Name: 'Alpha' } },
      total_rows: 2,
      total_keys: 1,
      page: 1,
      page_size: COMPOSITE_PREVIEW_PAGE_SIZE,
      total_pages: 1,
      loaded_rows: 1,
      loaded_all_rows: true,
    },
  })
}

describe('VariablePoolPanel composite preview pagination', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockCompositePreviewResponse()
  })

  it('requests a paged preview and saves without refetching the full mapping', async () => {
    const store = createStore()
    const wrapper = mount(VariablePoolPanel, {
      props: { store },
      global: { stubs: globalStubs },
    })
    const exposed = wrapper.vm as unknown as {
      openCompositeCreateTab: (prefill: {
        source_id: string
        sheet: string
        columns: string[]
        key_column: string
        tag: string
      }) => Promise<void>
    }

    await exposed.openCompositeCreateTab({
      source_id: 'src_items',
      sheet: 'items',
      columns: ['ID', 'Name'],
      key_column: 'ID',
      tag: '[items-mapping]',
    })
    await flushPromises()

    expect(fetchCompositePreviewMock).toHaveBeenCalledWith(
      expect.objectContaining({
        page: 1,
        size: COMPOSITE_PREVIEW_PAGE_SIZE,
      }),
    )

    const saveButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('保存变量'))
    expect(saveButton).toBeTruthy()
    await saveButton?.trigger('click')
    await flushPromises()

    expect(store.upsertVariable).toHaveBeenCalledWith(
      expect.objectContaining({
        tag: '[items-mapping]',
      }),
      undefined,
    )
    expect(fetchCompositePreviewMock).toHaveBeenCalledTimes(1)
  })
})
