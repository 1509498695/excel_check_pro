<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Collection,
  CopyDocument,
  Document,
  Download,
  FolderOpened,
  MoreFilled,
  Plus,
  Refresh,
  SuccessFilled,
  Upload,
  VideoPlay,
  View,
  WarningFilled,
} from '@element-plus/icons-vue'

import CollapsibleSection from '../components/shell/CollapsibleSection.vue'
import MetricCard from '../components/shell/MetricCard.vue'
import PageHeader from '../components/shell/PageHeader.vue'
import PrimaryButton from '../components/shell/PrimaryButton.vue'
import SecondaryButton from '../components/shell/SecondaryButton.vue'
import DataSourcePanel from '../components/workbench/DataSourcePanel.vue'
import {
  createReferenceCategory as createReferenceCategoryApi,
  deleteReferenceFile,
  exportTestCaseWorkbook,
  fetchReferenceCategories,
  fetchReferenceFiles,
  generateTestCases,
  readPlanningSnapshot,
  readPlanningSnapshotBrief,
  setRecommendedPrimaryReference,
  uploadReferenceFile,
} from '../api/testCases'
import { fetchSourceMetadata, fetchWorkbenchConfig, saveWorkbenchConfig } from '../api/workbench'
import type { SourceManagementStoreLike } from '../types/panelStores'
import type { ApiFileResponse } from '../types/api'
import type {
  GenerationWarning,
  PlanningSnapshotResponse,
  ReferenceCategoryResponse,
  ReferenceFileResponse,
  ReferenceProfile,
  ReferenceSheetOption as BackendReferenceSheetOption,
  TestCaseGenerationResponse,
  TestCaseGenerationRequest,
} from '../types/testCases'
import type { DataSource, SourceMetadata } from '../types/workbench'

type PreviewTab = 'brief' | 'cases' | 'warnings'
type Priority = string
type ReferenceFileType = 'xlsx' | 'md' | 'txt'
type ReferenceTypeFilter = 'all' | ReferenceFileType
type ReferenceSort = 'recommended' | 'newest' | 'name'

interface TestCaseGenerationPlanningSourceConfig {
  planning_sources: DataSource[]
  preferred_planning_source_id: string | null
  selected_planning_sheet_name: string | null
}

interface ReferenceFile {
  id: string
  backendId: number
  categoryId: string
  categoryNumericId: number | null
  name: string
  type: ReferenceFileType
  tag?: string
  summary: string
  uploadedBy: string
  uploadedAt: string
  caseCount?: number
  profileSummary: string
  warnings?: string[]
  isRecommendedPrimary?: boolean
  defaultSheetName?: string
  sheetOptions?: ReferenceSheetOption[]
  profile?: ReferenceProfile | null
}

interface ReferenceCategory {
  id: string
  backendId: number | null
  name: string
  description: string
  referenceCount: number
}

interface ReferenceSheetOption {
  sheetName: string
  sheetIndex: number
  isDefault?: boolean
  caseCount?: number
}

interface GeneratedCase {
  id: string
  module: string
  checkpoint: string
  title: string
  priority: Priority
  status: string
  remarks: string
}

const activeTab = ref<PreviewTab>('cases')
const selectedReferenceCategoryId = ref('')
const selectedReferenceIds = ref<string[]>([])
const primaryReferenceId = ref('')
const selectedReferenceSheetName = ref('')
const referenceSearchKeyword = ref('')
const referenceTypeFilter = ref<ReferenceTypeFilter>('all')
const referenceSort = ref<ReferenceSort>('recommended')
const referenceCurrentPage = ref(1)
const createCategoryDialogVisible = ref(false)
const uploadReferenceDialogVisible = ref(false)
const profilePreviewDialogVisible = ref(false)
const referenceMoreDialogVisible = ref(false)
const newReferenceCategoryName = ref('')
const createCategoryError = ref('')
const referenceApiErrorMessage = ref('')
const uploadReferenceError = ref('')
const referenceUploadFile = ref<File | null>(null)
const isReferenceLibraryLoading = ref(false)
const isCreatingReferenceCategory = ref(false)
const isUploadingReference = ref(false)
const isUpdatingReference = ref(false)
const profilePreviewFileId = ref('')
const referenceMoreFileId = ref('')
const isGeneratedResultStale = ref(false)
const generatedResultStaleReason = ref('')
const selectedPlanningSourceId = ref('')
const selectedPlanningSheetName = ref('')
const planningSourceCollapsed = ref(false)
const planningSourcePanelRef = ref<{ openCreateDialog: () => void } | null>(null)
const planningSnapshot = ref<PlanningSnapshotResponse | null>(null)
const snapshotBriefMarkdown = ref('')
const snapshotBriefWarnings = ref<GenerationWarning[]>([])
const snapshotBriefErrorMessage = ref('')
const generationResult = ref<TestCaseGenerationResponse | null>(null)
const apiErrorMessage = ref('')
const isSnapshotLoading = ref(false)
const isSnapshotBriefLoading = ref(false)
const isGeneratingCases = ref(false)
const isExportingCases = ref(false)
const snapshotBriefParticipatedInLastGeneration = ref<boolean | null>(null)
const workbenchConfigSnapshot = ref<Record<string, unknown>>({})
const hasLoadedWorkbenchConfig = ref(false)
const isPlanningSourceConfigHydrating = ref(false)
const planningSourcePersistenceError = ref('')

let snapshotBriefRequestId = 0
let hasPlanningSourceConfigLocalEdits = false
let isApplyingPlanningSourceConfig = false

const referencePageSize = 5
const TEST_CASE_GENERATION_CONFIG_KEY = 'test_case_generation'
const PLANNING_SOURCE_TYPES = new Set<string>(['local_excel', 'feishu', 'svn'])

const planningSourceStore = reactive<SourceManagementStoreLike>({
  sources: [],
  capabilities: ['local_excel', 'feishu', 'svn'],
  preferredSourceId: null,
  sourceMetadataMap: {},
  svnPathReplacementPresets: [],
  selectedSvnPathReplacementPreset: null,
  async loadSourceMetadata(sourceId: string): Promise<SourceMetadata> {
    const source = planningSourceStore.sources.find((item) => item.id === sourceId)
    if (!source) {
      throw new Error(`未找到策划案来源“${sourceId}”。`)
    }
    const cached = planningSourceStore.sourceMetadataMap?.[sourceId]
    if (cached) {
      return cached
    }
    const response = await fetchSourceMetadata(source)
    const metadata = response.data
    if (planningSourceStore.sourceMetadataMap) {
      planningSourceStore.sourceMetadataMap[sourceId] = metadata
    }
    return metadata
  },
  upsertSource(source: DataSource, originalId?: string): void {
    const normalizedSource = {
      ...source,
      id: source.id.trim(),
      pathOrUrl: source.pathOrUrl?.trim(),
    }
    const targetId = originalId ?? normalizedSource.id
    const existingIndex = planningSourceStore.sources.findIndex((item) => item.id === targetId)

    if (existingIndex >= 0) {
      planningSourceStore.sources.splice(existingIndex, 1, normalizedSource)
    } else {
      planningSourceStore.sources.unshift(normalizedSource)
    }

    if (originalId && originalId !== normalizedSource.id && planningSourceStore.sourceMetadataMap) {
      const previousMetadata = planningSourceStore.sourceMetadataMap[originalId]
      delete planningSourceStore.sourceMetadataMap[originalId]
      if (previousMetadata) {
        planningSourceStore.sourceMetadataMap[normalizedSource.id] = {
          ...previousMetadata,
          source_id: normalizedSource.id,
          source_type: normalizedSource.type,
        }
      }
    }

    planningSourceStore.preferredSourceId = normalizedSource.id
    selectedPlanningSourceId.value = normalizedSource.id
    queuePlanningSourceConfigPersist()
  },
  removeSource(sourceId: string): void {
    planningSourceStore.sources = planningSourceStore.sources.filter((source) => source.id !== sourceId)
    if (planningSourceStore.sourceMetadataMap) {
      delete planningSourceStore.sourceMetadataMap[sourceId]
    }
    if (selectedPlanningSourceId.value === sourceId) {
      selectedPlanningSourceId.value = planningSourceStore.sources[0]?.id ?? ''
    }
    planningSourceStore.preferredSourceId = selectedPlanningSourceId.value || null
    if (!selectedPlanningSourceId.value) {
      selectedPlanningSheetName.value = ''
    }
    queuePlanningSourceConfigPersist()
  },
  useSampleSource(): void {
    // 用例生成页不提供演示来源，避免生产页面出现假数据。
  },
})

const REFERENCE_UNCATEGORIZED_CATEGORY_ID = 'uncategorized'

const referenceCategories = ref<ReferenceCategory[]>([])
const referenceFiles = ref<ReferenceFile[]>([])

const generatedCases = computed<GeneratedCase[]>(() =>
  (generationResult.value?.cases ?? []).map((caseItem, index) => ({
    id: caseItem.case_id || `TC-${String(index + 1).padStart(3, '0')}`,
    module: caseItem.module || caseItem.feature || '-',
    checkpoint: caseItem.feature || caseItem.scenario || caseItem.case_type || '-',
    title: caseItem.title || caseItem.scenario || caseItem.source_requirement || '-',
    priority: caseItem.priority || 'P2',
    status: caseItem.initial_status || '未执行',
    remarks: caseItem.remarks || caseItem.config_source || '-',
  })),
)

const warnings = computed<string[]>(() => {
  const warningItems: GenerationWarning[] = generationResult.value
    ? [...generationResult.value.warnings, ...(generationResult.value.blueprint.warnings ?? [])]
    : planningSnapshot.value?.warnings ?? []
  return [...new Set(warningItems.map((warning) => warning.message).filter(Boolean))]
})

const tabs: Array<{ key: PreviewTab; label: string }> = [
  { key: 'brief', label: 'AI 整理稿' },
  { key: 'cases', label: '测试用例' },
  { key: 'warnings', label: '限制提示' },
]

const selectedPlanningSource = computed(
  () => planningSourceStore.sources.find((source) => source.id === selectedPlanningSourceId.value) ?? null,
)
const selectedPlanningSheetOptions = computed(
  () => planningSourceStore.sourceMetadataMap?.[selectedPlanningSourceId.value]?.sheets ?? [],
)
const hasPlanningSheetOptions = computed(() => selectedPlanningSheetOptions.value.length > 0)

