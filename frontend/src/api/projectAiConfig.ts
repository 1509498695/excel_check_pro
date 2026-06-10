import type {
  ProjectAiConfigPayload,
  ProjectAiConfigResponse,
} from '../types/projectAiConfig'
import { apiFetch } from '../utils/apiFetch'

function projectAiConfigPath(projectId: number): string {
  return `/api/v1/admin/projects/${projectId}/ai-config`
}

export async function apiGetProjectAiConfig(
  projectId: number,
): Promise<ProjectAiConfigResponse> {
  return apiFetch<ProjectAiConfigResponse>(projectAiConfigPath(projectId))
}

export async function apiSaveProjectAiConfig(
  projectId: number,
  payload: ProjectAiConfigPayload,
): Promise<ProjectAiConfigResponse> {
  const body: Record<string, unknown> = {
    provider: payload.provider,
    model: payload.model,
    base_url: payload.base_url,
  }
  if (payload.api_key) {
    body.api_key = payload.api_key
  }
  body.enabled = payload.enabled
  body.auto_match_threshold = payload.auto_match_threshold
  body.candidate_threshold = payload.candidate_threshold
  body.max_candidates = payload.max_candidates
  if (payload.extra_headers) {
    body.extra_headers = payload.extra_headers
  }
  return apiFetch<ProjectAiConfigResponse>(projectAiConfigPath(projectId), {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export async function apiDeleteProjectAiConfig(projectId: number): Promise<void> {
  await apiFetch(projectAiConfigPath(projectId), {
    method: 'DELETE',
  })
}

export async function apiTestProjectAiConfig(
  projectId: number,
): Promise<ProjectAiConfigResponse> {
  return apiFetch<ProjectAiConfigResponse>(`${projectAiConfigPath(projectId)}/test`, {
    method: 'POST',
  })
}
