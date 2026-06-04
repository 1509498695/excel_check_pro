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
export type EventTaskValidationScope = 'all' | 'specified'
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
  loot?: string
  config_key?: string
  config_task_desc?: string
  config_task_id?: string
  config_loot?: string
  match_status?: 'matched' | 'missing_config' | 'missing_task' | 'mismatch'
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

export interface FixedRuleGroup {
  group_id: string
  group_name: string
  builtin: boolean
}

export interface FixedRuleDefinition {
  rule_id: string
  group_id: string
  rule_name: string
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
  left_package_field?: string
  left_item_field?: string
  left_count_field?: string
  right_package_field?: string
  right_items_field?: string
  package_id_filter?: string
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
