import { computed, ref, unref, type ComputedRef, type Ref } from 'vue'

import {
  apiCreateRuleConfig,
  apiDeleteRuleConfig,
  apiGetRuleConfig,
  apiListRuleConfigs,
  apiListRuleConfigVersions,
  apiPublishRuleConfig,
  apiRollbackRuleConfigVersion,
  apiSaveRuleConfigDraft,
  apiTrialRuleConfig,
  apiValidateRuleConfig,
} from '../../api/ruleConfigs'
import type { StatusBadgeType } from '../../components/shell/types'
import type {
  RuleConfigCreateRequest,
  RuleConfigListResponse,
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
import { ApiRequestError } from '../../utils/apiFetch'

export const CONFIG_LOOKUP_SAMPLE_MARKDOWN = `查询类型: 礼包
数据根: game_datas
配置文件: IAPConfig.xls

  - 分页名称: AbsolutePack
  - 匹配字段
    - ID字段: INT_PackageId
    - 礼包名称: DESC
  - 输出字段
    - 礼包ID: INT_PackageId
    - 礼包名称:DESC
    - 国际服开启:STR_ServerCond_US
    - 国服开启:STR_ServerCond_CN
    - 绿色服开关:STR_ABSwitch
      - 0:绿色服关闭
      - 1:绿色服开启

  - 分页名称: Template
  - 匹配字段
    - ID字段: INT_PackageId
    - 礼包名称: DESC
  - 输出字段
    - 礼包ID: INT_PackageId
    - 礼包名称:DESC
    - 价格:INT_PriceId
      - 引用分页名称:Price
      - 引用规则:Template.INT_PriceId=Price.INT_Id
      - 显示内容:Price.INT_Point/100
    - 限制次数:INT_Limit
    - 重置cd:INT_LimitCD
    - 重置类型:INT_Reset
      - 0:不重置
      - 1:每天重置
      - 2:每周重置
      - 3:每月重置
      - 4:按LinmitCD重置`

export interface RuleConfigKpiItem {
  label: string
  value: string
  statusLabel: string
  statusType: StatusBadgeType
  iconTone: 'primary' | 'success' | 'warning' | 'danger' | 'purple'
}

export interface CreateRuleInput {
  queryType: string
  queryRoot: string
  fileName: string
}

export interface ActionResult {
  ok: boolean
  message: string
}

export interface CreateRuleResult extends ActionResult {
  ruleId?: number
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

export interface RuleConfigListApiClient {
  listRules: () => Promise<RuleConfigListResponse>
  createRule: (payload: RuleConfigCreateRequest) => Promise<RuleConfigRecordResponse>
  deleteRule: (ruleId: number | string, baseVersion: number) => Promise<void>
}

export interface RuleConfigDetailApiClient {
  getRule: (ruleId: number | string) => Promise<RuleConfigRecordResponse>
  listVersions: (ruleId: number | string) => Promise<RuleConfigVersionsResponse>
  validate: (ruleId: number | string, contentMd: string) => Promise<RuleConfigValidationResponse>
  saveDraft: (ruleId: number | string, payload: RuleConfigMutationRequest) => Promise<RuleConfigRecordResponse>
  publish: (ruleId: number | string, payload: RuleConfigMutationRequest) => Promise<RuleConfigRecordResponse>
  rollback: (
    ruleId: number | string,
    version: number,
    payload: Omit<RuleConfigMutationRequest, 'contentMd'>,
  ) => Promise<RuleConfigRecordResponse>
  trial: (ruleId: number | string, payload: RuleConfigTrialRequest) => Promise<RuleConfigTrialResponse>
}

export interface ConfigLookupRuleListState {
  rules: Ref<RuleConfigRecord[]>
  loading: Ref<boolean>
  creating: Ref<boolean>
  deletingRuleId: Ref<number | null>
  errorMessage: Ref<string>
  kpiItems: ComputedRef<RuleConfigKpiItem[]>
  load: () => Promise<void>
  createRule: (input: CreateRuleInput) => Promise<CreateRuleResult>
  deleteRule: (rule: RuleConfigRecord) => Promise<ActionResult>
}

export interface ConfigLookupRuleDetailState {
  record: Ref<RuleConfigRecord | null>
  versions: Ref<RuleConfigVersion[]>
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
  errorMessage: Ref<string>
  conflictMessage: Ref<string>
  baseVersion: ComputedRef<number>
  validationErrors: ComputedRef<string[]>
  versionRows: ComputedRef<VersionRow[]>
  isQueryTypeLocked: ComputedRef<boolean>
  load: () => Promise<void>
  reloadVersions: () => Promise<void>
  validate: () => Promise<ActionResult>
  saveDraft: () => Promise<ActionResult>
  publish: () => Promise<ActionResult>
  rollback: (version: number) => Promise<ActionResult>
  runTrial: (payload: Omit<RuleConfigTrialRequest, 'contentMd'>) => Promise<ActionResult>
  resetConflict: () => void
}

const defaultListApiClient: RuleConfigListApiClient = {
  listRules: () => apiListRuleConfigs(),
  createRule: (payload: RuleConfigCreateRequest) => apiCreateRuleConfig(payload),
  deleteRule: (ruleId: number | string, baseVersion: number) =>
    apiDeleteRuleConfig(ruleId, baseVersion),
}

const defaultDetailApiClient: RuleConfigDetailApiClient = {
  getRule: (ruleId: number | string) => apiGetRuleConfig(ruleId),
  listVersions: (ruleId: number | string) => apiListRuleConfigVersions(ruleId),
  validate: (ruleId: number | string, contentMd: string) => apiValidateRuleConfig(ruleId, contentMd),
  saveDraft: (ruleId: number | string, payload: RuleConfigMutationRequest) =>
    apiSaveRuleConfigDraft(ruleId, payload),
  publish: (ruleId: number | string, payload: RuleConfigMutationRequest) =>
    apiPublishRuleConfig(ruleId, payload),
  rollback: (
    ruleId: number | string,
    version: number,
    payload: Omit<RuleConfigMutationRequest, 'contentMd'>,
  ) => apiRollbackRuleConfigVersion(ruleId, version, payload),
  trial: (ruleId: number | string, payload: RuleConfigTrialRequest) =>
    apiTrialRuleConfig(ruleId, payload),
}

export function createConfigLookupRuleListState(
  apiClient: RuleConfigListApiClient = defaultListApiClient,
): ConfigLookupRuleListState {
  const rules = ref<RuleConfigRecord[]>([])
  const loading = ref(false)
  const creating = ref(false)
  const deletingRuleId = ref<number | null>(null)
  const errorMessage = ref('')

  const kpiItems = computed(() => buildRuleConfigListKpis(rules.value))

  async function load(): Promise<void> {
    loading.value = true
    errorMessage.value = ''
    try {
      const response = await apiClient.listRules()
      rules.value = response.data.items
    } catch (error) {
      errorMessage.value = getErrorMessage(error)
      rules.value = []
    } finally {
      loading.value = false
    }
  }

  async function createRule(input: CreateRuleInput): Promise<CreateRuleResult> {
    creating.value = true
    errorMessage.value = ''
    try {
      const response = await apiClient.createRule({
        contentMd: buildCreateRuleMarkdown(input),
        description: `创建${input.queryType.trim()}查询规则`,
      })
      await load()
      return {
        ok: true,
        message: '规则草稿已创建',
        ruleId: response.data.rule_id,
      }
    } catch (error) {
      errorMessage.value = getErrorMessage(error)
      return { ok: false, message: errorMessage.value }
    } finally {
      creating.value = false
    }
  }

  async function deleteRule(rule: RuleConfigRecord): Promise<ActionResult> {
    deletingRuleId.value = rule.rule_id
    errorMessage.value = ''
    try {
      await apiClient.deleteRule(rule.rule_id, rule.optimistic_lock_version)
      await load()
      return { ok: true, message: '规则已删除' }
    } catch (error) {
      const conflictDetail = getVersionConflictDetail(error)
      if (conflictDetail) {
        errorMessage.value = '规则已被他人更新，请刷新后手动合并。'
        return { ok: false, message: errorMessage.value }
      }
      errorMessage.value = getErrorMessage(error)
      return { ok: false, message: errorMessage.value }
    } finally {
      deletingRuleId.value = null
    }
  }

  return {
    rules,
    loading,
    creating,
    deletingRuleId,
    errorMessage,
    kpiItems,
    load,
    createRule,
    deleteRule,
  }
}

export function createConfigLookupRuleDetailState(
  ruleId: number | string | Ref<number | string>,
  apiClient: RuleConfigDetailApiClient = defaultDetailApiClient,
): ConfigLookupRuleDetailState {
  const record = ref<RuleConfigRecord | null>(null)
  const versions = ref<RuleConfigVersion[]>([])
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
  const errorMessage = ref('')
  const conflictMessage = ref('')

  const baseVersion = computed(() => record.value?.optimistic_lock_version ?? 0)
  const validationErrors = computed(() => validation.value?.errors ?? [])
  const versionRows = computed(() => buildVersionRows(versions.value))
  const isQueryTypeLocked = computed(() => Boolean(record.value?.published_version))

  async function load(): Promise<void> {
    loading.value = true
    errorMessage.value = ''
    conflictMessage.value = ''
    const currentRuleId = unref(ruleId)
    try {
      const [recordResponse, versionsResponse] = await Promise.all([
        apiClient.getRule(currentRuleId),
        apiClient.listVersions(currentRuleId),
      ])
      applyRecord(recordResponse.data)
      versions.value = versionsResponse.data.items
    } catch (error) {
      errorMessage.value = getErrorMessage(error)
      record.value = null
      versions.value = []
    } finally {
      loading.value = false
    }
  }

  async function reloadVersions(): Promise<void> {
    const response = await apiClient.listVersions(unref(ruleId))
    versions.value = response.data.items
  }

  async function validate(): Promise<ActionResult> {
    validating.value = true
    clearOperationState()
    try {
      const response = await apiClient.validate(unref(ruleId), contentMd.value)
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
      const queryTypeGuard = guardLockedQueryType()
      if (queryTypeGuard) {
        return queryTypeGuard
      }
      const response = await apiClient.saveDraft(unref(ruleId), {
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
      const queryTypeGuard = guardLockedQueryType()
      if (queryTypeGuard) {
        return queryTypeGuard
      }
      const response = await apiClient.publish(unref(ruleId), {
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
      const response = await apiClient.rollback(unref(ruleId), version, {
        baseVersion: baseVersion.value,
        description: `回滚到 v${version}`,
      })
      applyRecordResponse(response)
      await reloadVersions()
      return { ok: true, message: `已将 v${version} 复制到当前草稿，发布后生效` }
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
      const response = await apiClient.trial(unref(ruleId), {
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
      trialErrorMessage.value = getErrorMessage(error)
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

  function clearOperationState(): void {
    conflictMessage.value = ''
    errorMessage.value = ''
  }

  function resetConflict(): void {
    conflictMessage.value = ''
  }

  function guardLockedQueryType(): ActionResult | null {
    if (!isQueryTypeLocked.value || !record.value) {
      return null
    }
    const nextQueryType = extractQueryTypeFromMarkdown(contentMd.value)
    if (!nextQueryType || nextQueryType === record.value.query_type) {
      return null
    }
    const message = '已发布过的查询类型不允许直接改名'
    validation.value = {
      ok: false,
      parsed_config_json: {},
      errors: [message],
      summary: createSummaryFallback(undefined),
    }
    return { ok: false, message }
  }

  function handleOperationError(error: unknown): ActionResult {
    const conflictDetail = getVersionConflictDetail(error)
    if (conflictDetail) {
      conflictMessage.value = '规则已被他人更新，请刷新后手动合并。'
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
      return { ok: false, message: validationDetail.msg || '规则结构校验失败' }
    }

    errorMessage.value = getErrorMessage(error)
    return { ok: false, message: errorMessage.value }
  }

  return {
    record,
    versions,
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
    errorMessage,
    conflictMessage,
    baseVersion,
    validationErrors,
    versionRows,
    isQueryTypeLocked,
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

export function buildCreateRuleMarkdown(input: CreateRuleInput): string {
  const queryType = input.queryType.trim() || '新查询'
  const queryRoot = input.queryRoot.trim() || 'game_datas'
  const fileName = input.fileName.trim() || 'IAPConfig.xls'
  return CONFIG_LOOKUP_SAMPLE_MARKDOWN
    .replace(/^查询类型: .+$/m, `查询类型: ${queryType}`)
    .replace(/^数据根: .+$/m, `数据根: ${queryRoot}`)
    .replace(/^配置文件: .+$/m, `配置文件: ${fileName}`)
}

export function buildRuleConfigListKpis(records: RuleConfigRecord[]): RuleConfigKpiItem[] {
  const published = records.filter((record) => record.status === 'published').length
  const drafts = records.filter((record) => isDraftRecord(record)).length
  const failed = records.filter((record) => record.status === 'validation_failed').length
  const recentPublished =
    records
      .map((record) => record.published_at)
      .filter((value): value is string => Boolean(value))
      .sort()
      .at(-1) ?? ''

  return [
    {
      label: '全部查询规则',
      value: String(records.length),
      statusLabel: '查询类型',
      statusType: 'neutral',
      iconTone: 'primary',
    },
    {
      label: '已发布',
      value: String(published),
      statusLabel: published > 0 ? '已发布' : '未发布',
      statusType: published > 0 ? 'success' : 'neutral',
      iconTone: 'success',
    },
    {
      label: '草稿中',
      value: String(drafts),
      statusLabel: drafts > 0 ? '有草稿' : '无草稿',
      statusType: drafts > 0 ? 'warning' : 'success',
      iconTone: 'warning',
    },
    {
      label: '校验失败',
      value: String(failed),
      statusLabel: failed > 0 ? '需处理' : '无失败',
      statusType: failed > 0 ? 'danger' : 'success',
      iconTone: 'danger',
    },
    {
      label: '最近发布',
      value: recentPublished ? formatDateTime(recentPublished) : '-',
      statusLabel: recentPublished ? '已记录' : '未发布',
      statusType: recentPublished ? 'success' : 'neutral',
      iconTone: 'purple',
    },
  ]
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

export function getRuleConfigStatusLabel(status: string): string {
  if (status === 'published') return '已发布'
  if (status === 'draft') return '草稿中'
  if (status === 'validation_failed') return '校验失败'
  if (status === 'archived') return '已归档'
  if (status === 'empty') return '未发布'
  return status || '-'
}

export function getRuleConfigBadgeType(status: string): StatusBadgeType {
  if (status === 'published') return 'success'
  if (status === 'draft') return 'warning'
  if (status === 'validation_failed') return 'danger'
  return 'neutral'
}

export function getRuleQueryRoot(record: RuleConfigRecord | null): string {
  return getParsedString(record, 'query_root')
}

export function getRuleFileName(record: RuleConfigRecord | null): string {
  return getParsedString(record, 'file')
}

export function getRulePageCount(record: RuleConfigRecord | null): number {
  const pages = record?.parsed_config_json?.pages
  return Array.isArray(pages) ? pages.length : 0
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

function isDraftRecord(record: RuleConfigRecord): boolean {
  return (
    record.status === 'draft' ||
    (record.status !== 'empty' && record.draft_version > (record.published_version ?? 0))
  )
}

function getParsedString(record: RuleConfigRecord | null, key: string): string {
  const value = record?.parsed_config_json?.[key]
  return typeof value === 'string' && value.trim() ? value : '-'
}

function extractQueryTypeFromMarkdown(contentMd: string): string {
  const match = contentMd.match(/^查询类型\s*[:：]\s*(.+)$/m)
  return match?.[1]?.trim() ?? ''
}

function getVersionStatusLabel(status: string): string {
  if (status === 'published') return '已发布'
  if (status === 'draft') return '草稿'
  if (status === 'archived') return '已归档'
  if (status === 'validation_failed') return '校验失败'
  return status || '-'
}

function getVersionBadgeType(status: string): StatusBadgeType {
  if (status === 'published') return 'success'
  if (status === 'draft') return 'warning'
  if (status === 'validation_failed') return 'danger'
  return 'neutral'
}

function buildVersionActions(version: RuleConfigVersion): string[] {
  void version
  return ['回滚']
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
