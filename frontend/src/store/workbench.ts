import { defineStore } from 'pinia'

import {
  executeTaskTree,
  exportExecutionResults,
  fetchColumnPreview,
  fetchCompositePreview,
  fetchExecutionResults,
  fetchSourceCapabilities,
  fetchSourceMetadata,
  triggerWorkbenchSvnUpdate,
} from '../api/workbench'
import type { SourceMetadataFetchOptions } from '../api/workbench'
import type { FixedRuleDefinition, FixedRuleGroup } from '../types/fixedRules'
import type {
  DataSource,
  SourceMetadata,
  TaskTree,
  ValidationRule,
  VariablePreviewData,
  VariableTag,
} from '../types/workbench'
import {
  collectCompositeAvailableFields,
  createWorkbenchDemoRules,
  normalizeDualCompositeFilters,
  resolveFieldAgainstAvailable,
} from './workbench/rules'
import {
  buildWorkbenchTaskTreePayload,
  selectAllRuleGroups,
  selectCanExecuteOrchestration,
  selectCurrentOrchestrationGroupPageCount,
  selectCurrentOrchestrationGroupRules,
  selectCurrentOrchestrationGroupRuleTotal,
  selectEngineValidationRules,
  selectFilteredRuleGroups,
  selectGroupOrchestrationCounts,
  selectHasBlockingSourceIssues,
  selectInvalidOrchestrationGroupIds,
  selectInvalidOrchestrationRuleIds,
  selectPagedCurrentOrchestrationGroupRules,
  selectResultPageCount,
  selectSelectedRuleGroup,
  selectSingleVariables,
  selectTaskTree,
} from './workbench/selectors'
import {
  getPresetListByGroup,
  getSelectedPresetByGroup,
  replaceSourceBasePathAction,
  setPresetListByGroup,
  setSelectedPresetByGroup,
} from './workbench/pathReplacementActions'
import {
  getAutoSavePayload,
  loadFromServerAction,
  saveConfigNowAction,
  scheduleAutoSaveAction,
} from './workbench/persistenceActions'
import { collectAffectedSourceIds } from './workbench/sourceActions'
import {
  getCompositePreviewPageOptions,
  normalizeStoredVariable,
  normalizeVariablePreviewOptions,
  variablePreviewMatchesRequest,
  type VariablePreviewLoadOptions,
} from './workbench/variableActions'
import { resetExecutionState } from './workbench/executionActions'
import { createWorkbenchState, type WorkbenchState } from './workbench/state'
import {
  collectVariableTagsBySourceIds,
  createEntityId,
  ensureDefaultGroup,
  normalizeCompositeConfig,
  normalizeExpectedValue,
  normalizeExpectedValueMode,
  normalizeMultiCompositeMappingConfig,
  normalizeMultiCompositePipelineConfig,
  pruneRulesByRemovedTags,
  RULE_ORCHESTRATION_PAGE_SIZE,
  UNGROUPED_GROUP,
} from '../utils/ruleOrchestrationModel'
import {
  normalizeReplacementPreset,
  type SourcePathReplacementGroup,
} from '../utils/sourcePathReplacement'
import { saveApiFile } from '../utils/download'
import { SAMPLE_SOURCE_PATH } from '../utils/workbenchMeta'

function canUseCachedSourceMetadata(
  cached: SourceMetadata | undefined,
  options?: SourceMetadataFetchOptions,
): cached is SourceMetadata {
  if (!cached) {
    return false
  }
  if (options?.includeColumns === false) {
    return true
  }
  return cached.sheets.length === 0 || cached.sheets.some((sheet) => sheet.columns.length > 0)
}

