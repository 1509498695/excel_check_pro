<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  Collection,
  DataAnalysis,
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
import type { SourceManagementStoreLike } from '../types/panelStores'
import type { DataSource, SourceMetadata } from '../types/workbench'

type PreviewTab = 'snapshot' | 'blueprint' | 'cases' | 'warnings'
type Priority = 'P0' | 'P1' | 'P2'
type ReferenceFileType = 'xlsx' | 'md' | 'txt'
type ReferenceTypeFilter = 'all' | ReferenceFileType
type ReferenceSort = 'recommended' | 'newest' | 'name'

interface ReferenceFile {
  id: string
  categoryId: string
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
}

interface ReferenceCategory {
  id: string
  name: string
  description: string
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

interface BlueprintModule {
  name: string
  count: number
  tone: 'primary' | 'success' | 'warning' | 'purple'
}

const activeTab = ref<PreviewTab>('cases')
const selectedReferenceCategoryId = ref('activity')
const selectedReferenceIds = ref<string[]>(['activity-regression-template'])
const primaryReferenceId = ref('activity-regression-template')
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
const profilePreviewFileId = ref('')
const referenceMoreFileId = ref('')
const isGeneratedResultStale = ref(false)
const generatedResultStaleReason = ref('')
const selectedPlanningSourceId = ref('plan_feishu')
const selectedPlanningSheetName = ref('')
const planningSourceCollapsed = ref(false)
const planningSourcePanelRef = ref<{ openCreateDialog: () => void } | null>(null)

const referencePageSize = 5

const defaultPlanningSource: DataSource = {
  id: 'plan_feishu',
  type: 'feishu',
  pathOrUrl: 'https://example.feishu.cn/sheets/xxx',
}

const defaultPlanningSourceMetadata: SourceMetadata = {
  source_id: 'plan_feishu',
  source_type: 'feishu',
  authorization_status: 'authorized',
  sheets: [
    { name: '活动策划案 / Sheet1', sheet_id: 'activity-sheet', columns: ['模块', '需求点', '配置来源', '备注'] },
    { name: '奖励配置 / Sheet2', sheet_id: 'reward-sheet', columns: ['奖励ID', '奖励内容', '限制条件'] },
  ],
}

const planningSourceStore = reactive<SourceManagementStoreLike>({
  sources: [{ ...defaultPlanningSource }],
  capabilities: ['local_excel', 'feishu', 'svn'],
  preferredSourceId: defaultPlanningSource.id,
  sourceMetadataMap: {
    [defaultPlanningSource.id]: { ...defaultPlanningSourceMetadata },
  },
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
    const metadata: SourceMetadata = {
      source_id: source.id,
      source_type: source.type,
      sheets: [],
    }
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
  },
  removeSource(sourceId: string): void {
    planningSourceStore.sources = planningSourceStore.sources.filter((source) => source.id !== sourceId)
    if (planningSourceStore.sourceMetadataMap) {
      delete planningSourceStore.sourceMetadataMap[sourceId]
    }
    if (selectedPlanningSourceId.value === sourceId) {
      selectedPlanningSourceId.value = planningSourceStore.sources[0]?.id ?? ''
    }
  },
  useSampleSource(): void {
    planningSourceStore.upsertSource({ ...defaultPlanningSource })
  },
})

const referenceCategories = ref<ReferenceCategory[]>([
  { id: 'activity', name: '活动用例', description: '活动入口、规则、奖励和回归影响' },
  { id: 'reward', name: '礼包用例', description: '礼包发放、领取限制和补偿边界' },
  { id: 'ui', name: 'UI 通用', description: '入口展示、按钮状态、空态和提示' },
  { id: 'uncategorized', name: '未分类', description: '暂未归入分类的参考材料' },
])

