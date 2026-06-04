import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { fetchCompositePreview } from '../../src/api/workbench'
import { useFixedRulesStore } from '../../src/store/fixedRules'
import { useWorkbenchStore } from '../../src/store/workbench'
import { COMPOSITE_PREVIEW_PAGE_SIZE } from '../../src/store/workbench/variableActions'
import type { DataSource, VariableTag } from '../../src/types/workbench'

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

vi.mock('../../src/api/fixedRules', () => ({
  executeFixedRules: vi.fn(),
  exportFixedRulesResults: vi.fn(),
  fetchFixedRulesConfig: vi.fn(),
  fetchFixedRulesResults: vi.fn(),
  saveFixedRulesConfig: vi.fn(),
  triggerFixedRulesSvnUpdate: vi.fn(),
}))

const fetchCompositePreviewMock = vi.mocked(fetchCompositePreview)

const source: DataSource = {
  id: 'src_items',
  type: 'local_excel',
  pathOrUrl: 'C:/data/items.xlsx',
}

const compositeVariable: VariableTag = {
  tag: '[items-mapping]',
  source_id: 'src_items',
  sheet: 'items',
  variable_kind: 'composite',
  columns: ['ID', 'Name'],
  key_column: 'ID',
  expected_type: 'json',
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

describe('variable preview pagination', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockCompositePreviewResponse()
  })

  it('requests the first composite preview page from workbench variable previews', async () => {
    const store = useWorkbenchStore()
    store.sources = [source]
    store.variables = [compositeVariable]

    await store.loadVariablePreview(compositeVariable, undefined, true)

    expect(fetchCompositePreviewMock).toHaveBeenCalledWith(
      expect.objectContaining({
        source,
        page: 1,
        size: COMPOSITE_PREVIEW_PAGE_SIZE,
      }),
    )
  })

  it('passes requested composite preview pages from fixed-rules variable previews', async () => {
    const store = useFixedRulesStore()
    store.config.sources = [source]
    store.config.variables = [compositeVariable]

    await store.loadVariablePreview(
      compositeVariable,
      { page: 2, size: COMPOSITE_PREVIEW_PAGE_SIZE },
      true,
    )

    expect(fetchCompositePreviewMock).toHaveBeenCalledWith(
      expect.objectContaining({
        source,
        page: 2,
        size: COMPOSITE_PREVIEW_PAGE_SIZE,
      }),
    )
  })

  it('does not reuse a cached composite preview for a different page', async () => {
    const store = useWorkbenchStore()
    store.sources = [source]
    store.variables = [compositeVariable]

    await store.loadVariablePreview(
      compositeVariable,
      { page: 1, size: COMPOSITE_PREVIEW_PAGE_SIZE },
      true,
    )
    await store.loadVariablePreview(
      compositeVariable,
      { page: 2, size: COMPOSITE_PREVIEW_PAGE_SIZE },
      false,
    )

    expect(fetchCompositePreviewMock).toHaveBeenCalledTimes(2)
    expect(fetchCompositePreviewMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        page: 2,
        size: COMPOSITE_PREVIEW_PAGE_SIZE,
      }),
    )
  })
})
