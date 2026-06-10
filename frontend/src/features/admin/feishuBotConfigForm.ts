import type { AiProviderPreset } from '../../types/aiProvider'
import type {
  FeishuBotAiCredentialStatus,
  FeishuBotConfig,
  FeishuBotConfigPayload,
  FeishuBotQueryRoot,
} from '../../types/admin'
import { ApiRequestError } from '../../utils/apiFetch'

export interface FeishuBotQueryRootFormRow {
  alias: string
  displayName: string
  svnUrl: string
  enabled: boolean
}

export interface FeishuBotSvnCredentialForm {
  isEditing: boolean
  username: string
  password: string
  configured: boolean
  updatedAt: string | null
}

export interface FeishuBotAiCredentialForm {
  isEditing: boolean
  providerPreset: AiProviderPreset
  baseUrl: string
  model: string
  apiKey: string
  maskedApiKey: string
  hasExtraHeaders: boolean
  extraHeadersText: string
  configured: boolean
  updatedAt: string | null
}

export interface FeishuBotAiMatchParamsForm {
  autoMatchThreshold: string
  candidateThreshold: string
  maxCandidates: string
}

export interface FeishuBotConfigFormState {
  appId: string
  appSecret: string
  defaultChatId: string
  boundChatIdsText: string
  allowedOpenIds: string
  localDownloadRoots: string
  svnDownloadRoots: string
  allowedDownloadSuffixes: string
  queryRoots: FeishuBotQueryRootFormRow[]
  svnCredential: FeishuBotSvnCredentialForm
  aiCredential: FeishuBotAiCredentialForm
  aiMatchParams: FeishuBotAiMatchParamsForm
}

export interface FeishuBotValidationResult {
  ok: boolean
  errors: string[]
}

const DEFAULT_DOWNLOAD_SUFFIXES = '.xls,.xlsx,.csv,.json,.xml,.txt'
const DEFAULT_AI_PROVIDER: AiProviderPreset = 'openai'

export function createFeishuBotConfigFormState(): FeishuBotConfigFormState {
  return {
    appId: '',
    appSecret: '',
    defaultChatId: '',
    boundChatIdsText: '',
    allowedOpenIds: '',
    localDownloadRoots: '',
    svnDownloadRoots: '',
    allowedDownloadSuffixes: DEFAULT_DOWNLOAD_SUFFIXES,
    queryRoots: [],
    svnCredential: {
      isEditing: false,
      username: '',
      password: '',
      configured: false,
      updatedAt: null,
    },
    aiCredential: {
      isEditing: false,
      providerPreset: DEFAULT_AI_PROVIDER,
      baseUrl: '',
      model: '',
      apiKey: '',
      maskedApiKey: '',
      hasExtraHeaders: false,
      extraHeadersText: '{}',
      configured: false,
      updatedAt: null,
    },
    aiMatchParams: {
      autoMatchThreshold: '0.90',
      candidateThreshold: '0.60',
      maxCandidates: '10',
    },
  }
}

export function applyFeishuBotConfigToForm(config: FeishuBotConfig): FeishuBotConfigFormState {
  const state = createFeishuBotConfigFormState()
  state.appId = config.app_id
  state.appSecret = ''
  state.defaultChatId = config.default_chat_id
  state.boundChatIdsText = config.bound_chat_ids.join('\n')
  state.allowedOpenIds = config.allowed_open_ids.join('\n')
  state.localDownloadRoots = config.local_download_roots.join('\n')
  state.svnDownloadRoots = config.svn_download_roots.join('\n')
  state.allowedDownloadSuffixes = config.allowed_download_suffixes.join(',')
  state.queryRoots = config.query_roots.map(queryRootToFormRow)
  state.svnCredential = {
    isEditing: false,
    username: config.svn_credential.username_masked,
    password: '',
    configured: config.svn_credential.configured,
    updatedAt: config.svn_credential.updated_at,
  }
  state.aiCredential = aiCredentialStatusToForm(config.ai_credential)
  state.aiMatchParams = {
    autoMatchThreshold: formatNumberInput(config.ai_match_params.auto_match_threshold),
    candidateThreshold: formatNumberInput(config.ai_match_params.candidate_threshold),
    maxCandidates: String(config.ai_match_params.max_candidates),
  }
  return state
}

