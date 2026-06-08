import type { ApiResponse, ExecutionResponse } from './api'
import type { DataSource, VariableTag } from './workbench'

export type FixedRuleOperator = 'eq' | 'ne' | 'gt' | 'lt'
export type CompositeFilterOperator = FixedRuleOperator | 'not_null' | 'contains' | 'not_contains'
export type CompositeAssertionOperator =
  | FixedRuleOperator
  | 'not_null'
  | 'regex'
  | 'unique'
  | 'duplicate_required'
export type CompositeConditionOperator = CompositeFilterOperator | CompositeAssertionOperator
export type PipelineAssertionOperator =
  | FixedRuleOperator
  | 'not_null'
  | 'regex'
  | 'unique'
  | 'duplicate_required'
export type CompositeValueSource = 'literal' | 'field'
export type ExpectedValueMode = 'single' | 'set'
export type DualCompositeKeyCheckMode = 'baseline_only' | 'bidirectional'
export type PackageParseStrategy = 'auto' | 'rule' | 'ai'
export type PackageAiParseMode = 'auto' | 'enabled' | 'disabled'
export type PackageItemsValidationScope = 'all' | 'specified'
export type EventTaskParseStrategy = 'group_desc'
export type EventTaskAiParseMode = 'auto' | 'enabled' | 'disabled'
export type EventTaskAiAssistMode = 'auto' | 'on' | 'off'
export type EventTaskValidationScope = 'all' | 'specified'
export type EventTaskRewardMatchStrategy =
  | 'groupId_desc'
  | 'groupId_taskId'
  | 'groupId_desc_then_taskId'
export type EventTaskAiSuggestionType =
  | 'field_mapping_suggestion'
  | 'match_suggestion'
  | 'error_explanation'
export type FixedRuleType =
  | 'fixed_value_compare'
  | 'regex_check'
  | 'not_null'
  | 'unique'
  | 'sequence_order_check'
  | 'cross_table_mapping'
  | 'composite_condition_check'
  | 'dual_composite_compare'
  | 'multi_composite_pipeline_check'
  | 'multi_composite_mapping_check'
  | 'package_items_compare'
  | 'event_task_reward'
  | 'event_task_validation'
export type FixedRuleSelection =
  | FixedRuleOperator
  | 'regex_check'
  | 'not_null'
  | 'unique'
  | 'sequence_order_check'
  | 'in'
  | 'composite_condition_check'
  | 'dual_composite_compare'
  | 'multi_composite_pipeline_check'
  | 'multi_composite_mapping_check'
export type SequenceDirection = 'asc' | 'desc'
export type SequenceStartMode = 'auto' | 'manual'

export interface CompositeCondition {
  condition_id: string
  field: string
  operator: CompositeConditionOperator
  value_source?: CompositeValueSource
  expected_value?: string
  expected_value_mode?: ExpectedValueMode
  expected_field?: string
}

export interface CompositeBranch {
  branch_id: string
  filters: CompositeCondition[]
  assertions: CompositeCondition[]
}

export interface CompositeRuleConfig {
  global_filters: CompositeCondition[]
  branches: CompositeBranch[]
}

export interface DualCompositeComparison {
  comparison_id: string
  left_field: string
  operator: FixedRuleOperator | 'not_null'
  right_field: string
}

export interface MultiCompositePipelineNode {
  node_id: string
  variable_tag: string
  display_field?: string
  filters: CompositeCondition[]
  assertions: CompositeCondition[]
}

export interface MultiCompositePipelineConfig {
  nodes: MultiCompositePipelineNode[]
}

export interface MultiCompositeMappingRange {
  range_id: string
  start_row: number
  end_row: number
  expected_value: string
}

export interface MultiCompositeMappingFieldCheck {
  check_id: string
  field: string
  default_expected_value: string
  filters: CompositeCondition[]
  ranges: MultiCompositeMappingRange[]
}

export interface MultiCompositeMappingExclusionRange {
  range_id: string
  start_row: number
  end_row: number
  expected_value?: string
}

export interface MultiCompositeMappingFilter extends CompositeCondition {
  exclusion_ranges: MultiCompositeMappingExclusionRange[]
}

