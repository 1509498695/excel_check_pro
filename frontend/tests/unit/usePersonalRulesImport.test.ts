import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  commitWorkbenchImport,
  fetchWorkbenchImportDraft,
  previewWorkbenchImport,
} from '../../src/features/fixed-rules-import/api'
import type {
  WorkbenchImportDraft,
  WorkbenchImportPreview,
} from '../../src/features/fixed-rules-import/types'
import { usePersonalRulesImport } from '../../src/features/fixed-rules-import/usePersonalRulesImport'
import type { FixedRulesConfig, FixedRuleDefinition, FixedRuleGroup } from '../../src/types/fixedRules'
import type { DataSource, VariableTag } from '../../src/types/workbench'

vi.mock('../../src/features/fixed-rules-import/api', () => ({
  commitWorkbenchImport: vi.fn(),
  fetchWorkbenchImportDraft: vi.fn(),
  previewWorkbenchImport: vi.fn(),
}))

const fetchWorkbenchImportDraftMock = vi.mocked(fetchWorkbenchImportDraft)
const previewWorkbenchImportMock = vi.mocked(previewWorkbenchImport)
const commitWorkbenchImportMock = vi.mocked(commitWorkbenchImport)

const source: DataSource = {
  id: 'src-personal',
  type: 'local_excel',
  pathOrUrl: 'D:/data/items.xlsx',
}

const variable: VariableTag = {
  tag: '[items-id]',
  source_id: source.id,
  sheet: 'items',
  variable_kind: 'single',
  column: 'ID',
}

const group: FixedRuleGroup = {
  group_id: 'group-a',
  group_name: '基础规则',
  builtin: false,
}

const rule: FixedRuleDefinition = {
  rule_id: 'rule-a',
  group_id: group.group_id,
  rule_name: 'ID 非空',
  target_variable_tag: variable.tag,
  rule_type: 'not_null',
}

const emptyConfig: FixedRulesConfig = {
  version: 1,
  configured: true,
  sources: [],
  variables: [],
  groups: [],
  rules: [],
  local_path_replacement_presets: [],
  selected_local_path_replacement_preset: null,
  svn_path_replacement_presets: [],
  selected_svn_path_replacement_preset: null,
}

const importSummary = {
  sources_new: 1,
  sources_reused: 0,
  sources_skipped: 0,
  variables_new: 1,
  variables_reused: 0,
  variables_skipped: 0,
  groups_new: 1,
  groups_reused: 0,
  rules_new: 1,
  rules_renamed: 0,
  rules_skipped: 0,
  blocking_errors: 0,
}

const draft: WorkbenchImportDraft = {
  personal_config: {
    ...emptyConfig,
    sources: [source],
    variables: [variable],
    groups: [group],
    rules: [rule],
  },
  project_config: emptyConfig,
  importable_groups: [group],
  importable_rules: [rule],
  importable_sources: [source],
  importable_variables: [variable],
  source_mappings: [
    {
      personal_source: source,
      recommended_action: 'new',
      project_source_id: null,
      next_source: source,
      reason: '项目校验尚无该数据源。',
      candidates: [],
      requires_confirmation: false,
    },
  ],
  conflicts: [],
  summary: importSummary,
}

const preview: WorkbenchImportPreview = {
  summary: importSummary,
  source_results: [],
  variable_results: [],
  group_results: [],
  rule_results: [],
  variable_previews: [],
  conflicts: [],
  blocking_errors: [],
  next_config_preview: draft.personal_config,
}

function getLastPreviewRequest() {
  const lastCall = previewWorkbenchImportMock.mock.calls.at(-1)
  if (!lastCall) {
    throw new Error('previewWorkbenchImport was not called')
  }
  return lastCall[0]
}

describe('usePersonalRulesImport', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    fetchWorkbenchImportDraftMock.mockReset()
    previewWorkbenchImportMock.mockReset()
    commitWorkbenchImportMock.mockReset()
    fetchWorkbenchImportDraftMock.mockResolvedValue({ code: 200, msg: 'ok', data: draft })
    previewWorkbenchImportMock.mockResolvedValue({ code: 200, msg: 'ok', data: preview })
    commitWorkbenchImportMock.mockResolvedValue({
      code: 200,
      msg: 'ok',
      data: draft.personal_config,
      meta: {
        import_summary: importSummary,
        source_results: [],
        variable_results: [],
        group_results: [],
        rule_results: [],
      },
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('loads draft using initial rule ids and initializes import state', async () => {
    const importer = usePersonalRulesImport({ initialRuleIds: () => ['rule-a'] })

    await importer.loadDraft()

    expect(fetchWorkbenchImportDraftMock).toHaveBeenCalledWith({
      selected_rule_ids: ['rule-a'],
      selected_group_ids: undefined,
    })
    expect(importer.draft.value).toEqual(draft)
    expect(importer.scope.mode).toBe('rules')
    expect(importer.scope.rule_ids).toEqual(['rule-a'])
    expect(importer.sourceMappings.value).toEqual([
      {
        personal_source_id: source.id,
        action: 'new',
        project_source_id: null,
        next_source: source,
        confirmed: true,
      },
    ])
  })

  it('sends the current scope, mappings and conflict decisions to preview and commit', async () => {
    const importer = usePersonalRulesImport({ initialRuleIds: ['rule-a'] })
    await importer.loadDraft()
    importer.duplicateRuleActions['rule-a'] = 'rename'
    importer.conflictResolutions.variable_tags['[items-id]'] = '[items-id-project]'

    await importer.runPreview()
    await importer.commit()

    const request = getLastPreviewRequest()
    expect(request).toMatchObject({
      scope: {
        mode: 'rules',
        group_ids: [],
        rule_ids: ['rule-a'],
      },
      selected_rule_ids: ['rule-a'],
      selected_group_ids: null,
      duplicate_rule_actions: {
        'rule-a': 'rename',
      },
      conflict_resolutions: {
        variable_tags: {
          '[items-id]': '[items-id-project]',
        },
        rule_names: {},
        group_names: {},
      },
    })
    expect(request.source_mappings).toEqual(importer.sourceMappings.value)
    expect(commitWorkbenchImportMock).toHaveBeenCalledWith(request)
  })

  it('marks preview stale and refreshes preview when a source locator changes', async () => {
    const importer = usePersonalRulesImport({ initialRuleIds: ['rule-a'] })
    await importer.loadDraft()
    await importer.runPreview()

    importer.updateSourceLocator(source.id, 'D:/data/items-new.xlsx')

    expect(importer.isPreviewStale.value).toBe(true)
    expect(previewWorkbenchImportMock).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(499)
    expect(previewWorkbenchImportMock).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(1)
    expect(previewWorkbenchImportMock).toHaveBeenCalledTimes(2)
    expect(importer.isPreviewStale.value).toBe(false)
    expect(getLastPreviewRequest().source_mappings[0]).toMatchObject({
      personal_source_id: source.id,
      action: 'new',
      next_source: {
        id: source.id,
        type: 'local_excel',
        pathOrUrl: 'D:/data/items-new.xlsx',
        path: 'D:/data/items-new.xlsx',
      },
      confirmed: true,
    })
  })
})
