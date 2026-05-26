import type { ApiResponse, ExecutionResponse } from './api'
export type {
  AbnormalResult,
  ApiResponse,
  ApiStatusResponse,
  ExecutionMeta,
  ExecutionResponse,
} from './api'

export type SourceType = 'local_excel' | 'local_csv' | 'feishu' | 'svn'
export type CreatableSourceType = Exclude<SourceType, 'local_csv'>

export type ExpectedType = 'int' | 'str' | 'json'

export type RuleMode = 'static' | 'dynamic'

export type VariableKind = 'single' | 'composite'

export interface DataSource {
  id: string
  type: SourceType
  path?: string
  url?: string
  pathOrUrl?: string
  token?: string
}

export interface VariableTag {
  tag: string
  source_id: string
  sheet: string
  variable_kind?: VariableKind
  column?: string
  columns?: string[]
  key_column?: string
  append_index_to_key?: boolean
  expected_type?: ExpectedType | null
}

export interface ValidationRuleDraftState {
  paramsText?: string
}

export interface ValidationRule {
  rule_id?: string
  rule_type: string
  params: Record<string, unknown>
  mode?: RuleMode
  draftState?: ValidationRuleDraftState
}

export interface TaskTree {
  sources: DataSource[]
  variables: VariableTag[]
  rules: ValidationRule[]
  selected_rule_ids?: string[]
  page?: number
  size?: number
}

export type ExecuteResponse = ExecutionResponse

export interface WorkbenchSvnUpdateItem {
  kind?: 'working_copy' | 'remote_cache'
  working_copy: string
  source_id?: string
  source_url?: string
  status: 'success' | 'error'
  output: string
  used_executable: string
  error?: string
}

export type WorkbenchSvnUpdateResponse = ApiResponse<{
  total_paths: number
  updated_paths: number
  results: WorkbenchSvnUpdateItem[]
}>

export type SourceCapabilitiesResponse = ApiResponse<{
  source_types: SourceType[]
  implemented: boolean
}>

export type LocalPickResponse = ApiResponse<{
  selected_path: string
  source_type: Extract<SourceType, 'local_excel'>
}>

export type SourceUploadResponse = ApiResponse<{
  source_type: Extract<SourceType, 'local_excel'>
  original_filename: string
  stored_filename: string
  selected_path: string
  size: number
  project_id: number
  user_id: number
}>

export type LocalDirectoryValidateResponse = ApiResponse<{
  directory_path: string
}>

export interface SourceSheetMetadata {
  name: string
  columns: string[]
}

export interface SourceMetadata {
  source_id: string
  source_type: SourceType
  sheets: SourceSheetMetadata[]
  authorization_status?: string
}

export type SourceMetadataResponse = ApiResponse<SourceMetadata>

export type FeishuAuthorizationStatus =
  | 'authorized'
  | 'pending_authorization'
  | 'authorization_sent'
  | 'authorization_success'
  | 'authorization_failed'
  | 'invalid_url'
  | 'app_permission_missing'
  | 'document_permission_denied'
  | 'not_found'
  | 'bot_not_configured'
  | 'callback_not_configured'
  | 'send_failed'

export interface FeishuSourceAuthorizationRequest {
  source_id: string
  sheet_url: string
}

export interface FeishuSourceAuthorizationData {
  status: FeishuAuthorizationStatus
  message?: string
  error_status?: FeishuAuthorizationStatus
  spreadsheet_token?: string
  sheet_url?: string
  title?: string
  reused_authorization?: boolean
  expires_at?: string
  chat_id?: string
  message_id?: string
}

export type FeishuPermissionCheckResponse = ApiResponse<FeishuSourceAuthorizationData>
export type FeishuSendAuthorizationCardResponse = ApiResponse<FeishuSourceAuthorizationData>

export interface ColumnPreviewRow {
  row_index: number
  value: unknown
}

export interface SingleVariablePreviewData {
  variable_kind: 'single'
  source_id: string
  source_type: SourceType
  source_path?: string
  sheet: string
  column: string
  preview_rows: ColumnPreviewRow[]
  total_rows: number
  loaded_rows?: number
  loaded_all_rows?: boolean
  preview_limit: number
}

export interface CompositeVariablePreviewData {
  variable_kind: 'composite'
  source_id: string
  source_type: SourceType
  source_path?: string
  sheet: string
  columns: string[]
  key_column: string
  has_duplicate_keys: boolean
  duplicate_keys_preview?: string[]
  mapping: Record<string, Record<string, unknown>>
  total_rows: number
  loaded_rows?: number
  loaded_all_rows?: boolean
}

export type VariablePreviewData = SingleVariablePreviewData | CompositeVariablePreviewData

export interface ColumnPreviewRequest {
  source: DataSource
  sheet: string
  column: string
  limit?: number
}

export interface CompositePreviewRequest {
  source: DataSource
  sheet: string
  columns: string[]
  key_column: string
  append_index_to_key?: boolean
}

export type ColumnPreviewResponse = ApiResponse<SingleVariablePreviewData>

export type CompositePreviewResponse = ApiResponse<CompositeVariablePreviewData>
