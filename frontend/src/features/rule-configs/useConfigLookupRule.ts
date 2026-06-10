import { computed, ref, type ComputedRef, type Ref } from 'vue'

import {
  apiGetRuleConfig,
  apiGetRuleConfigCredentialsStatus,
  apiListRuleConfigVersions,
  apiPublishRuleConfig,
  apiRollbackRuleConfigVersion,
  apiSaveRuleConfigDraft,
  apiTrialRuleConfig,
  apiValidateRuleConfig,
} from '../../api/ruleConfigs'
import type { StatusBadgeType } from '../../components/shell/types'
import type {
  RuleConfigCredentialsStatus,
  RuleConfigCredentialsStatusResponse,
  RuleConfigMutationRequest,
  RuleConfigRecord,
  RuleConfigRecordResponse,
  RuleConfigTrialRequest,
  RuleConfigTrialResponse,
  RuleConfigTrialResult,
  RuleConfigValidationFailureDetail,
  RuleConfigValidationResult,
  RuleConfigValidationResponse,
  RuleConfigVersion,
  RuleConfigVersionConflictDetail,
  RuleConfigVersionsResponse,
} from '../../types/ruleConfigs'
import { RULE_FAMILY_CONFIG_LOOKUP } from '../../types/ruleConfigs'
import { ApiRequestError } from '../../utils/apiFetch'

export const CONFIG_LOOKUP_SAMPLE_MARKDOWN = `查询类型: 礼包
数据根: game_datas
配置文件: IAPConfig.xls

分页:
  - 名称: AbsolutePack
    ID字段: INT_PackageId
    名称字段: DESC
    输出字段:
      - INT_PackageId
      - 字段: DESC
        显示名: 礼包名称

引用:
  - 名称: price
    配置文件: Price.xls
    分页: Price
    关联: INT_PriceId=INT_PriceId
    输出字段:
      - 字段: INT_Point
        显示名: 价格点数`

export interface RuleOverviewItem {
  label: string
  value: string
  tone: 'default' | 'success' | 'warning' | 'danger'
}

export interface RuleCatalogItem {
  id: string
  title: string
  family: string
  statusLabel: string
  badgeType: StatusBadgeType
  description: string
  updatedAt: string
  supported: boolean
  futureLabel?: string
}

export interface VersionRow {
  version: string
  versionNumber: number
  statusLabel: string
  badgeType: StatusBadgeType
  operator: string
  updatedAt: string
  description: string
  actions: string[]
}

export interface CredentialRow {
  label: string
  statusLabel: string
  accountLabel: string
  secretLabel: string
  updatedAt: string
  canManage: boolean
}

export interface ActionResult {
  ok: boolean
  message: string
}

export interface RuleConfigApiClient {
  getCurrent: () => Promise<RuleConfigRecordResponse>
  listVersions: () => Promise<RuleConfigVersionsResponse>
  getCredentialsStatus: () => Promise<RuleConfigCredentialsStatusResponse>
  validate: (contentMd: string) => Promise<RuleConfigValidationResponse>
  saveDraft: (payload: RuleConfigMutationRequest) => Promise<RuleConfigRecordResponse>
  publish: (payload: RuleConfigMutationRequest) => Promise<RuleConfigRecordResponse>
  rollback: (version: number, payload: Omit<RuleConfigMutationRequest, 'contentMd'>) => Promise<RuleConfigRecordResponse>
  trial: (payload: RuleConfigTrialRequest) => Promise<RuleConfigTrialResponse>
}

export interface ConfigLookupRuleState {
  record: Ref<RuleConfigRecord>
  versions: Ref<RuleConfigVersion[]>
  credentials: Ref<RuleConfigCredentialsStatus | null>
  contentMd: Ref<string>
  validation: Ref<RuleConfigValidationResult | null>
  loading: Ref<boolean>
  saving: Ref<boolean>
  validating: Ref<boolean>
  publishing: Ref<boolean>
  rollingBack: Ref<boolean>
  trialLoading: Ref<boolean>
  trialResult: Ref<RuleConfigTrialResult | null>
  trialErrorMessage: Ref<string>
  trialErrorLines: Ref<string[]>
  fallbackActive: Ref<boolean>
  errorMessage: Ref<string>
  conflictMessage: Ref<string>
  baseVersion: ComputedRef<number>
  validationErrors: ComputedRef<string[]>
  overviewItems: ComputedRef<RuleOverviewItem[]>
  versionRows: ComputedRef<VersionRow[]>
  ruleItems: ComputedRef<RuleCatalogItem[]>
  load: () => Promise<void>
  reloadVersions: () => Promise<void>
  validate: () => Promise<ActionResult>
  saveDraft: () => Promise<ActionResult>
  publish: () => Promise<ActionResult>
  rollback: (version: number) => Promise<ActionResult>
  runTrial: (payload: Omit<RuleConfigTrialRequest, 'contentMd'>) => Promise<ActionResult>
  resetConflict: () => void
}