const rewardReferenceFiles: ReferenceFile[] = Array.from({ length: 24 }, (_, index) => {
  const caseNumber = index + 1
  const isExcel = caseNumber % 4 === 0
  const paddedNumber = String(caseNumber).padStart(2, '0')

  return {
    id: `reward-edge-${paddedNumber}`,
    categoryId: 'reward',
    name: isExcel ? `礼包领取回归 ${paddedNumber}.xlsx` : `礼包活动边界补充 ${paddedNumber}.md`,
    type: isExcel ? 'xlsx' : 'md',
    summary: isExcel ? '礼包发放字段、兑换条件和回归状态' : '领取次数、补偿发放和异常提示',
    uploadedBy: caseNumber % 3 === 0 ? 'Samo QA' : 'admin',
    uploadedAt: `2026-06-${String(22 - (caseNumber % 7)).padStart(2, '0')}T${String(9 + (caseNumber % 8)).padStart(
      2,
      '0',
    )}:20:00+08:00`,
    caseCount: isExcel ? 64 + caseNumber : 18 + caseNumber,
    profileSummary: isExcel
      ? '字段结构：用例编号 / 礼包ID / 奖励内容 / 限制条件；优先级：P0/P1/P2；默认 Sheet：礼包用例'
      : '字段结构：Markdown 表格；优先级风格：高/中/低；粒度：一行一个领取边界',
    defaultSheetName: isExcel ? '礼包用例' : undefined,
    sheetOptions: isExcel
      ? [
          { sheetName: '礼包用例', sheetIndex: 0, isDefault: true, caseCount: 64 + caseNumber },
          { sheetName: '补偿回归', sheetIndex: 1, caseCount: 28 + caseNumber },
        ]
      : undefined,
  }
})

const referenceFiles = ref<ReferenceFile[]>([
  {
    id: 'activity-regression-template',
    categoryId: 'activity',
    name: '活动回归模板.xlsx',
    type: 'xlsx',
    tag: '推荐主参考',
    summary: '字段完整，P0/P1/P2 优先级风格',
    uploadedBy: 'admin',
    uploadedAt: '2026-06-22T10:18:00+08:00',
    caseCount: 120,
    profileSummary: '字段结构：编号 / 模块 / 检查点 / 标题 / 优先级 / 备注；优先级：P0/P1/P2；默认 Sheet：测试用例',
    warnings: ['包含历史说明页，已排除不可用 Sheet。'],
    isRecommendedPrimary: true,
    defaultSheetName: '测试用例',
    sheetOptions: [
      { sheetName: '测试用例', sheetIndex: 0, isDefault: true, caseCount: 120 },
      { sheetName: '历史回归', sheetIndex: 1, caseCount: 86 },
      { sheetName: '边界场景', sheetIndex: 2, caseCount: 34 },
    ],
  },
  {
    id: 'activity-boundary-md',
    categoryId: 'activity',
    name: '礼包活动边界.md',
    type: 'md',
    summary: '补充奖励领取、次数限制和异常路径',
    uploadedBy: 'Samo QA',
    uploadedAt: '2026-06-21T16:36:00+08:00',
    caseCount: 42,
    profileSummary: '字段结构：Markdown 表格；优先级风格：P0/P1；粒度：边界条件独立成例',
  },
  {
    id: 'activity-ui-checklist',
    categoryId: 'activity',
    name: 'UI 通用检查.txt',
    type: 'txt',
    summary: '覆盖入口展示、按钮状态和空态提示',
    uploadedBy: 'admin',
    uploadedAt: '2026-06-20T14:12:00+08:00',
    caseCount: undefined,
    profileSummary: '字段结构：checklist；优先级未知；粒度：入口、按钮、空态提示',
    warnings: ['TXT 未可靠识别用例数量。'],
  },
  {
    id: 'ui-common-checklist',
    categoryId: 'ui',
    name: 'UI 通用冒烟.xlsx',
    type: 'xlsx',
    tag: '推荐主参考',
    summary: '入口、弹窗、按钮、空态与错误提示',
    uploadedBy: 'admin',
    uploadedAt: '2026-06-19T11:08:00+08:00',
    caseCount: 76,
    profileSummary: '字段结构：页面 / 控件 / 状态 / 预期；优先级：P1/P2；默认 Sheet：UI冒烟',
    isRecommendedPrimary: true,
    defaultSheetName: 'UI冒烟',
    sheetOptions: [
      { sheetName: 'UI冒烟', sheetIndex: 0, isDefault: true, caseCount: 76 },
      { sheetName: '空态检查', sheetIndex: 1, caseCount: 24 },
    ],
  },
  {
    id: 'ui-empty-state',
    categoryId: 'ui',
    name: '空态与弱网提示.txt',
    type: 'txt',
    summary: '覆盖空态、错误提示、弱网重试和二次确认',
    uploadedBy: 'Samo QA',
    uploadedAt: '2026-06-18T17:45:00+08:00',
    profileSummary: '字段结构：文本 checklist；优先级未知；粒度：一个提示态一个检查点',
  },
  {
    id: 'uncategorized-legacy',
    categoryId: 'uncategorized',
    name: '历史活动用例摘录.md',
    type: 'md',
    summary: '旧活动用例片段，尚未归类',
    uploadedBy: 'admin',
    uploadedAt: '2026-06-16T15:22:00+08:00',
    caseCount: 18,
    profileSummary: '字段结构：Markdown 段落；优先级风格不稳定；粒度偏粗，需要人工确认',
    warnings: ['该文件未归类，建议先整理分类后使用。'],
  },
  ...rewardReferenceFiles,
])

