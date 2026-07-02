<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  apiDeleteProjectVisionAiConfig,
  apiGetProjectVisionAiConfig,
  apiGetSourceEvidenceSvnRoots,
  apiSaveProjectVisionAiConfig,
  apiSaveSourceEvidenceSvnRoots,
  apiTestProjectVisionAiConfig,
} from '../../api/admin'
import {
  AI_PROVIDER_PRESETS,
  getAiProviderPresetDefaults,
  normalizeSharedAiProviderPreset,
} from '../../features/ai/providerPresets'
import { ApiRequestError } from '../../utils/apiFetch'
import type {
  ProjectVisionAiConfig,
  SourceEvidenceSvnRoot,
} from '../../types/admin'
import type { AiProviderPreset } from '../../types/aiProvider'
import AppCard from '../shell/AppCard.vue'
import PrimaryButton from '../shell/PrimaryButton.vue'
import SecondaryButton from '../shell/SecondaryButton.vue'
import SectionHeader from '../shell/SectionHeader.vue'
import StatusBadge from '../shell/StatusBadge.vue'

interface Props {
  projectId: number | null
  projectName?: string
}

interface SourceEvidenceSvnRootFormRow {
  alias: string
  displayName: string
  svnUrl: string
  enabled: boolean
}

interface VisionAiFormState {
  configured: boolean
  enabled: boolean
  provider: AiProviderPreset
  model: string
  baseUrl: string
  apiKey: string
  maskedApiKey: string
  lastTestStatus: string
  lastTestAt: string | null
  lastTestErrorSummary: string
  updatedAt: string | null
}

interface VisionProviderPreset {
  label: string
  value: AiProviderPreset
  baseUrl: string
  model: string
  guidance: string
}

interface VisionProviderNotice {
  tone: 'info' | 'warning'
  message: string
}

const VISION_PROVIDER_PRESETS = [
  {
    label: 'OpenAI（视觉）',
    value: 'openai',
    baseUrl: 'https://api.openai.com/v1',
    model: 'gpt-5.4-mini',
    guidance: '请确认当前账号已开通支持 image input 的模型；Source Evidence 会用 OpenAI-compatible image_url 协议做图片 observation。',
  },
  {
    label: '通义千问 Qwen-VL',
    value: 'qwen',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'qwen3.7-plus',
    guidance: '请使用支持图片输入的 Qwen 视觉模型；百炼业务空间专属域名也可手动填入 Base URL，qwen-plus/qwen3.6-plus 等文本模型不能用于 Source Evidence 图片 observation。',
  },
  {
    label: '智谱 GLM-V',
    value: 'zhipu',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    model: 'glm-5v-turbo',
    guidance: '请使用 GLM-5V-Turbo 等视觉模型；glm-5.2 等文本模型不能用于 Source Evidence 图片 observation。',
  },
  {
    label: 'OpenRouter（视觉模型）',
    value: 'openrouter',
    baseUrl: 'https://openrouter.ai/api/v1',
    model: 'openai/gpt-5-mini',
    guidance: '请在 OpenRouter 选择带 image input / vision 能力的模型；只支持 OpenAI-compatible chat/completions 图片输入。',
  },
  {
    label: '自定义 OpenAI 兼容视觉模型',
    value: 'custom_openai',
    baseUrl: '',
    model: '',
    guidance: '自定义服务必须兼容 OpenAI chat/completions，并支持 messages.content 中的 image_url 图片输入。',
  },
] as const satisfies readonly VisionProviderPreset[]

const TEXT_DEFAULT_MODEL_KEYS = new Set<string>([
  'deepseek:deepseek-v4-flash',
  'qwen:qwen-plus',
  'qwen:qwen3.6-plus',
  'kimi:kimi-k2-turbo-preview',
  'zhipu:glm-4.7-flash',
  'zhipu:glm-5.2',
  'xiaomi_mimo:mimo-v2.5-pro',
  'xiaomi_mimo_token_plan:mimo-v2.5-pro',
])

const VISION_PROVIDER_VALUES = new Set<AiProviderPreset>(
  VISION_PROVIDER_PRESETS.map((option) => option.value),
)

const props = withDefaults(defineProps<Props>(), {
  projectName: '',
})

