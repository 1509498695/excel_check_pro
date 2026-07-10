<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch, type Component } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Collection,
  CopyDocument,
  DataAnalysis,
  Document,
  DocumentChecked,
  Download,
  FolderOpened,
  Link,
  MoreFilled,
  Picture,
  Plus,
  Refresh,
  SuccessFilled,
  Upload,
  VideoPlay,
  View,
  WarningFilled,
} from '@element-plus/icons-vue'

import AppCard from '../components/shell/AppCard.vue'
import CollapsibleSection from '../components/shell/CollapsibleSection.vue'
import MetricCard from '../components/shell/MetricCard.vue'
import PageHeader from '../components/shell/PageHeader.vue'
import PrimaryButton from '../components/shell/PrimaryButton.vue'
import SecondaryButton from '../components/shell/SecondaryButton.vue'
import SvnCredentialDialog from '../components/workbench/SvnCredentialDialog.vue'
import {
  adoptSourceEvidenceVisualEvidence,
  cancelGenerationRun,
  createLocalFileSourceEvidenceRun,
  createGenerationRun,
  createSourceEvidenceRun,
  createReferenceCategory as createReferenceCategoryApi,
  deleteReferenceFile,
  downloadGenerationRunArtifact,
  exportGenerationRunWorkbook,
  fetchGenerationRunArtifactText,
  fetchSourceEvidenceCapabilities,
  fetchSourceEvidenceResources,
  fetchSourceEvidenceObservations,
  fetchSourceEvidenceVisualCandidates,
  fetchReferenceCategories,
  fetchReferenceFiles,
  getGenerationRun,
  listGenerationRunAtoms,
  listGenerationRunArtifacts,
  listGenerationRunCases,
  observeSourceEvidenceRun,
  readPlanningSnapshot,
  readPlanningSnapshotBrief,
  readSourceEvidenceSnapshot,
  requestSourceEvidenceAuthorization,
  revokeSourceEvidenceVisualEvidence,
  retrySourceEvidenceRun,
  retryFailedGenerationChunks,
  retryGenerationRunArtifacts,
  saveSourceEvidenceVisualSelections,
  setRecommendedPrimaryReference,
  uploadReferenceFile,
} from '../api/testCases'
import {
  SvnApiError,
  ensureTrailingSlash,
  fetchSvnCredential,
  getDefaultSvnCredentialTestDirUrl,
  isHttpDirUrl,
  listSvnCredentialHosts,
  listSvnDirectory,
  parseSvnHost,
  type SvnCredentialItem,
  type SvnEntry,
} from '../api/svn'
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
  SourceEvidenceAuthorizationRequestResponse,
  SourceEvidenceCapabilityStatusResponse,
  SourceEvidenceResourceResponse,
  SourceEvidenceRunResponse,
  SourceEvidenceSheetOption,
  SourceEvidenceObservationResponse,
  SourceEvidenceVisualCandidateResponse,
  TestCaseGenerationCaseResponse,
  TestCaseGenerationArtifactResponse,
  TestCaseGenerationRunResponse,
  TestCaseGenerationRunStatus,
  TestCaseGenerationResponse,
  TestCaseRequirementAtomResponse,
} from '../types/testCases'
import type { DataSource, SourceMetadata } from '../types/workbench'

type PreviewTab = 'brief' | 'cases' | 'coverage' | 'atoms' | 'warnings' | 'artifact'
type Priority = string
type ReferenceFileType = 'xlsx'
type ReferenceSort = 'recommended' | 'newest' | 'name'
type SourceMode = 'local' | 'svn' | 'feishu_doc'
type LocalReadStepStatus = 'done' | 'current' | 'pending'
type ProgressStepKey = 'source' | 'reference' | 'generate' | 'export'
type ProgressStepStatus = 'done' | 'active' | 'pending'
type ActiveGenerationInputKind = 'empty' | 'local_excel' | 'svn' | 'source_evidence' | 'legacy_feishu'
type GenerationRunStageKey =
  | 'queued'
  | 'reading'
  | 'chunking'
  | 'extracting_atoms'
  | 'merging_atoms'
  | 'blueprinting'
  | 'generating_cases'
  | 'auditing_coverage'
  | 'supplementing'
  | 'auditing_quality'
  | 'repairing_cases'
  | 'rendering_artifacts'
type GenerationRunStageStatus = 'done' | 'active' | 'pending'

interface ReadFlowStep {
  label: string
  status: LocalReadStepStatus
  statusLabel: string
  icon: Component
}

interface ActiveGenerationInput {
  kind: ActiveGenerationInputKind
  source: DataSource | null
  metadata: SourceMetadata | null
  run: SourceEvidenceRunResponse | null
  typeLabel: string
  title: string
  detail: string
  statusLabel: string
  statusType: 'success' | 'warning' | 'danger' | 'info'
  emptyMessage: string
}

interface TestCaseGenerationPlanningSourceConfig {
  planning_sources: DataSource[]
  preferred_planning_source_id: string | null
  selected_planning_sheet_name: string | null
}

interface LocalSourceUploadMeta {
  sourceId: string
  fileName: string
  size: number | null
  uploadedAt: string | null
  lastReadAt: string | null
}

interface SvnSelectedFileMeta {
  sourceId: string
  fileName: string
  size: number | null
  revision: number | null
  lastModifiedAt: string
}

interface SvnConnectionTestResult {
  status: 'success' | 'failed'
  message: string
  testedAt: string
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
  updatedAt: string
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

interface PlanningSheetSelectorOption {
  name: string
  sheet_id?: string | null
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

interface CoverageAuditDisplaySummary {
  status: string
  totalAtoms: number
  coveredAtoms: number
  uncoveredAtoms: number
  failedChunkCount: number
  exportLimitations: string[]
  warnings: string[]
}

const activeTab = ref<PreviewTab>('cases')
const selectedReferenceCategoryId = ref('')
const selectedReferenceIds = ref<string[]>([])
const primaryReferenceId = ref('')
const selectedReferenceSheetName = ref('')
const referenceSearchKeyword = ref('')
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
const activeSourceMode = ref<SourceMode>('local')
const hasUserSelectedSourceMode = ref(false)
const localUploadInputRef = ref<HTMLInputElement | null>(null)
const isLocalSourceUploading = ref(false)
const isLocalSourceDragActive = ref(false)
const isLocalSourceRefreshing = ref(false)
const localSourceUploadErrorMessage = ref('')
const localSourceUploadMeta = ref<LocalSourceUploadMeta | null>(null)
const svnFileUrl = ref('')
const svnDirectoryUrl = ref('')
const svnBaseDirectoryUrl = ref('')
const svnCurrentDirectoryUrl = ref('')
const svnDirectoryEntries = ref<SvnEntry[]>([])
const svnSelectedFileMeta = ref<SvnSelectedFileMeta | null>(null)
const svnCredentialItems = ref<SvnCredentialItem[]>([])
const svnCredentialLoadState = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const svnCredentialAttention = ref(false)
const svnConnectionTestResult = ref<SvnConnectionTestResult | null>(null)
const svnDirectoryErrorMessage = ref('')
const isSvnDirectoryLoading = ref(false)
const isSvnReadingData = ref(false)
const isSvnTestingConnection = ref(false)
const svnCredentialDialogVisible = ref(false)
const svnCredentialDialogHost = ref('')
const svnCredentialDialogDefaultUsername = ref('')
const svnCredentialDialogDefaultPassword = ref('')
const svnCredentialDialogDefaultTestDirUrl = ref('')
const sourceEvidenceUrl = ref('')
const sourceEvidenceRun = ref<SourceEvidenceRunResponse | null>(null)
const sourceEvidenceRunUrl = ref('')
const sourceEvidenceSnapshotRunId = ref<number | null>(null)
const sourceEvidenceResources = ref<SourceEvidenceResourceResponse[]>([])
const sourceEvidenceVisualCandidates = ref<SourceEvidenceVisualCandidateResponse[]>([])
const sourceEvidenceRecommendedVisualRefs = ref<string[]>([])
const sourceEvidenceSelectedVisualRefs = ref<string[]>([])
const sourceEvidenceObservations = ref<SourceEvidenceObservationResponse[]>([])
const sourceEvidenceAuthorizationResult = ref<SourceEvidenceAuthorizationRequestResponse | null>(null)
const sourceEvidenceAuthorizationErrorMessage = ref('')
const sourceEvidenceResourcesDrawerVisible = ref(false)
const sourceEvidenceApiErrorMessage = ref('')
const sourceEvidenceResourcesErrorMessage = ref('')
const sourceEvidenceCapabilityStatus = ref<SourceEvidenceCapabilityStatusResponse | null>(null)
const isSourceEvidenceCreating = ref(false)
const isSourceEvidenceRetrying = ref(false)
const isSourceEvidenceAuthorizationRequesting = ref(false)
const isSourceEvidenceResourcesLoading = ref(false)
const isSourceEvidenceVisualSaving = ref(false)
const isSourceEvidenceObserving = ref(false)
const sourceEvidenceAdoptionSavingIds = ref<number[]>([])
const planningSnapshot = ref<PlanningSnapshotResponse | null>(null)
const snapshotBriefMarkdown = ref('')
const snapshotBriefWarnings = ref<GenerationWarning[]>([])
const snapshotBriefErrorMessage = ref('')
const generationResult = ref<TestCaseGenerationResponse | null>(null)
const generationRun = ref<TestCaseGenerationRunResponse | null>(null)
const generationRunAtoms = ref<TestCaseRequirementAtomResponse[]>([])
const generationRunCases = ref<TestCaseGenerationCaseResponse[]>([])
const generationRunArtifacts = ref<TestCaseGenerationArtifactResponse[]>([])
const selectedArtifactKey = ref('workbook')
const artifactPreviewText = ref('')
const isArtifactPreviewLoading = ref(false)
const isArtifactRenderingRetrying = ref(false)
const strictMode = ref(false)
const apiErrorMessage = ref('')
const isSnapshotLoading = ref(false)
const isSnapshotBriefLoading = ref(false)
const isGeneratingCases = ref(false)
const isExportingCases = ref(false)
const isGenerationRunPolling = ref(false)
const isGenerationRunCancelling = ref(false)
const isGenerationRunRetrying = ref(false)
const snapshotBriefParticipatedInLastGeneration = ref<boolean | null>(null)
const workbenchConfigSnapshot = ref<Record<string, unknown>>({})
const hasLoadedWorkbenchConfig = ref(false)
const isPlanningSourceConfigHydrating = ref(false)
const planningSourcePersistenceError = ref('')

let snapshotBriefRequestId = 0
let generationRunPollTimer: ReturnType<typeof window.setTimeout> | null = null
let hasPlanningSourceConfigLocalEdits = false
let isApplyingPlanningSourceConfig = false

const referencePageSize = 5
const TEST_CASE_GENERATION_CONFIG_KEY = 'test_case_generation'
const GENERATION_RUN_STORAGE_KEY = 'test-case-generation:v3:last-run-id'
const PLANNING_SOURCE_TYPES = new Set<string>(['local_excel', 'feishu', 'svn'])
const SOURCE_EVIDENCE_READABLE_STATUSES = new Set(['ready', 'vision_pending'])
const SOURCE_EVIDENCE_RETRYABLE_STATUSES = new Set(['pending_permission', 'failed'])
const SOURCE_EVIDENCE_BLOCKED_STATUSES = new Set(['expired', 'cleaned'])
const SOURCE_EVIDENCE_PERMISSION_RESOURCE_STATUSES = new Set(['pending_permission', 'download_failed'])
const SOURCE_EVIDENCE_AUTHORIZATION_WAITING_STATUSES = new Set(['authorization_sent', 'already_sent'])
const SOURCE_EVIDENCE_AUTHORIZATION_READY_STATUSES = new Set(['already_authorized', 'already_readable'])
const SOURCE_EVIDENCE_AUTHORIZATION_RETRYABLE_STATUSES = new Set(['send_failed', 'bot_not_configured'])
const GENERATION_RUN_ACTIVE_STATUSES = new Set<TestCaseGenerationRunStatus>([
  'queued',
  'reading',
  'chunking',
  'extracting_atoms',
  'merging_atoms',
  'blueprinting',
  'generating_cases',
  'auditing_coverage',
  'supplementing',
  'auditing_quality',
  'repairing_cases',
  'rendering_artifacts',
])
const GENERATION_RUN_RESULT_STATUSES = new Set<TestCaseGenerationRunStatus>(['completed', 'partial_completed'])
const GENERATION_RUN_STAGE_ORDER: GenerationRunStageKey[] = [
  'queued',
  'reading',
  'chunking',
  'extracting_atoms',
  'merging_atoms',
  'blueprinting',
  'generating_cases',
  'auditing_coverage',
  'supplementing',
  'auditing_quality',
  'repairing_cases',
  'rendering_artifacts',
]
const GENERATION_RUN_STAGE_LABELS: Record<GenerationRunStageKey, string> = {
  queued: '排队中',
  reading: '读取来源',
  chunking: '结构切片',
  extracting_atoms: '抽取需求',
  merging_atoms: '合并需求',
  blueprinting: '生成蓝图',
  generating_cases: '生成用例',
  auditing_coverage: '覆盖审计',
  supplementing: '补充生成',
  auditing_quality: '质量审计',
  repairing_cases: '定向修复',
  rendering_artifacts: '生成文件',
}

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

function stringifyCaseField(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => stringifyCaseField(item)).filter(Boolean).join('\n')
  }
  if (value === null || value === undefined) {
    return ''
  }
  return String(value)
}

function mapGenerationRunCase(caseItem: TestCaseGenerationCaseResponse, index: number): GeneratedCase {
  const fields = caseItem.fields ?? {}
  const caseId = stringifyCaseField(fields.case_id) || caseItem.case_id || `TC-${String(index + 1).padStart(4, '0')}`
  const moduleName = stringifyCaseField(fields.primary_module || fields.module || fields.feature) || '-'
  const checkpoint = stringifyCaseField(
    fields.secondary_module || fields.feature || fields.scenario || fields.case_type,
  ) || '-'
  const title = stringifyCaseField(fields.checkpoint || fields.title || fields.scenario || fields.source_requirement) || '-'
  const expectedResults = stringifyCaseField(fields.expected_results)
  const remarks = stringifyCaseField(fields.remarks || fields.config_source)
  const traceText = caseItem.atom_refs.join(', ')
  return {
    id: caseId,
    module: moduleName,
    checkpoint,
    title,
    priority: stringifyCaseField(fields.priority) || 'P2',
    status: stringifyCaseField(fields.initial_status || caseItem.status) || '未执行',
    remarks: [expectedResults, remarks, traceText].filter(Boolean).join(' / ') || '-',
  }
}

function toNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function normalizePayloadMessages(items: unknown): string[] {
  if (!Array.isArray(items)) {
    return []
  }
  return items
    .map((item) => {
      if (typeof item === 'string') {
        return item
      }
      if (isRecord(item)) {
        const message = item.message ?? item.reason ?? item.type
        return typeof message === 'string' ? message : ''
      }
      return ''
    })
    .filter(Boolean)
}

const coverageAuditSummary = computed<CoverageAuditDisplaySummary>(() => {
  const payload = generationRun.value?.stage_payload ?? {}
  const audit = isRecord(payload.coverage_audit) ? payload.coverage_audit : {}
  const rootLimitations = normalizePayloadMessages(payload.export_limitations)
  const auditLimitations = normalizePayloadMessages(audit.export_limitations)
  const rootWarnings = normalizePayloadMessages(payload.warnings)
  const auditWarnings = normalizePayloadMessages(audit.warnings)
  return {
    status: typeof audit.status === 'string' ? audit.status : generationRun.value?.status ?? '',
    totalAtoms: toNumber(audit.total_atoms) || generationRun.value?.atom_count || generationRunAtoms.value.length,
    coveredAtoms: toNumber(audit.covered_atoms),
    uncoveredAtoms: toNumber(audit.uncovered_atoms),
    failedChunkCount: toNumber(audit.failed_chunk_count) || generationRun.value?.failed_chunks || 0,
    exportLimitations: [...new Set([...rootLimitations, ...auditLimitations])],
    warnings: [...new Set([...rootWarnings, ...auditWarnings])],
  }
})

const qualityAuditSummary = computed(() => {
  const payload = generationRun.value?.stage_payload ?? {}
  return isRecord(payload.quality_audit) ? payload.quality_audit : {}
})

const selectedGenerationArtifact = computed(() =>
  generationRunArtifacts.value.find((item) => item.key === selectedArtifactKey.value) ?? null,
)

const workbookGenerationArtifact = computed(() =>
  generationRunArtifacts.value.find((item) => item.key === 'workbook') ?? null,
)

const generatedCases = computed<GeneratedCase[]>(() =>
  generationRunCases.value.length
    ? generationRunCases.value.map(mapGenerationRunCase)
    : (generationResult.value?.cases ?? []).map((caseItem, index) => ({
        id: caseItem.case_id || `TC-${String(index + 1).padStart(4, '0')}`,
        module: caseItem.primary_module || caseItem.module || caseItem.feature || '-',
        checkpoint: caseItem.secondary_module || caseItem.feature || caseItem.scenario || caseItem.case_type || '-',
        title: caseItem.checkpoint || caseItem.title || caseItem.scenario || caseItem.source_requirement || '-',
        priority: caseItem.priority || 'P2',
        status: caseItem.initial_status || '未执行',
        remarks: caseItem.remarks || caseItem.config_source || '-',
      })),
)

const warnings = computed<string[]>(() => {
  const runWarnings = generationRun.value?.warnings.map((warning) => warning.message).filter(Boolean) ?? []
  const auditWarnings = coverageAuditSummary.value.warnings
  const limitationWarnings = coverageAuditSummary.value.exportLimitations
  const warningItems: GenerationWarning[] = generationResult.value
    ? [...generationResult.value.warnings, ...(generationResult.value.blueprint.warnings ?? [])]
    : planningSnapshot.value?.warnings ?? []
  return [
    ...new Set([
      ...runWarnings,
      ...auditWarnings,
      ...limitationWarnings,
      ...warningItems.map((warning) => warning.message).filter(Boolean),
    ]),
  ]
})

const tabs: Array<{ key: PreviewTab; label: string }> = [
  { key: 'cases', label: '测试用例' },
  { key: 'coverage', label: '覆盖审计' },
  { key: 'atoms', label: '需求原子' },
  { key: 'warnings', label: '限制提示' },
  { key: 'brief', label: 'AI 整理稿' },
]

