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
  TestCaseExportRequest,
  TestCaseGenerationApiResponse,
  TestCaseGenerationRequest,
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