export const ruleCatalog: RuleCatalogItem[] = [
  {
    id: RULE_FAMILY_CONFIG_LOOKUP,
    title: '配置表查询',
    family: RULE_FAMILY_CONFIG_LOOKUP,
    statusLabel: '未发布',
    badgeType: 'neutral',
    description: '用于通过飞书机器人按配置表查询命令读取数据，支持多分页查询与引用关联。',
    updatedAt: '-',
    supported: true,
  },
  {
    id: 'project_check',
    title: '项目校验规则',
    family: 'project_check',
    statusLabel: '未来扩展',
    badgeType: 'warning',
    description: '项目级固定校验规则配置，当前仅作为未来扩展入口展示。',
    updatedAt: '-',
    supported: false,
    futureLabel: '未来扩展',
  },
  {
    id: 'directory_query',
    title: '目录查询规则',
    family: 'directory_query',
    statusLabel: '未来扩展',
    badgeType: 'neutral',
    description: '目录级文件查询规则配置，当前仅作为未来扩展入口展示。',
    updatedAt: '-',
    supported: false,
    futureLabel: '未来扩展',
  },
]

const defaultRuleConfigApiClient: RuleConfigApiClient = {
  getCurrent: () => apiGetRuleConfig(),
  listVersions: () => apiListRuleConfigVersions(),
  getCredentialsStatus: () => apiGetRuleConfigCredentialsStatus(),
  validate: (contentMd: string) => apiValidateRuleConfig(contentMd),
  saveDraft: (payload: RuleConfigMutationRequest) => apiSaveRuleConfigDraft(payload),
  publish: (payload: RuleConfigMutationRequest) => apiPublishRuleConfig(payload),
  rollback: (version: number, payload: Omit<RuleConfigMutationRequest, 'contentMd'>) =>
    apiRollbackRuleConfigVersion(version, payload),
  trial: (payload: RuleConfigTrialRequest) => apiTrialRuleConfig(payload),
}