const roots = ref<SourceEvidenceSvnRootFormRow[]>([])
const visionConfig = ref<ProjectVisionAiConfig | null>(null)
const isLoading = ref(false)
const isSavingRoots = ref(false)
const isSavingVision = ref(false)
const isTestingVision = ref(false)
const isClearingVision = ref(false)
const rootErrors = ref<string[]>([])
const visionErrors = ref<string[]>([])
const visionErrorTitle = ref('Vision AI 配置保存失败')

const visionForm = reactive<VisionAiFormState>(createVisionAiFormState())

const visionProviderOptions = computed(() => {
  const options: Array<{ label: string; value: AiProviderPreset }> =
    VISION_PROVIDER_PRESETS.map(({ label, value }) => ({ label, value }))
  if (!VISION_PROVIDER_VALUES.has(visionForm.provider)) {
    options.push({
      label: `${getSharedProviderLabel(visionForm.provider)}（已保存，需确认视觉能力）`,
      value: visionForm.provider,
    })
  }
  return options
})

const visionProviderNotice = computed<VisionProviderNotice | null>(() => {
  const provider = visionForm.provider
  const model = visionForm.model.trim().toLowerCase()
  const modelKey = `${provider}:${model}`
  if (!VISION_PROVIDER_VALUES.has(provider)) {
    return {
      tone: 'warning',
      message: `${getSharedProviderLabel(provider)} 来自项目级文本 AI provider 列表，当前没有明确作为 Source Evidence 视觉模型推荐。请改用 OpenAI、Qwen-VL、OpenRouter 视觉模型，或选择自定义 OpenAI 兼容视觉模型。`,
    }
  }
  if (TEXT_DEFAULT_MODEL_KEYS.has(modelKey)) {
    return {
      tone: 'warning',
      message: `${visionForm.model.trim()} 是文本默认模型，不是明确的视觉模型；图片 observation 测试大概率会失败，请改成支持 image input 的视觉模型。`,
    }
  }
  const preset = getVisionProviderPreset(provider)
  if (!preset) {
    return null
  }
  return { tone: 'info', message: preset.guidance }
})

function isProjectVisionAiConfigPayload(value: unknown): value is ProjectVisionAiConfig {
  if (!value || typeof value !== 'object') {
    return false
  }
  const payload = value as Partial<ProjectVisionAiConfig>
  return (
    typeof payload.configured === 'boolean' &&
    typeof payload.enabled === 'boolean' &&
    typeof payload.model === 'string' &&
    typeof payload.base_url === 'string' &&
    typeof payload.masked_api_key === 'string'
  )
}

function extractVisionConfigFromApiError(error: unknown): ProjectVisionAiConfig | null {
  if (!(error instanceof ApiRequestError)) {
    return null
  }
  if (!error.payload || typeof error.payload !== 'object') {
    return null
  }
  const data = (error.payload as { data?: unknown }).data
  return isProjectVisionAiConfigPayload(data) ? data : null
}

function getVisionActionErrorMessage(error: unknown, fallback: string): string {
  const failedConfig = extractVisionConfigFromApiError(error)
  if (failedConfig?.last_test_error_summary?.trim()) {
    return failedConfig.last_test_error_summary.trim()
  }
  return error instanceof Error ? error.message : fallback
}

const hasSourceEvidenceSvnRoots = computed(() =>
  roots.value.some((root) => root.enabled && root.svnUrl.trim()),
)

const cardStatus = computed(() => {
  if (hasSourceEvidenceSvnRoots.value && visionForm.configured) {
    return { type: 'success' as const, label: '已配置' }
  }
  if (hasSourceEvidenceSvnRoots.value || visionForm.configured) {
    return { type: 'warning' as const, label: '部分配置' }
  }
  return { type: 'neutral' as const, label: '待配置' }
})

watch(
  () => props.projectId,
  async (projectId) => {
    if (projectId === null) {
      resetState()
      return
    }
    await loadConfig(projectId)
  },
  { immediate: true },
)

function createVisionAiFormState(): VisionAiFormState {
  const defaults = getVisionProviderDefaults('openai')
  return {
    configured: false,
    enabled: false,
    provider: 'openai',
    model: defaults.model,
    baseUrl: defaults.baseUrl,
    apiKey: '',
    maskedApiKey: '',
    lastTestStatus: '',
    lastTestAt: null,
    lastTestErrorSummary: '',
    updatedAt: null,
  }
}

