<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import {
  checkFeishuSourcePermission,
  pickLocalSourcePath,
  sendFeishuSourceAuthorizationCard,
  uploadSourceFile,
} from '../../api/workbench'
import {
  ensureTrailingSlash,
  fetchSvnCredential,
  getDefaultSvnCredentialTestDirUrl,
  isHttpDirUrl,
  parseSvnHost,
  type SvnCredentialItem,
  listSvnCredentialHosts,
} from '../../api/svn'
import SvnPickerDialog from './SvnPickerDialog.vue'
import SvnCredentialDialog from './SvnCredentialDialog.vue'
import EmptyState from '../shell/EmptyState.vue'
import { useWorkbenchStore } from '../../store/workbench'
import type { SourceManagementStoreLike } from '../../types/panelStores'
import type { DataSource, FeishuAuthorizationStatus, SourceType } from '../../types/workbench'
import { extractSourceBasename } from '../../utils/sourcePathReplacement'
import { DEFAULT_SOURCE_TYPE, getSourceTypeLabel, SOURCE_TYPE_OPTIONS } from '../../utils/workbenchMeta'

export interface DataSourceDialogPrefill {
  id?: string
  type?: SourceType
  pathOrUrl?: string
  token?: string
}

const props = withDefaults(
  defineProps<{
    store?: SourceManagementStoreLike
    sourceIssues?: Record<string, string>
    variant?: 'workbench' | 'fixed-rules'
    toolbarMode?: 'embedded' | 'hidden'
  }>(),
  {
    sourceIssues: () => ({}),
    variant: 'workbench',
    toolbarMode: 'embedded',
  },
)

const emit = defineEmits<{
  saved: [sourceId: string]
  changed: []
}>()

const defaultStore = useWorkbenchStore()
const store = props.store ?? defaultStore
const sourceIssueMap = computed(() => props.sourceIssues ?? {})
const isFixedRulesVariant = computed(() => props.variant === 'fixed-rules')

const dialogVisible = ref(false)
const editingId = ref<string | null>(null)
const isPicking = ref(false)
const isUploading = ref(false)
const uploadInputRef = ref<HTMLInputElement | null>(null)
const sourceIdTouched = ref(false)

const draft = reactive<DataSource>({
  id: '',
  type: DEFAULT_SOURCE_TYPE,
  pathOrUrl: '',
  token: '',
})

const draftErrors = reactive({
  id: '',
  pathOrUrl: '',
})

const localSource = computed(() => draft.type === 'local_excel')
const isFeishuSource = computed(() => draft.type === 'feishu')
const isSvnSource = computed(() => draft.type === 'svn')
const isUnsupportedCsvSource = computed(() => draft.type === 'local_csv')
const feishuAuthState = ref<'idle' | 'checking' | 'requesting'>('idle')
const feishuAuthStatus = ref<FeishuAuthorizationStatus | null>(null)
const feishuAuthMessage = ref('')
const feishuPermissionPollTimer = ref<number | null>(null)
const feishuPermissionPollStartedAt = ref<number | null>(null)
const feishuPermissionAutoCheckTimer = ref<number | null>(null)
const activeFeishuPermissionRequestKey = ref('')
const lastFeishuAutoCheckKey = ref('')
const savedFeishuStatusMap = reactive<Record<string, FeishuAuthorizationStatus | undefined>>({})
const savedFeishuStatusLoadingMap = reactive<Record<string, boolean>>({})
const savedFeishuStatusErrorMap = reactive<Record<string, string>>({})
const FEISHU_PERMISSION_POLL_INTERVAL_MS = 3000
const FEISHU_PERMISSION_POLL_TIMEOUT_MS = 10 * 60 * 1000
const FEISHU_PERMISSION_AUTO_CHECK_DEBOUNCE_MS = 500

// SVN 子模式：远端 URL（默认）或本地工作副本路径
const svnSubMode = ref<'remote' | 'working_copy'>('remote')

const svnPickerVisible = ref(false)
const svnCredentialDialogVisible = ref(false)
const svnCredentialDialogHost = ref('')
const svnCredentialDialogDefaultTestDirUrl = ref('')
const svnCredentialDialogDefaultUsername = ref('')
const svnCredentialDialogDefaultPassword = ref('')
const svnPickerDirUrl = ref('')
const svnCredentialItems = ref<SvnCredentialItem[]>([])
const svnCredentialLoadState = ref<'loading' | 'ready' | 'error'>('loading')

