<script lang="ts">
import type {
  EventTaskAiSuggestion,
  EventTaskFieldMapping,
  EventTaskExtraVariableTask,
  EventTaskRewardMatchStrategy,
  EventTaskPreviewReward,
  EventTaskPreviewRow,
  EventTaskPreviewSampleRow,
  EventTaskRewardValidationResult,
  FixedRuleGroup,
} from '../../types/fixedRules'
import type { DataSource, SourceMetadata, SourceSheetMetadata, VariableTag } from '../../types/workbench'

export type EventTaskRuleDialogMode = 'create' | 'edit'
export type EventTaskParseStrategy = 'group_desc'
export type EventTaskAiParseMode = 'auto' | 'enabled' | 'disabled'
export type EventTaskAiAssistMode = 'auto' | 'on' | 'off'
export type EventTaskValidationScope = 'all' | 'specified'

export interface EventTaskRuleDialogDraft {
  rule_id?: string
  group_id: string
  rule_name: string
  enabled: boolean
  description: string
  feishu_source_id: string
  feishu_sheet_id: string
  feishu_sheet_name: string
  config_variable_tag: string
  parse_strategy: EventTaskParseStrategy
  ai_parse_mode: EventTaskAiParseMode
  ai_assist_mode: EventTaskAiAssistMode
  match_strategy: EventTaskRewardMatchStrategy
  validation_scope: EventTaskValidationScope
  task_group_id_filter: string
  key_delimiter: string
  fallback_match_field: string
  event_task_field_mapping?: EventTaskFieldMapping | null
}

export interface EventTaskRuleDialogValidation {
  status?: 'idle' | 'success' | 'failed'
  errorMessage?: string
  sourceId?: string
  sheetId?: string
  configVariableTag?: string
  matchStrategy?: EventTaskRewardMatchStrategy
  validationScope?: EventTaskValidationScope
  taskGroupIdFilter?: string
  warnings?: string[]
  errors?: string[]
  total?: number
  passCount?: number
  failCount?: number
  unmatchedCount?: number
  warningCount?: number
  results?: EventTaskRewardValidationResult[]
  extraVariableTasks?: EventTaskExtraVariableTask[]
  aiSuggestions?: EventTaskAiSuggestion[]
  aiSuggestionWarnings?: string[]
  aiSuggestionUsed?: boolean
}

export interface EventTaskRuleDialogPreview {
  status?: 'idle' | 'success' | 'failed'
  parseStatus?: 'success' | 'failed'
  warnings?: string[]
  errors?: string[]
  errorMessage?: string
  sourceId?: string
  sheetId?: string
  parseStrategy?: EventTaskParseStrategy
  aiParseMode?: EventTaskAiParseMode
  validationScope?: EventTaskValidationScope
  taskGroupIdFilter?: string
  taskGroupIds?: string[]
  totalRows?: number
  parsedRows?: number
  rewardGroupCount?: number
  sampleRows?: EventTaskPreviewSampleRow[]
  previewRows?: EventTaskPreviewRow[]
  aiSuggestions?: EventTaskAiSuggestion[]
  aiSuggestionWarnings?: string[]
  aiSuggestionUsed?: boolean
}

export type EventTaskFeishuAuthorizationStatus =
  | 'checking'
  | 'authorized'
  | 'pending_authorization'
  | 'error'
  | 'unknown'

export interface EventTaskFeishuAuthorizationState {
  status: EventTaskFeishuAuthorizationStatus
  message?: string
}

export interface EventTaskRuleDialogProps {
  visible: boolean
  mode: EventTaskRuleDialogMode
  draft?: Partial<EventTaskRuleDialogDraft>
  groups?: FixedRuleGroup[]
  feishuSources?: DataSource[]
  sourceMetadataMap?: Record<string, SourceMetadata>
  feishuAuthorizationMap?: Record<string, EventTaskFeishuAuthorizationState>
  taskVariables?: VariableTag[]
  compositeVariables?: VariableTag[]
  preview?: EventTaskRuleDialogPreview
  validation?: EventTaskRuleDialogValidation
  saving?: boolean
  previewing?: boolean
  validating?: boolean
  aiSuggesting?: boolean
  refreshingSheets?: boolean
  backendReady?: boolean
}
</script>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  buildEventTaskErrorDetailText,
  buildEventTaskValidationCsv,
  buildEventTaskValidationCsvFilename,
  downloadCsv,
  formatEventTaskCountMismatches,
  formatEventTaskResultWarnings,
  formatEventTaskRewards,
  getEventTaskResultActualRewards,
  getEventTaskResultCountMismatches,
  getEventTaskResultErrorMessage,
  getEventTaskResultExpectedRewards,
  getEventTaskResultExtraRewards,
  getEventTaskResultMissingRewards,
  getEventTaskResultTaskDesc,
  getEventTaskResultTaskGroupId,
  getEventTaskResultVariableKey,
  hasEventTaskResultWarning,
  isEventTaskResultUnmatched,
  type EventTaskValidationExportMode,
} from '../../utils/eventTaskValidationReport'

const props = withDefaults(defineProps<EventTaskRuleDialogProps>(), {
  draft: undefined,
  groups: () => [],
  feishuSources: () => [],
  sourceMetadataMap: () => ({}),
  feishuAuthorizationMap: () => ({}),
  taskVariables: () => [],
  compositeVariables: () => [],
  preview: undefined,
  validation: undefined,
  saving: false,
  previewing: false,
  validating: false,
  aiSuggesting: false,
  refreshingSheets: false,
  backendReady: true,
})

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'save', payload: EventTaskRuleDialogDraft): void
  (event: 'preview', payload: EventTaskRuleDialogDraft): void
  (event: 'validate', payload: EventTaskRuleDialogDraft): void
  (event: 'ai-analyze', payload: EventTaskRuleDialogDraft): void
  (event: 'refresh-sheets', sourceId: string, forceRefresh?: boolean): void
}>()

const DEFAULT_RULE_DESCRIPTION =
  '节日任务表与项目任务配置表一致性校验规则，校验任务组ID、任务描述及 STR_Loot 奖励内容是否一致。'
const DEFAULT_RULE_NAME = '节日任务校验'
const RULE_DESCRIPTION_MAX_LENGTH = 500
const PREVIEW_PAGE_SIZE = 5

type EventTaskValidationStatusFilter = 'all' | 'pass' | 'fail' | 'unmatched' | 'warning'

interface EventTaskPreviewDisplayRow {
  rowIndex: number
  taskGroupId: string
  desc: string
  rewards: EventTaskPreviewReward[]
  rawLoot?: string | null
}

const form = reactive<EventTaskRuleDialogDraft>(createEmptyDraft())
const previewPage = ref(1)
const validationStatusFilter = ref<EventTaskValidationStatusFilter>('all')
const validationTaskGroupQuery = ref('')
const validationDescQuery = ref('')

const dialogVisible = computed({
  get: () => props.visible,
  set: (value: boolean) => {
    if (!value) {
      emit('close')
    }
  },
})

const dialogTitle = computed(() =>
  props.mode === 'edit' ? '编辑节日任务校验规则' : '新增节日任务校验规则',
)

const feishuSourceOptions = computed(() =>
  props.feishuSources.filter((source) => source.type === 'feishu'),
)

const compositeVariableOptions = computed(() =>
  props.compositeVariables.filter((variable) => (variable.variable_kind ?? 'single') === 'composite'),
)

const selectedFeishuSource = computed(
  () => feishuSourceOptions.value.find((source) => source.id === form.feishu_source_id) ?? null,
)

const selectedSourceMetadata = computed(() => props.sourceMetadataMap[form.feishu_source_id] ?? null)
const selectedAuthorizationState = computed(
  () => props.feishuAuthorizationMap[form.feishu_source_id] ?? { status: 'unknown' as const },
)

const documentAddress = computed(() => {
  const source = selectedFeishuSource.value
  if (!source) {
    return ''
  }
  return getSourceLocator(source)
})

