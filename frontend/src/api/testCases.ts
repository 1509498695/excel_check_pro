import type { ApiFileResponse } from '../types/api'
import type {
  PlanningSnapshotApiResponse,
  PlanningSnapshotBriefApiResponse,
  PlanningSnapshotBriefRequest,
  PlanningSnapshotRequest,
  ReferenceCategoryApiResponse,
  ReferenceCategoryCreateRequest,
  ReferenceCategoryListApiResponse,
  ReferenceCategoryUpdateRequest,
  ReferenceDeleteApiResponse,
  ReferenceFileApiResponse,
  ReferenceFileListApiResponse,
  SourceEvidenceAdoptVisualEvidenceRequest,
  SourceEvidenceCleanupAuditListApiResponse,
  SourceEvidenceObservationListApiResponse,
  SourceEvidenceResourceListApiResponse,
  SourceEvidenceRunApiResponse,
  SourceEvidenceRunCreateRequest,
  SourceEvidenceSnapshotRequest,
  SourceEvidenceVisualCandidatesApiResponse,
  SourceEvidenceVisualSelectionRequest,
  TestCaseExportRequest,
  TestCaseGenerationCaseListApiResponse,
  TestCaseGenerationArtifactListApiResponse,
  TestCaseGenerationApiResponse,
  TestCaseGenerationRequest,
  TestCaseGenerationRunApiResponse,
  TestCaseGenerationRunCreateRequest,
  TestCaseGenerationRunRetryFailedChunksApiResponse,
  TestCaseRequirementAtomListApiResponse,
  SourceEvidenceAuthorizationRequestApiResponse,
  SourceEvidenceCapabilityStatusApiResponse,
} from '../types/testCases'
import { apiDownloadFile, apiFetch } from '../utils/apiFetch'