const panelCopy = computed(() => ({
  emptyText: isFixedRulesVariant.value ? '暂无数据源。' : '还没有录入数据源。',
  localExcelHelper: '远程访问时请用上传文件；服务器本机或共享盘路径可手动输入或选择。',
}))
const canPickLocalFile = computed(
  () =>
    localSource.value &&
    !isPicking.value &&
    (draft.type === 'local_excel' || draft.id.trim().length > 0),
)
const canUploadLocalFile = computed(() => localSource.value && !isUploading.value)
const canBrowseSvnDirectory = computed(
  () =>
    isSvnSource.value &&
    svnSubMode.value === 'remote' &&
    isHttpDirUrl(draft.pathOrUrl?.trim() ?? ''),
)
const savedSvnDirectoryOptions = computed(() => store.svnPathReplacementPresets ?? [])
const savedFeishuSourceSignature = computed(() =>
  store.sources
    .filter((source) => source.type === 'feishu')
    .map((source) => `${source.id}:${getSourceLocator(source)}`)
    .join('|'),
)
const feishuAuthStatusLabelMap: Record<FeishuAuthorizationStatus, string> = {
  authorized: '已授权',
  pending_authorization: '待授权',
  authorization_sent: '已发送授权请求',
  authorization_success: '授权成功',
  authorization_failed: '授权失败',
  invalid_url: '链接无效',
  app_permission_missing: '应用权限不足',
  document_permission_denied: '文档权限不足',
  not_found: '表格不存在',
  bot_not_configured: '机器人未配置',
  callback_not_configured: '回调地址未配置',
  send_failed: '发送失败',
}
const feishuAuthStatusLabel = computed(() => {
  if (feishuAuthState.value === 'checking') return '检测中'
  if (feishuAuthState.value === 'requesting') return '授权请求发送中'
  if (!feishuAuthStatus.value && hasFeishuUrl.value) return '待授权'
  if (!feishuAuthStatus.value) return '待检测'
  return feishuAuthStatusLabelMap[feishuAuthStatus.value] ?? '状态未知'
})
const feishuAuthStatusTone = computed<'success' | 'info' | 'warning' | 'danger'>(() => {
  if (feishuAuthState.value === 'checking' || feishuAuthState.value === 'requesting') {
    return 'info'
  }
  if (feishuAuthStatus.value === 'authorized' || feishuAuthStatus.value === 'authorization_success') {
    return 'success'
  }
  if (
    feishuAuthStatus.value === 'authorization_failed' ||
    feishuAuthStatus.value === 'invalid_url' ||
    feishuAuthStatus.value === 'not_found' ||
    feishuAuthStatus.value === 'send_failed'
  ) {
    return 'danger'
  }
  if (feishuAuthStatus.value) {
    return 'warning'
  }
  return 'info'
})
const feishuAuthStatusDescription = computed(() => {
  if (feishuAuthMessage.value) return feishuAuthMessage.value
  if (feishuAuthStatus.value === 'authorized' || feishuAuthStatus.value === 'authorization_success') {
    return '飞书电子表格已授权，可保存后进入变量配置。'
  }
  if (feishuAuthStatus.value === 'authorization_sent') {
    return '授权请求已发送到群，正在等待有权限的成员完成授权。'
  }
  if (
    feishuAuthStatus.value === 'pending_authorization' ||
    feishuAuthStatus.value === 'document_permission_denied'
  ) {
    return '机器人暂无该表格权限，请发送授权请求到群。'
  }
  if (!feishuAuthStatus.value && hasFeishuUrl.value) {
    if (!draft.id.trim()) {
      return '请先填写数据源标识，系统会自动检测飞书表格读取权限。'
    }
    if (!isValidSourceIdFormat(draft.id.trim()) || findDuplicateSourceId(draft.id.trim())) {
      return '请先修正数据源标识，系统会自动检测飞书表格读取权限。'
    }
    return '正在确认机器人是否已具备该表格读取权限。'
  }
  return '请先检测飞书电子表格读取权限。'
})
const isFeishuAuthBusy = computed(
  () => feishuAuthState.value === 'checking' || feishuAuthState.value === 'requesting',
)
const hasFeishuUrl = computed(() => Boolean(draft.pathOrUrl?.trim()))
const canCheckFeishuPermission = computed(
  () => isFeishuPermissionRequestReady() && !isFeishuAuthBusy.value,
)
const showFeishuPermissionCheck = computed(
  () => hasFeishuUrl.value && feishuAuthStatus.value !== 'authorization_sent' && !isFeishuAuthorized.value,
)
const canSendFeishuAuthRequest = computed(
  () =>
    !isFeishuAuthBusy.value &&
    hasFeishuUrl.value &&
    (
      feishuAuthStatus.value === 'pending_authorization' ||
      feishuAuthStatus.value === 'document_permission_denied'
    ),
)
const canRecheckFeishuPermission = computed(
  () =>
    !isFeishuAuthBusy.value &&
    hasFeishuUrl.value &&
    feishuAuthStatus.value === 'authorization_sent',
)
const isFeishuAuthorized = computed(
  () => feishuAuthStatus.value === 'authorized' || feishuAuthStatus.value === 'authorization_success',
)
const canSaveSource = computed(() => {
  const path = draft.pathOrUrl?.trim() ?? ''
  return (
    !isUnsupportedCsvSource.value &&
    !isPicking.value &&
    draft.id.trim().length > 0 &&
    path.length > 0 &&
    validatePathByType(path) &&
    (!isFeishuSource.value || isFeishuAuthorized.value)
  )
})

function resetDraft(): void {
  draft.id = ''
  draft.type = DEFAULT_SOURCE_TYPE
  draft.pathOrUrl = ''
  draft.token = ''
  resetFeishuAuthStatus()
  sourceIdTouched.value = false
  clearDraftErrors()
}

function resetFeishuAuthStatus(): void {
  stopFeishuPermissionPolling()
  clearFeishuPermissionAutoCheck()
  activeFeishuPermissionRequestKey.value = ''
  lastFeishuAutoCheckKey.value = ''
  feishuAuthState.value = 'idle'
  feishuAuthStatus.value = null
  feishuAuthMessage.value = ''
}

function clearDraftErrors(): void {
  draftErrors.id = ''
  draftErrors.pathOrUrl = ''
}

function openCreateDialog(prefill?: DataSourceDialogPrefill): void {
  editingId.value = null
  resetDraft()
  if (prefill) {
    draft.id = prefill.id?.trim() ?? ''
    draft.type = prefill.type ?? DEFAULT_SOURCE_TYPE
    draft.pathOrUrl = prefill.pathOrUrl?.trim() ?? ''
    draft.token = prefill.token?.trim() ?? ''
    sourceIdTouched.value = Boolean(draft.id)
  }
  svnSubMode.value = 'remote'
  syncDraftIdError()
  dialogVisible.value = true
  if (draft.type === 'feishu') {
    applySavedFeishuStatusForDraft()
    scheduleFeishuPermissionAutoCheck({ immediate: true })
  }
  void refreshSvnCredentialItems()
}

function openEditDialog(source: DataSource): void {
  editingId.value = source.id
  draft.id = source.id
  draft.type = source.type
  draft.pathOrUrl = source.pathOrUrl ?? source.path ?? source.url ?? ''
  draft.token = source.token ?? ''
  resetFeishuAuthStatus()
  if (source.type === 'svn') {
    svnSubMode.value = isRemoteSvnSource(source) ? 'remote' : 'working_copy'
  } else {
    svnSubMode.value = 'remote'
  }
  sourceIdTouched.value = true
  clearDraftErrors()
  dialogVisible.value = true
  if (source.type === 'feishu') {
    applySavedFeishuStatusForDraft(source)
    scheduleFeishuPermissionAutoCheck({ immediate: true })
  }
  void refreshSvnCredentialItems()
}