export interface MultiCompositeMappingNode {
  node_id: string
  variable_tag: string
  display_field?: string
  filters: MultiCompositeMappingFilter[]
  field_checks?: MultiCompositeMappingFieldCheck[]
  field?: string
  ranges?: MultiCompositeMappingRange[]
}

export interface MultiCompositeMappingConfig {
  nodes: MultiCompositeMappingNode[]
}

export interface PackageItemsFieldMapping {
  package_id?: string
  item_id?: string
  count?: string
  package_id_column?: string | null
  item_id_column?: string | null
  count_column?: string | null
  header_row_index?: number | null
  detail_start_row_index?: number | null
  detail_end_row_index?: number | null
}

export interface PackageItemsParseConfig {
  feishu_source_id?: string
  feishu_sheet_id?: string
  feishu_sheet_name?: string
  parse_strategy?: PackageParseStrategy
  ai_parse_mode?: PackageAiParseMode
  validation_scope?: PackageItemsValidationScope
  package_id_filter?: string
}

export interface PackageItemsPreviewRow {
  row_index: number
  package_id: string
  item_id: string
  count: string
}

export interface EventTaskPreviewRow {
  row_index: number
  task_group_id: string
  task_desc: string
  task_id?: string
  day?: number | null
  loot?: string
  rewards?: EventTaskPreviewReward[]
  warnings?: string[]
  config_key?: string
  config_task_desc?: string
  config_task_id?: string
  config_loot?: string
  match_type?: string | null
  match_status?: 'matched' | 'missing_config' | 'missing_task' | 'mismatch'
}

export interface EventTaskPreviewReward {
  type: string
  item_id: number
  itemId: number
  count: number
  name?: string | null
}

export interface EventTaskPreviewSampleRow {
  rowIndex: number
  taskGroupId: string
  taskId?: string | null
  day?: number | null
  desc: string
  rewards: EventTaskPreviewReward[]
  rawLoot?: string | null
  warnings: string[]
}

export interface EventTaskLootFieldMapping {
  item_id: string
  count: string
  name?: string | null
  value_type?: string | null
}

export interface EventTaskFieldMapping {
  header_row_index?: number | null
  task_group_id?: string | null
  task_id?: string | null
  day?: string | null
  task_desc?: string | null
  loot?: string | null
  loot_groups?: EventTaskLootFieldMapping[]
}

export interface EventTaskAiSuggestion {
  type: EventTaskAiSuggestionType
  confidence: number
  suggestions: Array<Record<string, unknown>>
  reason: string
  requiresUserConfirm: boolean
  requires_user_confirm: boolean
}

export interface EventTaskParseConfig {
  feishu_source_id?: string
  feishu_sheet_id?: string
  feishu_sheet_name?: string
  config_variable_tag?: string
  parse_strategy?: EventTaskParseStrategy
  ai_parse_mode?: EventTaskAiParseMode
  validation_scope?: EventTaskValidationScope
  task_group_id_filter?: string
  key_delimiter?: string
  fallback_match_field?: string
  event_task_field_mapping?: EventTaskFieldMapping | null
}

export interface RewardValidationItem {
  type?: string | null
  item_id: number
  itemId: number
  count: number
  name?: string | null
  source?: string | null
}

export interface RewardCountMismatchData {
  item_id: number
  itemId: number
  expected_count: number
  expectedCount: number
  actual_count: number
  actualCount: number
}

export interface EventTaskRewardValidationResult {
  taskGroupId: string
  task_group_id: string
  taskDesc: string
  task_desc: string
  feishuRowIndex?: number | null
  feishu_row_index?: number | null
  variableKey?: string | null
  variable_key?: string | null
  variableTaskId?: string | null
  variable_task_id?: string | null
  matchStrategy: EventTaskRewardMatchStrategy | string
  match_strategy: EventTaskRewardMatchStrategy | string
  status: 'pass' | 'fail'
  expectedRewards: RewardValidationItem[]
  expected_rewards: RewardValidationItem[]
  actualRewards: RewardValidationItem[]
  actual_rewards: RewardValidationItem[]
  missingRewards: RewardValidationItem[]
  missing_rewards: RewardValidationItem[]
  extraRewards: RewardValidationItem[]
  extra_rewards: RewardValidationItem[]
  countMismatches: RewardCountMismatchData[]
  count_mismatches: RewardCountMismatchData[]
  duplicateWarnings: string[]
  duplicate_warnings: string[]
  parseWarnings: string[]
  parse_warnings: string[]
  errorMessage?: string | null
  error_message?: string | null
}