const generatedCases: GeneratedCase[] = [
  {
    id: 'TC-001',
    module: '活动入口',
    checkpoint: '展示校验',
    title: '活动入口按配置开放',
    priority: 'P1',
    status: '未执行',
    remarks: '-',
  },
  {
    id: 'TC-002',
    module: '奖励领取',
    checkpoint: '次数限制',
    title: '同账号重复领取提示',
    priority: 'P0',
    status: '未执行',
    remarks: '-',
  },
  {
    id: 'TC-003',
    module: '奖励领取',
    checkpoint: '道具发放',
    title: '奖励发放成功并计入背包',
    priority: 'P1',
    status: '未执行',
    remarks: '-',
  },
  {
    id: 'TC-004',
    module: '兑换商店',
    checkpoint: '兑换条件',
    title: '积分不足时提示规则说明',
    priority: 'P1',
    status: '未执行',
    remarks: '-',
  },
  {
    id: 'TC-005',
    module: '异常与边界',
    checkpoint: '网络异常',
    title: '网络中断后重试机制生效',
    priority: 'P0',
    status: '未执行',
    remarks: '弱网/断网',
  },
  {
    id: 'TC-006',
    module: '回归影响',
    checkpoint: '历史数据',
    title: '历史活动数据不受影响',
    priority: 'P2',
    status: '未执行',
    remarks: '回归验证',
  },
]

const blueprintModules: BlueprintModule[] = [
  { name: '入口与展示', count: 28, tone: 'primary' },
  { name: '奖励领取', count: 36, tone: 'success' },
  { name: '异常与边界', count: 34, tone: 'warning' },
  { name: '回归影响', count: 28, tone: 'purple' },
]

const warnings = [
  '来源材料可能包含图片或附件，V1 未读取其中语义。',
  '读取 1800 行，纳入前 800 行。',
  '5 个超长单元格已截断到 300 字符。',
]

const snapshotRows = [
  ['1', '模块', '需求点', '配置来源', '备注'],
  ['2', '活动入口', '按开服时间开放入口', 'ActivityConfig.xls', '入口图未读取'],
  ['3', '奖励领取', '每日可领取 1 次，跨日刷新', 'RewardConfig.xls', '需校验背包'],
  ['4', '兑换商店', '积分不足时不能兑换', 'ShopConfig.xls', '弱网重试'],
]

