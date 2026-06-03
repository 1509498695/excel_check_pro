import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  commitWorkbenchImport,
  fetchWorkbenchImportDraft,
  previewWorkbenchImport,
} from '../../src/features/fixed-rules-import/api'
import type { WorkbenchImportPreviewRequest } from '../../src/features/fixed-rules-import/types'
import { apiFetch } from '../../src/utils/apiFetch'

vi.mock('../../src/utils/apiFetch', () => ({
  apiFetch: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)

const previewRequest: WorkbenchImportPreviewRequest = {
  scope: {
    mode: 'rules',
    group_ids: [],
    rule_ids: ['rule-a'],
  },
  selected_rule_ids: ['rule-a'],
  selected_group_ids: null,
  source_mappings: [
    {
      personal_source_id: 'src-personal',
      action: 'new',
      project_source_id: null,
      next_source: {
        id: 'src-personal',
        type: 'local_excel',
        pathOrUrl: 'D:/data/items.xlsx',
      },
      confirmed: true,
    },
  ],
  conflict_resolutions: {
    variable_tags: {},
    rule_names: {},
    group_names: {},
  },
  duplicate_rule_actions: {
    'rule-a': 'rename',
  },
}

describe('fixed-rules-import api', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    apiFetchMock.mockResolvedValue({ code: 200, msg: 'ok', data: {} })
  })

  it('requests draft from the current workbench import endpoint', async () => {
    await fetchWorkbenchImportDraft({
      selected_rule_ids: ['rule-a', 'rule-b'],
      selected_group_ids: ['group-a'],
    })

    expect(apiFetchMock).toHaveBeenCalledWith(
      '/api/v1/fixed-rules/import/workbench/draft?selected_rule_ids=rule-a&selected_rule_ids=rule-b&selected_group_ids=group-a',
    )
  })

  it('posts preview payload to the current workbench preview endpoint', async () => {
    await previewWorkbenchImport(previewRequest)

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/fixed-rules/import/workbench/preview', {
      method: 'POST',
      body: JSON.stringify(previewRequest),
    })
  })

  it('posts commit payload to the current workbench commit endpoint', async () => {
    await commitWorkbenchImport(previewRequest)

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/fixed-rules/import/workbench/commit', {
      method: 'POST',
      body: JSON.stringify(previewRequest),
    })
  })
})