const currentReferenceCategory = computed(
  () => referenceCategories.value.find((category) => category.id === selectedReferenceCategoryId.value) ?? null,
)
const currentCategoryReferenceFiles = computed(() =>
  referenceFiles.value.filter((file) => file.categoryId === selectedReferenceCategoryId.value),
)
const referenceCategoryCounts = computed<Record<string, number>>(() =>
  referenceFiles.value.reduce<Record<string, number>>((counts, file) => {
    counts[file.categoryId] = (counts[file.categoryId] ?? 0) + 1
    return counts
  }, {}),
)
const filteredReferenceFiles = computed(() => {
  const keyword = referenceSearchKeyword.value.trim().toLowerCase()
  const filtered = currentCategoryReferenceFiles.value.filter((file) => {
    const matchesType = referenceTypeFilter.value === 'all' || file.type === referenceTypeFilter.value
    if (!matchesType) {
      return false
    }
    if (!keyword) {
      return true
    }

    return `${file.name} ${file.summary} ${file.profileSummary}`.toLowerCase().includes(keyword)
  })

  return [...filtered].sort((first, second) => {
    if (referenceSort.value === 'recommended') {
      const recommendedDelta = Number(Boolean(second.isRecommendedPrimary)) - Number(Boolean(first.isRecommendedPrimary))
      if (recommendedDelta !== 0) {
        return recommendedDelta
      }
      return new Date(second.uploadedAt).getTime() - new Date(first.uploadedAt).getTime()
    }
    if (referenceSort.value === 'newest') {
      return new Date(second.uploadedAt).getTime() - new Date(first.uploadedAt).getTime()
    }
    return first.name.localeCompare(second.name, 'zh-Hans-CN')
  })
})
const referenceTotalPages = computed(() => Math.max(1, Math.ceil(filteredReferenceFiles.value.length / referencePageSize)))
const visibleReferenceFiles = computed(() => {
  const startIndex = (referenceCurrentPage.value - 1) * referencePageSize
  return filteredReferenceFiles.value.slice(startIndex, startIndex + referencePageSize)
})
const referencePageStart = computed(() =>
  filteredReferenceFiles.value.length ? (referenceCurrentPage.value - 1) * referencePageSize + 1 : 0,
)
const referencePageEnd = computed(() =>
  Math.min(referenceCurrentPage.value * referencePageSize, filteredReferenceFiles.value.length),
)
const referencePageNumbers = computed(() => {
  const totalPages = referenceTotalPages.value
  if (totalPages <= 5) {
    return Array.from({ length: totalPages }, (_, index) => index + 1)
  }

  const startPage = Math.min(Math.max(referenceCurrentPage.value - 2, 1), totalPages - 4)
  return Array.from({ length: 5 }, (_, index) => startPage + index)
})
const selectedReferenceFiles = computed(() =>
  currentCategoryReferenceFiles.value.filter((file) => selectedReferenceIds.value.includes(file.id)),
)
const primaryReference = computed(
  () => selectedReferenceFiles.value.find((file) => file.id === primaryReferenceId.value) ?? null,
)
const selectedReferenceSheetOptions = computed(() => primaryReference.value?.sheetOptions ?? [])
const hasReferenceSheetOptions = computed(() => selectedReferenceSheetOptions.value.length > 0)
const selectedReferenceSheet = computed(
  () =>
    selectedReferenceSheetOptions.value.find((sheet) => sheet.sheetName === selectedReferenceSheetName.value) ??
    selectedReferenceSheetOptions.value.find((sheet) => sheet.isDefault) ??
    selectedReferenceSheetOptions.value[0],
)
const referenceCaseCountDisplay = computed(() => {
  if (!primaryReference.value) {
    return '未使用主参考'
  }
  const caseCount = hasReferenceSheetOptions.value ? selectedReferenceSheet.value?.caseCount : primaryReference.value?.caseCount

  return typeof caseCount === 'number' ? `约 ${caseCount} 条` : '未识别'
})
const hasPlanningSnapshot = computed(() => Boolean(planningSnapshot.value))
const hasGeneratedResult = computed(() => Boolean(generationResult.value))
const hasSnapshotBriefMarkdown = computed(() => Boolean(snapshotBriefMarkdown.value.trim()))
const canReadSnapshot = computed(() => Boolean(selectedPlanningSource.value && selectedPlanningSheetName.value))
const isGenerationReady = computed(() => hasPlanningSnapshot.value && !isSnapshotLoading.value && !isGeneratingCases.value)
const prioritySummary = computed(() => Object.entries(generationResult.value?.stats.priority_counts ?? {}))
const snapshotBriefWarningMessages = computed(() =>
  snapshotBriefWarnings.value.map((warning) => warning.message).filter(Boolean),
)
const snapshotFirstRowSummary = computed(() => {
  const firstRow = planningSnapshot.value?.rows[0]
  if (!firstRow) {
    return ''
  }
  return firstRow.cells
    .map((cell) => cell.value)
    .filter(Boolean)
    .join(' / ')
})
const previewStatusLabel = computed(() => {
  if (generationResult.value) {
    return '用例已生成'
  }
  if (planningSnapshot.value) {
    return '快照已读取'
  }
  return '待读取快照'
})
const previewStatusType = computed(() => (generationResult.value ? 'primary' : planningSnapshot.value ? 'success' : 'info'))
const canExportGeneratedResult = computed(() => hasGeneratedResult.value && !isGeneratedResultStale.value)
const selectedReferenceSummary = computed(() => {
  if (!selectedReferenceFiles.value.length) {
    return '未选择参考案例 · 使用 qa-case 标准生成'
  }
  if (!primaryReference.value) {
    return `已选 ${selectedReferenceFiles.value.length} 个 · 未指定主参考`
  }
  return `已选 ${selectedReferenceFiles.value.length} 个 · 主参考：${primaryReference.value.name}`
})
const profilePreviewFile = computed(
  () => referenceFiles.value.find((file) => file.id === profilePreviewFileId.value) ?? null,
)
const referenceMoreFile = computed(() => referenceFiles.value.find((file) => file.id === referenceMoreFileId.value) ?? null)
const metrics = computed(() => [
  {
    label: '快照行数',
    value: planningSnapshot.value ? `${planningSnapshot.value.rows.length} 行` : '未读取',
    statusLabel: planningSnapshot.value ? '已读取' : '待读取',
    statusType: planningSnapshot.value ? ('success' as const) : ('neutral' as const),
    iconTone: 'primary' as const,
  },
  {
    label: '本次参考',
    value: `${selectedReferenceFiles.value.length} 个`,
    statusLabel: primaryReference.value ? '含主参考' : selectedReferenceFiles.value.length ? '补充参考' : '可选增强',
    statusType: primaryReference.value || selectedReferenceFiles.value.length ? ('success' as const) : ('neutral' as const),
    iconTone: 'success' as const,
  },
  {
    label: '预览用例',
    value: generationResult.value ? `${generationResult.value.stats.total} 条` : '未生成',
    statusLabel: generationResult.value ? '未保存' : '待生成',
    statusType: generationResult.value ? ('neutral' as const) : ('neutral' as const),
    iconTone: 'purple' as const,
  },
  {
    label: '限制提示',
    value: `${warnings.value.length} 条`,
    statusLabel: warnings.value.length ? '需确认' : '暂无',
    statusType: warnings.value.length ? ('warning' as const) : ('neutral' as const),
    iconTone: 'warning' as const,
  },
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isPlanningSourceType(value: unknown): value is DataSource['type'] {
  return typeof value === 'string' && PLANNING_SOURCE_TYPES.has(value)
}

function normalizePlanningSource(value: unknown): DataSource | null {
  if (!isRecord(value) || !isPlanningSourceType(value.type)) {
    return null
  }

  const sourceId = typeof value.id === 'string' ? value.id.trim() : ''
  if (!sourceId) {
    return null
  }

  const source: DataSource = {
    id: sourceId,
    type: value.type,
  }
  if (typeof value.path === 'string') {
    source.path = value.path
  }
  if (typeof value.url === 'string') {
    source.url = value.url
  }
  if (typeof value.pathOrUrl === 'string') {
    source.pathOrUrl = value.pathOrUrl.trim()
  }
  if (typeof value.token === 'string') {
    source.token = value.token
  }
  return source
}

function normalizePlanningSourceConfig(rawConfig: unknown): TestCaseGenerationPlanningSourceConfig {
  if (!isRecord(rawConfig)) {
    return {
      planning_sources: [],
      preferred_planning_source_id: null,
      selected_planning_sheet_name: null,
    }
  }

  const planningSources = Array.isArray(rawConfig.planning_sources)
    ? rawConfig.planning_sources
        .map(normalizePlanningSource)
        .filter((source): source is DataSource => Boolean(source))
    : []
  const preferredSourceId =
    typeof rawConfig.preferred_planning_source_id === 'string' && rawConfig.preferred_planning_source_id.trim()
      ? rawConfig.preferred_planning_source_id.trim()
      : null
  const selectedSheetName =
    typeof rawConfig.selected_planning_sheet_name === 'string' && rawConfig.selected_planning_sheet_name.trim()
      ? rawConfig.selected_planning_sheet_name.trim()
      : null

  return {
    planning_sources: planningSources,
    preferred_planning_source_id: preferredSourceId,
    selected_planning_sheet_name: selectedSheetName,
  }
}

function buildPlanningSourceConfig(): TestCaseGenerationPlanningSourceConfig {
  const preferredSourceId = selectedPlanningSourceId.value || planningSourceStore.preferredSourceId || null
  return {
    planning_sources: planningSourceStore.sources.map((source) => ({ ...source })),
    preferred_planning_source_id: preferredSourceId,
    selected_planning_sheet_name: selectedPlanningSheetName.value.trim() || null,
  }
}

function applyPlanningSourceConfig(config: TestCaseGenerationPlanningSourceConfig): void {
  isApplyingPlanningSourceConfig = true
  planningSourceStore.sources = config.planning_sources
  planningSourceStore.sourceMetadataMap = {}
  planningSourceStore.preferredSourceId = config.preferred_planning_source_id

  const preferredSourceId = config.preferred_planning_source_id
  const restoredSourceId =
    preferredSourceId && config.planning_sources.some((source) => source.id === preferredSourceId)
      ? preferredSourceId
      : config.planning_sources[0]?.id ?? ''

  selectedPlanningSourceId.value = restoredSourceId
  selectedPlanningSheetName.value = restoredSourceId ? config.selected_planning_sheet_name ?? '' : ''
  void nextTick(() => {
    isApplyingPlanningSourceConfig = false
  })
}

function queuePlanningSourceConfigPersist(): void {
  hasPlanningSourceConfigLocalEdits = true
  void persistPlanningSourceConfig()
}

async function persistPlanningSourceConfig(): Promise<void> {
  if (isPlanningSourceConfigHydrating.value) {
    return
  }
  if (!hasLoadedWorkbenchConfig.value) {
    planningSourcePersistenceError.value = '策划案来源保存失败：尚未读取到当前工作台配置，避免覆盖个人校验配置。'
    return
  }

  const payload: Record<string, unknown> = {
    ...workbenchConfigSnapshot.value,
    [TEST_CASE_GENERATION_CONFIG_KEY]: buildPlanningSourceConfig(),
  }
  planningSourcePersistenceError.value = ''

  try {
    await saveWorkbenchConfig(payload)
    workbenchConfigSnapshot.value = payload
    hasPlanningSourceConfigLocalEdits = false
  } catch (error) {
    planningSourcePersistenceError.value = getApiErrorMessage(error, '策划案来源保存失败，刷新后可能无法保留。')
  }
}

async function loadPlanningSourceConfig(): Promise<void> {
  isPlanningSourceConfigHydrating.value = true
  planningSourcePersistenceError.value = ''
  let loadedWorkbenchConfig = false

  try {
    const response = await fetchWorkbenchConfig()
    const config = isRecord(response.data) ? { ...response.data } : {}
    loadedWorkbenchConfig = true
    hasLoadedWorkbenchConfig.value = true
    workbenchConfigSnapshot.value = config

    if (!hasPlanningSourceConfigLocalEdits) {
      applyPlanningSourceConfig(normalizePlanningSourceConfig(config[TEST_CASE_GENERATION_CONFIG_KEY]))
    }
  } catch (error) {
    planningSourcePersistenceError.value = getApiErrorMessage(error, '读取策划案来源保存配置失败。')
  } finally {
    isPlanningSourceConfigHydrating.value = false
  }

  if (loadedWorkbenchConfig && hasPlanningSourceConfigLocalEdits) {
    void persistPlanningSourceConfig()
  }
}

watch(
  selectedPlanningSourceId,
  (sourceId, previousSourceId) => {
    if (previousSourceId !== undefined && sourceId !== previousSourceId) {
      clearSnapshotAndGeneratedResult()
    }
    const shouldPersistSourceChange =
      previousSourceId !== undefined &&
      sourceId !== previousSourceId &&
      !isPlanningSourceConfigHydrating.value &&
      !isApplyingPlanningSourceConfig
    const firstSheetName = selectedPlanningSheetOptions.value[0]?.name ?? ''
    if (!sourceId) {
      selectedPlanningSheetName.value = ''
    } else if (firstSheetName && !selectedPlanningSheetOptions.value.some((sheet) => sheet.name === selectedPlanningSheetName.value)) {
      selectedPlanningSheetName.value = firstSheetName
    }
    void ensurePlanningSourceMetadata(sourceId).then((metadata) => {
      if (!metadata || selectedPlanningSourceId.value !== sourceId) {
        return
      }
      if (!metadata.sheets.some((sheet) => sheet.name === selectedPlanningSheetName.value)) {
        selectedPlanningSheetName.value = metadata.sheets[0]?.name ?? ''
      }
      if (shouldPersistSourceChange) {
        queuePlanningSourceConfigPersist()
      }
    })
    planningSourceStore.preferredSourceId = sourceId || null
    if (shouldPersistSourceChange && !sourceId) {
      queuePlanningSourceConfigPersist()
    }
  },
  { immediate: true },
)

watch(
  () => planningSourceStore.sources.map((source) => source.id),
  (sourceIds) => {
    if (sourceIds.includes(selectedPlanningSourceId.value)) {
      return
    }
    selectedPlanningSourceId.value = sourceIds[0] ?? ''
  },
)

watch(
  selectedPlanningSheetOptions,
  (sheetOptions) => {
    if (sheetOptions.some((sheet) => sheet.name === selectedPlanningSheetName.value)) {
      return
    }
    selectedPlanningSheetName.value = sheetOptions[0]?.name ?? ''
  },
)

watch(selectedPlanningSheetName, (sheetName, previousSheetName) => {
  if (previousSheetName !== undefined && sheetName !== previousSheetName) {
    clearSnapshotAndGeneratedResult()
  }
})

watch([referenceSearchKeyword, referenceTypeFilter, referenceSort], () => {
  referenceCurrentPage.value = 1
})

watch(referenceTotalPages, (totalPages) => {
  if (referenceCurrentPage.value > totalPages) {
    referenceCurrentPage.value = totalPages
  }
})

function getPriorityType(priority: Priority): 'danger' | 'warning' | 'primary' {
  if (priority === 'P0') {
    return 'danger'
  }
  if (priority === 'P1') {
    return 'warning'
  }
  return 'primary'
}

function getReferenceCategoryCount(categoryId: string): number {
  return currentReferenceCategory.value?.id === categoryId
    ? currentReferenceCategory.value.referenceCount
    : referenceCategories.value.find((category) => category.id === categoryId)?.referenceCount ??
        referenceCategoryCounts.value[categoryId] ??
        0
}

function getReferenceTypeLabel(type: ReferenceFileType): string {
  if (type === 'xlsx') {
    return 'Excel'
  }
  if (type === 'md') {
    return 'Markdown'
  }
  return 'TXT'
}

function getReferenceTypeClass(type: ReferenceFileType): string {
  return `is-${type}`
}

function formatReferenceUploadTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

function getReferenceFileType(suffix: string): ReferenceFileType {
  const normalizedSuffix = suffix.toLowerCase().replace(/^\./, '')
  if (normalizedSuffix === 'md') {
    return 'md'
  }
  if (normalizedSuffix === 'txt') {
    return 'txt'
  }
  return 'xlsx'
}

function getReferenceSourceTypeLabel(sourceType: ReferenceProfile['source_type']): string {
  if (sourceType === 'excel') {
    return 'Excel'
  }
  if (sourceType === 'markdown') {
    return 'Markdown'
  }
  return 'TXT'
}

function mapReferenceSheetOption(sheet: BackendReferenceSheetOption, index: number): ReferenceSheetOption {
  return {
    sheetName: sheet.name,
    sheetIndex: index,
    isDefault: sheet.is_default,
    caseCount: sheet.reference_case_count,
  }
}

function getRecognizedReferenceFields(profile: ReferenceProfile): string[] {
  return profile.columns
    .map((column) => column.standard_label ?? column.standard_field ?? column.original_name)
    .filter((field): field is string => Boolean(field?.trim()))
}

function buildReferenceProfileSummary(record: ReferenceFileResponse): string {
  const profile = record.profile
  if (!profile) {
    return '暂未识别画像。'
  }

  const fields = getRecognizedReferenceFields(profile)
  const defaultSheetName = record.default_sheet_name ?? profile.default_sheet_name
  return [
    `来源类型：${getReferenceSourceTypeLabel(profile.source_type)}`,
    fields.length ? `字段结构：${fields.slice(0, 6).join(' / ')}` : '字段结构：未识别',
    defaultSheetName ? `默认 Sheet：${defaultSheetName}` : '',
  ]
    .filter(Boolean)
    .join('；')
}

function mapReferenceFileResponse(record: ReferenceFileResponse): ReferenceFile {
  const profileWarnings = record.profile?.warnings.map((warning) => warning.message).filter(Boolean) ?? []
  const sheetOptions = record.profile?.sheet_options.map(mapReferenceSheetOption) ?? []
  const type = getReferenceFileType(record.suffix)

  return {
    id: String(record.id),
    backendId: record.id,
    categoryId:
      typeof record.category_id === 'number' ? String(record.category_id) : REFERENCE_UNCATEGORIZED_CATEGORY_ID,
    categoryNumericId: record.category_id ?? null,
    name: record.original_filename,
    type,
    tag: record.is_recommended_primary ? '推荐主参考' : undefined,
    summary: record.category_name,
    uploadedBy: '项目成员',
    uploadedAt: record.created_at,
    caseCount: record.reference_case_count ?? record.profile?.reference_case_count ?? undefined,
    profileSummary: buildReferenceProfileSummary(record),
    warnings: profileWarnings.length ? profileWarnings : undefined,
    isRecommendedPrimary: record.is_recommended_primary,
    defaultSheetName: record.default_sheet_name ?? record.profile?.default_sheet_name ?? undefined,
    sheetOptions: sheetOptions.length ? sheetOptions : undefined,
    profile: record.profile ?? null,
  }
}

function buildReferenceCategories(
  categoryItems: ReferenceCategoryResponse[],
  files: ReferenceFile[],
): ReferenceCategory[] {
  const uncategorizedCount = files.filter((file) => file.categoryId === REFERENCE_UNCATEGORIZED_CATEGORY_ID).length
  return [
    ...categoryItems.map((category) => ({
      id: String(category.id),
      backendId: category.id,
      name: category.name,
      description: '项目参考案例分类',
      referenceCount: category.reference_count,
    })),
    {
      id: REFERENCE_UNCATEGORIZED_CATEGORY_ID,
      backendId: null,
      name: '未分类',
      description: '暂未归入分类的参考材料',
      referenceCount: uncategorizedCount,
    },
  ]
}

function applyReferenceCategorySelection(categoryId: string, options: { markStale: boolean }): void {
  selectedReferenceCategoryId.value = categoryId
  referenceSearchKeyword.value = ''
  referenceCurrentPage.value = 1

  const recommendedReference = referenceFiles.value.find(
    (file) => file.categoryId === categoryId && file.isRecommendedPrimary,
  )
  selectedReferenceIds.value = recommendedReference ? [recommendedReference.id] : []
  primaryReferenceId.value = recommendedReference?.id ?? ''
  updatePrimaryReferenceSheet(recommendedReference ?? null)
  if (options.markStale) {
    markGeneratedResultStale(
      recommendedReference
        ? '参考案例分类已切换，已使用该分类的推荐主参考。'
        : '参考案例分类已切换，本次将按 qa-case 标准逻辑生成。',
    )
  }
}

async function loadReferenceLibrary(): Promise<void> {
  isReferenceLibraryLoading.value = true
  referenceApiErrorMessage.value = ''
  try {
    const [categoryResponse, fileResponse] = await Promise.all([
      fetchReferenceCategories(),
      fetchReferenceFiles(),
    ])
    const files = fileResponse.data.items.map(mapReferenceFileResponse)
    const categories = buildReferenceCategories(categoryResponse.data.items, files)
    referenceFiles.value = files
    referenceCategories.value = categories

    const nextCategoryId = categories.some((category) => category.id === selectedReferenceCategoryId.value)
      ? selectedReferenceCategoryId.value
      : categories[0]?.id ?? ''
    applyReferenceCategorySelection(nextCategoryId, { markStale: false })
  } catch (error) {
    referenceApiErrorMessage.value = getApiErrorMessage(error, '读取参考案例库失败，请稍后重试。')
    referenceCategories.value = []
    referenceFiles.value = []
    selectedReferenceCategoryId.value = ''
    selectedReferenceIds.value = []
    primaryReferenceId.value = ''
    selectedReferenceSheetName.value = ''
  } finally {
    isReferenceLibraryLoading.value = false
  }
}

function markGeneratedResultStale(reason: string): void {
  isGeneratedResultStale.value = true
  generatedResultStaleReason.value = reason
}

function clearSnapshotAndGeneratedResult(): void {
  planningSnapshot.value = null
  resetSnapshotBriefState()
  clearGeneratedResult()
}

function clearGeneratedResult(): void {
  generationResult.value = null
  apiErrorMessage.value = ''
  isGeneratedResultStale.value = false
  generatedResultStaleReason.value = ''
  snapshotBriefParticipatedInLastGeneration.value = null
}

function resetSnapshotBriefState(): void {
  snapshotBriefRequestId += 1
  snapshotBriefMarkdown.value = ''
  snapshotBriefWarnings.value = []
  snapshotBriefErrorMessage.value = ''
  isSnapshotBriefLoading.value = false
}

function getApiErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

async function generateSnapshotBrief(): Promise<void> {
  const snapshot = planningSnapshot.value
  if (!snapshot) {
    return
  }

  const requestId = ++snapshotBriefRequestId
  isSnapshotBriefLoading.value = true
  snapshotBriefMarkdown.value = ''
  snapshotBriefWarnings.value = []
  snapshotBriefErrorMessage.value = ''

  try {
    const response = await readPlanningSnapshotBrief({ planning_snapshot: snapshot })
    if (requestId !== snapshotBriefRequestId || planningSnapshot.value !== snapshot) {
      return
    }
    snapshotBriefMarkdown.value = response.data.brief_markdown
    snapshotBriefWarnings.value = response.data.warnings ?? []
  } catch (error) {
    if (requestId !== snapshotBriefRequestId || planningSnapshot.value !== snapshot) {
      return
    }
    snapshotBriefErrorMessage.value = getApiErrorMessage(error, 'AI 整理稿生成失败，请稍后重试。')
  } finally {
    if (requestId === snapshotBriefRequestId) {
      isSnapshotBriefLoading.value = false
    }
  }
}

async function copySnapshotBriefMarkdown(): Promise<void> {
  const markdown = snapshotBriefMarkdown.value.trim()
  if (!markdown) {
    return
  }

  try {
    await copyTextToClipboard(markdown)
    ElMessage.success('已复制整理稿 Markdown。')
  } catch {
    ElMessage.warning('复制失败，请手动选择 Markdown 内容复制。')
  }
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

async function refreshPlanningSourceMetadata(sourceId: string): Promise<SourceMetadata | null> {
  const source = planningSourceStore.sources.find((item) => item.id === sourceId)
  if (!source) {
    return null
  }

  const response = await fetchSourceMetadata(source)
  const metadata = response.data
  if (planningSourceStore.sourceMetadataMap) {
    planningSourceStore.sourceMetadataMap[sourceId] = metadata
  }
  return metadata
}

async function ensurePlanningSourceMetadata(sourceId: string): Promise<SourceMetadata | null> {
  if (!sourceId) {
    return null
  }

  const cached = planningSourceStore.sourceMetadataMap?.[sourceId]
  if (cached) {
    return cached
  }

  return refreshPlanningSourceMetadata(sourceId)
}

async function readSnapshot(): Promise<void> {
  if (!selectedPlanningSource.value || !selectedPlanningSheetName.value) {
    return
  }

  isSnapshotLoading.value = true
  apiErrorMessage.value = ''
  try {
    const source = selectedPlanningSource.value
    const response = await readPlanningSnapshot({
      source_type: source.type === 'feishu' ? 'feishu' : 'uploaded_excel',
      source,
      sheet_name: selectedPlanningSheetName.value,
    })
    planningSnapshot.value = response.data
    clearGeneratedResult()
    resetSnapshotBriefState()
    activeTab.value = 'brief'
    void generateSnapshotBrief()
  } catch (error) {
    apiErrorMessage.value = getApiErrorMessage(error, '读取策划案快照失败，请稍后重试。')
  } finally {
    isSnapshotLoading.value = false
  }
}

async function generateCases(): Promise<void> {
  if (!planningSnapshot.value) {
    return
  }

  isGeneratingCases.value = true
  apiErrorMessage.value = ''
  try {
    const selectedReferenceBackendIds = selectedReferenceFiles.value.map((file) => file.backendId)
    const primaryReferenceBackendId = primaryReference.value?.backendId ?? null
    const primaryReferenceSheetName =
      primaryReference.value && hasReferenceSheetOptions.value ? selectedReferenceSheetName.value || null : null
    const briefMarkdown = snapshotBriefMarkdown.value.trim()
    const payload: TestCaseGenerationRequest = {
      planning_snapshot: planningSnapshot.value,
      reference_ids: selectedReferenceBackendIds,
      primary_reference_id: primaryReferenceBackendId,
      primary_reference_sheet_name: primaryReferenceSheetName,
    }
    if (briefMarkdown) {
      payload.snapshot_brief_markdown = briefMarkdown
    }
    const response = await generateTestCases(payload)
    generationResult.value = response.data
    isGeneratedResultStale.value = false
    generatedResultStaleReason.value = ''
    snapshotBriefParticipatedInLastGeneration.value = Boolean(briefMarkdown)
    activeTab.value = 'cases'
  } catch (error) {
    apiErrorMessage.value = getApiErrorMessage(error, '生成用例失败，请稍后重试。')
  } finally {
    isGeneratingCases.value = false
  }
}

function saveDownloadedFile(file: ApiFileResponse): void {
  if (typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') {
    return
  }

  const url = URL.createObjectURL(file.blob)
  const link = document.createElement('a')
  link.href = url
  link.download = file.filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

async function exportCases(): Promise<void> {
  if (!generationResult.value || isGeneratedResultStale.value) {
    return
  }

  isExportingCases.value = true
  apiErrorMessage.value = ''
  try {
    const file = await exportTestCaseWorkbook({
      blueprint: generationResult.value.blueprint,
      cases: generationResult.value.cases,
      warnings: generationResult.value.warnings,
      stats: generationResult.value.stats,
      export_columns: generationResult.value.export_columns,
      primary_reference_profile: generationResult.value.primary_reference_profile ?? null,
      source_summary: planningSnapshot.value?.source_summary ?? '',
    })
    saveDownloadedFile(file)
  } catch (error) {
    apiErrorMessage.value = getApiErrorMessage(error, '导出 Excel 失败，请稍后重试。')
  } finally {
    isExportingCases.value = false
  }
}

function updatePrimaryReferenceSheet(file: ReferenceFile | null): void {
  if (!file?.sheetOptions?.length) {
    selectedReferenceSheetName.value = ''
    return
  }
  selectedReferenceSheetName.value =
    file.defaultSheetName ??
    file.sheetOptions.find((sheet) => sheet.isDefault)?.sheetName ??
    file.sheetOptions[0]?.sheetName ??
    ''
}

function selectReferenceCategory(categoryId: string): void {
  if (selectedReferenceCategoryId.value === categoryId) {
    return
  }

  applyReferenceCategorySelection(categoryId, { markStale: true })
}

function isReferenceSelected(fileId: string): boolean {
  return selectedReferenceIds.value.includes(fileId)
}

function handleReferenceCheckboxChange(file: ReferenceFile, event: Event): void {
  const checked = event.target instanceof HTMLInputElement ? event.target.checked : false
  toggleReferenceSelection(file, checked)
}

function toggleReferenceSelection(file: ReferenceFile, checked: boolean): void {
  if (checked) {
    if (!selectedReferenceIds.value.includes(file.id)) {
      selectedReferenceIds.value = [...selectedReferenceIds.value, file.id]
      markGeneratedResultStale('参考案例选择已变化，需要重新生成。')
    }
    return
  }

  selectedReferenceIds.value = selectedReferenceIds.value.filter((selectedId) => selectedId !== file.id)
  if (primaryReferenceId.value === file.id) {
    primaryReferenceId.value = ''
    selectedReferenceSheetName.value = ''
    markGeneratedResultStale('当前主参考案例已移出选择，本次将按无主参考模式生成。')
    return
  }
  markGeneratedResultStale('参考案例选择已变化，需要重新生成。')
}

function setPrimaryReference(file: ReferenceFile): void {
  const primaryChanged = primaryReferenceId.value !== file.id
  if (!selectedReferenceIds.value.includes(file.id)) {
    selectedReferenceIds.value = [...selectedReferenceIds.value, file.id]
  }
  primaryReferenceId.value = file.id
  updatePrimaryReferenceSheet(file)
  if (primaryChanged) {
    markGeneratedResultStale('主参考案例已切换，需要重新生成。')
  }
}

function handlePrimaryReferenceChange(referenceId: string): void {
  const file = selectedReferenceFiles.value.find((item) => item.id === referenceId) ?? null
  if (!file) {
    primaryReferenceId.value = ''
    selectedReferenceSheetName.value = ''
    return
  }
  setPrimaryReference(file)
}

function handleReferenceSheetChange(sheetName: string): void {
  if (selectedReferenceSheetName.value === sheetName) {
    return
  }
  selectedReferenceSheetName.value = sheetName
  markGeneratedResultStale('主参考 Sheet 已切换，需要重新生成。')
}

function goToReferencePage(page: number): void {
  referenceCurrentPage.value = Math.min(Math.max(page, 1), referenceTotalPages.value)
}

function clearReferenceFilters(): void {
  referenceSearchKeyword.value = ''
  referenceTypeFilter.value = 'all'
  referenceSort.value = 'recommended'
  referenceCurrentPage.value = 1
}

function openCreateReferenceCategoryDialog(): void {
  newReferenceCategoryName.value = ''
  createCategoryError.value = ''
  createCategoryDialogVisible.value = true
}

async function createReferenceCategory(): Promise<void> {
  const categoryName = newReferenceCategoryName.value.trim()
  if (!categoryName) {
    createCategoryError.value = '分类名不能为空。'
    return
  }
  if (referenceCategories.value.some((category) => category.name === categoryName)) {
    createCategoryError.value = '已存在同名参考案例分类。'
    return
  }

  isCreatingReferenceCategory.value = true
  createCategoryError.value = ''
  try {
    const response = await createReferenceCategoryApi({ name: categoryName })
    selectedReferenceCategoryId.value = String(response.data.id)
    createCategoryDialogVisible.value = false
    await loadReferenceLibrary()
  } catch (error) {
    createCategoryError.value = getApiErrorMessage(error, '创建参考案例分类失败，请稍后重试。')
  } finally {
    isCreatingReferenceCategory.value = false
  }
}

function openUploadReferenceDialog(): void {
  referenceUploadFile.value = null
  uploadReferenceError.value = ''
  uploadReferenceDialogVisible.value = true
}

function handleReferenceUploadFileChange(event: Event): void {
  const input = event.target instanceof HTMLInputElement ? event.target : null
  referenceUploadFile.value = input?.files?.[0] ?? null
  uploadReferenceError.value = ''
}

async function uploadReference(): Promise<void> {
  if (!referenceUploadFile.value) {
    uploadReferenceError.value = '请选择一个 .xlsx、.xls、.md 或 .txt 参考案例文件。'
    return
  }

  isUploadingReference.value = true
  uploadReferenceError.value = ''
  try {
    await uploadReferenceFile(referenceUploadFile.value, currentReferenceCategory.value?.backendId ?? null)
    uploadReferenceDialogVisible.value = false
    await loadReferenceLibrary()
  } catch (error) {
    uploadReferenceError.value = getApiErrorMessage(error, '上传参考案例失败，请稍后重试。')
  } finally {
    isUploadingReference.value = false
  }
}

function openProfilePreview(file: ReferenceFile): void {
  profilePreviewFileId.value = file.id
  profilePreviewDialogVisible.value = true
}

function openReferenceMore(file: ReferenceFile): void {
  referenceMoreFileId.value = file.id
  referenceMoreDialogVisible.value = true
}

async function setReferenceAsRecommended(file: ReferenceFile): Promise<void> {
  isUpdatingReference.value = true
  referenceApiErrorMessage.value = ''
  try {
    await setRecommendedPrimaryReference(file.backendId)
    selectedReferenceCategoryId.value = file.categoryId
    referenceMoreDialogVisible.value = false
    await loadReferenceLibrary()
    markGeneratedResultStale('推荐主参考已更新，本次默认主参考已同步。')
  } catch (error) {
    referenceApiErrorMessage.value = getApiErrorMessage(error, '设置推荐主参考失败，请确认当前账号权限。')
  } finally {
    isUpdatingReference.value = false
  }
}

async function removeReferenceFile(file: ReferenceFile): Promise<void> {
  isUpdatingReference.value = true
  referenceApiErrorMessage.value = ''
  try {
    await deleteReferenceFile(file.backendId)
    referenceMoreDialogVisible.value = false
    await loadReferenceLibrary()
    markGeneratedResultStale('参考案例已删除，当前生成结果需要重新生成。')
  } catch (error) {
    referenceApiErrorMessage.value = getApiErrorMessage(error, '删除参考案例失败，请确认当前账号权限。')
  } finally {
    isUpdatingReference.value = false
  }
}

function getPlanningSourceLabel(source: DataSource): string {
  return `${source.id} · ${getPlanningSourceTypeLabel(source.type)}`
}

function getPlanningSourceTypeLabel(sourceType: DataSource['type']): string {
  if (sourceType === 'feishu') {
    return '飞书电子表格'
  }
  if (sourceType === 'svn') {
    return 'SVN Excel'
  }
  if (sourceType === 'local_excel') {
    return '上传 Excel'
  }
  return 'CSV'
}

function openPlanningSourceCreate(): void {
  planningSourcePanelRef.value?.openCreateDialog()
}

async function handlePlanningSourceSaved(sourceId: string): Promise<void> {
  selectedPlanningSourceId.value = sourceId
  const metadata = await refreshPlanningSourceMetadata(sourceId)
  if (metadata && selectedPlanningSourceId.value === sourceId) {
    selectedPlanningSheetName.value = metadata.sheets[0]?.name ?? ''
  }
  queuePlanningSourceConfigPersist()
}

function handlePlanningSheetSelectionChange(): void {
  if (isPlanningSourceConfigHydrating.value || isApplyingPlanningSourceConfig) {
    return
  }
  queuePlanningSourceConfigPersist()
}

function togglePlanningSourceSection(): void {
  planningSourceCollapsed.value = !planningSourceCollapsed.value
}

onMounted(() => {
  void loadPlanningSourceConfig()
  void loadReferenceLibrary()
})
</script>

<template>
  <div class="test-case-generator-page">
    <PageHeader
      breadcrumb="主页 / 用例生成"
      title="用例生成工作台"
      description="按 01 到 04 完成来源维护、快照读取、参考选择和结果导出。"
    >
      <template #actions>
        <div class="tcg-ai-status">
          <el-icon><SuccessFilled /></el-icon>
          <span>项目 AI 可用</span>
        </div>
      </template>
    </PageHeader>

    <main class="tcg-content">
      <section class="tcg-metrics" aria-label="用例生成概览">
        <MetricCard
          v-for="item in metrics"
          :key="item.label"
          :label="item.label"
          :value="item.value"
          :status-label="item.statusLabel"
          :status-type="item.statusType"
          :icon-tone="item.iconTone"
        >
          <template #icon>
            <Document v-if="item.label === '快照行数'" />
            <FolderOpened v-else-if="item.label === '本次参考'" />
            <Collection v-else-if="item.label === '预览用例'" />
            <WarningFilled v-else />
          </template>
        </MetricCard>
      </section>

      <CollapsibleSection
        class="tcg-source-module"
        step="01"
        title="数据源"
        description="维护本页策划案来源，读取前确认默认 Sheet。"
        status-label="用户项目保存"
        status-tone="done"
        :active="true"
        :collapsed="planningSourceCollapsed"
        content-class="tcg-source-module__content"
        @toggle="togglePlanningSourceSection"
      >
        <template #actions>
          <PrimaryButton size="sm" @click="openPlanningSourceCreate">
            <template #icon><Plus /></template>
            新增来源
          </PrimaryButton>
        </template>

        <DataSourcePanel
          ref="planningSourcePanelRef"
          :store="planningSourceStore"
          toolbar-mode="hidden"
          @saved="handlePlanningSourceSaved"
        />
        <p v-if="planningSourcePersistenceError" class="tcg-api-error" role="alert">
          {{ planningSourcePersistenceError }}
        </p>
      </CollapsibleSection>

      <section class="tcg-panel tcg-input-module" data-test="generation-input-module">
        <div class="tcg-panel__header">
          <div class="tcg-module-heading">
            <span class="tcg-module-heading__index">02</span>
            <div>
              <h2>生成输入</h2>
              <p>读取策划案快照；参考案例可选，用于补充字段、粒度和历史风格。</p>
            </div>
          </div>
        </div>

        <div class="tcg-input-grid">
          <section class="tcg-input-block" aria-labelledby="planning-source-title">
            <div class="tcg-input-block__header">
              <h3 id="planning-source-title">策划案快照</h3>
              <span>可读取</span>
            </div>
            <label class="tcg-field">
              <span>策划案来源</span>
              <el-select
                v-model="selectedPlanningSourceId"
                :disabled="!planningSourceStore.sources.length"
              >
                <el-option
                  v-if="!planningSourceStore.sources.length"
                  label="请先添加策划案来源"
                  value=""
                />
                <el-option
                  v-for="source in planningSourceStore.sources"
                  :key="source.id"
                  :label="getPlanningSourceLabel(source)"
                  :value="source.id"
                />
              </el-select>
            </label>
            <label class="tcg-field">
              <span>策划案 Sheet</span>
              <el-select
                v-model="selectedPlanningSheetName"
                :disabled="!hasPlanningSheetOptions"
                @change="handlePlanningSheetSelectionChange"
              >
                <el-option
                  v-if="!hasPlanningSheetOptions"
                  label="当前来源无可选 Sheet"
                  value=""
                />
                <el-option
                  v-for="sheet in selectedPlanningSheetOptions"
                  :key="sheet.sheet_id ?? sheet.name"
                  :label="sheet.name"
                  :value="sheet.name"
                />
              </el-select>
            </label>
            <p v-if="selectedPlanningSource" class="tcg-source-hint">
              {{ selectedPlanningSource.pathOrUrl ?? selectedPlanningSource.path ?? selectedPlanningSource.url }}
            </p>
            <SecondaryButton
              class="tcg-full-button"
              data-test="read-snapshot-button"
              :disabled="!canReadSnapshot"
              :loading="isSnapshotLoading"
              @click="readSnapshot"
            >
              <template #icon><Refresh /></template>
              读取快照
            </SecondaryButton>
          </section>

          <section class="tcg-input-block" aria-labelledby="generation-settings-title">
            <div class="tcg-input-block__header">
              <h3 id="generation-settings-title">主参考设置</h3>
              <span>{{ hasPlanningSnapshot ? '可生成' : '待快照' }}</span>
            </div>
            <label class="tcg-field">
              <span>主参考案例</span>
              <el-select
                :model-value="primaryReferenceId"
                :disabled="!selectedReferenceFiles.length"
                data-test="primary-reference-select"
                @change="handlePrimaryReferenceChange"
                @update:model-value="handlePrimaryReferenceChange"
              >
                <el-option
                  v-if="!selectedReferenceFiles.length"
                  label="可选：先选择参考案例后指定主参考"
                  value=""
                />
                <el-option
                  v-for="item in selectedReferenceFiles"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </label>
            <label class="tcg-field">
              <span>主参考 Sheet</span>
              <el-select
                :model-value="selectedReferenceSheetName"
                :disabled="!hasReferenceSheetOptions"
                data-test="primary-reference-sheet-select"
                @change="handleReferenceSheetChange"
                @update:model-value="handleReferenceSheetChange"
              >
                <el-option
                  v-if="!hasReferenceSheetOptions"
                  :label="primaryReference ? '当前参考案例无 Sheet' : '未选择主参考'"
                  value=""
                />
                <el-option
                  v-for="sheet in selectedReferenceSheetOptions"
                  :key="sheet.sheetName"
                  :label="sheet.isDefault ? `${sheet.sheetName}（默认）` : sheet.sheetName"
                  :value="sheet.sheetName"
                />
              </el-select>
            </label>
            <label class="tcg-field">
              <span>参考用例数量</span>
              <el-input :model-value="referenceCaseCountDisplay" readonly />
            </label>
            <div class="tcg-warning-note">
              <el-icon><WarningFilled /></el-icon>
              <span>{{ primaryReference ? '当前版本不读取图片或附件，参考案例仅作增强' : '未选择主参考时按 qa-case 标准逻辑生成' }}</span>
            </div>
          </section>
        </div>
      </section>

      <section class="tcg-panel tcg-reference-library" data-test="reference-library">
        <div class="tcg-panel__header">
          <div class="tcg-module-heading">
            <span class="tcg-module-heading__index">03</span>
            <div>
              <h2>参考案例库</h2>
              <p>{{ selectedReferenceSummary }}；参考案例是增强输入，不是生成前置条件。</p>
            </div>
          </div>
          <div class="tcg-panel__actions">
            <SecondaryButton size="sm" @click="openCreateReferenceCategoryDialog">
              <template #icon><Plus /></template>
              新建分类
            </SecondaryButton>
            <SecondaryButton size="sm" @click="openUploadReferenceDialog">
              <template #icon><Upload /></template>
              上传参考案例
            </SecondaryButton>
          </div>
        </div>

        <p v-if="referenceApiErrorMessage" class="tcg-api-error" role="alert">{{ referenceApiErrorMessage }}</p>
        <p v-else-if="isReferenceLibraryLoading" class="tcg-inline-warning" aria-live="polite">
          正在读取项目参考案例库…
        </p>

        <div class="tcg-reference-categories" aria-label="参考案例分类">
          <button
            v-for="category in referenceCategories"
            :key="category.id"
            type="button"
            class="tcg-reference-category"
            :class="{ 'is-active': selectedReferenceCategoryId === category.id }"
            :aria-pressed="selectedReferenceCategoryId === category.id"
            data-test="reference-category-pill"
            @click="selectReferenceCategory(category.id)"
          >
            <span>{{ category.name }}</span>
            <strong>{{ getReferenceCategoryCount(category.id) }}</strong>
          </button>
        </div>

        <div class="tcg-reference-toolbar">
          <label class="tcg-reference-search">
            <span class="tcg-sr-only">搜索参考案例</span>
            <input
              v-model="referenceSearchKeyword"
              type="search"
              name="reference-search"
              autocomplete="off"
              placeholder="搜索文件名或画像摘要…"
              data-test="reference-search"
            />
          </label>
          <div class="tcg-reference-type-filter" aria-label="参考案例类型筛选">
            <button
              type="button"
              :class="{ 'is-active': referenceTypeFilter === 'all' }"
              :aria-pressed="referenceTypeFilter === 'all'"
              @click="referenceTypeFilter = 'all'"
            >
              全部
            </button>
            <button
              type="button"
              :class="{ 'is-active': referenceTypeFilter === 'xlsx' }"
              :aria-pressed="referenceTypeFilter === 'xlsx'"
              @click="referenceTypeFilter = 'xlsx'"
            >
              Excel
            </button>
            <button
              type="button"
              :class="{ 'is-active': referenceTypeFilter === 'md' }"
              :aria-pressed="referenceTypeFilter === 'md'"
              @click="referenceTypeFilter = 'md'"
            >
              Markdown
            </button>
            <button
              type="button"
              :class="{ 'is-active': referenceTypeFilter === 'txt' }"
              :aria-pressed="referenceTypeFilter === 'txt'"
              @click="referenceTypeFilter = 'txt'"
            >
              TXT
            </button>
          </div>
          <label class="tcg-reference-sort">
            <span>排序</span>
            <select v-model="referenceSort" name="reference-sort" autocomplete="off">
              <option value="recommended">推荐优先</option>
              <option value="newest">最新上传</option>
              <option value="name">文件名</option>
            </select>
          </label>
        </div>

        <p v-if="!primaryReference && selectedReferenceFiles.length" class="tcg-inline-warning" aria-live="polite">
          已选择参考案例但未指定主参考，本次会把它们作为补充参考使用。
        </p>
        <p v-else-if="!selectedReferenceFiles.length" class="tcg-inline-warning" aria-live="polite">
          当前分类未选择参考案例，本次将按 qa-case 标准逻辑生成。
        </p>

        <div
          v-if="visibleReferenceFiles.length"
          class="tcg-reference-list"
          role="list"
          aria-label="参考案例文件"
        >
          <article
            v-for="item in visibleReferenceFiles"
            :key="item.id"
            class="tcg-reference-item"
            :class="{
              'is-primary': primaryReference?.id === item.id,
              'is-selected': isReferenceSelected(item.id) && primaryReference?.id !== item.id,
            }"
            role="listitem"
            data-test="reference-file-row"
            :data-reference-id="item.id"
          >
            <label class="tcg-reference-check">
              <input
                type="checkbox"
                :checked="isReferenceSelected(item.id)"
                :aria-label="`选择参考案例 ${item.name}`"
                data-test="reference-checkbox"
                @change="handleReferenceCheckboxChange(item, $event)"
              />
            </label>
            <div class="tcg-reference-item__icon" :class="getReferenceTypeClass(item.type)" aria-hidden="true">
              <Document />
            </div>
            <div class="tcg-reference-item__body">
              <div class="tcg-reference-item__title">
                <span :title="item.name">{{ item.name }}</span>
                <em class="tcg-reference-type">{{ getReferenceTypeLabel(item.type) }}</em>
                <el-tag v-if="item.isRecommendedPrimary" size="small" type="success">推荐主参考</el-tag>
              </div>
              <p :title="item.profileSummary">{{ item.profileSummary }}</p>
              <div class="tcg-reference-meta">
                <span>用例数：{{ typeof item.caseCount === 'number' ? item.caseCount : '未识别' }}</span>
                <span>默认 Sheet：{{ item.defaultSheetName ?? '无' }}</span>
                <span>{{ item.uploadedBy }} · {{ formatReferenceUploadTime(item.uploadedAt) }}</span>
              </div>
            </div>
            <div class="tcg-reference-item__actions">
              <button type="button" :aria-label="`预览画像 ${item.name}`" @click.stop="openProfilePreview(item)">
                <el-icon><View /></el-icon>
              </button>
              <button
                type="button"
                class="tcg-reference-primary-action"
                :disabled="primaryReference?.id === item.id"
                @click.stop="setPrimaryReference(item)"
              >
                {{ primaryReference?.id === item.id ? '当前主参考' : '设为主参考' }}
              </button>
              <button type="button" :aria-label="`更多操作 ${item.name}`" @click.stop="openReferenceMore(item)">
                <el-icon><MoreFilled /></el-icon>
              </button>
            </div>
          </article>
          <div class="tcg-reference-list__footer">
            <span>第 {{ referencePageStart }}-{{ referencePageEnd }} 条 / 共 {{ filteredReferenceFiles.length }} 条</span>
            <nav class="tcg-reference-pagination" aria-label="参考案例分页">
              <button
                type="button"
                :disabled="referenceCurrentPage === 1"
                data-test="reference-page-prev"
                aria-label="上一页参考案例"
                @click="goToReferencePage(referenceCurrentPage - 1)"
              >
                上一页
              </button>
              <button
                v-for="pageNumber in referencePageNumbers"
                :key="pageNumber"
                type="button"
                class="tcg-reference-page-number"
                :class="{ 'is-active': referenceCurrentPage === pageNumber }"
                :aria-current="referenceCurrentPage === pageNumber ? 'page' : undefined"
                :aria-label="`第 ${pageNumber} 页参考案例`"
                data-test="reference-page-number"
                @click="goToReferencePage(pageNumber)"
              >
                {{ pageNumber }}
              </button>
              <button
                type="button"
                :disabled="referenceCurrentPage === referenceTotalPages"
                data-test="reference-page-next"
                aria-label="下一页参考案例"
                @click="goToReferencePage(referenceCurrentPage + 1)"
              >
                下一页
              </button>
            </nav>
          </div>
        </div>
        <div v-else class="tcg-reference-empty" aria-live="polite">
          <strong>{{ currentCategoryReferenceFiles.length ? '没有匹配的参考案例' : '当前分类暂无参考案例' }}</strong>
          <span>
            {{
              currentCategoryReferenceFiles.length
                ? '调整搜索、类型或排序后再查看。'
                : '可以先上传参考案例到当前分类。'
            }}
          </span>
          <SecondaryButton v-if="currentCategoryReferenceFiles.length" size="sm" @click="clearReferenceFilters">
            清空筛选
          </SecondaryButton>
          <SecondaryButton v-else size="sm" @click="openUploadReferenceDialog">
            <template #icon><Upload /></template>
            上传参考案例
          </SecondaryButton>
        </div>
      </section>

      <section class="tcg-preview" aria-label="用例生成预览">
          <div class="tcg-preview__header" data-test="preview-action-bar">
            <div class="tcg-module-heading">
              <span class="tcg-module-heading__index">04</span>
              <div>
                <h2>结果预览</h2>
                <p>核对整理稿、测试用例和限制提示，确认后导出 Excel。</p>
              </div>
            </div>
            <div class="tcg-preview__actions">
              <SecondaryButton
                data-test="preview-export-button"
                :disabled="!canExportGeneratedResult"
                :loading="isExportingCases"
                @click="exportCases"
              >
                <template #icon><Download /></template>
                导出 Excel
              </SecondaryButton>
              <PrimaryButton
                :disabled="!isGenerationReady"
                :loading="isGeneratingCases"
                data-test="preview-generate-button"
                @click="generateCases"
              >
                <template #icon><VideoPlay /></template>
                生成用例
              </PrimaryButton>
            </div>
          </div>

          <div class="tcg-preview__tabs">
            <button
              v-for="tab in tabs"
              :key="tab.key"
              type="button"
              :class="{ 'is-active': activeTab === tab.key }"
              @click="activeTab = tab.key"
            >
              {{ tab.label }}
            </button>
          </div>

          <div class="tcg-preview__toolbar">
            <div class="tcg-status-strip">
              <el-tag :type="previewStatusType" size="large">{{ previewStatusLabel }}</el-tag>
              <el-tag :type="warnings.length ? 'warning' : 'info'" size="large">{{ warnings.length }} 条限制提示</el-tag>
              <span v-if="generationResult" class="tcg-muted">用例总数 {{ generationResult.stats.total }}</span>
              <span class="tcg-muted">主参考：{{ primaryReference?.name ?? '未选择主参考' }}</span>
            </div>
            <div class="tcg-priority-summary">
              <el-tag v-for="[priority, count] in prioritySummary" :key="priority" :type="getPriorityType(priority)" size="large">
                {{ priority }} {{ count }}
              </el-tag>
              <span v-if="!prioritySummary.length" class="tcg-muted">待读取生成结果</span>
            </div>
          </div>

          <p v-if="apiErrorMessage" class="tcg-api-error" role="alert">{{ apiErrorMessage }}</p>

          <div v-if="isGeneratedResultStale" class="tcg-stale-notice" role="status" aria-live="polite">
            <el-icon><WarningFilled /></el-icon>
            <span>{{ generatedResultStaleReason }}</span>
          </div>

          <div v-if="activeTab === 'brief'" class="tcg-tab-panel">
            <div class="tcg-brief-panel">
              <div class="tcg-brief-panel__header">
                <div>
                  <strong>AI 快照整理稿</strong>
                  <span>辅助阅读与对齐，需求事实来源仍以 Planning Sheet Snapshot 为准。</span>
                </div>
                <div class="tcg-brief-panel__actions">
                  <SecondaryButton
                    size="sm"
                    data-test="copy-snapshot-brief-button"
                    :disabled="!hasSnapshotBriefMarkdown || isSnapshotBriefLoading"
                    @click="copySnapshotBriefMarkdown"
                  >
                    <template #icon><CopyDocument /></template>
                    复制 Markdown
                  </SecondaryButton>
                  <SecondaryButton
                    size="sm"
                    data-test="retry-snapshot-brief-button"
                    :disabled="!hasPlanningSnapshot || isSnapshotBriefLoading"
                    :loading="isSnapshotBriefLoading"
                    @click="generateSnapshotBrief"
                  >
                    <template #icon><Refresh /></template>
                    重新整理
                  </SecondaryButton>
                </div>
              </div>

              <p
                v-if="generationResult && snapshotBriefParticipatedInLastGeneration === false"
                class="tcg-brief-panel__notice"
                role="status"
              >
                整理稿未参与本次生成。
              </p>

              <div v-if="isSnapshotBriefLoading" class="tcg-brief-state" role="status" aria-live="polite">
                <span class="tcg-loading-dot"></span>
                <div>
                  <strong>整理中</strong>
                  <span>快照已读取，可直接生成用例。</span>
                </div>
              </div>
              <div v-else-if="snapshotBriefErrorMessage" class="tcg-brief-error" role="alert">
                <el-icon><WarningFilled /></el-icon>
                <div>
                  <strong>整理稿生成失败</strong>
                  <p>{{ snapshotBriefErrorMessage }}</p>
                  <p v-if="snapshotFirstRowSummary" class="tcg-muted">
                    原始快照仍已保留：{{ snapshotFirstRowSummary }}
                  </p>
                  <SecondaryButton
                    size="sm"
                    data-test="retry-snapshot-brief-error-button"
                    :loading="isSnapshotBriefLoading"
                    @click="generateSnapshotBrief"
                  >
                    <template #icon><Refresh /></template>
                    重新整理
                  </SecondaryButton>
                </div>
              </div>
              <div v-else-if="snapshotBriefMarkdown" class="tcg-brief-markdown" data-test="snapshot-brief-markdown">
                <pre>{{ snapshotBriefMarkdown }}</pre>
                <ul v-if="snapshotBriefWarningMessages.length" class="tcg-brief-warning-list">
                  <li v-for="warning in snapshotBriefWarningMessages" :key="warning">
                    <el-icon><WarningFilled /></el-icon>
                    <span>{{ warning }}</span>
                  </li>
                </ul>
              </div>
              <div v-else class="tcg-empty-result">生成前先读取策划案快照</div>
            </div>
          </div>

          <div v-else-if="activeTab === 'cases'" class="tcg-tab-panel">
            <el-table v-if="generatedCases.length" :data="generatedCases" class="tcg-case-table">
              <el-table-column prop="id" label="用例编号" width="112" />
              <el-table-column prop="module" label="功能模块" width="128" />
              <el-table-column prop="checkpoint" label="检查点" width="132" />
              <el-table-column prop="title" label="用例标题" min-width="230" />
              <el-table-column label="优先级" width="92">
                <template #default="{ row }: { row: GeneratedCase }">
                  <el-tag :type="getPriorityType(row.priority)" size="small">{{ row.priority }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="status" label="状态" width="104">
                <template #default="{ row }: { row: GeneratedCase }">
                  <el-tag size="small">{{ row.status }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="remarks" label="备注" min-width="132" />
              <el-table-column label="" width="52" align="center">
                <template #default>
                  <el-icon class="tcg-row-more"><MoreFilled /></el-icon>
                </template>
              </el-table-column>
            </el-table>
            <div v-else class="tcg-empty-result">
              {{ hasPlanningSnapshot ? '快照已读取，点击生成用例。' : '生成前先读取策划案快照' }}
            </div>
          </div>

          <div v-else class="tcg-tab-panel">
            <ul v-if="warnings.length" class="tcg-warning-list">
              <li v-for="warning in warnings" :key="warning">
                <el-icon><WarningFilled /></el-icon>
                <span>{{ warning }}</span>
              </li>
            </ul>
            <div v-else class="tcg-empty-result">暂无限制提示</div>
          </div>

          <div class="tcg-warning-strip">
            <div class="tcg-section-title">
              <h2>限制提示</h2>
              <span>本次生成限制</span>
            </div>
            <div class="tcg-warning-strip__items">
              <span v-for="warning in warnings" :key="warning">
                <el-icon><WarningFilled /></el-icon>
                {{ warning }}
              </span>
              <span v-if="!warnings.length" class="tcg-muted">暂无限制提示。</span>
            </div>
          </div>

      </section>
    </main>

    <el-dialog v-model="createCategoryDialogVisible" title="新建参考案例分类" width="420px">
      <label class="tcg-dialog-field">
        <span>分类名称</span>
        <input
          v-model="newReferenceCategoryName"
          name="reference-category-name"
          type="text"
          autocomplete="off"
          placeholder="例如：活动用例…"
          @input="createCategoryError = ''"
        />
      </label>
      <p v-if="createCategoryError" class="tcg-dialog-error" role="alert">{{ createCategoryError }}</p>
      <template #footer>
        <div class="tcg-dialog-actions">
          <SecondaryButton size="sm" @click="createCategoryDialogVisible = false">取消</SecondaryButton>
          <PrimaryButton size="sm" :loading="isCreatingReferenceCategory" @click="createReferenceCategory">
            创建分类
          </PrimaryButton>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="uploadReferenceDialogVisible" title="上传参考案例" width="460px">
      <div class="tcg-static-dialog">
        <strong>上传到当前分类：{{ currentReferenceCategory?.name ?? '未选择分类' }}</strong>
        <p>支持 .xlsx、.xls、.md、.txt；上传后由后端生成确定性画像。</p>
        <label class="tcg-dialog-field">
          <span>参考案例文件</span>
          <input
            type="file"
            accept=".xlsx,.xls,.md,.txt"
            data-test="reference-upload-input"
            @change="handleReferenceUploadFileChange"
          />
        </label>
        <p v-if="uploadReferenceError" class="tcg-dialog-error" role="alert">{{ uploadReferenceError }}</p>
      </div>
      <template #footer>
        <div class="tcg-dialog-actions">
          <SecondaryButton size="sm" @click="uploadReferenceDialogVisible = false">取消</SecondaryButton>
          <PrimaryButton
            size="sm"
            data-test="reference-upload-submit"
            :loading="isUploadingReference"
            @click="uploadReference"
          >
            上传
          </PrimaryButton>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="profilePreviewDialogVisible" title="参考案例画像" width="520px">
      <div v-if="profilePreviewFile" class="tcg-static-dialog">
        <strong>{{ profilePreviewFile.name }}</strong>
        <p>{{ profilePreviewFile.profileSummary }}</p>
        <ul v-if="profilePreviewFile.warnings?.length">
          <li v-for="warning in profilePreviewFile.warnings" :key="warning">{{ warning }}</li>
        </ul>
      </div>
    </el-dialog>

    <el-dialog v-model="referenceMoreDialogVisible" title="更多操作" width="420px">
      <div v-if="referenceMoreFile" class="tcg-static-dialog">
        <strong>{{ referenceMoreFile.name }}</strong>
        <p>管理员动作以后端权限校验结果为准，普通项目成员调用时会被后端拒绝。</p>
        <div class="tcg-static-actions">
          <button type="button" disabled>重命名分类</button>
          <button type="button" :disabled="isUpdatingReference" @click="removeReferenceFile(referenceMoreFile)">
            删除文件
          </button>
          <button
            type="button"
            :disabled="isUpdatingReference || referenceMoreFile.isRecommendedPrimary"
            @click="setReferenceAsRecommended(referenceMoreFile)"
          >
            设为推荐主参考
          </button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.test-case-generator-page {
  --tcg-panel-bg: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(251, 253, 255, 0.98) 100%);
  --tcg-panel-border: rgba(203, 213, 225, 0.78);
  --tcg-panel-shadow: 0 14px 36px rgba(15, 23, 42, 0.045);
  --tcg-panel-shadow-strong: 0 18px 44px rgba(15, 23, 42, 0.075);
  --tcg-row-hover: #f4f8ff;
  --tcg-focus-ring: rgba(15, 98, 254, 0.18);
  --tcg-section-bg: #f5f8ff;
  --tcg-panel-rail: linear-gradient(90deg, rgba(15, 98, 254, 0.74), rgba(18, 183, 106, 0.52));
  --tcg-soft-inset: inset 0 1px 0 rgba(255, 255, 255, 0.92);

  display: flex;
  min-height: 0;
  height: 100%;
  flex-direction: column;
  overflow: hidden;
  background: var(--color-bg-page);
  color: var(--color-text-secondary);
}

.tcg-content {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 16px;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 20px 28px 44px;
  scrollbar-gutter: stable;
}

.tcg-content > :deep(.ui-collapsible-section) {
  flex: 0 0 auto;
}

.tcg-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.tcg-metrics :deep(.ui-metric-card) {
  border-color: var(--tcg-panel-border);
  background: var(--tcg-panel-bg);
  box-shadow: var(--tcg-panel-shadow), var(--tcg-soft-inset);
  min-height: 74px;
  padding: 13px 18px;
  transition:
    border-color 160ms cubic-bezier(0.2, 0, 0, 1),
    box-shadow 160ms cubic-bezier(0.2, 0, 0, 1);
}

.tcg-metrics :deep(.ui-metric-card:hover) {
  border-color: rgba(148, 163, 184, 0.62);
  box-shadow: var(--tcg-panel-shadow-strong);
}

.tcg-metrics :deep(.ui-metric-card__label) {
  color: #64748b;
  font-weight: 750;
  letter-spacing: 0;
}

.tcg-metrics :deep(.ui-metric-card__icon) {
  width: 38px;
  height: 38px;
}

.tcg-metrics :deep(.ui-metric-card__icon svg) {
  width: 19px;
  height: 19px;
}

.tcg-metrics :deep(.ui-metric-card__value) {
  margin: 3px 0;
  font-size: 23px;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
}

.tcg-source-module {
  border-radius: 12px;
}

.tcg-source-module :deep(.ui-collapsible-section__inner) {
  border-color: var(--tcg-panel-border);
  background: var(--tcg-panel-bg);
  padding: 14px 18px;
  box-shadow: var(--tcg-panel-shadow), var(--tcg-soft-inset) !important;
}

.tcg-source-module :deep(.workbench-section-head) {
  min-height: 0;
  align-items: center;
}

.tcg-source-module :deep(.workbench-section-head__index) {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  font-size: 15px;
}

.tcg-source-module :deep(.workbench-section-head__title) {
  font-size: 16px;
}

.tcg-source-module :deep(.workbench-section-head__description) {
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.45;
}

.tcg-source-module :deep(.workbench-section-toolbar__actions) {
  gap: 10px;
}

.tcg-source-module :deep(.tcg-source-module__content) {
  padding-top: 8px;
}

.tcg-source-module :deep(.panel-stack) {
  gap: 0;
}

.tcg-source-module :deep(.workbench-table.el-table) {
  overflow: hidden;
  border-radius: 10px !important;
  box-shadow: none !important;
}

.tcg-source-module :deep(.workbench-table th.el-table__cell) {
  height: 32px;
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.tcg-source-module :deep(.workbench-table td.el-table__cell) {
  height: 36px;
  font-size: 12px;
}

.tcg-preview {
  position: relative;
  border: 1px solid var(--tcg-panel-border);
  border-radius: 14px;
  background: var(--tcg-panel-bg);
  box-shadow: var(--tcg-panel-shadow), var(--tcg-soft-inset);
}

.tcg-preview::before,
.tcg-input-module::before,
.tcg-reference-library::before {
  position: absolute;
  inset: 0 0 auto;
  height: 3px;
  border-radius: 14px 14px 0 0;
  background: var(--tcg-panel-rail);
  content: '';
  opacity: 0.82;
}

.tcg-panel {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 12px;
  border-bottom: 1px solid var(--color-border-light);
  padding: 16px 18px;
}

.tcg-panel:last-child {
  border-bottom: 0;
}

.tcg-panel__header,
.tcg-section-title,
.tcg-preview__toolbar {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.tcg-panel__header > div,
.tcg-preview__header > div,
.tcg-section-title > div {
  min-width: 0;
}

.tcg-module-heading {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 12px;
}

.tcg-module-heading__index {
  display: inline-flex;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.68), rgba(255, 255, 255, 0)) padding-box,
    var(--color-primary-soft);
  color: var(--color-primary-hover);
  font-size: 15px;
  font-weight: 850;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  box-shadow:
    inset 0 0 0 1px rgba(15, 98, 254, 0.08),
    0 8px 18px rgba(15, 98, 254, 0.1);
}

.tcg-module-heading > div {
  min-width: 0;
}

.tcg-panel__header h2,
.tcg-section-title h2 {
  margin: 0;
  color: var(--color-text-main);
  font-size: 15px;
  font-weight: 800;
  letter-spacing: 0;
  line-height: 1.25;
  text-wrap: balance;
}

.tcg-panel__header p {
  margin: 5px 0 0;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.45;
}

.tcg-panel__actions {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.tcg-section-title span,
.tcg-muted {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 650;
}

.tcg-segmented {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--ui-control-radius);
  background: #ffffff;
}

.tcg-segmented button {
  min-height: 36px;
  border: 0;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
}

.tcg-segmented button.is-active {
  color: var(--color-primary);
  background: var(--color-primary-soft);
  box-shadow: inset 0 0 0 1px rgba(15, 98, 254, 0.08);
}

.tcg-control,
.tcg-full-button,
.tcg-field :deep(.el-select),
.tcg-field :deep(.el-input) {
  width: 100%;
}

.tcg-upload-placeholder {
  display: flex;
  min-height: var(--ui-control-height-md);
  align-items: center;
  gap: 8px;
  border: 1px dashed #c9d8ee;
  border-radius: var(--ui-control-radius);
  background: var(--color-primary-light);
  color: var(--color-primary-hover);
  font-size: 13px;
  font-weight: 700;
  padding: 0 12px;
}

.tcg-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
}

.tcg-input-module,
.tcg-reference-library {
  position: relative;
  gap: 14px;
  border: 1px solid var(--tcg-panel-border);
  border-radius: 14px;
  border-bottom: 1px solid var(--tcg-panel-border);
  background: var(--tcg-panel-bg);
  box-shadow: var(--tcg-panel-shadow), var(--tcg-soft-inset);
  padding: 16px 18px;
}

.tcg-input-module .tcg-panel__header,
.tcg-reference-library .tcg-panel__header {
  align-items: flex-start;
}

.tcg-input-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 18px;
}

.tcg-input-block {
  display: grid;
  min-width: 0;
  align-content: start;
  gap: 10px;
}

.tcg-input-block + .tcg-input-block {
  border-left: 1px solid var(--color-border-light);
  padding-left: 18px;
}

.tcg-input-block__header {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.tcg-input-block__header h3 {
  margin: 0;
  color: var(--color-text-main);
  font-size: 14px;
  font-weight: 800;
  letter-spacing: 0;
  line-height: 1.25;
}

.tcg-input-block__header span {
  flex: 0 0 auto;
  border-radius: var(--radius-pill);
  background: #eef5ff;
  color: #315fbe;
  font-size: 11px;
  font-weight: 800;
  line-height: 1;
  padding: 5px 8px;
}

.tcg-input-module .tcg-field {
  grid-template-columns: 104px minmax(0, 1fr);
}

.tcg-reference-categories {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 1px 0 3px;
  scrollbar-width: thin;
  scrollbar-gutter: stable;
}

.tcg-reference-category {
  display: inline-flex;
  min-height: 34px;
  flex: 0 0 auto;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(203, 213, 225, 0.86);
  border-radius: var(--radius-pill);
  background: rgba(255, 255, 255, 0.92);
  color: var(--color-text-secondary);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 750;
  padding: 0 10px;
  touch-action: manipulation;
  transition:
    background-color 160ms cubic-bezier(0.2, 0, 0, 1),
    border-color 160ms cubic-bezier(0.2, 0, 0, 1),
    color 160ms cubic-bezier(0.2, 0, 0, 1);
}

.tcg-reference-category strong {
  display: inline-flex;
  min-width: 22px;
  height: 20px;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  background: var(--color-bg-page);
  color: var(--color-text-muted);
  font-size: 11px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.tcg-reference-category:hover,
.tcg-reference-category.is-active {
  border-color: rgba(15, 98, 254, 0.28);
  background: linear-gradient(180deg, #f8fbff, var(--color-primary-soft));
  color: var(--color-primary);
}

.tcg-reference-category.is-active {
  box-shadow:
    inset 0 0 0 1px rgba(15, 98, 254, 0.1),
    0 6px 14px rgba(15, 98, 254, 0.08);
}

.tcg-reference-category:focus-visible,
.tcg-reference-type-filter button:focus-visible,
.tcg-reference-item__actions button:focus-visible,
.tcg-reference-list__footer button:focus-visible,
.tcg-static-actions button:focus-visible {
  outline: 2px solid rgba(15, 98, 254, 0.42);
  outline-offset: 2px;
}

.tcg-reference-toolbar {
  display: grid;
  grid-template-columns: minmax(300px, 1fr) minmax(360px, 440px) minmax(180px, 220px);
  align-items: center;
  gap: 12px;
}

.tcg-reference-search input,
.tcg-reference-sort select,
.tcg-dialog-field input {
  width: 100%;
  min-height: 34px;
  border: 1px solid rgba(203, 213, 225, 0.86);
  border-radius: var(--ui-control-radius);
  background: rgba(255, 255, 255, 0.94);
  color: var(--color-text-main);
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  padding: 0 12px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.025);
}

.tcg-reference-search input::placeholder,
.tcg-dialog-field input::placeholder {
  color: #9aa7b8;
}

.tcg-reference-search input:focus-visible,
.tcg-reference-sort select:focus-visible,
.tcg-dialog-field input:focus-visible {
  border-color: rgba(15, 98, 254, 0.45);
  outline: 2px solid var(--tcg-focus-ring);
  outline-offset: 0;
}

.tcg-reference-type-filter {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  overflow: hidden;
  border: 1px solid rgba(203, 213, 225, 0.86);
  border-radius: var(--ui-control-radius);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.025);
}

.tcg-reference-type-filter button {
  min-height: 32px;
  min-width: 0;
  border: 0;
  border-right: 1px solid var(--color-border-light);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 12px;
  font-weight: 750;
  line-height: 1.2;
  padding: 0 6px;
  touch-action: manipulation;
}

.tcg-reference-type-filter button:last-child {
  border-right: 0;
}

.tcg-reference-type-filter button:hover,
.tcg-reference-type-filter button.is-active {
  color: var(--color-primary);
  background: linear-gradient(180deg, #f7fbff, var(--color-primary-soft));
}

.tcg-reference-sort {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
}

.tcg-reference-sort span {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 750;
}

.tcg-inline-warning {
  display: flex;
  align-items: center;
  border: 1px solid rgba(255, 122, 26, 0.2);
  border-radius: 10px;
  background: linear-gradient(180deg, #fff7ed, var(--color-warning-soft));
  color: #b45309;
  font-size: 12px;
  font-weight: 750;
  line-height: 1.45;
  margin: 0;
  padding: 8px 10px;
}

.tcg-reference-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: visible;
  overscroll-behavior: contain;
  padding: 2px 0 0;
}

.tcg-reference-item {
  display: grid;
  width: 100%;
  grid-template-columns: 24px 30px minmax(320px, 1fr) auto;
  grid-template-areas:
    "check icon body actions";
  gap: 12px;
  align-items: center;
  border: 1px solid rgba(226, 232, 240, 0.94);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(250, 252, 255, 0.98));
  color: inherit;
  font: inherit;
  padding: 9px 11px;
  text-align: left;
  transition:
    background-color 160ms cubic-bezier(0.2, 0, 0, 1),
    border-color 160ms cubic-bezier(0.2, 0, 0, 1),
    box-shadow 160ms cubic-bezier(0.2, 0, 0, 1),
    transform 160ms cubic-bezier(0.2, 0, 0, 1);
}

.tcg-reference-item:hover,
.tcg-reference-item.is-selected {
  border-color: #c9d8ee;
  background: #ffffff;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.045);
  transform: translateY(-1px);
}

.tcg-reference-item.is-primary {
  border-color: rgba(15, 98, 254, 0.45);
  background: linear-gradient(90deg, rgba(239, 246, 255, 0.96), rgba(255, 255, 255, 0.98));
  box-shadow:
    inset 3px 0 0 var(--color-primary),
    0 6px 16px rgba(15, 98, 254, 0.08);
}

.tcg-reference-check {
  grid-area: check;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.tcg-reference-check input {
  width: 16px;
  height: 16px;
  margin: 0;
  accent-color: var(--color-primary);
  cursor: pointer;
}

.tcg-reference-item__icon {
  grid-area: icon;
  display: inline-flex;
  width: 30px;
  height: 30px;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  color: var(--color-primary);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.64), rgba(255, 255, 255, 0)),
    var(--color-primary-soft);
  box-shadow: inset 0 0 0 1px rgba(15, 98, 254, 0.08);
}

.tcg-reference-item__icon.is-md {
  color: #7c3aed;
  background: #f3e8ff;
}

.tcg-reference-item__icon.is-txt {
  color: #64748b;
  background: #eef2f7;
}

.tcg-reference-item__body {
  grid-area: body;
  min-width: 0;
}

.tcg-reference-item__title {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.tcg-reference-item__title span {
  overflow: hidden;
  color: var(--color-text-main);
  font-size: 13px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-reference-type {
  flex: 0 0 auto;
  border-radius: var(--radius-pill);
  background: #eef4ff;
  color: #315fbe;
  font-size: 11px;
  font-style: normal;
  font-weight: 800;
  line-height: 1;
  padding: 4px 7px;
}

.tcg-reference-item__body p {
  overflow: hidden;
  margin: 4px 0 0;
  color: var(--color-text-muted);
  font-size: 12px;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-reference-meta {
  display: flex;
  min-width: 0;
  gap: 6px 10px;
  flex-wrap: wrap;
  margin-top: 5px;
  color: #7b8aa0;
  font-size: 11px;
  font-weight: 650;
  line-height: 1.35;
}

.tcg-reference-meta span {
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  font-variant-numeric: tabular-nums;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-reference-item__actions {
  grid-area: actions;
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  color: #64748b;
  white-space: nowrap;
}

.tcg-reference-item__actions button,
.tcg-reference-list__footer button,
.tcg-static-actions button {
  display: inline-flex;
  min-height: 28px;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: #ffffff;
  color: var(--color-text-secondary);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 750;
  padding: 0 9px;
  touch-action: manipulation;
  transition:
    background-color 160ms cubic-bezier(0.2, 0, 0, 1),
    border-color 160ms cubic-bezier(0.2, 0, 0, 1),
    color 160ms cubic-bezier(0.2, 0, 0, 1);
}

.tcg-reference-item__actions button:not(.tcg-reference-primary-action) {
  min-width: 30px;
  padding: 0 7px;
}

.tcg-reference-item__actions button:hover,
.tcg-reference-list__footer button:hover,
.tcg-static-actions button:hover {
  border-color: rgba(15, 98, 254, 0.28);
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.tcg-reference-item__actions button:disabled,
.tcg-static-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.62;
}

.tcg-reference-primary-action {
  min-width: 82px;
}

.tcg-reference-list__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border-top: 1px solid var(--color-border-light);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.78), rgba(255, 255, 255, 0.98));
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 750;
  font-variant-numeric: tabular-nums;
  padding: 10px 2px 0;
}

.tcg-reference-pagination {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  flex-wrap: wrap;
}

.tcg-reference-page-number {
  min-width: 30px;
  padding: 0 8px !important;
}

.tcg-reference-page-number.is-active {
  border-color: rgba(15, 98, 254, 0.36);
  background: var(--color-primary-soft);
  color: var(--color-primary);
  box-shadow: inset 0 0 0 1px rgba(15, 98, 254, 0.1);
}

.tcg-reference-empty {
  display: grid;
  gap: 8px;
  justify-items: start;
  border: 1px dashed #c9d8ee;
  border-radius: 10px;
  background: #f8fbff;
  padding: 16px;
}

.tcg-reference-empty strong {
  color: var(--color-text-main);
  font-size: 13px;
  font-weight: 800;
}

.tcg-reference-empty span {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.45;
}

.tcg-field {
  display: grid;
  min-width: 0;
  grid-template-columns: 92px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
}

.tcg-field > span {
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 700;
  line-height: 1.35;
}

.tcg-field :deep(.el-select__wrapper),
.tcg-field :deep(.el-input__wrapper) {
  border-radius: var(--ui-control-radius);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: inset 0 0 0 1px var(--color-border-light);
  transition:
    box-shadow 160ms cubic-bezier(0.2, 0, 0, 1),
    background-color 160ms cubic-bezier(0.2, 0, 0, 1);
}

.tcg-field :deep(.el-select__wrapper:hover),
.tcg-field :deep(.el-input__wrapper:hover) {
  background: #ffffff;
  box-shadow: inset 0 0 0 1px #cbd7e8;
}

.tcg-field :deep(.el-select__wrapper.is-focused),
.tcg-field :deep(.el-input__wrapper.is-focus) {
  box-shadow:
    inset 0 0 0 1px rgba(15, 98, 254, 0.45),
    0 0 0 2px var(--tcg-focus-ring);
}

.tcg-source-hint {
  overflow: hidden;
  margin: 0;
  border-radius: 9px;
  background: #f8fafc;
  color: var(--color-text-muted);
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: 12px;
  font-weight: 650;
  line-height: 1.45;
  padding: 7px 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-warning-note {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--color-warning);
  font-size: 13px;
  font-weight: 750;
}

.tcg-dialog-field {
  display: grid;
  gap: 8px;
}

.tcg-dialog-field span {
  color: var(--color-text-secondary);
  font-size: 13px;
  font-weight: 750;
}

.tcg-dialog-error {
  margin: 8px 0 0;
  color: var(--color-danger);
  font-size: 13px;
  font-weight: 750;
}

.tcg-dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.tcg-static-dialog {
  display: grid;
  gap: 10px;
  color: var(--color-text-secondary);
  font-size: 13px;
  font-weight: 650;
  line-height: 1.55;
}

.tcg-static-dialog strong {
  color: var(--color-text-main);
  font-size: 14px;
  font-weight: 800;
}

.tcg-static-dialog p,
.tcg-static-dialog ul {
  margin: 0;
}

.tcg-static-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.tcg-ai-status {
  display: inline-flex;
  min-height: var(--ui-control-height-md);
  align-items: center;
  gap: 8px;
  border: 1px solid rgba(18, 183, 106, 0.2);
  border-radius: var(--ui-control-radius);
  background: var(--color-success-soft);
  color: #15803d;
  font-size: 14px;
  font-weight: 750;
  padding: 0 14px;
}

.tcg-preview {
  display: flex;
  min-height: 0;
  flex: 0 0 auto;
  flex-direction: column;
  min-width: 0;
  overflow: visible;
}

.tcg-preview__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  border-bottom: 1px solid var(--color-border-light);
  border-radius: 12px 12px 0 0;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(248, 251, 255, 0.72));
  padding: 12px 16px;
}

.tcg-preview__header h2 {
  margin: 0;
  color: var(--color-text-main);
  font-size: 14px;
  font-weight: 800;
  letter-spacing: 0;
  line-height: 1.25;
  text-wrap: balance;
}

.tcg-preview__header p {
  margin: 4px 0 0;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.45;
}

.tcg-preview__actions {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.tcg-preview__tabs {
  position: sticky;
  top: 0;
  z-index: 2;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px;
  border-bottom: 1px solid var(--color-border);
  background: #f4f8ff;
  padding: 4px;
}

.tcg-preview__tabs button {
  position: relative;
  min-width: 0;
  min-height: 38px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 14px;
  font-weight: 750;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition:
    background-color 160ms cubic-bezier(0.2, 0, 0, 1),
    color 160ms cubic-bezier(0.2, 0, 0, 1);
}

.tcg-preview__tabs button::after {
  position: absolute;
  right: 20px;
  bottom: 4px;
  left: 20px;
  height: 3px;
  border-radius: var(--radius-pill);
  background: transparent;
  content: '';
}

.tcg-preview__tabs button.is-active {
  color: var(--color-primary-hover);
  background: #ffffff;
  box-shadow:
    0 1px 2px rgba(15, 23, 42, 0.04),
    inset 0 0 0 1px rgba(15, 98, 254, 0.08);
}

.tcg-preview__tabs button.is-active::after {
  background: var(--tcg-panel-rail);
}

.tcg-preview__tabs button:hover {
  background: rgba(239, 246, 255, 0.72);
}

.tcg-preview__tabs button:focus-visible {
  z-index: 1;
  outline: 2px solid rgba(15, 98, 254, 0.42);
  outline-offset: -2px;
}

.tcg-preview__toolbar {
  border-bottom: 1px solid var(--color-border-light);
  background: rgba(255, 255, 255, 0.74);
  padding: 10px 16px;
}

.tcg-stale-notice {
  display: flex;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid rgba(255, 122, 26, 0.12);
  background: var(--color-warning-soft);
  color: #b45309;
  font-size: 13px;
  font-weight: 750;
  line-height: 1.45;
  padding: 10px 18px;
}

.tcg-api-error {
  margin: 0;
  border-bottom: 1px solid rgba(220, 38, 38, 0.12);
  background: #fef2f2;
  color: #b91c1c;
  font-size: 13px;
  font-weight: 750;
  line-height: 1.45;
  padding: 10px 18px;
}

.tcg-status-strip,
.tcg-priority-summary {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.tcg-tab-panel {
  background: rgba(255, 255, 255, 0.54);
  padding: 14px 16px 16px;
}

.tcg-brief-panel {
  display: grid;
  gap: 12px;
}

.tcg-brief-panel__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: var(--radius-md);
  background: linear-gradient(180deg, #ffffff, #f8fbff);
  padding: 11px 12px;
}

.tcg-brief-panel__header > div:first-child {
  display: grid;
  gap: 4px;
}

.tcg-brief-panel__header strong,
.tcg-brief-state strong,
.tcg-brief-error strong {
  color: var(--color-text-main);
  font-size: 14px;
  font-weight: 800;
  line-height: 1.35;
}

.tcg-brief-panel__header span,
.tcg-brief-state span {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.45;
}

.tcg-brief-panel__actions {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.tcg-brief-panel__notice {
  margin: 0;
  border: 1px solid rgba(245, 158, 11, 0.22);
  border-radius: var(--radius-md);
  background: var(--color-warning-soft);
  color: #b45309;
  font-size: 13px;
  font-weight: 750;
  line-height: 1.45;
  padding: 9px 11px;
}

.tcg-brief-state,
.tcg-brief-error {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: linear-gradient(180deg, #ffffff, #f8fbff);
  color: var(--color-text-secondary);
  padding: 14px;
}

.tcg-brief-state > div,
.tcg-brief-error > div {
  display: grid;
  gap: 8px;
}

.tcg-loading-dot {
  width: 9px;
  height: 9px;
  flex: 0 0 auto;
  border-radius: 999px;
  margin-top: 5px;
  background: var(--color-primary);
  box-shadow: 0 0 0 5px rgba(15, 98, 254, 0.12);
}

.tcg-brief-error {
  border-color: rgba(220, 38, 38, 0.18);
  background: #fef2f2;
}

.tcg-brief-error .el-icon {
  color: var(--color-danger);
  margin-top: 2px;
}

.tcg-brief-error p {
  margin: 0;
  color: #b91c1c;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.45;
}

.tcg-brief-markdown {
  display: grid;
  gap: 10px;
}

.tcg-brief-markdown pre {
  max-height: 420px;
  overflow: auto;
  margin: 0;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: linear-gradient(180deg, #ffffff, #f8fbff);
  color: var(--color-text-secondary);
  font-family:
    'Inter', 'Noto Sans SC', 'SF Pro Display', 'Segoe UI', 'PingFang SC', sans-serif;
  font-size: 13px;
  font-weight: 650;
  line-height: 1.7;
  padding: 14px;
  white-space: pre-wrap;
  word-break: break-word;
}

.tcg-brief-warning-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.tcg-brief-warning-list li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  border-radius: var(--radius-md);
  background: var(--color-warning-soft);
  color: #b45309;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.45;
  padding: 8px 10px;
}

.tcg-case-table {
  width: 100%;
  font-variant-numeric: tabular-nums;
  border-radius: var(--radius-md);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.025);
}

.tcg-case-table :deep(.el-table) {
  font-size: 12px;
}

.tcg-case-table :deep(th.el-table__cell) {
  height: 36px;
  background: linear-gradient(180deg, #f8fbff, #f3f7fc) !important;
  color: #64748b;
  font-weight: 800;
}

.tcg-case-table :deep(td.el-table__cell) {
  height: 42px;
  color: var(--color-text-secondary);
}

.tcg-case-table :deep(.el-table__row:hover > td.el-table__cell) {
  background: var(--tcg-row-hover) !important;
}

.tcg-empty-result {
  display: flex;
  min-height: 118px;
  align-items: center;
  justify-content: center;
  border: 1px dashed rgba(148, 163, 184, 0.62);
  border-radius: var(--radius-md);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.72), rgba(248, 251, 255, 0.92)),
    repeating-linear-gradient(-45deg, rgba(15, 98, 254, 0.035) 0 8px, transparent 8px 16px);
  color: var(--color-text-muted);
  font-size: 13px;
  font-weight: 750;
}

.tcg-row-more {
  color: #64748b;
}

.tcg-warning-strip {
  border-top: 1px solid var(--color-border-light);
  background: rgba(255, 255, 255, 0.72);
  padding: 12px 16px;
}

.is-primary {
  color: var(--color-primary);
  background: var(--color-primary-soft);
}

.is-success {
  color: var(--color-success);
  background: var(--color-success-soft);
}

.is-warning {
  color: var(--color-warning);
  background: var(--color-warning-soft);
}

.is-purple {
  color: #7c3aed;
  background: #f3e8ff;
}

.tcg-warning-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 0;
}

.tcg-warning-list li,
.tcg-warning-strip__items span {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #b45309;
  font-size: 13px;
  font-weight: 650;
}

.tcg-warning-list li {
  border: 1px solid rgba(255, 122, 26, 0.2);
  border-radius: 10px;
  background: linear-gradient(180deg, #fff7ed, var(--color-warning-soft));
  list-style: none;
  padding: 12px 14px;
}

.tcg-warning-strip__items {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
  border: 1px solid rgba(255, 122, 26, 0.18);
  border-radius: 10px;
  background: linear-gradient(180deg, #fff7ed, var(--color-warning-soft));
  padding: 10px 12px;
}

@media (prefers-reduced-motion: reduce) {
  .tcg-metrics :deep(.ui-metric-card),
  .tcg-reference-category,
  .tcg-reference-item,
  .tcg-reference-item__actions button,
  .tcg-reference-list__footer button,
  .tcg-static-actions button,
  .tcg-preview__tabs button {
    transition-duration: 1ms;
  }
}

@media (max-width: 1360px) {
  .tcg-reference-toolbar {
    grid-template-columns: minmax(0, 1fr) minmax(300px, 380px);
  }

  .tcg-reference-sort {
    grid-column: 1 / -1;
    max-width: 320px;
  }

}

@media (max-width: 1024px) {
  .tcg-content {
    padding: 20px;
  }

  .tcg-metrics,
  .tcg-input-grid {
    grid-template-columns: 1fr;
  }

  .tcg-input-block + .tcg-input-block {
    border-top: 1px solid var(--color-border-light);
    border-left: 0;
    padding-top: 14px;
    padding-left: 0;
  }

  .tcg-input-module .tcg-field {
    grid-template-columns: 96px minmax(0, 1fr);
  }

  .tcg-input-module .tcg-panel__header,
  .tcg-reference-library .tcg-panel__header,
  .tcg-reference-toolbar {
    grid-template-columns: 1fr;
  }

  .tcg-reference-toolbar {
    align-items: stretch;
  }

  .tcg-reference-sort {
    max-width: none;
  }

  .tcg-reference-item {
    grid-template-columns: 24px 30px minmax(0, 1fr);
    grid-template-areas:
      "check icon body"
      "actions actions actions";
  }

  .tcg-reference-item__actions {
    justify-content: flex-start;
    flex-wrap: wrap;
    white-space: normal;
  }

  .tcg-reference-list__footer {
    align-items: flex-start;
    flex-direction: column;
  }

  .tcg-reference-pagination {
    justify-content: flex-start;
  }

  .tcg-preview__header {
    align-items: flex-start;
    flex-direction: column;
  }

  .tcg-preview__actions {
    width: 100%;
    justify-content: flex-start;
  }

  .tcg-preview__tabs {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