const documentAddressHref = computed(() =>
  /^https?:\/\//i.test(documentAddress.value) ? documentAddress.value : '',
)

const authorizationStatusLabel = computed(() => {
  const metadata = selectedSourceMetadata.value
  const authorizationStatus = selectedAuthorizationState.value.status
  if (!form.feishu_source_id) {
    return '未选择'
  }
  if (authorizationStatus === 'checking') {
    return '检测中'
  }
  if (authorizationStatus === 'pending_authorization') {
    return '未授权'
  }
  if (authorizationStatus === 'error') {
    return '授权异常'
  }
  if (
    authorizationStatus === 'authorized' ||
    metadata?.authorization_status === 'authorized' ||
    (metadata?.sheets?.length ?? 0) > 0
  ) {
    return '已授权'
  }
  if (props.refreshingSheets) {
    return '检测中'
  }
  return '待读取'
})

const isAuthorized = computed(() => {
  const metadata = selectedSourceMetadata.value
  const authorizationStatus = selectedAuthorizationState.value.status
  if (
    authorizationStatus === 'checking' ||
    authorizationStatus === 'pending_authorization' ||
    authorizationStatus === 'error'
  ) {
    return false
  }
  return (
    authorizationStatus === 'authorized' ||
    metadata?.authorization_status === 'authorized' ||
    (metadata?.sheets?.length ?? 0) > 0
  )
})

interface TaskSheetOption {
  sheet_id: string
  name: string
}

const feishuSheetOptions = computed<TaskSheetOption[]>(() => {
  return buildSheetOptions(form.feishu_source_id, form.feishu_sheet_id, form.feishu_sheet_name)
})

const selectedFeishuSheet = computed(
  () => feishuSheetOptions.value.find((sheet) => sheet.sheet_id === form.feishu_sheet_id) ?? null,
)

const selectedConfigVariable = computed(
  () => compositeVariableOptions.value.find((variable) => variable.tag === form.config_variable_tag) ?? null,
)

const currentPreview = computed(() => {
  const preview = props.preview
  if (!preview) {
    return null
  }
  const taskGroupFilter =
    form.validation_scope === 'specified' ? normalizeTaskGroupIdFilter(form.task_group_id_filter) : ''
  if (
    preview.sourceId !== form.feishu_source_id ||
    preview.sheetId !== form.feishu_sheet_id ||
    preview.parseStrategy !== form.parse_strategy ||
    preview.aiParseMode !== toPreviewAiParseMode(form.ai_assist_mode) ||
    preview.validationScope !== form.validation_scope ||
    (preview.taskGroupIdFilter ?? '') !== taskGroupFilter
  ) {
    return null
  }
  return preview
})

const currentValidation = computed(() => {
  const validation = props.validation
  if (!validation) {
    return null
  }
  const taskGroupFilter =
    form.validation_scope === 'specified' ? normalizeTaskGroupIdFilter(form.task_group_id_filter) : ''
  if (
    validation.sourceId !== form.feishu_source_id ||
    validation.sheetId !== form.feishu_sheet_id ||
    validation.configVariableTag !== form.config_variable_tag ||
    validation.matchStrategy !== form.match_strategy ||
    validation.validationScope !== form.validation_scope ||
    (validation.taskGroupIdFilter ?? '') !== taskGroupFilter
  ) {
    return null
  }
  return validation
})

const hasPreviewSelection = computed(() => Boolean(form.feishu_source_id && form.feishu_sheet_id))

const isPreviewSuccessful = computed(
  () => currentPreview.value?.status === 'success' && currentPreview.value.parseStatus === 'success',
)

const previewWarnings = computed(() => currentPreview.value?.warnings ?? [])

const previewErrors = computed(() => currentPreview.value?.errors ?? [])

const previewSampleRows = computed(() => currentPreview.value?.sampleRows ?? [])

const previewDisplayRows = computed<EventTaskPreviewDisplayRow[]>(() => {
  if (!isPreviewSuccessful.value) {
    return []
  }
  const previewRows = currentPreview.value?.previewRows ?? []
  if (previewRows.length) {
    return previewRows.map((row) => ({
      rowIndex: row.row_index,
      taskGroupId: row.task_group_id,
      desc: row.task_desc,
      rewards: row.rewards ?? [],
      rawLoot: row.loot ?? null,
    }))
  }
  return previewSampleRows.value.map((row) => ({
    rowIndex: row.rowIndex,
    taskGroupId: row.taskGroupId,
    desc: row.desc,
    rewards: row.rewards,
    rawLoot: row.rawLoot ?? null,
  }))
})

const paginatedPreviewRows = computed(() => {
  const startIndex = (previewPage.value - 1) * PREVIEW_PAGE_SIZE
  return previewDisplayRows.value.slice(startIndex, startIndex + PREVIEW_PAGE_SIZE)
})

const previewDetailLines = computed(() => paginatedPreviewRows.value.map(buildPreviewSampleLine))

const shouldShowPreviewPagination = computed(
  () => previewDisplayRows.value.length > PREVIEW_PAGE_SIZE,
)

const previewErrorMessage = computed(() => {
  if (!props.backendReady) {
    return '当前环境未启用节日任务解析预览能力。'
  }
  if (!hasPreviewSelection.value) {
    return '请先选择飞书数据源和任务 Sheet。'
  }
  if (!currentPreview.value) {
    return '尚未生成当前配置的解析预览。'
  }
  if (currentPreview.value.status === 'failed') {
    return currentPreview.value.errorMessage || previewErrors.value[0] || '解析预览失败，请检查飞书数据源和 Sheet。'
  }
  if (currentPreview.value.parseStatus === 'failed') {
    return currentPreview.value.errorMessage || previewErrors.value[0] || '未识别到有效的节日任务明细表头。'
  }
  return ''
})

const previewInfoLines = computed(() => {
  if (isPreviewSuccessful.value) {
    const taskGroupIds = currentPreview.value?.taskGroupIds ?? []
    return [
      `识别到任务组ID：${taskGroupIds.length ? taskGroupIds.join('、') : '未识别到任务组ID'}`,
      `识别到任务明细数：${currentPreview.value?.parsedRows ?? 0} 行`,
      `识别到奖励字段组：${currentPreview.value?.rewardGroupCount ?? 0} 组`,
    ]
  }
  return [previewErrorMessage.value || '尚未生成当前配置的解析预览。']
})

const validationRows = computed(() => currentValidation.value?.results ?? [])

const failedValidationRows = computed(() => validationRows.value.filter((row) => row.status === 'fail'))

const validationDerivedStats = computed(() => ({
  missingRewardTaskCount: validationRows.value.filter(
    (row) => getEventTaskResultMissingRewards(row).length > 0,
  ).length,
  extraRewardTaskCount: validationRows.value.filter(
    (row) => getEventTaskResultExtraRewards(row).length > 0,
  ).length,
  countMismatchTaskCount: validationRows.value.filter(
    (row) => getEventTaskResultCountMismatches(row).length > 0,
  ).length,
  unmatchedTaskCount:
    currentValidation.value?.unmatchedCount ??
    validationRows.value.filter((row) => isEventTaskResultUnmatched(row)).length,
}))

const filteredValidationRows = computed(() => {
  const taskGroupQuery = validationTaskGroupQuery.value.trim().toLowerCase()
  const descQuery = validationDescQuery.value.trim().toLowerCase()
  return validationRows.value.filter((row) => {
    if (!matchesValidationStatusFilter(row, validationStatusFilter.value)) {
      return false
    }
    if (
      taskGroupQuery &&
      !getEventTaskResultTaskGroupId(row).toLowerCase().includes(taskGroupQuery)
    ) {
      return false
    }
    if (descQuery && !getEventTaskResultTaskDesc(row).toLowerCase().includes(descQuery)) {
      return false
    }
    return true
  })
})

const validationWarnings = computed(() => currentValidation.value?.warnings ?? [])

const validationErrors = computed(() => currentValidation.value?.errors ?? [])

