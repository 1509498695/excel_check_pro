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
}

export type PlanningSnapshotApiResponse = ApiResponse<PlanningSnapshotResponse>
export type PlanningSnapshotBriefApiResponse = ApiResponse<PlanningSnapshotBriefResponse>
export type TestCaseGenerationApiResponse = ApiResponse<TestCaseGenerationResponse>
export type ReferenceCategoryListApiResponse = ApiResponse<ReferenceCategoryListResponse>
export type ReferenceCategoryApiResponse = ApiResponse<ReferenceCategoryResponse>
export type ReferenceFileListApiResponse = ApiResponse<ReferenceFileListResponse>
export type ReferenceFileApiResponse = ApiResponse<ReferenceFileResponse>
export type ReferenceDeleteApiResponse = ApiResponse<ReferenceDeleteResponse>