const tabs: Array<{ key: PreviewTab; label: string }> = [
  { key: 'snapshot', label: '策划案快照' },
  { key: 'blueprint', label: '用例蓝图' },
  { key: 'cases', label: '测试用例' },
  { key: 'warnings', label: 'Warnings' },
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
  const caseCount = hasReferenceSheetOptions.value ? selectedReferenceSheet.value?.caseCount : primaryReference.value?.caseCount

  return typeof caseCount === 'number' ? `约 ${caseCount} 条` : '未识别'
})
const isGenerationReady = computed(() => selectedReferenceFiles.value.length > 0 && Boolean(primaryReference.value))
const selectedReferenceSummary = computed(() => {
  if (!selectedReferenceFiles.value.length) {
    return '未选择参考案例'
  }
  if (!primaryReference.value) {
    return `已选 ${selectedReferenceFiles.value.length} 个，请指定主参考`
  }
  return `已选 ${selectedReferenceFiles.value.length} 个 · 主参考：${primaryReference.value.name}`
})
const profilePreviewFile = computed(
  () => referenceFiles.value.find((file) => file.id === profilePreviewFileId.value) ?? null,
)
const referenceMoreFile = computed(() => referenceFiles.value.find((file) => file.id === referenceMoreFileId.value) ?? null)
const metrics = computed(() => [
  { label: '策划案快照', value: '728 行', statusLabel: '已读取', statusType: 'success' as const, iconTone: 'primary' as const },
  {
    label: '参考案例',
    value: `${selectedReferenceFiles.value.length} 个`,
    statusLabel: primaryReference.value ? '含主参考' : '待选择',
    statusType: primaryReference.value ? ('success' as const) : ('warning' as const),
    iconTone: 'success' as const,
  },
  { label: '生成用例', value: '126 条', statusLabel: '本次预览', statusType: 'neutral' as const, iconTone: 'purple' as const },
  { label: 'Warnings', value: '3 条', statusLabel: '需确认', statusType: 'warning' as const, iconTone: 'warning' as const },
])