function removeSource(sourceId: string): void {
  store.removeSource(sourceId)
  emit('changed')
  ElMessage.success('数据源已移除。')
}

function handleSourceTypeChange(nextType: SourceType): void {
  draft.type = nextType
  draftErrors.pathOrUrl = ''

  if (nextType === 'local_excel') {
    draft.pathOrUrl = ''
    draft.token = ''
    resetFeishuAuthStatus()
    return
  }

  if (nextType === 'svn') {
    svnSubMode.value = 'remote'
    draft.pathOrUrl = ''
    draft.token = ''
    resetFeishuAuthStatus()
    return
  }

  draft.pathOrUrl = draft.pathOrUrl?.trim() ?? ''
  if (nextType === 'feishu') {
    draft.token = ''
    resetFeishuAuthStatus()
    scheduleFeishuPermissionAutoCheck()
  }
}

function handlePathInput(): void {
  draftErrors.pathOrUrl = ''
  if (isFeishuSource.value) {
    resetFeishuAuthStatus()
    scheduleFeishuPermissionAutoCheck()
  }
}

function handleSvnSubModeChange(value: 'remote' | 'working_copy'): void {
  svnSubMode.value = value
  draft.pathOrUrl = ''
  draftErrors.pathOrUrl = ''
}

type SavedSvnDirectorySuggestion = {
  value: string
}

function querySavedSvnDirectories(
  queryString: string,
  callback: (suggestions: SavedSvnDirectorySuggestion[]) => void,
): void {
  const normalizedQuery = queryString.trim().toLowerCase()
  const matchedDirectories = normalizedQuery
    ? savedSvnDirectoryOptions.value.filter((directoryUrl) =>
        directoryUrl.toLowerCase().includes(normalizedQuery),
      )
    : savedSvnDirectoryOptions.value

  callback(matchedDirectories.map((directoryUrl) => ({ value: directoryUrl })))
}

function handleSavedSvnDirectorySelect(item: SavedSvnDirectorySuggestion): void {
  draft.pathOrUrl = item.value
  draftErrors.pathOrUrl = ''
}

function validatePathByType(path: string): boolean {
  const lowerPath = path.toLowerCase()

  if (draft.type === 'local_excel') {
    return lowerPath.endsWith('.xlsx') || lowerPath.endsWith('.xls')
  }

  if (draft.type === 'svn' && svnSubMode.value === 'remote') {
    // 远端 URL 必须是 http(s) 且指向 .xls/.xlsx 单文件。
    if (!isHttpDirUrl(path)) {
      return false
    }
    if (path.endsWith('/')) {
      return false
    }
    return lowerPath.endsWith('.xls') || lowerPath.endsWith('.xlsx')
  }

  return true
}

function isValidSourceIdFormat(sourceId: string): boolean {
  return /^[A-Za-z0-9_]+$/.test(sourceId)
}

function findDuplicateSourceId(sourceId: string): DataSource | undefined {
  return store.sources.find((source) => source.id === sourceId && source.id !== editingId.value)
}

function sanitizeSourceIdFromLocator(locator: string): string {
  const basename = extractSourceBasename(locator)
  const withoutExtension = basename.replace(/\.xlsx?$/i, '')
  const normalized = withoutExtension
    .replace(/[^A-Za-z0-9_]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '')
  return normalized || 'source'
}

function syncDraftIdError(options?: { autoGenerated?: boolean }): void {
  const sourceId = draft.id.trim()
  if (!sourceId) {
    draftErrors.id = ''
    return
  }
  if (!isValidSourceIdFormat(sourceId)) {
    draftErrors.id = '数据源标识仅允许字母、数字与下划线。'
    return
  }
  if (findDuplicateSourceId(sourceId)) {
    draftErrors.id = options?.autoGenerated
      ? '根据文件名自动生成的数据源标识已存在，请手动修改后再保存。'
      : '数据源标识已存在，请修改后再保存。'
    return
  }
  draftErrors.id = ''
}

function autofillSourceIdFromLocator(locator: string): void {
  if (sourceIdTouched.value) {
    syncDraftIdError()
    return
  }
  draft.id = sanitizeSourceIdFromLocator(locator)
  syncDraftIdError({ autoGenerated: true })
}

function handleSourceIdInput(value: string): void {
  draft.id = value
  sourceIdTouched.value = true
  syncDraftIdError()
  if (isFeishuSource.value) {
    resetFeishuAuthStatus()
    scheduleFeishuPermissionAutoCheck()
  }
}

function validateDraft(): boolean {
  clearDraftErrors()

  const sourceId = draft.id.trim()
  if (!sourceId) {
    draftErrors.id = '请输入数据源标识。'
  } else if (!isValidSourceIdFormat(sourceId)) {
    draftErrors.id = '数据源标识仅允许字母、数字与下划线。'
  } else if (findDuplicateSourceId(sourceId)) {
    draftErrors.id = '数据源标识已存在，请修改后再保存。'
  }

  if (!draft.pathOrUrl?.trim()) {
    draftErrors.pathOrUrl = localSource.value
      ? '请选择或输入本地文件路径。'
      : isFeishuSource.value
        ? '请输入飞书电子表格 URL。'
        : '请输入链接或目录路径。'
  } else if (isUnsupportedCsvSource.value) {
    draftErrors.pathOrUrl = 'CSV 数据源已不再支持，请删除后改用 Excel 或 SVN Excel。'
  } else if (!validatePathByType(draft.pathOrUrl.trim())) {
    draftErrors.pathOrUrl = '本地 Excel 数据源仅支持 .xls 或 .xlsx 文件。'
  } else if (isFeishuSource.value && !isFeishuAuthorized.value) {
    draftErrors.pathOrUrl = '请先完成飞书表格授权检测后再保存数据源。'
  }

  return !draftErrors.id && !draftErrors.pathOrUrl
}