export function validateFeishuBotConfigForm(
  form: FeishuBotConfigFormState,
  options: { hasAppSecret: boolean },
): FeishuBotValidationResult {
  const errors: string[] = []
  if (!form.appId.trim()) {
    errors.push('请填写 App ID')
  }
  if (!options.hasAppSecret && !form.appSecret.trim()) {
    errors.push('首次保存请填写 App Secret')
  }

  const seenAliases = new Set<string>()
  for (const row of form.queryRoots) {
    const alias = row.alias.trim()
    if (!alias) {
      errors.push('query_roots alias 不能为空')
      continue
    }
    if (seenAliases.has(alias)) {
      errors.push(`query_roots alias 重复：${alias}`)
    }
    seenAliases.add(alias)
    if (!row.svnUrl.trim()) {
      errors.push(`query_roots.svn_url 不能为空：${alias}`)
    }
  }

  return { ok: errors.length === 0, errors }
}

export function buildFeishuBotConfigPayload(
  form: FeishuBotConfigFormState,
  _options: { hasAppSecret: boolean },
): FeishuBotConfigPayload {
  const payload: FeishuBotConfigPayload = {
    app_id: form.appId.trim(),
    app_secret: form.appSecret.trim() ? form.appSecret.trim() : null,
    default_chat_id: form.defaultChatId.trim(),
    allowed_open_ids: form.allowedOpenIds,
    local_download_roots: form.localDownloadRoots,
    svn_download_roots: form.svnDownloadRoots,
    allowed_download_suffixes: form.allowedDownloadSuffixes,
    bound_chat_ids: parseTextList(
      mergeDefaultChatIdIntoBoundChats(form.defaultChatId, form.boundChatIdsText),
    ),
    query_roots: form.queryRoots.map(formRowToQueryRoot),
  }

  if (form.svnCredential.isEditing) {
    payload.svn_credential = {
      username: form.svnCredential.username.trim(),
      password: form.svnCredential.password.trim() ? form.svnCredential.password : null,
    }
  }

  return payload
}

export function extractFeishuBotConfigError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    return error.message
  }
  if (error instanceof Error) {
    return error.message
  }
  return '保存配置失败'
}

export function parseTextList(raw: string): string[] {
  const result: string[] = []
  const seen = new Set<string>()
  for (const line of raw.replace(/\r/g, '\n').split('\n')) {
    for (const piece of line.split(',')) {
      const normalized = piece.trim()
      if (!normalized || seen.has(normalized)) {
        continue
      }
      seen.add(normalized)
      result.push(normalized)
    }
  }
  return result
}

export function mergeDefaultChatIdIntoBoundChats(
  defaultChatId: string,
  boundChatIdsText: string,
): string {
  const boundChatIds = parseTextList(boundChatIdsText)
  const normalizedDefaultChatId = defaultChatId.trim()
  if (normalizedDefaultChatId && !boundChatIds.includes(normalizedDefaultChatId)) {
    boundChatIds.push(normalizedDefaultChatId)
  }
  return boundChatIds.join('\n')
}

function queryRootToFormRow(row: FeishuBotQueryRoot): FeishuBotQueryRootFormRow {
  return {
    alias: row.alias,
    displayName: row.display_name,
    svnUrl: row.svn_url,
    enabled: row.enabled,
  }
}

function formRowToQueryRoot(row: FeishuBotQueryRootFormRow): FeishuBotQueryRoot {
  return {
    alias: row.alias.trim(),
    display_name: row.displayName.trim(),
    svn_url: row.svnUrl.trim(),
    enabled: row.enabled,
  }
}

function aiCredentialStatusToForm(
  credential: FeishuBotAiCredentialStatus,
): FeishuBotAiCredentialForm {
  return {
    isEditing: false,
    providerPreset: credential.provider_preset || DEFAULT_AI_PROVIDER,
    baseUrl: credential.base_url,
    model: credential.model,
    apiKey: '',
    maskedApiKey: credential.api_key_masked,
    hasExtraHeaders: credential.has_extra_headers,
    extraHeadersText: '{}',
    configured: credential.configured,
    updatedAt: credential.updated_at,
  }
}

function formatNumberInput(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}
