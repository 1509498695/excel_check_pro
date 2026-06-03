import type {
  FixedRulesConfig,
  FixedRulesConfigResponse,
  FixedRulesExecuteResponse,
  FixedRulesSvnUpdateResponse,
} from '../types/fixedRules'
import { apiDownloadFile, apiFetch, type ApiFileResponse } from '../utils/apiFetch'

export async function fetchFixedRulesConfig(): Promise<FixedRulesConfigResponse> {
  return apiFetch<FixedRulesConfigResponse>('/api/v1/fixed-rules/config')
}

export async function saveFixedRulesConfig(
  config: FixedRulesConfig,
): Promise<FixedRulesConfigResponse> {
  return apiFetch<FixedRulesConfigResponse>('/api/v1/fixed-rules/config', {
    method: 'PUT',
    body: JSON.stringify(config),
  })
}

export async function executeFixedRules(payload?: {
  selected_rule_ids?: string[]
  page?: number
  size?: number
}): Promise<FixedRulesExecuteResponse> {
  return apiFetch<FixedRulesExecuteResponse>('/api/v1/fixed-rules/execute', {
    method: 'POST',
    body: payload ? JSON.stringify(payload) : undefined,
  })
}

export async function fetchFixedRulesResults(
  resultId: number,
  page: number,
  size: number,
): Promise<FixedRulesExecuteResponse> {
  return apiFetch<FixedRulesExecuteResponse>(
    `/api/v1/fixed-rules/results/${resultId}?page=${page}&size=${size}`,
  )
}

export async function exportFixedRulesResults(resultId: number): Promise<ApiFileResponse> {
  return apiDownloadFile(
    `/api/v1/fixed-rules/results/${resultId}/export`,
    `project-check-results-${resultId}.xlsx`,
  )
}

export async function triggerFixedRulesSvnUpdate(): Promise<FixedRulesSvnUpdateResponse> {
  return apiFetch<FixedRulesSvnUpdateResponse>('/api/v1/fixed-rules/svn-update', {
    method: 'POST',
  })
}