async function saveSource(): Promise<void> {
  if (!validateDraft()) {
    ElMessage.warning('请先完善必填项后再保存数据源。')
    return
  }

  const sourceId = draft.id.trim()
  const isSavingFeishuSource = draft.type === 'feishu'
  store.upsertSource(
    {
      id: sourceId,
      type: draft.type,
      pathOrUrl: draft.pathOrUrl?.trim(),
      token: draft.type === 'feishu' ? undefined : draft.token?.trim(),
    },
    editingId.value ?? undefined,
  )
  if (isSavingFeishuSource) {
    await refreshSavedFeishuStatus(sourceId)
  }
  dialogVisible.value = false
  emit('saved', sourceId)
  emit('changed')
  ElMessage.success(editingId.value ? '数据源已更新。' : '数据源已添加。')
}

async function refreshSavedFeishuStatus(
  sourceId: string,
  options?: { silent?: boolean },
): Promise<void> {
  const source = store.sources.find((item) => item.id === sourceId && item.type === 'feishu')
  const sheetUrl = source ? getSourceLocator(source) : ''
  if (!source || !sheetUrl) {
    return
  }
  savedFeishuStatusLoadingMap[sourceId] = true
  savedFeishuStatusErrorMap[sourceId] = ''
  try {
    const response = await checkFeishuSourcePermission({
      source_id: sourceId,
      sheet_url: sheetUrl,
    })
    savedFeishuStatusMap[sourceId] = response.data.status
    if (
      (response.data.status === 'authorized' || response.data.status === 'authorization_success') &&
      response.data.sheet_url?.trim() &&
      response.data.sheet_url.trim() !== sheetUrl
    ) {
      store.upsertSource({ ...source, pathOrUrl: response.data.sheet_url.trim() }, source.id)
    }
  } catch (error) {
    const message = getFeishuErrorMessage(error, '飞书授权状态读取失败，请稍后重试。')
    savedFeishuStatusErrorMap[sourceId] = message
    if (!options?.silent) {
      ElMessage.error(message)
    }
  } finally {
    savedFeishuStatusLoadingMap[sourceId] = false
  }
}

async function refreshSavedFeishuSourcesStatus(): Promise<void> {
  const feishuSources = store.sources.filter((source) => source.type === 'feishu')
  await Promise.allSettled(
    feishuSources.map((source) => refreshSavedFeishuStatus(source.id, { silent: true })),
  )
}

function getSourceLocator(source: DataSource): string {
  return (source.pathOrUrl ?? source.path ?? source.url ?? '').trim()
}

function getFeishuSourceMetadata(sourceId: string) {
  return store.sourceMetadataMap?.[sourceId] ?? null
}

function getSavedFeishuStatus(sourceId: string): FeishuAuthorizationStatus | undefined {
  return savedFeishuStatusMap[sourceId]
}

function isSavedFeishuStatusLoading(sourceId: string): boolean {
  return Boolean(savedFeishuStatusLoadingMap[sourceId])
}

function hasSavedFeishuStatusError(sourceId: string): boolean {
  return Boolean(savedFeishuStatusErrorMap[sourceId])
}

function isFeishuSourceReady(source: DataSource): boolean {
  const metadata = getFeishuSourceMetadata(source.id)
  const status = getSavedFeishuStatus(source.id)
  return (
    status === 'authorized' ||
    status === 'authorization_success' ||
    metadata?.authorization_status === 'authorized' ||
    Boolean(metadata?.sheets?.length)
  )
}

function getStatusTone(source: DataSource): 'success' | 'warning' | 'info' {
  if (sourceIssueMap.value[source.id]) {
    return 'warning'
  }

  if (source.type === 'local_csv') {
    return 'warning'
  }

  if (source.type === 'feishu') {
    if (isSavedFeishuStatusLoading(source.id)) {
      return 'info'
    }
    const savedStatus = getSavedFeishuStatus(source.id)
    if (savedStatus === 'authorized' || savedStatus === 'authorization_success') {
      return 'success'
    }
    if (
      savedStatus === 'authorization_failed' ||
      savedStatus === 'invalid_url' ||
      savedStatus === 'not_found' ||
      savedStatus === 'send_failed'
    ) {
      return 'warning'
    }
    return isFeishuSourceReady(source) ? 'success' : 'warning'
  }

  if (source.type === 'svn') {
    if (!isRemoteSvnSource(source)) {
      return 'success'
    }
    if (svnCredentialLoadState.value === 'loading') {
      return 'info'
    }
    if (svnCredentialLoadState.value === 'error') {
      return 'info'
    }
    if (!hasCredentialFor(source)) {
      return 'warning'
    }
    return 'success'
  }

  return 'success'
}

function getStatusLabel(source: DataSource): string {
  if (sourceIssueMap.value[source.id]) {
    return '路径失效'
  }
  if (source.type === 'local_csv') {
    return '不支持'
  }
  if (source.type === 'feishu') {
    if (isFeishuSourceReady(source)) {
      return '已授权'
    }
    if (isSavedFeishuStatusLoading(source.id)) {
      return '检测中'
    }
    if (hasSavedFeishuStatusError(source.id)) {
      return '读取失败'
    }
    const savedStatus = getSavedFeishuStatus(source.id)
    if (savedStatus) {
      return feishuAuthStatusLabelMap[savedStatus] ?? '待检测'
    }
    return '待检测'
  }

  if (source.type === 'svn') {
    if (!isRemoteSvnSource(source)) {
      return '已就绪'
    }
    if (svnCredentialLoadState.value === 'loading') {
      return '检测中'
    }
    if (svnCredentialLoadState.value === 'error') {
      return '状态未知'
    }
    if (!hasCredentialFor(source)) {
      return '待授权'
    }
    return '已就绪'
  }

  return '已就绪'
}

function getPathLabel(sourceType: SourceType): string {
  if (sourceType === 'feishu') {
    return '飞书电子表格 URL'
  }

  if (sourceType === 'svn') {
    return svnSubMode.value === 'remote' ? 'SVN 文件 URL' : 'SVN 工作副本路径'
  }

  return '本地路径'
}