export interface EventTaskExtraVariableTask {
  taskGroupId: string
  task_group_id: string
  taskDesc: string
  task_desc: string
  variableKey: string
  variable_key: string
  variableTaskId?: string | null
  variable_task_id?: string | null
  actualRewards: RewardValidationItem[]
  actual_rewards: RewardValidationItem[]
  parseWarnings: string[]
  parse_warnings: string[]
}

export interface WorkbenchPackageItemsPreviewRequest {
  feishu_source_id: string
  feishu_sheet_id: string
  feishu_sheet_name?: string | null
  parse_strategy: PackageParseStrategy
  ai_parse_mode: PackageAiParseMode
  validation_scope: PackageItemsValidationScope
  package_id_filter?: string | null
}

export interface WorkbenchPackageItemsPreviewData {
  success: boolean
  message: string
  warnings: string[]
  errors: string[]
  field_mapping?: PackageItemsFieldMapping | null
  package_ids: string[]
  detail_row_count: number
  preview_rows: PackageItemsPreviewRow[]
  raw_sheet_name?: string | null
  parse_strategy_used?: 'manual' | 'ai' | null
  ai_used: boolean
}

export type WorkbenchPackageItemsPreviewResponse =
  ApiResponse<WorkbenchPackageItemsPreviewData>

export interface WorkbenchEventTaskPreviewRequest {
  feishu_source_id: string
  feishu_sheet_id: string
  feishu_sheet_name?: string | null
  config_variable_tag?: string | null
  parse_strategy: EventTaskParseStrategy
  ai_parse_mode: EventTaskAiParseMode
  ai_assist_mode?: EventTaskAiAssistMode
  validation_scope: EventTaskValidationScope
  task_group_id_filter?: string | null
  key_delimiter?: string | null
  fallback_match_field?: string | null
  event_task_field_mapping?: EventTaskFieldMapping | null
}

export interface WorkbenchEventTaskPreviewData {
  success: boolean
  message: string
  warnings: string[]
  errors: string[]
  taskGroupIds: string[]
  task_group_ids: string[]
  totalRows: number
  total_rows: number
  parsedRows: number
  parsed_rows: number
  detail_row_count: number
  rewardGroupCount: number
  reward_group_count: number
  sampleRows: EventTaskPreviewSampleRow[]
  preview_rows: EventTaskPreviewRow[]
  rawSheetName?: string | null
  raw_sheet_name?: string | null
  parse_strategy_used?: 'manual' | null
  ai_used: boolean
  aiSuggestions?: EventTaskAiSuggestion[]
  ai_suggestions?: EventTaskAiSuggestion[]
  aiSuggestionWarnings?: string[]
  ai_suggestion_warnings?: string[]
  aiSuggestionUsed?: boolean
  ai_suggestion_used?: boolean
}

export type WorkbenchEventTaskPreviewResponse =
  ApiResponse<WorkbenchEventTaskPreviewData>

export interface WorkbenchEventTaskValidationRequest {
  feishu_source_id: string
  feishu_sheet_id: string
  feishu_sheet_name?: string | null
  config_variable_tag: string
  match_strategy: EventTaskRewardMatchStrategy
  ai_assist_mode: EventTaskAiAssistMode
  validation_scope: EventTaskValidationScope
  task_group_id_filter?: string | null
  parse_strategy?: EventTaskParseStrategy
  ai_parse_mode?: EventTaskAiParseMode
  key_delimiter?: string | null
  fallback_match_field?: string | null
  event_task_field_mapping?: EventTaskFieldMapping | null
}