watch(
  selectedPlanningSourceId,
  () => {
    selectedPlanningSheetName.value = selectedPlanningSheetOptions.value[0]?.name ?? ''
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
  return referenceCategoryCounts.value[categoryId] ?? 0
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

function markGeneratedResultStale(reason: string): void {
  isGeneratedResultStale.value = true
  generatedResultStaleReason.value = reason
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

  selectedReferenceCategoryId.value = categoryId
  referenceSearchKeyword.value = ''
  referenceCurrentPage.value = 1

  const recommendedReference = referenceFiles.value.find(
    (file) => file.categoryId === categoryId && file.isRecommendedPrimary,
  )
  selectedReferenceIds.value = recommendedReference ? [recommendedReference.id] : []
  primaryReferenceId.value = recommendedReference?.id ?? ''
  updatePrimaryReferenceSheet(recommendedReference ?? null)
  markGeneratedResultStale(
    recommendedReference ? '参考案例分类已切换，已使用该分类的推荐主参考。' : '参考案例分类已切换，请先选择参考案例和主参考案例。',
  )
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
    markGeneratedResultStale('当前主参考案例已移出选择，请重新指定主参考案例。')
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

function createReferenceCategory(): void {
  const categoryName = newReferenceCategoryName.value.trim()
  if (!categoryName) {
    createCategoryError.value = '分类名不能为空。'
    return
  }
  if (referenceCategories.value.some((category) => category.name === categoryName)) {
    createCategoryError.value = '已存在同名参考案例分类。'
    return
  }

  const categoryId = `custom-${referenceCategories.value.length + 1}`
  referenceCategories.value.push({
    id: categoryId,
    name: categoryName,
    description: '页面态新建分类，尚未接入后端保存。',
  })
  createCategoryDialogVisible.value = false
  selectReferenceCategory(categoryId)
}

function openUploadReferenceDialog(): void {
  uploadReferenceDialogVisible.value = true
}

function openProfilePreview(file: ReferenceFile): void {
  profilePreviewFileId.value = file.id
  profilePreviewDialogVisible.value = true
}

function openReferenceMore(file: ReferenceFile): void {
  referenceMoreFileId.value = file.id
  referenceMoreDialogVisible.value = true
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

function handlePlanningSourceSaved(sourceId: string): void {
  selectedPlanningSourceId.value = sourceId
}

function togglePlanningSourceSection(): void {
  planningSourceCollapsed.value = !planningSourceCollapsed.value
}

updatePrimaryReferenceSheet(referenceFiles.value.find((file) => file.id === primaryReferenceId.value) ?? null)
</script>

<template>
  <div class="test-case-generator-page">
    <PageHeader
      breadcrumb="主页 / 用例生成"
      title="用例生成"
      description="读取策划案 Sheet，结合项目参考案例生成测试用例。"
    >
      <template #actions>
        <div class="tcg-ai-status">
          <el-icon><SuccessFilled /></el-icon>
          <span>项目 AI 已配置</span>
        </div>
        <SecondaryButton @click="openUploadReferenceDialog">
          <template #icon><Upload /></template>
          上传参考案例
        </SecondaryButton>
        <PrimaryButton :disabled="!isGenerationReady">
          <template #icon><VideoPlay /></template>
          生成用例
        </PrimaryButton>
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
            <Document v-if="item.label === '策划案快照'" />
            <FolderOpened v-else-if="item.label === '参考案例'" />
            <Collection v-else-if="item.label === '生成用例'" />
            <WarningFilled v-else />
          </template>
        </MetricCard>
      </section>

      <CollapsibleSection
        class="tcg-source-module"
        step="01"
        title="数据源"
        description="添加飞书表格、上传 Excel 或 SVN Excel 作为策划案来源"
        status-label="页面态"
        status-tone="done"
        :active="true"
        :collapsed="planningSourceCollapsed"
        content-class="tcg-source-module__content"
        @toggle="togglePlanningSourceSection"
      >
        <template #actions>
          <PrimaryButton size="sm" @click="openPlanningSourceCreate">
            <template #icon><Plus /></template>
            新增策划案来源
          </PrimaryButton>
        </template>

        <DataSourcePanel
          ref="planningSourcePanelRef"
          :store="planningSourceStore"
          toolbar-mode="hidden"
          @saved="handlePlanningSourceSaved"
        />
      </CollapsibleSection>

      <section class="tcg-panel tcg-input-module" data-test="generation-input-module">
        <div class="tcg-panel__header">
          <div>
            <h2>生成输入</h2>
            <p>选择策划案来源、Planning Sheet 和本次生成主参考</p>
          </div>
        </div>

        <div class="tcg-input-grid">
          <section class="tcg-input-block" aria-labelledby="planning-source-title">
            <div class="tcg-input-block__header">
              <h3 id="planning-source-title">策划案来源</h3>
              <span>读取快照</span>
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
            <SecondaryButton class="tcg-full-button">
              <template #icon><Refresh /></template>
              读取快照
            </SecondaryButton>
          </section>

          <section class="tcg-input-block" aria-labelledby="generation-settings-title">
            <div class="tcg-input-block__header">
              <h3 id="generation-settings-title">生成设置</h3>
              <span>{{ isGenerationReady ? '可生成' : '待选择' }}</span>
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
                  label="先在参考案例库选择参考案例"
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
                  label="当前参考案例无 Sheet"
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
              <span>{{ isGenerationReady ? 'V1 不读取图片/附件' : '请选择参考案例并指定一个主参考案例' }}</span>
            </div>
          </section>
        </div>
      </section>

      <section class="tcg-panel tcg-reference-library" data-test="reference-library">
        <div class="tcg-panel__header">
          <div>
            <h2>参考案例库</h2>
            <p>{{ selectedReferenceSummary }}</p>
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
          已选择参考案例，请指定一个主参考案例后再生成。
        </p>
        <p v-else-if="!selectedReferenceFiles.length" class="tcg-inline-warning" aria-live="polite">
          当前分类未选择参考案例，生成前必须选择参考案例并指定主参考。
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
              <el-tag type="primary" size="large">蓝图已生成</el-tag>
              <el-tag type="warning" size="large">3 条限制提示</el-tag>
              <span class="tcg-muted">主参考：{{ primaryReference?.name ?? '未选择主参考' }}</span>
            </div>
            <div class="tcg-priority-summary">
              <el-tag type="danger" size="large">P0 8</el-tag>
              <el-tag type="warning" size="large">P1 42</el-tag>
              <el-tag type="primary" size="large">P2 76</el-tag>
            </div>
          </div>

          <div v-if="isGeneratedResultStale" class="tcg-stale-notice" role="status" aria-live="polite">
            <el-icon><WarningFilled /></el-icon>
            <span>{{ generatedResultStaleReason }}</span>
          </div>

          <div v-if="activeTab === 'cases'" class="tcg-tab-panel">
            <el-table :data="generatedCases" class="tcg-case-table">
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
          </div>

          <div v-else-if="activeTab === 'snapshot'" class="tcg-tab-panel">
            <div class="tcg-snapshot-grid">
              <div v-for="row in snapshotRows" :key="row.join('-')" class="tcg-snapshot-row">
                <span v-for="cell in row" :key="cell">{{ cell }}</span>
              </div>
            </div>
          </div>

          <div v-else-if="activeTab === 'blueprint'" class="tcg-tab-panel">
            <div class="tcg-blueprint-list">
              <article v-for="item in blueprintModules" :key="item.name" class="tcg-blueprint-card">
                <div class="tcg-blueprint-card__icon" :class="`is-${item.tone}`">
                  <DataAnalysis />
                </div>
                <div>
                  <strong>{{ item.name }}</strong>
                  <span>约 {{ item.count }} 条</span>
                </div>
              </article>
            </div>
          </div>

          <div v-else class="tcg-tab-panel">
            <ul class="tcg-warning-list">
              <li v-for="warning in warnings" :key="warning">
                <el-icon><WarningFilled /></el-icon>
                <span>{{ warning }}</span>
              </li>
            </ul>
          </div>

          <div class="tcg-blueprint-summary">
            <div class="tcg-section-title">
              <h2>用例蓝图</h2>
              <span>只读预览</span>
            </div>
            <div class="tcg-blueprint-modules">
              <article v-for="item in blueprintModules" :key="item.name">
                <div class="tcg-module-icon" :class="`is-${item.tone}`">
                  <DataAnalysis />
                </div>
                <div>
                  <strong>{{ item.name }}</strong>
                  <span>约 {{ item.count }} 条</span>
                </div>
              </article>
            </div>
          </div>

          <div class="tcg-warning-strip">
            <div class="tcg-section-title">
              <h2>Warnings</h2>
              <span>本次生成限制</span>
            </div>
            <div class="tcg-warning-strip__items">
              <span v-for="warning in warnings.slice(0, 2)" :key="warning">
                <el-icon><WarningFilled /></el-icon>
                {{ warning }}
              </span>
            </div>
          </div>

          <div class="tcg-export-bar">
            <span>本次结果仅保留在当前页面预览，不保存生成历史。</span>
            <SecondaryButton>
              <template #icon><Download /></template>
              导出 Excel
            </SecondaryButton>
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
          <PrimaryButton size="sm" @click="createReferenceCategory">创建分类</PrimaryButton>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="uploadReferenceDialogVisible" title="上传参考案例" width="460px">
      <div class="tcg-static-dialog">
        <strong>上传到当前分类：{{ currentReferenceCategory?.name ?? '未选择分类' }}</strong>
        <p>静态页仅展示入口，不读取文件或保存到后端。后续接入时支持 Excel、Markdown 和 TXT 参考案例。</p>
      </div>
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
        <p>以下管理员动作仅作为静态页面态展示，当前未接入后端权限或持久化。</p>
        <div class="tcg-static-actions">
          <button type="button" disabled>重命名分类</button>
          <button type="button" disabled>删除文件</button>
          <button type="button" disabled>设为推荐主参考</button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.test-case-generator-page {
  --tcg-panel-bg: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(250, 252, 255, 0.94));
  --tcg-panel-border: rgba(203, 213, 225, 0.72);
  --tcg-panel-shadow:
    0 10px 26px rgba(15, 23, 42, 0.045),
    inset 0 1px 0 rgba(255, 255, 255, 0.86);
  --tcg-panel-shadow-strong:
    0 14px 34px rgba(15, 23, 42, 0.065),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
  --tcg-row-hover: #f7faff;
  --tcg-focus-ring: rgba(15, 98, 254, 0.18);

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
  gap: 12px;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 18px 28px 40px;
  scrollbar-gutter: stable;
}

.tcg-content > :deep(.ui-collapsible-section) {
  flex: 0 0 auto;
}

.tcg-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.tcg-metrics :deep(.ui-metric-card) {
  border-color: var(--tcg-panel-border);
  background: var(--tcg-panel-bg);
  box-shadow: var(--tcg-panel-shadow);
  min-height: 78px;
  padding: 12px 18px;
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
  width: 40px;
  height: 40px;
}

.tcg-metrics :deep(.ui-metric-card__icon svg) {
  width: 20px;
  height: 20px;
}

.tcg-metrics :deep(.ui-metric-card__value) {
  margin: 4px 0;
  font-size: 24px;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
}

.tcg-source-module {
  border-radius: 12px;
}

.tcg-source-module :deep(.ui-collapsible-section__inner) {
  border-color: var(--tcg-panel-border);
  background: var(--tcg-panel-bg);
  padding: 12px 16px;
  box-shadow: var(--tcg-panel-shadow) !important;
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
  border: 1px solid var(--tcg-panel-border);
  border-radius: 12px;
  background: var(--tcg-panel-bg);
  box-shadow: var(--tcg-panel-shadow);
}

.tcg-panel {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 8px;
  border-bottom: 1px solid var(--color-border-light);
  padding: 11px 14px;
}

.tcg-panel:last-child {
  border-bottom: 0;
}

.tcg-panel__header,
.tcg-section-title,
.tcg-preview__toolbar,
.tcg-export-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.tcg-panel__header h2,
.tcg-section-title h2 {
  margin: 0;
  color: var(--color-text-main);
  font-size: 14px;
  font-weight: 750;
  letter-spacing: 0;
  line-height: 1.25;
  text-wrap: balance;
}

.tcg-panel__header p {
  margin: 3px 0 0;
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
  gap: 10px;
  border: 1px solid var(--tcg-panel-border);
  border-radius: 12px;
  border-bottom: 1px solid var(--tcg-panel-border);
  background: var(--tcg-panel-bg);
  box-shadow: var(--tcg-panel-shadow);
  padding: 12px 14px;
}

.tcg-input-module .tcg-panel__header,
.tcg-reference-library .tcg-panel__header {
  align-items: flex-start;
}

.tcg-input-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 14px;
}

.tcg-input-block {
  display: grid;
  min-width: 0;
  align-content: start;
  gap: 8px;
}

.tcg-input-block + .tcg-input-block {
  border-left: 1px solid var(--color-border-light);
  padding-left: 14px;
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
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0;
  line-height: 1.25;
}

.tcg-input-block__header span {
  flex: 0 0 auto;
  border-radius: var(--radius-pill);
  background: #eef4ff;
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
  padding-bottom: 2px;
  scrollbar-width: thin;
  scrollbar-gutter: stable;
}

.tcg-reference-category {
  display: inline-flex;
  min-height: 32px;
  flex: 0 0 auto;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: #ffffff;
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
  background: var(--color-primary-soft);
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
  grid-template-columns: minmax(280px, 1fr) minmax(360px, 440px) minmax(180px, 220px);
  align-items: center;
  gap: 10px;
}

.tcg-reference-search input,
.tcg-reference-sort select,
.tcg-dialog-field input {
  width: 100%;
  min-height: 34px;
  border: 1px solid var(--color-border);
  border-radius: var(--ui-control-radius);
  background: rgba(255, 255, 255, 0.94);
  color: var(--color-text-main);
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  padding: 0 10px;
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
  border: 1px solid var(--color-border);
  border-radius: var(--ui-control-radius);
  background: #ffffff;
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
  background: var(--color-primary-soft);
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
  border: 1px solid rgba(255, 122, 26, 0.16);
  border-radius: 8px;
  background: var(--color-warning-soft);
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
  gap: 6px;
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
  gap: 10px;
  align-items: center;
  border: 1px solid var(--color-border-light);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.96);
  color: inherit;
  font: inherit;
  padding: 7px 9px;
  text-align: left;
  transition:
    background-color 160ms cubic-bezier(0.2, 0, 0, 1),
    border-color 160ms cubic-bezier(0.2, 0, 0, 1),
    box-shadow 160ms cubic-bezier(0.2, 0, 0, 1);
}

.tcg-reference-item:hover,
.tcg-reference-item.is-selected {
  border-color: #c9d8ee;
  background: var(--tcg-row-hover);
}

.tcg-reference-item.is-primary {
  border-color: rgba(15, 98, 254, 0.45);
  background: linear-gradient(180deg, rgba(239, 246, 255, 0.9), rgba(255, 255, 255, 0.96));
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
  width: 28px;
  height: 28px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: var(--color-primary);
  background: var(--color-primary-soft);
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
  margin: 3px 0 0;
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
  margin-top: 4px;
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
  border-radius: 8px;
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

.tcg-preview__tabs {
  position: sticky;
  top: 0;
  z-index: 2;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border-bottom: 1px solid var(--color-border);
  border-radius: 12px 12px 0 0;
  background: #f8fbff;
}

.tcg-preview__tabs button {
  position: relative;
  min-width: 0;
  min-height: 42px;
  border: 0;
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
  right: 28px;
  bottom: 0;
  left: 28px;
  height: 2px;
  border-radius: var(--radius-pill);
  background: transparent;
  content: '';
}

.tcg-preview__tabs button.is-active {
  color: var(--color-primary);
  background: #ffffff;
}

.tcg-preview__tabs button.is-active::after {
  background: var(--color-primary);
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
  background: rgba(255, 255, 255, 0.58);
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

.tcg-status-strip,
.tcg-priority-summary {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.tcg-tab-panel {
  padding: 12px 16px 14px;
}

.tcg-case-table {
  width: 100%;
  font-variant-numeric: tabular-nums;
}

.tcg-case-table :deep(.el-table) {
  font-size: 12px;
}

.tcg-case-table :deep(th.el-table__cell) {
  height: 36px;
  background: #f5f8fc !important;
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

.tcg-row-more {
  color: #64748b;
}

.tcg-snapshot-grid {
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.tcg-snapshot-row {
  display: grid;
  grid-template-columns: 56px repeat(4, minmax(0, 1fr));
}

.tcg-snapshot-row:first-child {
  background: var(--color-bg-page);
  color: #64748b;
  font-weight: 750;
}

.tcg-snapshot-row span {
  min-height: 42px;
  border-right: 1px solid var(--color-border-light);
  border-bottom: 1px solid var(--color-border-light);
  color: var(--color-text-secondary);
  font-size: 13px;
  padding: 10px 12px;
}

.tcg-blueprint-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.tcg-blueprint-card,
.tcg-blueprint-modules article {
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.96);
  padding: 12px;
}

.tcg-blueprint-card strong,
.tcg-blueprint-modules strong {
  display: block;
  color: var(--color-text-main);
  font-size: 14px;
  font-weight: 750;
}

.tcg-blueprint-card span,
.tcg-blueprint-modules span {
  display: block;
  margin-top: 3px;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 650;
}

.tcg-blueprint-card__icon,
.tcg-module-icon {
  display: inline-flex;
  width: 40px;
  height: 40px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
}

.tcg-blueprint-summary,
.tcg-warning-strip,
.tcg-export-bar {
  border-top: 1px solid var(--color-border-light);
  padding: 12px 16px;
}

.tcg-blueprint-modules {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
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
  border: 1px solid rgba(255, 122, 26, 0.16);
  border-radius: 10px;
  background: var(--color-warning-soft);
  list-style: none;
  padding: 12px 14px;
}

.tcg-warning-strip__items {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
  border-radius: 10px;
  background: var(--color-warning-soft);
  padding: 10px 12px;
}

.tcg-export-bar {
  color: var(--color-text-muted);
  font-size: 13px;
  font-weight: 650;
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

  .tcg-blueprint-modules {
    grid-template-columns: repeat(2, minmax(0, 1fr));
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

  .tcg-preview__tabs {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
