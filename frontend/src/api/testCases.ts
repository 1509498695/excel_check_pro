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
  SourceEvidenceVisualCandidatesApiResponse,
  SourceEvidenceVisualSelectionRequest,
  TestCaseExportRequest,
  TestCaseGenerationApiResponse,
  TestCaseGenerationRequest,
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
): Promise<SourceEvidenceVisualCandidatesApiResponse> {
  return apiFetch<SourceEvidenceVisualCandidatesApiResponse>(
    `/api/v1/test-cases/source-evidence-runs/${runId}/visual-candidates`,
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

export async function readSourceEvidenceSnapshot(runId: number): Promise<PlanningSnapshotApiResponse> {
  return apiFetch<PlanningSnapshotApiResponse>(`/api/v1/test-cases/source-evidence-runs/${runId}/snapshot`, {
    method: 'POST',
  })
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