const extraVariableTasks = computed(() => currentValidation.value?.extraVariableTasks ?? [])

const activeAiSuggestions = computed<EventTaskAiSuggestion[]>(() => {
  if (form.ai_assist_mode === 'off') {
    return []
  }
  const validationSuggestions = currentValidation.value?.aiSuggestions ?? []
  if (validationSuggestions.length) {
    return validationSuggestions
  }
  return currentPreview.value?.aiSuggestions ?? []
})

const activeAiSuggestionWarnings = computed(() => {
  if (form.ai_assist_mode === 'off') {
    return []
  }
  const validationWarnings = currentValidation.value?.aiSuggestionWarnings ?? []
  if (validationWarnings.length) {
    return validationWarnings
  }
  return currentPreview.value?.aiSuggestionWarnings ?? []
})

const activeAiSuggestionUsed = computed(() => {
  if (form.ai_assist_mode === 'off') {
    return false
  }
  return Boolean(currentValidation.value?.aiSuggestionUsed || currentPreview.value?.aiSuggestionUsed)
})

const shouldShowAiSuggestionSection = computed(() => form.ai_assist_mode !== 'off')

const manualFieldMappingSummary = computed(() =>
  buildFieldMappingSummary(form.event_task_field_mapping ?? null),
)

const validationErrorMessage = computed(() => {
  if (!currentValidation.value) {
    return '尚未执行当前配置的奖励校验。'
  }
  if (currentValidation.value.status === 'failed') {
    return currentValidation.value.errorMessage || validationErrors.value[0] || '奖励校验失败。'
  }
  return ''
})

const ruleDescriptionCount = computed(() => form.description.length)

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      resetForm()
      previewPage.value = 1
      resetValidationFilters()
    }
  },
  { immediate: true },
)

watch(
  () => props.draft,
  () => {
    if (props.visible) {
      resetForm()
      previewPage.value = 1
      resetValidationFilters()
    }
  },
  { deep: true },
)

watch(
  () => currentPreview.value,
  () => {
    previewPage.value = 1
  },
)

watch(
  () => currentValidation.value,
  () => {
    resetValidationFilters()
  },
)

watch(
  () => previewDisplayRows.value.length,
  (rowCount) => {
    const maxPage = Math.max(1, Math.ceil(rowCount / PREVIEW_PAGE_SIZE))
    if (previewPage.value > maxPage) {
      previewPage.value = maxPage
    }
  },
)

watch(
  () => form.feishu_source_id,
  () => {
    requestSheetRefreshIfNeeded(form.feishu_source_id)
    const sourceSheetOptions = buildSheetOptions(form.feishu_source_id)
    if (
      !form.feishu_sheet_id ||
      !sourceSheetOptions.some((sheet) => sheet.sheet_id === form.feishu_sheet_id)
    ) {
      const firstSheet = sourceSheetOptions[0]
      form.feishu_sheet_id = firstSheet?.sheet_id ?? ''
      form.feishu_sheet_name = firstSheet?.name ?? ''
    }
  },
)

watch(
  () => form.feishu_sheet_id,
  () => {
    const selectedSheet = selectedFeishuSheet.value
    form.feishu_sheet_name = selectedSheet?.name ?? form.feishu_sheet_name
  },
)

watch(
  feishuSheetOptions,
  (options) => {
    if (form.feishu_sheet_id && options.some((sheet) => sheet.sheet_id === form.feishu_sheet_id)) {
      return
    }
    const firstSheet = options[0]
    form.feishu_sheet_id = firstSheet?.sheet_id ?? ''
    form.feishu_sheet_name = firstSheet?.name ?? ''
  },
)

function buildSheetOptions(
  sourceId: string,
  currentSheetId = '',
  currentSheetName = '',
): TaskSheetOption[] {
  const options = new Map<string, TaskSheetOption>()
  const metadataSheets = props.sourceMetadataMap[sourceId]?.sheets ?? []
  metadataSheets.forEach((sheet: SourceSheetMetadata) => {
    const sheetId = sheet.sheet_id?.trim() || sheet.name.trim()
    if (!sheetId) {
      return
    }
    options.set(sheetId, {
      sheet_id: sheetId,
      name: sheet.name.trim() || sheetId,
    })
  })
  props.taskVariables
    .filter((variable) => !sourceId || variable.source_id === sourceId)
    .forEach((variable) => {
      const sheetName = variable.sheet?.trim() ?? ''
      if (!sheetName || options.has(sheetName)) {
        return
      }
      options.set(sheetName, {
        sheet_id: sheetName,
        name: sheetName,
      })
    })
  if (currentSheetId && !options.has(currentSheetId)) {
    options.set(currentSheetId, {
      sheet_id: currentSheetId,
      name: currentSheetName || currentSheetId,
    })
  }
  return [...options.values()]
}

function createEmptyDraft(): EventTaskRuleDialogDraft {
  return {
    group_id: '',
    rule_name: DEFAULT_RULE_NAME,
    enabled: true,
    description: DEFAULT_RULE_DESCRIPTION,
    feishu_source_id: '',
    feishu_sheet_id: '',
    feishu_sheet_name: '',
    config_variable_tag: '',
    parse_strategy: 'group_desc',
    ai_parse_mode: 'auto',
    ai_assist_mode: 'auto',
    match_strategy: 'groupId_desc_then_taskId',
    validation_scope: 'all',
    task_group_id_filter: '',
    key_delimiter: '_',
    fallback_match_field: 'INT_TaskID',
    event_task_field_mapping: null,
  }
}

function resetForm(): void {
  const draftGroupId = props.draft?.group_id?.trim() ?? ''
  const defaultGroupId =
    props.groups.find((group) => group.group_id === 'ungrouped')?.group_id ??
    props.groups.find((group) => group.group_name === '未分组')?.group_id ??
    props.groups[0]?.group_id ??
    ''
  const draftSourceId = props.draft?.feishu_source_id?.trim() ?? ''
  const firstSourceId = draftSourceId || feishuSourceOptions.value[0]?.id || ''
  const sheetOptions = buildSheetOptions(
    firstSourceId,
    props.draft?.feishu_sheet_id,
    props.draft?.feishu_sheet_name,
  )
  const firstSheet =
    sheetOptions.find((sheet) => sheet.sheet_id === props.draft?.feishu_sheet_id) ?? sheetOptions[0]
  const preferredVariableTag =
    props.draft?.config_variable_tag?.trim() ||
    (compositeVariableOptions.value.find((variable) => variable.sheet === 'EventTask')?.tag ??
      compositeVariableOptions.value.find((variable) => variable.columns?.includes('INT_ID'))?.tag ??
      compositeVariableOptions.value[0]?.tag ??
      '')
  Object.assign(form, {
    ...createEmptyDraft(),
    ...props.draft,
    group_id: draftGroupId || defaultGroupId,
    rule_name: props.draft?.rule_name?.trim() || DEFAULT_RULE_NAME,
    enabled: props.draft?.enabled ?? true,
    description: props.draft?.description ?? DEFAULT_RULE_DESCRIPTION,
    feishu_source_id: firstSourceId,
    feishu_sheet_id: firstSheet?.sheet_id ?? '',
    feishu_sheet_name: firstSheet?.name ?? '',
    config_variable_tag: preferredVariableTag,
    parse_strategy: props.draft?.parse_strategy ?? 'group_desc',
    ai_assist_mode:
      props.draft?.ai_assist_mode ?? toAiAssistMode(props.draft?.ai_parse_mode ?? 'auto'),
    ai_parse_mode: toPreviewAiParseMode(
      props.draft?.ai_assist_mode ?? toAiAssistMode(props.draft?.ai_parse_mode ?? 'auto'),
    ),
    match_strategy: props.draft?.match_strategy ?? 'groupId_desc_then_taskId',
    validation_scope: props.draft?.validation_scope ?? 'all',
    task_group_id_filter: props.draft?.task_group_id_filter ?? '',
    key_delimiter: props.draft?.key_delimiter ?? '_',
    fallback_match_field: props.draft?.fallback_match_field ?? 'INT_TaskID',
    event_task_field_mapping: cloneEventTaskFieldMapping(
      props.draft?.event_task_field_mapping ?? null,
    ),
  })
  requestSheetRefreshIfNeeded(form.feishu_source_id)
}

