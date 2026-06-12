import type { ApiResponse } from './api'

export const RULE_FAMILY_CONFIG_LOOKUP = 'config_lookup'

export type RuleFamily = typeof RULE_FAMILY_CONFIG_LOOKUP
export type RuleConfigStatus = 'empty' | 'draft' | 'published' | string
export type RuleConfigVersionStatus = 'draft' | 'published' | 'archived' | string
export type RuleConfigVersionAction = 'save_draft' | 'publish' | 'rollback' | string
export type RuleConfigTrialStatus = 'hit' | 'candidates' | 'not_found' | 'ai_unavailable' | string

export interface RuleConfigSummaryPage {
  query_type: string
  names: string[]
}

export interface RuleConfigSummaryReference {
  query_type: string
  name: string
  file: string
  page: string
}

export interface RuleConfigSummary {
  query_count: number
  query_types: string[]
  query_roots: string[]
  primary_files: string[]
  pages: RuleConfigSummaryPage[]
  references: RuleConfigSummaryReference[]
}

export interface RuleConfigValidationResult {
  ok: boolean
  parsed_config_json: Record<string, unknown>
  errors: string[]
  summary: RuleConfigSummary
}

export interface RuleConfigRecord {
  id: number
  rule_id: number
  project_id: number
  rule_family: RuleFamily | string
  query_type: string
  content_md: string
  parsed_config_json: Record<string, unknown>
  status: RuleConfigStatus
  draft_version: number
  published_version: number | null
  created_by: number | null
  updated_by: number | null
  published_by: number | null
  published_at: string | null
  optimistic_lock_version: number
  created_at: string | null
  updated_at: string | null
  validation?: RuleConfigValidationResult
}

export interface RuleConfigVersion {
  id: number
  rule_config_id: number
  rule_id: number
  project_id: number
  rule_family: RuleFamily | string
  query_type: string
  version: number
  content_md: string
  parsed_config_json: Record<string, unknown>
  status: RuleConfigVersionStatus
  action: RuleConfigVersionAction
  operator: number | null
  description: string
  created_at: string | null
}

export interface RuleConfigVersionsData {
  items: RuleConfigVersion[]
  total: number
}

export interface RuleConfigListData {
  items: RuleConfigRecord[]
  total: number
}

export interface RuleConfigCredentialStatusItem {
  configured: boolean
  account_masked?: string
  enabled?: boolean
  provider?: string
  base_url?: string
  model?: string
  credential_masked?: string
  masked_api_key?: string
  last_test_status?: string
  last_test_at?: string | null
  updated_at: string | null
}

export interface RuleConfigCredentialsStatus {
  svn: RuleConfigCredentialStatusItem
  ai: RuleConfigCredentialStatusItem
}

export type RuleConfigRecordResponse = ApiResponse<RuleConfigRecord>
export type RuleConfigListResponse = ApiResponse<RuleConfigListData>
export type RuleConfigVersionsResponse = ApiResponse<RuleConfigVersionsData>
export type RuleConfigValidationResponse = ApiResponse<RuleConfigValidationResult>
export type RuleConfigCredentialsStatusResponse = ApiResponse<RuleConfigCredentialsStatus>
export type RuleConfigTrialResponse = ApiResponse<RuleConfigTrialResult>

export interface RuleConfigCreateRequest {
  contentMd: string
  description?: string
}

export interface RuleConfigMutationRequest {
  contentMd: string
  baseVersion: number
  description?: string
}

export interface RuleConfigRollbackRequest {
  baseVersion: number
  description?: string
}

export interface RuleConfigTrialRequest {
  queryType: string
  versionedConfigFolder: string
  lookupInput: string
  useCurrentDraft: boolean
  contentMd?: string
}

export interface RuleConfigTrialField {
  field: string
  label: string
  value: string
}

export interface RuleConfigTrialResultItem {
  query_type: string
  page: string
  id_value: string
  name_value: string
  fields: RuleConfigTrialField[]
  warnings: string[]
}

export interface RuleConfigTrialCandidate {
  key: string
  page: string
  id_value: string
  name_value: string
  score: number
}

export interface RuleConfigTrialAiInfo {
  used: boolean
  unavailable_reason?: string | null
  thresholds: {
    auto_match_threshold: number
    candidate_threshold: number
    max_candidates: number
  }
}

export interface RuleConfigTrialResult {
  status: RuleConfigTrialStatus
  message: string
  results: RuleConfigTrialResultItem[]
  candidates: RuleConfigTrialCandidate[]
  ai: RuleConfigTrialAiInfo
  validation?: RuleConfigValidationResult
}

export interface RuleConfigVersionConflictDetail {
  code: 'RULE_CONFIG_VERSION_CONFLICT'
  current_optimistic_lock_version: number
}

export interface RuleConfigValidationFailureDetail {
  code: 'RULE_CONFIG_VALIDATION_FAILED'
  msg?: string
  errors: string[]
  summary?: Partial<RuleConfigSummary>
}

export type RuleConfigApiErrorDetail =
  | RuleConfigVersionConflictDetail
  | RuleConfigValidationFailureDetail
  | Record<string, unknown>
  | string
  | unknown