export function createConfigLookupRuleState(
  apiClient: RuleConfigApiClient = defaultRuleConfigApiClient,
  options: { allowDevFallback?: boolean } = {},
): ConfigLookupRuleState {
  const allowDevFallback = options.allowDevFallback ?? import.meta.env.DEV
  const record = ref<RuleConfigRecord>(createEmptyRuleConfigRecord())
  const versions = ref<RuleConfigVersion[]>([])
  const credentials = ref<RuleConfigCredentialsStatus | null>(null)
  const contentMd = ref(CONFIG_LOOKUP_SAMPLE_MARKDOWN)
  const validation = ref<RuleConfigValidationResult | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const validating = ref(false)
  const publishing = ref(false)
  const rollingBack = ref(false)
  const trialLoading = ref(false)
  const trialResult = ref<RuleConfigTrialResult | null>(null)
  const trialErrorMessage = ref('')
  const trialErrorLines = ref<string[]>([])
  const fallbackActive = ref(false)
  const errorMessage = ref('')
  const conflictMessage = ref('')

  const baseVersion = computed(() => record.value.optimistic_lock_version)
  const validationErrors = computed(() => validation.value?.errors ?? [])
  const overviewItems = computed(() => buildRuleConfigOverview(record.value, versions.value))
  const versionRows = computed(() => buildVersionRows(versions.value))
  const ruleItems = computed(() => buildRuleItems(record.value))

  async function load(): Promise<void> {
    loading.value = true
    errorMessage.value = ''
    conflictMessage.value = ''
    try {
      const [configResponse, versionsResponse, credentialsResponse] = await Promise.all([
        apiClient.getCurrent(),
        apiClient.listVersions(),
        apiClient.getCredentialsStatus(),
      ])
      applyRecord(configResponse.data)
      versions.value = versionsResponse.data.items
      credentials.value = credentialsResponse.data
      fallbackActive.value = false
    } catch (error) {
      if (canUseDevFallback(error, allowDevFallback)) {
        applyDevFallback()
      } else {
        errorMessage.value = getErrorMessage(error)
      }
    } finally {
      loading.value = false
    }
  }

  async function reloadVersions(): Promise<void> {
    const response = await apiClient.listVersions()
    versions.value = response.data.items
  }

  async function validate(): Promise<ActionResult> {
    validating.value = true
    clearOperationState()
    try {
      const response = await apiClient.validate(contentMd.value)
      validation.value = response.data
      return {
        ok: response.data.ok,
        message: response.data.ok ? '结构校验通过' : '结构校验未通过',
      }
    } catch (error) {
      return handleOperationError(error)
    } finally {
      validating.value = false
    }
  }

  async function saveDraft(): Promise<ActionResult> {
    saving.value = true
    clearOperationState()
    try {
      const response = await apiClient.saveDraft({
        contentMd: contentMd.value,
        baseVersion: baseVersion.value,
        description: '保存草稿',
      })
      applyRecordResponse(response)
      await reloadVersions()
      return { ok: true, message: '草稿已保存' }
    } catch (error) {
      return handleOperationError(error)
    } finally {
      saving.value = false
    }
  }

  async function publish(): Promise<ActionResult> {
    publishing.value = true
    clearOperationState()
    try {
      const response = await apiClient.publish({
        contentMd: contentMd.value,
        baseVersion: baseVersion.value,
        description: '发布规则',
      })
      applyRecordResponse(response)
      await reloadVersions()
      return { ok: true, message: '发布后已立即生效，无需重启机器人。' }
    } catch (error) {
      return handleOperationError(error)
    } finally {
      publishing.value = false
    }
  }

  async function rollback(version: number): Promise<ActionResult> {
    rollingBack.value = true
    clearOperationState()
    try {
      const response = await apiClient.rollback(version, {
        baseVersion: baseVersion.value,
        description: `回滚到 v${version}`,
      })
      applyRecordResponse(response)
      await reloadVersions()
      return { ok: true, message: `已回滚到 v${version} 并生成新草稿` }
    } catch (error) {
      return handleOperationError(error)
    } finally {
      rollingBack.value = false
    }
  }

  async function runTrial(payload: Omit<RuleConfigTrialRequest, 'contentMd'>): Promise<ActionResult> {
    trialLoading.value = true
    trialResult.value = null
    trialErrorMessage.value = ''
    trialErrorLines.value = []
    try {
      const response = await apiClient.trial({
        ...payload,
        contentMd: payload.useCurrentDraft ? contentMd.value : undefined,
      })
      trialResult.value = response.data
      const ok = response.data.status === 'hit' || response.data.status === 'candidates'
      if (!ok) {
        trialErrorMessage.value = response.data.message
      }
      return { ok, message: response.data.message }
    } catch (error) {
      const validationDetail = getValidationFailureDetail(error)
      if (validationDetail) {
        trialErrorMessage.value = validationDetail.msg || '规则结构校验失败'
        trialErrorLines.value = validationDetail.errors
        return { ok: false, message: trialErrorMessage.value }
      }
      if (error instanceof ApiRequestError && (error.status === 404 || error.status === 405)) {
        trialErrorMessage.value = '试查接口不可用，请确认后端已更新'
      } else {
        trialErrorMessage.value = getErrorMessage(error)
      }
      return { ok: false, message: trialErrorMessage.value }
    } finally {
      trialLoading.value = false
    }
  }

  function applyRecordResponse(response: RuleConfigRecordResponse): void {
    applyRecord(response.data)
    if (response.data.validation) {
      validation.value = response.data.validation
    }
  }

  function applyRecord(nextRecord: RuleConfigRecord): void {
    record.value = nextRecord
    contentMd.value = nextRecord.content_md.trim() ? nextRecord.content_md : CONFIG_LOOKUP_SAMPLE_MARKDOWN
  }

  function applyDevFallback(): void {
    record.value = createEmptyRuleConfigRecord()
    versions.value = []
    credentials.value = createEmptyCredentialsStatus()
    contentMd.value = CONFIG_LOOKUP_SAMPLE_MARKDOWN
    validation.value = null
    fallbackActive.value = true
    errorMessage.value = ''
  }

  function clearOperationState(): void {
    conflictMessage.value = ''
    errorMessage.value = ''
  }

  function resetConflict(): void {
    conflictMessage.value = ''
  }

  function handleOperationError(error: unknown): ActionResult {
    const conflictDetail = getVersionConflictDetail(error)
    if (conflictDetail) {
      conflictMessage.value = `规则已被他人更新，请刷新后手动合并。当前版本：${conflictDetail.current_optimistic_lock_version}`
      return { ok: false, message: conflictMessage.value }
    }

    const validationDetail = getValidationFailureDetail(error)
    if (validationDetail) {
      validation.value = {
        ok: false,
        parsed_config_json: {},
        errors: validationDetail.errors,
        summary: createSummaryFallback(validationDetail.summary),
      }
      return { ok: false, message: '规则结构校验失败' }
    }

    errorMessage.value = getErrorMessage(error)
    return { ok: false, message: errorMessage.value }
  }

  return {
    record,
    versions,
    credentials,
    contentMd,
    validation,
    loading,
    saving,
    validating,
    publishing,
    rollingBack,
    trialLoading,
    trialResult,
    trialErrorMessage,
    trialErrorLines,
    fallbackActive,
    errorMessage,
    conflictMessage,
    baseVersion,
    validationErrors,
    overviewItems,
    versionRows,
    ruleItems,
    load,
    reloadVersions,
    validate,
    saveDraft,
    publish,
    rollback,
    runTrial,
    resetConflict,
  }
}