function isRemoteSvnSource(source: DataSource): boolean {
  const locator = (source.pathOrUrl ?? source.path ?? source.url ?? '').trim()
  return /^https?:\/\//i.test(locator)
}

function hasCredentialFor(source: DataSource): boolean {
  const host = parseSvnHost(source.pathOrUrl ?? source.url ?? '')
  if (!host) {
    return false
  }
  return svnCredentialItems.value.some((item) => item.host === host)
}

async function refreshSvnCredentialItems(): Promise<void> {
  svnCredentialLoadState.value = 'loading'
  try {
    const response = await listSvnCredentialHosts()
    svnCredentialItems.value = response.data.items
    svnCredentialLoadState.value = 'ready'
  } catch {
    svnCredentialItems.value = []
    svnCredentialLoadState.value = 'error'
    // 凭据列表加载失败不阻塞主流程，但状态需回退为“状态未知”，避免误报“待授权”。
  }
}

function openSvnPicker(): void {
  if (!canBrowseSvnDirectory.value) {
    ElMessage.warning('请先输入合法的 SVN 目录 URL（http/https，以 / 结尾）。')
    return
  }
  svnPickerDirUrl.value = ensureTrailingSlash(draft.pathOrUrl ?? '')
  svnPickerVisible.value = true
}

function handleSvnPicked(fileUrl: string): void {
  draft.pathOrUrl = fileUrl
  draftErrors.pathOrUrl = ''
  autofillSourceIdFromLocator(fileUrl)
  ElMessage.success('已选择 SVN 文件。')
}

function handleCredentialRequiredFromPicker(host: string): void {
  svnPickerVisible.value = false
  void openSvnCredentialDialog(host)
}

async function openSvnCredentialDialog(host: string): Promise<void> {
  const normalizedHost = host.trim().toLowerCase()
  const matchedCredential = svnCredentialItems.value.find((item) => item.host === normalizedHost)
  const fallbackTestDirUrl =
    matchedCredential?.test_dir_url?.trim() || getDefaultSvnCredentialTestDirUrl(normalizedHost)

  svnCredentialDialogHost.value = normalizedHost
  svnCredentialDialogDefaultUsername.value = matchedCredential?.username ?? ''
  svnCredentialDialogDefaultPassword.value = ''
  svnCredentialDialogDefaultTestDirUrl.value = fallbackTestDirUrl

  try {
    const response = await fetchSvnCredential(normalizedHost)
    if (response?.data) {
      svnCredentialDialogDefaultUsername.value = response.data.username
      svnCredentialDialogDefaultPassword.value = response.data.password
      svnCredentialDialogDefaultTestDirUrl.value =
        response.data.test_dir_url?.trim() || fallbackTestDirUrl
    }
  } catch (error) {
    const message =
      error instanceof Error ? error.message : '读取已保存的 SVN 凭据失败，已回退到默认值。'
    ElMessage.warning(message)
  }

  svnCredentialDialogVisible.value = true
}

async function handleSvnCredentialSaved(host: string): Promise<void> {
  await refreshSvnCredentialItems()
  ElMessage.success(`已保存 ${host} 的 SVN 凭据。`)
  // 凭据保存完成后自动重新打开 picker 触发一次浏览。
  if (canBrowseSvnDirectory.value) {
    openSvnPicker()
  }
}

function handleManageSvnCredential(): void {
  const dirUrl = ensureTrailingSlash(draft.pathOrUrl ?? '')
  const host = parseSvnHost(dirUrl)
  if (!host) {
    ElMessage.warning('请先输入 SVN 目录 URL，再配置凭据。')
    return
  }
  void openSvnCredentialDialog(host)
}

function getSourceIssue(sourceId: string): string {
  return sourceIssueMap.value[sourceId] ?? ''
}

function ensureFeishuUrlReady(): boolean {
  if (!draft.pathOrUrl?.trim()) {
    ElMessage.warning('请先填写飞书电子表格 URL。')
    return false
  }
  return true
}

function ensureFeishuRequestReady(): boolean {
  if (!ensureFeishuUrlReady()) {
    return false
  }
  const sourceId = draft.id.trim()
  if (!sourceId) {
    ElMessage.warning('请先填写数据源标识。')
    return false
  }
  if (!isValidSourceIdFormat(sourceId)) {
    ElMessage.warning('数据源标识仅允许字母、数字与下划线。')
    return false
  }
  if (findDuplicateSourceId(sourceId)) {
    ElMessage.warning('数据源标识已存在，请修改后再检测权限。')
    return false
  }
  return true
}

function getFeishuRequestPayload(): { source_id: string; sheet_url: string } {
  return {
    source_id: draft.id.trim(),
    sheet_url: draft.pathOrUrl?.trim() ?? '',
  }
}

function getFeishuRequestKey(payload = getFeishuRequestPayload()): string {
  return `${payload.source_id}\n${payload.sheet_url}`
}

function isFeishuPermissionRequestReady(): boolean {
  const sourceId = draft.id.trim()
  return Boolean(
    isFeishuSource.value &&
      sourceId &&
      isValidSourceIdFormat(sourceId) &&
      !findDuplicateSourceId(sourceId) &&
      draft.pathOrUrl?.trim(),
  )
}

function clearFeishuPermissionAutoCheck(): void {
  if (feishuPermissionAutoCheckTimer.value !== null) {
    window.clearTimeout(feishuPermissionAutoCheckTimer.value)
    feishuPermissionAutoCheckTimer.value = null
  }
}

function scheduleFeishuPermissionAutoCheck(options?: { immediate?: boolean }): void {
  clearFeishuPermissionAutoCheck()
  if (!dialogVisible.value || !isFeishuPermissionRequestReady()) {
    return
  }

  const requestKey = getFeishuRequestKey()
  if (requestKey === lastFeishuAutoCheckKey.value) {
    return
  }

  const run = () => {
    if (requestKey !== getFeishuRequestKey() || !isFeishuPermissionRequestReady()) {
      return
    }
    lastFeishuAutoCheckKey.value = requestKey
    void checkFeishuPermission({ silent: true, requestKey })
  }

  if (options?.immediate) {
    run()
    return
  }

  feishuPermissionAutoCheckTimer.value = window.setTimeout(() => {
    feishuPermissionAutoCheckTimer.value = null
    run()
  }, FEISHU_PERMISSION_AUTO_CHECK_DEBOUNCE_MS)
}

