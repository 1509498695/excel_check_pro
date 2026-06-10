import { describe, expect, it } from 'vitest'

import {
  PROJECT_AI_PROVIDER_OPTIONS,
  applyProjectAiConfigToForm,
  buildProjectAiConfigPayload,
  createProjectAiConfigFormState,
  getModelOptionsForProjectAiProvider,
  getProjectAiProviderDefaults,
  normalizeProjectAiProvider,
  validateProjectAiConfigForm,
} from '../../src/features/admin/projectAiConfigForm'
import { AI_PROVIDER_PRESETS } from '../../src/features/ai/providerPresets'
import type { ProjectAiConfig } from '../../src/types/projectAiConfig'

const backendConfig: ProjectAiConfig = {
  configured: true,
  enabled: true,
  provider: 'openai',
  model: 'gpt-5.4-mini',
  base_url: 'https://api.openai.com/v1',
  masked_api_key: 'sk-***cret',
  has_extra_headers: false,
  auto_match_threshold: 0.9,
  candidate_threshold: 0.6,
  max_candidates: 10,
  last_test_status: 'success',
  last_test_at: '2024-05-27T01:20:11',
  last_test_error_summary: '',
  updated_by: 1,
  updated_at: '2024-05-27T01:20:11',
}

describe('project AI config form model', () => {
  it('derives provider choices from shared AI provider presets', () => {
    expect(PROJECT_AI_PROVIDER_OPTIONS).toEqual(
      AI_PROVIDER_PRESETS.map(({ label, value }) => ({ label, value })),
    )
  })

  it('uses shared provider defaults and manual model input', () => {
    const form = createProjectAiConfigFormState()

    expect(form.provider).toBe('openai')
    expect(form.model).toBe('gpt-5.4-mini')
    expect(form.baseUrl).toBe('https://api.openai.com/v1')
    expect(getProjectAiProviderDefaults('deepseek')).toEqual({
      baseUrl: 'https://api.deepseek.com',
      model: 'deepseek-v4-flash',
    })
    for (const preset of AI_PROVIDER_PRESETS) {
      expect(getModelOptionsForProjectAiProvider(preset.value)).toEqual([])
    }
  })

  it('normalizes legacy custom OpenAI compatible provider to shared custom provider', () => {
    expect(normalizeProjectAiProvider('custom_openai_compatible')).toBe('custom_openai')
  })

  it('hydrates form from masked backend status', () => {
    const form = applyProjectAiConfigToForm(backendConfig)

    expect(form.provider).toBe('openai')
    expect(form.model).toBe('gpt-5.4-mini')
    expect(form.baseUrl).toBe('https://api.openai.com/v1')
    expect(form.apiKey).toBe('')
    expect(form.maskedApiKey).toBe('sk-***cret')
    expect(form.enabled).toBe(true)
    expect(form.lastTestStatus).toBe('success')
  })

  it('builds save payload and omits blank API key', () => {
    const form = applyProjectAiConfigToForm(backendConfig)

    expect(buildProjectAiConfigPayload(form)).toEqual({
      provider: 'openai',
      model: 'gpt-5.4-mini',
      base_url: 'https://api.openai.com/v1',
      api_key: null,
      enabled: true,
      auto_match_threshold: 0.9,
      candidate_threshold: 0.6,
      max_candidates: 10,
    })

    form.apiKey = 'sk-new'
    expect(buildProjectAiConfigPayload(form).api_key).toBe('sk-new')
  })

  it('validates API key threshold order and candidate count', () => {
    const form = createProjectAiConfigFormState()
    form.enabled = true
    form.model = ''
    form.apiKey = ''
    form.maskedApiKey = ''
    form.autoMatchThreshold = '0.50'
    form.candidateThreshold = '0.70'
    form.maxCandidates = '21'

    const result = validateProjectAiConfigForm(form)

    expect(result.ok).toBe(false)
    expect(result.errors).toEqual([
      '启用项目级 AI 前必须填写 API Key',
      '请填写模型名称',
      '高置信自动返回阈值必须大于或等于候选列表阈值',
      '最大候选数量必须是 1 到 20 之间的整数',
    ])
  })
})
