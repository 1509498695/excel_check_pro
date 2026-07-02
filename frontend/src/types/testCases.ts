import type { ApiResponse } from './api'
import type { DataSource } from './workbench'

export type PlanningSnapshotSourceType = 'feishu' | 'uploaded_excel'
export type GenerationWarningLevel = 'info' | 'warning' | 'error'

export interface GenerationWarning {
  source: string
  level: GenerationWarningLevel
  message: string
}

export interface PlanningSnapshotLimits {
  max_chars?: number
  max_rows?: number
  max_columns?: number
  max_cell_chars?: number
  max_non_empty_cells?: number
}

export interface PlanningSnapshotCell {
  row_index: number
  column_index: number
  column_name?: string | null
  value: string
  truncated?: boolean
}

export interface PlanningSnapshotRow {
  row_index: number
  cells: PlanningSnapshotCell[]
}

export interface PlanningSnapshotRequest {
  source_type: PlanningSnapshotSourceType
  source: DataSource
  sheet_name: string
  limits?: PlanningSnapshotLimits
}

export interface PlanningSnapshotResponse {
  source_summary: string
  sheet_name: string
  rows: PlanningSnapshotRow[]
  columns: string[]
  non_empty_cell_count: number
  truncated: boolean
  warnings: GenerationWarning[]
}

export interface PlanningSnapshotBriefRequest {
  planning_snapshot: PlanningSnapshotResponse
}

export interface PlanningSnapshotBriefResponse {
  brief_markdown: string
  warnings: GenerationWarning[]
}

export type SourceEvidenceSourceType = 'feishu' | 'local_file' | 'svn_file'

export interface SourceEvidenceRunCreateRequest {
  source_type: 'feishu' | 'svn_file'
  source_url: string
}

export interface SourceEvidenceRunResponse {
  id: number
  status: string
  source_type: SourceEvidenceSourceType | string
  source_summary: string
  source_title: string
  source_identifier?: string
  created_at?: string | null
  expires_at?: string | null
  warnings: GenerationWarning[]
  resource_count: number
}

export interface SourceEvidenceCapabilityItem {
  key: string
  label: string
  configured: boolean
  available: boolean
  status: string
  message: string
  action: string
  level: GenerationWarningLevel
}

export interface SourceEvidenceCapabilityStatusResponse {
  svn_credential_configured: boolean
  source_evidence_svn_roots_configured: boolean
  vision_ai_configured: boolean
  soffice_configured: boolean
  soffice_available: boolean
  is_project_admin: boolean
  items: SourceEvidenceCapabilityItem[]
  warnings: GenerationWarning[]
  admin_details?: Record<string, unknown>
}

export type SourceEvidenceAuthorizationRequestStatus =
  | 'authorization_sent'
  | 'already_sent'
  | 'already_authorized'
  | 'already_readable'
  | 'send_failed'
  | 'bot_not_configured'
  | 'invalid_run_state'
  | 'expired_or_cleaned'

export type SourceEvidenceAuthorizationTargetMode =
  | 'owner_direct'
  | 'creator_direct'
  | 'default_chat'
  | 'not_sent'

export interface SourceEvidenceAuthorizationRequestResponse {
  status: SourceEvidenceAuthorizationRequestStatus
  message: string
  authorization_id?: number | null
  target_mode: SourceEvidenceAuthorizationTargetMode
  sent_targets_count: number
  failed_targets_count: number
  fallback_to_default_chat: boolean
  owner_candidates_truncated: boolean
  expires_at?: string | null
  can_retry_read: boolean
}

export interface SourceEvidenceResourceResponse {
  id: number
  ref: string
  type: string
  position: string
  filename: string
  download_status: string
  adoption_status: string
  mime_type: string
}

export interface SourceEvidenceResourceListResponse {
  items: SourceEvidenceResourceResponse[]
  run_status?: string | null
  warnings?: GenerationWarning[]
}