export const useWorkbenchStore = defineStore('workbench', {
  state: (): WorkbenchState => createWorkbenchState(),

  getters: {
    /** 供引擎执行的 ValidationRule 列表（由编排规则映射）。 */
    engineValidationRules(): ValidationRule[] {
      return selectEngineValidationRules(this)
    },

    taskTree(): TaskTree {
      return selectTaskTree(this)
    },

    allRuleGroups(): FixedRuleGroup[] {
      return selectAllRuleGroups(this)
    },

    filteredRuleGroups(): FixedRuleGroup[] {
      return selectFilteredRuleGroups(this)
    },

    selectedRuleGroup(): FixedRuleGroup {
      return selectSelectedRuleGroup(this)
    },

    groupOrchestrationCounts(): Record<string, number> {
      return selectGroupOrchestrationCounts(this)
    },

    currentOrchestrationGroupRules(): FixedRuleDefinition[] {
      return selectCurrentOrchestrationGroupRules(this)
    },

    pagedCurrentOrchestrationGroupRules(): FixedRuleDefinition[] {
      return selectPagedCurrentOrchestrationGroupRules(this)
    },

    currentOrchestrationGroupRuleTotal(): number {
      return selectCurrentOrchestrationGroupRuleTotal(this)
    },

    currentOrchestrationGroupPageCount(): number {
      return selectCurrentOrchestrationGroupPageCount(this)
    },

    orchestrationRuleCount(): number {
      return this.orchestrationRules.length
    },

    invalidOrchestrationRuleIds(): string[] {
      return selectInvalidOrchestrationRuleIds(this)
    },

    invalidOrchestrationGroupIds(): string[] {
      return selectInvalidOrchestrationGroupIds(this)
    },

    canExecuteOrchestration(): boolean {
      return selectCanExecuteOrchestration(this)
    },

    canRunSvnUpdate(): boolean {
      return this.sources.length > 0
    },

    hasBlockingSourceIssues(state): boolean {
      return selectHasBlockingSourceIssues(state)
    },

    singleVariables(state): VariableTag[] {
      return selectSingleVariables(state)
    },

    resultCount(state): number {
      return state.abnormalResultTotal
    },

    resultPageCount(state): number {
      return selectResultPageCount(state)
    },
  },

  actions: {
    clearPageError(): void {
      this.pageError = ''
    },

    clearExecutionResult(): void {
      Object.assign(this, resetExecutionState())
    },

    clearSvnUpdateResult(): void {
      this.svnUpdateResults = []
      this.svnUpdateSummary = ''
    },

    setActiveTag(tag: string | null): void {
      this.activeTag = tag
    },

    clearSourceMetadata(sourceId: string): void {
      delete this.sourceMetadataMap[sourceId]
    },

    clearVariablePreview(tag: string): void {
      delete this.variablePreviewMap[tag]
    },

    setSelectedPathReplacementPreset(
      group: SourcePathReplacementGroup,
      path: string | null,
    ): void {
      setSelectedPresetByGroup(
        this,
        group,
        path ? normalizeReplacementPreset(path, group) : null,
      )
    },

    addPathReplacementPreset(group: SourcePathReplacementGroup, path: string): void {
      const normalizedPath = normalizeReplacementPreset(path, group)
      if (!normalizedPath) {
        return
      }

      const presetMap = new Map(
        getPresetListByGroup(this, group).map((preset) => [preset.toLowerCase(), preset] as const),
      )
      if (!presetMap.has(normalizedPath.toLowerCase())) {
        presetMap.set(normalizedPath.toLowerCase(), normalizedPath)
        setPresetListByGroup(this, group, [...presetMap.values()])
      }
    },

    updatePathReplacementPreset(
      group: SourcePathReplacementGroup,
      originalPath: string,
      nextPath: string,
    ): void {
      const normalizedOriginalPath = normalizeReplacementPreset(originalPath, group)
      const normalizedNextPath = normalizeReplacementPreset(nextPath, group)
      if (!normalizedOriginalPath || !normalizedNextPath) {
        return
      }

      const presetList = getPresetListByGroup(this, group)
      const nextPresetList = presetList.map((preset) =>
        preset.toLowerCase() === normalizedOriginalPath.toLowerCase()
          ? normalizedNextPath
          : preset,
      )
      setPresetListByGroup(this, group, [...new Map(
        nextPresetList.map((preset) => [preset.toLowerCase(), preset] as const),
      ).values()])

      const selectedPreset = getSelectedPresetByGroup(this, group)
      if (selectedPreset?.toLowerCase() === normalizedOriginalPath.toLowerCase()) {
        this.setSelectedPathReplacementPreset(group, normalizedNextPath)
      }
    },

    removePathReplacementPreset(group: SourcePathReplacementGroup, path: string): void {
      const normalizedPath = normalizeReplacementPreset(path, group)
      if (!normalizedPath) {
        return
      }

      setPresetListByGroup(
        this,
        group,
        getPresetListByGroup(this, group).filter(
          (preset) => preset.toLowerCase() !== normalizedPath.toLowerCase(),
        ),
      )

      const selectedPreset = getSelectedPresetByGroup(this, group)
      if (selectedPreset?.toLowerCase() === normalizedPath.toLowerCase()) {
        this.setSelectedPathReplacementPreset(group, null)
      }
    },

    invalidateSourceArtifacts(sourceIds: string[]): void {
      const normalizedIds = new Set(sourceIds.filter(Boolean))
      if (!normalizedIds.size) {
        return
      }

      normalizedIds.forEach((sourceId) => {
        delete this.sourceMetadataMap[sourceId]
      })

      const affectedTags = collectVariableTagsBySourceIds(this.variables, normalizedIds)
      affectedTags.forEach((tag) => {
        delete this.variablePreviewMap[tag]
      })
    },

    async loadCapabilities(): Promise<void> {
      try {
        const response = await fetchSourceCapabilities()
        this.capabilities = response.data.source_types
      } catch (error) {
        this.pageError = error instanceof Error ? error.message : '获取数据源能力失败。'
      }
    },

    async loadSourceMetadata(
      sourceId: string,
      forceRefresh = false,
      options?: SourceMetadataFetchOptions,
    ): Promise<SourceMetadata> {
      const cached = this.sourceMetadataMap[sourceId]
      if (!forceRefresh && canUseCachedSourceMetadata(cached, options)) {
        return cached
      }

      const source = this.sources.find((item) => item.id === sourceId)
      if (!source) {
        throw new Error(`未找到数据源 "${sourceId}"。`)
      }

      const response = await fetchSourceMetadata(source, options)
      this.sourceMetadataMap[sourceId] = response.data
      return response.data
    },

    async loadVariablePreview(
      variable: VariableTag,
      options?: number | VariablePreviewLoadOptions,
      forceRefresh = false,
    ): Promise<VariablePreviewData> {
      const cached = this.variablePreviewMap[variable.tag]
      const previewOptions = normalizeVariablePreviewOptions(options)

      if (
        cached &&
        !forceRefresh &&
        variablePreviewMatchesRequest(cached, variable, previewOptions)
      ) {
        return cached
      }

      const source = this.sources.find((item) => item.id === variable.source_id)
      if (!source) {
        throw new Error(`变量 "${variable.tag}" 引用了不存在的数据源 "${variable.source_id}"。`)
      }

      const compositePageOptions = getCompositePreviewPageOptions(previewOptions)
      const response =
        (variable.variable_kind ?? 'single') === 'composite'
          ? await fetchCompositePreview({
              source,
              sheet: variable.sheet,
              columns: variable.columns ?? [],
              key_column: variable.key_column ?? '',
              append_index_to_key: variable.append_index_to_key ?? false,
              page: compositePageOptions.page,
              size: compositePageOptions.size,
            })
          : await fetchColumnPreview({
              source,
              sheet: variable.sheet,
              column: variable.column ?? '',
              limit: previewOptions.limit,
            })
      this.variablePreviewMap[variable.tag] = response.data
      return response.data
    },

    upsertSource(source: DataSource, originalId?: string): void {
      const sourceCopy = { ...source }
      const affectedSourceIds = collectAffectedSourceIds(sourceCopy, originalId)

      affectedSourceIds.forEach((sourceId) => {
        delete this.sourceIssues[sourceId]
      })

      if (originalId && originalId !== source.id) {
        const index = this.sources.findIndex((item) => item.id === originalId)
        if (index >= 0) {
          this.sources.splice(index, 1, sourceCopy)
          this.variables = this.variables.map((variable) =>
            variable.source_id === originalId ? { ...variable, source_id: source.id } : variable,
          )
          this.preferredSourceId = sourceCopy.id
          this.invalidateSourceArtifacts([...affectedSourceIds])
          return
        }
      }

      const index = this.sources.findIndex((item) => item.id === source.id)

      if (index >= 0) {
        this.sources.splice(index, 1, sourceCopy)
        this.preferredSourceId = sourceCopy.id
        this.invalidateSourceArtifacts([...affectedSourceIds])
        return
      }

      this.sources.unshift(sourceCopy)
      this.preferredSourceId = sourceCopy.id
      this.invalidateSourceArtifacts([...affectedSourceIds])
    },

    removeSource(sourceId: string): void {
      const removedTags = new Set(
        this.variables
          .filter((variable) => variable.source_id === sourceId)
          .map((variable) => variable.tag),
      )

      this.sources = this.sources.filter((source) => source.id !== sourceId)
      this.variables = this.variables.filter((variable) => variable.source_id !== sourceId)
      this.orchestrationRules = pruneRulesByRemovedTags(this.orchestrationRules, removedTags)
      this.invalidateSourceArtifacts([sourceId])
      delete this.sourceIssues[sourceId]

      const pageCount = Math.max(
        1,
        Math.ceil(this.currentOrchestrationGroupRuleTotal / RULE_ORCHESTRATION_PAGE_SIZE),
      )
      if (this.orchestrationCurrentPage > pageCount) {
        this.orchestrationCurrentPage = pageCount
      }

      removedTags.forEach((tag) => {
        delete this.variablePreviewMap[tag]
      })

      if (this.activeTag && removedTags.has(this.activeTag)) {
        this.activeTag = null
      }

      if (this.preferredSourceId === sourceId) {
        this.preferredSourceId = this.sources[0]?.id ?? null
      }
    },

    useSampleSource(): void {
      this.upsertSource({
        id: 'src_demo',
        type: 'local_excel',
        pathOrUrl: SAMPLE_SOURCE_PATH,
      })
    },

    upsertVariable(variable: VariableTag, originalTag?: string): void {
      const variableCopy = normalizeStoredVariable(variable)

      if (originalTag) {
        const index = this.variables.findIndex((item) => item.tag === originalTag)
        if (index >= 0) {
          this.variables.splice(index, 1, variableCopy)
          delete this.variablePreviewMap[originalTag]
          delete this.variablePreviewMap[variableCopy.tag]

          if (originalTag !== variable.tag) {
            this.replaceTagInOrchestrationRules(originalTag, variable.tag)
            if (this.activeTag === originalTag) {
              this.activeTag = variable.tag
            }
          }
          this.activeTag = variableCopy.tag
          return
        }
      }

      const index = this.variables.findIndex((item) => item.tag === variable.tag)
      if (index >= 0) {
        this.variables.splice(index, 1, variableCopy)
        delete this.variablePreviewMap[variableCopy.tag]
        this.activeTag = variableCopy.tag
        return
      }

      this.variables.push(variableCopy)
      delete this.variablePreviewMap[variableCopy.tag]
      this.activeTag = variableCopy.tag
    },

    removeVariable(tag: string): void {
      this.variables = this.variables.filter((variable) => variable.tag !== tag)
      this.orchestrationRules = pruneRulesByRemovedTags(this.orchestrationRules, new Set([tag]))
      delete this.variablePreviewMap[tag]

      if (this.activeTag === tag) {
        this.activeTag = null
      }

      const pageCount = Math.max(
        1,
        Math.ceil(this.currentOrchestrationGroupRuleTotal / RULE_ORCHESTRATION_PAGE_SIZE),
      )
      if (this.orchestrationCurrentPage > pageCount) {
        this.orchestrationCurrentPage = pageCount
      }
    },

    useSampleVariables(): void {
      if (!this.sources.length) {
        this.useSampleSource()
      }

      const sourceId =
        this.sources.find((source) => source.id === 'src_demo')?.id ??
        this.sources[0]?.id ??
        'src_demo'

      this.upsertVariable({
        tag: '[items-id]',
        source_id: sourceId,
        sheet: 'items',
        variable_kind: 'single',
        column: 'ID',
        expected_type: 'str',
      })
      this.upsertVariable({
        tag: '[drops-ref]',
        source_id: sourceId,
        sheet: 'drops',
        variable_kind: 'single',
        column: 'RefID',
        expected_type: 'str',
      })
    },

    applyDemoScenario(): void {
      this.pageError = ''
      this.executionMeta = null
      this.resultId = null
      this.resultCurrentPage = 1
      this.abnormalResultTotal = 0
      this.isResultPageLoading = false
      this.abnormalResults = []
      this.activeTag = '[items-id]'
      this.sourceMetadataMap = {}
      this.variablePreviewMap = {}

      this.sources = []
      this.variables = []

      this.useSampleSource()
      this.useSampleVariables()

      this.ruleGroups = [{ ...UNGROUPED_GROUP }]
      this.selectedGroupId = UNGROUPED_GROUP.group_id
      this.groupKeyword = ''
      this.orchestrationCurrentPage = 1
      this.orchestrationRules = createWorkbenchDemoRules()
    },

    setSelectedOrchestrationGroup(groupId: string): void {
      this.selectedGroupId = groupId
      this.orchestrationCurrentPage = 1
    },

    setOrchestrationCurrentPage(page: number): void {
      this.orchestrationCurrentPage = page
    },

    createOrchestrationGroup(groupName: string): void {
      this.ruleGroups = ensureDefaultGroup([
        ...this.ruleGroups,
        {
          group_id: createEntityId('group'),
          group_name: groupName.trim(),
          builtin: false,
        },
      ])
    },

    ensureOrchestrationGroupByName(groupName: string): string {
      const normalizedName = groupName.trim() || 'AI生成规则组'
      const existingGroup = this.ruleGroups.find(
        (group) => group.group_name === normalizedName,
      )
      if (existingGroup) {
        return existingGroup.group_id
      }

      const groupId = createEntityId('group')
      this.ruleGroups = ensureDefaultGroup([
        ...this.ruleGroups,
        {
          group_id: groupId,
          group_name: normalizedName,
          builtin: false,
        },
      ])
      return groupId
    },

    renameOrchestrationGroup(groupId: string, groupName: string): void {
      this.ruleGroups = ensureDefaultGroup(
        this.ruleGroups.map((group) =>
          group.group_id === groupId && !group.builtin
            ? { ...group, group_name: groupName.trim() }
            : group,
        ),
      )
    },

    removeOrchestrationGroup(groupId: string): void {
      if (groupId === UNGROUPED_GROUP.group_id) {
        return
      }
      this.ruleGroups = ensureDefaultGroup(
        this.ruleGroups.filter((group) => group.group_id !== groupId),
      )
      this.orchestrationRules = this.orchestrationRules.map((rule) =>
        rule.group_id === groupId ? { ...rule, group_id: UNGROUPED_GROUP.group_id } : rule,
      )
      this.selectedGroupId = this.ruleGroups[0]?.group_id ?? UNGROUPED_GROUP.group_id
      this.orchestrationCurrentPage = 1
    },

    upsertOrchestrationRule(
      rule: Omit<FixedRuleDefinition, 'rule_id'> & { rule_id?: string },
    ): void {
      const normalizedCompositeConfig =
        rule.rule_type === 'composite_condition_check'
          ? normalizeCompositeConfig(rule.composite_config)
          : undefined
      const normalizedPipelineConfig =
        rule.rule_type === 'multi_composite_pipeline_check'
          ? normalizeMultiCompositePipelineConfig(rule.pipeline_config)
          : undefined
      const normalizedMappingConfig =
        rule.rule_type === 'multi_composite_mapping_check'
          ? normalizeMultiCompositeMappingConfig(rule.mapping_config)
          : undefined
      const variableMap = new Map(this.variables.map((variable) => [variable.tag, variable] as const))
      const normalizedTargetTag =
        rule.rule_type === 'multi_composite_pipeline_check'
          ? normalizedPipelineConfig?.nodes[0]?.variable_tag ?? rule.target_variable_tag
          : rule.rule_type === 'multi_composite_mapping_check'
          ? normalizedMappingConfig?.nodes[0]?.variable_tag ?? rule.target_variable_tag
          : rule.target_variable_tag
      const targetVariable = variableMap.get(normalizedTargetTag.trim())
      const referenceVariable =
        rule.rule_type === 'dual_composite_compare'
          ? variableMap.get(rule.reference_variable_tag?.trim() ?? '')
          : undefined
      const targetFields = collectCompositeAvailableFields(targetVariable)
      const referenceFields = collectCompositeAvailableFields(referenceVariable)

      const nextRule: FixedRuleDefinition = {
        rule_id: rule.rule_id ?? createEntityId('wb-rule'),
        group_id: rule.group_id,
        rule_name: rule.rule_name.trim(),
        enabled: rule.enabled ?? true,
        description: rule.description?.trim() || undefined,
        target_variable_tag: normalizedTargetTag.trim(),
        display_field: rule.display_field?.trim() || undefined,
        rule_type: rule.rule_type,
        operator: rule.rule_type === 'fixed_value_compare' ? rule.operator : undefined,
        expected_value:
          rule.rule_type === 'fixed_value_compare' || rule.rule_type === 'regex_check'
            ? normalizeExpectedValue(rule.expected_value)
            : undefined,
        expected_value_mode:
          rule.rule_type === 'fixed_value_compare' && (rule.operator === 'eq' || rule.operator === 'ne')
            ? normalizeExpectedValueMode(rule.expected_value_mode)
            : undefined,
        reference_variable_tag:
          rule.rule_type === 'cross_table_mapping' ||
          rule.rule_type === 'dual_composite_compare' ||
          rule.rule_type === 'package_items_compare' ||
          rule.rule_type === 'event_task_reward' ||
          rule.rule_type === 'event_task_validation'
            ? rule.reference_variable_tag?.trim() || undefined
            : undefined,
        sequence_direction:
          rule.rule_type === 'sequence_order_check' ? rule.sequence_direction ?? 'asc' : undefined,
        sequence_step:
          rule.rule_type === 'sequence_order_check' ? rule.sequence_step?.trim() || '1' : undefined,
        sequence_start_mode:
          rule.rule_type === 'sequence_order_check'
            ? rule.sequence_start_mode ?? 'auto'
            : undefined,
        sequence_start_value:
          rule.rule_type === 'sequence_order_check' && rule.sequence_start_mode === 'manual'
            ? rule.sequence_start_value?.trim() || undefined
            : undefined,
        composite_config: normalizedCompositeConfig,
        pipeline_config: normalizedPipelineConfig,
        mapping_config: normalizedMappingConfig,
        key_check_mode:
          rule.rule_type === 'dual_composite_compare'
            ? rule.key_check_mode ?? 'baseline_only'
            : undefined,
        left_key_field:
          rule.rule_type === 'dual_composite_compare'
            ? resolveFieldAgainstAvailable(rule.left_key_field ?? '__key__', targetFields) ?? '__key__'
            : undefined,
        right_key_field:
          rule.rule_type === 'dual_composite_compare'
            ? resolveFieldAgainstAvailable(rule.right_key_field ?? '__key__', referenceFields) ?? '__key__'
            : undefined,
        comparisons:
          rule.rule_type === 'dual_composite_compare'
            ? (rule.comparisons ?? []).map((comparison) => ({
                comparison_id: comparison.comparison_id,
                left_field:
                  resolveFieldAgainstAvailable(comparison.left_field, targetFields) ??
                  comparison.left_field.trim(),
                operator: comparison.operator,
                right_field:
                  resolveFieldAgainstAvailable(comparison.right_field, referenceFields) ??
                  comparison.right_field.trim(),
              }))
            : [],
        left_filters:
          rule.rule_type === 'dual_composite_compare'
            ? normalizeDualCompositeFilters(rule.left_filters, targetFields)
            : [],
        right_filters:
          rule.rule_type === 'dual_composite_compare'
            ? normalizeDualCompositeFilters(rule.right_filters, referenceFields)
            : [],
        package_parse_config:
          rule.rule_type === 'package_items_compare'
            ? {
                feishu_source_id: rule.package_parse_config?.feishu_source_id?.trim() ?? '',
                feishu_sheet_id: rule.package_parse_config?.feishu_sheet_id?.trim() ?? '',
                feishu_sheet_name: rule.package_parse_config?.feishu_sheet_name?.trim() || undefined,
                parse_strategy: rule.package_parse_config?.parse_strategy ?? 'auto',
                ai_parse_mode: rule.package_parse_config?.ai_parse_mode ?? 'auto',
                validation_scope: rule.package_parse_config?.validation_scope ?? 'all',
                package_id_filter:
                  rule.package_parse_config?.validation_scope === 'specified'
                    ? rule.package_parse_config?.package_id_filter?.trim() || undefined
                    : undefined,
              }
            : undefined,
        left_package_field:
          rule.rule_type === 'package_items_compare'
            ? rule.left_package_field?.trim() || '礼包id'
            : undefined,
        left_item_field:
          rule.rule_type === 'package_items_compare'
            ? rule.left_item_field?.trim() || '道具ID'
            : undefined,
        left_count_field:
          rule.rule_type === 'package_items_compare'
            ? rule.left_count_field?.trim() || '个数'
            : undefined,
        right_package_field:
          rule.rule_type === 'package_items_compare'
            ? rule.right_package_field?.trim() || 'INT_PackageId'
            : undefined,
        right_items_field:
          rule.rule_type === 'package_items_compare'
            ? rule.right_items_field?.trim() || 'STR_Items'
            : undefined,
        package_id_filter:
          rule.rule_type === 'package_items_compare' &&
          rule.package_parse_config?.validation_scope === 'specified'
            ? rule.package_id_filter?.trim() ||
              rule.package_parse_config?.package_id_filter?.trim() ||
              undefined
            : undefined,
        event_task_parse_config:
          rule.rule_type === 'event_task_reward' || rule.rule_type === 'event_task_validation'
            ? {
                feishu_source_id: rule.event_task_parse_config?.feishu_source_id?.trim() ?? '',
                feishu_sheet_id: rule.event_task_parse_config?.feishu_sheet_id?.trim() ?? '',
                feishu_sheet_name:
                  rule.event_task_parse_config?.feishu_sheet_name?.trim() || undefined,
                config_variable_tag:
                  rule.event_task_parse_config?.config_variable_tag?.trim() ||
                  rule.reference_variable_tag?.trim() ||
                  undefined,
                parse_strategy: rule.event_task_parse_config?.parse_strategy ?? 'group_desc',
                ai_parse_mode: rule.event_task_parse_config?.ai_parse_mode ?? 'auto',
                validation_scope: rule.event_task_parse_config?.validation_scope ?? 'all',
                task_group_id_filter:
                  rule.event_task_parse_config?.validation_scope === 'specified'
                    ? rule.event_task_parse_config?.task_group_id_filter?.trim() ||
                      rule.task_group_id_filter?.trim() ||
                      undefined
                    : undefined,
                key_delimiter: rule.event_task_parse_config?.key_delimiter?.trim() || '_',
                fallback_match_field:
                  rule.event_task_parse_config?.fallback_match_field?.trim() || 'INT_TaskID',
                event_task_field_mapping:
                  rule.event_task_parse_config?.event_task_field_mapping ?? undefined,
              }
            : undefined,
        left_task_group_field:
          rule.rule_type === 'event_task_reward' || rule.rule_type === 'event_task_validation'
            ? rule.left_task_group_field?.trim() || '任务组ID'
            : undefined,
        left_task_id_field:
          rule.rule_type === 'event_task_reward' || rule.rule_type === 'event_task_validation'
            ? rule.left_task_id_field?.trim() || 'INT_TaskID'
            : undefined,
        left_task_desc_field:
          rule.rule_type === 'event_task_reward' || rule.rule_type === 'event_task_validation'
            ? rule.left_task_desc_field?.trim() || '任务描述'
            : undefined,
        left_task_loot_field:
          rule.rule_type === 'event_task_reward' || rule.rule_type === 'event_task_validation'
            ? rule.left_task_loot_field?.trim() || 'STR_Loot'
            : undefined,
        right_task_group_field:
          rule.rule_type === 'event_task_reward' || rule.rule_type === 'event_task_validation'
            ? rule.right_task_group_field?.trim() || 'INT_ID'
            : undefined,
        right_task_id_field:
          rule.rule_type === 'event_task_reward' || rule.rule_type === 'event_task_validation'
            ? rule.right_task_id_field?.trim() || 'INT_TaskID'
            : undefined,
        right_task_desc_field:
          rule.rule_type === 'event_task_reward' || rule.rule_type === 'event_task_validation'
            ? rule.right_task_desc_field?.trim() || 'STR_Desc'
            : undefined,
        right_task_loot_field:
          rule.rule_type === 'event_task_reward' || rule.rule_type === 'event_task_validation'
            ? rule.right_task_loot_field?.trim() || 'STR_Loot'
            : undefined,
        event_task_match_strategy:
          rule.rule_type === 'event_task_reward' || rule.rule_type === 'event_task_validation'
            ? rule.event_task_match_strategy ?? 'groupId_desc_then_taskId'
            : undefined,
        ai_assist_mode:
          rule.rule_type === 'event_task_reward' || rule.rule_type === 'event_task_validation'
            ? rule.ai_assist_mode ?? 'auto'
            : undefined,
        task_group_id_filter:
          (rule.rule_type === 'event_task_reward' || rule.rule_type === 'event_task_validation') &&
          rule.event_task_parse_config?.validation_scope === 'specified'
            ? rule.task_group_id_filter?.trim() ||
              rule.event_task_parse_config?.task_group_id_filter?.trim() ||
              undefined
            : undefined,
      }

      const index = this.orchestrationRules.findIndex((item) => item.rule_id === nextRule.rule_id)
      if (index >= 0) {
        this.orchestrationRules.splice(index, 1, nextRule)
      } else {
        this.orchestrationRules.push(nextRule)
      }
    },

    removeOrchestrationRule(ruleId: string): void {
      this.orchestrationRules = this.orchestrationRules.filter((rule) => rule.rule_id !== ruleId)
      const pageCount = Math.max(
        1,
        Math.ceil(this.currentOrchestrationGroupRuleTotal / RULE_ORCHESTRATION_PAGE_SIZE),
      )
      if (this.orchestrationCurrentPage > pageCount) {
        this.orchestrationCurrentPage = pageCount
      }
    },

    replaceTagInOrchestrationRules(previousTag: string, nextTag: string): void {
      this.orchestrationRules = this.orchestrationRules.map((rule) =>
        rule.target_variable_tag === previousTag ||
        rule.reference_variable_tag === previousTag
          ? {
              ...rule,
              target_variable_tag:
                rule.target_variable_tag === previousTag
                  ? nextTag
                  : rule.target_variable_tag,
              reference_variable_tag:
                rule.reference_variable_tag === previousTag
                  ? nextTag
                  : rule.reference_variable_tag,
            }
          : rule,
      )
    },

    buildTaskTreePayload(
      selectedRuleIds?: string[],
      page?: number,
      size?: number,
    ): TaskTree {
      return buildWorkbenchTaskTreePayload(this, selectedRuleIds, page, size)
    },

    async executeValidation(selectedRuleIds?: string[]): Promise<void> {
      this.pageError = ''
      if (!this.orchestrationRules.length) {
        this.pageError = '请先在步骤 3 添加至少一条规则。'
        return
      }
      if (this.hasBlockingSourceIssues) {
        this.pageError = '当前存在读取失败的数据源，请先修复数据源路径管理中的路径问题或重新接入数据源后再执行校验。'
        throw new Error(this.pageError)
      }
      if (this.invalidOrchestrationRuleIds.length) {
        this.pageError = '存在未配置完整的规则，请按步骤 3 顶部提示修复后再执行。'
        return
      }

      this.isExecuting = true

      try {
        const payload = this.buildTaskTreePayload(
          selectedRuleIds,
          1,
          this.resultPageSize,
        )
        const response = await executeTaskTree(payload)
        this.executionMeta = response.meta
        this.resultId = response.meta.result_id ?? null
        this.resultCurrentPage = response.data.page ?? 1
        this.abnormalResultTotal =
          response.data.total ?? response.data.abnormal_results.length
        this.abnormalResults = response.data.list ?? response.data.abnormal_results
      } catch (error) {
        this.executionMeta = null
        this.resultId = null
        this.resultCurrentPage = 1
        this.abnormalResultTotal = 0
        this.abnormalResults = []
        this.pageError = error instanceof Error ? error.message : '执行校验失败。'
        throw error
      } finally {
        this.isExecuting = false
      }
    },

    async loadResultPage(page: number): Promise<void> {
      if (!this.resultId || !this.executionMeta) {
        return
      }

      this.isResultPageLoading = true
      this.pageError = ''
      try {
        const response = await fetchExecutionResults(
          this.resultId,
          page,
          this.resultPageSize,
        )
        this.executionMeta = response.meta
        this.resultCurrentPage = response.data.page ?? page
        this.abnormalResultTotal =
          response.data.total ?? response.data.abnormal_results.length
        this.abnormalResults = response.data.list ?? response.data.abnormal_results
      } catch (error) {
        this.pageError = error instanceof Error ? error.message : '读取结果分页失败。'
        throw error
      } finally {
        this.isResultPageLoading = false
      }
    },

    async exportResults(): Promise<void> {
      if (!this.resultId || !this.executionMeta) {
        return
      }

      this.isResultExporting = true
      this.pageError = ''
      try {
        const file = await exportExecutionResults(this.resultId)
        saveApiFile(file)
      } catch (error) {
        this.pageError = error instanceof Error ? error.message : '导出结果失败。'
        throw error
      } finally {
        this.isResultExporting = false
      }
    },

    async saveConfigNow(): Promise<void> {
      await saveConfigNowAction(this)
    },

    async runSvnUpdate(): Promise<void> {
      this.isUpdatingSvn = true
      this.pageError = ''

      try {
        await this.saveConfigNow()
        const response = await triggerWorkbenchSvnUpdate()
        this.svnUpdateResults = response.data.results
        this.svnUpdateSummary = `已处理 ${response.data.total_paths} 个路径，成功更新 ${response.data.updated_paths} 个。`
      } catch (error) {
        this.pageError = error instanceof Error ? error.message : 'SVN 更新失败。'
        throw error
      } finally {
        this.isUpdatingSvn = false
      }
    },

    async replaceSourceBasePath(group: SourcePathReplacementGroup, baseDirectory: string): Promise<{
      updatedCount: number
      skippedCount: number
      failedCount: number
      affectedSourceIds: string[]
    }> {
      return replaceSourceBasePathAction(this, group, baseDirectory)
    },

    _getAutoSavePayload(): Record<string, unknown> {
      return getAutoSavePayload(this)
    },

    _scheduleAutoSave(): void {
      scheduleAutoSaveAction(this as WorkbenchState & { _autoSaveTimer?: ReturnType<typeof setTimeout> })
    },

    triggerAutoSave(): void {
      this._scheduleAutoSave()
    },

    async retryAutoSave(): Promise<void> {
      await this.saveConfigNow()
    },

    async loadFromServer(): Promise<void> {
      await loadFromServerAction(this)
    },
  },
})
