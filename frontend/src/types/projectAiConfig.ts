import type { ApiResponse, ApiStatusResponse } from './api'
import type { AiProviderPreset } from './aiProvider'

export type ProjectAiProviderPreset = AiProviderPreset

export type ProjectAiTestStatus = '' | 'success' | 'failed' | string

export interface ProjectAiConfig {
  configured: boolean
  enabled: boolean
  provider: ProjectAiProviderPreset | ''
  model: string
  base_url: string
  masked_api_key: string
  has_extra_headers: boolean
  auto_match_threshold: number
  candidate_threshold: number
  max_candidates: number
  last_test_status: ProjectAiTestStatus
  last_test_at: string | null
  last_test_error_summary: string
  updated_by: number | null
  updated_at: string | null
}

export interface ProjectAiConfigPayload {
  provider: ProjectAiProviderPreset
  model: string
  base_url: string
  api_key?: string | null
  enabled: boolean
  auto_match_threshold: number
  candidate_threshold: number
  max_candidates: number
  extra_headers?: Record<string, string>
}

export type ProjectAiConfigResponse = ApiResponse<ProjectAiConfig>
export type ProjectAiConfigStatusResponse = ApiStatusResponse