export interface SourceEvidenceVisualCandidateResponse {
  ref: string
  type: string
  position: string
  filename: string
  status: string
  selectable: boolean
  recommended: boolean
  selected: boolean
  recommendation_reasons: string[]
  download_status: string
  adoption_status: string
  dimensions: Record<string, number>
}

export interface SourceEvidenceVisualCandidatesResponse {
  items: SourceEvidenceVisualCandidateResponse[]
  recommended_refs: string[]
  selected_refs: string[]
  warnings: GenerationWarning[]
  run_status?: string | null
}

export interface SourceEvidenceVisualSelectionRequest {
  selected_refs: string[]
}

export interface SourceEvidenceObservationResponse {
  id: number
  ref: string
  resource_id?: number | null
  type: string
  position: string
  filename: string
  status: string
  summary: string
  visible_text: string
  confidence?: number | null
  limitations: string[]
  source: Record<string, unknown>
  created_by?: number | null
  created_at?: string | null
  adopted_by?: number | null
  adopted_at?: string | null
  revoked_at?: string | null
}

export interface SourceEvidenceObservationListResponse {
  items: SourceEvidenceObservationResponse[]
  warnings: GenerationWarning[]
  run_status?: string | null
}

export interface SourceEvidenceAdoptVisualEvidenceRequest {
  observation_ids: number[]
}

export interface SourceEvidenceCleanupAuditResource {
  resource_id?: number | null
  run_id?: number | null
  project_id?: number | null
  ref: string
  type: string
  filename: string
  status: string
  download_status: string
  created_at?: string | null
  cleaned_at?: string | null
}

export interface SourceEvidenceCleanupAuditItem {
  run_id: number
  project_id: number
  source_type: string
  source_identifier: string
  source_title: string
  status_before: string
  status_after: string
  created_by?: number | null
  cleaned_by?: number | null
  created_at?: string | null
  expires_at?: string | null
  cleaned_at?: string | null
  error_summary: string
  counts: Record<string, number>
  resources: SourceEvidenceCleanupAuditResource[]
}

export interface SourceEvidenceCleanupAuditListResponse {
  items: SourceEvidenceCleanupAuditItem[]
  total: number
  limit: number
  offset: number
}

export type BlueprintItem = string | Record<string, unknown>

export interface TestCaseBlueprint {
  modules: BlueprintItem[]
  flows: BlueprintItem[]
  requirement_traces?: Record<string, unknown>[]
  coverage_dimensions?: BlueprintItem[]
  risks?: BlueprintItem[]
  unmapped_requirements?: BlueprintItem[]
  unsupported_or_unfounded_test_points?: BlueprintItem[]
  open_questions?: BlueprintItem[]
  warnings: GenerationWarning[]
}

export interface GeneratedTestCase {
  case_id: string
  module: string
  feature: string
  scenario: string
  title: string
  preconditions: string
  steps: string
  expected_results: string
  priority: string
  case_type: string
  source_requirement: string
  config_source: string
  planning_answer: string
  initial_status: string
  bug_link: string
  remarks: string
}

export interface GeneratedCaseStats {
  total: number
  priority_counts: Record<string, number>
  module_counts: Record<string, number>
  case_type_counts: Record<string, number>
  warning_count: number
}

export interface RequirementTrace {
  source_row_index?: number | null
  source_fragment: string
  blueprint_node: string
  case_id: string
}

export interface QaCaseMethodContext {
  method_name: string
  method_version: string
  knowledge_library_note: string
  dimensions: string[]
}

export interface ReferenceProfileColumn {
  index: number
  original_name: string
  standard_field?: string | null
  standard_label?: string | null
}

export interface ReferenceSheetOption {
  name: string
  reference_case_count: number
  is_default: boolean
  header_row_index: number
  columns: ReferenceProfileColumn[]
  warnings: GenerationWarning[]
}

export interface ReferenceProfile {
  source_type: 'excel' | 'markdown' | 'text'
  source_name: string
  default_sheet_name?: string | null
  reference_case_count?: number | null
  columns: ReferenceProfileColumn[]
  sheet_options: ReferenceSheetOption[]
  warnings: GenerationWarning[]
}