function applySavedFeishuStatusForDraft(source?: DataSource): void {
  const sourceId = draft.id.trim()
  const sheetUrl = draft.pathOrUrl?.trim() ?? ''
  const savedSource = source ?? store.sources.find((item) => item.id === sourceId && item.type === 'feishu')
  if (!savedSource || savedSource.type !== 'feishu') {
    return
  }
  if (getSourceLocator(savedSource) !== sheetUrl) {
    return
  }

  const savedStatus = getSavedFeishuStatus(sourceId)
  if (savedStatus) {
    applyFeishuAuthStatus(savedStatus)
    return
  }

  const metadata = getFeishuSourceMetadata(sourceId)
  if (metadata?.authorization_status === 'authorized') {
    applyFeishuAuthStatus('authorized')
  }
}

function applyFeishuAuthStatus(
  status: FeishuAuthorizationStatus,
  message?: string,
): void {
  feishuAuthStatus.value = status
  feishuAuthMessage.value = message?.trim() ?? ''
}

function applyFeishuAuthResponse(data: {
  status: FeishuAuthorizationStatus
  message?: string
  sheet_url?: string
}): void {
  applyFeishuAuthStatus(data.status, data.message ?? '')
  if (
    (data.status === 'authorized' || data.status === 'authorization_success') &&
    data.sheet_url?.trim()
  ) {
    draft.pathOrUrl = data.sheet_url.trim()
    lastFeishuAutoCheckKey.value = getFeishuRequestKey()
  }
}

function getFeishuErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message
  }
  return fallback
}

function notifyFeishuAuthResult(status: FeishuAuthorizationStatus, message: string): void {
  if (status === 'authorized' || status === 'authorization_success') {
    ElMessage.success(message || '飞书表格已授权。')
    return
  }
  if (status === 'authorization_sent') {
    ElMessage.success(message || '授权请求已发送到群。')
    return
  }
  if (status === 'pending_authorization' || status === 'document_permission_denied') {
    ElMessage.warning(message || '文档权限不足，请发送授权请求到群。')
    return
  }
  ElMessage.error(message || '飞书授权状态异常，请稍后重试。')
}

async function checkFeishuPermission(options?: {
  silent?: boolean
  requestKey?: string
}): Promise<void> {
  if (!ensureFeishuRequestReady()) {
    return
  }
  const payload = getFeishuRequestPayload()
  const requestKey = options?.requestKey ?? getFeishuRequestKey(payload)
  feishuAuthState.value = 'checking'
  activeFeishuPermissionRequestKey.value = requestKey
  try {
    const response = await checkFeishuSourcePermission(payload)
    if (
      activeFeishuPermissionRequestKey.value !== requestKey ||
      getFeishuRequestKey() !== requestKey
    ) {
      return
    }
    const status = response.data.status
    const message = response.data.message ?? ''
    applyFeishuAuthResponse(response.data)
    if (status === 'authorized' || status === 'authorization_success' || status === 'authorization_failed') {
      stopFeishuPermissionPolling()
    }
    if (!options?.silent) {
      notifyFeishuAuthResult(status, message)
    }
  } catch (error) {
    if (
      activeFeishuPermissionRequestKey.value !== requestKey ||
      getFeishuRequestKey() !== requestKey
    ) {
      return
    }
    const message = getFeishuErrorMessage(error, '飞书权限检测失败，请稍后重试。')
    applyFeishuAuthStatus('authorization_failed', message)
    stopFeishuPermissionPolling()
    if (!options?.silent) {
      ElMessage.error(message)
    }
  } finally {
    if (activeFeishuPermissionRequestKey.value === requestKey) {
      activeFeishuPermissionRequestKey.value = ''
      feishuAuthState.value = 'idle'
    }
  }
}

async function sendFeishuAuthRequest(): Promise<void> {
  if (!ensureFeishuRequestReady()) {
    return
  }
  feishuAuthState.value = 'requesting'
  try {
    const response = await sendFeishuSourceAuthorizationCard(getFeishuRequestPayload())
    const status = response.data.status
    const message = response.data.message ?? ''
    applyFeishuAuthResponse(response.data)
    notifyFeishuAuthResult(status, message || '授权请求已发送到群。')
    if (status === 'authorization_sent') {
      startFeishuPermissionPolling()
    }
  } catch (error) {
    const message = getFeishuErrorMessage(error, '飞书授权请求发送失败，请稍后重试。')
    applyFeishuAuthStatus('send_failed', message)
    ElMessage.error(message)
  } finally {
    feishuAuthState.value = 'idle'
  }
}

async function recheckFeishuPermission(): Promise<void> {
  await checkFeishuPermission()
}

function startFeishuPermissionPolling(): void {
  stopFeishuPermissionPolling()
  feishuPermissionPollStartedAt.value = Date.now()
  feishuPermissionPollTimer.value = window.setInterval(() => {
    if (!dialogVisible.value || !isFeishuSource.value || !hasFeishuUrl.value) {
      stopFeishuPermissionPolling()
      return
    }
    const startedAt = feishuPermissionPollStartedAt.value
    if (startedAt && Date.now() - startedAt > FEISHU_PERMISSION_POLL_TIMEOUT_MS) {
      stopFeishuPermissionPolling()
      return
    }
    if (feishuAuthState.value === 'idle') {
      void checkFeishuPermission({ silent: true })
    }
  }, FEISHU_PERMISSION_POLL_INTERVAL_MS)
}

function stopFeishuPermissionPolling(): void {
  if (feishuPermissionPollTimer.value !== null) {
    window.clearInterval(feishuPermissionPollTimer.value)
    feishuPermissionPollTimer.value = null
  }
  feishuPermissionPollStartedAt.value = null
}

