import type {
  ProjectAiConfig,
  ProjectAiConfigPayload,
  ProjectAiProviderPreset,
} from '../../types/projectAiConfig'
import {
  AI_PROVIDER_PRESETS,
  getAiProviderPresetDefaults,
  normalizeSharedAiProviderPreset,
} from '../ai/providerPresets'

export interface ProjectAiProviderOption {
  label: string
  value: ProjectAiProviderPreset
}

export interface ProjectAiConfigFormState {
  configured: boolean
  enabled: boolean
  provider: ProjectAiProviderPreset
  model: string
  baseUrl: string
  apiKey: string
  maskedApiKey: string
  autoMatchThreshold: string
  candidateThreshold: string
  maxCandidates: string
  lastTestStatus: string
  lastTestAt: string | null
  lastTestErrorSummary: string
  updatedAt: string | null
}

export interface ProjectAiValidationResult {
  ok: boolean
  errors: string[]
}

export const PROJECT_AI_PROVIDER_OPTIONS: ProjectAiProviderOption[] = AI_PROVIDER_PRESETS.map(
  ({ label, value }) => ({ label, value }),
)

export function getModelOptionsForProjectAiProvider(
  _provider: ProjectAiProviderPreset,
): string[] {
  return []
}

export function getProjectAiProviderDefaults(
  provider: ProjectAiProviderPreset,
): { baseUrl: string; model: string } {
  return getAiProviderPresetDefaults(provider)
}

export function createProjectAiConfigFormState(): ProjectAiConfigFormState {
  const defaults = getProjectAiProviderDefaults('openai')
  return {
    configured: false,
    enabled: false,
    provider: 'openai',
    model: defaults.model,
    baseUrl: defaults.baseUrl,
    apiKey: '',
    maskedApiKey: '',
    autoMatchThreshold: '0.90',
    candidateThreshold: '0.60',
    maxCandidates: '10',
    lastTestStatus: '',
    lastTestAt: null,
    lastTestErrorSummary: '',
    updatedAt: null,
  }
}

export function applyProjectAiConfigToForm(
  config: ProjectAiConfig | null,
): ProjectAiConfigFormState {
  const state = createProjectAiConfigFormState()
  if (!config) {
    return state
  }
  const provider = normalizeProjectAiProvider(config.provider)
  state.configured = config.configured
  state.enabled = config.enabled
  state.provider = provider
  state.model = config.model || getProjectAiProviderDefaults(provider).model
  state.baseUrl = config.base_url || getProjectAiProviderDefaults(provider).baseUrl
  state.apiKey = ''
  state.maskedApiKey = config.masked_api_key
  state.autoMatchThreshold = formatNumberInput(config.auto_match_threshold)
  state.candidateThreshold = formatNumberInput(config.candidate_threshold)
  state.maxCandidates = String(config.max_candidates)
  state.lastTestStatus = config.last_test_status
  state.lastTestAt = config.last_test_at
  state.lastTestErrorSummary = config.last_test_error_summary
  state.updatedAt = config.updated_at
  return state
}

export function applyProjectAiProviderDefaults(
  form: ProjectAiConfigFormState,
  provider: ProjectAiProviderPreset,
): void {
  const defaults = getProjectAiProviderDefaults(provider)
  form.provider = provider
  form.baseUrl = defaults.baseUrl
  form.model = defaults.model
}

export function validateProjectAiConfigForm(
  form: ProjectAiConfigFormState,
): ProjectAiValidationResult {
  const errors: string[] = []
  const hasSavedKey = Boolean(form.maskedApiKey)
  if (form.enabled && !hasSavedKey && !form.apiKey.trim()) {
    errors.push('启用项目级 AI 前必须填写 API Key')
  }
  if (!form.model.trim()) {
    errors.push('请填写模型名称')
  }
  if (!form.baseUrl.trim()) {
    errors.push('请填写 Base URL')
  }
  const autoThreshold = Number(form.autoMatchThreshold)
  const candidateThreshold = Number(form.candidateThreshold)
  const maxCandidates = Number(form.maxCandidates)
  if (!Number.isFinite(autoThreshold) || autoThreshold < 0 || autoThreshold > 1) {
    errors.push('高置信自动返回阈值必须是 0 到 1 之间的数字')
  }
  if (!Number.isFinite(candidateThreshold) || candidateThreshold < 0 || candidateThreshold > 1) {
    errors.push('候选列表阈值必须是 0 到 1 之间的数字')
  }
  if (
    Number.isFinite(autoThreshold) &&
    Number.isFinite(candidateThreshold) &&
    autoThreshold < candidateThreshold
  ) {
    errors.push('高置信自动返回阈值必须大于或等于候选列表阈值')
  }
  if (!Number.isInteger(maxCandidates) || maxCandidates < 1 || maxCandidates > 20) {
    errors.push('最大候选数量必须是 1 到 20 之间的整数')
  }
  return { ok: errors.length === 0, errors }
}

export function buildProjectAiConfigPayload(
  form: ProjectAiConfigFormState,
): ProjectAiConfigPayload {
  return {
    provider: form.provider,
    model: form.model.trim(),
    base_url: form.baseUrl.trim(),
    api_key: form.apiKey.trim() ? form.apiKey.trim() : null,
    enabled: form.enabled,
    auto_match_threshold: Number(form.autoMatchThreshold),
    candidate_threshold: Number(form.candidateThreshold),
    max_candidates: Number(form.maxCandidates),
  }
}

export function normalizeProjectAiProvider(value: string): ProjectAiProviderPreset {
  return normalizeSharedAiProviderPreset(value) ?? 'openai'
}

function formatNumberInput(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}