export interface PrimaryReferenceProfile extends ReferenceProfile {
  selected_sheet_name?: string | null
  reference_id?: number
  original_filename?: string
  recognized_fields?: string[]
}

export interface ReferenceCategoryCreateRequest {
  name: string
}

export interface ReferenceCategoryUpdateRequest {
  name: string
}

export interface ReferenceCategoryResponse {
  id: number
  name: string
  reference_count: number
}

export interface ReferenceFileResponse {
  id: number
  category_id?: number | null
  category_name: string
  original_filename: string
  suffix: string
  size_bytes: number
  profile?: ReferenceProfile | null
  reference_case_count?: number | null
  default_sheet_name?: string | null
  is_recommended_primary: boolean
  created_at: string
  updated_at: string
}

export interface ReferenceCategoryListResponse {
  items: ReferenceCategoryResponse[]
}

export interface ReferenceFileListResponse {
  items: ReferenceFileResponse[]
}

export interface ReferenceDeleteResponse {
  id: number
  deleted: boolean
}

export interface TestCaseGenerationRequest {
  planning_snapshot: PlanningSnapshotResponse
  source_evidence_run_id?: number | null
  adopted_visual_evidence_ids?: number[]
  snapshot_brief_markdown?: string
  reference_ids: number[]
  primary_reference_id?: number | null
  primary_reference_sheet_name?: string | null
  generation_options?: Record<string, unknown>
}

export interface TestCaseGenerationResponse {
  blueprint: TestCaseBlueprint
  cases: GeneratedTestCase[]
  warnings: GenerationWarning[]
  stats: GeneratedCaseStats
  export_columns: string[]
  requirement_trace: RequirementTrace[]
  method_context: QaCaseMethodContext
  primary_reference_profile?: PrimaryReferenceProfile | null
  reference_context: Record<string, unknown>
}

export interface TestCaseExportRequest {
  blueprint: TestCaseBlueprint
  cases: GeneratedTestCase[]
  warnings: GenerationWarning[]
  stats: GeneratedCaseStats
  export_columns: string[]
  primary_reference_profile?: PrimaryReferenceProfile | null
  source_summary: string
  source_evidence_run_id?: number | null
  adopted_visual_evidence_ids?: number[]
  source_evidence_summary?: string
  evidence_summary?: string
}

export type PlanningSnapshotApiResponse = ApiResponse<PlanningSnapshotResponse>
export type PlanningSnapshotBriefApiResponse = ApiResponse<PlanningSnapshotBriefResponse>
export type SourceEvidenceRunApiResponse = ApiResponse<SourceEvidenceRunResponse>
export type SourceEvidenceCapabilityStatusApiResponse = ApiResponse<SourceEvidenceCapabilityStatusResponse>
export type SourceEvidenceAuthorizationRequestApiResponse = ApiResponse<SourceEvidenceAuthorizationRequestResponse>
export type SourceEvidenceResourceListApiResponse = ApiResponse<SourceEvidenceResourceListResponse>
export type SourceEvidenceVisualCandidatesApiResponse = ApiResponse<SourceEvidenceVisualCandidatesResponse>
export type SourceEvidenceObservationListApiResponse = ApiResponse<SourceEvidenceObservationListResponse>
export type SourceEvidenceCleanupAuditListApiResponse = ApiResponse<SourceEvidenceCleanupAuditListResponse>
export type TestCaseGenerationApiResponse = ApiResponse<TestCaseGenerationResponse>
export type ReferenceCategoryListApiResponse = ApiResponse<ReferenceCategoryListResponse>
export type ReferenceCategoryApiResponse = ApiResponse<ReferenceCategoryResponse>
export type ReferenceFileListApiResponse = ApiResponse<ReferenceFileListResponse>
export type ReferenceFileApiResponse = ApiResponse<ReferenceFileResponse>
export type ReferenceDeleteApiResponse = ApiResponse<ReferenceDeleteResponse>