async function chooseLocalFile(): Promise<void> {
  if (!localSource.value || isPicking.value) {
    return
  }

  isPicking.value = true
  draftErrors.pathOrUrl = ''

  try {
    const response = await pickLocalSourcePath('local_excel')

    if (response.code !== 200 || !response.data.selected_path) {
      ElMessage.info('已取消选择文件。')
      return
    }

    draft.pathOrUrl = response.data.selected_path
    autofillSourceIdFromLocator(response.data.selected_path)
    ElMessage.success('已记录真实本地路径。')
  } catch (error) {
    draftErrors.pathOrUrl = error instanceof Error ? error.message : '选择本地文件失败。'
    ElMessage.error(draftErrors.pathOrUrl)
  } finally {
    isPicking.value = false
  }
}

function triggerUploadFile(): void {
  if (!canUploadLocalFile.value) {
    return
  }
  uploadInputRef.value?.click()
}

async function handleUploadFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !localSource.value || isUploading.value) {
    return
  }

  isUploading.value = true
  draftErrors.pathOrUrl = ''

  try {
    const response = await uploadSourceFile(file)
    draft.type = response.data.source_type
    draft.pathOrUrl = response.data.selected_path
    autofillSourceIdFromLocator(response.data.original_filename)
    ElMessage.success('文件已上传并记录为服务器路径。')
  } catch (error) {
    draftErrors.pathOrUrl = error instanceof Error ? error.message : '上传文件失败。'
    ElMessage.error(draftErrors.pathOrUrl)
  } finally {
    isUploading.value = false
  }
}

defineExpose({
  openCreateDialog,
  openEditDialog,
})

onMounted(() => {
  void refreshSvnCredentialItems()
})

onUnmounted(() => {
  stopFeishuPermissionPolling()
  clearFeishuPermissionAutoCheck()
  activeFeishuPermissionRequestKey.value = ''
})

watch(dialogVisible, (visible) => {
  if (!visible) {
    stopFeishuPermissionPolling()
    clearFeishuPermissionAutoCheck()
    activeFeishuPermissionRequestKey.value = ''
  }
})

watch(
  savedFeishuSourceSignature,
  () => {
    void refreshSavedFeishuSourcesStatus()
  },
  { immediate: true },
)
</script>