export async function readPlanningSnapshot(
  payload: PlanningSnapshotRequest,
): Promise<PlanningSnapshotApiResponse> {
  return apiFetch<PlanningSnapshotApiResponse>('/api/v1/test-cases/planning-snapshot', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function readPlanningSnapshotBrief(
  payload: PlanningSnapshotBriefRequest,
): Promise<PlanningSnapshotBriefApiResponse> {
  return apiFetch<PlanningSnapshotBriefApiResponse>('/api/v1/test-cases/planning-snapshot/brief', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function createSourceEvidenceRun(
  payload: SourceEvidenceRunCreateRequest,
): Promise<SourceEvidenceRunApiResponse> {
  return apiFetch<SourceEvidenceRunApiResponse>('/api/v1/test-cases/source-evidence-runs', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function createLocalFileSourceEvidenceRun(file: File): Promise<SourceEvidenceRunApiResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return apiFetch<SourceEvidenceRunApiResponse>('/api/v1/test-cases/source-evidence-runs/upload', {
    method: 'POST',
    body: formData,
  })
}

export async function fetchSourceEvidenceRun(runId: number): Promise<SourceEvidenceRunApiResponse> {
  return apiFetch<SourceEvidenceRunApiResponse>(`/api/v1/test-cases/source-evidence-runs/${runId}`)
}

export async function fetchSourceEvidenceCapabilities(): Promise<SourceEvidenceCapabilityStatusApiResponse> {
  return apiFetch<SourceEvidenceCapabilityStatusApiResponse>('/api/v1/test-cases/source-evidence-capabilities')
}

export async function fetchSourceEvidenceResources(runId: number): Promise<SourceEvidenceResourceListApiResponse> {
  return apiFetch<SourceEvidenceResourceListApiResponse>(
    `/api/v1/test-cases/source-evidence-runs/${runId}/resources`,
  )
}

export async function fetchSourceEvidenceVisualCandidates(
  runId: number,
  sheetName?: string | null,
): Promise<SourceEvidenceVisualCandidatesApiResponse> {
  const normalizedSheetName = sheetName?.trim()
  const query = normalizedSheetName ? `?sheet_name=${encodeURIComponent(normalizedSheetName)}` : ''
  return apiFetch<SourceEvidenceVisualCandidatesApiResponse>(
    `/api/v1/test-cases/source-evidence-runs/${runId}/visual-candidates${query}`,
  )
}

export async function saveSourceEvidenceVisualSelections(
  runId: number,
  payload: SourceEvidenceVisualSelectionRequest,
): Promise<SourceEvidenceVisualCandidatesApiResponse> {
  return apiFetch<SourceEvidenceVisualCandidatesApiResponse>(
    `/api/v1/test-cases/source-evidence-runs/${runId}/visual-selections`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )
}

export async function observeSourceEvidenceRun(
  runId: number,
): Promise<SourceEvidenceObservationListApiResponse> {
  return apiFetch<SourceEvidenceObservationListApiResponse>(
    `/api/v1/test-cases/source-evidence-runs/${runId}/observations`,
    {
      method: 'POST',
    },
  )
}

export async function fetchSourceEvidenceObservations(
  runId: number,
): Promise<SourceEvidenceObservationListApiResponse> {
  return apiFetch<SourceEvidenceObservationListApiResponse>(
    `/api/v1/test-cases/source-evidence-runs/${runId}/observations`,
  )
}

export async function adoptSourceEvidenceVisualEvidence(
  runId: number,
  payload: SourceEvidenceAdoptVisualEvidenceRequest,
): Promise<SourceEvidenceObservationListApiResponse> {
  return apiFetch<SourceEvidenceObservationListApiResponse>(
    `/api/v1/test-cases/source-evidence-runs/${runId}/adopted-visual-evidence`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )
}

export async function revokeSourceEvidenceVisualEvidence(
  runId: number,
  evidenceId: number,
): Promise<SourceEvidenceObservationListApiResponse> {
  return apiFetch<SourceEvidenceObservationListApiResponse>(
    `/api/v1/test-cases/source-evidence-runs/${runId}/adopted-visual-evidence/${evidenceId}`,
    {
      method: 'DELETE',
    },
  )
}

export async function readSourceEvidenceSnapshot(
  runId: number,
  payload?: SourceEvidenceSnapshotRequest | null,
): Promise<PlanningSnapshotApiResponse> {
  const options: RequestInit = {
    method: 'POST',
  }
  if (payload) {
    options.body = JSON.stringify(payload)
  }
  return apiFetch<PlanningSnapshotApiResponse>(`/api/v1/test-cases/source-evidence-runs/${runId}/snapshot`, options)
}

export async function retrySourceEvidenceRun(runId: number): Promise<SourceEvidenceRunApiResponse> {
  return apiFetch<SourceEvidenceRunApiResponse>(`/api/v1/test-cases/source-evidence-runs/${runId}/retry`, {
    method: 'POST',
  })
}

export async function requestSourceEvidenceAuthorization(
  runId: number,
): Promise<SourceEvidenceAuthorizationRequestApiResponse> {
  return apiFetch<SourceEvidenceAuthorizationRequestApiResponse>(
    `/api/v1/test-cases/source-evidence-runs/${runId}/authorization-request`,
    {
      method: 'POST',
    },
  )
}

export async function fetchSourceEvidenceCleanupAudits(
  params: { limit?: number; offset?: number } = {},
): Promise<SourceEvidenceCleanupAuditListApiResponse> {
  const query = new URLSearchParams()
  if (typeof params.limit === 'number') {
    query.set('limit', String(params.limit))
  }
  if (typeof params.offset === 'number') {
    query.set('offset', String(params.offset))
  }
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return apiFetch<SourceEvidenceCleanupAuditListApiResponse>(
    `/api/v1/test-cases/source-evidence-cleanup-audits${suffix}`,
  )
}

export async function generateTestCases(
  payload: TestCaseGenerationRequest,
): Promise<TestCaseGenerationApiResponse> {
  return apiFetch<TestCaseGenerationApiResponse>('/api/v1/test-cases/generate', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function createGenerationRun(
  payload: TestCaseGenerationRunCreateRequest,
): Promise<TestCaseGenerationRunApiResponse> {
  return apiFetch<TestCaseGenerationRunApiResponse>('/api/v1/test-cases/generation-runs', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function fetchGenerationRun(runId: number): Promise<TestCaseGenerationRunApiResponse> {
  return apiFetch<TestCaseGenerationRunApiResponse>(`/api/v1/test-cases/generation-runs/${runId}`)
}

export const getGenerationRun = fetchGenerationRun

export async function cancelGenerationRun(runId: number): Promise<TestCaseGenerationRunApiResponse> {
  return apiFetch<TestCaseGenerationRunApiResponse>(`/api/v1/test-cases/generation-runs/${runId}/cancel`, {
    method: 'POST',
  })
}

export async function retryFailedGenerationChunks(
  runId: number,
): Promise<TestCaseGenerationRunRetryFailedChunksApiResponse> {
  return apiFetch<TestCaseGenerationRunRetryFailedChunksApiResponse>(
    `/api/v1/test-cases/generation-runs/${runId}/retry-failed-chunks`,
    {
      method: 'POST',
    },
  )
}

export async function fetchGenerationRunAtoms(runId: number): Promise<TestCaseRequirementAtomListApiResponse> {
  return apiFetch<TestCaseRequirementAtomListApiResponse>(`/api/v1/test-cases/generation-runs/${runId}/atoms`)
}

export const listGenerationRunAtoms = fetchGenerationRunAtoms

export async function fetchGenerationRunCases(runId: number): Promise<TestCaseGenerationCaseListApiResponse> {
  return apiFetch<TestCaseGenerationCaseListApiResponse>(`/api/v1/test-cases/generation-runs/${runId}/cases`)
}

export const listGenerationRunCases = fetchGenerationRunCases

export async function fetchGenerationRunArtifacts(
  runId: number,
): Promise<TestCaseGenerationArtifactListApiResponse> {
  return apiFetch<TestCaseGenerationArtifactListApiResponse>(
    `/api/v1/test-cases/generation-runs/${runId}/artifacts`,
  )
}

export const listGenerationRunArtifacts = fetchGenerationRunArtifacts

export async function downloadGenerationRunArtifact(
  runId: number,
  artifactKey: string,
  fallbackFilename: string,
): Promise<ApiFileResponse> {
  return apiDownloadFile(
    `/api/v1/test-cases/generation-runs/${runId}/artifacts/${encodeURIComponent(artifactKey)}`,
    fallbackFilename,
  )
}

export async function fetchGenerationRunArtifactText(
  runId: number,
  artifactKey: string,
): Promise<string> {
  const file = await apiDownloadFile(
    `/api/v1/test-cases/generation-runs/${runId}/artifacts/${encodeURIComponent(artifactKey)}?inline=true`,
    artifactKey,
  )
  return file.blob.text()
}

export async function retryGenerationRunArtifacts(
  runId: number,
): Promise<TestCaseGenerationArtifactListApiResponse> {
  return apiFetch<TestCaseGenerationArtifactListApiResponse>(
    `/api/v1/test-cases/generation-runs/${runId}/artifacts/retry`,
    { method: 'POST' },
  )
}

export async function exportGenerationRunWorkbook(runId: number): Promise<ApiFileResponse> {
  return apiDownloadFile(
    `/api/v1/test-cases/generation-runs/${runId}/export`,
    `test-cases-v3-run-${runId}.xlsx`,
    {
      method: 'POST',
    },
  )
}

export async function exportTestCaseWorkbook(payload: TestCaseExportRequest): Promise<ApiFileResponse> {
  return apiDownloadFile('/api/v1/test-cases/export', 'test-cases-v1.xlsx', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function fetchReferenceCategories(): Promise<ReferenceCategoryListApiResponse> {
  return apiFetch<ReferenceCategoryListApiResponse>('/api/v1/test-cases/reference-categories')
}

export async function createReferenceCategory(
  payload: ReferenceCategoryCreateRequest,
): Promise<ReferenceCategoryApiResponse> {
  return apiFetch<ReferenceCategoryApiResponse>('/api/v1/test-cases/reference-categories', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function renameReferenceCategory(
  categoryId: number,
  payload: ReferenceCategoryUpdateRequest,
): Promise<ReferenceCategoryApiResponse> {
  return apiFetch<ReferenceCategoryApiResponse>(`/api/v1/test-cases/reference-categories/${categoryId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteReferenceCategory(categoryId: number): Promise<ReferenceDeleteApiResponse> {
  return apiFetch<ReferenceDeleteApiResponse>(`/api/v1/test-cases/reference-categories/${categoryId}`, {
    method: 'DELETE',
  })
}

export async function fetchReferenceFiles(categoryId?: number | null): Promise<ReferenceFileListApiResponse> {
  const query = typeof categoryId === 'number' ? `?category_id=${encodeURIComponent(String(categoryId))}` : ''
  return apiFetch<ReferenceFileListApiResponse>(`/api/v1/test-cases/references${query}`)
}

export async function uploadReferenceFile(
  file: File,
  categoryId?: number | null,
): Promise<ReferenceFileApiResponse> {
  const formData = new FormData()
  formData.append('file', file)
  if (typeof categoryId === 'number') {
    formData.append('category_id', String(categoryId))
  }

  return apiFetch<ReferenceFileApiResponse>('/api/v1/test-cases/references', {
    method: 'POST',
    body: formData,
  })
}

export async function setRecommendedPrimaryReference(referenceId: number): Promise<ReferenceFileApiResponse> {
  return apiFetch<ReferenceFileApiResponse>(`/api/v1/test-cases/references/${referenceId}/recommended-primary`, {
    method: 'POST',
  })
}

export async function deleteReferenceFile(referenceId: number): Promise<ReferenceDeleteApiResponse> {
  return apiFetch<ReferenceDeleteApiResponse>(`/api/v1/test-cases/references/${referenceId}`, {
    method: 'DELETE',
  })
}