export interface WorkbenchEventTaskValidationData {
  success: boolean
  message: string
  warnings: string[]
  errors: string[]
  total: number
  passCount: number
  pass_count: number
  failCount: number
  fail_count: number
  unmatchedCount: number
  unmatched_count: number
  warningCount: number
  warning_count: number
  results: EventTaskRewardValidationResult[]
  extraVariableTasks: EventTaskExtraVariableTask[]
  extra_variable_tasks: EventTaskExtraVariableTask[]
  rawSheetName?: string | null
  raw_sheet_name?: string | null
  aiSuggestions?: EventTaskAiSuggestion[]
  ai_suggestions?: EventTaskAiSuggestion[]
  aiSuggestionWarnings?: string[]
  ai_suggestion_warnings?: string[]
  aiSuggestionUsed?: boolean
  ai_suggestion_used?: boolean
}

export type WorkbenchEventTaskValidationResponse =
  ApiResponse<WorkbenchEventTaskValidationData>

export interface WorkbenchEventTaskAiSuggestionRequest
  extends WorkbenchEventTaskValidationRequest {
  analysis_context?: 'preview' | 'validation'
}

export interface WorkbenchEventTaskAiSuggestionData {
  success: boolean
  message: string
  aiSuggestions: EventTaskAiSuggestion[]
  ai_suggestions: EventTaskAiSuggestion[]
  aiSuggestionWarnings: string[]
  ai_suggestion_warnings: string[]
  aiSuggestionUsed: boolean
  ai_suggestion_used: boolean
}

export type WorkbenchEventTaskAiSuggestionResponse =
  ApiResponse<WorkbenchEventTaskAiSuggestionData>

export interface FixedRuleGroup {
  group_id: string
  group_name: string
  builtin: boolean
}

export interface FixedRuleDefinition {
  rule_id: string
  group_id: string
  rule_name: string
  enabled?: boolean
  description?: string
  target_variable_tag: string
  display_field?: string
  rule_type: FixedRuleType
  operator?: FixedRuleOperator
  expected_value?: string
  expected_value_mode?: ExpectedValueMode
  reference_variable_tag?: string
  sequence_direction?: SequenceDirection
  sequence_step?: string
  sequence_start_mode?: SequenceStartMode
  sequence_start_value?: string
  composite_config?: CompositeRuleConfig
  key_check_mode?: DualCompositeKeyCheckMode
  left_key_field?: string
  right_key_field?: string
  comparisons?: DualCompositeComparison[]
  left_filters?: CompositeCondition[]
  right_filters?: CompositeCondition[]
  pipeline_config?: MultiCompositePipelineConfig
  mapping_config?: MultiCompositeMappingConfig
  package_parse_config?: PackageItemsParseConfig
  event_task_parse_config?: EventTaskParseConfig
  left_package_field?: string
  left_item_field?: string
  left_count_field?: string
  right_package_field?: string
  right_items_field?: string
  package_id_filter?: string
  left_task_group_field?: string
  left_task_id_field?: string
  left_task_desc_field?: string
  left_task_loot_field?: string
  right_task_group_field?: string
  right_task_id_field?: string
  right_task_desc_field?: string
  right_task_loot_field?: string
  event_task_match_strategy?: EventTaskRewardMatchStrategy
  ai_assist_mode?: EventTaskAiAssistMode
  task_group_id_filter?: string
}

export interface FixedRulesConfig {
  version: number
  configured: boolean
  sources: DataSource[]
  variables: VariableTag[]
  groups: FixedRuleGroup[]
  rules: FixedRuleDefinition[]
  local_path_replacement_presets: string[]
  selected_local_path_replacement_preset?: string | null
  svn_path_replacement_presets: string[]
  selected_svn_path_replacement_preset?: string | null
  path_replacement_presets?: string[]
  selected_path_replacement_preset?: string | null
}

export interface FixedRulesConfigIssue {
  level: 'warning' | 'error'
  source_id?: string | null
  variable_tag?: string | null
  rule_id?: string | null
  message: string
}

export type FixedRulesConfigResponse = ApiResponse<
  FixedRulesConfig,
  {
    config_issues?: FixedRulesConfigIssue[]
  }
>

export type FixedRulesExecuteResponse = ExecutionResponse

export interface FixedRulesSvnUpdateItem {
  working_copy: string
  status: 'success' | 'error'
  output: string
  used_executable: string
  error?: string
}

export type FixedRulesSvnUpdateResponse = ApiResponse<{
  total_paths: number
  updated_paths: number
  results: FixedRulesSvnUpdateItem[]
}>
