import { defineStore } from 'pinia'

import {
  executeFixedRules,
  exportFixedRulesResults,
  fetchFixedRulesResults,
  fetchFixedRulesConfig,
  saveFixedRulesConfig,
  triggerFixedRulesSvnUpdate,
} from '../api/fixedRules'
import {
  fetchColumnPreview,
  fetchCompositePreview,
  fetchSourceCapabilities,
  fetchSourceMetadata,
} from '../api/workbench'
import type {
  CompositeCondition,
  FixedRuleDefinition,
  FixedRuleGroup,
  FixedRulesConfig,
  FixedRulesConfigIssue,
  FixedRulesSvnUpdateItem,
} from '../types/fixedRules'
import type {
  AbnormalResult,
  DataSource,
  ExecutionMeta,
  SourceMetadata,
  SourceType,
  VariablePreviewData,
  VariableTag,
} from '../types/workbench'
import {
  collectVariableTagsBySourceIds,
  createEntityId,
  ensureDefaultGroup,
  isCompositeVariable,
  isValidMultiCompositeMappingConfig,
  isValidMultiCompositePipelineConfig,
  isSingleVariable,
  isValidCompositeConfig,
  isValidCompositeCondition,
  normalizeCompositeConfig,
  normalizeCompositeCondition,
  normalizeExpectedValueMode,
  normalizeMultiCompositeMappingConfig,
  normalizeMultiCompositePipelineConfig,
  normalizeExpectedValue,
  pruneRulesByRemovedTags,
  RULE_ORCHESTRATION_PAGE_SIZE,
  UNGROUPED_GROUP,
} from '../utils/ruleOrchestrationModel'
import {
  extractSourceBasename,
  getSourceLocator,
  isAffectedVariable,
  isLocalPathManagedSource,
  isSvnPathManagedSource,
  joinDirectoryAndBasename,
  joinSvnDirectoryAndBasename,
  normalizeReplacementPreset,
  type SourcePathReplacementGroup,
} from '../utils/sourcePathReplacement'
import { saveApiFile } from '../utils/download'
import { SAMPLE_SOURCE_PATH } from '../utils/workbenchMeta'

const FIXED_RULES_PAGE_SIZE = RULE_ORCHESTRATION_PAGE_SIZE

interface FixedRulesState {
  config: FixedRulesConfig
  capabilities: SourceType[]
  activeTag: string | null
  preferredSourceId: string | null
  sourceMetadataMap: Record<string, SourceMetadata>
  variablePreviewMap: Record<string, VariablePreviewData>
  selectedGroupId: string
  groupKeyword: string
  currentPage: number
  isLoading: boolean
  isSaving: boolean
  isExecuting: boolean
  isResultPageLoading: boolean
  isResultExporting: boolean
  isUpdatingSvn: boolean
  pageError: string
  configIssues: FixedRulesConfigIssue[]
  executionMeta: ExecutionMeta | null
  abnormalResults: AbnormalResult[]
  abnormalResultTotal: number
  resultId: number | null
  resultCurrentPage: number
  resultPageSize: number
  svnUpdateResults: FixedRulesSvnUpdateItem[]
  svnUpdateSummary: string
}

function createDefaultConfig(): FixedRulesConfig {
  return {
    version: 6,
    configured: false,
    sources: [],
    variables: [],
    groups: [{ ...UNGROUPED_GROUP }],
    rules: [],
    local_path_replacement_presets: [],
    selected_local_path_replacement_preset: null,
    svn_path_replacement_presets: [],
    selected_svn_path_replacement_preset: null,
  }
}

function getPresetListByGroup(
  config: Pick<
    FixedRulesConfig,
    | 'local_path_replacement_presets'
    | 'svn_path_replacement_presets'
  >,
  group: SourcePathReplacementGroup,
): string[] {
  return group === 'svn'
    ? config.svn_path_replacement_presets
    : config.local_path_replacement_presets
}

function setPresetListByGroup(
  config: FixedRulesConfig,
  group: SourcePathReplacementGroup,
  presets: string[],
): void {
  if (group === 'svn') {
    config.svn_path_replacement_presets = presets
    return
  }
  config.local_path_replacement_presets = presets
}

function setSelectedPresetByGroup(
  config: FixedRulesConfig,
  group: SourcePathReplacementGroup,
  selectedPreset: string | null,
): void {
  if (group === 'svn') {
    config.selected_svn_path_replacement_preset = selectedPreset
    return
  }
  config.selected_local_path_replacement_preset = selectedPreset
}

function isValidSequenceStep(value: string | undefined): boolean {
  const normalized = value?.trim() ?? ''
  if (!normalized) {
    return false
  }
  const numeric = Number(normalized)
  return Number.isFinite(numeric) && numeric > 0
}