export function buildRuleConfigOverview(
  record: RuleConfigRecord,
  versions: RuleConfigVersion[],
): RuleOverviewItem[] {
  const publishedCount = record.status === 'published' && record.published_version !== null ? 1 : 0
  const hasDraft =
    record.status === 'draft' ||
    (record.status !== 'empty' &&
      record.draft_version > (record.published_version ?? 0))
  const recentPublishedAt =
    record.published_at ??
    versions.find((version) => version.status === 'published')?.created_at ??
    '-'

  return [
    { label: '全部规则', value: '3', tone: 'default' },
    { label: '已发布', value: String(publishedCount), tone: 'success' },
    { label: '草稿中', value: hasDraft ? '1' : '0', tone: 'warning' },
    { label: '校验失败', value: '0', tone: 'danger' },
    { label: '最近发布', value: formatDateTime(recentPublishedAt), tone: 'default' },
  ]
}

export function buildRuleItems(record: RuleConfigRecord): RuleCatalogItem[] {
  return ruleCatalog.map((rule) => {
    if (rule.id !== RULE_FAMILY_CONFIG_LOOKUP) {
      return rule
    }
    return {
      ...rule,
      statusLabel: getRecordStatusLabel(record),
      badgeType: getRecordBadgeType(record),
      updatedAt: formatDateTime(record.updated_at),
    }
  })
}

export function buildVersionRows(versions: RuleConfigVersion[]): VersionRow[] {
  return versions.map((version) => ({
    version: `v${version.version}`,
    versionNumber: version.version,
    statusLabel: getVersionStatusLabel(version.status),
    badgeType: getVersionBadgeType(version.status),
    operator: version.operator === null ? '-' : `用户 #${version.operator}`,
    updatedAt: formatDateTime(version.created_at),
    description: version.description || '-',
    actions: buildVersionActions(version),
  }))
}

export function buildCredentialRows(
  credentials: RuleConfigCredentialsStatus,
  canManage: boolean,
): CredentialRow[] {
  return [
    {
      label: 'SVN 凭据',
      statusLabel: credentials.svn.configured ? '已连接' : '未配置',
      accountLabel: `账号：${credentials.svn.account_masked || '-'}`,
      secretLabel: credentials.svn.configured ? '密码：已脱敏' : '密码：未配置',
      updatedAt: formatDateTime(credentials.svn.updated_at),
      canManage,
    },
    {
      label: 'AI 凭据',
      statusLabel: credentials.ai.configured ? '已连接' : '未配置',
      accountLabel: `供应商：${credentials.ai.provider || '-'} / 模型：${credentials.ai.model || '-'}`,
      secretLabel: `密钥：${credentials.ai.masked_api_key || credentials.ai.credential_masked || (credentials.ai.configured ? '已脱敏' : '未配置')} / 测试：${getAiTestStatusLabel(credentials.ai.last_test_status)}`,
      updatedAt: formatDateTime(credentials.ai.last_test_at ?? credentials.ai.updated_at),
      canManage,
    },
  ]
}

function getAiTestStatusLabel(status: string | undefined): string {
  if (status === 'success') return '成功'
  if (status === 'failed') return '失败'
  return '未测试'
}

