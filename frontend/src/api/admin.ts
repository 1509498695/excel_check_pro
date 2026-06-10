import type {
  FeishuBotConfig,
  FeishuBotConfigPayload,
  FeishuBotTestSendPayload,
  FeishuBotTestSendResult,
  ProjectSvnCredentialTestResult,
} from '../types/admin'
import type { ProjectDetail, ProjectMember } from '../types/auth'
import { apiFetch } from '../utils/apiFetch'

interface ListResponse<T> {
  code: number
  msg: string
  data: T[]
}

interface SingleResponse<T> {
  code: number
  msg: string
  data: T
}

export async function apiListProjects(): Promise<ListResponse<ProjectDetail>> {
  return apiFetch<ListResponse<ProjectDetail>>('/api/v1/admin/projects')
}

export async function apiCreateProject(
  name: string,
  description: string,
): Promise<SingleResponse<ProjectDetail>> {
  return apiFetch<SingleResponse<ProjectDetail>>('/api/v1/admin/projects', {
    method: 'POST',
    body: JSON.stringify({ name, description }),
  })
}

export async function apiUpdateProject(
  projectId: number,
  payload: { name?: string; description?: string },
): Promise<SingleResponse<ProjectDetail>> {
  return apiFetch<SingleResponse<ProjectDetail>>(`/api/v1/admin/projects/${projectId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export async function apiDeleteProject(projectId: number): Promise<void> {
  await apiFetch(`/api/v1/admin/projects/${projectId}`, {
    method: 'DELETE',
  })
}

export async function apiListProjectMembers(
  projectId: number,
): Promise<ListResponse<ProjectMember>> {
  return apiFetch<ListResponse<ProjectMember>>(
    `/api/v1/admin/projects/${projectId}/members`,
  )
}

export async function apiSetMemberRole(
  projectId: number,
  userId: number,
  role: string,
): Promise<{ code: number; msg: string }> {
  return apiFetch(`/api/v1/admin/projects/${projectId}/members/${userId}/role`, {
    method: 'PUT',
    body: JSON.stringify({ role }),
  })
}

export async function apiMoveMemberProject(
  projectId: number,
  userId: number,
  targetProjectId: number,
): Promise<{ code: number; msg: string }> {
  return apiFetch(`/api/v1/admin/projects/${projectId}/members/${userId}/project`, {
    method: 'PUT',
    body: JSON.stringify({ target_project_id: targetProjectId }),
  })
}

export async function apiRemoveMember(
  projectId: number,
  userId: number,
): Promise<{ code: number; msg: string }> {
  return apiFetch(`/api/v1/admin/projects/${projectId}/members/${userId}`, {
    method: 'DELETE',
  })
}

export async function apiResetUserPassword(
  userId: number,
  newPassword: string,
): Promise<{ code: number; msg: string }> {
  return apiFetch(`/api/v1/admin/users/${userId}/reset-password`, {
    method: 'POST',
    body: JSON.stringify({ new_password: newPassword }),
  })
}

export async function apiGetFeishuBotConfig(
  projectId: number,
): Promise<SingleResponse<FeishuBotConfig>> {
  return apiFetch<SingleResponse<FeishuBotConfig>>(
    `/api/v1/admin/projects/${projectId}/feishu-bot`,
  )
}

export async function apiUpsertFeishuBotConfig(
  projectId: number,
  payload: FeishuBotConfigPayload,
): Promise<SingleResponse<FeishuBotConfig>> {
  // 仅按 null 语义条件加入可选字段，避免把空串透传到后端引发 400 校验失败。
  const body: Record<string, unknown> = { app_id: payload.app_id }
  if (payload.app_secret !== undefined && payload.app_secret !== null) {
    body.app_secret = payload.app_secret
  }
  if (payload.default_chat_id !== undefined && payload.default_chat_id !== null) {
    body.default_chat_id = payload.default_chat_id
  }
  if (payload.allowed_open_ids !== undefined && payload.allowed_open_ids !== null) {
    body.allowed_open_ids = payload.allowed_open_ids
  }
  if (payload.local_download_roots !== undefined && payload.local_download_roots !== null) {
    body.local_download_roots = payload.local_download_roots
  }
  if (payload.svn_download_roots !== undefined && payload.svn_download_roots !== null) {
    body.svn_download_roots = payload.svn_download_roots
  }
  if (
    payload.allowed_download_suffixes !== undefined &&
    payload.allowed_download_suffixes !== null
  ) {
    body.allowed_download_suffixes = payload.allowed_download_suffixes
  }
  if (payload.bound_chat_ids !== undefined && payload.bound_chat_ids !== null) {
    body.bound_chat_ids = payload.bound_chat_ids
  }
  if (payload.query_roots !== undefined && payload.query_roots !== null) {
    body.query_roots = payload.query_roots
  }
  if (payload.svn_credential !== undefined && payload.svn_credential !== null) {
    body.svn_credential = payload.svn_credential
  }
  if (payload.ai_credential !== undefined && payload.ai_credential !== null) {
    body.ai_credential = payload.ai_credential
  }
  if (payload.ai_match_params !== undefined && payload.ai_match_params !== null) {
    body.ai_match_params = payload.ai_match_params
  }
  return apiFetch<SingleResponse<FeishuBotConfig>>(
    `/api/v1/admin/projects/${projectId}/feishu-bot`,
    {
      method: 'PUT',
      body: JSON.stringify(body),
    },
  )
}

export async function apiDeleteFeishuBotConfig(projectId: number): Promise<void> {
  await apiFetch(`/api/v1/admin/projects/${projectId}/feishu-bot`, {
    method: 'DELETE',
  })
}

export async function apiTestSendFeishuBot(
  projectId: number,
  payload: FeishuBotTestSendPayload,
): Promise<SingleResponse<FeishuBotTestSendResult>> {
  return apiFetch<SingleResponse<FeishuBotTestSendResult>>(
    `/api/v1/admin/projects/${projectId}/feishu-bot/test-send`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )
}

export async function apiTestProjectSvnCredential(
  projectId: number,
): Promise<SingleResponse<ProjectSvnCredentialTestResult>> {
  return apiFetch<SingleResponse<ProjectSvnCredentialTestResult>>(
    `/api/v1/admin/projects/${projectId}/svn-credential/test`,
    {
      method: 'POST',
    },
  )
}
