import type { WorkbenchState } from './state'
import { fetchWorkbenchConfig, saveWorkbenchConfig } from '../../api/workbench'
import type { FixedRuleDefinition, FixedRuleGroup } from '../../types/fixedRules'
import type { DataSource, VariableTag } from '../../types/workbench'
import { normalizeReplacementPreset } from '../../utils/sourcePathReplacement'
import { UNGROUPED_GROUP } from '../../utils/ruleOrchestrationModel'
import { resetExecutionState } from './executionActions'

export function hasWorkbenchContentForPersistence(state: WorkbenchState): boolean {
  return Boolean(
    state.sources.length ||
      state.variables.length ||
      state.ruleGroups.length > 1 ||
      state.orchestrationRules.length,
  )
}

type WorkbenchPersistenceContext = WorkbenchState & {
  _autoSaveTimer?: ReturnType<typeof setTimeout>
}

export function getAutoSavePayload(state: WorkbenchState): Record<string, unknown> {
  return {
    sources: state.sources,
    variables: state.variables,
    ruleGroups: state.ruleGroups,
    orchestrationRules: state.orchestrationRules,
    local_path_replacement_presets: state.localPathReplacementPresets,
    selected_local_path_replacement_preset: state.selectedLocalPathReplacementPreset,
    svn_path_replacement_presets: state.svnPathReplacementPresets,
    selected_svn_path_replacement_preset: state.selectedSvnPathReplacementPreset,
  }
}

export async function saveConfigNowAction(state: WorkbenchState): Promise<void> {
  state.autoSaveStatus = 'saving'
  state.autoSaveError = ''
  try {
    await saveWorkbenchConfig(getAutoSavePayload(state))
    state.autoSaveStatus = 'saved'
    state.autoSaveSavedAt = Date.now()
  } catch (error) {
    state.autoSaveStatus = 'failed'
    state.autoSaveError = error instanceof Error ? error.message : '保存个人校验配置失败。'
    throw error
  }
}

export function scheduleAutoSaveAction(state: WorkbenchPersistenceContext): void {
  if (state._autoSaveTimer) {
    clearTimeout(state._autoSaveTimer)
  }
  state._autoSaveTimer = setTimeout(() => {
    state._autoSaveTimer = undefined
    saveConfigNowAction(state).catch(() => {
      /* 自动保存失败仅更新状态，不打断用户输入。 */
    })
  }, 2000)
}

export async function loadFromServerAction(state: WorkbenchState): Promise<void> {
  try {
    const response = await fetchWorkbenchConfig()
    const data = response.data

    state.sources = []
    state.variables = []
    state.ruleGroups = [{ ...UNGROUPED_GROUP }]
    state.orchestrationRules = []
    Object.assign(state, resetExecutionState())
    state.isUpdatingSvn = false
    state.svnUpdateResults = []
    state.svnUpdateSummary = ''
    state.sourceMetadataMap = {}
    state.variablePreviewMap = {}
    state.sourceIssues = {}
    state.activeTag = null
    state.preferredSourceId = null
    state.localPathReplacementPresets = []
    state.selectedLocalPathReplacementPreset = null
    state.svnPathReplacementPresets = []
    state.selectedSvnPathReplacementPreset = null
    state.autoSaveStatus = 'idle'
    state.autoSaveError = ''
    state.autoSaveSavedAt = null

    if (data && typeof data === 'object') {
      if (Array.isArray(data.sources)) state.sources = data.sources as DataSource[]
      if (Array.isArray(data.variables)) state.variables = data.variables as VariableTag[]
      if (Array.isArray(data.ruleGroups)) {
        state.ruleGroups = data.ruleGroups as FixedRuleGroup[]
      }
      if (Array.isArray(data.orchestrationRules)) {
        state.orchestrationRules = data.orchestrationRules as FixedRuleDefinition[]
      }
      const legacyPresetPayload =
        (data as Record<string, unknown>).path_replacement_presets ??
        (data as Record<string, unknown>).pathReplacementPresets
      const localPresetPayload =
        (data as Record<string, unknown>).local_path_replacement_presets ?? legacyPresetPayload
      const svnPresetPayload = (data as Record<string, unknown>).svn_path_replacement_presets
      if (Array.isArray(localPresetPayload)) {
        state.localPathReplacementPresets = (localPresetPayload as unknown[])
          .map((preset) => normalizeReplacementPreset(String(preset ?? ''), 'local'))
          .filter(Boolean)
      }
      if (Array.isArray(svnPresetPayload)) {
        state.svnPathReplacementPresets = (svnPresetPayload as unknown[])
          .map((preset) => normalizeReplacementPreset(String(preset ?? ''), 'svn'))
          .filter(Boolean)
      }
      const legacySelectedPreset =
        (data as Record<string, unknown>).selected_path_replacement_preset ??
        (data as Record<string, unknown>).selectedPathReplacementPreset
      const localSelectedPreset =
        (data as Record<string, unknown>).selected_local_path_replacement_preset ??
        legacySelectedPreset
      const svnSelectedPreset =
        (data as Record<string, unknown>).selected_svn_path_replacement_preset
      state.selectedLocalPathReplacementPreset =
        typeof localSelectedPreset === 'string'
          ? normalizeReplacementPreset(localSelectedPreset, 'local')
          : null
      state.selectedSvnPathReplacementPreset =
        typeof svnSelectedPreset === 'string'
          ? normalizeReplacementPreset(svnSelectedPreset, 'svn')
          : null
    }
  } catch {
    /* 首次加载无数据正常 */
  }
}