function isValidSequenceStartValue(value: string | undefined): boolean {
  const normalized = value?.trim() ?? ''
  if (!normalized) {
    return false
  }
  return Number.isFinite(Number(normalized))
}

function resolveFieldAgainstAvailable(
  requestedField: string | undefined,
  availableFields: string[],
): string | null {
  const rawField = requestedField ?? ''
  if (availableFields.includes(rawField)) {
    return rawField
  }

  const normalizedField = rawField.trim()
  if (!normalizedField) {
    return null
  }

  const matchedFields = availableFields.filter((field) => field.trim() === normalizedField)
  return matchedFields.length === 1 ? matchedFields[0] : null
}

function collectCompositeAvailableFields(variable: VariableTag | undefined): string[] {
  const fields = new Set<string>(['__key__'])
  const keyColumn = variable?.key_column
  if (keyColumn?.trim()) {
    fields.add(keyColumn)
  }
  ;(variable?.columns ?? []).forEach((column) => {
    if (column?.trim()) {
      fields.add(column)
    }
  })
  return [...fields]
}

function isValidDualCompositeFilters(
  filters: CompositeCondition[] | undefined,
  availableFields: string[],
): boolean {
  return (filters ?? []).every((condition) => {
    if (!isValidCompositeCondition(condition, 'filter')) {
      return false
    }
    if (!resolveFieldAgainstAvailable(condition.field, availableFields)) {
      return false
    }
    if (
      condition.value_source === 'field' &&
      !resolveFieldAgainstAvailable(condition.expected_field, availableFields)
    ) {
      return false
    }
    return true
  })
}

function normalizeDualCompositeFilters(
  filters: CompositeCondition[] | undefined,
  availableFields: string[],
): CompositeCondition[] {
  return (filters ?? []).map((condition) => {
    const normalized = normalizeCompositeCondition(condition)
    return {
      ...normalized,
      field: resolveFieldAgainstAvailable(normalized.field, availableFields) ?? normalized.field,
      expected_field:
        normalized.value_source === 'field'
          ? resolveFieldAgainstAvailable(normalized.expected_field, availableFields) ??
            normalized.expected_field
          : normalized.expected_field,
    }
  })
}

function isValidDualCompositeRule(rule: FixedRuleDefinition, variableMap: Map<string, VariableTag>): boolean {
  const targetTag = rule.target_variable_tag.trim()
  const referenceTag = rule.reference_variable_tag?.trim() ?? ''
  const targetVariable = variableMap.get(targetTag)
  const referenceVariable = variableMap.get(referenceTag)

  if (!targetTag || !referenceTag) {
    return false
  }
  if (!isCompositeVariable(targetVariable) || !isCompositeVariable(referenceVariable)) {
    return false
  }
  if (!rule.key_check_mode || !['baseline_only', 'bidirectional'].includes(rule.key_check_mode)) {
    return false
  }
  if (!rule.comparisons?.length) {
    return false
  }

  const leftFieldList = collectCompositeAvailableFields(targetVariable)
  const rightFieldList = collectCompositeAvailableFields(referenceVariable)
  if (!resolveFieldAgainstAvailable(rule.left_key_field ?? '__key__', leftFieldList)) {
    return false
  }
  if (!resolveFieldAgainstAvailable(rule.right_key_field ?? '__key__', rightFieldList)) {
    return false
  }
  if (targetTag === referenceTag && (!rule.left_filters?.length || !rule.right_filters?.length)) {
    return false
  }
  if (!isValidDualCompositeFilters(rule.left_filters, leftFieldList)) {
    return false
  }
  if (!isValidDualCompositeFilters(rule.right_filters, rightFieldList)) {
    return false
  }

  return rule.comparisons.every((comparison) => {
    if (!comparison.comparison_id?.trim()) {
      return false
    }
    if (!resolveFieldAgainstAvailable(comparison.left_field, leftFieldList)) {
      return false
    }
    if (!resolveFieldAgainstAvailable(comparison.right_field, rightFieldList)) {
      return false
    }
    return ['eq', 'ne', 'gt', 'lt', 'not_null'].includes(comparison.operator)
  })
}

