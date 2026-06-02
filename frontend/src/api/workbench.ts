import type {
  WorkbenchPackageItemsPreviewRequest,
  WorkbenchPackageItemsPreviewResponse,
} from '../types/fixedRules'
import type {
  ApiResponse,
  ApiStatusResponse,
  ColumnPreviewRequest,
  ColumnPreviewResponse,
  CompositePreviewRequest,
  CompositePreviewResponse,
  DataSource,
  ExecuteResponse,
  FeishuPermissionCheckResponse,
  FeishuSendAuthorizationCardResponse,
  FeishuSourceAuthorizationRequest,
  LocalDirectoryValidateResponse,
  LocalPickResponse,
  SourceCapabilitiesResponse,
  SourceMetadataResponse,
  SourceUploadResponse,
  TaskTree,
  WorkbenchSvnUpdateResponse,
} from '../types/workbench'
import { apiDownloadFile, apiFetch, type ApiFileResponse } from '../utils/apiFetch'

export async function fetchSourceCapabilities(): Promise<SourceCapabilitiesResponse> {
  return apiFetch<SourceCapabilitiesResponse>('/api/v1/sources/capabilities')
}

export async function pickLocalSourcePath(
  sourceType: 'local_excel',
): Promise<LocalPickResponse> {
  return apiFetch<LocalPickResponse>('/api/v1/sources/local-pick', {
    method: 'POST',
    body: JSON.stringify({ source_type: sourceType }),
  })
}

export async function uploadSourceFile(file: File): Promise<SourceUploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return apiFetch<SourceUploadResponse>('/api/v1/sources/upload', {
    method: 'POST',
    body: formData,
  })
}

export async function validateLocalDirectoryPath(
  directoryPath: string,
): Promise<LocalDirectoryValidateResponse> {
  return apiFetch<LocalDirectoryValidateResponse>('/api/v1/sources/local-directory-validate', {
    method: 'POST',
    body: JSON.stringify({ directory_path: directoryPath }),
  })
}

export async function fetchSourceMetadata(source: DataSource): Promise<SourceMetadataResponse> {
  return apiFetch<SourceMetadataResponse>('/api/v1/sources/metadata', {
    method: 'POST',
    body: JSON.stringify(source),
  })
}

export async function checkFeishuSourcePermission(
  payload: FeishuSourceAuthorizationRequest,
): Promise<FeishuPermissionCheckResponse> {
  return apiFetch<FeishuPermissionCheckResponse>('/api/v1/feishu/sources/check-permission', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function sendFeishuSourceAuthorizationCard(
  payload: FeishuSourceAuthorizationRequest,
): Promise<FeishuSendAuthorizationCardResponse> {
  return apiFetch<FeishuSendAuthorizationCardResponse>(
    '/api/v1/feishu/sources/send-authorization-card',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )
}

export async function fetchColumnPreview(
  payload: ColumnPreviewRequest,
): Promise<ColumnPreviewResponse> {
  return apiFetch<ColumnPreviewResponse>('/api/v1/sources/column-preview', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function fetchCompositePreview(
  payload: CompositePreviewRequest,
): Promise<CompositePreviewResponse> {
  return apiFetch<CompositePreviewResponse>('/api/v1/sources/composite-preview', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function executeTaskTree(taskTree: TaskTree): Promise<ExecuteResponse> {
  return apiFetch<ExecuteResponse>('/api/v1/engine/execute', {
    method: 'POST',
    body: JSON.stringify(taskTree),
  })
}

export async function fetchExecutionResults(
  resultId: number,
  page: number,
  size: number,
): Promise<ExecuteResponse> {
  return apiFetch<ExecuteResponse>(`/api/v1/engine/results/${resultId}?page=${page}&size=${size}`)
}

export async function exportExecutionResults(resultId: number): Promise<ApiFileResponse> {
  return apiDownloadFile(
    `/api/v1/engine/results/${resultId}/export`,
    `personal-check-results-${resultId}.xlsx`,
  )
}

export async function fetchWorkbenchConfig(): Promise<ApiResponse<Record<string, unknown>>> {
  return apiFetch('/api/v1/workbench/config')
}

export async function saveWorkbenchConfig(
  config: Record<string, unknown>,
): Promise<ApiStatusResponse> {
  return apiFetch('/api/v1/workbench/config', {
    method: 'PUT',
    body: JSON.stringify(config),
  })
}

export async function previewWorkbenchPackageItems(
  payload: WorkbenchPackageItemsPreviewRequest,
): Promise<WorkbenchPackageItemsPreviewResponse> {
  return apiFetch<WorkbenchPackageItemsPreviewResponse>('/api/v1/workbench/package-items/preview', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function triggerWorkbenchSvnUpdate(): Promise<WorkbenchSvnUpdateResponse> {
  return apiFetch<WorkbenchSvnUpdateResponse>('/api/v1/workbench/svn-update', {
    method: 'POST',
  })
}
