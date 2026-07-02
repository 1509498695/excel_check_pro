import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createLocalFileSourceEvidenceRun,
  createSourceEvidenceRun,
  createReferenceCategory,
  deleteReferenceFile,
  exportTestCaseWorkbook,
  fetchSourceEvidenceCleanupAudits,
  fetchSourceEvidenceCapabilities,
  fetchSourceEvidenceResources,
  fetchSourceEvidenceRun,
  fetchSourceEvidenceVisualCandidates,
  fetchSourceEvidenceObservations,
  fetchReferenceCategories,
  fetchReferenceFiles,
  generateTestCases,
  observeSourceEvidenceRun,
  readPlanningSnapshot,
  readSourceEvidenceSnapshot,
  requestSourceEvidenceAuthorization,
  revokeSourceEvidenceVisualEvidence,
  retrySourceEvidenceRun,
  adoptSourceEvidenceVisualEvidence,
  saveSourceEvidenceVisualSelections,
  setRecommendedPrimaryReference,
  uploadReferenceFile,
} from '../../src/api/testCases'
import { apiDownloadFile, apiFetch } from '../../src/utils/apiFetch'

vi.mock('../../src/utils/apiFetch', () => ({
  apiDownloadFile: vi.fn(),
  apiFetch: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)
const apiDownloadFileMock = vi.mocked(apiDownloadFile)

describe('test case generation api', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    apiDownloadFileMock.mockReset()
    apiFetchMock.mockResolvedValue({ code: 200, msg: 'ok', data: {} })
    apiDownloadFileMock.mockResolvedValue({
      blob: new Blob(['xlsx']),
      filename: 'test-cases-v1.xlsx',
    })
  })

  it('reads a planning sheet snapshot from the backend', async () => {
    const payload = {
      source_type: 'uploaded_excel' as const,
      source: {
        id: 'plan_excel',
        type: 'local_excel' as const,
        pathOrUrl: 'D:/runtime/uploads/planning.xlsx',
      },
      sheet_name: '策划案',
    }

    await readPlanningSnapshot(payload)

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/test-cases/planning-snapshot', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  })

  it('reads an AI-assisted planning snapshot brief from the backend', async () => {
    const planningSnapshot = {
      source_summary: '上传 Excel：planning.xlsx',
      sheet_name: '策划案',
      rows: [
        {
          row_index: 1,
          cells: [
            { row_index: 1, column_index: 1, column_name: '模块', value: '活动入口' },
            { row_index: 1, column_index: 2, column_name: '需求点', value: '按配置开放入口' },
          ],
        },
      ],
      columns: ['模块', '需求点'],
      non_empty_cell_count: 2,
      truncated: false,
      warnings: [],
    }
    const payload = { planning_snapshot: planningSnapshot }
    const api = await import('../../src/api/testCases')

    await api.readPlanningSnapshotBrief(payload)

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/test-cases/planning-snapshot/brief', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  })

  it('generates test cases without reference inputs', async () => {
    const payload = {
      planning_snapshot: {
        source_summary: '上传 Excel：planning.xlsx',
        sheet_name: '策划案',
        rows: [],
        columns: [],
        non_empty_cell_count: 0,
        truncated: false,
        warnings: [],
      },
      reference_ids: [],
      primary_reference_id: null,
      source_evidence_run_id: 42,
      adopted_visual_evidence_ids: [7],
    }

    await generateTestCases(payload)

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/test-cases/generate', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  })

  it('exports the current in-memory result through apiDownloadFile', async () => {
    const payload = {
      blueprint: { modules: [], flows: [], warnings: [] },
      cases: [],
      warnings: [],
      stats: {
        total: 0,
        priority_counts: {},
        module_counts: {},
        case_type_counts: {},
        warning_count: 0,
      },
      export_columns: ['case_id', 'title'],
      source_summary: '上传 Excel：planning.xlsx',
      source_evidence_run_id: 42,
      adopted_visual_evidence_ids: [7],
    }

    await exportTestCaseWorkbook(payload)

    expect(apiDownloadFileMock).toHaveBeenCalledWith(
      '/api/v1/test-cases/export',
      'test-cases-v1.xlsx',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    )
  })

  it('calls Source Evidence Run endpoints', async () => {
    const createPayload = {
      source_type: 'feishu' as const,
      source_url: 'https://example.feishu.cn/docx/doc123',
    }

    await createSourceEvidenceRun(createPayload)
    await fetchSourceEvidenceRun(42)
    await fetchSourceEvidenceResources(42)
    await fetchSourceEvidenceVisualCandidates(42)
    await saveSourceEvidenceVisualSelections(42, { selected_refs: ['img_001'] })
    await observeSourceEvidenceRun(42)
    await fetchSourceEvidenceObservations(42)
    await adoptSourceEvidenceVisualEvidence(42, { observation_ids: [7] })
    await revokeSourceEvidenceVisualEvidence(42, 7)
    await readSourceEvidenceSnapshot(42)
    await retrySourceEvidenceRun(42)
    await requestSourceEvidenceAuthorization(42)
    await fetchSourceEvidenceCapabilities()
    await fetchSourceEvidenceCleanupAudits({ limit: 25, offset: 50 })

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, '/api/v1/test-cases/source-evidence-runs', {
      method: 'POST',
      body: JSON.stringify(createPayload),
    })
    expect(apiFetchMock).toHaveBeenNthCalledWith(2, '/api/v1/test-cases/source-evidence-runs/42')
    expect(apiFetchMock).toHaveBeenNthCalledWith(3, '/api/v1/test-cases/source-evidence-runs/42/resources')
    expect(apiFetchMock).toHaveBeenNthCalledWith(4, '/api/v1/test-cases/source-evidence-runs/42/visual-candidates')
    expect(apiFetchMock).toHaveBeenNthCalledWith(5, '/api/v1/test-cases/source-evidence-runs/42/visual-selections', {
      method: 'POST',
      body: JSON.stringify({ selected_refs: ['img_001'] }),
    })
    expect(apiFetchMock).toHaveBeenNthCalledWith(6, '/api/v1/test-cases/source-evidence-runs/42/observations', {
      method: 'POST',
    })
    expect(apiFetchMock).toHaveBeenNthCalledWith(7, '/api/v1/test-cases/source-evidence-runs/42/observations')
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      8,
      '/api/v1/test-cases/source-evidence-runs/42/adopted-visual-evidence',
      {
        method: 'POST',
        body: JSON.stringify({ observation_ids: [7] }),
      },
    )
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      9,
      '/api/v1/test-cases/source-evidence-runs/42/adopted-visual-evidence/7',
      {
        method: 'DELETE',
      },
    )
    expect(apiFetchMock).toHaveBeenNthCalledWith(10, '/api/v1/test-cases/source-evidence-runs/42/snapshot', {
      method: 'POST',
    })
    expect(apiFetchMock).toHaveBeenNthCalledWith(11, '/api/v1/test-cases/source-evidence-runs/42/retry', {
      method: 'POST',
    })
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      12,
      '/api/v1/test-cases/source-evidence-runs/42/authorization-request',
      {
        method: 'POST',
      },
    )
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      13,
      '/api/v1/test-cases/source-evidence-capabilities',
    )
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      14,
      '/api/v1/test-cases/source-evidence-cleanup-audits?limit=25&offset=50',
    )
  })

  it('creates svn_file Source Evidence runs and uploads local source evidence files', async () => {
    const svnPayload = {
      source_type: 'svn_file' as const,
      source_url: 'https://samosvn/data/project/samo/GameDatas/QuestReward.xls',
    }
    const file = new File(['xlsx'], 'QuestReward.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })

    await createSourceEvidenceRun(svnPayload)
    await createLocalFileSourceEvidenceRun(file)

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, '/api/v1/test-cases/source-evidence-runs', {
      method: 'POST',
      body: JSON.stringify(svnPayload),
    })
    expect(apiFetchMock).toHaveBeenNthCalledWith(2, '/api/v1/test-cases/source-evidence-runs/upload', {
      method: 'POST',
      body: expect.any(FormData),
    })
    const formData = apiFetchMock.mock.calls[1]?.[1]?.body
    expect(formData).toBeInstanceOf(FormData)
    expect((formData as FormData).get('file')).toBe(file)
  })

  it('fetches reference categories and files', async () => {
    await fetchReferenceCategories()
    await fetchReferenceFiles(12)

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, '/api/v1/test-cases/reference-categories')
    expect(apiFetchMock).toHaveBeenNthCalledWith(2, '/api/v1/test-cases/references?category_id=12')
  })

  it('creates a reference category', async () => {
    await createReferenceCategory({ name: '活动用例' })

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/test-cases/reference-categories', {
      method: 'POST',
      body: JSON.stringify({ name: '活动用例' }),
    })
  })

  it('uploads a reference file with an optional category id', async () => {
    const file = new File(['case'], 'history.xlsx')

    await uploadReferenceFile(file, 12)

    const [, options] = apiFetchMock.mock.calls[0]
    expect(apiFetchMock.mock.calls[0][0]).toBe('/api/v1/test-cases/references')
    expect(options?.method).toBe('POST')
    expect(options?.body).toBeInstanceOf(FormData)
    expect((options?.body as FormData).get('category_id')).toBe('12')
    expect((options?.body as FormData).get('file')).toBe(file)
  })

  it('sets recommended primary and deletes a reference file', async () => {
    await setRecommendedPrimaryReference(88)
    await deleteReferenceFile(88)

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, '/api/v1/test-cases/references/88/recommended-primary', {
      method: 'POST',
    })
    expect(apiFetchMock).toHaveBeenNthCalledWith(2, '/api/v1/test-cases/references/88', {
      method: 'DELETE',
    })
  })
})