function resetState(): void {
  roots.value = []
  visionConfig.value = null
  Object.assign(visionForm, createVisionAiFormState())
  rootErrors.value = []
  visionErrors.value = []
  visionErrorTitle.value = 'Vision AI 配置保存失败'
}

async function loadConfig(projectId: number): Promise<void> {
  isLoading.value = true
  try {
    const [rootsResponse, visionResponse] = await Promise.all([
      apiGetSourceEvidenceSvnRoots(projectId),
      apiGetProjectVisionAiConfig(projectId),
    ])
    roots.value = rootsResponse.data.items.map(rootToFormRow)
    visionConfig.value = visionResponse.data
    applyVisionConfigToForm(visionResponse.data)
    rootErrors.value = []
    visionErrors.value = []
    visionErrorTitle.value = 'Vision AI 配置保存失败'
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载 Source Evidence 配置失败')
    resetState()
  } finally {
    isLoading.value = false
  }
}

function rootToFormRow(root: SourceEvidenceSvnRoot): SourceEvidenceSvnRootFormRow {
  return {
    alias: root.alias,
    displayName: root.display_name,
    svnUrl: root.svn_url,
    enabled: root.enabled,
  }
}

function formRowToRoot(row: SourceEvidenceSvnRootFormRow): SourceEvidenceSvnRoot {
  return {
    alias: row.alias.trim(),
    display_name: row.displayName.trim(),
    svn_url: row.svnUrl.trim(),
    enabled: row.enabled,
  }
}

function normalizeVisionProvider(value: string): AiProviderPreset {
  return normalizeSharedAiProviderPreset(value) ?? 'openai'
}

function getVisionProviderPreset(provider: AiProviderPreset): VisionProviderPreset | undefined {
  return VISION_PROVIDER_PRESETS.find((option) => option.value === provider)
}

function getVisionProviderDefaults(
  provider: AiProviderPreset,
): { baseUrl: string; model: string } {
  const visionPreset = getVisionProviderPreset(provider)
  if (visionPreset) {
    return { baseUrl: visionPreset.baseUrl, model: visionPreset.model }
  }
  return getAiProviderPresetDefaults(provider)
}

function getSharedProviderLabel(provider: AiProviderPreset): string {
  const normalizedProvider =
    provider === 'custom_openai_compatible' ? 'custom_openai' : provider
  const preset = AI_PROVIDER_PRESETS.find((option) => option.value === normalizedProvider)
  return preset?.label ?? provider
}

function applyVisionConfigToForm(config: ProjectVisionAiConfig | null): void {
  Object.assign(visionForm, createVisionAiFormState())
  if (!config) {
    return
  }
  const provider = normalizeVisionProvider(config.provider)
  visionForm.configured = config.configured
  visionForm.enabled = config.enabled
  visionForm.provider = provider
  visionForm.model = config.model || getVisionProviderDefaults(provider).model
  visionForm.baseUrl = config.base_url || getVisionProviderDefaults(provider).baseUrl
  visionForm.apiKey = ''
  visionForm.maskedApiKey = config.masked_api_key
  visionForm.lastTestStatus = config.last_test_status
  visionForm.lastTestAt = config.last_test_at
  visionForm.lastTestErrorSummary = config.last_test_error_summary
  visionForm.updatedAt = config.updated_at
}

function addRoot(): void {
  roots.value.push({
    alias: '',
    displayName: '',
    svnUrl: '',
    enabled: true,
  })
}

function removeRoot(index: number): void {
  roots.value.splice(index, 1)
}

function validateRoots(): string[] {
  const errors: string[] = []
  const aliases = new Set<string>()
  for (const row of roots.value) {
    const alias = row.alias.trim()
    if (!alias) {
      errors.push('Source Evidence SVN Root alias 不能为空')
      continue
    }
    if (aliases.has(alias)) {
      errors.push(`Source Evidence SVN Root alias 重复：${alias}`)
    }
    aliases.add(alias)
    if (!row.svnUrl.trim()) {
      errors.push(`Source Evidence SVN Root URL 不能为空：${alias}`)
    }
  }
  return errors
}