function buildPayload(): EventTaskRuleDialogDraft {
  const taskGroupFilter =
    form.validation_scope === 'specified'
      ? normalizeTaskGroupIdFilter(form.task_group_id_filter)
      : ''

  return {
    rule_id: form.rule_id?.trim() || undefined,
    group_id: form.group_id.trim(),
    rule_name: form.rule_name.trim(),
    enabled: form.enabled,
    description: form.description.trim(),
    feishu_source_id: form.feishu_source_id.trim(),
    feishu_sheet_id: form.feishu_sheet_id.trim(),
    feishu_sheet_name: form.feishu_sheet_name.trim(),
    config_variable_tag: form.config_variable_tag.trim(),
    parse_strategy: form.parse_strategy,
    ai_assist_mode: form.ai_assist_mode,
    ai_parse_mode: toPreviewAiParseMode(form.ai_assist_mode),
    match_strategy: form.match_strategy,
    validation_scope: form.validation_scope,
    task_group_id_filter: taskGroupFilter,
    key_delimiter: form.key_delimiter.trim() || '_',
    fallback_match_field: form.fallback_match_field.trim() || 'INT_TaskID',
    event_task_field_mapping: cloneEventTaskFieldMapping(form.event_task_field_mapping ?? null),
  }
}

function validateForSave(payload: EventTaskRuleDialogDraft): boolean {
  if (!payload.group_id) {
    ElMessage.warning('请选择规则组。')
    return false
  }
  if (!payload.rule_name) {
    ElMessage.warning('规则名称不能为空。')
    return false
  }
  if (!payload.feishu_source_id) {
    ElMessage.warning('请选择任务数据源。')
    return false
  }
  if (!payload.feishu_sheet_id) {
    ElMessage.warning('请选择任务 Sheet。')
    return false
  }
  if (!payload.config_variable_tag) {
    ElMessage.warning('请选择任务配置组合变量。')
    return false
  }
  if (payload.validation_scope === 'specified' && !payload.task_group_id_filter) {
    ElMessage.warning('请输入指定任务组 ID，多个 ID 用英文逗号分隔。')
    return false
  }
  return true
}

function handleClose(): void {
  emit('close')
}

function handleRefreshSheets(): void {
  const sourceId = form.feishu_source_id.trim()
  if (!sourceId) {
    return
  }
  emit('refresh-sheets', sourceId, true)
}

function handlePreview(): void {
  if (!props.backendReady) {
    ElMessage.info('当前环境未启用节日任务解析预览能力。')
    return
  }
  const payload = buildPayload()
  if (!payload.feishu_source_id) {
    ElMessage.warning('请选择任务数据源。')
    return
  }
  if (!payload.feishu_sheet_id) {
    ElMessage.warning('请选择任务 Sheet。')
    return
  }
  if (!isAuthorized.value) {
    ElMessage.warning('请先完成飞书授权。')
    return
  }
  emit('preview', payload)
}

function handleValidate(): void {
  if (!props.backendReady) {
    ElMessage.info('当前环境未启用节日任务奖励校验能力。')
    return
  }
  const payload = buildPayload()
  if (!validateForSave(payload)) {
    return
  }
  if (!isAuthorized.value) {
    ElMessage.warning('请先完成飞书授权。')
    return
  }
  emit('validate', payload)
}

function handleAiAnalyze(): void {
  if (form.ai_assist_mode !== 'on') {
    return
  }
  if (!props.backendReady) {
    ElMessage.info('当前环境未启用节日任务 AI 辅助建议能力。')
    return
  }
  const payload = buildPayload()
  if (!validateForSave(payload)) {
    return
  }
  if (!isAuthorized.value) {
    ElMessage.warning('请先完成飞书授权。')
    return
  }
  emit('ai-analyze', payload)
}

function handleSave(): void {
  const payload = buildPayload()
  if (!validateForSave(payload)) {
    return
  }
  emit('save', payload)
}

function resetValidationFilters(): void {
  validationStatusFilter.value = 'all'
  validationTaskGroupQuery.value = ''
  validationDescQuery.value = ''
}

function matchesValidationStatusFilter(
  row: EventTaskRewardValidationResult,
  filter: EventTaskValidationStatusFilter,
): boolean {
  if (filter === 'all') {
    return true
  }
  if (filter === 'pass') {
    return row.status === 'pass'
  }
  if (filter === 'fail') {
    return row.status === 'fail'
  }
  if (filter === 'unmatched') {
    return isEventTaskResultUnmatched(row)
  }
  return hasEventTaskResultWarning(row)
}

async function handleCopyValidationDetail(row: EventTaskRewardValidationResult): Promise<void> {
  try {
    await copyTextToClipboard(buildEventTaskErrorDetailText(row))
    ElMessage.success('已复制错误详情。')
  } catch {
    ElMessage.warning('复制失败，请展开详情后手动复制。')
  }
}

function handleExportValidationResults(mode: EventTaskValidationExportMode): void {
  const rows = mode === 'failed' ? failedValidationRows.value : validationRows.value
  if (!rows.length) {
    ElMessage.warning(mode === 'failed' ? '没有失败结果可导出。' : '没有校验结果可导出。')
    return
  }
  const filename = buildEventTaskValidationCsvFilename(mode)
  downloadCsv(filename, buildEventTaskValidationCsv(rows))
  ElMessage.success(mode === 'failed' ? '已导出失败校验结果。' : '已导出全部校验结果。')
}

function handleApplyFieldMappingSuggestion(suggestion: EventTaskAiSuggestion): void {
  const fieldMapping = extractEventTaskFieldMappingSuggestion(suggestion)
  if (!fieldMapping) {
    ElMessage.warning('AI 建议中没有可应用的字段映射。')
    return
  }
  form.event_task_field_mapping = fieldMapping
  ElMessage.success('已应用字段映射建议，请重新生成预览或执行校验。')
}

function getAiSuggestionTitle(suggestion: EventTaskAiSuggestion): string {
  if (suggestion.type === 'field_mapping_suggestion') {
    return '字段映射建议'
  }
  if (suggestion.type === 'match_suggestion') {
    return '任务匹配建议'
  }
  return '异常解释'
}