export const useFixedRulesStore = defineStore('fixed-rules', {
  state: (): FixedRulesState => ({
    config: createDefaultConfig(),
    capabilities: [],
    activeTag: null,
    preferredSourceId: null,
    sourceMetadataMap: {},
    variablePreviewMap: {},
    selectedGroupId: UNGROUPED_GROUP.group_id,
    groupKeyword: '',
    currentPage: 1,
    isLoading: false,
    isSaving: false,
    isExecuting: false,
    isResultPageLoading: false,
    isResultExporting: false,
    isUpdatingSvn: false,
    pageError: '',
    configIssues: [],
    executionMeta: null,
    abnormalResults: [],
    abnormalResultTotal: 0,
    resultId: null,
    resultCurrentPage: 1,
    resultPageSize: 20,
    svnUpdateResults: [],
    svnUpdateSummary: '',
  }),

  getters: {
    sources(state): DataSource[] {
      return state.config.sources
    },

    localPathReplacementPresets(state): string[] {
      return state.config.local_path_replacement_presets
    },

    selectedLocalPathReplacementPreset(state): string | null {
      return state.config.selected_local_path_replacement_preset ?? null
    },

    svnPathReplacementPresets(state): string[] {
      return state.config.svn_path_replacement_presets
    },

    selectedSvnPathReplacementPreset(state): string | null {
      return state.config.selected_svn_path_replacement_preset ?? null
    },

    variables(state): VariableTag[] {
      return state.config.variables
    },

    rules(state): FixedRuleDefinition[] {
      return state.config.rules
    },

    singleVariables(): VariableTag[] {
      return this.variables.filter((variable) => (variable.variable_kind ?? 'single') === 'single')
    },

    compositeVariables(): VariableTag[] {
      return this.variables.filter((variable) => (variable.variable_kind ?? 'single') === 'composite')
    },

    allGroups(state): FixedRuleGroup[] {
      return ensureDefaultGroup(state.config.groups)
    },

    filteredGroups(): FixedRuleGroup[] {
      const keyword = this.groupKeyword.trim().toLowerCase()
      if (!keyword) {
        return this.allGroups
      }

      return this.allGroups.filter((group) => group.group_name.toLowerCase().includes(keyword))
    },

    selectedGroup(): FixedRuleGroup {
      return (
        this.allGroups.find((group) => group.group_id === this.selectedGroupId) ??
        this.allGroups[0]
      )
    },

    groupRuleCounts(): Record<string, number> {
      return this.rules.reduce<Record<string, number>>((accumulator, rule) => {
        accumulator[rule.group_id] = (accumulator[rule.group_id] ?? 0) + 1
        return accumulator
      }, {})
    },

    currentGroupRules(): FixedRuleDefinition[] {
      const groupId = this.selectedGroup.group_id
      return this.rules.filter((rule) => rule.group_id === groupId)
    },

    pagedCurrentGroupRules(): FixedRuleDefinition[] {
      const start = (this.currentPage - 1) * FIXED_RULES_PAGE_SIZE
      return this.currentGroupRules.slice(start, start + FIXED_RULES_PAGE_SIZE)
    },

    currentGroupRuleTotal(): number {
      return this.currentGroupRules.length
    },

    currentGroupPageCount(): number {
      return Math.max(1, Math.ceil(this.currentGroupRuleTotal / FIXED_RULES_PAGE_SIZE))
    },

    totalRuleCount(): number {
      return this.rules.length
    },

    resultPageCount(state): number {
      return Math.max(1, Math.ceil(state.abnormalResultTotal / state.resultPageSize))
    },

    sourceCount(): number {
      return this.sources.length
    },

    variableCount(): number {
      return this.variables.length
    },

    invalidRuleIds(): string[] {
      const validGroupIds = new Set(this.allGroups.map((group) => group.group_id))
      const variableMap = new Map(this.variables.map((variable) => [variable.tag, variable] as const))

      return this.rules
        .filter((rule) => {
          if (!validGroupIds.has(rule.group_id)) {
            return true
          }
          if (!rule.rule_name.trim()) {
            return true
          }

          if (rule.rule_type === 'multi_composite_pipeline_check') {
            return !isValidMultiCompositePipelineConfig(rule.pipeline_config, variableMap)
          }
          if (rule.rule_type === 'multi_composite_mapping_check') {
            return !isValidMultiCompositeMappingConfig(rule.mapping_config, variableMap)
          }

          const targetTag = rule.target_variable_tag.trim()
          const variable = variableMap.get(targetTag)
          if (!targetTag || !variable) {
            return true
          }

          if (isSingleVariable(variable)) {
            if (
              rule.rule_type === 'composite_condition_check' ||
              rule.rule_type === 'dual_composite_compare'
            ) {
              return true
            }

            if (rule.rule_type === 'cross_table_mapping') {
              const referenceTag = rule.reference_variable_tag?.trim() ?? ''
              if (!referenceTag || referenceTag === targetTag) {
                return true
              }
              const referenceVariable = variableMap.get(referenceTag)
              if (!referenceVariable || !isSingleVariable(referenceVariable)) {
                return true
              }
              return false
            }

            if (rule.rule_type === 'sequence_order_check') {
              if (!rule.sequence_direction || !['asc', 'desc'].includes(rule.sequence_direction)) {
                return true
              }
              if (!rule.sequence_start_mode || !['auto', 'manual'].includes(rule.sequence_start_mode)) {
                return true
              }
              if (!isValidSequenceStep(rule.sequence_step)) {
                return true
              }
              if (rule.sequence_start_mode === 'manual' && !isValidSequenceStartValue(rule.sequence_start_value)) {
                return true
              }
              return false
            }

            if (rule.rule_type === 'regex_check') {
              return !normalizeExpectedValue(rule.expected_value)
            }

            if (rule.rule_type !== 'fixed_value_compare') {
              return false
            }

            if (!rule.operator) {
              return true
            }

            const expectedValue = normalizeExpectedValue(rule.expected_value)
            if (!expectedValue) {
              return true
            }

            if ((rule.operator === 'gt' || rule.operator === 'lt') && Number.isNaN(Number(expectedValue))) {
              return true
            }

            return false
          }

          if (!isCompositeVariable(variable)) {
            return true
          }

          if (rule.rule_type === 'composite_condition_check') {
            return !isValidCompositeConfig(rule.composite_config)
          }
          if (rule.rule_type === 'dual_composite_compare') {
            return !isValidDualCompositeRule(rule, variableMap)
          }
          return true
        })
        .map((rule) => rule.rule_id)
    },

    invalidGroupIds(): string[] {
      const invalidRuleIds = new Set(this.invalidRuleIds)
      const invalidGroupIds = new Set<string>()

      this.rules.forEach((rule) => {
        if (invalidRuleIds.has(rule.rule_id)) {
          invalidGroupIds.add(rule.group_id)
        }
      })

      return [...invalidGroupIds]
    },

    canRunSvnUpdate(): boolean {
      return this.sources.length > 0
    },

    hasBlockingConfigIssues(): boolean {
      return this.configIssues.length > 0
    },

    canExecute(): boolean {
      return (
        this.rules.length > 0 &&
        this.invalidRuleIds.length === 0 &&
        !this.hasBlockingConfigIssues
      )
    },
  },

  actions: {
    resetState(): void {
      this.config = createDefaultConfig()
      this.activeTag = null
      this.preferredSourceId = null
      this.sourceMetadataMap = {}
      this.variablePreviewMap = {}
      this.selectedGroupId = UNGROUPED_GROUP.group_id
      this.groupKeyword = ''
      this.currentPage = 1
      this.isLoading = false
      this.isSaving = false
      this.isExecuting = false
      this.isResultPageLoading = false
      this.isResultExporting = false
      this.isUpdatingSvn = false
      this.pageError = ''
      this.configIssues = []
      this.executionMeta = null
      this.abnormalResults = []
      this.abnormalResultTotal = 0
      this.resultId = null
      this.resultCurrentPage = 1
      this.svnUpdateResults = []
      this.svnUpdateSummary = ''
    },

    clearPageError(): void {
      this.pageError = ''
    },

    clearExecutionResult(): void {
      this.executionMeta = null
      this.abnormalResults = []
      this.abnormalResultTotal = 0
      this.resultId = null
      this.resultCurrentPage = 1
      this.isResultPageLoading = false
      this.isResultExporting = false
    },

    setSelectedGroup(groupId: string): void {
      this.selectedGroupId = groupId
      this.currentPage = 1
    },

    setCurrentPage(page: number): void {
      this.currentPage = page
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

    reconcileRuntimeCaches(): void {
      const validSourceIds = new Set(this.sources.map((source) => source.id))
      const validTags = new Set(this.variables.map((variable) => variable.tag))

      this.sourceMetadataMap = Object.fromEntries(
        Object.entries(this.sourceMetadataMap).filter(([sourceId]) => validSourceIds.has(sourceId)),
      )
      this.variablePreviewMap = Object.fromEntries(
        Object.entries(this.variablePreviewMap).filter(([tag]) => validTags.has(tag)),
      )

      if (this.preferredSourceId && !validSourceIds.has(this.preferredSourceId)) {
        this.preferredSourceId = this.sources[0]?.id ?? null
      }
      if (!this.preferredSourceId) {
        this.preferredSourceId = this.sources[0]?.id ?? null
      }

      if (this.activeTag && !validTags.has(this.activeTag)) {
        this.activeTag = null
      }
    },

    applyConfig(config: FixedRulesConfig): void {
      const legacyLocalPresets = config.path_replacement_presets ?? []
      const localPathReplacementPresetMap = new Map<string, string>()
      ;(config.local_path_replacement_presets ?? legacyLocalPresets).forEach((preset) => {
        const normalizedPreset = normalizeReplacementPreset(preset, 'local')
        if (
          normalizedPreset &&
          !localPathReplacementPresetMap.has(normalizedPreset.toLowerCase())
        ) {
          localPathReplacementPresetMap.set(normalizedPreset.toLowerCase(), normalizedPreset)
        }
      })
      const svnPathReplacementPresetMap = new Map<string, string>()
      ;(config.svn_path_replacement_presets ?? []).forEach((preset) => {
        const normalizedPreset = normalizeReplacementPreset(preset, 'svn')
        if (
          normalizedPreset &&
          !svnPathReplacementPresetMap.has(normalizedPreset.toLowerCase())
        ) {
          svnPathReplacementPresetMap.set(normalizedPreset.toLowerCase(), normalizedPreset)
        }
      })
      const localSelectedPresetCandidate =
        config.selected_local_path_replacement_preset ?? config.selected_path_replacement_preset
      const normalizedLocalSelectedPreset = localSelectedPresetCandidate
        ? normalizeReplacementPreset(localSelectedPresetCandidate, 'local')
        : null
      const normalizedSvnSelectedPreset = config.selected_svn_path_replacement_preset
        ? normalizeReplacementPreset(config.selected_svn_path_replacement_preset, 'svn')
        : null

      this.config = {
        ...config,
        version: 6,
        groups: ensureDefaultGroup(config.groups),
        local_path_replacement_presets: [...localPathReplacementPresetMap.values()],
        selected_local_path_replacement_preset:
          normalizedLocalSelectedPreset &&
          localPathReplacementPresetMap.has(normalizedLocalSelectedPreset.toLowerCase())
            ? localPathReplacementPresetMap.get(normalizedLocalSelectedPreset.toLowerCase()) ?? null
            : null,
        svn_path_replacement_presets: [...svnPathReplacementPresetMap.values()],
        selected_svn_path_replacement_preset:
          normalizedSvnSelectedPreset &&
          svnPathReplacementPresetMap.has(normalizedSvnSelectedPreset.toLowerCase())
            ? svnPathReplacementPresetMap.get(normalizedSvnSelectedPreset.toLowerCase()) ?? null
            : null,
      }

      if (!this.config.groups.some((group) => group.group_id === this.selectedGroupId)) {
        this.selectedGroupId = this.config.groups[0]?.group_id ?? UNGROUPED_GROUP.group_id
      }

      this.currentPage = 1
      this.reconcileRuntimeCaches()
    },

    async loadCapabilities(): Promise<void> {
      try {
        const response = await fetchSourceCapabilities()
        this.capabilities = response.data.source_types
      } catch (error) {
        this.pageError = error instanceof Error ? error.message : '获取数据源能力失败。'
      }
    },

    async loadSourceMetadata(sourceId: string, forceRefresh = false): Promise<SourceMetadata> {
      const cached = this.sourceMetadataMap[sourceId]
      if (cached && !forceRefresh) {
        return cached
      }

      const source = this.sources.find((item) => item.id === sourceId)
      if (!source) {
        throw new Error(`未找到数据源“${sourceId}”。`)
      }

      const response = await fetchSourceMetadata(source)
      this.sourceMetadataMap[sourceId] = response.data
      return response.data
    },

    async loadVariablePreview(
      variable: VariableTag,
      limit?: number,
      forceRefresh = false,
    ): Promise<VariablePreviewData> {
      const cached = this.variablePreviewMap[variable.tag]
      const wantsAllRows = limit === undefined || limit === null

      if (cached && !forceRefresh) {
        const cachedLoadsAllRows =
          cached.variable_kind === 'single'
            ? cached.loaded_all_rows ?? cached.preview_rows.length === cached.total_rows
            : cached.loaded_all_rows ?? (cached.loaded_rows ?? 0) === cached.total_rows

        const cachedMatchesLimit =
          cached.variable_kind === 'single'
            ? cached.preview_limit === limit
            : wantsAllRows

        if ((wantsAllRows && cachedLoadsAllRows) || (!wantsAllRows && cachedMatchesLimit)) {
          return cached
        }
      }

      const source = this.sources.find((item) => item.id === variable.source_id)
      if (!source) {
        throw new Error(`变量“${variable.tag}”引用了不存在的数据源“${variable.source_id}”。`)
      }

      const response =
        (variable.variable_kind ?? 'single') === 'composite'
          ? await fetchCompositePreview({
              source,
              sheet: variable.sheet,
              columns: variable.columns ?? [],
              key_column: variable.key_column ?? '',
              append_index_to_key: variable.append_index_to_key ?? false,
            })
          : await fetchColumnPreview({
              source,
              sheet: variable.sheet,
              column: variable.column ?? '',
              limit,
            })

      this.variablePreviewMap[variable.tag] = response.data
      return response.data
    },

    async loadConfig(): Promise<void> {
      this.isLoading = true
      this.pageError = ''
      this.configIssues = []

      try {
        const response = await fetchFixedRulesConfig()
        this.applyConfig(response.data)
        this.configIssues = response.meta?.config_issues ?? []
      } catch (error) {
        this.configIssues = []
        this.pageError = error instanceof Error ? error.message : '读取项目校验配置失败。'
        throw error
      } finally {
        this.isLoading = false
      }
    },

    async saveConfig(): Promise<FixedRulesConfig> {
      this.isSaving = true
      this.pageError = ''

      try {
        const response = await saveFixedRulesConfig({
          ...this.config,
          version: 6,
          groups: ensureDefaultGroup(this.config.groups),
        })
        this.applyConfig(response.data)
        this.configIssues = response.meta?.config_issues ?? []
        return response.data
      } catch (error) {
        this.pageError = error instanceof Error ? error.message : '保存项目校验配置失败。'
        throw error
      } finally {
        this.isSaving = false
      }
    },

    async saveConfigNow(): Promise<void> {
      await this.saveConfig()
    },

    async executeConfig(selectedRuleIds?: string[]): Promise<void> {
      this.isExecuting = true
      this.pageError = ''

      try {
        if (this.hasBlockingConfigIssues) {
          this.pageError = '当前存在读取失败的数据源，请先修复数据源路径管理中的路径问题或重新接入数据源后再执行校验。'
          throw new Error(this.pageError)
        }
        await this.saveConfig()
        const response = await executeFixedRules(
          {
            selected_rule_ids: selectedRuleIds,
            page: 1,
            size: this.resultPageSize,
          },
        )
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
        this.pageError = error instanceof Error ? error.message : '执行项目校验失败。'
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
        const response = await fetchFixedRulesResults(
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
        const file = await exportFixedRulesResults(this.resultId)
        saveApiFile(file)
      } catch (error) {
        this.pageError = error instanceof Error ? error.message : '导出结果失败。'
        throw error
      } finally {
        this.isResultExporting = false
      }
    },

    async runSvnUpdate(): Promise<void> {
      this.isUpdatingSvn = true
      this.pageError = ''

      try {
        await this.saveConfig()
        const response = await triggerFixedRulesSvnUpdate()
        this.svnUpdateResults = response.data.results
        this.svnUpdateSummary = `已处理 ${response.data.total_paths} 个路径，成功更新 ${response.data.updated_paths} 个。`
      } catch (error) {
        this.pageError = error instanceof Error ? error.message : 'SVN 更新失败。'
        throw error
      } finally {
        this.isUpdatingSvn = false
      }
    },

    createGroup(groupName: string): void {
      this.config.groups = ensureDefaultGroup([
        ...this.config.groups,
        {
          group_id: createEntityId('group'),
          group_name: groupName.trim(),
          builtin: false,
        },
      ])
    },

    renameGroup(groupId: string, groupName: string): void {
      this.config.groups = ensureDefaultGroup(
        this.config.groups.map((group) =>
          group.group_id === groupId && !group.builtin
            ? { ...group, group_name: groupName.trim() }
            : group,
        ),
      )
    },

    removeGroup(groupId: string): void {
      if (groupId === UNGROUPED_GROUP.group_id) {
        return
      }

      this.config.groups = ensureDefaultGroup(
        this.config.groups.filter((group) => group.group_id !== groupId),
      )
      this.config.rules = this.config.rules.map((rule) =>
        rule.group_id === groupId ? { ...rule, group_id: UNGROUPED_GROUP.group_id } : rule,
      )
      this.selectedGroupId = this.config.groups[0]?.group_id ?? UNGROUPED_GROUP.group_id
      this.currentPage = 1
    },

    upsertSource(source: DataSource, originalId?: string): void {
      const sourceCopy = { ...source, id: source.id.trim(), pathOrUrl: source.pathOrUrl?.trim() }
      const affectedSourceIds = new Set<string>([sourceCopy.id])

      if (originalId) {
        affectedSourceIds.add(originalId)
      }

      if (originalId && originalId !== sourceCopy.id) {
        const index = this.config.sources.findIndex((item) => item.id === originalId)
        if (index >= 0) {
          this.config.sources.splice(index, 1, sourceCopy)
          this.config.variables = this.config.variables.map((variable) =>
            variable.source_id === originalId ? { ...variable, source_id: sourceCopy.id } : variable,
          )
          this.preferredSourceId = sourceCopy.id
          this.invalidateSourceArtifacts([...affectedSourceIds])
          return
        }
      }

      const index = this.config.sources.findIndex((item) => item.id === sourceCopy.id)
      if (index >= 0) {
        this.config.sources.splice(index, 1, sourceCopy)
      } else {
        this.config.sources.unshift(sourceCopy)
      }

      this.preferredSourceId = sourceCopy.id
      this.invalidateSourceArtifacts([...affectedSourceIds])
    },

    removeSource(sourceId: string): void {
      const removedTags = new Set(
        this.config.variables
          .filter((variable) => variable.source_id === sourceId)
          .map((variable) => variable.tag),
      )

      this.config.sources = this.config.sources.filter((source) => source.id !== sourceId)
      this.config.variables = this.config.variables.filter((variable) => variable.source_id !== sourceId)
      this.config.rules = pruneRulesByRemovedTags(this.config.rules, removedTags)
      this.invalidateSourceArtifacts([sourceId])

      removedTags.forEach((tag) => {
        delete this.variablePreviewMap[tag]
      })

      if (this.activeTag && removedTags.has(this.activeTag)) {
        this.activeTag = null
      }

      if (this.preferredSourceId === sourceId) {
        this.preferredSourceId = this.config.sources[0]?.id ?? null
      }

      const pageCount = Math.max(1, Math.ceil(this.currentGroupRuleTotal / FIXED_RULES_PAGE_SIZE))
      if (this.currentPage > pageCount) {
        this.currentPage = pageCount
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
      const nextTag = variable.tag.trim()
      const variableCopy: VariableTag = {
        ...variable,
        tag: nextTag,
        source_id: variable.source_id.trim(),
        sheet: variable.sheet,
        column: variable.column,
        columns: variable.columns ? [...variable.columns] : undefined,
        key_column: variable.key_column,
        append_index_to_key: variable.append_index_to_key ?? false,
      }

      if (originalTag && originalTag !== nextTag) {
        const index = this.config.variables.findIndex((item) => item.tag === originalTag)
        if (index >= 0) {
          this.config.variables.splice(index, 1, variableCopy)
          this.config.rules = this.config.rules.map((rule) =>
            rule.target_variable_tag === originalTag
              ? { ...rule, target_variable_tag: nextTag }
              : rule,
          )
          delete this.variablePreviewMap[originalTag]
          if (this.activeTag === originalTag) {
            this.activeTag = nextTag
          }
          return
        }
      }

      const index = this.config.variables.findIndex((item) => item.tag === nextTag)
      if (index >= 0) {
        this.config.variables.splice(index, 1, variableCopy)
      } else {
        this.config.variables.push(variableCopy)
      }
    },

    removeVariable(tag: string): void {
      const removedTags = new Set([tag])
      this.config.variables = this.config.variables.filter((variable) => variable.tag !== tag)
      this.config.rules = pruneRulesByRemovedTags(this.config.rules, removedTags)
      delete this.variablePreviewMap[tag]

      if (this.activeTag === tag) {
        this.activeTag = null
      }

      const pageCount = Math.max(1, Math.ceil(this.currentGroupRuleTotal / FIXED_RULES_PAGE_SIZE))
      if (this.currentPage > pageCount) {
        this.currentPage = pageCount
      }
    },

    upsertRule(rule: Omit<FixedRuleDefinition, 'rule_id'> & { rule_id?: string }): void {
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
      const variableMap = new Map(this.config.variables.map((variable) => [variable.tag, variable] as const))
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
        rule_id: rule.rule_id ?? createEntityId('fixed-rule'),
        group_id: rule.group_id,
        rule_name: rule.rule_name.trim(),
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
          rule.rule_type === 'cross_table_mapping' || rule.rule_type === 'dual_composite_compare'
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
      }

      const index = this.config.rules.findIndex((item) => item.rule_id === nextRule.rule_id)
      if (index >= 0) {
        this.config.rules.splice(index, 1, nextRule)
      } else {
        this.config.rules.push(nextRule)
      }
    },

    removeRule(ruleId: string): void {
      this.config.rules = this.config.rules.filter((rule) => rule.rule_id !== ruleId)
      const pageCount = Math.max(1, Math.ceil(this.currentGroupRuleTotal / FIXED_RULES_PAGE_SIZE))
      if (this.currentPage > pageCount) {
        this.currentPage = pageCount
      }
    },

    setSelectedPathReplacementPreset(
      group: SourcePathReplacementGroup,
      path: string | null,
    ): void {
      setSelectedPresetByGroup(
        this.config,
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
        getPresetListByGroup(this.config, group).map((preset) => [preset.toLowerCase(), preset] as const),
      )
      if (!presetMap.has(normalizedPath.toLowerCase())) {
        presetMap.set(normalizedPath.toLowerCase(), normalizedPath)
        setPresetListByGroup(this.config, group, [...presetMap.values()])
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

      const presetList = getPresetListByGroup(this.config, group)
      const nextPresetList = presetList.map((preset) =>
        preset.toLowerCase() === normalizedOriginalPath.toLowerCase()
          ? normalizedNextPath
          : preset,
      )
      setPresetListByGroup(
        this.config,
        group,
        [...new Map(nextPresetList.map((preset) => [preset.toLowerCase(), preset] as const)).values()],
      )

      const selectedPreset =
        group === 'svn'
          ? this.config.selected_svn_path_replacement_preset
          : this.config.selected_local_path_replacement_preset
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
        this.config,
        group,
        getPresetListByGroup(this.config, group).filter(
          (preset) => preset.toLowerCase() !== normalizedPath.toLowerCase(),
        ),
      )

      const selectedPreset =
        group === 'svn'
          ? this.config.selected_svn_path_replacement_preset
          : this.config.selected_local_path_replacement_preset
      if (selectedPreset?.toLowerCase() === normalizedPath.toLowerCase()) {
        this.setSelectedPathReplacementPreset(group, null)
      }
    },

    async replaceSourceBasePath(group: SourcePathReplacementGroup, baseDirectory: string): Promise<{
      updatedCount: number
      skippedCount: number
      failedCount: number
      affectedSourceIds: string[]
    }> {
      const normalizedBaseDirectory = normalizeReplacementPreset(baseDirectory, group)
      const candidateSources: Array<{
        sourceId: string
        source: DataSource
        nextSource: DataSource
        nextPath: string
      }> = []
      const affectedSourceIds = new Set<string>()
      let updatedCount = 0
      let skippedCount = 0

      this.sources.slice().forEach((source) => {
        const isManagedSource =
          group === 'svn' ? isSvnPathManagedSource(source) : isLocalPathManagedSource(source)
        if (!isManagedSource) {
          skippedCount += 1
          return
        }

        const basename = extractSourceBasename(getSourceLocator(source))
        if (!basename) {
          skippedCount += 1
          return
        }

        const nextPath =
          group === 'svn'
            ? joinSvnDirectoryAndBasename(normalizedBaseDirectory, basename)
            : joinDirectoryAndBasename(normalizedBaseDirectory, basename)
        candidateSources.push({
          sourceId: source.id,
          source,
          nextSource: {
            ...source,
            path: group === 'svn' ? undefined : nextPath,
            url: group === 'svn' ? nextPath : source.url,
            pathOrUrl: nextPath,
          },
          nextPath,
        })
      })

      if (!candidateSources.length) {
        return {
          updatedCount,
          skippedCount,
          failedCount: 0,
          affectedSourceIds: [],
        }
      }

      const validationFailures: string[] = []
      const metadataValidatedSourceIds = new Set<string>()
      for (const candidate of candidateSources) {
        try {
          await fetchSourceMetadata(candidate.nextSource)
          metadataValidatedSourceIds.add(candidate.sourceId)
        } catch (error) {
          const reason =
            error instanceof Error ? error.message : '读取数据源元数据失败。'
          validationFailures.push(
            `- ${candidate.sourceId} -> ${candidate.nextPath}：${reason}`,
          )
        }
      }

      for (const candidate of candidateSources) {
        if (!metadataValidatedSourceIds.has(candidate.sourceId)) {
          continue
        }
        const affectedVariables = this.variables.filter(
          (variable) => variable.source_id === candidate.sourceId,
        )

        for (const variable of affectedVariables) {
          const isComposite = (variable.variable_kind ?? 'single') === 'composite'
          try {
            if (isComposite) {
              await fetchCompositePreview({
                source: candidate.nextSource,
                sheet: variable.sheet,
                columns: variable.columns ?? [],
                key_column: variable.key_column ?? '',
                append_index_to_key: variable.append_index_to_key ?? false,
              })
            } else {
              await fetchColumnPreview({
                source: candidate.nextSource,
                sheet: variable.sheet,
                column: variable.column ?? '',
              })
            }
          } catch (error) {
            const reason =
              error instanceof Error ? error.message : '变量预览校验失败。'
            validationFailures.push(
              `- ${candidate.sourceId} / ${variable.tag}：${reason}`,
            )
          }
        }
      }

      if (validationFailures.length) {
        throw new Error(
          [
            `以下${group === 'svn' ? 'SVN 路径' : '本地路径'}替换失败，本次未生效：`,
            ...validationFailures,
          ].join('\n'),
        )
      }

      candidateSources.forEach((candidate) => {
        this.upsertSource(candidate.nextSource, candidate.sourceId)
        affectedSourceIds.add(candidate.sourceId)
        updatedCount += 1
      })

      this.addPathReplacementPreset(group, normalizedBaseDirectory)
      this.setSelectedPathReplacementPreset(group, normalizedBaseDirectory)
      await this.saveConfig()

      let failedCount = 0
      for (const sourceId of affectedSourceIds) {
        try {
          await this.loadSourceMetadata(sourceId)
        } catch {
          failedCount += 1
        }
      }

      const activeVariable = this.variables.find((variable) => variable.tag === this.activeTag)
      if (isAffectedVariable(activeVariable, affectedSourceIds)) {
        try {
          await this.loadVariablePreview(activeVariable, undefined, true)
        } catch {
          // 具体问题会由 configIssues 和数据源行提示呈现，这里只保持交互不中断。
        }
      }

      this.clearExecutionResult()
      this.clearPageError()

      return {
        updatedCount,
        skippedCount,
        failedCount,
        affectedSourceIds: [...affectedSourceIds],
      }
    },
  },
})