async function handleSaveRoots(): Promise<void> {
  if (props.projectId === null) {
    ElMessage.warning('请先选择项目')
    return
  }
  const errors = validateRoots()
  if (errors.length) {
    rootErrors.value = errors
    ElMessage.warning(errors[0])
    return
  }
  isSavingRoots.value = true
  try {
    const response = await apiSaveSourceEvidenceSvnRoots(props.projectId, {
      items: roots.value.map(formRowToRoot),
    })
    roots.value = response.data.items.map(rootToFormRow)
    rootErrors.value = []
    ElMessage.success('Source Evidence SVN Root 已保存')
  } catch (error) {
    const message = error instanceof Error ? error.message : '保存 Source Evidence SVN Root 失败'
    rootErrors.value = [message]
    ElMessage.error(message)
  } finally {
    isSavingRoots.value = false
  }
}

function handleVisionProviderChange(): void {
  const defaults = getVisionProviderDefaults(visionForm.provider)
  visionForm.baseUrl = defaults.baseUrl
  visionForm.model = defaults.model
}

function validateVision(): string[] {
  const errors: string[] = []
  if (!visionForm.model.trim()) {
    errors.push('请填写 Vision AI 模型名称')
  }
  if (!visionForm.baseUrl.trim()) {
    errors.push('请填写 Vision AI Base URL')
  }
  if (visionForm.enabled && !visionForm.maskedApiKey && !visionForm.apiKey.trim()) {
    errors.push('启用项目级 Vision AI 前必须填写 API Key')
  }
  return errors
}

async function handleSaveVision(): Promise<void> {
  if (props.projectId === null) {
    ElMessage.warning('请先选择项目')
    return
  }
  const errors = validateVision()
  if (errors.length) {
    visionErrorTitle.value = 'Vision AI 配置校验失败'
    visionErrors.value = errors
    ElMessage.warning(errors[0])
    return
  }
  isSavingVision.value = true
  try {
    const response = await apiSaveProjectVisionAiConfig(props.projectId, {
      provider: visionForm.provider,
      model: visionForm.model.trim(),
      base_url: visionForm.baseUrl.trim(),
      api_key: visionForm.apiKey.trim() || null,
      enabled: visionForm.enabled,
    })
    visionConfig.value = response.data
    applyVisionConfigToForm(response.data)
    visionErrors.value = []
    visionErrorTitle.value = 'Vision AI 配置保存失败'
    ElMessage.success('项目级 Vision AI 配置已保存')
  } catch (error) {
    const message = getVisionActionErrorMessage(error, '保存项目级 Vision AI 配置失败')
    visionErrorTitle.value = 'Vision AI 配置保存失败'
    visionErrors.value = [message]
    ElMessage.error(message)
  } finally {
    isSavingVision.value = false
  }
}

async function handleTestVision(): Promise<void> {
  if (props.projectId === null) {
    return
  }
  if (!visionForm.configured) {
    ElMessage.warning('请先保存项目级 Vision AI 配置后再测试连接')
    return
  }
  isTestingVision.value = true
  try {
    const response = await apiTestProjectVisionAiConfig(props.projectId)
    visionConfig.value = response.data
    applyVisionConfigToForm(response.data)
    visionErrors.value = []
    visionErrorTitle.value = 'Vision AI 连接测试失败'
    ElMessage.success('项目级 Vision AI 连接测试成功')
  } catch (error) {
    const failedConfig = extractVisionConfigFromApiError(error)
    if (failedConfig) {
      visionConfig.value = failedConfig
      applyVisionConfigToForm(failedConfig)
    }
    const message = getVisionActionErrorMessage(error, '项目级 Vision AI 连接测试失败')
    visionErrorTitle.value = 'Vision AI 连接测试失败'
    visionErrors.value = [message]
    ElMessage.error(message)
  } finally {
    isTestingVision.value = false
  }
}