function formatAiSuggestionConfidence(value: number): string {
  if (!Number.isFinite(value)) {
    return '-'
  }
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`
}

function formatAiSuggestionPayload(payload: Record<string, unknown>): string {
  return Object.entries(payload)
    .filter(([, value]) => value != null && value !== '')
    .map(([key, value]) => `${key}=${formatUnknownValue(value)}`)
    .join('；')
}

function formatUnknownValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => formatUnknownValue(item)).join(', ')
  }
  if (isRecord(value)) {
    return `{${formatAiSuggestionPayload(value)}}`
  }
  return String(value)
}

function canApplyFieldMappingSuggestion(suggestion: EventTaskAiSuggestion): boolean {
  return suggestion.type === 'field_mapping_suggestion' && Boolean(extractEventTaskFieldMappingSuggestion(suggestion))
}

function extractEventTaskFieldMappingSuggestion(
  suggestion: EventTaskAiSuggestion,
): EventTaskFieldMapping | null {
  for (const item of suggestion.suggestions) {
    const candidates = [
      item.event_task_field_mapping,
      item.eventTaskFieldMapping,
      item.field_mapping,
      item.fieldMapping,
      item,
    ]
    for (const candidate of candidates) {
      const mapping = normalizeEventTaskFieldMapping(candidate)
      if (mapping) {
        return mapping
      }
    }
  }
  return null
}

function normalizeEventTaskFieldMapping(value: unknown): EventTaskFieldMapping | null {
  if (!isRecord(value)) {
    return null
  }
  const lootGroups = Array.isArray(value.loot_groups)
    ? value.loot_groups
    : Array.isArray(value.lootGroups)
      ? value.lootGroups
      : []
  const normalizedLootGroups = lootGroups
    .filter(isRecord)
    .map((group) => {
      const itemId = normalizeOptionalText(group.item_id ?? group.itemId)
      const count = normalizeOptionalText(group.count)
      return {
        item_id: itemId ?? '',
        count: count ?? '',
        name: normalizeOptionalText(group.name),
        value_type: normalizeOptionalText(group.value_type ?? group.valueType),
      }
    })
    .filter((group) => group.item_id && group.count)

  const mapping: EventTaskFieldMapping = {
    header_row_index: normalizeOptionalNumber(value.header_row_index ?? value.headerRowIndex),
    task_group_id: normalizeOptionalText(value.task_group_id ?? value.taskGroupId),
    task_id: normalizeOptionalText(value.task_id ?? value.taskId),
    day: normalizeOptionalText(value.day),
    task_desc: normalizeOptionalText(value.task_desc ?? value.taskDesc),
    loot: normalizeOptionalText(value.loot),
    loot_groups: normalizedLootGroups,
  }
  const hasAnyMapping =
    mapping.header_row_index != null ||
    Boolean(mapping.task_group_id) ||
    Boolean(mapping.task_id) ||
    Boolean(mapping.day) ||
    Boolean(mapping.task_desc) ||
    Boolean(mapping.loot) ||
    normalizedLootGroups.length > 0
  return hasAnyMapping ? mapping : null
}

function normalizeOptionalText(value: unknown): string | null {
  if (value == null) {
    return null
  }
  const text = String(value).trim()
  return text || null
}

function normalizeOptionalNumber(value: unknown): number | null {
  if (value == null || value === '') {
    return null
  }
  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : null
}

function cloneEventTaskFieldMapping(
  value: EventTaskFieldMapping | null | undefined,
): EventTaskFieldMapping | null {
  if (!value) {
    return null
  }
  return {
    header_row_index: value.header_row_index ?? null,
    task_group_id: value.task_group_id ?? null,
    task_id: value.task_id ?? null,
    day: value.day ?? null,
    task_desc: value.task_desc ?? null,
    loot: value.loot ?? null,
    loot_groups: (value.loot_groups ?? []).map((group) => ({
      item_id: group.item_id,
      count: group.count,
      name: group.name ?? null,
      value_type: group.value_type ?? null,
    })),
  }
}

function buildFieldMappingSummary(mapping: EventTaskFieldMapping | null): string {
  if (!mapping) {
    return ''
  }
  const segments = [
    mapping.header_row_index ? `表头行 ${mapping.header_row_index}` : '',
    mapping.task_group_id ? `任务组ID=${mapping.task_group_id}` : '',
    mapping.task_id ? `INT_TaskID=${mapping.task_id}` : '',
    mapping.task_desc ? `任务描述=${mapping.task_desc}` : '',
    mapping.loot_groups?.length ? `奖励组 ${mapping.loot_groups.length} 组` : '',
  ].filter(Boolean)
  return segments.join('；')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

async function copyTextToClipboard(text: string): Promise<void> {
  const clipboard = globalThis.navigator?.clipboard
  if (clipboard?.writeText) {
    await clipboard.writeText(text)
    return
  }
  copyTextWithTextarea(text)
}

function copyTextWithTextarea(text: string): void {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', 'readonly')
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  document.body.appendChild(textarea)
  textarea.select()
  const copied = document.execCommand('copy')
  textarea.remove()
  if (!copied) {
    throw new Error('copy failed')
  }
}

function requestSheetRefreshIfNeeded(sourceId: string): void {
  const normalizedSourceId = sourceId.trim()
  if (!props.visible || !normalizedSourceId || props.sourceMetadataMap[normalizedSourceId]?.sheets?.length) {
    return
  }
  const authorizationState = props.feishuAuthorizationMap[normalizedSourceId]
  if (
    authorizationState?.status === 'checking' ||
    authorizationState?.status === 'pending_authorization' ||
    authorizationState?.status === 'error'
  ) {
    return
  }
  emit('refresh-sheets', normalizedSourceId, false)
}

function getSourceLocator(source: DataSource | null): string {
  if (!source) {
    return '未选择飞书数据源'
  }
  return source.pathOrUrl || source.url || source.path || source.id
}

function buildSourceOptionLabel(source: DataSource): string {
  return source.id
}

function getVariableFieldSummary(variable: VariableTag | null): string {
  if (!variable) {
    return '未选择组合变量'
  }
  const fields = variable.columns?.filter(Boolean) ?? []
  if (fields.length) {
    return fields.join(' / ')
  }
  return variable.key_column || variable.tag
}

function buildVariableOptionLabel(variable: VariableTag): string {
  return `${variable.tag} · ${variable.sheet} · ${getVariableFieldSummary(variable)}`
}

function getVariablePathSummary(variable: VariableTag | null): string {
  if (!variable) {
    return '请先选择任务配置组合变量'
  }
  const availableFields = new Set((variable.columns ?? []).map((field) => field.trim()))
  const preferredSummary = ['INT_ID', 'STR_Desc', 'STR_Loot']
    .filter((field) => availableFields.has(field) || variable.key_column?.trim() === field)
    .join(' / ')
  return `${variable.sheet} · ${preferredSummary || getVariableFieldSummary(variable)}`
}

function normalizeTaskGroupIdFilter(value: string): string {
  return value
    .replace(/，/g, ',')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
    .join(', ')
}

function toAiAssistMode(value: EventTaskAiParseMode | EventTaskAiAssistMode): EventTaskAiAssistMode {
  if (value === 'enabled') {
    return 'on'
  }
  if (value === 'disabled') {
    return 'off'
  }
  return value
}

function toPreviewAiParseMode(value: EventTaskAiAssistMode): EventTaskAiParseMode {
  if (value === 'on') {
    return 'enabled'
  }
  if (value === 'off') {
    return 'disabled'
  }
  return 'auto'
}

function handlePreviewPageChange(page: number): void {
  previewPage.value = Math.max(1, page)
}

function formatRewards(
  rewards: EventTaskPreviewReward[] | Array<{ itemId?: number; item_id?: number; count?: number; type?: string | null; name?: string | null }>,
): string {
  return formatEventTaskRewards(rewards)
}

function formatCountMismatches(row: EventTaskRewardValidationResult): string {
  return formatEventTaskCountMismatches(getEventTaskResultCountMismatches(row))
}

function formatRowWarnings(row: EventTaskRewardValidationResult): string {
  return formatEventTaskResultWarnings(row)
}

function buildPreviewSampleLine(row: EventTaskPreviewDisplayRow): string {
  const rewards = row.rewards.length
    ? row.rewards
        .map((reward) => {
          const itemName = reward.name ? `（${reward.name}）` : ''
          return `${reward.itemId}x${reward.count}${itemName}`
        })
        .join(', ')
    : row.rawLoot?.trim() || '无'
  return `第${row.rowIndex}行 / ${row.taskGroupId || '任务组ID为空'} / ${
    row.desc || '任务描述为空'
  } / 奖励 ${rewards}`
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    :title="dialogTitle"
    width="1080px"
    class="package-items-rule-dialog event-task-rule-dialog"
    append-to-body
    destroy-on-close
  >
    <div class="package-items-rule-dialog__body">
      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>基本信息</h3>
            <p>规则归属、命名与启用状态</p>
          </div>
        </div>
        <div class="package-items-rule-dialog__basic-grid">
          <div class="package-items-rule-dialog__field package-items-rule-dialog__field--group">
            <label>规则组</label>
            <el-select v-model="form.group_id" class="w-full" placeholder="选择规则组">
              <el-option
                v-for="group in groups"
                :key="group.group_id"
                :label="group.group_name"
                :value="group.group_id"
              />
            </el-select>
          </div>
          <div class="package-items-rule-dialog__field package-items-rule-dialog__field--name">
            <label>规则名称</label>
            <el-input v-model="form.rule_name" placeholder="例如：26年7月节日任务奖励 vs 配置表校验" />
          </div>
          <div class="package-items-rule-dialog__field package-items-rule-dialog__field--switch">
            <label>启用状态</label>
            <el-switch v-model="form.enabled" />
          </div>
        </div>
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>任务数据源（飞书）</h3>
          </div>
        </div>
        <div class="package-items-rule-dialog__source-grid">
          <div class="package-items-rule-dialog__field">
            <label>飞书数据源</label>
            <el-select
              v-model="form.feishu_source_id"
              class="w-full"
              filterable
              placeholder="选择飞书数据源"
            >
              <el-option
                v-for="source in feishuSourceOptions"
                :key="source.id"
                :label="buildSourceOptionLabel(source)"
                :value="source.id"
              />
            </el-select>
          </div>
          <div class="package-items-rule-dialog__field">
            <label>Sheet 页</label>
            <el-select
              v-model="form.feishu_sheet_id"
              class="w-full"
              filterable
              placeholder="选择飞书 Sheet"
            >
              <el-option
                v-for="sheet in feishuSheetOptions"
                :key="sheet.sheet_id"
                :label="sheet.name"
                :value="sheet.sheet_id"
              />
            </el-select>
          </div>
          <div class="package-items-rule-dialog__field package-items-rule-dialog__field--status">
            <label>授权状态</label>
            <span
              class="package-items-rule-dialog__auth-status"
              :class="{
                'package-items-rule-dialog__auth-status--success': isAuthorized,
                'package-items-rule-dialog__auth-status--warning': !isAuthorized,
              }"
            >
              {{ authorizationStatusLabel }}
            </span>
          </div>
        </div>
        <div class="package-items-rule-dialog__link-row">
          <div class="package-items-rule-dialog__document-link">
            <span>文档地址</span>
            <a
              v-if="documentAddressHref"
              :href="documentAddressHref"
              target="_blank"
              rel="noreferrer"
            >
              {{ documentAddress }}
            </a>
            <strong v-else>{{ documentAddress || '未选择飞书数据源' }}</strong>
          </div>
          <el-button
            size="small"
            :loading="refreshingSheets"
            :disabled="!form.feishu_source_id"
            @click="handleRefreshSheets"
          >
            刷新 Sheet 列表
          </el-button>
        </div>
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>任务配置组合变量</h3>
          </div>
        </div>
        <div class="package-items-rule-dialog__field">
          <label>组合变量</label>
          <el-select
            v-model="form.config_variable_tag"
            class="w-full"
            filterable
            placeholder="选择任务配置组合变量"
          >
            <el-option
              v-for="variable in compositeVariableOptions"
              :key="variable.tag"
              :label="buildVariableOptionLabel(variable)"
              :value="variable.tag"
            />
          </el-select>
          <div class="package-items-rule-dialog__field-path">
            {{ getVariablePathSummary(selectedConfigVariable) }}
          </div>
        </div>
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>匹配策略</h3>
          </div>
        </div>
        <div class="package-items-rule-dialog__strategy-grid">
          <div class="package-items-rule-dialog__field">
            <label>匹配策略</label>
            <el-select v-model="form.match_strategy" class="w-full">
              <el-option label="任务组ID + 描述，失败后按任务ID兜底" value="groupId_desc_then_taskId" />
              <el-option label="任务组ID + 描述" value="groupId_desc" />
              <el-option label="任务组ID + INT_TaskID" value="groupId_taskId" />
            </el-select>
          </div>
          <div class="package-items-rule-dialog__field">
            <label>AI 辅助解析</label>
            <el-radio-group v-model="form.ai_assist_mode" class="event-task-rule-dialog__mode-radios">
              <el-radio label="auto">自动</el-radio>
              <el-radio label="on">开启</el-radio>
              <el-radio label="off">关闭</el-radio>
            </el-radio-group>
          </div>
        </div>
        <div class="event-task-rule-dialog__strategy-help">
          <span>key 分隔符：{{ form.key_delimiter || '_' }}</span>
          <span>任务组ID：取 key 前缀</span>
          <span>备用匹配：{{ form.fallback_match_field || 'INT_TaskID' }}</span>
          <span v-if="manualFieldMappingSummary">人工字段映射：{{ manualFieldMappingSummary }}</span>
        </div>
      </section>

      <section v-if="shouldShowAiSuggestionSection" class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>AI 建议，仅供参考</h3>
            <p>建议不会改变解析结果和校验状态</p>
          </div>
          <el-button
            v-if="form.ai_assist_mode === 'on'"
            size="small"
            plain
            :loading="aiSuggesting"
            :disabled="aiSuggesting"
            @click="handleAiAnalyze"
          >
            AI 分析当前结果
          </el-button>
        </div>
        <div class="event-task-rule-dialog__ai-box">
          <div
            v-if="!activeAiSuggestions.length && !activeAiSuggestionWarnings.length"
            class="event-task-rule-dialog__ai-empty"
          >
            {{
              form.ai_assist_mode === 'auto'
                ? '当前规则解析未触发 AI 分析。'
                : '尚未请求 AI 分析。'
            }}
          </div>
          <div
            v-for="suggestion in activeAiSuggestions"
            :key="`${suggestion.type}-${suggestion.reason}-${suggestion.confidence}`"
            class="event-task-rule-dialog__ai-card"
          >
            <div class="event-task-rule-dialog__ai-card-head">
              <strong>{{ getAiSuggestionTitle(suggestion) }}</strong>
              <span>置信度 {{ formatAiSuggestionConfidence(suggestion.confidence) }}</span>
            </div>
            <div class="event-task-rule-dialog__ai-reason">{{ suggestion.reason || '-' }}</div>
            <div
              v-for="(item, index) in suggestion.suggestions"
              :key="index"
              class="event-task-rule-dialog__ai-item"
            >
              {{ formatAiSuggestionPayload(item) }}
            </div>
            <el-button
              v-if="canApplyFieldMappingSuggestion(suggestion)"
              size="small"
              type="primary"
              plain
              @click="handleApplyFieldMappingSuggestion(suggestion)"
            >
              应用字段映射建议
            </el-button>
          </div>
          <div v-if="activeAiSuggestionWarnings.length" class="event-task-rule-dialog__preview-warnings">
            <div v-for="warning in activeAiSuggestionWarnings" :key="warning">AI Warning：{{ warning }}</div>
          </div>
          <div v-if="activeAiSuggestionUsed" class="event-task-rule-dialog__ai-footnote">
            AI 建议未参与最终校验结果。
          </div>
        </div>
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>校验结果</h3>
          </div>
          <div class="event-task-rule-dialog__validation-actions">
            <el-button
              size="small"
              plain
              :disabled="!validationRows.length"
              @click="handleExportValidationResults('all')"
            >
              导出全部
            </el-button>
            <el-button
              size="small"
              plain
              :disabled="!failedValidationRows.length"
              @click="handleExportValidationResults('failed')"
            >
              导出失败
            </el-button>
            <el-button
              size="small"
              type="primary"
              :loading="validating"
              :disabled="validating"
              @click="handleValidate"
            >
              执行校验
            </el-button>
          </div>
        </div>
        <div
          v-if="currentValidation?.status === 'success'"
          class="event-task-rule-dialog__validation"
        >
          <div class="event-task-rule-dialog__summary-grid">
            <div>总任务数：{{ currentValidation.total ?? 0 }}</div>
            <div>通过数：{{ currentValidation.passCount ?? 0 }}</div>
            <div>失败数：{{ currentValidation.failCount ?? 0 }}</div>
            <div>未匹配数：{{ validationDerivedStats.unmatchedTaskCount }}</div>
            <div>Warning 数：{{ currentValidation.warningCount ?? 0 }}</div>
            <div>缺失奖励任务数：{{ validationDerivedStats.missingRewardTaskCount }}</div>
            <div>多余奖励任务数：{{ validationDerivedStats.extraRewardTaskCount }}</div>
            <div>数量不一致任务数：{{ validationDerivedStats.countMismatchTaskCount }}</div>
          </div>
          <div v-if="validationRows.length" class="event-task-rule-dialog__filters">
            <el-radio-group v-model="validationStatusFilter" class="event-task-rule-dialog__filter-status">
              <el-radio label="all">全部</el-radio>
              <el-radio label="pass">只看通过</el-radio>
              <el-radio label="fail">只看失败</el-radio>
              <el-radio label="unmatched">只看未匹配</el-radio>
              <el-radio label="warning">只看 warning</el-radio>
            </el-radio-group>
            <el-input
              v-model="validationTaskGroupQuery"
              clearable
              class="event-task-rule-dialog__filter-input"
              placeholder="按任务组ID筛选"
            />
            <el-input
              v-model="validationDescQuery"
              clearable
              class="event-task-rule-dialog__filter-input"
              placeholder="按任务描述关键词搜索"
            />
          </div>
          <el-table
            v-if="filteredValidationRows.length"
            :data="filteredValidationRows"
            size="small"
            class="event-task-rule-dialog__result-table"
          >
            <el-table-column type="expand">
              <template #default="{ row }">
                <div class="event-task-rule-dialog__reward-detail">
                  <div>飞书行号：{{ row.feishuRowIndex ?? row.feishu_row_index ?? '-' }}</div>
                  <div>任务组ID：{{ getEventTaskResultTaskGroupId(row) || '-' }}</div>
                  <div>任务描述：{{ getEventTaskResultTaskDesc(row) || '任务描述为空' }}</div>
                  <div>组合变量 key：{{ getEventTaskResultVariableKey(row) || '-' }}</div>
                  <div>Expected：{{ formatRewards(getEventTaskResultExpectedRewards(row)) }}</div>
                  <div>Actual：{{ formatRewards(getEventTaskResultActualRewards(row)) }}</div>
                  <div>缺失奖励：{{ formatRewards(getEventTaskResultMissingRewards(row)) }}</div>
                  <div>多余奖励：{{ formatRewards(getEventTaskResultExtraRewards(row)) }}</div>
                  <div>数量不一致：{{ formatCountMismatches(row) }}</div>
                  <div>Parse Warning：{{ formatRowWarnings(row) }}</div>
                  <div>错误信息：{{ getEventTaskResultErrorMessage(row) || '-' }}</div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="任务组ID" min-width="110">
              <template #default="{ row }">{{ getEventTaskResultTaskGroupId(row) }}</template>
            </el-table-column>
            <el-table-column label="任务描述" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">{{ getEventTaskResultTaskDesc(row) || '任务描述为空' }}</template>
            </el-table-column>
            <el-table-column label="飞书行号" width="90">
              <template #default="{ row }">{{ row.feishuRowIndex ?? row.feishu_row_index ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="组合变量 key" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ getEventTaskResultVariableKey(row) || '-' }}</template>
            </el-table-column>
            <el-table-column label="匹配策略" width="130">
              <template #default="{ row }">{{ row.matchStrategy || row.match_strategy }}</template>
            </el-table-column>
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <span
                  :class="{
                    'event-task-rule-dialog__status-pass': row.status === 'pass',
                    'event-task-rule-dialog__status-fail': row.status === 'fail',
                  }"
                >
                  {{ row.status === 'pass' ? '通过' : '失败' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="缺失奖励" min-width="130" show-overflow-tooltip>
              <template #default="{ row }">{{ formatRewards(getEventTaskResultMissingRewards(row)) }}</template>
            </el-table-column>
            <el-table-column label="多余奖励" min-width="130" show-overflow-tooltip>
              <template #default="{ row }">{{ formatRewards(getEventTaskResultExtraRewards(row)) }}</template>
            </el-table-column>
            <el-table-column label="数量不一致" min-width="130" show-overflow-tooltip>
              <template #default="{ row }">{{ formatCountMismatches(row) }}</template>
            </el-table-column>
            <el-table-column label="Warning" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">{{ formatRowWarnings(row) }}</template>
            </el-table-column>
            <el-table-column label="错误信息" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ getEventTaskResultErrorMessage(row) || '-' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button
                  v-if="row.status === 'fail'"
                  size="small"
                  plain
                  @click="handleCopyValidationDetail(row)"
                >
                  复制详情
                </el-button>
                <span v-else>-</span>
              </template>
            </el-table-column>
          </el-table>
          <div v-else class="event-task-rule-dialog__empty-result">
            {{ validationRows.length ? '暂无符合筛选条件的校验结果' : '暂无校验明细' }}
          </div>
          <div v-if="extraVariableTasks.length" class="event-task-rule-dialog__extra-tasks">
            <div v-for="task in extraVariableTasks" :key="task.variableKey || task.variable_key">
              多余组合变量：{{ task.taskGroupId || task.task_group_id }} /
              {{ task.taskDesc || task.task_desc || '任务描述为空' }} /
              {{ task.variableKey || task.variable_key }}
            </div>
          </div>
          <div v-if="validationWarnings.length" class="event-task-rule-dialog__preview-warnings">
            <div v-for="warning in validationWarnings" :key="warning">Warning：{{ warning }}</div>
          </div>
        </div>
        <div v-else class="package-items-rule-dialog__preview-box">
          <div>{{ validationErrorMessage }}</div>
          <div v-if="validationErrors.length" class="event-task-rule-dialog__preview-errors">
            <div v-for="error in validationErrors" :key="error">Error：{{ error }}</div>
          </div>
        </div>
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>校验范围</h3>
          </div>
        </div>
        <el-radio-group v-model="form.validation_scope" class="package-items-rule-dialog__scope-radios">
          <el-radio label="all">全部任务</el-radio>
          <el-radio label="specified">指定任务组 ID</el-radio>
        </el-radio-group>
        <el-input
          v-if="form.validation_scope === 'specified'"
          v-model="form.task_group_id_filter"
          class="package-items-rule-dialog__scope-input"
          placeholder="请输入任务组ID，多个用英文逗号分隔"
        />
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>解析预览</h3>
          </div>
          <el-button
            size="small"
            type="primary"
            :loading="previewing"
            :disabled="previewing"
            @click="handlePreview"
          >
            生成预览
          </el-button>
        </div>
        <div class="package-items-rule-dialog__preview-box">
          <div v-for="line in previewInfoLines" :key="line">{{ line }}</div>
          <div
            v-for="line in previewDetailLines"
            :key="line"
            class="event-task-rule-dialog__preview-detail-line"
          >
            {{ line }}
          </div>
          <div v-if="shouldShowPreviewPagination" class="event-task-rule-dialog__preview-pagination">
            <el-pagination
              small
              background
              layout="prev, pager, next"
              :current-page="previewPage"
              :page-size="PREVIEW_PAGE_SIZE"
              :total="previewDisplayRows.length"
              @current-change="handlePreviewPageChange"
            />
          </div>
          <div v-if="previewWarnings.length" class="event-task-rule-dialog__preview-warnings">
            <div v-for="warning in previewWarnings" :key="warning">Warning：{{ warning }}</div>
          </div>
          <div v-if="previewErrors.length" class="event-task-rule-dialog__preview-errors">
            <div v-for="error in previewErrors" :key="error">Error：{{ error }}</div>
          </div>
        </div>
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>规则说明</h3>
          </div>
        </div>
        <div class="package-items-rule-dialog__textarea-wrap">
          <el-input
            v-model="form.description"
            type="textarea"
            :maxlength="RULE_DESCRIPTION_MAX_LENGTH"
            :rows="3"
            resize="none"
          />
          <div class="package-items-rule-dialog__counter">
            {{ ruleDescriptionCount }} / {{ RULE_DESCRIPTION_MAX_LENGTH }}
          </div>
        </div>
      </section>
    </div>

    <template #footer>
      <div class="package-items-rule-dialog__footer">
        <el-button :disabled="saving" @click="handleClose">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存规则</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.package-items-rule-dialog__body {
  max-height: calc(100vh - 190px);
  overflow-y: auto;
  padding: 0 6px 0 0;
}

.package-items-rule-dialog__section {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 14px 0;
  border-bottom: 1px solid var(--color-border, #e5e7eb);
}

.package-items-rule-dialog__section:first-child {
  padding-top: 0;
}

.package-items-rule-dialog__section:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.package-items-rule-dialog__section-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
}

.package-items-rule-dialog__section-head h3 {
  margin: 0;
  color: var(--color-ink-900, #111827);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0;
}

.package-items-rule-dialog__section-head p {
  margin: 2px 0 0;
  color: var(--color-ink-500, #6b7280);
  font-size: 12px;
}

.package-items-rule-dialog__basic-grid {
  display: grid;
  grid-template-columns: minmax(240px, 320px) minmax(300px, 400px) minmax(110px, 140px);
  align-items: end;
  gap: 24px;
}

.package-items-rule-dialog__source-grid {
  display: grid;
  grid-template-columns: minmax(240px, 320px) minmax(240px, 320px) minmax(110px, 160px);
  align-items: end;
  gap: 24px;
}

.package-items-rule-dialog__strategy-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 0.55fr);
  gap: 24px;
}

.package-items-rule-dialog__field {
  min-width: 0;
}

.package-items-rule-dialog__field label {
  display: block;
  margin-bottom: 6px;
  color: var(--color-ink-500, #64748b);
  font-size: 12px;
  font-weight: 500;
  line-height: 18px;
}

.package-items-rule-dialog__field--switch {
  justify-self: end;
  min-width: 110px;
}

.package-items-rule-dialog__field--status {
  align-self: end;
}

.package-items-rule-dialog__auth-status {
  display: inline-flex;
  min-height: 32px;
  align-items: center;
  color: var(--color-ink-500, #6b7280);
  font-size: 13px;
  font-weight: 600;
}

.package-items-rule-dialog__auth-status--success {
  color: #16a34a;
}

.package-items-rule-dialog__auth-status--warning {
  color: #d97706;
}

.package-items-rule-dialog__link-row {
  display: flex;
  min-height: 24px;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px 24px;
  font-size: 13px;
  line-height: 20px;
}

.package-items-rule-dialog__document-link {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 18px;
}

.package-items-rule-dialog__document-link span {
  flex: 0 0 auto;
  color: var(--color-ink-500, #6b7280);
  font-weight: 500;
}

.package-items-rule-dialog__document-link a {
  color: #0f62fe;
  text-decoration: none;
  word-break: break-all;
}

.package-items-rule-dialog__document-link a:hover {
  text-decoration: underline;
}

.package-items-rule-dialog__document-link strong {
  color: var(--color-ink-700, #334155);
  font-weight: 500;
  word-break: break-all;
}

.package-items-rule-dialog__field-path {
  margin-top: 8px;
  color: var(--color-ink-500, #64748b);
  font-size: 12px;
  line-height: 18px;
  word-break: break-all;
}

.event-task-rule-dialog__mode-radios {
  display: flex;
  min-height: 32px;
  align-items: center;
  flex-wrap: wrap;
  gap: 28px;
}

.event-task-rule-dialog__strategy-help {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 28px;
  border-radius: 6px;
  background: #f5f7fb;
  padding: 10px 14px;
  color: var(--color-ink-500, #64748b);
  font-size: 12px;
  line-height: 18px;
}

.package-items-rule-dialog__scope-input {
  margin-top: 10px;
  max-width: 520px;
}

.package-items-rule-dialog__scope-radios {
  display: flex;
  flex-wrap: wrap;
  gap: 28px;
}

.package-items-rule-dialog__preview-box {
  border-radius: 6px;
  background: #f5f7fb;
  padding: 12px 16px;
  color: var(--color-ink-600, #475569);
  font-size: 13px;
  line-height: 24px;
}

.event-task-rule-dialog__preview-detail-line {
  word-break: break-all;
}

.event-task-rule-dialog__preview-pagination {
  display: flex;
  justify-content: center;
  margin-top: 10px;
}

.event-task-rule-dialog__preview-warnings {
  margin-top: 8px;
  color: #b45309;
}

.event-task-rule-dialog__preview-errors {
  margin-top: 8px;
  color: #b91c1c;
}

.event-task-rule-dialog__ai-box {
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-radius: 6px;
  background: #f5f7fb;
  padding: 12px 16px;
  color: var(--color-ink-600, #475569);
  font-size: 13px;
  line-height: 22px;
}

.event-task-rule-dialog__ai-empty,
.event-task-rule-dialog__ai-footnote {
  color: var(--color-ink-500, #64748b);
}

.event-task-rule-dialog__ai-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 6px;
  background: #fff;
  padding: 10px 12px;
}

.event-task-rule-dialog__ai-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--color-ink-800, #1f2937);
}

.event-task-rule-dialog__ai-card-head span {
  color: var(--color-ink-500, #64748b);
  font-size: 12px;
}

.event-task-rule-dialog__ai-reason,
.event-task-rule-dialog__ai-item {
  word-break: break-all;
}

.event-task-rule-dialog__validation {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.event-task-rule-dialog__validation-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.event-task-rule-dialog__summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 8px;
  border-radius: 6px;
  background: #f5f7fb;
  padding: 10px 14px;
  color: var(--color-ink-600, #475569);
  font-size: 13px;
  line-height: 20px;
}

.event-task-rule-dialog__filters {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(150px, 190px) minmax(180px, 240px);
  align-items: center;
  gap: 10px;
}

.event-task-rule-dialog__filter-status {
  min-width: 0;
}

.event-task-rule-dialog__filter-input {
  width: 100%;
}

.event-task-rule-dialog__result-table {
  width: 100%;
}

.event-task-rule-dialog__reward-detail {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 18px;
  color: var(--color-ink-700, #334155);
  font-size: 12px;
  line-height: 18px;
  word-break: break-all;
}

.event-task-rule-dialog__status-pass {
  color: #16a34a;
  font-weight: 600;
}

.event-task-rule-dialog__status-fail {
  color: #dc2626;
  font-weight: 600;
}

.event-task-rule-dialog__empty-result,
.event-task-rule-dialog__extra-tasks {
  border-radius: 6px;
  background: #f5f7fb;
  padding: 10px 14px;
  color: var(--color-ink-600, #475569);
  font-size: 13px;
  line-height: 22px;
}

.package-items-rule-dialog__textarea-wrap {
  position: relative;
}

.package-items-rule-dialog__counter {
  position: absolute;
  right: 12px;
  bottom: 8px;
  color: var(--color-ink-500, #64748b);
  font-size: 12px;
  line-height: 16px;
}

.package-items-rule-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: 16px;
}

:global(.event-task-rule-dialog .el-dialog__body) {
  padding: 18px 24px 0;
}

:global(.event-task-rule-dialog .el-dialog__footer) {
  margin-top: 0;
  border-top: 1px solid var(--color-border, #e5e7eb);
  padding: 16px 24px 18px;
}

:global(.event-task-rule-dialog .el-textarea__inner) {
  min-height: var(--ui-textarea-min-height-md, 80px) !important;
  padding-bottom: 28px;
}

@media (max-width: 900px) {
  .package-items-rule-dialog__basic-grid,
  .package-items-rule-dialog__source-grid,
  .package-items-rule-dialog__strategy-grid {
    grid-template-columns: 1fr;
  }

  .package-items-rule-dialog__field--switch {
    justify-self: start;
  }

  .package-items-rule-dialog__section-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .event-task-rule-dialog__summary-grid {
    grid-template-columns: 1fr;
  }

  .event-task-rule-dialog__filters {
    grid-template-columns: 1fr;
  }
}
</style>
