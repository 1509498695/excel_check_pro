import type { FixedRuleDefinition, FixedRuleGroup } from '../../types/fixedRules'
import type {
  AbnormalResult,
  DataSource,
  ExecutionMeta,
  SourceMetadata,
  SourceType,
  VariablePreviewData,
  VariableTag,
  WorkbenchSvnUpdateItem,
} from '../../types/workbench'
import { UNGROUPED_GROUP } from '../../utils/ruleOrchestrationModel'

export interface WorkbenchState {
  sources: DataSource[]
  variables: VariableTag[]
  ruleGroups: FixedRuleGroup[]
  orchestrationRules: FixedRuleDefinition[]
  selectedGroupId: string
  groupKeyword: string
  orchestrationCurrentPage: number
  capabilities: SourceType[]
  isExecuting: boolean
  isResultPageLoading: boolean
  isResultExporting: boolean
  isUpdatingSvn: boolean
  pageError: string
  abnormalResults: AbnormalResult[]
  abnormalResultTotal: number
  executionMeta: ExecutionMeta | null
  resultId: number | null
  resultCurrentPage: number
  resultPageSize: number
  svnUpdateResults: WorkbenchSvnUpdateItem[]
  svnUpdateSummary: string
  activeTag: string | null
  preferredSourceId: string | null
  sourceMetadataMap: Record<string, SourceMetadata>
  variablePreviewMap: Record<string, VariablePreviewData>
  sourceIssues: Record<string, string>
  localPathReplacementPresets: string[]
  selectedLocalPathReplacementPreset: string | null
  svnPathReplacementPresets: string[]
  selectedSvnPathReplacementPreset: string | null
  autoSaveStatus: 'idle' | 'saving' | 'saved' | 'failed'
  autoSaveError: string
  autoSaveSavedAt: number | null
}

export function createWorkbenchState(): WorkbenchState {
  return {
    sources: [],
    variables: [],
    ruleGroups: [{ ...UNGROUPED_GROUP }],
    orchestrationRules: [],
    selectedGroupId: UNGROUPED_GROUP.group_id,
    groupKeyword: '',
    orchestrationCurrentPage: 1,
    capabilities: [],
    isExecuting: false,
    isResultPageLoading: false,
    isResultExporting: false,
    isUpdatingSvn: false,
    pageError: '',
    abnormalResults: [],
    abnormalResultTotal: 0,
    executionMeta: null,
    resultId: null,
    resultCurrentPage: 1,
    resultPageSize: 20,
    svnUpdateResults: [],
    svnUpdateSummary: '',
    activeTag: null,
    preferredSourceId: null,
    sourceMetadataMap: {},
    variablePreviewMap: {},
    sourceIssues: {},
    localPathReplacementPresets: [],
    selectedLocalPathReplacementPreset: null,
    svnPathReplacementPresets: [],
    selectedSvnPathReplacementPreset: null,
    autoSaveStatus: 'idle',
    autoSaveError: '',
    autoSaveSavedAt: null,
  }
}