async function handleClearVision(): Promise<void> {
  if (props.projectId === null) {
    return
  }
  try {
    await ElMessageBox.confirm(
      '确认清除当前项目的 Vision AI 配置？清除后图片仍可提取为资源，但不能执行视觉观察。',
      '清除 Vision AI 配置',
      {
        confirmButtonText: '清除配置',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }
  isClearingVision.value = true
  try {
    await apiDeleteProjectVisionAiConfig(props.projectId)
    visionConfig.value = null
    applyVisionConfigToForm(null)
    visionErrors.value = []
    visionErrorTitle.value = 'Vision AI 配置保存失败'
    ElMessage.success('项目级 Vision AI 配置已清除')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '清除项目级 Vision AI 配置失败')
  } finally {
    isClearingVision.value = false
  }
}

function formatUpdatedAt(value: string | null): string {
  if (!value) return '尚未保存'
  return new Date(value).toLocaleString('zh-CN')
}
</script>

<template>
  <AppCard
    v-loading="isLoading"
    as="article"
    padding="none"
    class="admin-dashboard-card"
    data-test="source-evidence-admin-config-card"
  >
    <div class="admin-dashboard-card__inner">
      <div class="admin-dashboard-card__header">
        <SectionHeader
          variant="workbench"
          step="05"
          title="Source Evidence 运行配置"
          description="配置用例生成 V2 的 SVN 文件读取边界和图片视觉观察模型。"
        >
          <template #actions>
            <StatusBadge :type="cardStatus.type" :label="cardStatus.label" />
          </template>
        </SectionHeader>
      </div>

      <div class="admin-dashboard-card__body">
        <div v-if="props.projectId === null" class="admin-empty-panel">
          <p class="text-[13px] text-ink-500">请先在上方选择项目，再配置 Source Evidence 运行能力。</p>
        </div>

        <div v-else class="source-evidence-admin-panel">
          <section
            class="source-evidence-admin-section"
            data-test="source-evidence-svn-roots-section"
          >
            <div class="source-evidence-admin-section__head">
              <div>
                <h3>Source Evidence SVN Root</h3>
                <p>用于 V2 SVN 文件 Source Evidence 的项目级读取边界，不等同于配置表查询 query_roots。</p>
              </div>
              <div class="source-evidence-section-actions">
                <SecondaryButton size="sm" @click="addRoot">新增 Root</SecondaryButton>
                <PrimaryButton
                  size="sm"
                  :disabled="isSavingRoots"
                  @click="handleSaveRoots"
                >
                  {{ isSavingRoots ? '保存中…' : '保存 SVN Root' }}
                </PrimaryButton>
              </div>
            </div>

            <div v-if="rootErrors.length" class="source-evidence-form-errors">
              <strong>SVN Root 配置未保存</strong>
              <span v-for="error in rootErrors" :key="error">{{ error }}</span>
            </div>

            <div v-if="!roots.length" class="source-evidence-empty-row">
              尚未配置 Source Evidence SVN Root。SVN 文件入口会被禁用，直到至少保存一个启用的 root。
            </div>

            <div v-else class="source-evidence-root-list">
              <div
                v-for="(root, index) in roots"
                :key="`${index}:${root.alias}`"
                class="source-evidence-root-row"
                data-test="source-evidence-root-row"
              >
                <label>
                  <span>Alias</span>
                  <el-input
                    v-model="root.alias"
                    name="source-evidence-root-alias"
                    autocomplete="off"
                    spellcheck="false"
                    placeholder="game_datas"
                  />
                </label>
                <label>
                  <span>显示名</span>
                  <el-input
                    v-model="root.displayName"
                    name="source-evidence-root-display-name"
                    autocomplete="off"
                    spellcheck="false"
                    placeholder="游戏配置 SVN 根"
                  />
                </label>
                <label class="source-evidence-root-row__url">
                  <span>SVN Root URL</span>
                  <el-input
                    v-model="root.svnUrl"
                    name="source-evidence-root-url"
                    autocomplete="off"
                    spellcheck="false"
                    placeholder="https://svn.example.com/game/"
                  />
                </label>
                <label>
                  <span>启用</span>
                  <el-switch v-model="root.enabled" active-text="启用" inactive-text="停用" />
                </label>
                <SecondaryButton size="sm" @click="removeRoot(index)">删除</SecondaryButton>
              </div>
            </div>
            <div class="source-evidence-inline-tip">
              SVN 账号密码仍在上方“飞书机器人基础配置”的项目级 SVN 凭据状态中维护；这里仅维护 V2 允许读取的 SVN URL 边界。
            </div>
          </section>

          <section
            class="source-evidence-admin-section"
            data-test="source-evidence-vision-ai-section"
          >
            <div class="source-evidence-admin-section__head">
              <div>
                <h3>Project Vision AI Credential</h3>
                <p>用于 Source Evidence 图片 observation。只推荐支持图片输入的 OpenAI-compatible 视觉模型；未配置时文本/表格生成仍可继续。</p>
              </div>
              <StatusBadge
                :type="visionForm.configured ? 'success' : 'neutral'"
                :label="visionForm.configured ? '已配置' : '未配置'"
              />
            </div>

            <div v-if="visionErrors.length" class="source-evidence-form-errors">
              <strong>{{ visionErrorTitle }}</strong>
              <span v-for="error in visionErrors" :key="error">{{ error }}</span>
            </div>

            <div class="source-evidence-vision-status">
              <p>密钥：{{ visionForm.maskedApiKey || '-' }}</p>
              <p>最后测试：{{ visionForm.lastTestStatus || '未测试' }}</p>
              <p>测试时间：{{ formatUpdatedAt(visionForm.lastTestAt) }}</p>
            </div>

            <div
              v-if="visionProviderNotice"
              class="source-evidence-vision-notice"
              :class="`source-evidence-vision-notice--${visionProviderNotice.tone}`"
              data-test="source-evidence-vision-provider-notice"
            >
              {{ visionProviderNotice.message }}
            </div>

            <div class="source-evidence-vision-grid">
              <label>
                <span>视觉模型提供商</span>
                <el-select
                  v-model="visionForm.provider"
                  name="source-evidence-vision-provider"
                  autocomplete="off"
                  @change="handleVisionProviderChange"
                >
                  <el-option
                    v-for="option in visionProviderOptions"
                    :key="option.value"
                    :label="option.label"
                    :value="option.value"
                  />
                </el-select>
              </label>
              <label>
                <span>启用状态</span>
                <el-switch
                  v-model="visionForm.enabled"
                  active-text="启用"
                  inactive-text="停用"
                />
              </label>
              <label>
                <span>模型</span>
                <el-input
                  v-model="visionForm.model"
                  name="source-evidence-vision-model"
                  autocomplete="off"
                  spellcheck="false"
                  placeholder="gpt-5.4-mini / qwen3.7-plus / glm-5v-turbo"
                />
              </label>
              <label>
                <span>Base URL</span>
                <el-input
                  v-model="visionForm.baseUrl"
                  name="source-evidence-vision-base-url"
                  type="url"
                  autocomplete="off"
                  spellcheck="false"
                  placeholder="https://api.example.com/v1"
                />
              </label>
              <label class="source-evidence-vision-grid__wide">
                <span>API Key（留空表示保持原值）</span>
                <el-input
                  v-model="visionForm.apiKey"
                  name="source-evidence-vision-api-key"
                  autocomplete="new-password"
                  spellcheck="false"
                  show-password
                  placeholder="已保存时留空保持原值…"
                />
              </label>
            </div>

            <div class="source-evidence-vision-actions">
              <SecondaryButton
                v-if="visionForm.configured"
                size="sm"
                :disabled="isClearingVision || isSavingVision || isTestingVision"
                @click="handleClearVision"
              >
                {{ isClearingVision ? '清除中…' : '清除配置' }}
              </SecondaryButton>
              <SecondaryButton
                size="sm"
                :disabled="isTestingVision || isSavingVision"
                @click="handleTestVision"
              >
                {{ isTestingVision ? '测试中…' : '连接测试' }}
              </SecondaryButton>
              <PrimaryButton
                size="sm"
                :disabled="isSavingVision"
                @click="handleSaveVision"
              >
                {{ isSavingVision ? '保存中…' : '保存 Vision AI' }}
              </PrimaryButton>
            </div>
          </section>

          <section class="source-evidence-admin-section source-evidence-runtime-hints">
            <h3>运行环境提示</h3>
            <div class="source-evidence-hint-list">
              <span>LibreOffice/soffice 只能在服务端通过 `SOURCE_EVIDENCE_SOFFICE_EXECUTABLE` 配置。</span>
              <span>项目级 SVN 凭据不复用个人 SVN 凭据；Source Evidence SVN Root 不复用 Remote SVN Query Root。</span>
              <span>Vision observation 结果必须人工采纳后才会进入生成和导出。</span>
            </div>
          </section>
        </div>
      </div>
    </div>
  </AppCard>
</template>

<style scoped>
.source-evidence-admin-panel,
.source-evidence-admin-section {
  min-width: 0;
}

.source-evidence-admin-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.source-evidence-admin-section {
  border: 1px solid #eef2f7;
  border-radius: 10px;
  background: #fbfcff;
  padding: 16px;
}

.source-evidence-admin-section__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.source-evidence-admin-section__head h3,
.source-evidence-runtime-hints h3 {
  margin: 0;
  color: var(--color-text-main);
  font-size: 15px;
  font-weight: 850;
  line-height: 1.3;
}

.source-evidence-admin-section__head p {
  margin: 5px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.5;
}

.source-evidence-section-actions,
.source-evidence-vision-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.source-evidence-form-errors {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #991b1b;
  background: #fef2f2;
  font-size: 13px;
  line-height: 1.45;
  padding: 12px 14px;
}

.source-evidence-form-errors strong {
  color: #7f1d1d;
  font-weight: 850;
}

.source-evidence-empty-row,
.source-evidence-inline-tip {
  border-radius: 8px;
  color: #475569;
  background: #ffffff;
  font-size: 13px;
  line-height: 1.5;
  padding: 12px;
}

.source-evidence-root-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.source-evidence-root-row {
  display: grid;
  grid-template-columns: minmax(120px, 0.8fr) minmax(140px, 1fr) minmax(260px, 2fr) 120px auto;
  gap: 12px;
  align-items: end;
  border: 1px solid var(--color-border-light);
  border-radius: 8px;
  background: #ffffff;
  padding: 14px;
}

.source-evidence-root-row label,
.source-evidence-vision-grid label {
  min-width: 0;
  margin: 0;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.35;
}

.source-evidence-root-row label > span,
.source-evidence-vision-grid label > span {
  display: block;
  margin-bottom: 6px;
}

.source-evidence-inline-tip {
  margin-top: 12px;
  color: var(--color-primary-hover);
  background: var(--color-primary-soft);
  font-weight: 750;
}

.source-evidence-vision-status {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 14px;
  border: 1px solid var(--color-border-light);
  border-radius: 8px;
  background: #ffffff;
  padding: 12px;
}

.source-evidence-vision-status p {
  min-width: 0;
  overflow: hidden;
  margin: 0;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-evidence-vision-notice {
  margin-bottom: 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 750;
  line-height: 1.5;
  padding: 12px 14px;
}

.source-evidence-vision-notice--info {
  border: 1px solid #bfdbfe;
  color: #1d4ed8;
  background: #eff6ff;
}

.source-evidence-vision-notice--warning {
  border: 1px solid #fed7aa;
  color: #c2410c;
  background: #fff7ed;
}

.source-evidence-vision-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.source-evidence-vision-grid__wide {
  grid-column: 1 / -1;
}

.source-evidence-vision-actions {
  margin-top: 14px;
}

.source-evidence-runtime-hints {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.source-evidence-hint-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  color: #475569;
  font-size: 13px;
  line-height: 1.55;
}

.source-evidence-hint-list span {
  border-left: 3px solid var(--color-success);
  padding-left: 10px;
}

@media (max-width: 1180px) {
  .source-evidence-root-row {
    grid-template-columns: 1fr 1fr;
  }

  .source-evidence-root-row__url {
    grid-column: 1 / -1;
  }

  .source-evidence-hint-list {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .source-evidence-admin-section__head {
    align-items: stretch;
    flex-direction: column;
  }

  .source-evidence-root-row,
  .source-evidence-vision-grid,
  .source-evidence-vision-status {
    grid-template-columns: 1fr;
  }

  .source-evidence-vision-grid__wide,
  .source-evidence-root-row__url {
    grid-column: auto;
  }

  .source-evidence-section-actions,
  .source-evidence-vision-actions {
    justify-content: flex-start;
  }
}
</style>
