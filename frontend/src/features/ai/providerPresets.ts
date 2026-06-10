import type { AiProviderPreset } from '../../types/aiProvider'

export const AI_PROVIDER_PRESETS = [
  {
    label: 'OpenAI',
    value: 'openai',
    protocol: 'OpenAI-compatible',
    baseUrl: 'https://api.openai.com/v1',
    model: 'gpt-5.4-mini',
  },
  {
    label: 'Anthropic Claude',
    value: 'anthropic',
    protocol: 'Messages API',
    baseUrl: 'https://api.anthropic.com/v1',
    model: 'claude-sonnet-4-5',
  },
  {
    label: 'Google Gemini',
    value: 'gemini',
    protocol: 'generateContent',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta',
    model: 'gemini-2.5-flash',
  },
  {
    label: 'DeepSeek',
    value: 'deepseek',
    protocol: 'OpenAI-compatible',
    baseUrl: 'https://api.deepseek.com',
    model: 'deepseek-v4-flash',
  },
  {
    label: '通义千问 DashScope',
    value: 'qwen',
    protocol: 'OpenAI-compatible',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'qwen-plus',
  },
  {
    label: 'Kimi',
    value: 'kimi',
    protocol: 'OpenAI-compatible',
    baseUrl: 'https://api.moonshot.ai/v1',
    model: 'kimi-k2-turbo-preview',
  },
  {
    label: '智谱 GLM',
    value: 'zhipu',
    protocol: 'OpenAI-compatible',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    model: 'glm-4.7-flash',
  },
  {
    label: 'OpenRouter',
    value: 'openrouter',
    protocol: 'OpenAI-compatible',
    baseUrl: 'https://openrouter.ai/api/v1',
    model: 'openai/gpt-5-mini',
  },
  {
    label: '小米 MiMo',
    value: 'xiaomi_mimo',
    protocol: 'OpenAI-compatible',
    baseUrl: 'https://api.xiaomimimo.com/v1',
    model: 'mimo-v2.5-pro',
  },
  {
    label: '小米 MiMo 会员',
    value: 'xiaomi_mimo_token_plan',
    protocol: 'OpenAI-compatible',
    baseUrl: 'https://token-plan-cn.xiaomimimo.com/v1',
    model: 'mimo-v2.5-pro',
  },
  {
    label: '自定义 OpenAI 兼容',
    value: 'custom_openai',
    protocol: 'OpenAI-compatible',
    baseUrl: '',
    model: '',
  },
] as const satisfies readonly {
  label: string
  value: AiProviderPreset
  protocol: string
  baseUrl: string
  model: string
}[]

export type AiProviderPresetOption = (typeof AI_PROVIDER_PRESETS)[number]
export type SharedAiProviderPreset = AiProviderPresetOption['value']

export function getAiProviderPresetDefaults(
  provider: AiProviderPreset,
): { baseUrl: string; model: string } {
  const normalizedProvider =
    provider === 'custom_openai_compatible' ? 'custom_openai' : provider
  const preset = AI_PROVIDER_PRESETS.find((option) => option.value === normalizedProvider)
  return {
    baseUrl: preset?.baseUrl ?? '',
    model: preset?.model ?? '',
  }
}

export function normalizeSharedAiProviderPreset(
  value: string,
): SharedAiProviderPreset | null {
  const normalizedValue = value === 'custom_openai_compatible' ? 'custom_openai' : value
  const preset = AI_PROVIDER_PRESETS.find((option) => option.value === normalizedValue)
  return preset?.value ?? null
}