const selectedPlanningSource = computed(
  () => planningSourceStore.sources.find((source) => source.id === selectedPlanningSourceId.value) ?? null,
)
const selectedPlanningSheetOptions = computed(
  () => planningSourceStore.sourceMetadataMap?.[selectedPlanningSourceId.value]?.sheets ?? [],
)
const svnPlanningSources = computed(() =>
  planningSourceStore.sources.filter((source) => source.type === 'svn'),
)
const legacyFeishuPlanningSource = computed(() =>
  selectedPlanningSource.value?.type === 'feishu'
    ? selectedPlanningSource.value
    : planningSourceStore.sources.find((source) => source.type === 'feishu') ?? null,
)
const legacyFeishuSourceMetadata = computed(() => {
  const sourceId = legacyFeishuPlanningSource.value?.id
  return sourceId ? planningSourceStore.sourceMetadataMap?.[sourceId] ?? null : null
})
const currentSvnPlanningSource = computed(() => {
  if (selectedPlanningSource.value?.type === 'svn') {
    return selectedPlanningSource.value
  }
  return svnPlanningSources.value[0] ?? null
})
const inferredSourceMode = computed<SourceMode>(() => {
  if (sourceEvidenceRun.value) {
    return sourceModeForSourceEvidenceRun(sourceEvidenceRun.value)
  }
  if (sourceEvidenceUrl.value.trim()) {
    return 'feishu_doc'
  }
  return 'local'
})
const isFeishuSourceEvidenceRun = computed(() => sourceEvidenceRun.value?.source_type === 'feishu')
const isLocalSourceEvidenceRun = computed(() => sourceEvidenceRun.value?.source_type === 'local_file')
const isSvnSourceEvidenceRun = computed(() => sourceEvidenceRun.value?.source_type === 'svn_file')
const sourceEvidenceStatus = computed(() => sourceEvidenceRun.value?.status ?? '')
const sourceEvidenceAuthorizationStatus = computed(() => sourceEvidenceAuthorizationResult.value?.status ?? '')
const isSourceEvidenceAuthorizationWaiting = computed(() =>
  SOURCE_EVIDENCE_AUTHORIZATION_WAITING_STATUSES.has(sourceEvidenceAuthorizationStatus.value),
)
const isSourceEvidenceAuthorizationReady = computed(() =>
  SOURCE_EVIDENCE_AUTHORIZATION_READY_STATUSES.has(sourceEvidenceAuthorizationStatus.value),
)
const isSourceEvidenceAuthorizationExpiredOrCleaned = computed(
  () => sourceEvidenceAuthorizationStatus.value === 'expired_or_cleaned',
)
const sourceEvidenceResourceListHasPermissionFailure = computed(() =>
  sourceEvidenceResources.value.some((resource) =>
    SOURCE_EVIDENCE_PERMISSION_RESOURCE_STATUSES.has(resource.download_status),
  ),
)
const sourceEvidenceVisualCandidateHasPermissionFailure = computed(() =>
  sourceEvidenceVisualCandidates.value.some((candidate) =>
    SOURCE_EVIDENCE_PERMISSION_RESOURCE_STATUSES.has(candidate.download_status),
  ),
)
const sourceEvidenceHasPermissionResourceFailure = computed(
  () => sourceEvidenceResourceListHasPermissionFailure.value || sourceEvidenceVisualCandidateHasPermissionFailure.value,
)
const sourceEvidenceCurrentInputNeedsAuthorization = computed(
  () =>
    SOURCE_EVIDENCE_RETRYABLE_STATUSES.has(sourceEvidenceStatus.value) ||
    sourceEvidenceResourceListHasPermissionFailure.value,
)
const sourceEvidenceNeedsAuthorization = computed(() =>
  Boolean(
    sourceEvidenceRun.value &&
      (sourceEvidenceCurrentInputNeedsAuthorization.value || sourceEvidenceVisualCandidateHasPermissionFailure.value),
  ),
)
const isSourceEvidenceBlocked = computed(
  () =>
    SOURCE_EVIDENCE_BLOCKED_STATUSES.has(sourceEvidenceStatus.value) ||
    isSourceEvidenceAuthorizationExpiredOrCleaned.value,
)
const canReadSourceEvidenceSnapshot = computed(() =>
  Boolean(sourceEvidenceRun.value && SOURCE_EVIDENCE_READABLE_STATUSES.has(sourceEvidenceStatus.value)),
)
const canRetrySourceEvidenceRun = computed(() =>
  Boolean(
    sourceEvidenceRun.value &&
      !isSourceEvidenceBlocked.value &&
      (SOURCE_EVIDENCE_RETRYABLE_STATUSES.has(sourceEvidenceStatus.value) ||
        sourceEvidenceHasPermissionResourceFailure.value ||
        sourceEvidenceAuthorizationResult.value?.can_retry_read),
  ),
)
const sourceEvidenceSnapshotRun = computed(() => {
  const run = sourceEvidenceRun.value
  if (!run || run.id !== sourceEvidenceSnapshotRunId.value) {
    return null
  }
  return run
})
const isSourceEvidenceSnapshotBlocked = computed(() => {
  const run = sourceEvidenceSnapshotRun.value
  return Boolean(
    run &&
      (SOURCE_EVIDENCE_BLOCKED_STATUSES.has(run.status) || isSourceEvidenceAuthorizationExpiredOrCleaned.value),
  )
})
const sourceEvidenceResourceCountLabel = computed(() => `${sourceEvidenceRun.value?.resource_count ?? 0} 个资源`)
const sourceEvidenceVisualSelectionLabel = computed(() => {
  if (!sourceEvidenceVisualCandidates.value.length) {
    return '推荐/已选待读取'
  }
  return `推荐 ${sourceEvidenceRecommendedVisualRefs.value.length} 个 · 已选 ${sourceEvidenceSelectedVisualRefs.value.length} 个`
})
const sourceEvidenceVisualSelectionDescription = computed(() =>
  hasSourceEvidenceSheetOptions.value
    ? '当前 Sheet 的可观察图片默认选中，用户仍可手动调整；未采纳资源不作为需求事实。'
    : '默认只选系统推荐集合，不会全量观察所有图片/附件。',
)
const sourceEvidenceAdoptedVisualEvidenceIds = computed(() =>
  sourceEvidenceObservations.value.filter((item) => item.status === 'adopted').map((item) => item.id),
)
const sourceEvidenceObservationLabel = computed(() => {
  const observedCount = sourceEvidenceObservations.value.length
  const adoptedCount = sourceEvidenceAdoptedVisualEvidenceIds.value.length
  if (!observedCount) {
    return '未观察'
  }
  return `已观察 ${observedCount} 个 · 已采纳 ${adoptedCount} 个`
})
const sourceEvidenceExpiryLabel = computed(() => formatSourceEvidenceDate(sourceEvidenceRun.value?.expires_at))
const shouldShowSourceEvidenceAuthorizationButton = computed(
  () => isFeishuSourceEvidenceRun.value && sourceEvidenceNeedsAuthorization.value && !isSourceEvidenceAuthorizationReady.value,
)
const canRequestSourceEvidenceAuthorization = computed(
  () =>
    shouldShowSourceEvidenceAuthorizationButton.value &&
    !isSourceEvidenceAuthorizationRequesting.value &&
    !isSourceEvidenceAuthorizationWaiting.value &&
    !isSourceEvidenceAuthorizationExpiredOrCleaned.value &&
    sourceEvidenceAuthorizationStatus.value !== 'invalid_run_state',
)
const sourceEvidenceAuthorizationMessage = computed(() => {
  const result = sourceEvidenceAuthorizationResult.value
  const status = result?.status ?? ''
  if (SOURCE_EVIDENCE_AUTHORIZATION_WAITING_STATUSES.has(status)) {
    return '等待作者授权，授权后请点击重试读取'
  }
  if (SOURCE_EVIDENCE_AUTHORIZATION_READY_STATUSES.has(status)) {
    return '已检测到授权，可点击重试读取'
  }
  if (SOURCE_EVIDENCE_AUTHORIZATION_RETRYABLE_STATUSES.has(status)) {
    return result?.message || '授权卡发送失败，可稍后再次申请。'
  }
  if (status === 'expired_or_cleaned') {
    return result?.message || '证据已过期或已清理，请重新读取来源。'
  }
  if (status === 'invalid_run_state') {
    return result?.message || '当前 Source Evidence 状态不可申请授权。'
  }
  if (isFeishuSourceEvidenceRun.value && sourceEvidenceNeedsAuthorization.value) {
    return '当前来源需要文档作者授权项目 App/Bot 读取。'
  }
  return ''
})
const sourceEvidenceStatusMessage = computed(() => {
  if (!sourceEvidenceRun.value) {
    if (activeSourceMode.value === 'svn') {
      return '输入 SVN 文件 URL 后创建 Source Evidence Run。'
    }
    if (activeSourceMode.value === 'feishu_doc') {
      return '输入飞书文档 URL 后读取文本/表格，并生成资源清单。'
    }
    return '上传本地文件后读取文本/表格，并生成资源清单。'
  }
  if (isSourceEvidenceBlocked.value) {
    return '证据已过期或已清理，请重新读取来源。'
  }
  if (canReadSourceEvidenceSnapshot.value) {
    return '文本/表格可继续，图片/附件待观察'
  }
  if (canRetrySourceEvidenceRun.value) {
    return '来源读取未完成，可重试读取。'
  }
  return '来源读取中或等待权限处理。'
})
const sourceEvidenceStatusTagType = computed(() => {
  if (isSourceEvidenceBlocked.value) {
    return 'danger'
  }
  if (canReadSourceEvidenceSnapshot.value) {
    return 'success'
  }
  if (canRetrySourceEvidenceRun.value) {
    return 'warning'
  }
  return 'info'
})
const sourceEvidenceSafeTitle = computed(() =>
  sanitizeSourceEvidenceDisplay(
    sourceEvidenceRun.value?.source_title || sourceEvidenceRun.value?.source_summary || sourceEvidenceEmptyTitle(),
  ),
)
const sourceEvidenceSafeSummary = computed(() =>
  sanitizeSourceEvidenceDisplay(sourceEvidenceRun.value?.source_summary || sourceEvidenceRun.value?.source_title || ''),
)
const sourceEvidenceSafeWarnings = computed<GenerationWarning[]>(() =>
  (sourceEvidenceRun.value?.warnings ?? []).map((warning) => ({
    ...warning,
    message: normalizeSourceEvidenceWarningMessage(sanitizeSourceEvidenceDisplay(warning.message)),
  })),
)
const sourceEvidenceCapabilityItems = computed(() => sourceEvidenceCapabilityStatus.value?.items ?? [])
const sourceEvidenceUnavailableCapabilityItems = computed(() =>
  sourceEvidenceCapabilityItems.value.filter((item) => !item.available),
)
const hasVisibleSourceEvidenceCapabilityWarning = computed(() =>
  Boolean(
    sourceEvidenceCapabilityStatus.value &&
      (sourceEvidenceUnavailableCapabilityItems.value.length ||
        sourceEvidenceCapabilityStatus.value.warnings?.length ||
        sourceEvidenceCapabilityStatus.value.is_project_admin),
  ),
)
const sourceEvidenceCapabilityWarnings = computed<GenerationWarning[]>(() =>
  sourceEvidenceUnavailableCapabilityItems.value.map((item) => ({
    source: 'source_evidence_capabilities',
    level: item.level,
    message: normalizeSourceEvidenceWarningMessage(
      sanitizeSourceEvidenceDisplay(`${item.message}${item.action ? ` ${item.action}` : ''}`),
    ),
  })),
)
const sourceEvidencePanelWarnings = computed<GenerationWarning[]>(() => {
  const seen = new Set<string>()
  return [...sourceEvidenceSafeWarnings.value, ...sourceEvidenceCapabilityWarnings.value].filter((warning) => {
    const key = `${warning.source}:${warning.level}:${warning.message}`
    if (seen.has(key)) {
      return false
    }
    seen.add(key)
    return true
  })
})
const isVisionAiCapabilityAvailable = computed(() => sourceEvidenceCapabilityStatus.value?.vision_ai_configured !== false)
const areSvnSourceEvidenceCapabilitiesAvailable = computed(() => {
  const status = sourceEvidenceCapabilityStatus.value
  if (!status) {
    return true
  }
  return status.svn_credential_configured && status.source_evidence_svn_roots_configured
})
const sourceEvidenceCapabilityAdminDetails = computed(() => sourceEvidenceCapabilityStatus.value?.admin_details ?? null)
const shouldShowSourceEvidenceCapabilityStatus = computed(
  () => hasVisibleSourceEvidenceCapabilityWarning.value,
)
const sourceEvidenceCapabilityStatusTone = computed(() => {
  if (!sourceEvidenceUnavailableCapabilityItems.value.length) {
    return 'is-success'
  }
  return sourceEvidenceUnavailableCapabilityItems.value.some((item) => item.level === 'error')
    ? 'is-danger'
    : 'is-warning'
})
const sourceEvidenceCapabilityStatusLabel = computed(() => {
  return sourceEvidenceUnavailableCapabilityItems.value.length ? '需关注' : '可用'
})
const sourceEvidenceCapabilityAdminDetailLines = computed(() => {
  const details = sourceEvidenceCapabilityAdminDetails.value
  if (!details || !isRecord(details)) {
    return []
  }
  const lines: string[] = []
  const configEntry = typeof details.config_entry === 'string' ? details.config_entry : ''
  if (configEntry) {
    lines.push(`配置入口：${configEntry}`)
  }
  if (typeof details.enabled_source_evidence_svn_root_count === 'number') {
    lines.push(`Source Evidence SVN Root：${details.enabled_source_evidence_svn_root_count} 个`)
  }
  const visionStatus = typeof details.vision_ai_last_test_status === 'string' ? details.vision_ai_last_test_status : ''
  const visionError =
    typeof details.vision_ai_last_test_error_summary === 'string'
      ? details.vision_ai_last_test_error_summary
      : ''
  if (visionStatus || visionError) {
    lines.push(`视觉模型测试：${[visionStatus, visionError].filter(Boolean).join(' · ')}`)
  }
  const sofficeSummary =
    typeof details.soffice_detection_summary === 'string' ? details.soffice_detection_summary : ''
  if (sofficeSummary) {
    lines.push(sofficeSummary)
  }
  return lines.map((line) => sanitizeSourceEvidenceDisplay(line))
})
const sourceEvidenceSvnCapabilityMessage = computed(() => {
  if (areSvnSourceEvidenceCapabilitiesAvailable.value) {
    return ''
  }
  const items = sourceEvidenceUnavailableCapabilityItems.value.filter((item) =>
    ['svn_credential', 'source_evidence_svn_roots'].includes(item.key),
  )
  return items.map((item) => `${item.message}${item.action ? ` ${item.action}` : ''}`).join(' ')
})
const sourceEvidenceVisionCapabilityMessage = computed(() => {
  if (isVisionAiCapabilityAvailable.value) {
    return ''
  }
  const item = sourceEvidenceCapabilityItems.value.find((entry) => entry.key === 'vision_ai')
  if (!item) {
    return '当前未配置视觉模型，图片不会参与语义理解。'
  }
  return `${item.message}${item.action ? ` ${item.action}` : ''}`
})
const sourceEvidenceSafeApiErrorMessage = computed(() =>
  sourceEvidenceApiErrorMessage.value ? sanitizeSourceEvidenceDisplay(sourceEvidenceApiErrorMessage.value) : '',
)
const sourceEvidenceSafeAuthorizationMessage = computed(() =>
  sourceEvidenceAuthorizationMessage.value
    ? sanitizeSourceEvidenceDisplay(sourceEvidenceAuthorizationMessage.value)
    : '',
)
const sourceEvidenceSafeAuthorizationErrorMessage = computed(() =>
  sourceEvidenceAuthorizationErrorMessage.value
    ? sanitizeSourceEvidenceDisplay(sourceEvidenceAuthorizationErrorMessage.value)
    : '',
)
const sourceEvidenceAuthorizationStatusLabel = computed(() => {
  const status = sourceEvidenceAuthorizationStatus.value
  if (!sourceEvidenceRun.value) {
    return '待读取'
  }
  if (isSourceEvidenceBlocked.value) {
    return '证据已过期或已清理'
  }
  if (SOURCE_EVIDENCE_AUTHORIZATION_WAITING_STATUSES.has(status)) {
    return '等待作者授权'
  }
  if (SOURCE_EVIDENCE_AUTHORIZATION_READY_STATUSES.has(status)) {
    return '已可读取'
  }
  if (SOURCE_EVIDENCE_AUTHORIZATION_RETRYABLE_STATUSES.has(status)) {
    return '发送失败'
  }
  if (sourceEvidenceHasPermissionResourceFailure.value && canReadSourceEvidenceSnapshot.value) {
    return '资源下载受限'
  }
  if (isFeishuSourceEvidenceRun.value && sourceEvidenceStatus.value === 'pending_permission') {
    return '待作者授权'
  }
  if (canReadSourceEvidenceSnapshot.value) {
    return '已可读取'
  }
  if (sourceEvidenceStatus.value === 'failed') {
    return '读取失败'
  }
  return '读取中'
})
const sourceEvidenceAuthorizationStatusDescription = computed(() => {
  const status = sourceEvidenceAuthorizationStatus.value
  if (!sourceEvidenceRun.value) {
    return sourceEvidenceEmptyAuthorizationDescription()
  }
  if (isSourceEvidenceBlocked.value) {
    return '证据已过期或已清理，请重新读取来源。'
  }
  if (SOURCE_EVIDENCE_AUTHORIZATION_WAITING_STATUSES.has(status)) {
    return '授权卡已发送，等待文档作者处理。'
  }
  if (SOURCE_EVIDENCE_AUTHORIZATION_READY_STATUSES.has(status)) {
    return '授权已可用，点击重试读取刷新来源证据。'
  }
  if (SOURCE_EVIDENCE_AUTHORIZATION_RETRYABLE_STATUSES.has(status)) {
    return sourceEvidenceSafeAuthorizationMessage.value || '授权请求发送失败，可再次申请。'
  }
  if (sourceEvidenceHasPermissionResourceFailure.value && canReadSourceEvidenceSnapshot.value) {
    return '正文和表格可继续，部分图片或附件下载需要授权。'
  }
  if (isFeishuSourceEvidenceRun.value && sourceEvidenceStatus.value === 'pending_permission') {
    return '需要文档作者授权项目 App/Bot 读取。'
  }
  return sourceEvidenceStatusMessage.value
})
const sourceEvidenceAuthorizationTagType = computed(() => {
  if (isSourceEvidenceBlocked.value) {
    return 'danger'
  }
  if (
    canReadSourceEvidenceSnapshot.value &&
    !sourceEvidenceNeedsAuthorization.value &&
    !SOURCE_EVIDENCE_AUTHORIZATION_RETRYABLE_STATUSES.has(sourceEvidenceAuthorizationStatus.value)
  ) {
    return 'success'
  }
  if (
    (isFeishuSourceEvidenceRun.value && sourceEvidenceNeedsAuthorization.value) ||
    isSourceEvidenceAuthorizationWaiting.value ||
    SOURCE_EVIDENCE_AUTHORIZATION_RETRYABLE_STATUSES.has(sourceEvidenceAuthorizationStatus.value)
  ) {
    return 'warning'
  }
  return 'info'
})
const sourceEvidenceAuthorizationToneClass = computed(() => {
  if (isSourceEvidenceBlocked.value) {
    return 'is-danger'
  }
  if (SOURCE_EVIDENCE_AUTHORIZATION_RETRYABLE_STATUSES.has(sourceEvidenceAuthorizationStatus.value)) {
    return 'is-warning'
  }
  if (isFeishuSourceEvidenceRun.value && (sourceEvidenceNeedsAuthorization.value || isSourceEvidenceAuthorizationWaiting.value)) {
    return 'is-warning'
  }
  if (canReadSourceEvidenceSnapshot.value) {
    return 'is-ready'
  }
  return 'is-neutral'
})
const sourceEvidenceAuthorizationTargetLabel = computed(() => {
  const result = sourceEvidenceAuthorizationResult.value
  if (!result) {
    return '未发送'
  }
  if (result.target_mode === 'default_chat') {
    return '默认群'
  }
  if (result.target_mode === 'creator_direct') {
    return '已发送给创建者'
  }
  if (result.target_mode === 'owner_direct') {
    return '已发送给文档作者'
  }
  return '未发送'
})
const sourceEvidenceAuthorizationSentCountLabel = computed(() => {
  const result = sourceEvidenceAuthorizationResult.value
  if (!result) {
    return '0 人'
  }
  return `${result.sent_targets_count} 人`
})
const sourceEvidenceResourceStatusLabel = computed(() => {
  if (!sourceEvidenceRun.value) {
    return '待读取'
  }
  if (sourceEvidenceHasPermissionResourceFailure.value) {
    return '资源下载受限'
  }
  if (sourceEvidenceResources.value.length || sourceEvidenceRun.value.resource_count) {
    return '资源清单已生成'
  }
  return '暂无资源'
})
const sourceEvidencePipelineSteps = computed<ReadFlowStep[]>(() => {
  const hasRun = Boolean(sourceEvidenceRun.value)
  const needsAuthorization =
    sourceEvidenceNeedsAuthorization.value ||
    isSourceEvidenceAuthorizationWaiting.value ||
    Boolean(sourceEvidenceAuthorizationResult.value)
  const hasAuthorizationRequest = Boolean(sourceEvidenceAuthorizationResult.value)
  const hasAuthorAuthorization =
    isSourceEvidenceAuthorizationReady.value || (canReadSourceEvidenceSnapshot.value && !sourceEvidenceNeedsAuthorization.value)
  const hasResourceDownload =
    Boolean(sourceEvidenceRun.value) &&
    (sourceEvidenceResources.value.length > 0 || Boolean(sourceEvidenceRun.value?.resource_count)) &&
    !sourceEvidenceHasPermissionResourceFailure.value
  const hasSnapshot = Boolean(sourceEvidenceSnapshotRun.value)
  const getStatus = (done: boolean, current: boolean): LocalReadStepStatus =>
    done ? 'done' : current ? 'current' : 'pending'

  return [
    { label: '读取链接', status: getStatus(hasRun, !hasRun), statusLabel: hasRun ? '已读取' : '待读取', icon: Link },
    {
      label: '识别 owner/creator',
      status: getStatus(hasRun, hasRun),
      statusLabel: hasRun ? '已识别' : '待处理',
      icon: View,
    },
    {
      label: '申请授权',
      status: getStatus(hasAuthorizationRequest, sourceEvidenceNeedsAuthorization.value),
      statusLabel: hasAuthorizationRequest ? '已申请' : sourceEvidenceNeedsAuthorization.value ? '当前' : '可跳过',
      icon: WarningFilled,
    },
    {
      label: '作者授权',
      status: getStatus(hasAuthorAuthorization, isSourceEvidenceAuthorizationWaiting.value),
      statusLabel: hasAuthorAuthorization ? '已可读取' : isSourceEvidenceAuthorizationWaiting.value ? '等待中' : needsAuthorization ? '待授权' : '可跳过',
      icon: SuccessFilled,
    },
    {
      label: '重试读取',
      status: getStatus(canReadSourceEvidenceSnapshot.value && Boolean(sourceEvidenceAuthorizationResult.value), canRetrySourceEvidenceRun.value),
      statusLabel: canRetrySourceEvidenceRun.value ? '可重试' : canReadSourceEvidenceSnapshot.value ? '可继续' : '待处理',
      icon: Refresh,
    },
    {
      label: '下载图片/附件',
      status: getStatus(hasResourceDownload, sourceEvidenceHasPermissionResourceFailure.value),
      statusLabel: hasResourceDownload ? '已完成' : sourceEvidenceHasPermissionResourceFailure.value ? '受限' : '待处理',
      icon: Picture,
    },
    {
      label: '生成快照',
      status: getStatus(hasSnapshot, canReadSourceEvidenceSnapshot.value),
      statusLabel: hasSnapshot ? '已生成' : canReadSourceEvidenceSnapshot.value ? '待生成' : '待处理',
      icon: DocumentChecked,
    },
  ]
})
const localSourceChipStatus = computed(() => (isLocalSourceEvidenceRun.value && canReadSourceEvidenceSnapshot.value ? '已读取' : '待读取'))
const svnSourceChipStatus = computed(() => {
  if (isSvnSourceEvidenceRun.value && canReadSourceEvidenceSnapshot.value) {
    return '已读取'
  }
  return svnFileUrl.value.trim() || isSvnSourceEvidenceRun.value ? '待读取' : '待选择文件'
})
const feishuDocumentChipStatus = computed(() => {
  if (canReadSourceEvidenceSnapshot.value) {
    return '已读取'
  }
  if (sourceEvidenceNeedsAuthorization.value || isSourceEvidenceAuthorizationWaiting.value) {
    return '待授权'
  }
  return '待读取'
})
const localSourcePanelStatus = computed(() => {
  if (isLocalSourceEvidenceRun.value) {
    return sourceEvidenceStatusMessage.value
  }
  return '等待上传本地文件。'
})
const localSourceFileName = computed(() => {
  if (isLocalSourceEvidenceRun.value) {
    return sourceEvidenceSafeTitle.value
  }
  if (localSourceUploadMeta.value) {
    return localSourceUploadMeta.value.fileName
  }
  return '未选择文件'
})
const localSourceSheetCountLabel = computed(() => {
  return isLocalSourceEvidenceRun.value ? sourceEvidenceResourceCountLabel.value : '未生成'
})
const localSourceSelectedSheetLabel = computed(() => {
  return isLocalSourceEvidenceRun.value ? sourceEvidenceStatus.value || '待读取' : '未选择'
})
const localSourceSnapshotRowsLabel = computed(() => {
  if (!isLocalSourceEvidenceRun.value) {
    return '待读取快照'
  }
  return sourceEvidenceSnapshotRunId.value && planningSnapshot.value ? `${planningSnapshot.value.rows.length} 行` : '待读取快照'
})
const localSourceLastReadAtLabel = computed(() => {
  if (!localSourceUploadMeta.value?.lastReadAt) {
    return '未记录'
  }
  return formatLocalSourceTime(localSourceUploadMeta.value.lastReadAt)
})
const localSourceFileSizeLabel = computed(() => {
  const size = localSourceUploadMeta.value?.size ?? null
  if (!size) {
    return '未记录'
  }
  if (size < 1024 * 1024) {
    return `${Math.max(1, Math.round(size / 1024))} KB`
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`
})
const localReadFlowSteps = computed<ReadFlowStep[]>(() => {
  const hasSource = isLocalSourceEvidenceRun.value
  const hasResourceList = hasSource && Boolean(sourceEvidenceRun.value?.resource_count)
  const hasSelectedVisuals = hasSource && sourceEvidenceSelectedVisualRefs.value.length > 0
  const hasLocalSnapshot = hasSource && Boolean(sourceEvidenceSnapshotRunId.value && planningSnapshot.value)
  const hasGeneratedLocalCases = hasLocalSnapshot && Boolean(generationResult.value)
  const getStatus = (done: boolean, current: boolean): LocalReadStepStatus =>
    done ? 'done' : current ? 'current' : 'pending'

  return [
    { label: '上传文件', status: getStatus(hasSource, !hasSource), statusLabel: hasSource ? '已完成' : '进行中', icon: Upload },
    {
      label: '生成资源清单',
      status: getStatus(hasResourceList, hasSource),
      statusLabel: hasResourceList ? '已完成' : hasSource ? '进行中' : '待处理',
      icon: DataAnalysis,
    },
    {
      label: '选择视觉证据',
      status: getStatus(hasSelectedVisuals, hasResourceList),
      statusLabel: hasSelectedVisuals ? '已选择' : hasResourceList ? '待处理' : '待处理',
      icon: Collection,
    },
    {
      label: '读取快照',
      status: getStatus(hasLocalSnapshot, hasSource),
      statusLabel: hasLocalSnapshot ? '已完成' : hasSource ? '待处理' : '待处理',
      icon: DocumentChecked,
    },
    {
      label: '生成用例',
      status: getStatus(hasGeneratedLocalCases, hasLocalSnapshot),
      statusLabel: hasGeneratedLocalCases ? '已完成' : hasLocalSnapshot ? '待处理' : '待处理',
      icon: VideoPlay,
    },
  ]
})
const svnCurrentHost = computed(() => {
  const sourceLocator = currentSvnPlanningSource.value?.pathOrUrl ?? currentSvnPlanningSource.value?.url ?? ''
  return parseSvnHost(svnFileUrl.value) || parseSvnHost(svnDirectoryUrl.value) || parseSvnHost(sourceLocator)
})
const currentSvnCredentialItem = computed(
  () => svnCredentialItems.value.find((item) => item.host === svnCurrentHost.value) ?? null,
)
const hasCurrentSvnCredential = computed(() => Boolean(currentSvnCredentialItem.value?.username))
const svnCredentialStatusLabel = computed(() => {
  if (!svnCurrentHost.value) {
    return '未选择 host'
  }
  if (svnCredentialAttention.value) {
    return '需要配置凭据'
  }
  return hasCurrentSvnCredential.value ? '已配置' : '未配置'
})
const svnCredentialUsernameLabel = computed(() => maskSvnUsername(currentSvnCredentialItem.value?.username ?? ''))
const svnCredentialLastTestLabel = computed(() => {
  if (!svnConnectionTestResult.value) {
    return '未测试'
  }
  return svnConnectionTestResult.value.status === 'success' ? '连接正常' : svnConnectionTestResult.value.message
})
const svnCredentialLastTestTimeLabel = computed(() =>
  svnConnectionTestResult.value ? formatLocalSourceTime(svnConnectionTestResult.value.testedAt) : '未记录',
)
const isSvnCredentialStatusWarning = computed(() =>
  svnCredentialAttention.value || svnConnectionTestResult.value?.status === 'failed',
)
const svnSelectedFileName = computed(() => {
  if (isSvnSourceEvidenceRun.value) {
    return sourceEvidenceSafeTitle.value
  }
  const pendingFileName = extractSvnFileName(svnFileUrl.value)
  if (pendingFileName) {
    return pendingFileName
  }
  const source = currentSvnPlanningSource.value
  if (!source) {
    return '未选择文件'
  }
  if (svnSelectedFileMeta.value?.sourceId === source.id) {
    return svnSelectedFileMeta.value.fileName
  }
  return extractSvnFileName(source.pathOrUrl ?? source.url ?? '') || '已选择 SVN 文件'
})
const svnSelectedFileDetailLabel = computed(() => {
  if (isSvnSourceEvidenceRun.value) {
    return sourceEvidenceSafeSummary.value || sourceEvidenceStatusMessage.value
  }
  if (extractSvnFileName(svnFileUrl.value)) {
    return '等待创建 Source Evidence Run'
  }
  const source = currentSvnPlanningSource.value
  if (!source) {
    return '请输入具体 SVN 文件 URL'
  }
  if (svnSelectedFileMeta.value?.sourceId === source.id) {
    const sizeLabel = formatSvnSize(svnSelectedFileMeta.value.size)
    const revisionLabel = svnSelectedFileMeta.value.revision ? `r${svnSelectedFileMeta.value.revision}` : '版本未记录'
    return `${sizeLabel} · ${revisionLabel}`
  }
  return '已选择 SVN 文件'
})
const svnVisibleDirectoryEntries = computed(() =>
  svnDirectoryEntries.value.filter((entry) => entry.kind === 'dir' || isSvnExcelEntry(entry)),
)
const svnCurrentDepth = computed(() => {
  if (!svnBaseDirectoryUrl.value || !svnCurrentDirectoryUrl.value) {
    return 0
  }
  if (svnBaseDirectoryUrl.value === svnCurrentDirectoryUrl.value) {
    return 0
  }
  const baseSegments = svnBaseDirectoryUrl.value.replace(/\/$/, '').split('/').length
  const currentSegments = svnCurrentDirectoryUrl.value.replace(/\/$/, '').split('/').length
  return Math.max(0, currentSegments - baseSegments)
})
const canEnterSvnSubdirectory = computed(() => svnCurrentDepth.value < 1)
const svnReadFlowSteps = computed<ReadFlowStep[]>(() => {
  const hasUrl = Boolean(svnFileUrl.value.trim())
  const hasRun = isSvnSourceEvidenceRun.value
  const hasResources = hasRun && Boolean(sourceEvidenceRun.value?.resource_count)
  const hasSvnSnapshot = hasRun && Boolean(sourceEvidenceSnapshotRunId.value && planningSnapshot.value)
  const getStatus = (done: boolean, current: boolean): LocalReadStepStatus =>
    done ? 'done' : current ? 'current' : 'pending'

  return [
    { label: '输入文件 URL', status: getStatus(hasUrl || hasRun, !hasUrl && !hasRun), statusLabel: hasUrl || hasRun ? '已输入' : '进行中', icon: Link },
    {
      label: '创建证据 Run',
      status: getStatus(hasRun, hasUrl),
      statusLabel: hasRun ? '已创建' : hasUrl ? '待处理' : '待处理',
      icon: DataAnalysis,
    },
    {
      label: '生成资源清单',
      status: getStatus(hasResources, hasRun),
      statusLabel: hasResources ? '已完成' : hasRun ? '进行中' : '待处理',
      icon: Collection,
    },
    {
      label: '读取快照',
      status: getStatus(hasSvnSnapshot, hasRun),
      statusLabel: hasSvnSnapshot ? '已完成' : hasRun ? '待处理' : '待处理',
      icon: DocumentChecked,
    },
  ]
})
const svnSourcePanelStatus = computed(() =>
  isSvnSourceEvidenceRun.value
    ? sourceEvidenceStatusMessage.value
    : svnFileUrl.value.trim()
      ? '已输入 SVN 文件 URL，待读取来源证据。'
      : '等待输入 SVN 文件 URL',
)
const canReadActiveSourceEvidenceSnapshot = computed(
  () =>
    canReadSourceEvidenceSnapshot.value &&
    !isSourceEvidenceBlocked.value &&
    !sourceEvidenceCurrentInputNeedsAuthorization.value,
)
const activeGenerationInput = computed<ActiveGenerationInput>(() => {
  if (sourceEvidenceRun.value) {
    return {
      kind: 'source_evidence',
      source: null,
      metadata: null,
      run: sourceEvidenceRun.value,
      typeLabel: sourceEvidenceTypeLabel(sourceEvidenceRun.value),
      title: sourceEvidenceSafeTitle.value,
      detail: sourceEvidenceAuthorizationStatusDescription.value,
      statusLabel: sourceEvidenceAuthorizationStatusLabel.value,
      statusType: sourceEvidenceAuthorizationTagType.value as ActiveGenerationInput['statusType'],
      emptyMessage: '',
    }
  }

  if (activeSourceMode.value === 'local') {
    if (legacyFeishuPlanningSource.value) {
      const metadata = legacyFeishuSourceMetadata.value
      return {
        kind: 'legacy_feishu',
        source: legacyFeishuPlanningSource.value,
        metadata,
        run: null,
        typeLabel: '飞书电子表格',
        title: legacyFeishuPlanningSource.value.id,
        detail: metadata ? `${metadata.sheets.length} 个 Sheet` : '等待识别 Sheet',
        statusLabel: metadata ? '已读取' : '待读取',
        statusType: metadata ? 'success' : 'info',
        emptyMessage: '',
      }
    }
    return {
      kind: 'empty',
        source: null,
        metadata: null,
        run: null,
        typeLabel: '本地文件',
        title: '未选择文件',
        detail: '等待上传本地文件',
        statusLabel: '待读取',
        statusType: 'info',
        emptyMessage: '等待上传本地文件',
      }
    }

  if (activeSourceMode.value === 'svn') {
    return {
      kind: 'empty',
      source: null,
      metadata: null,
      run: null,
      typeLabel: 'SVN 文件',
      title: '未选择文件',
      detail: '等待输入 SVN 文件 URL',
      statusLabel: '待选择文件',
      statusType: 'info',
      emptyMessage: '等待输入 SVN 文件 URL',
    }
  }

  return {
    kind: 'empty',
    source: null,
    metadata: null,
    run: null,
    typeLabel: '飞书文档',
    title: '未读取文档',
    detail: '等待读取飞书文档',
    statusLabel: '待读取',
    statusType: 'info',
    emptyMessage: '等待读取飞书文档',
  }
})
const activeGenerationInputSourceId = computed(() => activeGenerationInput.value.source?.id ?? '')
const activeGenerationInputKey = computed(() => {
  const input = activeGenerationInput.value
  if (input.kind === 'source_evidence') {
    return `${input.kind}:${input.run?.id ?? 'none'}:${sourceEvidenceStatus.value}:${sourceEvidenceAuthorizationStatus.value}`
  }
  return `${input.kind}:${input.source?.id ?? 'none'}`
})
const sourceEvidenceSheetOptions = computed<SourceEvidenceSheetOption[]>(() => sourceEvidenceRun.value?.sheet_options ?? [])
const hasSourceEvidenceSheetOptions = computed(() => sourceEvidenceSheetOptions.value.length > 0)
const activePlanningSheetOptions = computed<PlanningSheetSelectorOption[]>(() => {
  if (activeGenerationInput.value.kind === 'source_evidence') {
    return sourceEvidenceSheetOptions.value
  }
  return activeGenerationInput.value.metadata?.sheets ?? []
})
const hasPlanningSheetOptions = computed(() => activePlanningSheetOptions.value.length > 0)
const activeGenerationInputIconLabel = computed(() => {
  if (activeGenerationInput.value.kind === 'svn') {
    return 'SVN'
  }
  if (activeGenerationInput.value.kind === 'source_evidence') {
    return 'Doc'
  }
  if (activeGenerationInput.value.kind === 'legacy_feishu') {
    return '表'
  }
  return 'XLS'
})
const activeGenerationSourceSummary = computed(() => {
  const input = activeGenerationInput.value
  if (input.kind === 'empty') {
    return input.emptyMessage
  }
  if (input.kind === 'source_evidence') {
    return sourceEvidenceStatusMessage.value
  }
  return hasPlanningSheetOptions.value ? `已读取 ${activePlanningSheetOptions.value.length} 个 Sheet` : '等待读取 Sheet'
})
const activeGenerationReadinessLabel = computed(() => {
  const input = activeGenerationInput.value
  if (input.kind === 'source_evidence') {
    if (isSourceEvidenceBlocked.value) {
      return '证据已过期或已清理，请重新读取来源。'
    }
    if (sourceEvidenceCurrentInputNeedsAuthorization.value) {
      return '当前来源需要先申请授权或重试读取。'
    }
    if (sourceEvidenceGenerationBlockMessage.value) {
      return sourceEvidenceGenerationBlockMessage.value
    }
    if (hasSourceEvidenceSheetOptions.value) {
      return selectedPlanningSheetName.value
        ? `当前 Sheet：${selectedPlanningSheetName.value}`
        : '请选择 Sheet 后读取快照'
    }
    return canReadActiveSourceEvidenceSnapshot.value ? '可生成兼容快照' : '等待来源读取完成'
  }
  if (input.kind === 'empty') {
    return input.emptyMessage || '当前来源无可选 Sheet'
  }
  if (!hasPlanningSheetOptions.value) {
    return '当前来源无可选 Sheet'
  }
  return `已读取 ${activePlanningSheetOptions.value.length} 个 Sheet`
})
const shouldShowPlanningSheetSelector = computed(() => hasPlanningSheetOptions.value)

const currentReferenceCategory = computed(
  () => referenceCategories.value.find((category) => category.id === selectedReferenceCategoryId.value) ?? null,
)
const referenceUploadCategoryLabel = computed(() => currentReferenceCategory.value?.name ?? '未选择分类')
const referenceUploadFileName = computed(() => referenceUploadFile.value?.name ?? '选择 Excel 参考案例')
const referenceUploadFileDetail = computed(() => {
  const file = referenceUploadFile.value
  if (!file) {
    return '支持 .xlsx / .xls'
  }
  if (!isExcelReferenceUploadFile(file)) {
    return '格式不支持，请换成 Excel 文件'
  }
  return `${formatSvnSize(file.size)} · 等待上传`
})
const referenceUploadFileStatusLabel = computed(() => {
  const file = referenceUploadFile.value
  if (!file) {
    return '待选择文件'
  }
  return isExcelReferenceUploadFile(file) ? '已选择' : '格式不支持'
})
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
const hasGenerationRunResult = computed(() =>
  Boolean(generationRun.value && GENERATION_RUN_RESULT_STATUSES.has(generationRun.value.status) && generationRun.value.case_count > 0),
)
const hasGeneratedResult = computed(() => hasGenerationRunResult.value || Boolean(generationResult.value))
const hasSnapshotBriefMarkdown = computed(() => Boolean(snapshotBriefMarkdown.value.trim()))
const selectedGenerationSheetName = computed(() => {
  const explicitSheetName = getSelectedSourceEvidenceSheetName() || selectedPlanningSheetName.value.trim()
  if (explicitSheetName) {
    return explicitSheetName
  }
  return sourceEvidenceRun.value ? 'Source Evidence' : ''
})
const canReadSnapshot = computed(() => {
  const input = activeGenerationInput.value
  if (input.kind === 'source_evidence') {
    return canReadActiveSourceEvidenceSnapshot.value && (!hasSourceEvidenceSheetOptions.value || Boolean(selectedPlanningSheetName.value))
  }
  if (input.kind === 'empty') {
    return false
  }
  return Boolean(input.source && selectedPlanningSheetName.value && hasPlanningSheetOptions.value)
})
const sourceEvidenceTextlessNeedsAdoption = computed(() => {
  if (!sourceEvidenceRun.value || sourceEvidenceAdoptedVisualEvidenceIds.value.length > 0) {
    return false
  }
  const warningMessages = [
    ...sourceEvidenceSafeWarnings.value.map((warning) => warning.message),
    ...(planningSnapshot.value?.warnings ?? []).map((warning) => warning.message),
  ]
  return warningMessages.some(isTextlessSourceEvidenceWarning)
})
const sourceEvidenceGenerationBlockMessage = computed(() =>
  sourceEvidenceTextlessNeedsAdoption.value
    ? '当前来源缺少文本主体，需先观察并采纳视觉证据后才能生成。'
    : '',
)
const isGenerationReady = computed(
  () =>
    Boolean(sourceEvidenceRun.value) &&
    Boolean(selectedGenerationSheetName.value) &&
    canReadActiveSourceEvidenceSnapshot.value &&
    !isSnapshotLoading.value &&
    !isGeneratingCases.value &&
    !isGenerationRunPolling.value &&
    !isSourceEvidenceSnapshotBlocked.value &&
    !sourceEvidenceTextlessNeedsAdoption.value,
)
const prioritySummary = computed(() => {
  if (generationRunCases.value.length) {
    return Object.entries(
      generationRunCases.value.reduce<Record<string, number>>((accumulator, caseItem) => {
        const priority = stringifyCaseField(caseItem.fields.priority) || 'P2'
        accumulator[priority] = (accumulator[priority] ?? 0) + 1
        return accumulator
      }, {}),
    )
  }
  return Object.entries(generationResult.value?.stats.priority_counts ?? {})
})
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
  if (generationRun.value) {
    return getGenerationRunStatusLabel(generationRun.value.status)
  }
  if (generationResult.value) {
    return '用例已生成'
  }
  if (planningSnapshot.value) {
    return '快照已读取'
  }
  return '待读取快照'
})
const previewStatusType = computed(() => {
  if (!generationRun.value) {
    return generationResult.value ? 'primary' : planningSnapshot.value ? 'success' : 'info'
  }
  if (generationRun.value.status === 'failed' || generationRun.value.status === 'expired') {
    return 'danger'
  }
  if (generationRun.value.status === 'partial_completed') {
    return 'warning'
  }
  if (generationRun.value.status === 'cancelled') {
    return 'info'
  }
  return GENERATION_RUN_RESULT_STATUSES.has(generationRun.value.status) ? 'success' : 'primary'
})
const canExportGeneratedResult = computed(
  () =>
    Boolean(generationRun.value) &&
    (generationRun.value?.status === 'completed' ||
      (generationRun.value?.status === 'partial_completed' && !generationRunStrictExportBlocked.value)) &&
    generationRun.value.case_count > 0 &&
    (!workbookGenerationArtifact.value || workbookGenerationArtifact.value.status === 'ready') &&
    !isGeneratedResultStale.value &&
    !isSourceEvidenceSnapshotBlocked.value,
)
const canDownloadSelectedArtifact = computed(() =>
  selectedGenerationArtifact.value
    ? selectedGenerationArtifact.value.status === 'ready'
    : canExportGeneratedResult.value,
)
const selectedReferenceSummary = computed(() => {
  if (!selectedReferenceFiles.value.length) {
    return '未选择参考案例 · 使用 qa-case 标准生成'
  }
  if (!primaryReference.value) {
    return `已选 ${selectedReferenceFiles.value.length} 个 · 未指定主参考`
  }
  return `已选 ${selectedReferenceFiles.value.length} 个 · 主参考：${primaryReference.value.name}`
})
const referenceEntrySummary = computed(() => {
  if (!selectedReferenceFiles.value.length) {
    return '未选择参考案例'
  }
  const primaryName = primaryReference.value?.name ?? '未指定主参考'
  return `已选 ${selectedReferenceFiles.value.length} 个 · 主参考：${primaryName}`
})
const referenceSelectionRecommendationLabel = computed(() => {
  if (!selectedReferenceFiles.value.length) {
    return '未选择'
  }
  if (primaryReference.value?.isRecommendedPrimary) {
    return '推荐主参考'
  }
  if (primaryReference.value) {
    return '手动主参考'
  }
  if (selectedReferenceFiles.value.some((file) => file.isRecommendedPrimary)) {
    return '包含推荐'
  }
  return '补充参考'
})
const referenceSelectionSourceLabel = computed(() => {
  if (!selectedReferenceFiles.value.length) {
    return '未选择 Excel'
  }
  if (selectedReferenceFiles.value.length === 1) {
    return selectedReferenceFiles.value[0]?.name ?? 'Excel 参考案例'
  }
  return `${selectedReferenceFiles.value[0]?.name ?? 'Excel 参考案例'} 等 ${selectedReferenceFiles.value.length} 个`
})
const referenceSelectionLatestUpdateLabel = computed(() => {
  if (!selectedReferenceFiles.value.length) {
    return '未选择'
  }
  const latestTimestamp = Math.max(
    ...selectedReferenceFiles.value.map((file) => new Date(file.updatedAt || file.uploadedAt).getTime()),
  )
  return Number.isFinite(latestTimestamp) ? formatReferenceUploadTime(new Date(latestTimestamp).toISOString()) : '未记录'
})
const profilePreviewFile = computed(
  () => referenceFiles.value.find((file) => file.id === profilePreviewFileId.value) ?? null,
)
const referenceMoreFile = computed(() => referenceFiles.value.find((file) => file.id === referenceMoreFileId.value) ?? null)
const generationRunStrictExportBlocked = computed(
  () =>
    Boolean(generationRun.value?.strict_mode) &&
    (coverageAuditSummary.value.uncoveredAtoms > 0 || Boolean(qualityAuditSummary.value.blocks_export)),
)
const generationRunPartialMessages = computed(() => {
  const messages: string[] = []
  if (generationRun.value?.status === 'partial_completed') {
    messages.push('partial_completed：当前结果存在覆盖缺口或阶段限制。')
  }
  if (coverageAuditSummary.value.uncoveredAtoms > 0) {
    messages.push(`未覆盖 Requirement Atom ${coverageAuditSummary.value.uncoveredAtoms} 个。`)
  }
  if (coverageAuditSummary.value.failedChunkCount > 0) {
    messages.push(`失败 chunk ${coverageAuditSummary.value.failedChunkCount} 个。`)
  }
  const qualityBlockingCount = toNumber(qualityAuditSummary.value.blocking_count)
  const qualityWarningCount = toNumber(qualityAuditSummary.value.warning_count)
  if (qualityBlockingCount > 0) {
    messages.push(`Case Quality Audit 有 ${qualityBlockingCount} 个阻塞问题。`)
  }
  if (qualityWarningCount > 0) {
    messages.push(`Case Quality Audit 有 ${qualityWarningCount} 个警告。`)
  }
  messages.push(...coverageAuditSummary.value.exportLimitations)
  if (generationRunStrictExportBlocked.value) {
    messages.push('严格模式下存在覆盖或质量阻塞，不能下载 Excel。')
  }
  return [...new Set(messages)]
})
const generationRunStageItems = computed<
  Array<{
    key: GenerationRunStageKey
    label: string
    status: GenerationRunStageStatus
  }>
>(() => {
  const currentStatus = generationRun.value?.status
  const currentIndex = currentStatus ? GENERATION_RUN_STAGE_ORDER.indexOf(currentStatus as GenerationRunStageKey) : -1
  const isTerminal = currentStatus ? !GENERATION_RUN_ACTIVE_STATUSES.has(currentStatus) : false
  return GENERATION_RUN_STAGE_ORDER.map((key, index) => ({
    key,
    label: GENERATION_RUN_STAGE_LABELS[key],
    status:
      currentIndex < 0
        ? 'pending'
        : isTerminal || index < currentIndex
          ? 'done'
          : index === currentIndex
            ? 'active'
            : 'pending',
  }))
})
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
    label: 'V3 用例',
    value: generationRun.value ? `${generationRun.value.case_count} 条` : '未生成',
    statusLabel: generationRun.value ? getGenerationRunStatusLabel(generationRun.value.status) : '待生成',
    statusType: generationRun.value ? ('success' as const) : ('neutral' as const),
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
const progressStepItems = computed<
  Array<{
    key: ProgressStepKey
    step: number
    label: string
    description: string
    status: ProgressStepStatus
  }>
>(() => {
  const hasReadableSource = canReadSnapshot.value || hasPlanningSnapshot.value
  const hasSelectedReference = selectedReferenceFiles.value.length > 0
  const hasGeneratedCases = hasGeneratedResult.value

  return [
    {
      key: 'source',
      step: 1,
      label: '数据源',
      description: hasReadableSource ? activeGenerationInput.value.statusLabel : '待读取来源',
      status: hasReadableSource ? 'done' : 'active',
    },
    {
      key: 'reference',
      step: 2,
      label: '参考',
      description: hasSelectedReference ? `已选 ${selectedReferenceFiles.value.length} 个` : '可选增强',
      status: hasSelectedReference ? 'done' : hasReadableSource ? 'active' : 'pending',
    },
    {
      key: 'generate',
      step: 3,
      label: '生成',
      description: hasGeneratedCases
        ? `${generationRun.value?.case_count ?? generationResult.value?.stats.total ?? 0} 条用例`
        : sourceEvidenceRun.value
          ? '可全量生成'
          : '待读取来源',
      status: hasGeneratedCases ? 'done' : sourceEvidenceRun.value ? 'active' : 'pending',
    },
    {
      key: 'export',
      step: 4,
      label: '导出',
      description: generationRunArtifacts.value.some((item) => item.status === 'ready')
        ? '文件已生成'
        : hasGeneratedCases
          ? '结果需确认'
          : '待生成结果',
      status: generationRunArtifacts.value.some((item) => item.status === 'ready')
        ? 'done'
        : hasGeneratedCases
          ? 'active'
          : 'pending',
    },
  ]
})

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function getGenerationRunStatusLabel(status: TestCaseGenerationRunStatus): string {
  const labels: Record<TestCaseGenerationRunStatus, string> = {
    queued: '排队中',
    reading: '读取来源',
    chunking: '结构切片',
    extracting_atoms: '抽取需求',
    merging_atoms: '合并需求',
    blueprinting: '生成蓝图',
    generating_cases: '生成用例',
    auditing_coverage: '覆盖审计',
    supplementing: '补充生成',
    auditing_quality: '质量审计',
    repairing_cases: '定向修复',
    rendering_artifacts: '生成文件',
    completed: '已完成',
    partial_completed: 'partial_completed',
    failed: '生成失败',
    cancelled: '已取消',
    expired: '已过期',
  }
  return labels[status]
}

function sourceModeForSourceEvidenceRun(run: SourceEvidenceRunResponse): SourceMode {
  if (run.source_type === 'local_file') {
    return 'local'
  }
  if (run.source_type === 'svn_file') {
    return 'svn'
  }
  return 'feishu_doc'
}

function sourceEvidenceTypeLabel(run: SourceEvidenceRunResponse | null = sourceEvidenceRun.value): string {
  if (run?.source_type === 'local_file') {
    return '本地文件'
  }
  if (run?.source_type === 'svn_file') {
    return 'SVN 文件'
  }
  if (run?.source_type === 'feishu') {
    return '飞书文档'
  }
  if (activeSourceMode.value === 'svn') {
    return 'SVN 文件'
  }
  if (activeSourceMode.value === 'feishu_doc') {
    return '飞书文档'
  }
  return '本地文件'
}

function sourceEvidenceEmptyTitle(): string {
  if (activeSourceMode.value === 'svn') {
    return '未读取 SVN 文件'
  }
  if (activeSourceMode.value === 'feishu_doc') {
    return '未读取飞书文档'
  }
  return '未上传本地文件'
}

function sourceEvidenceEmptyAuthorizationDescription(): string {
  if (activeSourceMode.value === 'feishu_doc') {
    return '读取文档后展示授权和资源下载状态。'
  }
  return '创建 Source Evidence Run 后展示读取状态、资源清单和视觉证据状态。'
}

function getDefaultSourceEvidenceSheetName(run: SourceEvidenceRunResponse | null): string {
  const options = run?.sheet_options ?? []
  return options.find((sheet) => sheet.is_default)?.name ?? options[0]?.name ?? ''
}

function applySourceEvidenceRun(run: SourceEvidenceRunResponse): void {
  sourceEvidenceRun.value = run
  selectedPlanningSheetName.value = getDefaultSourceEvidenceSheetName(run)
}

function getSelectedSourceEvidenceSheetName(): string | null {
  if (activeGenerationInput.value.kind !== 'source_evidence' || !hasSourceEvidenceSheetOptions.value) {
    return null
  }
  return selectedPlanningSheetName.value.trim() || null
}

function buildSourceEvidenceSnapshotRequest(): { sheet_name: string } | undefined {
  const sheetName = getSelectedSourceEvidenceSheetName()
  return sheetName ? { sheet_name: sheetName } : undefined
}

function warningNeedsVisualSemanticsNote(message: string): boolean {
  return /(Vision|soffice|转换失败|图片提取失败|下载失败|download_failed|未观察|未采纳|缺少文本主体|无文本主体)/i.test(
    message,
  )
}

function normalizeSourceEvidenceWarningMessage(message: string): string {
  if (!warningNeedsVisualSemanticsNote(message) || message.includes('图片未参与语义理解')) {
    return message
  }
  return `${message} 图片未参与语义理解。`
}

function isTextlessSourceEvidenceWarning(message: string): boolean {
  return /独立图片缺少文本主体|缺少文本主体|无文本主体/.test(message)
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
        .filter((source) => source.type === 'feishu')
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
  const persistedPlanningSheetName =
    activeGenerationInput.value.kind === 'source_evidence' ? null : selectedPlanningSheetName.value.trim() || null
  return {
    planning_sources: planningSourceStore.sources.map((source) => ({ ...source })),
    preferred_planning_source_id: preferredSourceId,
    selected_planning_sheet_name: persistedPlanningSheetName,
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
  inferredSourceMode,
  (mode) => {
    if (!hasUserSelectedSourceMode.value) {
      activeSourceMode.value = mode
    }
  },
  { immediate: true },
)

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
  activeGenerationInputKey,
  (_key, previousKey) => {
    if (previousKey !== undefined) {
      clearSnapshotAndGeneratedResult()
    }
  },
)

watch(
  activeGenerationInputSourceId,
  (sourceId) => {
    if (!sourceId) {
      return
    }
    if (selectedPlanningSourceId.value !== sourceId) {
      selectedPlanningSourceId.value = sourceId
    }
  },
  { immediate: true },
)

watch(
  activePlanningSheetOptions,
  (sheetOptions) => {
    if (isPlanningSourceConfigHydrating.value || isApplyingPlanningSourceConfig) {
      return
    }
    if (activeGenerationInput.value.kind === 'source_evidence') {
      if (!sheetOptions.length) {
        selectedPlanningSheetName.value = ''
        return
      }
      if (!sheetOptions.some((sheet) => sheet.name === selectedPlanningSheetName.value)) {
        selectedPlanningSheetName.value = getDefaultSourceEvidenceSheetName(sourceEvidenceRun.value)
      }
      return
    }
    if (!sheetOptions.length) {
      if (activeGenerationInput.value.kind === 'empty') {
        selectedPlanningSheetName.value = ''
      }
      return
    }
    if (!sheetOptions.some((sheet) => sheet.name === selectedPlanningSheetName.value)) {
      selectedPlanningSheetName.value = sheetOptions[0]?.name ?? ''
    }
  },
  { immediate: true },
)

watch(
  currentSvnPlanningSource,
  (source) => {
    if (!source) {
      return
    }
    const locator = source.pathOrUrl ?? source.url ?? ''
    if (!svnDirectoryUrl.value) {
      svnDirectoryUrl.value = extractSvnDirectoryUrl(locator)
    }
  },
  { immediate: true },
)

watch(
  selectedPlanningSheetOptions,
  (sheetOptions) => {
    if (activeGenerationInput.value.kind === 'source_evidence') {
      return
    }
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

watch([referenceSearchKeyword, referenceSort], () => {
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
  return referenceCategoryCounts.value[categoryId] ?? 0
}

function getReferenceTypeLabel(_type: ReferenceFileType): string {
  return 'Excel'
}

function getReferenceTypeClass(type: ReferenceFileType): string {
  return `is-${type}`
}

function getReferencePriorityLabel(file: ReferenceFile): string {
  if (primaryReference.value?.id === file.id) {
    return '当前主参考'
  }
  if (file.isRecommendedPrimary) {
    return '推荐主参考'
  }
  return '普通参考'
}

function getReferencePriorityTagType(file: ReferenceFile): 'success' | 'primary' | 'info' {
  if (primaryReference.value?.id === file.id) {
    return 'primary'
  }
  if (file.isRecommendedPrimary) {
    return 'success'
  }
  return 'info'
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

function isExcelReferenceSuffix(suffix: string): boolean {
  const normalizedSuffix = suffix.toLowerCase().replace(/^\./, '')
  return normalizedSuffix === 'xlsx' || normalizedSuffix === 'xls'
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
    '来源类型：Excel',
    fields.length ? `字段结构：${fields.slice(0, 6).join(' / ')}` : '字段结构：未识别',
    defaultSheetName ? `默认 Sheet：${defaultSheetName}` : '',
  ]
    .filter(Boolean)
    .join('；')
}

function mapReferenceFileResponse(record: ReferenceFileResponse): ReferenceFile | null {
  if (!isExcelReferenceSuffix(record.suffix)) {
    return null
  }

  const profileWarnings = record.profile?.warnings.map((warning) => warning.message).filter(Boolean) ?? []
  const sheetOptions = record.profile?.sheet_options.map(mapReferenceSheetOption) ?? []

  return {
    id: String(record.id),
    backendId: record.id,
    categoryId:
      typeof record.category_id === 'number' ? String(record.category_id) : REFERENCE_UNCATEGORIZED_CATEGORY_ID,
    categoryNumericId: record.category_id ?? null,
    name: record.original_filename,
    type: 'xlsx',
    tag: record.is_recommended_primary ? '推荐主参考' : undefined,
    summary: record.category_name,
    uploadedBy: '项目成员',
    uploadedAt: record.created_at,
    updatedAt: record.updated_at,
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
      referenceCount: files.filter((file) => file.categoryId === String(category.id)).length,
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
    const files = fileResponse.data.items
      .map(mapReferenceFileResponse)
      .filter((file): file is ReferenceFile => Boolean(file))
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

async function loadSourceEvidenceCapabilities(): Promise<void> {
  try {
    const response = await fetchSourceEvidenceCapabilities()
    sourceEvidenceCapabilityStatus.value = response.data
  } catch {
    sourceEvidenceCapabilityStatus.value = null
  }
}

function markGeneratedResultStale(reason: string): void {
  isGeneratedResultStale.value = true
  generatedResultStaleReason.value = reason
}

function clearSnapshotAndGeneratedResult(): void {
  planningSnapshot.value = null
  sourceEvidenceSnapshotRunId.value = null
  resetSnapshotBriefState()
  clearGeneratedResult()
}

function clearGeneratedResult(): void {
  stopGenerationRunPolling()
  generationResult.value = null
  generationRun.value = null
  generationRunAtoms.value = []
  generationRunCases.value = []
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

function formatLocalSourceTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

function sanitizeLocalSourceIdFromFileName(fileName: string): string {
  const withoutExtension = fileName.replace(/\.[^.]+$/i, '')
  const normalized = withoutExtension
    .replace(/[^A-Za-z0-9_]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '')
  return normalized || 'source'
}

function isLocalSourceEvidenceUploadFile(file: File): boolean {
  return /\.(xlsx|xls|png|jpe?g|webp)$/i.test(file.name)
}

function sanitizeSensitiveDisplay(message: string): string {
  return message
    .replace(/https?:\/\/[^\s，。；;]+/gi, '[已隐藏URL]')
    .replace(/[A-Za-z]:[\\/][^\s，。；;]+/g, '[已隐藏路径]')
    .replace(
      /\b(?:token|access_token|tenant_access_token|user_access_token|app_secret|authorization|open_id|doc_token|wiki_token|file_token)\s*[:=]\s*[^\s，。；;]+/gi,
      '[已隐藏敏感字段]',
    )
    .replace(/\bpassword\s*[:=]\s*[^\s，。；;]+/gi, '[已隐藏敏感字段]')
    .replace(/\bou_[A-Za-z0-9_-]+/g, '[已隐藏open_id]')
    .replace(/\bBearer\s+[A-Za-z0-9._-]+/gi, 'Bearer [已隐藏]')
    .replace(/\bBearer\b/gi, '[已隐藏凭据]')
    .replace(/\bAuthorization\b/gi, '[已隐藏凭据]')
}

function sanitizeLocalSourceErrorSummary(message: string): string {
  return sanitizeSensitiveDisplay(message)
}

function sanitizeSourceEvidenceDisplay(message: string): string {
  return sanitizeSensitiveDisplay(message)
}

function getSafeLocalSourceErrorMessage(error: unknown, fallback: string): string {
  const rawMessage = getApiErrorMessage(error, fallback)
  const safeMessage = sanitizeLocalSourceErrorSummary(rawMessage).trim()
  if (!safeMessage || safeMessage === fallback) {
    return fallback
  }
  return `${fallback} ${safeMessage}`
}

function triggerLocalSourceUpload(): void {
  if (isLocalSourceUploading.value) {
    return
  }
  localUploadInputRef.value?.click()
}

async function uploadLocalSourceFile(file: File | null | undefined): Promise<void> {
  if (!file || isLocalSourceUploading.value) {
    return
  }
  if (!isLocalSourceEvidenceUploadFile(file)) {
    localSourceUploadErrorMessage.value = '请选择 .xlsx / .xls / .png / .jpg / .jpeg / .webp 文件。'
    return
  }

  isLocalSourceUploading.value = true
  localSourceUploadErrorMessage.value = ''
  try {
    const response = await createLocalFileSourceEvidenceRun(file)
    applySourceEvidenceRun(response.data)
    sourceEvidenceRunUrl.value = ''
    localSourceUploadMeta.value = {
      sourceId: `source-evidence-run-${response.data.id}`,
      fileName: file.name,
      size: file.size,
      uploadedAt: new Date().toISOString(),
      lastReadAt: null,
    }
    resetSourceEvidenceAuthorizationState()
    resetSourceEvidenceVisualCandidates()
    sourceEvidenceResourcesErrorMessage.value = ''
    sourceEvidenceResourcesDrawerVisible.value = false
    activeSourceMode.value = 'local'
    clearSnapshotAndGeneratedResult()
    await refreshSourceEvidenceResourcesForAuthorization(response.data.id)
    ElMessage.success('本地文件已创建 Source Evidence Run。')
  } catch (error) {
    localSourceUploadErrorMessage.value = getSafeLocalSourceErrorMessage(error, '上传文件失败，请稍后重试。')
    ElMessage.error(localSourceUploadErrorMessage.value)
  } finally {
    isLocalSourceUploading.value = false
    isLocalSourceDragActive.value = false
  }
}

async function handleLocalSourceInputChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  input.value = ''
  await uploadLocalSourceFile(file)
}

function handleLocalSourceDragEnter(): void {
  if (!isLocalSourceUploading.value) {
    isLocalSourceDragActive.value = true
  }
}

function handleLocalSourceDragLeave(): void {
  isLocalSourceDragActive.value = false
}

async function handleLocalSourceDrop(event: Event): Promise<void> {
  isLocalSourceDragActive.value = false
  const dragEvent = event as Event & {
    dataTransfer?: {
      files?: {
        [index: number]: File | undefined
      }
    }
  }
  await uploadLocalSourceFile(dragEvent.dataTransfer?.files?.[0] ?? null)
}

async function refreshCurrentLocalSourceSheets(): Promise<void> {
  const run = sourceEvidenceRun.value
  if (!isLocalSourceEvidenceRun.value || !run || isLocalSourceRefreshing.value) {
    return
  }

  isLocalSourceRefreshing.value = true
  localSourceUploadErrorMessage.value = ''
  try {
    const response = await retrySourceEvidenceRun(run.id)
    applySourceEvidenceRun(response.data)
    resetSourceEvidenceAuthorizationState()
    resetSourceEvidenceVisualCandidates()
    sourceEvidenceResourcesErrorMessage.value = ''
    clearSnapshotAndGeneratedResult()
    await refreshSourceEvidenceResourcesForAuthorization(response.data.id)
    ElMessage.success('已重试读取本地文件。')
  } catch (error) {
    localSourceUploadErrorMessage.value = getSafeLocalSourceErrorMessage(error, '重试读取本地文件失败，请稍后重试。')
    ElMessage.error(localSourceUploadErrorMessage.value)
  } finally {
    isLocalSourceRefreshing.value = false
  }
}

function clearCurrentLocalSource(): void {
  if (!isLocalSourceEvidenceRun.value) {
    return
  }
  localSourceUploadErrorMessage.value = ''
  localSourceUploadMeta.value = null
  resetSourceEvidenceRunState()
}

function updateLocalSourceLastReadAt(sourceId: string): void {
  const existing =
    localSourceUploadMeta.value?.sourceId === sourceId
      ? localSourceUploadMeta.value
      : {
          sourceId,
          fileName: '已上传 Excel',
          size: null,
          uploadedAt: null,
          lastReadAt: null,
        }
  localSourceUploadMeta.value = {
    ...existing,
    lastReadAt: new Date().toISOString(),
  }
}

function isSvnExcelEntry(entry: SvnEntry): boolean {
  return entry.kind === 'file' && /\.xlsx?$/i.test(entry.name)
}

function extractSvnFileName(locator: string): string {
  const trimmed = locator.trim()
  if (!trimmed) {
    return ''
  }
  const withoutQuery = trimmed.split(/[?#]/)[0] ?? trimmed
  const lastSlash = withoutQuery.lastIndexOf('/')
  return lastSlash >= 0 ? withoutQuery.slice(lastSlash + 1) : withoutQuery
}

function extractSvnDirectoryUrl(locator: string): string {
  const trimmed = locator.trim()
  if (!trimmed) {
    return ''
  }
  const withoutQuery = trimmed.split(/[?#]/)[0] ?? trimmed
  const lastSlash = withoutQuery.lastIndexOf('/')
  return lastSlash >= 0 ? ensureTrailingSlash(withoutQuery.slice(0, lastSlash)) : ''
}

function formatSvnSize(size: number | null): string {
  if (size === null || size === undefined) {
    return '大小未记录'
  }
  if (size < 1024) {
    return `${size} B`
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function formatSvnEntryTime(value: string): string {
  if (!value) {
    return '未记录'
  }
  try {
    return formatLocalSourceTime(value)
  } catch {
    return value
  }
}

function maskSvnUsername(username: string): string {
  const trimmed = username.trim()
  if (!trimmed) {
    return '未配置'
  }
  if (trimmed.length <= 2) {
    return `${trimmed[0] ?? '*'}*`
  }
  return `${trimmed[0]}${'*'.repeat(Math.min(6, Math.max(2, trimmed.length - 2)))}${trimmed.at(-1)}`
}

function getSafeSvnErrorMessage(error: unknown, fallback: string): string {
  const message = error instanceof Error && error.message ? error.message : fallback
  return sanitizeLocalSourceErrorSummary(message).trim() || fallback
}

function createUniqueSvnSourceId(fileName: string): string {
  const baseId = sanitizeLocalSourceIdFromFileName(fileName)
  const existingIds = new Set(
    planningSourceStore.sources.filter((source) => source.type !== 'svn').map((source) => source.id),
  )
  if (!existingIds.has(baseId)) {
    return baseId
  }

  let suffix = 2
  let candidate = `${baseId}_${suffix}`
  while (existingIds.has(candidate)) {
    suffix += 1
    candidate = `${baseId}_${suffix}`
  }
  return candidate
}

async function refreshSvnCredentialItemsForPage(): Promise<void> {
  svnCredentialLoadState.value = 'loading'
  try {
    const response = await listSvnCredentialHosts()
    svnCredentialItems.value = response.data.items
    svnCredentialLoadState.value = 'ready'
  } catch {
    svnCredentialItems.value = []
    svnCredentialLoadState.value = 'error'
  }
}

async function browseSvnDirectory(dirUrl: string, options?: { resetBase?: boolean }): Promise<void> {
  if (!isHttpDirUrl(dirUrl)) {
    svnDirectoryErrorMessage.value = '请输入有效的 http(s):// SVN 目录 URL。'
    svnDirectoryEntries.value = []
    return
  }

  const normalized = ensureTrailingSlash(dirUrl)
  if (options?.resetBase) {
    svnBaseDirectoryUrl.value = normalized
  }
  svnDirectoryUrl.value = normalized
  svnCurrentDirectoryUrl.value = normalized
  isSvnDirectoryLoading.value = true
  svnDirectoryErrorMessage.value = ''

  try {
    const response = await listSvnDirectory(normalized)
    svnDirectoryEntries.value = response.data.entries
    svnCredentialAttention.value = false
    if (response.data.credential_username && !currentSvnCredentialItem.value) {
      svnCredentialItems.value = [
        ...svnCredentialItems.value,
        {
          host: response.data.host,
          username: response.data.credential_username,
          updated_at: '',
          test_dir_url: normalized,
        },
      ]
    }
  } catch (error) {
    svnDirectoryEntries.value = []
    svnDirectoryErrorMessage.value = getSafeSvnErrorMessage(error, '加载 SVN 目录失败。')
    if (error instanceof SvnApiError && error.category === 'auth_failed') {
      svnCredentialAttention.value = true
      svnConnectionTestResult.value = {
        status: 'failed',
        message: '需要配置凭据',
        testedAt: new Date().toISOString(),
      }
    }
  } finally {
    isSvnDirectoryLoading.value = false
  }
}

async function enterSvnDirectory(entry: SvnEntry): Promise<void> {
  if (entry.kind !== 'dir' || !canEnterSvnSubdirectory.value) {
    return
  }
  await browseSvnDirectory(ensureTrailingSlash(`${svnCurrentDirectoryUrl.value}${entry.name}`))
}

function applyCurrentSvnSource(source: DataSource, metadata?: SourceMetadata): void {
  const svnSourceIds = new Set(planningSourceStore.sources.filter((item) => item.type === 'svn').map((item) => item.id))
  planningSourceStore.sources = [source, ...planningSourceStore.sources.filter((item) => item.type !== 'svn')]
  if (planningSourceStore.sourceMetadataMap) {
    svnSourceIds.forEach((sourceId) => {
      delete planningSourceStore.sourceMetadataMap?.[sourceId]
    })
    if (metadata) {
      planningSourceStore.sourceMetadataMap[source.id] = metadata
    } else {
      planningSourceStore.sourceMetadataMap[source.id] = {
        source_id: source.id,
        source_type: 'svn',
        sheets: [],
      }
    }
  }
  planningSourceStore.preferredSourceId = source.id
  selectedPlanningSourceId.value = source.id
  selectedPlanningSheetName.value = metadata?.sheets[0]?.name ?? ''
  clearSnapshotAndGeneratedResult()
  queuePlanningSourceConfigPersist()
}

function selectSvnExcelFile(entry: SvnEntry): void {
  if (!isSvnExcelEntry(entry) || !svnCurrentDirectoryUrl.value) {
    return
  }
  const fileUrl = `${svnCurrentDirectoryUrl.value}${entry.name}`
  const source: DataSource = {
    id: createUniqueSvnSourceId(entry.name),
    type: 'svn',
    pathOrUrl: fileUrl,
  }
  svnSelectedFileMeta.value = {
    sourceId: source.id,
    fileName: entry.name,
    size: entry.size,
    revision: entry.revision,
    lastModifiedAt: entry.last_modified_at,
  }
  applyCurrentSvnSource(source)
}

async function readCurrentSvnData(): Promise<void> {
  const sourceUrl = svnFileUrl.value.trim()
  if (!sourceUrl || isSvnReadingData.value) {
    return
  }
  if (!areSvnSourceEvidenceCapabilitiesAvailable.value) {
    svnDirectoryErrorMessage.value =
      sourceEvidenceSvnCapabilityMessage.value || 'SVN 文件 Source Evidence 不可用，请联系项目管理员。'
    return
  }
  isSvnReadingData.value = true
  svnDirectoryErrorMessage.value = ''
  try {
    const response = await createSourceEvidenceRun({
      source_type: 'svn_file',
      source_url: sourceUrl,
    })
    applySourceEvidenceRun(response.data)
    sourceEvidenceRunUrl.value = sourceUrl
    activeSourceMode.value = 'feishu_doc'
    resetSourceEvidenceAuthorizationState()
    resetSourceEvidenceVisualCandidates()
    sourceEvidenceResourcesErrorMessage.value = ''
    sourceEvidenceResourcesDrawerVisible.value = false
    activeSourceMode.value = 'svn'
    clearSnapshotAndGeneratedResult()
    await refreshSourceEvidenceResourcesForAuthorization(response.data.id)
    ElMessage.success('SVN 文件已创建 Source Evidence Run。')
  } catch (error) {
    svnDirectoryErrorMessage.value = getSafeSvnErrorMessage(error, '读取 SVN 文件来源失败。')
    ElMessage.error(svnDirectoryErrorMessage.value)
  } finally {
    isSvnReadingData.value = false
  }
}

async function openSvnCredentialDialogForCurrentHost(): Promise<void> {
  const host = svnCurrentHost.value
  if (!host) {
    svnDirectoryErrorMessage.value = '请先输入 SVN 目录 URL。'
    return
  }
  const matchedCredential = currentSvnCredentialItem.value
  const fallbackTestDirUrl =
    matchedCredential?.test_dir_url?.trim() ||
    svnBaseDirectoryUrl.value ||
    ensureTrailingSlash(svnDirectoryUrl.value) ||
    getDefaultSvnCredentialTestDirUrl(host)

  svnCredentialDialogHost.value = host
  svnCredentialDialogDefaultUsername.value = matchedCredential?.username ?? ''
  svnCredentialDialogDefaultPassword.value = ''
  svnCredentialDialogDefaultTestDirUrl.value = fallbackTestDirUrl

  try {
    const response = await fetchSvnCredential(host)
    if (response?.data) {
      svnCredentialDialogDefaultUsername.value = response.data.username
      svnCredentialDialogDefaultPassword.value = response.data.password
      svnCredentialDialogDefaultTestDirUrl.value = response.data.test_dir_url?.trim() || fallbackTestDirUrl
    }
  } catch (error) {
    ElMessage.warning(getSafeSvnErrorMessage(error, '读取已保存的 SVN 凭据失败，已回退到默认值。'))
  }

  svnCredentialDialogVisible.value = true
}

async function handleSvnCredentialSaved(host: string): Promise<void> {
  await refreshSvnCredentialItemsForPage()
  svnCredentialAttention.value = false
  if (host === svnCurrentHost.value && isHttpDirUrl(svnDirectoryUrl.value)) {
    await browseSvnDirectory(svnDirectoryUrl.value, { resetBase: !svnBaseDirectoryUrl.value })
  }
}

async function testCurrentSvnConnection(): Promise<void> {
  const dirUrl =
    svnDirectoryUrl.value.trim() ||
    currentSvnCredentialItem.value?.test_dir_url?.trim() ||
    getDefaultSvnCredentialTestDirUrl(svnCurrentHost.value)
  if (!dirUrl || !isHttpDirUrl(dirUrl) || isSvnTestingConnection.value) {
    return
  }

  isSvnTestingConnection.value = true
  svnDirectoryErrorMessage.value = ''
  try {
    await listSvnDirectory(ensureTrailingSlash(dirUrl))
    svnCredentialAttention.value = false
    svnConnectionTestResult.value = {
      status: 'success',
      message: '连接正常',
      testedAt: new Date().toISOString(),
    }
    ElMessage.success('SVN 连接正常。')
  } catch (error) {
    const message = getSafeSvnErrorMessage(error, '测试连接失败。')
    svnConnectionTestResult.value = {
      status: 'failed',
      message,
      testedAt: new Date().toISOString(),
    }
    if (error instanceof SvnApiError && error.category === 'auth_failed') {
      svnCredentialAttention.value = true
    }
    ElMessage.error(message)
  } finally {
    isSvnTestingConnection.value = false
  }
}

function formatSourceEvidenceDate(value?: string | null): string {
  if (!value) {
    return '未记录'
  }
  return value.slice(0, 10)
}

function resetSourceEvidenceRunState(reason = ''): void {
  sourceEvidenceRun.value = null
  sourceEvidenceRunUrl.value = ''
  resetSourceEvidenceAuthorizationState()
  resetSourceEvidenceVisualCandidates()
  sourceEvidenceResourcesErrorMessage.value = ''
  sourceEvidenceResourcesDrawerVisible.value = false
  if (reason) {
    sourceEvidenceApiErrorMessage.value = reason
  }
  clearSnapshotAndGeneratedResult()
}

function resetSourceEvidenceAuthorizationState(): void {
  sourceEvidenceAuthorizationResult.value = null
  sourceEvidenceAuthorizationErrorMessage.value = ''
}

function resetSourceEvidenceVisualCandidates(): void {
  sourceEvidenceResources.value = []
  sourceEvidenceVisualCandidates.value = []
  sourceEvidenceRecommendedVisualRefs.value = []
  sourceEvidenceSelectedVisualRefs.value = []
  sourceEvidenceObservations.value = []
  sourceEvidenceAdoptionSavingIds.value = []
}

function applySourceEvidenceResources(payload: { items: SourceEvidenceResourceResponse[] }): void {
  sourceEvidenceResources.value = payload.items.map((item) => ({ ...item }))
}

function applySourceEvidenceVisualCandidates(payload: {
  items: SourceEvidenceVisualCandidateResponse[]
  recommended_refs: string[]
  selected_refs: string[]
}): void {
  sourceEvidenceVisualCandidates.value = payload.items.map((candidate) => ({
    ...candidate,
    selected: payload.selected_refs.includes(candidate.ref),
  }))
  sourceEvidenceRecommendedVisualRefs.value = [...payload.recommended_refs]
  sourceEvidenceSelectedVisualRefs.value = [...payload.selected_refs]
}

function applySourceEvidenceObservations(payload: {
  items: SourceEvidenceObservationResponse[]
}): void {
  sourceEvidenceObservations.value = payload.items.map((item) => ({ ...item }))
}

function applySourceEvidenceAuthorizationResult(result: SourceEvidenceAuthorizationRequestResponse): void {
  sourceEvidenceAuthorizationResult.value = { ...result }
  sourceEvidenceAuthorizationErrorMessage.value = ''
}

function extractSourceEvidenceAuthorizationResult(error: unknown): SourceEvidenceAuthorizationRequestResponse | null {
  if (!isRecord(error) || !isRecord(error.payload)) {
    return null
  }
  const data = error.payload.data
  if (!isRecord(data) || typeof data.status !== 'string') {
    return null
  }
  return data as unknown as SourceEvidenceAuthorizationRequestResponse
}

async function refreshSourceEvidenceResourcesForAuthorization(runId: number): Promise<void> {
  try {
    const response = await fetchSourceEvidenceResources(runId)
    applySourceEvidenceResources(response.data)
  } catch (error) {
    sourceEvidenceAuthorizationErrorMessage.value = getApiErrorMessage(
      error,
      '资源状态暂不可用，可打开资源清单重试。',
    )
  }
}

function handleSourceEvidenceUrlInput(): void {
  if (!sourceEvidenceRun.value) {
    sourceEvidenceApiErrorMessage.value = ''
    return
  }
  if (sourceEvidenceUrl.value.trim() !== sourceEvidenceRunUrl.value) {
    resetSourceEvidenceRunState('飞书文档 URL 已变更，请重新读取来源。')
  }
}

async function createFeishuSourceEvidenceRun(): Promise<void> {
  const sourceUrl = sourceEvidenceUrl.value.trim()
  if (!sourceUrl) {
    sourceEvidenceApiErrorMessage.value = '请输入飞书文档 URL。'
    return
  }

  isSourceEvidenceCreating.value = true
  sourceEvidenceApiErrorMessage.value = ''
  try {
    const response = await createSourceEvidenceRun({
      source_type: 'feishu',
      source_url: sourceUrl,
    })
    applySourceEvidenceRun(response.data)
    sourceEvidenceRunUrl.value = sourceUrl
    resetSourceEvidenceAuthorizationState()
    resetSourceEvidenceVisualCandidates()
    sourceEvidenceResourcesErrorMessage.value = ''
    sourceEvidenceResourcesDrawerVisible.value = false
    clearSnapshotAndGeneratedResult()
    await refreshSourceEvidenceResourcesForAuthorization(response.data.id)
  } catch (error) {
    sourceEvidenceApiErrorMessage.value = getApiErrorMessage(error, '读取飞书文档来源失败，请稍后重试。')
  } finally {
    isSourceEvidenceCreating.value = false
  }
}

async function retryFeishuSourceEvidenceRun(): Promise<void> {
  const run = sourceEvidenceRun.value
  if (!run) {
    return
  }

  isSourceEvidenceRetrying.value = true
  sourceEvidenceApiErrorMessage.value = ''
  try {
    const response = await retrySourceEvidenceRun(run.id)
    applySourceEvidenceRun(response.data)
    resetSourceEvidenceAuthorizationState()
    resetSourceEvidenceVisualCandidates()
    sourceEvidenceResourcesErrorMessage.value = ''
    clearSnapshotAndGeneratedResult()
    await refreshSourceEvidenceResourcesForAuthorization(response.data.id)
  } catch (error) {
    sourceEvidenceApiErrorMessage.value = getApiErrorMessage(error, '重试读取来源失败，请稍后重试。')
  } finally {
    isSourceEvidenceRetrying.value = false
  }
}

async function requestFeishuSourceEvidenceAuthorization(): Promise<void> {
  const run = sourceEvidenceRun.value
  if (!run || !canRequestSourceEvidenceAuthorization.value) {
    return
  }

  isSourceEvidenceAuthorizationRequesting.value = true
  sourceEvidenceAuthorizationErrorMessage.value = ''
  try {
    const response = await requestSourceEvidenceAuthorization(run.id)
    applySourceEvidenceAuthorizationResult(response.data)
  } catch (error) {
    const authorizationResult = extractSourceEvidenceAuthorizationResult(error)
    if (authorizationResult) {
      applySourceEvidenceAuthorizationResult(authorizationResult)
      return
    }
    sourceEvidenceAuthorizationErrorMessage.value = getApiErrorMessage(
      error,
      '申请授权失败，请稍后重试。',
    )
  } finally {
    isSourceEvidenceAuthorizationRequesting.value = false
  }
}

async function openSourceEvidenceResources(): Promise<void> {
  const run = sourceEvidenceRun.value
  if (!run) {
    return
  }

  sourceEvidenceResourcesDrawerVisible.value = true
  isSourceEvidenceResourcesLoading.value = true
  sourceEvidenceResourcesErrorMessage.value = ''
  try {
    const sheetName = getSelectedSourceEvidenceSheetName()
    const [resourceResponse, candidateResponse, observationResponse] = await Promise.all([
      fetchSourceEvidenceResources(run.id),
      sheetName ? fetchSourceEvidenceVisualCandidates(run.id, sheetName) : fetchSourceEvidenceVisualCandidates(run.id),
      fetchSourceEvidenceObservations(run.id),
    ])
    applySourceEvidenceResources(resourceResponse.data)
    applySourceEvidenceVisualCandidates(candidateResponse.data)
    applySourceEvidenceObservations(observationResponse.data)
  } catch (error) {
    sourceEvidenceResourcesErrorMessage.value = getApiErrorMessage(error, '读取视觉候选失败，请稍后重试。')
  } finally {
    isSourceEvidenceResourcesLoading.value = false
  }
}

async function refreshSourceEvidenceVisualCandidatesForCurrentSheet(): Promise<void> {
  const run = sourceEvidenceRun.value
  if (!run || activeGenerationInput.value.kind !== 'source_evidence' || isSourceEvidenceBlocked.value) {
    return
  }
  if (hasSourceEvidenceSheetOptions.value && !getSelectedSourceEvidenceSheetName()) {
    return
  }

  isSourceEvidenceResourcesLoading.value = sourceEvidenceResourcesDrawerVisible.value
  sourceEvidenceResourcesErrorMessage.value = ''
  try {
    const sheetName = getSelectedSourceEvidenceSheetName()
    const response = sheetName
      ? await fetchSourceEvidenceVisualCandidates(run.id, sheetName)
      : await fetchSourceEvidenceVisualCandidates(run.id)
    applySourceEvidenceVisualCandidates(response.data)
  } catch (error) {
    sourceEvidenceResourcesErrorMessage.value = getApiErrorMessage(error, '读取视觉候选失败，请稍后重试。')
  } finally {
    isSourceEvidenceResourcesLoading.value = false
  }
}

function handleSourceEvidenceVisualSelectionChange(
  candidate: SourceEvidenceVisualCandidateResponse,
  event: Event,
): void {
  if (!candidate.selectable) {
    return
  }
  const checked = event.target instanceof HTMLInputElement ? event.target.checked : false
  const selected = new Set(sourceEvidenceSelectedVisualRefs.value)
  if (checked) {
    selected.add(candidate.ref)
  } else {
    selected.delete(candidate.ref)
  }
  sourceEvidenceSelectedVisualRefs.value = [...selected]
  sourceEvidenceVisualCandidates.value = sourceEvidenceVisualCandidates.value.map((item) =>
    item.ref === candidate.ref ? { ...item, selected: checked } : item,
  )
}

async function saveSourceEvidenceVisualSelection(): Promise<void> {
  const run = sourceEvidenceRun.value
  if (!run || isSourceEvidenceBlocked.value) {
    return
  }

  isSourceEvidenceVisualSaving.value = true
  sourceEvidenceResourcesErrorMessage.value = ''
  try {
    const sheetName = getSelectedSourceEvidenceSheetName()
    const response = await saveSourceEvidenceVisualSelections(run.id, {
      selected_refs: sourceEvidenceSelectedVisualRefs.value,
      ...(sheetName ? { sheet_name: sheetName } : {}),
    })
    applySourceEvidenceVisualCandidates(response.data)
    if (hasGeneratedResult.value) {
      markGeneratedResultStale('视觉观察选择已变化，需要重新生成。')
    }
  } catch (error) {
    sourceEvidenceResourcesErrorMessage.value = getApiErrorMessage(error, '保存视觉观察选择失败，请稍后重试。')
  } finally {
    isSourceEvidenceVisualSaving.value = false
  }
}

async function observeSelectedSourceEvidenceVisuals(): Promise<void> {
  const run = sourceEvidenceRun.value
  if (!run || isSourceEvidenceBlocked.value) {
    return
  }
  if (!isVisionAiCapabilityAvailable.value) {
    sourceEvidenceResourcesErrorMessage.value =
      sourceEvidenceVisionCapabilityMessage.value || '当前未配置视觉模型，图片不会参与语义理解。'
    return
  }

  isSourceEvidenceObserving.value = true
  sourceEvidenceResourcesErrorMessage.value = ''
  try {
    const sheetName = getSelectedSourceEvidenceSheetName()
    const selectionResponse = await saveSourceEvidenceVisualSelections(run.id, {
      selected_refs: sourceEvidenceSelectedVisualRefs.value,
      ...(sheetName ? { sheet_name: sheetName } : {}),
    })
    applySourceEvidenceVisualCandidates(selectionResponse.data)
    const observationResponse = await observeSourceEvidenceRun(run.id)
    applySourceEvidenceObservations(observationResponse.data)
  } catch (error) {
    sourceEvidenceResourcesErrorMessage.value = getApiErrorMessage(
      error,
      'Vision 未配置或观察失败，文本/表格仍可继续生成。',
    )
  } finally {
    isSourceEvidenceObserving.value = false
  }
}

async function adoptSourceEvidenceObservation(observation: SourceEvidenceObservationResponse): Promise<void> {
  const run = sourceEvidenceRun.value
  if (!run || isSourceEvidenceBlocked.value || observation.status === 'adopted') {
    return
  }

  sourceEvidenceAdoptionSavingIds.value = [...sourceEvidenceAdoptionSavingIds.value, observation.id]
  sourceEvidenceResourcesErrorMessage.value = ''
  try {
    const response = await adoptSourceEvidenceVisualEvidence(run.id, {
      observation_ids: [observation.id],
    })
    applySourceEvidenceObservations(response.data)
    if (hasGeneratedResult.value) {
      markGeneratedResultStale('已采纳视觉证据已变化，需要重新生成。')
    }
  } catch (error) {
    sourceEvidenceResourcesErrorMessage.value = getApiErrorMessage(error, '采纳视觉证据失败，请稍后重试。')
  } finally {
    sourceEvidenceAdoptionSavingIds.value = sourceEvidenceAdoptionSavingIds.value.filter((id) => id !== observation.id)
  }
}

async function revokeSourceEvidenceObservation(observation: SourceEvidenceObservationResponse): Promise<void> {
  const run = sourceEvidenceRun.value
  if (!run || isSourceEvidenceBlocked.value || observation.status !== 'adopted') {
    return
  }

  sourceEvidenceAdoptionSavingIds.value = [...sourceEvidenceAdoptionSavingIds.value, observation.id]
  sourceEvidenceResourcesErrorMessage.value = ''
  try {
    const response = await revokeSourceEvidenceVisualEvidence(run.id, observation.id)
    applySourceEvidenceObservations(response.data)
    if (hasGeneratedResult.value) {
      markGeneratedResultStale('已采纳视觉证据已变化，需要重新生成。')
    }
  } catch (error) {
    sourceEvidenceResourcesErrorMessage.value = getApiErrorMessage(error, '撤销采纳失败，请稍后重试。')
  } finally {
    sourceEvidenceAdoptionSavingIds.value = sourceEvidenceAdoptionSavingIds.value.filter((id) => id !== observation.id)
  }
}

function isObservationSaving(observationId: number): boolean {
  return sourceEvidenceAdoptionSavingIds.value.includes(observationId)
}

function getVisualCandidateStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    ready: '可观察',
    missing: '本地文件缺失',
    pending_permission: '权限不足',
    download_failed: '下载失败',
    unsupported_attachment: '非图片附件',
    invalid_image: '图片不可解析',
    pending: '待下载',
  }
  return labels[status] ?? status
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
  if (!canReadSnapshot.value) {
    return
  }

  isSnapshotLoading.value = true
  apiErrorMessage.value = ''
  try {
    let response
    let localSnapshotSourceId = ''
    const input = activeGenerationInput.value
    if (input.kind === 'source_evidence') {
      const run = input.run
      if (!run) {
        return
      }
      const snapshotRequest = buildSourceEvidenceSnapshotRequest()
      response = snapshotRequest
        ? await readSourceEvidenceSnapshot(run.id, snapshotRequest)
        : await readSourceEvidenceSnapshot(run.id)
      sourceEvidenceSnapshotRunId.value = run.id
      if (run.source_type === 'local_file' && localSourceUploadMeta.value) {
        localSourceUploadMeta.value = {
          ...localSourceUploadMeta.value,
          lastReadAt: new Date().toISOString(),
        }
      }
    } else {
      const source = input.source
      if (!source || !selectedPlanningSheetName.value) {
        return
      }
      response = await readPlanningSnapshot({
        source_type: input.kind === 'legacy_feishu' || source.type === 'feishu' ? 'feishu' : 'uploaded_excel',
        source,
        sheet_name: selectedPlanningSheetName.value,
      })
      if (input.kind === 'local_excel') {
        localSnapshotSourceId = source.id
      }
      sourceEvidenceSnapshotRunId.value = null
    }
    planningSnapshot.value = response.data
    if (localSnapshotSourceId) {
      updateLocalSourceLastReadAt(localSnapshotSourceId)
    }
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

function getStoredGenerationRunId(): number | null {
  try {
    const rawValue = window.localStorage.getItem(GENERATION_RUN_STORAGE_KEY)
    const runId = rawValue ? Number(rawValue) : NaN
    return Number.isFinite(runId) && runId > 0 ? runId : null
  } catch {
    return null
  }
}

function storeGenerationRunId(runId: number): void {
  try {
    window.localStorage.setItem(GENERATION_RUN_STORAGE_KEY, String(runId))
  } catch {
    // localStorage can be unavailable in hardened browser contexts.
  }
}

function removeStoredGenerationRunId(runId?: number): void {
  try {
    if (runId === undefined || window.localStorage.getItem(GENERATION_RUN_STORAGE_KEY) === String(runId)) {
      window.localStorage.removeItem(GENERATION_RUN_STORAGE_KEY)
    }
  } catch {
    // localStorage can be unavailable in hardened browser contexts.
  }
}

function applyGenerationRun(run: TestCaseGenerationRunResponse, options: { persist?: boolean } = {}): void {
  generationRun.value = run
  generationRunArtifacts.value = run.artifacts ?? []
  if (!generationRunArtifacts.value.some((item) => item.key === selectedArtifactKey.value)) {
    selectedArtifactKey.value = generationRunArtifacts.value[0]?.key ?? 'workbook'
  }
  generationResult.value = null
  isGeneratedResultStale.value = false
  generatedResultStaleReason.value = ''
  if (options.persist !== false) {
    storeGenerationRunId(run.id)
  }
  if (run.status === 'expired') {
    removeStoredGenerationRunId(run.id)
  }
}

function stopGenerationRunPolling(): void {
  if (generationRunPollTimer !== null) {
    window.clearTimeout(generationRunPollTimer)
    generationRunPollTimer = null
  }
  isGenerationRunPolling.value = false
}

function scheduleGenerationRunPolling(runId: number): void {
  stopGenerationRunPolling()
  isGenerationRunPolling.value = true
  generationRunPollTimer = window.setTimeout(() => {
    generationRunPollTimer = null
    void refreshGenerationRun(runId, { scheduleNext: true })
  }, 2000)
}

async function loadGenerationRunResultDetails(runId: number): Promise<void> {
  try {
    const [casesResponse, atomsResponse] = await Promise.all([
      listGenerationRunCases(runId),
      listGenerationRunAtoms(runId),
    ])
    generationRunCases.value = casesResponse.data.items
    generationRunAtoms.value = atomsResponse.data.items
    try {
      const artifactsResponse = await listGenerationRunArtifacts(runId)
      generationRunArtifacts.value = artifactsResponse.data.items
      if (!generationRunArtifacts.value.some((item) => item.key === selectedArtifactKey.value)) {
        selectedArtifactKey.value = generationRunArtifacts.value[0]?.key ?? 'workbook'
      }
    } catch {
      generationRunArtifacts.value = generationRun.value?.artifacts ?? []
    }
  } catch (error) {
    const message = getApiErrorMessage(error, '')
    if (message) {
      apiErrorMessage.value = message
    }
    generationRunCases.value = []
    generationRunAtoms.value = []
    generationRunArtifacts.value = []
  }
}

async function refreshGenerationRun(runId: number, options: { scheduleNext?: boolean } = {}): Promise<void> {
  try {
    const response = await getGenerationRun(runId)
    const run = response.data
    applyGenerationRun(run)
    if (GENERATION_RUN_RESULT_STATUSES.has(run.status)) {
      stopGenerationRunPolling()
      await loadGenerationRunResultDetails(run.id)
      return
    }
    if (GENERATION_RUN_ACTIVE_STATUSES.has(run.status)) {
      if (options.scheduleNext !== false) {
        scheduleGenerationRunPolling(run.id)
      }
      return
    }
    stopGenerationRunPolling()
    if (run.status === 'cancelled' || run.status === 'expired') {
      generationRunCases.value = []
      generationRunAtoms.value = []
    }
  } catch (error) {
    stopGenerationRunPolling()
    const message = getApiErrorMessage(error, '恢复 Generation Run 失败。')
    apiErrorMessage.value = message
    removeStoredGenerationRunId(runId)
  }
}

async function restoreLatestGenerationRun(): Promise<void> {
  const runId = getStoredGenerationRunId()
  if (!runId) {
    return
  }
  await refreshGenerationRun(runId, { scheduleNext: true })
}

async function generateCases(): Promise<void> {
  const run = sourceEvidenceRun.value
  const planningSheetName = selectedGenerationSheetName.value
  if (!run || !planningSheetName) {
    apiErrorMessage.value = 'V3 全量生成需要先读取 Source Evidence 并选择 Planning Sheet。'
    return
  }

  isGeneratingCases.value = true
  apiErrorMessage.value = ''
  stopGenerationRunPolling()
  generationRunAtoms.value = []
  generationRunCases.value = []
  generationRunArtifacts.value = []
  artifactPreviewText.value = ''
  try {
    const selectedReferenceBackendIds = selectedReferenceFiles.value.map((file) => file.backendId)
    const primaryReferenceBackendId = primaryReference.value?.backendId ?? null
    const primaryReferenceSheetName =
      primaryReference.value && hasReferenceSheetOptions.value ? selectedReferenceSheetName.value || null : null
    const response = await createGenerationRun({
      source_evidence_run_id: run.id,
      planning_sheet_name: planningSheetName,
      reference_ids: selectedReferenceBackendIds,
      primary_reference_id: primaryReferenceBackendId,
      primary_reference_sheet_name: primaryReferenceSheetName,
      strict_mode: strictMode.value,
    })
    applyGenerationRun(response.data)
    isGeneratedResultStale.value = false
    generatedResultStaleReason.value = ''
    snapshotBriefParticipatedInLastGeneration.value = false
    activeTab.value = 'cases'
    await refreshGenerationRun(response.data.id, { scheduleNext: true })
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
  const run = generationRun.value
  const selectedArtifact = selectedGenerationArtifact.value ?? workbookGenerationArtifact.value
  if (!run || (!selectedArtifact && !canExportGeneratedResult.value)) {
    return
  }

  isExportingCases.value = true
  apiErrorMessage.value = ''
  try {
    if (selectedArtifact && selectedArtifact.status !== 'ready') {
      apiErrorMessage.value = selectedArtifact.message || '所选文件当前不可下载，请重试文件渲染。'
      return
    }
    const file = selectedArtifact
      ? await downloadGenerationRunArtifact(run.id, selectedArtifact.key, selectedArtifact.file_name)
      : await exportGenerationRunWorkbook(run.id)
    saveDownloadedFile(file)
  } catch (error) {
    apiErrorMessage.value = getApiErrorMessage(error, '导出 Excel 失败，请稍后重试。')
  } finally {
    isExportingCases.value = false
  }
}

async function previewGenerationArtifact(artifactKey: string): Promise<void> {
  selectedArtifactKey.value = artifactKey
  const run = generationRun.value
  const artifact = generationRunArtifacts.value.find((item) => item.key === artifactKey)
  artifactPreviewText.value = ''
  if (!run || !artifact) {
    return
  }
  if (artifact.preview_kind === 'cases') {
    activeTab.value = 'cases'
    return
  }
  activeTab.value = 'artifact'
  if (artifact.status !== 'ready') {
    artifactPreviewText.value = artifact.message || '文件当前不可预览。'
    return
  }
  isArtifactPreviewLoading.value = true
  try {
    artifactPreviewText.value = await fetchGenerationRunArtifactText(run.id, artifact.key)
  } catch (error) {
    artifactPreviewText.value = ''
    apiErrorMessage.value = getApiErrorMessage(error, '文件预览失败，请稍后重试。')
  } finally {
    isArtifactPreviewLoading.value = false
  }
}

async function retryArtifactRendering(): Promise<void> {
  const run = generationRun.value
  if (!run || !GENERATION_RUN_RESULT_STATUSES.has(run.status)) {
    return
  }
  isArtifactRenderingRetrying.value = true
  apiErrorMessage.value = ''
  try {
    const response = await retryGenerationRunArtifacts(run.id)
    generationRunArtifacts.value = response.data.items
    if (!generationRunArtifacts.value.some((item) => item.key === selectedArtifactKey.value)) {
      selectedArtifactKey.value = generationRunArtifacts.value[0]?.key ?? 'workbook'
    }
    ElMessage.success('文件渲染已完成。')
    await refreshGenerationRun(run.id, { scheduleNext: false })
  } catch (error) {
    apiErrorMessage.value = getApiErrorMessage(error, '重试文件渲染失败。')
  } finally {
    isArtifactRenderingRetrying.value = false
  }
}

async function cancelCurrentGenerationRun(): Promise<void> {
  const run = generationRun.value
  if (!run || !GENERATION_RUN_ACTIVE_STATUSES.has(run.status)) {
    return
  }
  isGenerationRunCancelling.value = true
  apiErrorMessage.value = ''
  try {
    const response = await cancelGenerationRun(run.id)
    applyGenerationRun(response.data)
    stopGenerationRunPolling()
  } catch (error) {
    apiErrorMessage.value = getApiErrorMessage(error, '取消 Generation Run 失败，请稍后重试。')
  } finally {
    isGenerationRunCancelling.value = false
  }
}

async function retryFailedChunks(): Promise<void> {
  const run = generationRun.value
  if (!run || run.status !== 'partial_completed' || run.failed_chunks <= 0) {
    return
  }
  isGenerationRunRetrying.value = true
  apiErrorMessage.value = ''
  try {
    await retryFailedGenerationChunks(run.id)
    generationRunCases.value = []
    generationRunAtoms.value = []
    await refreshGenerationRun(run.id, { scheduleNext: true })
  } catch (error) {
    apiErrorMessage.value = getApiErrorMessage(error, '重试失败 chunk 失败，请稍后重试。')
  } finally {
    isGenerationRunRetrying.value = false
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

function goToReferencePage(page: number): void {
  referenceCurrentPage.value = Math.min(Math.max(page, 1), referenceTotalPages.value)
}

function clearReferenceFilters(): void {
  referenceSearchKeyword.value = ''
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

function isExcelReferenceUploadFile(file: File): boolean {
  return /\.(xlsx|xls)$/i.test(file.name)
}

async function uploadReference(): Promise<void> {
  if (!referenceUploadFile.value) {
    uploadReferenceError.value = '请选择一个 .xlsx 或 .xls Excel 参考案例文件。'
    return
  }

  if (!isExcelReferenceUploadFile(referenceUploadFile.value)) {
    uploadReferenceError.value = '请选择一个 .xlsx 或 .xls Excel 参考案例文件。'
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

function selectSourceMode(mode: SourceMode): void {
  if (sourceEvidenceRun.value && sourceModeForSourceEvidenceRun(sourceEvidenceRun.value) !== mode) {
    resetSourceEvidenceRunState()
  } else {
    clearSnapshotAndGeneratedResult()
  }
  activeSourceMode.value = mode
  hasUserSelectedSourceMode.value = true
}

function handlePlanningSheetSelectionChange(): void {
  if (isPlanningSourceConfigHydrating.value || isApplyingPlanningSourceConfig) {
    return
  }
  if (activeGenerationInput.value.kind === 'source_evidence') {
    void refreshSourceEvidenceVisualCandidatesForCurrentSheet()
    return
  }
  queuePlanningSourceConfigPersist()
}

function scrollToReferenceLibrary(): void {
  document.querySelector('[data-test="reference-library"]')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function applyReferenceSelection(): void {
  document.querySelector('[data-test="generation-input-module"]')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function scrollToProgressStep(stepKey: ProgressStepKey): void {
  const selectorByStep: Record<ProgressStepKey, string> = {
    source: '.tcg-source-module',
    reference: '[data-test="reference-library"]',
    generate: '[data-test="generation-preview"]',
    export: '[data-test="generation-preview"]',
  }

  document.querySelector(selectorByStep[stepKey])?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function togglePlanningSourceSection(): void {
  planningSourceCollapsed.value = !planningSourceCollapsed.value
}

onMounted(() => {
  void loadPlanningSourceConfig()
  void loadSourceEvidenceCapabilities()
  void loadReferenceLibrary()
  void restoreLatestGenerationRun()
})

onUnmounted(() => {
  stopGenerationRunPolling()
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
      <AppCard as="section" aria-label="用例生成流程" padding="none" class="tcg-progress-card" data-test="test-case-progress-stepper">
        <div class="tcg-progress-stepper">
          <template v-for="(item, index) in progressStepItems" :key="item.key">
            <button
              type="button"
              class="tcg-progress-stepper__item"
              :class="[
                item.status === 'done' ? 'tcg-progress-stepper__item--done' : '',
                item.status === 'active' ? 'tcg-progress-stepper__item--active' : '',
                item.status === 'pending' ? 'tcg-progress-stepper__item--pending' : '',
              ]"
              data-test="test-case-progress-step"
              @click="scrollToProgressStep(item.key)"
            >
              <span class="tcg-progress-stepper__badge">{{ item.step }}</span>
              <span class="tcg-progress-stepper__copy">
                <strong>{{ item.label }}</strong>
                <span>{{ item.description }}</span>
              </span>
            </button>
            <span
              v-if="index < progressStepItems.length - 1"
              class="tcg-progress-stepper__line"
              :class="item.status === 'done' ? 'tcg-progress-stepper__line--done' : ''"
              aria-hidden="true"
            ></span>
          </template>
        </div>
      </AppCard>

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
        <div class="tcg-source-shell">
          <div class="tcg-source-mode-tabs" role="tablist" aria-label="策划案来源类型">
            <button
              type="button"
              role="tab"
              data-test="source-mode-local"
              :class="{ 'is-active': activeSourceMode === 'local' }"
              :aria-selected="activeSourceMode === 'local'"
              @click="selectSourceMode('local')"
            >
              <el-icon><Upload /></el-icon>
              本地文件
            </button>
            <button
              type="button"
              role="tab"
              data-test="source-mode-svn"
              :class="{ 'is-active': activeSourceMode === 'svn' }"
              :aria-selected="activeSourceMode === 'svn'"
              @click="selectSourceMode('svn')"
            >
              <el-icon><FolderOpened /></el-icon>
              SVN 文件
            </button>
            <button
              type="button"
              role="tab"
              data-test="source-mode-feishu-doc"
              :class="{ 'is-active': activeSourceMode === 'feishu_doc' }"
              :aria-selected="activeSourceMode === 'feishu_doc'"
              @click="selectSourceMode('feishu_doc')"
            >
              <el-icon><Document /></el-icon>
              飞书文档
            </button>
          </div>

          <div class="tcg-source-summary-chips" aria-label="已接入来源">
            <span class="tcg-source-chip" :class="{ 'is-ready': isLocalSourceEvidenceRun && canReadSourceEvidenceSnapshot }" data-test="source-chip-local">
              本地文件 · {{ localSourceChipStatus }}
            </span>
            <span class="tcg-source-chip" :class="{ 'is-ready': isSvnSourceEvidenceRun && canReadSourceEvidenceSnapshot }" data-test="source-chip-svn">
              SVN 文件 · {{ svnSourceChipStatus }}
            </span>
            <span class="tcg-source-chip" :class="{ 'is-ready': canReadSourceEvidenceSnapshot, 'is-warning': sourceEvidenceNeedsAuthorization }" data-test="source-chip-feishu-doc">
              飞书文档 · {{ feishuDocumentChipStatus }}
            </span>
          </div>

          <div
            v-if="shouldShowSourceEvidenceCapabilityStatus"
            class="tcg-source-evidence-capability-status"
            :class="sourceEvidenceCapabilityStatusTone"
            data-test="source-evidence-capability-status"
            role="status"
            aria-live="polite"
          >
            <div class="tcg-source-evidence-capability-status__header">
              <div>
                <strong>Source Evidence 运行能力</strong>
                <span>影响 SVN 文件读取、图片观察和 .xls 图片语义理解。</span>
              </div>
              <el-tag
                :type="
                  sourceEvidenceCapabilityStatusTone === 'is-danger'
                    ? 'danger'
                    : sourceEvidenceCapabilityStatusTone === 'is-success'
                      ? 'success'
                      : 'warning'
                "
                effect="light"
              >
                {{ sourceEvidenceCapabilityStatusLabel }}
              </el-tag>
            </div>
            <ul v-if="sourceEvidenceUnavailableCapabilityItems.length">
              <li v-for="item in sourceEvidenceUnavailableCapabilityItems" :key="item.key">
                <el-icon><WarningFilled /></el-icon>
                <span>{{ sanitizeSourceEvidenceDisplay(item.message) }}</span>
                <small v-if="item.action">{{ sanitizeSourceEvidenceDisplay(item.action) }}</small>
              </li>
            </ul>
            <ul v-if="sourceEvidenceCapabilityStatus?.warnings?.length">
              <li
                v-for="(warning, index) in sourceEvidenceCapabilityStatus.warnings"
                :key="`${warning.source}-${index}-${warning.message}`"
              >
                <el-icon><WarningFilled /></el-icon>
                <span>{{ sanitizeSourceEvidenceDisplay(warning.message) }}</span>
              </li>
            </ul>
            <div
              v-if="sourceEvidenceCapabilityStatus?.is_project_admin"
              class="tcg-source-evidence-capability-status__admin"
            >
              <strong>去管理后台配置</strong>
              <span
                v-for="line in sourceEvidenceCapabilityAdminDetailLines"
                :key="line"
              >
                {{ line }}
              </span>
            </div>
          </div>

          <section v-if="activeSourceMode === 'local'" class="tcg-source-mode-panel" data-test="source-panel-local">
            <div class="tcg-local-source-layout">
              <section class="tcg-local-source-upload" aria-label="上传本地文件">
                <h3>上传文件</h3>
                <input
                  ref="localUploadInputRef"
                  class="tcg-hidden-file-input"
                  type="file"
                  accept=".xlsx,.xls,.png,.jpg,.jpeg,.webp"
                  data-test="local-source-upload-input"
                  @change="handleLocalSourceInputChange"
                />
                <div
                  class="tcg-local-source-dropzone"
                  :class="{ 'is-drag-active': isLocalSourceDragActive }"
                  role="button"
                  tabindex="0"
                  data-test="local-source-dropzone"
                  @click="triggerLocalSourceUpload"
                  @keydown.enter.prevent="triggerLocalSourceUpload"
                  @keydown.space.prevent="triggerLocalSourceUpload"
                  @dragenter.prevent="handleLocalSourceDragEnter"
                  @dragover.prevent="handleLocalSourceDragEnter"
                  @dragleave.prevent="handleLocalSourceDragLeave"
                  @drop.prevent="handleLocalSourceDrop"
                >
                  <el-icon><Upload /></el-icon>
                  <strong>拖拽文件到这里，或点击上传</strong>
                  <span>支持 .xlsx / .xls / .png / .jpg / .jpeg / .webp</span>
                  <PrimaryButton
                    size="sm"
                    data-test="local-source-upload-button"
                    :loading="isLocalSourceUploading"
                    :disabled="isLocalSourceUploading"
                    @click.stop="triggerLocalSourceUpload"
                  >
                    <template #icon><Upload /></template>
                    选择文件
                  </PrimaryButton>
                </div>
                <div class="tcg-local-source-recent">
                  <span>最近上传</span>
                  <strong>{{ localSourceFileName }}</strong>
                  <small>{{ localSourceFileSizeLabel }}</small>
                </div>
                <p
                  v-if="localSourceUploadErrorMessage"
                  class="tcg-api-error"
                  role="alert"
                  data-test="local-source-upload-error"
                >
                  {{ localSourceUploadErrorMessage }}
                </p>
              </section>

              <section class="tcg-local-source-status" data-test="local-source-file-status">
                <div class="tcg-local-source-status__header">
                  <div>
                    <h3>Source Evidence 状态</h3>
                    <p>{{ localSourcePanelStatus }}</p>
                  </div>
                  <el-tag :type="isLocalSourceEvidenceRun && canReadSourceEvidenceSnapshot ? 'success' : 'info'" effect="light">
                    {{ localSourceChipStatus }}
                  </el-tag>
                </div>
                <dl class="tcg-local-source-status__list">
                  <div>
                    <dt>文件名</dt>
                    <dd>{{ localSourceFileName }}</dd>
                  </div>
                  <div>
                    <dt>资源清单</dt>
                    <dd>{{ localSourceSheetCountLabel }}</dd>
                  </div>
                  <div>
                    <dt>数据行数</dt>
                    <dd>{{ localSourceSnapshotRowsLabel }}</dd>
                  </div>
                  <div>
                    <dt>Run 状态</dt>
                    <dd>{{ localSourceSelectedSheetLabel }}</dd>
                  </div>
                  <div>
                    <dt>最后读取时间</dt>
                    <dd>{{ localSourceLastReadAtLabel }}</dd>
                  </div>
                </dl>
                <div class="tcg-local-source-actions">
                  <SecondaryButton
                    size="sm"
                    data-test="local-source-refresh-sheets"
                    :disabled="!isLocalSourceEvidenceRun || isLocalSourceRefreshing"
                    :loading="isLocalSourceRefreshing"
                    @click="refreshCurrentLocalSourceSheets"
                  >
                    <template #icon><Refresh /></template>
                    重试读取
                  </SecondaryButton>
                  <SecondaryButton
                    size="sm"
                    data-test="local-source-clear-file"
                    :disabled="!isLocalSourceEvidenceRun"
                    @click="clearCurrentLocalSource"
                  >
                    清除文件
                  </SecondaryButton>
                </div>
              </section>

              <section class="tcg-local-source-flow" data-test="local-source-read-flow">
                <h3>读取流程</h3>
                <ol>
                  <li
                    v-for="step in localReadFlowSteps"
                    :key="step.label"
                    :class="`is-${step.status}`"
                  >
                    <span class="tcg-local-source-flow__dot tcg-flow-dot">
                      <el-icon aria-hidden="true"><component :is="step.icon" /></el-icon>
                    </span>
                    <div>
                      <strong>{{ step.label }}</strong>
                      <span>{{ step.statusLabel }}</span>
                    </div>
                  </li>
                </ol>
              </section>
            </div>
          </section>

          <section v-else-if="activeSourceMode === 'svn'" class="tcg-source-mode-panel" data-test="source-panel-svn">
            <div class="tcg-svn-source-layout">
              <section class="tcg-svn-browser" aria-label="SVN 文件读取">
                <h3>SVN 文件读取</h3>
                <div class="tcg-svn-browser__controls">
                  <label>
                    <span>文件 URL</span>
                    <input
                      v-model="svnFileUrl"
                      type="url"
                      autocomplete="off"
                      placeholder="https://samosvn/data/project/samo/GameDatas/QuestReward.xls"
                      data-test="svn-file-url-input"
                    />
                  </label>
                  <PrimaryButton
                    size="sm"
                    data-test="svn-read-data"
                    :disabled="!isHttpDirUrl(svnFileUrl) || isSvnReadingData || !areSvnSourceEvidenceCapabilitiesAvailable"
                    :loading="isSvnReadingData"
                    @click="readCurrentSvnData"
                  >
                    <template #icon><Refresh /></template>
                    读取来源
                  </PrimaryButton>
                </div>

                <div class="tcg-svn-selected-file" data-test="svn-selected-file-summary">
                  <span>已选 SVN 文件</span>
                  <strong>{{ svnSelectedFileName }}</strong>
                  <small>{{ svnSelectedFileDetailLabel }}</small>
                </div>

                <p v-if="svnDirectoryErrorMessage" class="tcg-api-error" role="alert" data-test="svn-directory-error">
                  {{ svnDirectoryErrorMessage }}
                </p>
                <p
                  v-else-if="!areSvnSourceEvidenceCapabilitiesAvailable"
                  class="tcg-inline-warning"
                  role="status"
                >
                  {{ sourceEvidenceSvnCapabilityMessage || 'SVN 文件 Source Evidence 不可用，请联系项目管理员。' }}
                </p>

                <div v-if="false" class="tcg-svn-table" data-test="svn-directory-table">
                  <table>
                    <thead>
                      <tr>
                        <th>文件名</th>
                        <th>大小</th>
                        <th>更新时间</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-if="isSvnDirectoryLoading">
                        <td colspan="4">正在加载…</td>
                      </tr>
                      <tr v-else-if="!svnVisibleDirectoryEntries.length">
                        <td colspan="4">暂无可选子目录或 Excel 文件。</td>
                      </tr>
                      <tr v-for="entry in svnVisibleDirectoryEntries" v-else :key="`${entry.kind}:${entry.name}`">
                        <td>
                          <span class="tcg-svn-entry-kind" :class="entry.kind === 'dir' ? 'is-dir' : 'is-file'">
                            {{ entry.kind === 'dir' ? '目录' : 'Excel' }}
                          </span>
                          <strong>{{ entry.name }}</strong>
                        </td>
                        <td>{{ entry.kind === 'dir' ? '-' : formatSvnSize(entry.size) }}</td>
                        <td>{{ formatSvnEntryTime(entry.last_modified_at) }}</td>
                        <td>
                          <button
                            v-if="entry.kind === 'dir'"
                            type="button"
                            class="tcg-inline-action"
                            :disabled="!canEnterSvnSubdirectory"
                            :data-test="`svn-entry-dir-${entry.name}`"
                            @click="enterSvnDirectory(entry)"
                          >
                            进入
                          </button>
                          <button
                            v-else
                            type="button"
                            class="tcg-inline-action"
                            :data-test="`svn-entry-file-${entry.name}`"
                            @click="selectSvnExcelFile(entry)"
                          >
                            选中
                          </button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </section>

              <section
                v-if="false"
                class="tcg-svn-credential"
                :class="{ 'is-warning': isSvnCredentialStatusWarning }"
                data-test="svn-credential-status"
              >
                <div class="tcg-svn-credential__header">
                  <div>
                    <h3>SVN 凭据状态</h3>
                    <p>{{ svnSourcePanelStatus }}</p>
                  </div>
                  <el-tag :type="isSvnCredentialStatusWarning ? 'warning' : hasCurrentSvnCredential ? 'success' : 'info'" effect="light">
                    {{ svnCredentialStatusLabel }}
                  </el-tag>
                </div>
                <dl class="tcg-svn-credential__list">
                  <div>
                    <dt>SVN Host</dt>
                    <dd>{{ svnCurrentHost || '未识别' }}</dd>
                  </div>
                  <div>
                    <dt>用户名</dt>
                    <dd>{{ svnCredentialUsernameLabel }}</dd>
                  </div>
                  <div>
                    <dt>上次测试结果</dt>
                    <dd>{{ svnCredentialLastTestLabel }}</dd>
                  </div>
                  <div>
                    <dt>最后测试时间</dt>
                    <dd>{{ svnCredentialLastTestTimeLabel }}</dd>
                  </div>
                </dl>
                <div class="tcg-svn-credential__actions">
                  <SecondaryButton
                    size="sm"
                    data-test="svn-configure-credential"
                    @click="openSvnCredentialDialogForCurrentHost"
                  >
                    配置凭据
                  </SecondaryButton>
                  <SecondaryButton
                    size="sm"
                    data-test="svn-test-connection"
                    :disabled="isSvnTestingConnection || !svnCurrentHost"
                    :loading="isSvnTestingConnection"
                    @click="testCurrentSvnConnection"
                  >
                    <template #icon><Refresh /></template>
                    测试连接
                  </SecondaryButton>
                </div>
              </section>

              <section class="tcg-svn-flow" data-test="svn-read-flow">
                <h3>读取流程</h3>
                <ol>
                  <li v-for="step in svnReadFlowSteps" :key="step.label" :class="`is-${step.status}`">
                    <span class="tcg-svn-flow__dot tcg-flow-dot">
                      <el-icon aria-hidden="true"><component :is="step.icon" /></el-icon>
                    </span>
                    <div>
                      <strong>{{ step.label }}</strong>
                      <span>{{ step.statusLabel }}</span>
                    </div>
                  </li>
                </ol>
              </section>
            </div>
          </section>

          <section
            v-else
            class="tcg-source-mode-panel tcg-source-evidence-mode-panel"
            aria-label="飞书文档来源"
            data-test="source-panel-feishu-doc"
          >
            <div class="tcg-source-evidence-layout">
              <section class="tcg-source-evidence-read-panel" data-test="source-evidence-read-panel">
                <div class="tcg-source-evidence-panel__header">
                  <div>
                    <h3>飞书文档读取</h3>
                    <p>读取正文、表格和资源清单，形成短期来源证据。</p>
                  </div>
                  <el-tag v-if="sourceEvidenceRun" :type="sourceEvidenceStatusTagType" effect="light">
                    {{ sourceEvidenceStatus }}
                  </el-tag>
                </div>
                <div class="tcg-source-evidence-entry__controls">
                  <input
                    v-model="sourceEvidenceUrl"
                    type="url"
                    autocomplete="off"
                    placeholder="粘贴 docx / docs / wiki / sheets / base 链接"
                    data-test="source-evidence-url-input"
                    @input="handleSourceEvidenceUrlInput"
                  />
                  <PrimaryButton
                    data-test="source-evidence-create-button"
                    :loading="isSourceEvidenceCreating"
                    :disabled="isSourceEvidenceCreating || !sourceEvidenceUrl.trim()"
                    @click="createFeishuSourceEvidenceRun"
                  >
                    <template #icon><Document /></template>
                    读取文档
                  </PrimaryButton>
                </div>
                <p v-if="sourceEvidenceSafeApiErrorMessage" class="tcg-api-error" role="alert">
                  {{ sourceEvidenceSafeApiErrorMessage }}
                </p>
                <div
                  v-if="sourceEvidenceRun"
                  class="tcg-source-evidence-document-card"
                  data-test="source-evidence-document-card"
                >
                  <div class="tcg-source-evidence-document-card__title">
                    <span class="tcg-source-evidence-document-card__icon">
                      <el-icon><Document /></el-icon>
                    </span>
                    <div>
                      <strong>{{ sourceEvidenceSafeTitle }}</strong>
                      <span>{{ sourceEvidenceSafeSummary }}</span>
                    </div>
                    <el-tag :type="sourceEvidenceStatusTagType" effect="light">
                      {{ sourceEvidenceStatus }}
                    </el-tag>
                  </div>
                  <div class="tcg-source-evidence-meta">
                    <span>TTL {{ sourceEvidenceExpiryLabel }}</span>
                    <span>{{ sourceEvidenceResourceCountLabel }}</span>
                    <span>{{ sourceEvidenceVisualSelectionLabel }}</span>
                    <span>{{ sourceEvidenceObservationLabel }}</span>
                    <span>{{ sourceEvidenceStatusMessage }}</span>
                  </div>
                  <ul v-if="sourceEvidencePanelWarnings.length" class="tcg-source-evidence-warnings">
                    <li
                      v-for="(warning, index) in sourceEvidencePanelWarnings"
                      :key="`${warning.source}-${index}-${warning.message}`"
                    >
                      <el-icon><WarningFilled /></el-icon>
                      <span>{{ warning.message }}</span>
                    </li>
                  </ul>
                  <p
                    v-if="sourceEvidenceSafeAuthorizationMessage"
                    class="tcg-inline-warning"
                    role="status"
                    aria-live="polite"
                  >
                    {{ sourceEvidenceSafeAuthorizationMessage }}
                  </p>
                  <p v-if="sourceEvidenceSafeAuthorizationErrorMessage" class="tcg-api-error" role="alert">
                    {{ sourceEvidenceSafeAuthorizationErrorMessage }}
                  </p>
                  <div class="tcg-source-evidence-actions">
                    <SecondaryButton
                      size="sm"
                      data-test="source-evidence-resources-button"
                      :disabled="isSourceEvidenceResourcesLoading"
                      :loading="isSourceEvidenceResourcesLoading"
                      @click="openSourceEvidenceResources"
                    >
                      <template #icon><Collection /></template>
                      资源清单
                    </SecondaryButton>
                    <SecondaryButton
                      v-if="shouldShowSourceEvidenceAuthorizationButton"
                      size="sm"
                      data-test="source-evidence-authorization-button"
                      :disabled="!canRequestSourceEvidenceAuthorization"
                      :loading="isSourceEvidenceAuthorizationRequesting"
                      @click="requestFeishuSourceEvidenceAuthorization"
                    >
                      <template #icon><WarningFilled /></template>
                      申请授权
                    </SecondaryButton>
                    <SecondaryButton
                      v-if="canRetrySourceEvidenceRun"
                      size="sm"
                      data-test="source-evidence-retry-button"
                      :loading="isSourceEvidenceRetrying"
                      @click="retryFeishuSourceEvidenceRun"
                    >
                      <template #icon><Refresh /></template>
                      重试读取
                    </SecondaryButton>
                  </div>
                </div>
                <div v-else class="tcg-source-evidence-empty">
                  <strong>待读取飞书文档</strong>
                  <span>粘贴链接后点击读取文档，页面不会自动申请授权或自动重试。</span>
                </div>
              </section>

              <section
                class="tcg-source-evidence-authorization"
                :class="sourceEvidenceAuthorizationToneClass"
                data-test="source-evidence-authorization-status"
              >
                <div class="tcg-source-evidence-panel__header">
                  <div>
                    <h3>授权与资源状态</h3>
                    <p>{{ sourceEvidenceAuthorizationStatusDescription }}</p>
                  </div>
                  <el-tag :type="sourceEvidenceAuthorizationTagType" effect="light">
                    {{ sourceEvidenceAuthorizationStatusLabel }}
                  </el-tag>
                </div>
                <dl class="tcg-source-evidence-status-list">
                  <div>
                    <dt>授权状态</dt>
                    <dd>{{ sourceEvidenceAuthorizationStatusLabel }}</dd>
                  </div>
                  <div>
                    <dt>授权目标</dt>
                    <dd>{{ sourceEvidenceAuthorizationTargetLabel }}</dd>
                  </div>
                  <div>
                    <dt>已发送</dt>
                    <dd>{{ sourceEvidenceAuthorizationSentCountLabel }}</dd>
                  </div>
                  <div>
                    <dt>资源状态</dt>
                    <dd>{{ sourceEvidenceResourceStatusLabel }}</dd>
                  </div>
                </dl>
                <p class="tcg-source-evidence-auth-note">
                  仅用于读取正文、表格、下载图片/附件和生成证据，不修改源文档
                </p>
              </section>

              <section class="tcg-source-evidence-pipeline" data-test="source-evidence-pipeline">
                <h3>证据流水线</h3>
                <ol>
                  <li
                    v-for="step in sourceEvidencePipelineSteps"
                    :key="step.label"
                    :class="`is-${step.status}`"
                  >
                    <span class="tcg-source-evidence-pipeline__dot tcg-flow-dot">
                      <el-icon aria-hidden="true"><component :is="step.icon" /></el-icon>
                    </span>
                    <div>
                      <strong>{{ step.label }}</strong>
                      <span>{{ step.statusLabel }}</span>
                    </div>
                  </li>
                </ol>
              </section>
            </div>
          </section>
          <div
            v-if="sourceEvidenceRun && activeSourceMode !== 'feishu_doc'"
            class="tcg-source-evidence-document-card"
            data-test="source-evidence-document-card"
          >
            <div class="tcg-source-evidence-document-card__title">
              <span class="tcg-source-evidence-document-card__icon">
                <el-icon><Document /></el-icon>
              </span>
              <div>
                <strong>{{ sourceEvidenceSafeTitle }}</strong>
                <span>{{ sourceEvidenceSafeSummary }}</span>
              </div>
              <el-tag :type="sourceEvidenceStatusTagType" effect="light">
                {{ sourceEvidenceStatus }}
              </el-tag>
            </div>
            <div class="tcg-source-evidence-meta">
              <span>TTL {{ sourceEvidenceExpiryLabel }}</span>
              <span>{{ sourceEvidenceResourceCountLabel }}</span>
              <span>{{ sourceEvidenceVisualSelectionLabel }}</span>
              <span>{{ sourceEvidenceObservationLabel }}</span>
              <span>{{ sourceEvidenceStatusMessage }}</span>
            </div>
            <ul v-if="sourceEvidencePanelWarnings.length" class="tcg-source-evidence-warnings">
              <li
                v-for="(warning, index) in sourceEvidencePanelWarnings"
                :key="`${warning.source}-${index}-${warning.message}`"
              >
                <el-icon><WarningFilled /></el-icon>
                <span>{{ warning.message }}</span>
              </li>
            </ul>
            <p v-if="sourceEvidenceGenerationBlockMessage" class="tcg-inline-warning" role="status">
              {{ sourceEvidenceGenerationBlockMessage }}
            </p>
            <div class="tcg-source-evidence-actions">
              <SecondaryButton
                size="sm"
                data-test="source-evidence-resources-button"
                :disabled="isSourceEvidenceResourcesLoading"
                :loading="isSourceEvidenceResourcesLoading"
                @click="openSourceEvidenceResources"
              >
                <template #icon><Collection /></template>
                资源清单
              </SecondaryButton>
              <SecondaryButton
                v-if="canRetrySourceEvidenceRun"
                size="sm"
                data-test="source-evidence-retry-button"
                :loading="isSourceEvidenceRetrying"
                @click="retryFeishuSourceEvidenceRun"
              >
                <template #icon><Refresh /></template>
                重试读取
              </SecondaryButton>
            </div>
          </div>
        </div>
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
          <section class="tcg-input-block tcg-current-source-card" aria-labelledby="planning-source-title" data-test="current-source-card">
            <div class="tcg-input-block__header">
              <h3 id="planning-source-title">当前来源</h3>
              <span>{{ activeGenerationInput.statusLabel }}</span>
            </div>
            <div class="tcg-current-source-card__body">
              <span class="tcg-current-source-card__icon">{{ activeGenerationInputIconLabel }}</span>
              <div>
                <strong>{{ activeGenerationInput.typeLabel }} / {{ activeGenerationInput.title }}</strong>
                <span>{{ activeGenerationSourceSummary }}</span>
              </div>
              <el-tag :type="activeGenerationInput.statusType" effect="light">
                {{ activeGenerationInput.statusLabel }}
              </el-tag>
            </div>
          </section>

          <section class="tcg-input-block tcg-snapshot-readiness-card" aria-labelledby="snapshot-readiness-title" data-test="snapshot-readiness-card">
            <div class="tcg-input-block__header">
              <h3 id="snapshot-readiness-title">{{ shouldShowPlanningSheetSelector ? 'Sheet 选择' : '读取状态说明' }}</h3>
              <span>{{ canReadSnapshot ? '可读取' : '待处理' }}</span>
            </div>
            <label v-if="shouldShowPlanningSheetSelector" class="tcg-field">
              <span>策划案 Sheet</span>
              <el-select
                v-model="selectedPlanningSheetName"
                :disabled="!hasPlanningSheetOptions"
                data-test="planning-sheet-select"
                @change="handlePlanningSheetSelectionChange"
              >
                <el-option
                  v-if="!hasPlanningSheetOptions"
                  label="当前来源无可选 Sheet"
                  value=""
                />
                <el-option
                  v-for="sheet in activePlanningSheetOptions"
                  :key="sheet.sheet_id ?? sheet.name"
                  :label="sheet.name"
                  :value="sheet.name"
                />
              </el-select>
            </label>
            <div v-else class="tcg-source-evidence-input-status" data-test="source-evidence-input-status">
              <div>
                <strong>纳入页签/章节范围</strong>
                <span>{{ sourceEvidenceSafeSummary || sourceEvidenceSafeTitle }}</span>
              </div>
              <div>
                <strong>文本/表格已读取</strong>
                <span>{{ canReadSourceEvidenceSnapshot ? '可生成兼容快照' : '等待来源读取完成' }}</span>
              </div>
              <div>
                <strong>资源清单已生成</strong>
                <span>{{ sourceEvidenceResourceCountLabel }}</span>
              </div>
              <div>
                <strong>图片/附件待观察</strong>
                <span>{{ sourceEvidenceVisualSelectionLabel }}；{{ sourceEvidenceObservationLabel }}；未采纳资源不作为需求事实。</span>
              </div>
            </div>
            <p class="tcg-source-hint">
              {{ activeGenerationReadinessLabel }}
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

          <section class="tcg-input-block tcg-reference-entry-card" aria-labelledby="generation-settings-title" data-test="reference-entry-card">
            <div class="tcg-input-block__header">
              <h3 id="generation-settings-title">参考来源（可选）</h3>
              <span>{{ selectedReferenceFiles.length ? `已选 ${selectedReferenceFiles.length} 个` : '可选' }}</span>
            </div>
            <strong>{{ referenceEntrySummary }}</strong>
            <span>{{ primaryReference ? `当前主参考 Sheet：${selectedReferenceSheet?.sheetName ?? primaryReference.defaultSheetName ?? '未记录'}；参考案例仅作增强。` : '从参考案例库选择 Excel 用例作为参考。' }}</span>
            <div class="tcg-warning-note">
              <el-icon><WarningFilled /></el-icon>
              <span>{{ primaryReference ? `参考用例数量${referenceCaseCountDisplay}` : '未选择主参考时按 qa-case 标准逻辑生成' }}</span>
            </div>
            <SecondaryButton class="tcg-full-button" @click="scrollToReferenceLibrary">
              <template #icon><View /></template>
              前往选择
            </SecondaryButton>
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

        <div class="tcg-reference-workspace">
          <aside class="tcg-reference-category-list" data-test="reference-category-list" aria-label="参考案例分类">
            <div class="tcg-reference-column-title">
              <strong>分类</strong>
              <span>共 {{ referenceCategories.length }} 类</span>
            </div>
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
          </aside>

          <section class="tcg-reference-excel-panel" data-test="reference-excel-table" aria-label="Excel 参考案例">
            <div class="tcg-reference-toolbar">
              <label class="tcg-reference-search">
                <span class="tcg-sr-only">搜索 Excel 参考案例</span>
                <input
                  v-model="referenceSearchKeyword"
                  type="search"
                  name="reference-search"
                  autocomplete="off"
                  placeholder="搜索 Excel 文件名或画像摘要…"
                  data-test="reference-search"
                />
              </label>
              <span class="tcg-reference-excel-only">仅 Excel</span>
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
              class="tcg-reference-table"
              role="table"
              aria-label="Excel 参考案例文件"
            >
              <div class="tcg-reference-table__head" role="row">
                <span>选择</span>
                <span>文件名</span>
                <span>场景数/用例数</span>
                <span>更新时间</span>
                <span>优先级</span>
                <span>操作</span>
              </div>
              <article
                v-for="item in visibleReferenceFiles"
                :key="item.id"
                class="tcg-reference-item"
                :class="{
                  'is-primary': primaryReference?.id === item.id,
                  'is-selected': isReferenceSelected(item.id) && primaryReference?.id !== item.id,
                }"
                role="row"
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
                <div class="tcg-reference-item__body">
                  <div class="tcg-reference-item__title">
                    <div class="tcg-reference-item__icon" :class="getReferenceTypeClass(item.type)" aria-hidden="true">
                      <Document />
                    </div>
                    <span :title="item.name">{{ item.name }}</span>
                    <em class="tcg-reference-type">{{ getReferenceTypeLabel(item.type) }}</em>
                    <el-tag v-if="item.isRecommendedPrimary" size="small" type="success">推荐主参考</el-tag>
                  </div>
                  <p :title="item.profileSummary">{{ item.profileSummary }}</p>
                </div>
                <div class="tcg-reference-metric">
                  <strong>{{ typeof item.caseCount === 'number' ? item.caseCount : '未识别' }}</strong>
                  <span>默认 Sheet：{{ item.defaultSheetName ?? '无' }}</span>
                </div>
                <div class="tcg-reference-updated">
                  <strong>{{ formatReferenceUploadTime(item.updatedAt) }}</strong>
                  <span>{{ item.uploadedBy }}</span>
                </div>
                <div class="tcg-reference-priority">
                  <el-tag :type="getReferencePriorityTagType(item)" size="small">{{ getReferencePriorityLabel(item) }}</el-tag>
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
              <strong>{{ currentCategoryReferenceFiles.length ? '没有匹配的参考案例' : '当前分类暂无 Excel 参考案例' }}</strong>
              <span>
                {{
                  currentCategoryReferenceFiles.length
                    ? '调整搜索或排序后再查看。'
                    : '可以先上传 Excel 参考案例到当前分类。'
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

          <aside class="tcg-reference-selection-summary" data-test="reference-selection-summary" aria-label="当前选择摘要">
            <div class="tcg-reference-column-title">
              <strong>当前选择</strong>
              <span>{{ selectedReferenceFiles.length ? `已选 ${selectedReferenceFiles.length} 个` : '可选增强' }}</span>
            </div>
            <dl>
              <div>
                <dt>已选</dt>
                <dd>{{ selectedReferenceFiles.length }} 个</dd>
              </div>
              <div>
                <dt>推荐优先级</dt>
                <dd>{{ referenceSelectionRecommendationLabel }}</dd>
              </div>
              <div>
                <dt>来源 Excel</dt>
                <dd>{{ referenceSelectionSourceLabel }}</dd>
              </div>
              <div>
                <dt>最近更新时间</dt>
                <dd>{{ referenceSelectionLatestUpdateLabel }}</dd>
              </div>
            </dl>
            <ul v-if="selectedReferenceFiles.length" class="tcg-reference-selected-list">
              <li v-for="file in selectedReferenceFiles" :key="file.id">
                <span>{{ file.name }}</span>
                <em>{{ primaryReference?.id === file.id ? '主参考' : '补充参考' }}</em>
              </li>
            </ul>
            <PrimaryButton size="sm" data-test="reference-apply-button" @click="applyReferenceSelection">
              应用参考
            </PrimaryButton>
          </aside>
        </div>
      </section>

      <section class="tcg-preview" aria-label="用例生成预览" data-test="generation-preview">
          <div class="tcg-preview__header" data-test="preview-action-bar">
            <div class="tcg-module-heading">
              <span class="tcg-module-heading__index">04</span>
              <div>
                <h2>结果预览</h2>
                <p>V3 读取完整 selected Planning Sheet；整理稿和快照仅用于来源预览。</p>
              </div>
            </div>
            <div class="tcg-preview__actions">
              <el-select
                v-if="generationRunArtifacts.length"
                v-model="selectedArtifactKey"
                class="tcg-artifact-select"
                data-test="generation-artifact-select"
                aria-label="选择生成文件预览"
                @change="previewGenerationArtifact"
              >
                <el-option
                  v-for="artifact in generationRunArtifacts"
                  :key="artifact.key"
                  :label="`${artifact.label} · ${artifact.status === 'ready' ? '已生成' : '不可用'}`"
                  :value="artifact.key"
                />
              </el-select>
              <label class="tcg-strict-mode">
                <input
                  v-model="strictMode"
                  type="checkbox"
                  data-test="generation-strict-mode-checkbox"
                  :disabled="isGeneratingCases || isGenerationRunPolling"
                />
                <span>严格模式</span>
              </label>
              <SecondaryButton
                v-if="generationRun && GENERATION_RUN_ACTIVE_STATUSES.has(generationRun.status)"
                data-test="generation-run-cancel-button"
                :loading="isGenerationRunCancelling"
                @click="cancelCurrentGenerationRun"
              >
                取消
              </SecondaryButton>
              <SecondaryButton
                v-if="generationRun?.status === 'partial_completed' && generationRun.failed_chunks > 0"
                data-test="generation-run-retry-button"
                :loading="isGenerationRunRetrying"
                @click="retryFailedChunks"
              >
                <template #icon><Refresh /></template>
                重试失败 chunk
              </SecondaryButton>
              <SecondaryButton
                v-if="generationRun && GENERATION_RUN_RESULT_STATUSES.has(generationRun.status)"
                data-test="generation-artifact-retry-button"
                :loading="isArtifactRenderingRetrying"
                @click="retryArtifactRendering"
              >
                <template #icon><Refresh /></template>
                重试文件渲染
              </SecondaryButton>
              <SecondaryButton
                data-test="preview-export-button"
                :disabled="!canDownloadSelectedArtifact"
                :loading="isExportingCases"
                @click="exportCases"
              >
                <template #icon><Download /></template>
                下载所选文件
              </SecondaryButton>
              <PrimaryButton
                :disabled="!isGenerationReady"
                :loading="isGeneratingCases"
                data-test="preview-generate-button"
                @click="generateCases"
              >
                <template #icon><VideoPlay /></template>
                全量生成用例
              </PrimaryButton>
            </div>
          </div>

          <div class="tcg-preview__tabs">
            <button
              v-for="tab in tabs"
              :key="tab.key"
              type="button"
              :class="{ 'is-active': activeTab === tab.key }"
              :data-test="`preview-tab-${tab.key}`"
              @click="activeTab = tab.key"
            >
              {{ tab.label }}
            </button>
          </div>

          <div v-if="generationRun" class="tcg-generation-run-progress" data-test="generation-run-stage-progress">
            <div class="tcg-generation-run-progress__summary">
              <strong>Generation Run #{{ generationRun.id }}</strong>
              <span>{{ getGenerationRunStatusLabel(generationRun.status) }}</span>
              <span>chunk {{ generationRun.completed_chunks }}/{{ generationRun.total_chunks }}</span>
              <span>失败 {{ generationRun.failed_chunks }}</span>
              <span>Requirement Atom {{ generationRun.atom_count }}</span>
              <span>用例 {{ generationRun.case_count }}</span>
            </div>
            <div class="tcg-generation-run-progress__stages">
              <span
                v-for="stage in generationRunStageItems"
                :key="stage.key"
                class="tcg-generation-run-stage"
                :class="`tcg-generation-run-stage--${stage.status}`"
                :data-test="`generation-run-stage-${stage.key}`"
              >
                {{ stage.label }}
              </span>
            </div>
          </div>

          <div
            v-if="generationRunPartialMessages.length"
            class="tcg-partial-notice"
            data-test="generation-run-partial-notice"
            role="status"
          >
            <el-icon><WarningFilled /></el-icon>
            <div>
              <strong>覆盖限制</strong>
              <ul>
                <li v-for="message in generationRunPartialMessages" :key="message">{{ message }}</li>
              </ul>
            </div>
          </div>

          <div class="tcg-preview__toolbar">
            <div class="tcg-status-strip">
              <el-tag :type="previewStatusType" size="large">{{ previewStatusLabel }}</el-tag>
              <el-tag :type="warnings.length ? 'warning' : 'info'" size="large">{{ warnings.length }} 条限制提示</el-tag>
              <el-tag v-if="sourceEvidenceRun" :type="sourceEvidenceStatusTagType" size="large">
                证据：{{ sourceEvidenceStatusMessage }} · {{ sourceEvidenceVisualSelectionLabel }} · {{ sourceEvidenceObservationLabel }}
              </el-tag>
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

          <div v-if="activeTab === 'artifact'" class="tcg-tab-panel">
            <div class="tcg-artifact-preview" data-test="generation-artifact-preview">
              <div v-if="isArtifactPreviewLoading" class="tcg-brief-state" role="status">
                <span class="tcg-loading-dot"></span>
                <strong>正在读取 {{ selectedGenerationArtifact?.label ?? '文件' }}</strong>
              </div>
              <pre v-else-if="artifactPreviewText">{{ artifactPreviewText }}</pre>
              <div v-else class="tcg-empty-result">选择蓝图、统计或审计文件后可在此预览。</div>
            </div>
          </div>

          <div v-else-if="activeTab === 'brief'" class="tcg-tab-panel">
            <div class="tcg-brief-panel">
              <div class="tcg-brief-panel__header">
                <div>
                  <strong>AI 快照整理稿</strong>
                  <span>辅助阅读与对齐；V3 生成读取完整 selected Planning Sheet，不只读取预览 rows。</span>
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
              <div v-else class="tcg-empty-result">读取来源预览后可查看整理稿</div>
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
              {{ sourceEvidenceRun ? '来源已就绪，点击全量生成用例。' : '生成前先读取 Source Evidence' }}
            </div>
          </div>

          <div v-else-if="activeTab === 'coverage'" class="tcg-tab-panel">
            <div class="tcg-coverage-panel" data-test="generation-run-coverage-panel">
              <div class="tcg-coverage-panel__summary">
                <strong>覆盖 {{ coverageAuditSummary.coveredAtoms }} / {{ coverageAuditSummary.totalAtoms }}</strong>
                <span>未覆盖 {{ coverageAuditSummary.uncoveredAtoms }}</span>
                <span>失败 chunk {{ coverageAuditSummary.failedChunkCount }}</span>
              </div>
              <ul v-if="coverageAuditSummary.exportLimitations.length" class="tcg-warning-list">
                <li v-for="limitation in coverageAuditSummary.exportLimitations" :key="limitation">
                  <el-icon><WarningFilled /></el-icon>
                  <span>{{ limitation }}</span>
                </li>
              </ul>
              <div v-else class="tcg-empty-result">暂无覆盖限制</div>
            </div>
          </div>

          <div v-else-if="activeTab === 'atoms'" class="tcg-tab-panel">
            <table v-if="generationRunAtoms.length" class="tcg-atom-table">
              <thead>
                <tr>
                  <th>Atom ID</th>
                  <th>类型</th>
                  <th>需求原子</th>
                  <th>覆盖状态</th>
                  <th>来源</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="atom in generationRunAtoms" :key="atom.id">
                  <td>{{ atom.atom_id }}</td>
                  <td>{{ atom.atom_type }}</td>
                  <td>{{ atom.requirement_text }}</td>
                  <td>{{ atom.coverage_status }}</td>
                  <td>{{ atom.source_sheet_name }} {{ atom.source_row_start ?? '-' }}-{{ atom.source_row_end ?? '-' }}</td>
                </tr>
              </tbody>
            </table>
            <div v-else class="tcg-empty-result">暂无 Requirement Atom 明细</div>
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

    <el-drawer v-model="sourceEvidenceResourcesDrawerVisible" title="Source Evidence 视觉候选" size="560px">
      <div class="tcg-source-evidence-drawer">
        <p v-if="sourceEvidenceResourcesErrorMessage" class="tcg-api-error" role="alert">
          {{ sourceEvidenceResourcesErrorMessage }}
        </p>
        <p v-else-if="isSourceEvidenceResourcesLoading" class="tcg-inline-warning" aria-live="polite">
          正在读取视觉候选…
        </p>
          <div v-else-if="sourceEvidenceVisualCandidates.length" class="tcg-resource-list">
            <div class="tcg-visual-selection-summary">
              <div>
                <strong>{{ sourceEvidenceVisualSelectionLabel }}</strong>
                <span>{{ sourceEvidenceVisualSelectionDescription }}{{ sourceEvidenceObservationLabel }}</span>
            </div>
            <div class="tcg-visual-selection-actions">
              <SecondaryButton
                size="sm"
                data-test="source-evidence-visual-selection-save-button"
                :disabled="isSourceEvidenceVisualSaving || isSourceEvidenceBlocked"
                :loading="isSourceEvidenceVisualSaving"
                @click="saveSourceEvidenceVisualSelection"
              >
                保存选择
              </SecondaryButton>
              <PrimaryButton
                size="sm"
                data-test="source-evidence-observe-button"
                :disabled="
                  isSourceEvidenceObserving ||
                  isSourceEvidenceBlocked ||
                  !isVisionAiCapabilityAvailable ||
                  !sourceEvidenceSelectedVisualRefs.length
                "
                :loading="isSourceEvidenceObserving"
                @click="observeSelectedSourceEvidenceVisuals"
              >
                <template #icon><View /></template>
                观察已选
              </PrimaryButton>
            </div>
          </div>
          <p v-if="sourceEvidenceVisionCapabilityMessage" class="tcg-inline-warning" role="status">
            {{ sourceEvidenceVisionCapabilityMessage }}
          </p>
          <article
            v-for="candidate in sourceEvidenceVisualCandidates"
            :key="candidate.ref"
            class="tcg-resource-item"
            data-test="source-evidence-resource-row"
          >
            <div class="tcg-visual-candidate-head">
              <label class="tcg-visual-candidate-select">
                <input
                  type="checkbox"
                  :data-test="`visual-candidate-checkbox-${candidate.ref}`"
                  :checked="candidate.selected"
                  :disabled="!candidate.selectable || isSourceEvidenceVisualSaving"
                  @change="handleSourceEvidenceVisualSelectionChange(candidate, $event)"
                />
                <strong>{{ candidate.ref }}</strong>
              </label>
              <span>{{ candidate.filename || '未命名资源' }}</span>
            </div>
            <div class="tcg-resource-meta">
              <span>{{ candidate.type }}</span>
              <span>{{ candidate.position }}</span>
              <span>{{ getVisualCandidateStatusLabel(candidate.status) }}</span>
              <span>{{ candidate.download_status }}</span>
              <span>{{ candidate.adoption_status }}</span>
              <span v-if="candidate.recommended">系统推荐</span>
              <span v-if="candidate.selected">已选</span>
            </div>
            <ul v-if="candidate.recommendation_reasons.length" class="tcg-visual-reasons">
              <li v-for="reason in candidate.recommendation_reasons" :key="`${candidate.ref}-${reason}`">
                {{ reason }}
              </li>
            </ul>
            <p v-if="!candidate.selectable" class="tcg-muted">
              {{ getVisualCandidateStatusLabel(candidate.status) }}，暂不可选择观察。
            </p>
            <div v-if="candidate.dimensions.original_width" class="tcg-resource-meta">
              <span>{{ candidate.dimensions.original_width }}×{{ candidate.dimensions.original_height }}</span>
              <span v-if="candidate.dimensions.optimized_width">
                优化 {{ candidate.dimensions.optimized_width }}×{{ candidate.dimensions.optimized_height }}
              </span>
            </div>
          </article>
          <section v-if="sourceEvidenceObservations.length" class="tcg-observation-list" data-test="source-evidence-observations">
            <div class="tcg-visual-selection-summary">
              <div>
                <strong>视觉观察结果</strong>
                <span>已观察不等于已采纳；只有已采纳证据会进入生成和导出。</span>
              </div>
            </div>
            <article
              v-for="observation in sourceEvidenceObservations"
              :key="observation.id"
              class="tcg-observation-item"
              data-test="source-evidence-observation-row"
            >
              <div class="tcg-visual-candidate-head">
                <strong>{{ observation.ref }}</strong>
                <span>{{ observation.status === 'adopted' ? '已采纳' : '已观察未采纳' }}</span>
              </div>
              <div class="tcg-resource-meta">
                <span>{{ observation.type }}</span>
                <span>{{ observation.position }}</span>
                <span v-if="observation.confidence !== null && observation.confidence !== undefined">
                  置信度 {{ Math.round(observation.confidence * 100) }}%
                </span>
              </div>
              <p>{{ observation.summary }}</p>
              <p v-if="observation.visible_text" class="tcg-muted">可见文字：{{ observation.visible_text }}</p>
              <ul v-if="observation.limitations.length" class="tcg-visual-reasons">
                <li v-for="limitation in observation.limitations" :key="`${observation.id}-${limitation}`">
                  {{ limitation }}
                </li>
              </ul>
              <div class="tcg-source-evidence-actions">
                <SecondaryButton
                  v-if="observation.status === 'adopted'"
                  size="sm"
                  :data-test="`source-evidence-revoke-observation-${observation.id}`"
                  :disabled="isObservationSaving(observation.id) || isSourceEvidenceBlocked"
                  :loading="isObservationSaving(observation.id)"
                  @click="revokeSourceEvidenceObservation(observation)"
                >
                  撤销采纳
                </SecondaryButton>
                <PrimaryButton
                  v-else
                  size="sm"
                  :data-test="`source-evidence-adopt-observation-${observation.id}`"
                  :disabled="isObservationSaving(observation.id) || isSourceEvidenceBlocked"
                  :loading="isObservationSaving(observation.id)"
                  @click="adoptSourceEvidenceObservation(observation)"
                >
                  采纳证据
                </PrimaryButton>
              </div>
            </article>
          </section>
        </div>
        <div v-else class="tcg-empty-result">暂无视觉候选</div>
      </div>
    </el-drawer>

    <SvnCredentialDialog
      :visible="svnCredentialDialogVisible"
      :host="svnCredentialDialogHost"
      :default-username="svnCredentialDialogDefaultUsername"
      :default-password="svnCredentialDialogDefaultPassword"
      :default-test-dir-url="svnCredentialDialogDefaultTestDirUrl"
      @update:visible="(value: boolean) => (svnCredentialDialogVisible = value)"
      @saved="handleSvnCredentialSaved"
    />

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

    <el-dialog
      v-model="uploadReferenceDialogVisible"
      title="上传参考案例"
      width="520px"
      class="tcg-reference-upload-dialog"
    >
      <div class="tcg-reference-upload-dialog__body">
        <section class="tcg-reference-upload-hero" aria-labelledby="reference-upload-title">
          <span class="tcg-reference-upload-hero__icon" aria-hidden="true">
            <el-icon><Upload /></el-icon>
          </span>
          <div>
            <strong id="reference-upload-title">上传 Excel 参考案例</strong>
            <p>只接收 Excel 文件，上传后自动生成画像并加入当前分类。</p>
          </div>
        </section>

        <div class="tcg-reference-upload-target">
          <span>当前分类</span>
          <strong>{{ referenceUploadCategoryLabel }}</strong>
          <em>{{ referenceUploadFileStatusLabel }}</em>
        </div>

        <label
          class="tcg-reference-upload-dropzone"
          :class="{
            'has-file': Boolean(referenceUploadFile),
            'has-error': Boolean(uploadReferenceError),
          }"
        >
          <input
            name="reference-upload-file"
            type="file"
            accept=".xlsx,.xls"
            :aria-describedby="uploadReferenceError ? 'reference-upload-help reference-upload-error' : 'reference-upload-help'"
            data-test="reference-upload-input"
            @change="handleReferenceUploadFileChange"
          />
          <span class="tcg-reference-upload-dropzone__icon" aria-hidden="true">
            <el-icon><DocumentChecked /></el-icon>
          </span>
          <span class="tcg-reference-upload-dropzone__copy">
            <strong>{{ referenceUploadFileName }}</strong>
            <span>{{ referenceUploadFileDetail }}</span>
          </span>
          <span class="tcg-reference-upload-dropzone__action">选择文件</span>
        </label>

        <div id="reference-upload-help" class="tcg-reference-upload-notes">
          <span>.xlsx / .xls</span>
          <span>生成确定性画像</span>
          <span>仅 Excel 来源</span>
        </div>

        <p
          v-if="uploadReferenceError"
          id="reference-upload-error"
          class="tcg-dialog-error"
          role="alert"
          aria-live="polite"
        >
          {{ uploadReferenceError }}
        </p>
      </div>
      <template #footer>
        <div class="tcg-dialog-actions tcg-reference-upload-actions">
          <SecondaryButton size="sm" @click="uploadReferenceDialogVisible = false">取消</SecondaryButton>
          <PrimaryButton
            size="sm"
            data-test="reference-upload-submit"
            :loading="isUploadingReference"
            @click="uploadReference"
          >
            上传 Excel
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
  --tcg-card-surface: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
  --tcg-card-shadow: 0 1px 2px rgba(15, 23, 42, 0.035), 0 10px 24px rgba(15, 23, 42, 0.035);
  --tcg-card-shadow-strong: 0 1px 2px rgba(15, 23, 42, 0.04), 0 14px 30px rgba(15, 98, 254, 0.085);
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

.tcg-progress-card {
  flex: 0 0 auto;
  border-radius: 18px;
}

.tcg-progress-stepper {
  display: flex;
  min-height: 76px;
  align-items: center;
  gap: 18px;
  overflow-x: auto;
  padding: 18px 28px;
  scrollbar-width: thin;
}

.tcg-progress-stepper__item {
  display: inline-flex;
  min-width: 120px;
  flex: 0 0 auto;
  align-items: center;
  gap: 14px;
  border: 0;
  background: transparent;
  cursor: pointer;
  padding: 0;
  text-align: left;
}

.tcg-progress-stepper__badge {
  display: inline-flex;
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border: 1px solid #d8e1ee;
  border-radius: var(--radius-pill);
  background: var(--color-bg-card-soft);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: 14px;
  font-weight: 800;
  transition:
    color 160ms cubic-bezier(0.2, 0, 0, 1),
    background-color 160ms cubic-bezier(0.2, 0, 0, 1),
    border-color 160ms cubic-bezier(0.2, 0, 0, 1),
    box-shadow 160ms cubic-bezier(0.2, 0, 0, 1);
}

.tcg-progress-stepper__copy {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.tcg-progress-stepper__copy strong {
  color: var(--color-text-main);
  font-size: 14px;
  font-weight: 800;
  line-height: 1.2;
}

.tcg-progress-stepper__copy span {
  overflow: hidden;
  max-width: 210px;
  color: var(--color-text-muted);
  font-size: 12px;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-progress-stepper__line {
  height: 2px;
  min-width: 56px;
  flex: 1 1 auto;
  border-radius: var(--radius-pill);
  background: var(--color-border);
}

.tcg-progress-stepper__item--done .tcg-progress-stepper__badge {
  border-color: var(--color-success);
  background: linear-gradient(180deg, #18c477, var(--color-success));
  color: var(--color-bg-card);
  box-shadow: 0 8px 18px rgba(18, 183, 106, 0.18);
}

.tcg-progress-stepper__line--done {
  background: var(--color-success);
}

.tcg-progress-stepper__item--active .tcg-progress-stepper__badge {
  border-color: var(--color-primary);
  background: linear-gradient(180deg, #1b6dff, var(--color-primary));
  color: var(--color-bg-card);
  box-shadow: 0 10px 20px rgba(15, 98, 254, 0.24);
}

.tcg-progress-stepper__item--active .tcg-progress-stepper__copy span {
  color: var(--color-primary-hover);
}

.tcg-progress-stepper__item--pending .tcg-progress-stepper__badge {
  background: var(--color-bg-card-soft);
  color: var(--color-text-muted);
}

.tcg-progress-stepper__item:focus-visible {
  outline: 2px solid rgba(15, 98, 254, 0.42);
  outline-offset: 4px;
  border-radius: var(--radius-md);
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
  min-height: 128px;
  padding: 24px 26px;
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
  font-size: 14px;
  font-weight: 750;
  letter-spacing: 0;
}

.tcg-metrics :deep(.ui-metric-card__icon) {
  width: 62px;
  height: 62px;
}

.tcg-metrics :deep(.ui-metric-card__icon svg) {
  width: 32px;
  height: 32px;
}

.tcg-metrics :deep(.ui-metric-card__value) {
  margin: 8px 0;
  font-family: var(--font-sans);
  font-size: 34px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
  line-height: 1.08;
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

.tcg-source-shell {
  display: grid;
  gap: 8px;
}

.tcg-source-mode-tabs {
  display: grid;
  width: min(100%, 430px);
  grid-template-columns: repeat(3, minmax(0, 1fr));
  overflow: hidden;
  border: 1px solid rgba(203, 213, 225, 0.84);
  border-radius: var(--ui-control-radius);
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.035), inset 0 1px 0 rgba(255, 255, 255, 0.86);
}

.tcg-source-mode-tabs button {
  display: inline-flex;
  min-width: 0;
  min-height: 38px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 0;
  border-right: 1px solid var(--color-border-light);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 13px;
  font-weight: 800;
  transition:
    background-color 160ms cubic-bezier(0.2, 0, 0, 1),
    color 160ms cubic-bezier(0.2, 0, 0, 1),
    box-shadow 160ms cubic-bezier(0.2, 0, 0, 1);
}

.tcg-source-mode-tabs button:last-child {
  border-right: 0;
}

.tcg-source-mode-tabs button.is-active {
  background: linear-gradient(180deg, #edf5ff 0%, #e8f1ff 100%);
  color: var(--color-primary-hover);
  box-shadow:
    inset 0 0 0 1px rgba(15, 98, 254, 0.18),
    inset 0 -2px 0 rgba(15, 98, 254, 0.58);
}

.tcg-source-mode-tabs .el-icon {
  font-size: 15px;
}

.tcg-source-summary-chips {
  display: flex;
  min-width: 0;
  gap: 8px;
  flex-wrap: wrap;
}

.tcg-source-chip {
  display: inline-flex;
  min-height: 26px;
  align-items: center;
  border: 1px solid rgba(203, 213, 225, 0.74);
  border-radius: var(--radius-pill);
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.025);
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 800;
  line-height: 1;
  padding: 0 10px;
}

.tcg-source-chip.is-ready {
  border-color: rgba(18, 183, 106, 0.2);
  background: var(--color-success-soft);
  color: #15803d;
}

.tcg-source-chip.is-warning {
  border-color: rgba(245, 158, 11, 0.24);
  background: var(--color-warning-soft);
  color: #b45309;
}

.tcg-source-evidence-capability-status {
  display: grid;
  gap: 8px;
  border: 1px solid rgba(245, 158, 11, 0.2);
  border-radius: var(--radius-md);
  background: linear-gradient(180deg, #fffbeb 0%, #ffffff 100%);
  color: var(--color-text-secondary);
  padding: 10px 12px;
}

.tcg-source-evidence-capability-status.is-danger {
  border-color: rgba(239, 68, 68, 0.22);
  background: linear-gradient(180deg, #fff5f5 0%, #ffffff 100%);
}

.tcg-source-evidence-capability-status.is-success {
  border-color: rgba(18, 183, 106, 0.2);
  background: linear-gradient(180deg, #f0fdf4 0%, #ffffff 100%);
}

.tcg-source-evidence-capability-status__header {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.tcg-source-evidence-capability-status__header > div,
.tcg-source-evidence-capability-status li,
.tcg-source-evidence-capability-status__admin {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.tcg-source-evidence-capability-status strong {
  color: var(--color-text-primary);
  font-size: 13px;
  font-weight: 900;
}

.tcg-source-evidence-capability-status span,
.tcg-source-evidence-capability-status small {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 700;
}

.tcg-source-evidence-capability-status ul {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.tcg-source-evidence-capability-status .el-icon {
  flex: 0 0 auto;
  color: #d97706;
}

.tcg-source-evidence-capability-status__admin {
  border-top: 1px solid rgba(203, 213, 225, 0.64);
  padding-top: 8px;
}

.tcg-source-mode-panel {
  display: grid;
  gap: 12px;
  border: 1px solid rgba(203, 213, 225, 0.86);
  border-radius: var(--radius-md);
  background:
    linear-gradient(180deg, rgba(248, 251, 255, 0.96) 0%, rgba(255, 255, 255, 0.98) 100%),
    radial-gradient(circle at 0 0, rgba(15, 98, 254, 0.08), transparent 32%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.82);
  padding: 12px;
}

.tcg-local-source-layout {
  display: grid;
  grid-template-columns: minmax(280px, 1.1fr) minmax(300px, 0.95fr) minmax(220px, 0.55fr);
  gap: 12px;
}

.tcg-local-source-upload,
.tcg-local-source-status,
.tcg-local-source-flow {
  position: relative;
  display: grid;
  min-width: 0;
  align-content: start;
  gap: 10px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: var(--tcg-card-surface);
  box-shadow: var(--tcg-card-shadow), var(--tcg-soft-inset);
  overflow: hidden;
  padding: 12px;
}

.tcg-local-source-upload::before,
.tcg-local-source-status::before,
.tcg-local-source-flow::before,
.tcg-svn-browser::before,
.tcg-svn-credential::before,
.tcg-svn-flow::before,
.tcg-source-evidence-read-panel::before,
.tcg-source-evidence-authorization::before,
.tcg-source-evidence-pipeline::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 2px;
  background: linear-gradient(90deg, rgba(15, 98, 254, 0.72), rgba(18, 183, 106, 0.48), rgba(15, 98, 254, 0.2));
  pointer-events: none;
}

.tcg-local-source-upload h3,
.tcg-local-source-status h3,
.tcg-local-source-flow h3 {
  margin: 0;
  color: var(--color-text-main);
  font-size: 13px;
  font-weight: 850;
  line-height: 1.35;
}

.tcg-hidden-file-input {
  display: none;
}

.tcg-local-source-dropzone {
  display: grid;
  min-height: 168px;
  place-items: center;
  align-content: center;
  gap: 8px;
  border: 1px dashed rgba(15, 98, 254, 0.38);
  border-radius: var(--radius-md);
  background:
    linear-gradient(180deg, #ffffff 0%, #f8fbff 100%),
    radial-gradient(circle at 50% 0, rgba(15, 98, 254, 0.08), transparent 45%);
  color: var(--color-text-muted);
  cursor: pointer;
  outline: 2px solid transparent;
  outline-offset: 3px;
  text-align: center;
  padding: 20px;
  transition:
    border-color 0.18s ease,
    background 0.18s ease,
    box-shadow 0.18s ease;
}

.tcg-local-source-dropzone:hover,
.tcg-local-source-dropzone:focus-visible,
.tcg-local-source-dropzone.is-drag-active {
  border-color: rgba(15, 98, 254, 0.72);
  background:
    linear-gradient(180deg, #f7fbff 0%, #eef5ff 100%),
    radial-gradient(circle at 50% 0, rgba(15, 98, 254, 0.14), transparent 48%);
  box-shadow:
    inset 0 0 0 1px rgba(15, 98, 254, 0.12),
    0 10px 24px rgba(15, 98, 254, 0.08);
}

.tcg-local-source-dropzone > .el-icon {
  color: #15803d;
  font-size: 30px;
}

.tcg-local-source-dropzone strong {
  color: var(--color-text-main);
  font-size: 13px;
  font-weight: 850;
  line-height: 1.35;
}

.tcg-local-source-dropzone span {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.45;
}

.tcg-local-source-recent {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  border-top: 1px solid var(--color-border-light);
  color: var(--color-text-muted);
  font-size: 12px;
  padding-top: 8px;
}

.tcg-local-source-recent strong {
  overflow: hidden;
  color: var(--color-text-main);
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-local-source-recent small {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 700;
}

.tcg-local-source-status__header {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--color-border-light);
  padding-bottom: 8px;
}

.tcg-local-source-status__header p {
  margin: 3px 0 0;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.45;
}

.tcg-local-source-status__list {
  display: grid;
  margin: 0;
}

.tcg-local-source-status__list > div {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr);
  gap: 12px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.82);
  padding: 8px 0;
}

.tcg-local-source-status__list > div:last-child {
  border-bottom: 0;
}

.tcg-local-source-status__list dt {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 750;
}

.tcg-local-source-status__list dd {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--color-text-main);
  font-size: 12px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-local-source-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 2px;
}

.tcg-local-source-flow ol {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.tcg-local-source-flow li {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  color: var(--color-text-muted);
}

.tcg-local-source-flow li > div {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.tcg-local-source-flow strong {
  overflow: hidden;
  color: var(--color-text-main);
  font-size: 12px;
  font-weight: 850;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-local-source-flow span {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.tcg-local-source-flow__dot {
  display: inline-flex;
  width: 24px;
  height: 24px;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(203, 213, 225, 0.92);
  border-radius: 999px;
  background: #ffffff;
  color: var(--color-text-muted);
  font-size: 12px;
}

.tcg-local-source-flow li.is-done .tcg-local-source-flow__dot {
  border-color: rgba(18, 183, 106, 0.3);
  background: var(--color-success-soft);
  color: #15803d;
}

.tcg-local-source-flow li.is-current .tcg-local-source-flow__dot {
  border-color: rgba(15, 98, 254, 0.38);
  background: var(--color-primary-soft);
  box-shadow: inset 0 0 0 4px #ffffff;
}

.tcg-local-source-flow li.is-current strong {
  color: var(--color-primary-hover);
}

.tcg-svn-source-layout {
  display: grid;
  grid-template-columns: minmax(380px, 1.2fr) minmax(300px, 0.85fr) minmax(220px, 0.52fr);
  gap: 12px;
}

.tcg-svn-browser,
.tcg-svn-credential,
.tcg-svn-flow {
  position: relative;
  display: grid;
  min-width: 0;
  align-content: start;
  gap: 10px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: var(--tcg-card-surface);
  box-shadow: var(--tcg-card-shadow), var(--tcg-soft-inset);
  overflow: hidden;
  padding: 12px;
}

.tcg-svn-credential.is-warning {
  border-color: rgba(245, 158, 11, 0.35);
  background: linear-gradient(180deg, #fffdf8 0%, #fff8ec 100%);
}

.tcg-svn-browser h3,
.tcg-svn-credential h3,
.tcg-svn-flow h3 {
  margin: 0;
  color: var(--color-text-main);
  font-size: 13px;
  font-weight: 850;
  line-height: 1.35;
}

.tcg-svn-browser__controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: end;
  gap: 8px;
}

.tcg-svn-browser__controls label {
  display: grid;
  min-width: 0;
  gap: 5px;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 750;
}

.tcg-svn-browser__controls input {
  width: 100%;
  min-width: 0;
  height: 34px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--ui-control-radius);
  background: #ffffff;
  color: var(--color-text-main);
  font-size: 12px;
  outline: 2px solid transparent;
  outline-offset: 2px;
  padding: 0 10px;
}

.tcg-svn-browser__controls input:focus-visible {
  border-color: rgba(15, 98, 254, 0.58);
  box-shadow: 0 0 0 3px var(--tcg-focus-ring);
}

.tcg-svn-selected-file {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: var(--radius-md);
  background: #f8fafc;
  color: var(--color-text-muted);
  font-size: 12px;
  padding: 8px 10px;
}

.tcg-svn-selected-file strong {
  overflow: hidden;
  color: var(--color-text-main);
  font-weight: 850;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-svn-selected-file small {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 700;
}

.tcg-svn-table {
  overflow: auto;
  max-height: 220px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
}

.tcg-svn-table table {
  width: 100%;
  min-width: 560px;
  border-collapse: collapse;
  font-size: 12px;
}

.tcg-svn-table th {
  height: 32px;
  background: #f8fafc;
  color: var(--color-text-muted);
  font-weight: 850;
  text-align: left;
  padding: 0 10px;
}

.tcg-svn-table td {
  height: 36px;
  border-top: 1px solid rgba(226, 232, 240, 0.82);
  color: var(--color-text-secondary);
  padding: 0 10px;
}

.tcg-svn-table td:first-child {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.tcg-svn-table td:first-child strong {
  overflow: hidden;
  color: var(--color-text-main);
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-svn-entry-kind {
  display: inline-flex;
  min-width: 42px;
  height: 20px;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 850;
}

.tcg-svn-entry-kind.is-dir {
  background: var(--color-primary-soft);
  color: var(--color-primary-hover);
}

.tcg-svn-entry-kind.is-file {
  background: var(--color-success-soft);
  color: #15803d;
}

.tcg-inline-action {
  border: 0;
  background: transparent;
  color: var(--color-primary-hover);
  cursor: pointer;
  font-size: 12px;
  font-weight: 850;
  padding: 0;
}

.tcg-inline-action:disabled {
  color: var(--color-text-muted);
  cursor: not-allowed;
}

.tcg-svn-credential__header {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--color-border-light);
  padding-bottom: 8px;
}

.tcg-svn-credential__header p {
  margin: 3px 0 0;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.45;
}

.tcg-svn-credential__list {
  display: grid;
  margin: 0;
}

.tcg-svn-credential__list > div {
  display: grid;
  grid-template-columns: 98px minmax(0, 1fr);
  gap: 10px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.82);
  padding: 8px 0;
}

.tcg-svn-credential__list > div:last-child {
  border-bottom: 0;
}

.tcg-svn-credential__list dt {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 750;
}

.tcg-svn-credential__list dd {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--color-text-main);
  font-size: 12px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-svn-credential__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tcg-svn-flow ol {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.tcg-svn-flow li {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
}

.tcg-svn-flow li > div {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.tcg-svn-flow strong {
  overflow: hidden;
  color: var(--color-text-main);
  font-size: 12px;
  font-weight: 850;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-svn-flow span {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.tcg-svn-flow__dot {
  display: inline-flex;
  width: 24px;
  height: 24px;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(203, 213, 225, 0.92);
  border-radius: 999px;
  background: #ffffff;
  color: var(--color-text-muted);
}

.tcg-svn-flow li.is-done .tcg-svn-flow__dot {
  border-color: rgba(18, 183, 106, 0.3);
  background: var(--color-success-soft);
  color: #15803d;
}

.tcg-svn-flow li.is-current .tcg-svn-flow__dot {
  border-color: rgba(15, 98, 254, 0.38);
  background: var(--color-primary-soft);
  box-shadow: inset 0 0 0 4px #ffffff;
}

.tcg-svn-flow li.is-current strong {
  color: var(--color-primary-hover);
}

.tcg-source-placeholder-upload {
  display: grid;
  min-height: 148px;
  place-items: center;
  align-content: center;
  gap: 8px;
  border: 1px dashed rgba(15, 98, 254, 0.34);
  border-radius: var(--radius-md);
  background: #ffffff;
  color: var(--color-text-muted);
  text-align: center;
  padding: 20px;
}

.tcg-source-placeholder-upload .el-icon {
  color: #15803d;
  font-size: 30px;
}

.tcg-source-placeholder-upload strong,
.tcg-source-status-card strong {
  color: var(--color-text-main);
  font-size: 13px;
  font-weight: 850;
  line-height: 1.35;
}

.tcg-source-placeholder-upload span,
.tcg-source-status-card span {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.45;
}

.tcg-source-status-card {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: #ffffff;
  padding: 11px 12px;
}

.tcg-source-status-card > div {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.tcg-source-placeholder-steps {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.tcg-source-placeholder-steps span {
  display: inline-flex;
  min-height: 32px;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-pill);
  background: #ffffff;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 800;
}

.tcg-source-placeholder-steps span.is-current {
  border-color: rgba(15, 98, 254, 0.22);
  background: var(--color-primary-soft);
  color: var(--color-primary-hover);
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
  grid-template-columns: minmax(260px, 0.9fr) minmax(320px, 1fr) minmax(260px, 0.78fr);
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

.tcg-current-source-card__body {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: var(--radius-md);
  background: #f8fafc;
  padding: 10px;
}

.tcg-current-source-card__icon {
  display: inline-flex;
  width: 34px;
  height: 34px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: var(--color-primary-soft);
  color: var(--color-primary-hover);
  font-size: 12px;
  font-weight: 900;
}

.tcg-current-source-card__body strong,
.tcg-reference-entry-card > strong {
  display: block;
  overflow: hidden;
  color: var(--color-text-main);
  font-size: 13px;
  font-weight: 850;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-current-source-card__body span:not(.tcg-current-source-card__icon),
.tcg-reference-entry-card > span {
  display: block;
  overflow: hidden;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
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

.tcg-reference-workspace {
  display: grid;
  min-width: 0;
  grid-template-columns: minmax(150px, 0.42fr) minmax(560px, 1.72fr) minmax(220px, 0.58fr);
  gap: 12px;
  align-items: stretch;
}

.tcg-reference-category-list,
.tcg-reference-excel-panel,
.tcg-reference-selection-summary {
  display: grid;
  min-width: 0;
  align-content: start;
  gap: 10px;
  border: 1px solid rgba(226, 232, 240, 0.94);
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.94);
  padding: 10px;
}

.tcg-reference-column-title {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.tcg-reference-column-title strong {
  color: var(--color-text-main);
  font-size: 13px;
  font-weight: 850;
}

.tcg-reference-column-title span {
  color: var(--color-text-muted);
  font-size: 11px;
  font-weight: 750;
}

.tcg-reference-category-list .tcg-reference-category {
  width: 100%;
  min-height: 32px;
  flex: initial;
  justify-content: space-between;
  border-radius: 8px;
  padding: 0 9px;
}

.tcg-reference-excel-panel {
  gap: 9px;
}

.tcg-reference-excel-panel .tcg-reference-toolbar {
  grid-template-columns: minmax(190px, 1fr) auto minmax(132px, 170px);
  gap: 10px;
}

.tcg-reference-excel-only {
  display: inline-flex;
  min-height: 32px;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(18, 183, 106, 0.22);
  border-radius: 8px;
  background: var(--color-success-soft);
  color: #15803d;
  font-size: 12px;
  font-weight: 850;
  padding: 0 10px;
  white-space: nowrap;
}

.tcg-reference-table {
  display: grid;
  min-width: 0;
  gap: 7px;
}

.tcg-reference-table__head,
.tcg-reference-table .tcg-reference-item {
  display: grid;
  grid-template-columns: 42px minmax(230px, 1.7fr) minmax(112px, 0.68fr) minmax(112px, 0.68fr) minmax(104px, 0.58fr) minmax(184px, 0.78fr);
  gap: 10px;
  align-items: center;
}

.tcg-reference-table__head {
  min-height: 30px;
  border-bottom: 1px solid var(--color-border-light);
  color: var(--color-text-muted);
  font-size: 11px;
  font-weight: 850;
  padding: 0 10px 6px;
}

.tcg-reference-table .tcg-reference-item {
  width: auto;
  grid-template-areas: none;
  border-radius: 8px;
  padding: 10px;
}

.tcg-reference-table .tcg-reference-check,
.tcg-reference-table .tcg-reference-item__body,
.tcg-reference-table .tcg-reference-item__actions,
.tcg-reference-table .tcg-reference-item__icon {
  grid-area: auto;
}

.tcg-reference-table .tcg-reference-item__title {
  gap: 7px;
}

.tcg-reference-table .tcg-reference-item__icon {
  width: 28px;
  height: 28px;
  border-radius: 7px;
}

.tcg-reference-metric,
.tcg-reference-updated {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.tcg-reference-metric strong,
.tcg-reference-updated strong {
  overflow: hidden;
  color: var(--color-text-main);
  font-size: 12px;
  font-weight: 850;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-reference-metric span,
.tcg-reference-updated span {
  overflow: hidden;
  color: var(--color-text-muted);
  font-size: 11px;
  font-weight: 650;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-reference-priority {
  min-width: 0;
}

.tcg-reference-selection-summary dl {
  display: grid;
  gap: 8px;
  margin: 0;
}

.tcg-reference-selection-summary dl > div {
  display: grid;
  gap: 3px;
  border-bottom: 1px solid var(--color-border-light);
  padding-bottom: 8px;
}

.tcg-reference-selection-summary dt {
  color: var(--color-text-muted);
  font-size: 11px;
  font-weight: 750;
}

.tcg-reference-selection-summary dd {
  overflow: hidden;
  margin: 0;
  color: var(--color-text-main);
  font-size: 12px;
  font-weight: 850;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-reference-selected-list {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.tcg-reference-selected-list li {
  display: grid;
  gap: 2px;
  border: 1px solid var(--color-border-light);
  border-radius: 8px;
  background: #f8fafc;
  padding: 7px 8px;
}

.tcg-reference-selected-list span {
  overflow: hidden;
  color: var(--color-text-main);
  font-size: 12px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-reference-selected-list em {
  color: var(--color-text-muted);
  font-size: 11px;
  font-style: normal;
  font-weight: 700;
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
  border-radius: var(--ui-input-radius);
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

.tcg-source-evidence-mode-panel {
  background: #f8fbff;
}

.tcg-source-evidence-layout {
  display: grid;
  grid-template-columns: minmax(420px, 1.22fr) minmax(320px, 0.78fr) minmax(220px, 0.48fr);
  gap: 12px;
}

.tcg-source-evidence-read-panel,
.tcg-source-evidence-authorization,
.tcg-source-evidence-pipeline {
  position: relative;
  display: grid;
  min-width: 0;
  align-content: start;
  gap: 10px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: var(--tcg-card-surface);
  box-shadow: var(--tcg-card-shadow), var(--tcg-soft-inset);
  overflow: hidden;
  padding: 12px;
}

.tcg-source-evidence-authorization.is-ready {
  border-color: rgba(18, 183, 106, 0.28);
  background: linear-gradient(180deg, #ffffff 0%, #f4fff9 100%);
}

.tcg-source-evidence-authorization.is-warning {
  border-color: rgba(245, 158, 11, 0.34);
  background: linear-gradient(180deg, #ffffff 0%, #fff8ec 100%);
}

.tcg-source-evidence-authorization.is-danger {
  border-color: rgba(239, 68, 68, 0.3);
  background: linear-gradient(180deg, #ffffff 0%, #fff4f4 100%);
}

.tcg-source-evidence-panel__header,
.tcg-source-evidence-document-card__title,
.tcg-source-evidence-actions {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.tcg-source-evidence-panel__header > div,
.tcg-source-evidence-document-card__title > div {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.tcg-source-evidence-panel__header h3,
.tcg-source-evidence-pipeline h3 {
  margin: 0;
  color: var(--color-text-main);
  font-size: 13px;
  font-weight: 850;
  line-height: 1.35;
}

.tcg-source-evidence-panel__header p {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.45;
}

.tcg-source-evidence-document-card strong,
.tcg-source-evidence-empty strong,
.tcg-source-evidence-input-status strong,
.tcg-resource-item strong {
  color: var(--color-text-main);
  font-size: 13px;
  font-weight: 800;
  line-height: 1.35;
}

.tcg-source-evidence-document-card span,
.tcg-source-evidence-empty span,
.tcg-source-evidence-input-status span,
.tcg-resource-item span {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.45;
}

.tcg-source-evidence-entry__controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.tcg-source-evidence-entry__controls input {
  min-width: 0;
  min-height: var(--ui-control-height-md);
  border: 1px solid var(--color-border-light);
  border-radius: var(--ui-control-radius);
  background: #ffffff;
  color: var(--color-text-main);
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  padding: 0 12px;
}

.tcg-source-evidence-entry__controls input:focus {
  border-color: rgba(15, 98, 254, 0.45);
  box-shadow: 0 0 0 2px var(--tcg-focus-ring);
  outline: 0;
}

.tcg-source-evidence-document-card,
.tcg-source-evidence-empty {
  display: grid;
  gap: 10px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: var(--radius-md);
  background: #f8fafc;
  padding: 10px;
}

.tcg-source-evidence-document-card__title {
  align-items: center;
}

.tcg-source-evidence-document-card__title strong,
.tcg-source-evidence-document-card__title span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-source-evidence-document-card__icon {
  display: inline-flex;
  width: 32px;
  height: 32px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: var(--color-primary-soft);
  color: var(--color-primary-hover);
  font-size: 18px;
}

.tcg-source-evidence-empty {
  border-style: dashed;
}

.tcg-source-evidence-meta,
.tcg-resource-meta {
  display: flex;
  min-width: 0;
  gap: 6px;
  flex-wrap: wrap;
}

.tcg-source-evidence-meta span,
.tcg-resource-meta span {
  border-radius: var(--radius-pill);
  background: #eef4ff;
  color: #315fbe;
  padding: 3px 7px;
}

.tcg-source-evidence-warnings {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.tcg-source-evidence-warnings li {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #b45309;
  font-size: 12px;
  font-weight: 700;
}

.tcg-source-evidence-status-list {
  display: grid;
  margin: 0;
}

.tcg-source-evidence-status-list > div {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr);
  gap: 10px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.82);
  padding: 8px 0;
}

.tcg-source-evidence-status-list > div:last-child {
  border-bottom: 0;
}

.tcg-source-evidence-status-list dt {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 750;
}

.tcg-source-evidence-status-list dd {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--color-text-main);
  font-size: 12px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-source-evidence-auth-note {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  border: 1px solid rgba(15, 98, 254, 0.18);
  border-radius: var(--radius-md);
  background: var(--color-primary-soft);
  color: var(--color-primary-hover);
  font-size: 12px;
  font-weight: 750;
  line-height: 1.55;
  margin: 0;
  padding: 9px 10px;
}

.tcg-source-evidence-pipeline ol {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.tcg-source-evidence-pipeline li {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
}

.tcg-source-evidence-pipeline li > div {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.tcg-source-evidence-pipeline strong {
  overflow: hidden;
  color: var(--color-text-main);
  font-size: 12px;
  font-weight: 850;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-source-evidence-pipeline span {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.tcg-source-evidence-pipeline__dot {
  display: inline-flex;
  width: 24px;
  height: 24px;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(203, 213, 225, 0.92);
  border-radius: 999px;
  background: #ffffff;
  color: var(--color-text-muted);
}

.tcg-source-evidence-pipeline li.is-done .tcg-source-evidence-pipeline__dot {
  border-color: rgba(18, 183, 106, 0.3);
  background: var(--color-success-soft);
  color: #15803d;
}

.tcg-source-evidence-pipeline li.is-current .tcg-source-evidence-pipeline__dot {
  border-color: rgba(15, 98, 254, 0.38);
  background: var(--color-primary-soft);
  box-shadow: inset 0 0 0 4px #ffffff;
}

.tcg-source-evidence-pipeline li.is-current strong {
  color: var(--color-primary-hover);
}

.tcg-local-source-flow ol,
.tcg-svn-flow ol,
.tcg-source-evidence-pipeline ol {
  position: relative;
}

.tcg-local-source-flow li,
.tcg-svn-flow li,
.tcg-source-evidence-pipeline li {
  position: relative;
}

.tcg-local-source-flow li:not(:last-child)::after,
.tcg-svn-flow li:not(:last-child)::after,
.tcg-source-evidence-pipeline li:not(:last-child)::after {
  content: '';
  position: absolute;
  z-index: 0;
  left: 12px;
  top: 27px;
  bottom: -11px;
  width: 1px;
  background: linear-gradient(180deg, rgba(15, 98, 254, 0.24), rgba(203, 213, 225, 0.58));
}

.tcg-local-source-flow li > div,
.tcg-svn-flow li > div,
.tcg-source-evidence-pipeline li > div {
  position: relative;
  z-index: 1;
}

.tcg-flow-dot {
  position: relative;
  z-index: 1;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.045);
}

.tcg-flow-dot .el-icon {
  font-size: 14px;
}

.tcg-local-source-flow li.is-done .tcg-flow-dot,
.tcg-svn-flow li.is-done .tcg-flow-dot,
.tcg-source-evidence-pipeline li.is-done .tcg-flow-dot {
  border-color: rgba(18, 183, 106, 0.34);
  background: linear-gradient(180deg, #ecfdf5 0%, #dcfce7 100%);
  box-shadow:
    0 0 0 3px rgba(18, 183, 106, 0.08),
    0 8px 18px rgba(18, 183, 106, 0.1);
  color: #15803d;
}

.tcg-local-source-flow li.is-current .tcg-flow-dot,
.tcg-svn-flow li.is-current .tcg-flow-dot,
.tcg-source-evidence-pipeline li.is-current .tcg-flow-dot {
  border-color: rgba(15, 98, 254, 0.66);
  background: linear-gradient(180deg, #1b6dff 0%, var(--color-primary) 100%);
  box-shadow:
    0 0 0 4px rgba(15, 98, 254, 0.12),
    0 10px 20px rgba(15, 98, 254, 0.22);
  color: #ffffff;
}

.tcg-source-evidence-input-status {
  display: grid;
  gap: 8px;
  border: 1px solid rgba(18, 183, 106, 0.18);
  border-radius: var(--radius-md);
  background: var(--color-success-soft);
  padding: 10px;
}

.tcg-source-evidence-input-status > div {
  display: grid;
  gap: 2px;
}

.tcg-source-evidence-drawer,
.tcg-resource-list {
  display: grid;
  gap: 10px;
}

.tcg-resource-item {
  display: grid;
  gap: 8px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: #ffffff;
  padding: 10px;
}

.tcg-resource-item > div:first-child {
  display: grid;
  gap: 3px;
}

.tcg-visual-selection-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid rgba(59, 130, 246, 0.18);
  border-radius: var(--radius-md);
  background: #f8fbff;
  padding: 10px;
}

.tcg-visual-selection-summary > div {
  display: grid;
  gap: 3px;
}

.tcg-visual-selection-actions {
  display: inline-flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.tcg-visual-candidate-head {
  display: grid;
  gap: 3px;
}

.tcg-visual-candidate-select {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.tcg-visual-candidate-select input {
  margin: 0;
}

.tcg-visual-reasons {
  display: grid;
  gap: 4px;
  margin: 0;
  padding: 0 0 0 18px;
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.45;
}

.tcg-observation-list,
.tcg-observation-item {
  display: grid;
  gap: 10px;
}

.tcg-observation-item {
  border: 1px solid rgba(18, 183, 106, 0.2);
  border-radius: var(--radius-md);
  background: #f8fffb;
  padding: 10px;
}

.tcg-observation-item p {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.5;
}

.tcg-source-hint {
  overflow: hidden;
  margin: 0;
  border-radius: 9px;
  background: #f8fafc;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
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

.tcg-reference-upload-dialog {
  overflow: hidden;
  border-radius: 18px !important;
  box-shadow:
    0 24px 60px rgba(15, 23, 42, 0.18),
    0 1px 2px rgba(15, 23, 42, 0.08) !important;
}

.tcg-reference-upload-dialog :deep(.el-dialog__header) {
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
  margin: 0;
  padding: 20px 24px 14px;
}

.tcg-reference-upload-dialog :deep(.el-dialog__title) {
  color: var(--color-text-main);
  font-size: 18px;
  font-weight: 850;
  letter-spacing: 0;
}

.tcg-reference-upload-dialog :deep(.el-dialog__body) {
  padding: 16px 24px 18px;
}

.tcg-reference-upload-dialog :deep(.el-dialog__footer) {
  border-top: 1px solid rgba(226, 232, 240, 0.86);
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  padding: 14px 24px 18px;
}

.tcg-reference-upload-dialog__body {
  display: grid;
  gap: 12px;
}

.tcg-reference-upload-hero {
  display: grid;
  min-width: 0;
  grid-template-columns: 44px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  border: 1px solid rgba(201, 216, 238, 0.9);
  border-radius: 14px;
  background:
    linear-gradient(180deg, #ffffff 0%, #f8fbff 100%),
    radial-gradient(circle at 0 0, rgba(15, 98, 254, 0.1), transparent 48%);
  box-shadow: var(--tcg-card-shadow), var(--tcg-soft-inset);
  padding: 12px;
}

.tcg-reference-upload-hero__icon {
  display: inline-flex;
  width: 44px;
  height: 44px;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  background: linear-gradient(180deg, #1b6dff, var(--color-primary));
  color: #ffffff;
  box-shadow: 0 12px 24px rgba(15, 98, 254, 0.2);
}

.tcg-reference-upload-hero__icon .el-icon {
  font-size: 22px;
}

.tcg-reference-upload-hero strong {
  display: block;
  color: var(--color-text-main);
  font-size: 15px;
  font-weight: 850;
  line-height: 1.35;
}

.tcg-reference-upload-hero p {
  margin: 3px 0 0;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.5;
}

.tcg-reference-upload-target {
  display: grid;
  min-width: 0;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 12px;
  background: #ffffff;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 750;
  padding: 8px 10px;
}

.tcg-reference-upload-target strong {
  overflow: hidden;
  color: var(--color-text-main);
  font-weight: 850;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-reference-upload-target em {
  border-radius: var(--radius-pill);
  background: var(--color-primary-soft);
  color: var(--color-primary-hover);
  font-style: normal;
  font-weight: 800;
  padding: 3px 8px;
}

.tcg-reference-upload-dropzone {
  position: relative;
  display: grid;
  min-width: 0;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  min-height: 92px;
  border: 1px dashed rgba(15, 98, 254, 0.36);
  border-radius: 14px;
  background:
    linear-gradient(180deg, #ffffff 0%, #f8fbff 100%),
    radial-gradient(circle at 100% 0, rgba(18, 183, 106, 0.1), transparent 42%);
  color: var(--color-text-secondary);
  cursor: pointer;
  outline: 2px solid transparent;
  outline-offset: 3px;
  overflow: hidden;
  padding: 14px;
  touch-action: manipulation;
  transition:
    border-color 160ms cubic-bezier(0.2, 0, 0, 1),
    box-shadow 160ms cubic-bezier(0.2, 0, 0, 1),
    background-color 160ms cubic-bezier(0.2, 0, 0, 1);
  -webkit-tap-highlight-color: transparent;
}

.tcg-reference-upload-dropzone input {
  position: absolute;
  inset: 0;
  z-index: 2;
  width: 100%;
  height: 100%;
  cursor: pointer;
  opacity: 0;
}

.tcg-reference-upload-dropzone:hover,
.tcg-reference-upload-dropzone:focus-within {
  border-color: rgba(15, 98, 254, 0.68);
  box-shadow:
    inset 0 0 0 1px rgba(15, 98, 254, 0.1),
    0 12px 28px rgba(15, 98, 254, 0.09);
}

.tcg-reference-upload-dropzone.has-file {
  border-color: rgba(18, 183, 106, 0.38);
  background:
    linear-gradient(180deg, #ffffff 0%, #f4fff9 100%),
    radial-gradient(circle at 100% 0, rgba(18, 183, 106, 0.14), transparent 42%);
}

.tcg-reference-upload-dropzone.has-error {
  border-color: rgba(239, 68, 68, 0.4);
  background: linear-gradient(180deg, #ffffff 0%, #fff7f7 100%);
}

.tcg-reference-upload-dropzone__icon {
  display: inline-flex;
  width: 38px;
  height: 38px;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: var(--color-success-soft);
  color: #15803d;
}

.tcg-reference-upload-dropzone__icon .el-icon {
  font-size: 20px;
}

.tcg-reference-upload-dropzone__copy {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.tcg-reference-upload-dropzone__copy strong {
  overflow: hidden;
  color: var(--color-text-main);
  font-size: 14px;
  font-weight: 850;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-reference-upload-dropzone__copy span {
  overflow: hidden;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tcg-reference-upload-dropzone__action {
  border-radius: var(--radius-pill);
  background: var(--color-primary);
  color: #ffffff;
  font-size: 12px;
  font-weight: 850;
  padding: 7px 11px;
  box-shadow: 0 10px 18px rgba(15, 98, 254, 0.18);
}

.tcg-reference-upload-notes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tcg-reference-upload-notes span {
  display: inline-flex;
  min-height: 24px;
  align-items: center;
  border: 1px solid rgba(203, 213, 225, 0.78);
  border-radius: var(--radius-pill);
  background: #ffffff;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 800;
  padding: 0 9px;
}

.tcg-reference-upload-actions {
  align-items: center;
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

.tcg-strict-mode {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 800;
  line-height: 1.25;
  white-space: nowrap;
}

.tcg-strict-mode input {
  width: 16px;
  height: 16px;
  accent-color: var(--color-primary);
}

.tcg-preview__tabs {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  align-items: stretch;
  gap: 4px;
  border-bottom: 1px solid var(--color-border-light);
  background: #ffffff;
  padding: 0 16px;
}

.tcg-preview__tabs button {
  position: relative;
  min-width: 0;
  min-height: 44px;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 13px;
  font-weight: 800;
  overflow: hidden;
  padding: 0 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition:
    background-color 160ms cubic-bezier(0.2, 0, 0, 1),
    color 160ms cubic-bezier(0.2, 0, 0, 1);
}

.tcg-preview__tabs button::after {
  position: absolute;
  right: 14px;
  bottom: -1px;
  left: 14px;
  height: 2px;
  border-radius: var(--radius-pill);
  background: transparent;
  content: '';
}

.tcg-preview__tabs button.is-active {
  color: var(--color-primary-hover);
  background: transparent;
  box-shadow: none;
}

.tcg-preview__tabs button.is-active::after {
  background: var(--color-primary);
}

.tcg-preview__tabs button:hover {
  color: var(--color-primary-hover);
  background: transparent;
}

.tcg-preview__tabs button:focus-visible {
  z-index: 1;
  outline: 2px solid rgba(15, 98, 254, 0.42);
  outline-offset: -4px;
}

.tcg-preview__toolbar {
  border-bottom: 1px solid var(--color-border-light);
  background: rgba(255, 255, 255, 0.74);
  padding: 10px 16px;
}

.tcg-generation-run-progress {
  display: grid;
  gap: 9px;
  border-bottom: 1px solid var(--color-border-light);
  background: #f8fafc;
  padding: 10px 16px;
}

.tcg-generation-run-progress__summary,
.tcg-generation-run-progress__stages {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.tcg-generation-run-progress__summary strong {
  color: var(--color-text-main);
  font-size: 13px;
  font-weight: 850;
}

.tcg-generation-run-progress__summary span {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 700;
}

.tcg-generation-run-stage {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: #ffffff;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 800;
  line-height: 1.2;
  padding: 6px 8px;
}

.tcg-generation-run-stage--active {
  border-color: rgba(15, 98, 254, 0.38);
  background: #eef5ff;
  color: var(--color-primary-hover);
}

.tcg-generation-run-stage--done {
  border-color: rgba(22, 163, 74, 0.25);
  background: #f0fdf4;
  color: #15803d;
}

.tcg-partial-notice {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  border-bottom: 1px solid rgba(245, 158, 11, 0.2);
  background: var(--color-warning-soft);
  color: #92400e;
  padding: 10px 16px;
}

.tcg-partial-notice strong {
  display: block;
  font-size: 13px;
  font-weight: 850;
  margin-bottom: 3px;
}

.tcg-partial-notice ul {
  display: grid;
  gap: 2px;
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  font-weight: 720;
  line-height: 1.45;
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

.tcg-coverage-panel {
  display: grid;
  gap: 12px;
}

.tcg-coverage-panel__summary {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  color: var(--color-text-secondary);
  font-size: 13px;
  font-weight: 760;
}

.tcg-coverage-panel__summary strong {
  color: var(--color-text-main);
  font-size: 15px;
  font-weight: 850;
}

.tcg-atom-table {
  width: 100%;
  border-collapse: collapse;
  color: var(--color-text-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.tcg-atom-table th,
.tcg-atom-table td {
  border-bottom: 1px solid var(--color-border-light);
  padding: 9px 10px;
  text-align: left;
  vertical-align: top;
}

.tcg-atom-table th {
  color: var(--color-text-main);
  font-weight: 850;
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
  font-family: var(--font-sans);
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
  .tcg-progress-stepper__item,
  .tcg-progress-stepper__badge,
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

/* 与个人/项目校验页对齐：保留结构，只收敛 /test-cases 独有的装饰风格。 */
.test-case-generator-page {
  --tcg-panel-bg: #ffffff;
  --tcg-panel-border: rgba(228, 236, 245, 0.98);
  --tcg-panel-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
  --tcg-panel-shadow-strong: 0 14px 28px rgba(15, 23, 42, 0.06);
  --tcg-panel-rail: transparent;
  --tcg-card-surface: #ffffff;
  --tcg-card-shadow: 0 1px 2px rgba(15, 23, 42, 0.025);
  --tcg-card-shadow-strong: 0 12px 24px rgba(15, 23, 42, 0.055);
}

.tcg-source-module :deep(.ui-collapsible-section__inner),
.tcg-input-module,
.tcg-reference-library,
.tcg-preview {
  border-color: var(--tcg-panel-border);
  background: #ffffff;
  box-shadow: var(--tcg-panel-shadow), inset 0 1px 0 rgba(255, 255, 255, 0.94);
}

.tcg-preview::before,
.tcg-input-module::before,
.tcg-reference-library::before,
.tcg-local-source-upload::before,
.tcg-local-source-status::before,
.tcg-local-source-flow::before,
.tcg-svn-browser::before,
.tcg-svn-credential::before,
.tcg-svn-flow::before,
.tcg-source-evidence-read-panel::before,
.tcg-source-evidence-authorization::before,
.tcg-source-evidence-pipeline::before {
  display: none;
}

.tcg-source-mode-tabs {
  border-color: rgba(205, 220, 245, 0.82);
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}

.tcg-source-mode-tabs button {
  color: #475569;
}

.tcg-source-mode-tabs button.is-active {
  background: #eff6ff;
  color: #2563eb;
  box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.1);
}

.tcg-source-chip,
.tcg-source-placeholder-steps span,
.tcg-reference-upload-notes span {
  border-color: rgba(205, 220, 245, 0.82);
  background: #ffffff;
  box-shadow: none;
}

.tcg-source-mode-panel,
.tcg-source-evidence-mode-panel {
  border-color: rgba(228, 236, 245, 0.98);
  background: #ffffff;
  box-shadow: none;
}

.tcg-local-source-upload,
.tcg-local-source-status,
.tcg-local-source-flow,
.tcg-svn-browser,
.tcg-svn-credential,
.tcg-svn-flow,
.tcg-source-evidence-read-panel,
.tcg-source-evidence-authorization,
.tcg-source-evidence-pipeline,
.tcg-reference-category-list,
.tcg-reference-excel-panel,
.tcg-reference-selection-summary,
.tcg-input-block,
.tcg-source-evidence-document-card,
.tcg-source-evidence-empty,
.tcg-brief-panel__header,
.tcg-brief-state,
.tcg-brief-markdown pre,
.tcg-empty-result {
  border-color: rgba(228, 236, 245, 0.94);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.99), rgba(248, 251, 255, 0.92)),
    #ffffff;
  box-shadow: var(--tcg-card-shadow);
}

.tcg-local-source-flow li,
.tcg-svn-flow li,
.tcg-source-evidence-pipeline li {
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  padding: 6px 8px 6px 0;
}

.tcg-local-source-flow li.is-current,
.tcg-svn-flow li.is-current,
.tcg-source-evidence-pipeline li.is-current {
  border-color: rgba(37, 99, 235, 0.12);
  background: #f8fbff;
}

.tcg-local-source-flow li.is-done,
.tcg-svn-flow li.is-done,
.tcg-source-evidence-pipeline li.is-done {
  background: rgba(240, 253, 244, 0.58);
}

.tcg-local-source-dropzone,
.tcg-source-placeholder-upload,
.tcg-reference-upload-dropzone {
  border-color: rgba(148, 163, 184, 0.48);
  background: #ffffff;
  box-shadow: none;
}

.tcg-local-source-dropzone:hover,
.tcg-local-source-dropzone:focus-visible,
.tcg-local-source-dropzone.is-drag-active,
.tcg-reference-upload-dropzone:hover,
.tcg-reference-upload-dropzone:focus-within {
  border-color: rgba(37, 99, 235, 0.46);
  background: #f8fbff;
  box-shadow:
    inset 0 0 0 1px rgba(37, 99, 235, 0.08),
    0 10px 22px rgba(15, 23, 42, 0.045);
}

.tcg-module-heading__index,
.tcg-source-evidence-document-card__icon,
.tcg-source-placeholder-steps span.is-current,
.tcg-reference-page-number.is-active {
  background: #eff6ff;
  color: #2563eb;
  box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.08);
}

.tcg-reference-category:hover,
.tcg-reference-category.is-active,
.tcg-reference-type-filter button:hover,
.tcg-reference-type-filter button.is-active,
.tcg-reference-item:hover,
.tcg-reference-item.is-selected,
.tcg-reference-item.is-primary {
  background: #f8fbff;
}

.tcg-reference-table__head,
.tcg-svn-table th,
.tcg-case-table :deep(th.el-table__cell) {
  background: #f8fafc !important;
  color: #64748b;
}

.tcg-reference-table .tcg-reference-item,
.tcg-svn-selected-file,
.tcg-reference-selected-list li,
.tcg-source-evidence-input-status {
  background: #f8fafc;
  box-shadow: none;
}

.tcg-flow-dot,
.tcg-source-evidence-pipeline__dot {
  border-color: #d9e3f0;
  background:
    linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  box-shadow:
    0 1px 2px rgba(15, 23, 42, 0.035),
    inset 0 1px 0 rgba(255, 255, 255, 0.92);
}

.tcg-local-source-flow li.is-done .tcg-flow-dot,
.tcg-svn-flow li.is-done .tcg-flow-dot,
.tcg-source-evidence-pipeline li.is-done .tcg-flow-dot {
  background: #f0fdf4;
  box-shadow:
    0 0 0 3px rgba(18, 183, 106, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.88);
}

.tcg-local-source-flow li.is-current .tcg-flow-dot,
.tcg-svn-flow li.is-current .tcg-flow-dot,
.tcg-source-evidence-pipeline li.is-current .tcg-flow-dot {
  background: #2563eb;
  box-shadow:
    0 0 0 4px rgba(37, 99, 235, 0.12),
    0 8px 18px rgba(37, 99, 235, 0.18);
}

.tcg-preview__header,
.tcg-preview__toolbar,
.tcg-preview__tabs,
.tcg-tab-panel,
.tcg-warning-strip,
.tcg-reference-list__footer {
  background: #ffffff;
}

.tcg-stale-notice,
.tcg-brief-panel__notice,
.tcg-warning-list li,
.tcg-warning-strip__items,
.tcg-reference-excel-only {
  box-shadow: none;
}

@media (max-width: 1360px) {
  .tcg-source-evidence-layout {
    grid-template-columns: minmax(0, 1fr) minmax(260px, 340px);
  }

  .tcg-source-evidence-pipeline {
    grid-column: 1 / -1;
  }

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

  .tcg-progress-stepper {
    padding: 16px 20px;
  }

  .tcg-metrics,
  .tcg-input-grid,
  .tcg-local-source-layout,
  .tcg-svn-source-layout,
  .tcg-reference-workspace,
  .tcg-source-evidence-layout {
    grid-template-columns: 1fr;
  }

  .tcg-source-evidence-pipeline {
    grid-column: auto;
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
  .tcg-reference-library .tcg-panel__header {
    align-items: stretch;
    flex-direction: column;
    gap: 10px;
  }

  .tcg-reference-library .tcg-panel__actions {
    width: 100%;
    flex-wrap: wrap;
    justify-content: flex-start;
  }

  .tcg-reference-toolbar,
  .tcg-reference-excel-panel .tcg-reference-toolbar,
  .tcg-svn-browser__controls,
  .tcg-source-evidence-entry__controls {
    grid-template-columns: 1fr;
  }

  .tcg-reference-toolbar {
    align-items: stretch;
  }

  .tcg-reference-sort {
    max-width: none;
  }

  .tcg-svn-browser__controls button,
  .tcg-source-evidence-entry__controls button {
    width: 100%;
  }

  .tcg-reference-table__head {
    display: none;
  }

  .tcg-reference-table .tcg-reference-item {
    grid-template-columns: 28px minmax(0, 1fr);
    grid-template-areas:
      "check body"
      "check metric"
      "check updated"
      "check priority"
      "actions actions";
    align-items: start;
  }

  .tcg-reference-table .tcg-reference-check {
    grid-area: check;
  }

  .tcg-reference-table .tcg-reference-item__body {
    grid-area: body;
  }

  .tcg-reference-table .tcg-reference-metric {
    grid-area: metric;
  }

  .tcg-reference-table .tcg-reference-updated {
    grid-area: updated;
  }

  .tcg-reference-table .tcg-reference-priority {
    grid-area: priority;
  }

  .tcg-reference-table .tcg-reference-item__actions {
    grid-area: actions;
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
    overflow-x: auto;
    padding: 0 12px;
  }
}

.tcg-artifact-select {
  width: 224px;
}

.tcg-artifact-preview {
  min-height: 240px;
}

.tcg-artifact-preview pre {
  max-height: 560px;
  margin: 0;
  padding: 18px;
  overflow: auto;
  border: 1px solid var(--app-border, #dce4ef);
  border-radius: 12px;
  background: #f7f9fc;
  color: #26344a;
  font: 13px/1.7 ui-monospace, SFMono-Regular, Consolas, monospace;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 640px) {
  .tcg-reference-upload-dialog {
    width: calc(100vw - 32px) !important;
  }

  .tcg-reference-upload-dialog :deep(.el-dialog__header),
  .tcg-reference-upload-dialog :deep(.el-dialog__body),
  .tcg-reference-upload-dialog :deep(.el-dialog__footer) {
    padding-right: 16px;
    padding-left: 16px;
  }

  .tcg-reference-upload-hero,
  .tcg-reference-upload-dropzone {
    grid-template-columns: 1fr;
    justify-items: start;
  }

  .tcg-reference-upload-target {
    grid-template-columns: 1fr;
  }

  .tcg-reference-upload-dropzone__action {
    justify-self: stretch;
    text-align: center;
  }
}
</style>