export function canOpenRuleDetail(rule: RuleCatalogItem): boolean {
  return rule.supported && rule.family === RULE_FAMILY_CONFIG_LOOKUP
}

export function createEmptyRuleConfigRecord(): RuleConfigRecord {
  return {
    project_id: 0,
    rule_family: RULE_FAMILY_CONFIG_LOOKUP,
    content_md: '',
    parsed_config_json: {},
    status: 'empty',
    draft_version: 0,
    published_version: null,
    created_by: null,
    updated_by: null,
    published_by: null,
    published_at: null,
    optimistic_lock_version: 0,
    created_at: null,
    updated_at: null,
  }
}

export function createEmptyCredentialsStatus(): RuleConfigCredentialsStatus {
  return {
    svn: {
      configured: false,
      account_masked: '',
      updated_at: null,
    },
    ai: {
      configured: false,
      enabled: false,
      provider: '',
      base_url: '',
      model: '',
      credential_masked: '',
      masked_api_key: '',
      last_test_status: '',
      last_test_at: null,
      updated_at: null,
    },
  }
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value || value === '-') {
    return '-'
  }
  const normalized = value.replace('T', ' ')
  const trimmed = normalized.split(/[.+Z]/)[0] ?? normalized
  const [datePart, timePart = ''] = trimmed.split(' ')
  const date = datePart.replaceAll('-', '/')
  const time = timePart.slice(0, 8)
  return time ? `${date} ${time}` : date
}

function getRecordStatusLabel(record: RuleConfigRecord): string {
  if (record.status === 'published') return '已发布'
  if (record.status === 'draft') return '草稿'
  return '未发布'
}

function getRecordBadgeType(record: RuleConfigRecord): StatusBadgeType {
  if (record.status === 'published') return 'success'
  if (record.status === 'draft') return 'warning'
  return 'neutral'
}

function getVersionStatusLabel(status: string): string {
  if (status === 'published') return '已发布'
  if (status === 'draft') return '草稿'
  if (status === 'archived') return '已归档'
  return status || '-'
}

function getVersionBadgeType(status: string): StatusBadgeType {
  if (status === 'published') return 'success'
  if (status === 'draft') return 'warning'
  return 'neutral'
}

function buildVersionActions(version: RuleConfigVersion): string[] {
  if (version.status === 'draft') {
    return ['查看', '发布', '对比']
  }
  if (version.status === 'published') {
    return ['查看', '对比']
  }
  return ['查看', '回滚', '对比']
}

function canUseDevFallback(error: unknown, allowDevFallback: boolean): boolean {
  if (!allowDevFallback) {
    return false
  }
  if (error instanceof ApiRequestError) {
    return error.status === 404 || error.status === 405
  }
  return error instanceof TypeError
}

function getVersionConflictDetail(error: unknown): RuleConfigVersionConflictDetail | null {
  if (!(error instanceof ApiRequestError)) {
    return null
  }
  const detail = error.detail
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) {
    return null
  }
  const payload = detail as Partial<RuleConfigVersionConflictDetail>
  if (payload.code !== 'RULE_CONFIG_VERSION_CONFLICT') {
    return null
  }
  return {
    code: 'RULE_CONFIG_VERSION_CONFLICT',
    current_optimistic_lock_version: Number(payload.current_optimistic_lock_version ?? 0),
  }
}

function getValidationFailureDetail(error: unknown): RuleConfigValidationFailureDetail | null {
  if (!(error instanceof ApiRequestError)) {
    return null
  }
  const detail = error.detail
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) {
    return null
  }
  const payload = detail as Partial<RuleConfigValidationFailureDetail>
  if (payload.code !== 'RULE_CONFIG_VALIDATION_FAILED' || !Array.isArray(payload.errors)) {
    return null
  }
  return {
    code: 'RULE_CONFIG_VALIDATION_FAILED',
    msg: payload.msg,
    errors: payload.errors,
    summary: payload.summary,
  }
}

function createSummaryFallback(
  summary: Partial<RuleConfigValidationResult['summary']> | undefined,
): RuleConfigValidationResult['summary'] {
  return {
    query_count: summary?.query_count ?? 0,
    query_types: summary?.query_types ?? [],
    query_roots: summary?.query_roots ?? [],
    primary_files: summary?.primary_files ?? [],
    pages: summary?.pages ?? [],
    references: summary?.references ?? [],
  }
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message
  }
  return '请求失败，请稍后重试。'
}