<template>
  <div class="panel-stack">
    <div v-if="toolbarMode === 'embedded'" class="workbench-section-toolbar">
      <div class="workbench-section-toolbar__actions">
        <button
          type="button"
          class="ec-btn ec-btn-primary ec-btn-sm"
          data-testid="source-create-button"
          @click="() => openCreateDialog()"
        >
          <svg class="ec-btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14" />
          </svg>
          新增数据源
        </button>
        <button
          type="button"
          class="ec-btn-text-collapse"
          aria-disabled="true"
        >
          收起
          <svg class="ec-btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="m18 15-6-6-6 6" />
          </svg>
        </button>
      </div>
    </div>

    <el-table :data="store.sources" class="workbench-table">
      <el-table-column label="标识" min-width="160">
        <template #default="{ row }">
          <div class="mono-chip">{{ row.id }}</div>
        </template>
      </el-table-column>
      <el-table-column label="类型" min-width="140">
        <template #default="{ row }">
          {{ getSourceTypeLabel(row.type) }}
        </template>
      </el-table-column>
      <el-table-column label="路径 / 链接" min-width="340">
        <template #default="{ row }">
          <div>
            <span class="truncate-line">{{ row.pathOrUrl ?? row.path ?? row.url }}</span>
            <small
              v-if="getSourceIssue(row.id)"
              style="display: block; margin-top: 4px; color: var(--el-color-warning)"
            >
              {{ getSourceIssue(row.id) }}
            </small>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="状态" min-width="120">
        <template #default="{ row }">
          <el-tag :type="getStatusTone(row)" effect="light" round>
            {{ getStatusLabel(row) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="170" align="left">
        <template #default="{ row }">
          <div class="table-actions">
            <button type="button" class="ec-action-link" @click="openEditDialog(row)">编辑</button>
            <button type="button" class="ec-action-link-danger" @click="removeSource(row.id)">删除</button>
          </div>
        </template>
      </el-table-column>
      <template #empty>
        <EmptyState
          variant="table"
          icon-tone="source"
          title="暂无数据源"
          description="请先添加数据源以供校验使用"
          :min-height="144"
        />
      </template>
    </el-table>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑数据源' : '新增数据源'"
      width="min(760px, calc(100vw - 32px))"
      data-testid="source-dialog"
      destroy-on-close
    >
      <div class="flex flex-col gap-4">
        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">数据源标识</label>
          <el-input
            v-model="draft.id"
            placeholder="例如：src_items、src_drop_table"
            maxlength="48"
            data-testid="source-id-input"
            @input="handleSourceIdInput"
          />
          <div
            v-if="draftErrors.id"
            class="mt-1 text-[12px] text-danger"
          >{{ draftErrors.id }}</div>
          <div
            v-else
            class="mt-1 text-[12px] text-ink-500"
          >唯一标识，仅允许字母、数字与下划线</div>
        </div>

        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">数据源类型</label>
          <el-select
            :model-value="draft.type"
            class="w-full"
            data-testid="source-type-select"
            @update:model-value="handleSourceTypeChange"
          >
            <el-option
              v-for="option in SOURCE_TYPE_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
              :disabled="option.disabled"
            />
          </el-select>
        </div>

        <div v-if="isSvnSource">
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">SVN 接入方式</label>
          <el-radio-group
            :model-value="svnSubMode"
            size="small"
            @update:model-value="(value: string | number | boolean) => handleSvnSubModeChange(value as 'remote' | 'working_copy')"
          >
            <el-radio-button label="remote">远端 URL</el-radio-button>
            <el-radio-button label="working_copy">本地工作副本</el-radio-button>
          </el-radio-group>
          <div class="mt-1 text-[12px] text-ink-500">
            首次接入推荐使用远端 URL：粘贴目录链接 → 浏览选择 .xls/.xlsx 文件即可。
          </div>
        </div>

        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">{{ getPathLabel(draft.type) }}</label>
          <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
            <el-autocomplete
              v-if="isSvnSource && svnSubMode === 'remote'"
              v-model="draft.pathOrUrl"
              class="w-full min-w-0 flex-1"
              :fetch-suggestions="querySavedSvnDirectories"
              :trigger-on-focus="true"
              clearable
              placeholder="例如 https://samosvn/data/project/samo/GameDatas/datas_qa88/"
              @input="draftErrors.pathOrUrl = ''"
              @clear="draftErrors.pathOrUrl = ''"
              @select="handleSavedSvnDirectorySelect"
            />
            <el-input
              v-else
              v-model="draft.pathOrUrl"
              class="w-full min-w-0 flex-1"
              data-testid="source-path-input"
              :placeholder="
                localSource
                  ? '上传文件，或输入服务器本机/共享盘文件路径'
                  : isSvnSource
                    ? '请输入本地 SVN 工作副本路径，例如 D:\\svn\\datas\\quests.xls'
                    : isFeishuSource
                      ? '请输入飞书电子表格 URL'
                      : '请输入链接或目录路径'
              "
              @input="handlePathInput"
            />
            <input
              v-if="localSource"
              ref="uploadInputRef"
              class="hidden"
              type="file"
              accept=".xlsx,.xls"
              data-testid="source-upload-input"
              @change="handleUploadFile"
            />
            <button
              v-if="localSource"
              type="button"
              class="ec-btn ec-btn-primary w-full shrink-0 justify-center sm:w-auto"
              data-testid="source-upload-button"
              :disabled="!canUploadLocalFile"
              @click="triggerUploadFile"
            >
              {{ isUploading ? '上传中…' : '上传文件' }}
            </button>
            <button
              v-if="localSource"
              type="button"
              class="ec-btn ec-btn-secondary w-full shrink-0 justify-center sm:w-auto"
              :disabled="!canPickLocalFile"
              @click="chooseLocalFile"
            >
              <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M4 4h12l4 4v12H4z M14 4v6h6" />
              </svg>
              {{ isPicking ? '选择中…' : '服务器选择' }}
            </button>
            <button
              v-if="isSvnSource && svnSubMode === 'remote'"
              type="button"
              class="ec-btn ec-btn-secondary w-full shrink-0 justify-center sm:w-auto"
              :disabled="!canBrowseSvnDirectory"
              :title="canBrowseSvnDirectory ? '' : '请先输入合法的 http(s) 目录 URL'"
              @click="openSvnPicker"
            >
              浏览此目录
            </button>
          </div>
          <div
            v-if="draftErrors.pathOrUrl"
            class="mt-1 text-[12px] text-danger"
          >{{ draftErrors.pathOrUrl }}</div>
          <div
            v-else-if="localSource"
            class="mt-1 text-[12px] text-ink-500"
          >
            {{ panelCopy.localExcelHelper }}
          </div>
          <div
            v-else-if="isUnsupportedCsvSource"
            class="mt-1 text-[12px] text-warning-ink"
          >
            CSV 数据源已不再支持，请删除后改用 Excel 或 SVN Excel。
          </div>
          <div
            v-else-if="isSvnSource && svnSubMode === 'remote'"
            class="mt-1 flex flex-col gap-1 text-[12px] text-ink-500 sm:flex-row sm:items-center sm:justify-between sm:gap-3"
          >
            <span class="min-w-0 flex-1">点击输入框可选择已保存 SVN 目录；选中文件后会自动写回完整文件 URL。</span>
            <button
              type="button"
              class="ec-action-link shrink-0 self-start whitespace-nowrap sm:self-auto"
              :disabled="!draft.pathOrUrl?.trim()"
              @click="handleManageSvnCredential"
            >
              管理 SVN 凭据
            </button>
          </div>
        </div>

        <div
          v-if="isFeishuSource"
          class="rounded-card border border-line bg-canvas px-4 py-3"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="text-[12px] font-medium text-ink-500">授权状态</div>
            <el-tag :type="feishuAuthStatusTone" effect="light" round>
              {{ feishuAuthStatusLabel }}
            </el-tag>
          </div>
          <div class="mt-2 text-[12px] text-ink-500">
            {{ feishuAuthStatusDescription }}
          </div>
          <div class="mt-3 flex flex-wrap gap-2">
            <button
              v-if="showFeishuPermissionCheck"
              type="button"
              class="ec-btn ec-btn-secondary ec-btn-sm"
              :disabled="!canCheckFeishuPermission"
              @click="() => checkFeishuPermission()"
            >
              检测权限
            </button>
            <button
              v-if="canSendFeishuAuthRequest"
              type="button"
              class="ec-btn ec-btn-primary ec-btn-sm"
              :disabled="isFeishuAuthBusy"
              @click="sendFeishuAuthRequest"
            >
              一键授权到群
            </button>
            <button
              v-if="canRecheckFeishuPermission"
              type="button"
              class="ec-btn ec-btn-secondary ec-btn-sm"
              :disabled="isFeishuAuthBusy"
              @click="recheckFeishuPermission"
            >
              重新检测
            </button>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="flex justify-end gap-2">
          <button
            type="button"
            class="ec-btn ec-btn-secondary"
            @click="dialogVisible = false"
          >
            取消
          </button>
          <button
            type="button"
            class="ec-btn ec-btn-primary"
            data-testid="source-save-button"
            :disabled="!canSaveSource"
            @click="saveSource"
          >
            保存数据源
          </button>
        </div>
      </template>
    </el-dialog>

    <SvnPickerDialog
      v-model:visible="svnPickerVisible"
      :base-dir-url="svnPickerDirUrl"
      :extension-filter="['xls', 'xlsx']"
      @picked="handleSvnPicked"
      @credential-required="handleCredentialRequiredFromPicker"
    />

    <SvnCredentialDialog
      v-model:visible="svnCredentialDialogVisible"
      :host="svnCredentialDialogHost"
      :default-test-dir-url="svnCredentialDialogDefaultTestDirUrl"
      :default-username="svnCredentialDialogDefaultUsername"
      :default-password="svnCredentialDialogDefaultPassword"
      @saved="handleSvnCredentialSaved"
    />
  </div>
</template>
