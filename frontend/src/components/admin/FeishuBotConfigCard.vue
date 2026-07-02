<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  apiDeleteFeishuBotConfig,
  apiGetFeishuBotConfig,
  apiTestProjectSvnCredential,
  apiUpsertFeishuBotConfig,
} from '../../api/admin'
import {
  apiGetProjectAiConfig,
  apiSaveProjectAiConfig,
  apiTestProjectAiConfig,
} from '../../api/projectAiConfig'
import {
  applyFeishuBotConfigToForm,
  buildFeishuBotConfigPayload,
  createFeishuBotConfigFormState,
  extractFeishuBotConfigError,
  mergeDefaultChatIdIntoBoundChats,
  parseTextList,
  validateFeishuBotConfigForm,
  type FeishuBotConfigFormState,
} from '../../features/admin/feishuBotConfigForm'
import {
  PROJECT_AI_PROVIDER_OPTIONS,
  applyProjectAiConfigToForm,
  applyProjectAiProviderDefaults,
  buildProjectAiConfigPayload,
  createProjectAiConfigFormState,
  getModelOptionsForProjectAiProvider,
  validateProjectAiConfigForm,
  type ProjectAiConfigFormState,
} from '../../features/admin/projectAiConfigForm'
import type {
  FeishuBotConfig,
  ProjectSvnCredentialTestResult,
} from '../../types/admin'
import type { ProjectAiConfig } from '../../types/projectAiConfig'
import AppCard from '../shell/AppCard.vue'
import DataTable from '../shell/DataTable.vue'
import PrimaryButton from '../shell/PrimaryButton.vue'
import SecondaryButton from '../shell/SecondaryButton.vue'
import SectionHeader from '../shell/SectionHeader.vue'
import StatusBadge from '../shell/StatusBadge.vue'
import type { StatusBadgeType } from '../shell/types'
import FeishuBotTestSendDialog from './FeishuBotTestSendDialog.vue'

interface Props {
  projectId: number | null
  projectName?: string
}

type FeishuConfigSaveTarget = 'basic' | 'boundChats' | 'queryRoots' | 'svnCredential' | 'footer'

const props = withDefaults(defineProps<Props>(), {
  projectName: '',
})

const config = ref<FeishuBotConfig | null>(null)
const projectAiConfig = ref<ProjectAiConfig | null>(null)
const isLoading = ref(false)
const isSaving = ref(false)
const isSavingProjectAi = ref(false)
const isClearing = ref(false)
const isTestingSvnCredential = ref(false)
const isTestingProjectAi = ref(false)
const isTestDialogVisible = ref(false)
const formErrors = ref<string[]>([])
const formErrorTarget = ref<FeishuConfigSaveTarget | null>(null)
const projectAiErrors = ref<string[]>([])
const svnCredentialTestResult = ref<ProjectSvnCredentialTestResult | null>(null)
const svnCredentialTestError = ref('')

const form = reactive<FeishuBotConfigFormState>(createFeishuBotConfigFormState())
const projectAiForm = reactive<ProjectAiConfigFormState>(createProjectAiConfigFormState())

const ruleHints = [
  '一个 chat_id 只能绑定一个项目。',
  '相同 App ID 的 App Secret 必须一致。',
  '删除或禁用数据根不会影响历史校验记录，只影响新查询请求。',
]

watch(
  () => props.projectId,
  async (next) => {
    if (next === null) {
      resetForm()
      config.value = null
      projectAiConfig.value = null
      return
    }
    await loadConfig(next)
  },
  { immediate: true },
)

function resetForm(): void {
  Object.assign(form, createFeishuBotConfigFormState())
  Object.assign(projectAiForm, createProjectAiConfigFormState())
  formErrors.value = []
  formErrorTarget.value = null
  projectAiErrors.value = []
  svnCredentialTestResult.value = null
  svnCredentialTestError.value = ''
}

function applyConfigToForm(next: FeishuBotConfig): void {
  Object.assign(form, applyFeishuBotConfigToForm(next))
  formErrors.value = []
  formErrorTarget.value = null
  svnCredentialTestResult.value = null
  svnCredentialTestError.value = ''
}

function applyProjectAiToForm(next: ProjectAiConfig | null): void {
  Object.assign(projectAiForm, applyProjectAiConfigToForm(next))
  projectAiErrors.value = []
}

async function loadConfig(projectId: number): Promise<void> {
  isLoading.value = true
  try {
    const [feishuResponse, projectAiResponse] = await Promise.all([
      apiGetFeishuBotConfig(projectId),
      apiGetProjectAiConfig(projectId),
    ])
    config.value = feishuResponse.data
    projectAiConfig.value = projectAiResponse.data
    applyConfigToForm(feishuResponse.data)
    applyProjectAiToForm(projectAiResponse.data)
  } catch (error) {
    ElMessage.error(
      error instanceof Error ? error.message : '加载飞书机器人配置失败',
    )
    config.value = null
    projectAiConfig.value = null
    resetForm()
  } finally {
    isLoading.value = false
  }
}

const stateBadge = computed<{ type: StatusBadgeType; label: string }>(() => {
  const state = config.value?.connection_state ?? 'inactive'
  if (state === 'active') {
    return { type: 'success', label: '长连接已激活' }
  }
  if (state === 'reconnecting') {
    return { type: 'warning', label: '正在重连…' }
  }
  if (state === 'error') {
    return {
      type: 'danger',
      label: '连接异常，请检查 app_id / app_secret',
    }
  }
  return { type: 'neutral', label: '未配置 / 未激活' }
})

const isConfigured = computed(() => config.value?.configured ?? false)
const hasAppSecret = computed(() => config.value?.has_app_secret ?? false)
const boundChatIdsPreview = computed(() => parseTextList(form.boundChatIdsText))
const projectAiModelOptions = computed(() =>
  getModelOptionsForProjectAiProvider(projectAiForm.provider),
)
const isSaveDisabled = computed(() => props.projectId === null || isSaving.value)

function shouldShowFormErrors(target: FeishuConfigSaveTarget): boolean {
  return formErrors.value.length > 0 && formErrorTarget.value === target
}

function syncDefaultChatToBoundChats(): void {
  const nextBoundChatIdsText = mergeDefaultChatIdIntoBoundChats(
    form.defaultChatId,
    form.boundChatIdsText,
  )
  if (nextBoundChatIdsText !== form.boundChatIdsText) {
    form.boundChatIdsText = nextBoundChatIdsText
  }
}

async function handleSave(target: FeishuConfigSaveTarget = 'footer'): Promise<void> {
  if (props.projectId === null) {
    ElMessage.warning('请先选择项目')
    return
  }
  formErrorTarget.value = target
  syncDefaultChatToBoundChats()
  const validation = validateFeishuBotConfigForm(form, {
    hasAppSecret: hasAppSecret.value,
  })
  if (!validation.ok) {
    formErrors.value = validation.errors
    ElMessage.warning(validation.errors[0])
    return
  }
  isSaving.value = true
  try {
    const response = await apiUpsertFeishuBotConfig(
      props.projectId,
      buildFeishuBotConfigPayload(form, { hasAppSecret: hasAppSecret.value }),
    )
    config.value = response.data
    applyConfigToForm(response.data)
    ElMessage.success('飞书机器人配置已保存')
  } catch (error) {
    const message = extractFeishuBotConfigError(error)
    formErrors.value = [message]
    ElMessage.error(message)
  } finally {
    isSaving.value = false
  }
}

async function handleClear(): Promise<void> {
  if (props.projectId === null) return
  try {
    await ElMessageBox.confirm(
      '确认清除当前项目的飞书机器人配置？清除后会立即停止该项目的长连接，需要重新填写 app_id / app_secret 才能恢复。',
      '清除飞书机器人配置',
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

  isClearing.value = true
  try {
    await apiDeleteFeishuBotConfig(props.projectId)
    ElMessage.success('飞书机器人配置已清除')
    await loadConfig(props.projectId)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '清除配置失败')
  } finally {
    isClearing.value = false
  }
}

function handleOpenTest(): void {
  if (!isConfigured.value) {
    ElMessage.warning('请先保存配置后再测试发送')
    return
  }
  isTestDialogVisible.value = true
}

function addQueryRoot(): void {
  form.queryRoots.push({
    alias: '',
    displayName: '',
    svnUrl: '',
    enabled: true,
  })
}

function removeQueryRoot(index: number): void {
  form.queryRoots.splice(index, 1)
}

function startEditSvnCredential(): void {
  form.svnCredential.isEditing = true
}

function cancelEditSvnCredential(): void {
  form.svnCredential.isEditing = false
  form.svnCredential.password = ''
  form.svnCredential.username = config.value?.svn_credential.username_masked ?? ''
}

async function handleSvnCredentialTest(): Promise<void> {
  if (props.projectId === null) {
    ElMessage.warning('请先选择项目')
    return
  }
  isTestingSvnCredential.value = true
  svnCredentialTestResult.value = null
  svnCredentialTestError.value = ''
  try {
    const response = await apiTestProjectSvnCredential(props.projectId)
    svnCredentialTestResult.value = response.data
    if (response.data.status === 'success') {
      ElMessage.success('项目级 SVN 连接测试成功')
    } else {
      ElMessage.warning('项目级 SVN 连接测试存在失败项')
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : '项目级 SVN 连接测试失败'
    svnCredentialTestError.value = message
    ElMessage.error(message)
  } finally {
    isTestingSvnCredential.value = false
  }
}

function handleProjectAiProviderChange(): void {
  applyProjectAiProviderDefaults(projectAiForm, projectAiForm.provider)
}

async function handleSaveProjectAiConfig(): Promise<void> {
  if (props.projectId === null) {
    ElMessage.warning('请先选择项目')
    return
  }
  const validation = validateProjectAiConfigForm(projectAiForm)
  if (!validation.ok) {
    projectAiErrors.value = validation.errors
    ElMessage.warning(validation.errors[0])
    return
  }
  isSavingProjectAi.value = true
  try {
    const response = await apiSaveProjectAiConfig(
      props.projectId,
      buildProjectAiConfigPayload(projectAiForm),
    )
    projectAiConfig.value = response.data
    applyProjectAiToForm(response.data)
    ElMessage.success('项目级 AI 配置已保存')
  } catch (error) {
    const message = error instanceof Error ? error.message : '保存项目级 AI 配置失败'
    projectAiErrors.value = [message]
    ElMessage.error(message)
  } finally {
    isSavingProjectAi.value = false
  }
}

async function handleTestProjectAiConfig(): Promise<void> {
  if (props.projectId === null) return
  if (!projectAiForm.configured) {
    ElMessage.warning('请先保存项目级 AI 配置后再测试连接')
    return
  }
  isTestingProjectAi.value = true
  try {
    const response = await apiTestProjectAiConfig(props.projectId)
    projectAiConfig.value = response.data
    applyProjectAiToForm(response.data)
    ElMessage.success('项目级 AI 连接测试成功')
  } catch (error) {
    const message = error instanceof Error ? error.message : '项目级 AI 连接测试失败'
    projectAiErrors.value = [message]
    if (projectAiConfig.value) {
      await loadProjectAiConfigOnly(props.projectId)
      projectAiErrors.value = [message]
    }
    ElMessage.error(message)
  } finally {
    isTestingProjectAi.value = false
  }
}

async function loadProjectAiConfigOnly(projectId: number): Promise<void> {
  try {
    const response = await apiGetProjectAiConfig(projectId)
    projectAiConfig.value = response.data
    applyProjectAiToForm(response.data)
  } catch {
    // 保留测试失败时的错误展示，不用二次加载错误覆盖用户可见信息。
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
  >
    <div class="admin-dashboard-card__inner">
      <div class="admin-dashboard-card__header">
        <SectionHeader
          variant="workbench"
          step="04"
          title="飞书机器人基础配置"
          description="配置飞书机器人基础信息、群绑定、配置表查询数据根与项目级凭据状态。"
        >
          <template #actions>
            <StatusBadge :type="stateBadge.type" :label="stateBadge.label" />
          </template>
        </SectionHeader>
      </div>

      <div class="admin-dashboard-card__body">
        <div v-if="props.projectId === null" class="admin-empty-panel">
          <p class="text-[13px] text-ink-500">请先在上方选择项目，再配置该项目的飞书机器人。</p>
        </div>

        <div v-else class="feishu-admin-panel">
          <div v-if="shouldShowFormErrors('footer')" class="feishu-form-errors">
            <strong>配置未保存</strong>
            <span v-for="error in formErrors" :key="error">{{ error }}</span>
          </div>

          <section class="feishu-admin-section" data-testid="feishu-basic-section">
            <div class="feishu-admin-section__head">
              <div>
                <h3>基础连接信息</h3>
                <p>保留现有保存逻辑，以下字段仍写入当前项目的飞书机器人配置。</p>
              </div>
              <div class="feishu-section-actions">
                <span class="feishu-admin-project">{{ props.projectName || '当前项目' }}</span>
                <PrimaryButton
                  size="sm"
                  :disabled="isSaveDisabled"
                  @click="handleSave('basic')"
                >
                  {{ isSaving ? '保存中…' : '保存基础配置' }}
                </PrimaryButton>
              </div>
            </div>
            <div v-if="shouldShowFormErrors('basic')" class="feishu-form-errors feishu-section-errors">
              <strong>配置未保存</strong>
              <span v-for="error in formErrors" :key="error">{{ error }}</span>
            </div>

            <div class="feishu-admin-form-grid">
              <div>
                <label>App ID（必填）</label>
                <el-input
                  v-model="form.appId"
                  name="feishu-app-id"
                  autocomplete="off"
                  spellcheck="false"
                  placeholder="例如：cli_abcdef1234567890…"
                  maxlength="64"
                  show-word-limit
                />
              </div>

              <div>
                <label>App Secret{{ hasAppSecret ? '（留空表示保持原值）' : '（首次必填）' }}</label>
                <el-input
                  v-model="form.appSecret"
                  name="feishu-app-secret"
                  autocomplete="new-password"
                  spellcheck="false"
                  :placeholder="hasAppSecret ? '已保存，留空保持原值…' : '请填写飞书自建应用 App Secret…'"
                  show-password
                  maxlength="256"
                />
              </div>

              <div>
                <label>默认 chat_id（可选，用于测试发送默认回填）</label>
                <el-input
                  v-model="form.defaultChatId"
                  name="default-chat-id"
                  autocomplete="off"
                  spellcheck="false"
                  data-testid="feishu-default-chat-id-input"
                  placeholder="例如：oc_1234567890abcdef…"
                  maxlength="128"
                  @change="syncDefaultChatToBoundChats"
                />
              </div>

              <div>
                <label>触发权限白名单 open_id（每行或英文逗号分隔，留空表示不限制）</label>
                <el-input
                  v-model="form.allowedOpenIds"
                  type="textarea"
                  name="allowed-open-ids"
                  autocomplete="off"
                  spellcheck="false"
                  :rows="4"
                  placeholder="例如：&#10;ou_aaa&#10;ou_bbb…"
                  maxlength="2048"
                />
              </div>

              <div>
                <label>本地下载根目录（每行或英文逗号分隔）</label>
                <el-input
                  v-model="form.localDownloadRoots"
                  type="textarea"
                  name="local-download-roots"
                  autocomplete="off"
                  spellcheck="false"
                  :rows="4"
                  placeholder="例如：&#10;D:\project\configs…"
                  maxlength="4096"
                />
              </div>

              <div>
                <label>SVN 下载根目录 / 工作副本目录（旧功能下载、目录查询使用）</label>
                <el-input
                  v-model="form.svnDownloadRoots"
                  type="textarea"
                  name="svn-download-roots"
                  autocomplete="off"
                  spellcheck="false"
                  :rows="4"
                  placeholder="例如：&#10;D:\svn\game-configs…"
                  maxlength="4096"
                />
              </div>

              <div class="feishu-admin-form-grid__wide">
                <label>允许下载后缀（每行或英文逗号分隔，留空恢复默认）</label>
                <el-input
                  v-model="form.allowedDownloadSuffixes"
                  name="allowed-download-suffixes"
                  autocomplete="off"
                  spellcheck="false"
                  placeholder=".xls,.xlsx,.csv,.json,.xml,.txt…"
                  maxlength="1024"
                />
              </div>
            </div>
          </section>

          <section class="feishu-admin-section">
            <div class="feishu-admin-section__head">
              <div>
                <h3>已绑定群列表 bound_chat_ids</h3>
                <p>项目绑定群用于把同一 App ID 的消息路由回正确项目。</p>
              </div>
              <PrimaryButton
                size="sm"
                :disabled="isSaveDisabled"
                @click="handleSave('boundChats')"
              >
                {{ isSaving ? '保存中…' : '保存绑定群' }}
              </PrimaryButton>
            </div>
            <div v-if="shouldShowFormErrors('boundChats')" class="feishu-form-errors feishu-section-errors">
              <strong>配置未保存</strong>
              <span v-for="error in formErrors" :key="error">{{ error }}</span>
            </div>
            <el-input
              v-model="form.boundChatIdsText"
              type="textarea"
              name="bound-chat-ids"
              autocomplete="off"
              spellcheck="false"
              :rows="3"
              placeholder="每行一个 chat_id，例如：&#10;oc_default&#10;oc_backup…"
            />
            <div class="feishu-chat-tags">
              <span
                v-for="chatId in boundChatIdsPreview"
                :key="chatId"
                class="feishu-chat-tag"
              >
                {{ chatId }}
              </span>
            </div>
            <div class="feishu-inline-tip">
              default_chat_id 会自动加入绑定群列表
            </div>
          </section>

          <section class="feishu-admin-section" data-testid="feishu-query-roots-section">
            <div class="feishu-admin-section__head">
              <div>
                <h3>配置表查询数据根 query_roots</h3>
                <p>query_roots 仅用于配置表查询读取 SVN 配置文件，与 SVN 下载根目录分开展示。</p>
              </div>
              <div class="feishu-section-actions">
                <SecondaryButton
                  size="sm"
                  :disabled="isSaveDisabled"
                  @click="handleSave('queryRoots')"
                >
                  {{ isSaving ? '保存中…' : '保存数据根' }}
                </SecondaryButton>
                <PrimaryButton size="sm" @click="addQueryRoot">
                  新增数据根
                </PrimaryButton>
              </div>
            </div>
            <div v-if="shouldShowFormErrors('queryRoots')" class="feishu-form-errors feishu-section-errors">
              <strong>配置未保存</strong>
              <span v-for="error in formErrors" :key="error">{{ error }}</span>
            </div>
            <DataTable aria-label="配置表查询数据根">
              <template #head>
                <tr>
                  <th class="w-[150px]">alias</th>
                  <th class="w-[180px]">显示名称</th>
                  <th>SVN 根地址</th>
                  <th class="w-[110px]">状态</th>
                  <th class="w-[120px]">操作</th>
                </tr>
              </template>
              <template #body>
                <tr
                  v-for="(root, index) in form.queryRoots"
                  :key="`${root.alias}-${index}`"
                  class="bg-white transition hover:bg-gray-50"
                >
                  <td>
                    <el-input
                      v-model="root.alias"
                      size="small"
                      :name="`query-root-alias-${index}`"
                      autocomplete="off"
                      spellcheck="false"
                      placeholder="game_datas…"
                    />
                  </td>
                  <td>
                    <el-input
                      v-model="root.displayName"
                      size="small"
                      :name="`query-root-name-${index}`"
                      autocomplete="off"
                      placeholder="游戏配置主目录…"
                    />
                  </td>
                  <td>
                    <el-input
                      v-model="root.svnUrl"
                      size="small"
                      :name="`query-root-url-${index}`"
                      type="url"
                      autocomplete="off"
                      spellcheck="false"
                      placeholder="https://svn.example.com/game…"
                    />
                  </td>
                  <td>
                    <div class="feishu-query-root-status">
                      <StatusBadge
                        :type="root.enabled ? 'success' : 'neutral'"
                        :label="root.enabled ? '已启用' : '已禁用'"
                      />
                      <el-switch v-model="root.enabled" size="small" />
                    </div>
                  </td>
                  <td>
                    <div class="table-actions">
                      <button type="button" class="ec-action-link-danger" @click="removeQueryRoot(index)">
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              </template>
            </DataTable>
          </section>

          <div class="feishu-admin-two-column">
            <section class="feishu-admin-section">
              <div class="feishu-admin-section__head">
                <div>
                  <h3>项目级凭据状态</h3>
                  <p>凭据内容脱敏展示；更新凭据后随本卡片保存按钮一起提交。</p>
                </div>
              </div>
              <div v-if="shouldShowFormErrors('svnCredential')" class="feishu-form-errors feishu-section-errors">
                <strong>配置未保存</strong>
                <span v-for="error in formErrors" :key="error">{{ error }}</span>
              </div>
              <div class="feishu-credential-list">
                <div class="feishu-credential-item">
                  <div class="feishu-credential-item__main">
                    <div class="feishu-credential-item__title">
                      <strong>SVN 凭据状态</strong>
                      <StatusBadge
                        :type="form.svnCredential.configured ? 'success' : 'neutral'"
                        :label="form.svnCredential.configured ? '已配置' : '未配置'"
                      />
                    </div>
                    <p>账号：{{ form.svnCredential.username || '-' }}</p>
                    <p>密码：{{ form.svnCredential.configured ? '********' : '-' }}</p>
                    <p>最后更新：{{ formatUpdatedAt(form.svnCredential.updatedAt) }}</p>
                  </div>
                  <div class="feishu-credential-item__actions">
                    <SecondaryButton size="sm" @click="startEditSvnCredential">
                      更新凭据
                    </SecondaryButton>
                    <SecondaryButton
                      size="sm"
                      :disabled="isTestingSvnCredential"
                      @click="handleSvnCredentialTest"
                    >
                      {{ isTestingSvnCredential ? '测试中…' : '连接测试' }}
                    </SecondaryButton>
                  </div>
                </div>
                <div v-if="form.svnCredential.isEditing" class="feishu-credential-edit">
                  <label>
                    <span>SVN 用户名</span>
                    <el-input
                      v-model="form.svnCredential.username"
                      name="svn-username"
                      autocomplete="off"
                      spellcheck="false"
                      placeholder="svn_admin…"
                    />
                  </label>
                  <label>
                    <span>SVN 密码（留空表示保持原值）</span>
                    <el-input
                      v-model="form.svnCredential.password"
                      name="svn-password"
                      autocomplete="new-password"
                      spellcheck="false"
                      show-password
                      placeholder="留空保持原值…"
                    />
                  </label>
                  <SecondaryButton size="sm" @click="cancelEditSvnCredential">
                    取消更新
                  </SecondaryButton>
                  <PrimaryButton
                    size="sm"
                    :disabled="isSaveDisabled"
                    @click="handleSave('svnCredential')"
                  >
                    {{ isSaving ? '保存中…' : '保存 SVN 凭据' }}
                  </PrimaryButton>
                </div>
                <div
                  v-if="svnCredentialTestError"
                  class="feishu-svn-test-result feishu-svn-test-result--failed"
                >
                  <strong>连接测试失败</strong>
                  <span>{{ svnCredentialTestError }}</span>
                </div>
                <div
                  v-else-if="svnCredentialTestResult"
                  class="feishu-svn-test-result"
                >
                  <strong>
                    连接测试{{ svnCredentialTestResult.status === 'success' ? '成功' : '存在失败项' }}
                  </strong>
                  <div class="feishu-svn-test-items">
                    <div
                      v-for="item in svnCredentialTestResult.items"
                      :key="`${item.alias}:${item.svn_url}`"
                      class="feishu-svn-test-item"
                    >
                      <StatusBadge
                        :type="item.status === 'success' ? 'success' : 'danger'"
                        :label="item.status === 'success' ? '成功' : '失败'"
                      />
                      <span class="feishu-svn-test-item__alias">{{ item.alias }}</span>
                      <span class="feishu-svn-test-item__message">
                        {{ item.message }}
                        <template v-if="item.status === 'success'">
                          · {{ item.entry_count }} 项
                        </template>
                      </span>
                    </div>
                  </div>
                </div>

              </div>
            </section>

            <section class="feishu-admin-section">
              <div class="feishu-admin-section__head">
                <div>
                  <h3>项目级 AI 凭据与名称匹配参数</h3>
                  <p>用于后续配置表查询名称匹配；不参与 Markdown 解析和规则修改。</p>
                </div>
                <StatusBadge
                  :type="projectAiForm.configured ? 'success' : 'neutral'"
                  :label="projectAiForm.configured ? '已配置' : '未配置'"
                />
              </div>
              <div v-if="projectAiErrors.length" class="feishu-form-errors feishu-project-ai-errors">
                <strong>AI 配置未保存</strong>
                <span v-for="error in projectAiErrors" :key="error">{{ error }}</span>
              </div>
              <div class="feishu-project-ai-status">
                <p>密钥：{{ projectAiForm.maskedApiKey || '-' }}</p>
                <p>最后测试：{{ projectAiForm.lastTestStatus || '未测试' }}</p>
                <p>测试时间：{{ formatUpdatedAt(projectAiForm.lastTestAt) }}</p>
              </div>
              <div class="feishu-ai-form-grid">
                <label>
                  <span>AI 提供商</span>
                  <el-select
                    v-model="projectAiForm.provider"
                    @change="handleProjectAiProviderChange"
                  >
                    <el-option
                      v-for="item in PROJECT_AI_PROVIDER_OPTIONS"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </el-select>
                </label>
                <label>
                  <span>启用状态</span>
                  <el-switch
                    v-model="projectAiForm.enabled"
                    active-text="启用"
                    inactive-text="停用"
                  />
                </label>
                <label>
                  <span>模型</span>
                  <el-select
                    v-if="projectAiModelOptions.length"
                    v-model="projectAiForm.model"
                  >
                    <el-option
                      v-for="model in projectAiModelOptions"
                      :key="model"
                      :label="model"
                      :value="model"
                    />
                  </el-select>
                  <el-input
                    v-else
                    v-model="projectAiForm.model"
                    name="project-ai-model"
                    autocomplete="off"
                    spellcheck="false"
                    placeholder="请输入模型名…"
                  />
                </label>
                <label>
                  <span>Base URL</span>
                  <el-input
                    v-model="projectAiForm.baseUrl"
                    name="project-ai-base-url"
                    type="url"
                    autocomplete="off"
                    spellcheck="false"
                    placeholder="https://api.example.com/v1…"
                  />
                </label>
              </div>
              <div class="feishu-ai-param-list">
                <label>
                  <span>API Key（留空表示保持原值）</span>
                  <el-input
                    v-model="projectAiForm.apiKey"
                    name="project-ai-api-key"
                    autocomplete="new-password"
                    spellcheck="false"
                    show-password
                    placeholder="已保存时留空保持原值…"
                  />
                </label>
                <label>
                  <span>高置信自动返回阈值</span>
                  <el-input
                    v-model="projectAiForm.autoMatchThreshold"
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                  />
                </label>
                <label>
                  <span>候选列表阈值</span>
                  <el-input
                    v-model="projectAiForm.candidateThreshold"
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                  />
                </label>
                <label>
                  <span>最大候选数量</span>
                  <el-input
                    v-model="projectAiForm.maxCandidates"
                    type="number"
                    min="1"
                    max="20"
                    step="1"
                  />
                </label>
              </div>
              <div class="feishu-project-ai-actions">
                <SecondaryButton
                  size="sm"
                  :disabled="isTestingProjectAi || isSavingProjectAi"
                  @click="handleTestProjectAiConfig"
                >
                  {{ isTestingProjectAi ? '测试中…' : '连接测试' }}
                </SecondaryButton>
                <PrimaryButton
                  size="sm"
                  :disabled="isSavingProjectAi"
                  @click="handleSaveProjectAiConfig"
                >
                  {{ isSavingProjectAi ? '保存中…' : '保存 AI 配置' }}
                </PrimaryButton>
              </div>
            </section>
          </div>

          <section class="feishu-admin-section feishu-hints-section">
            <div class="feishu-admin-section__head">
              <div>
                <h3>关键校验规则提示</h3>
              </div>
            </div>
            <div class="feishu-rule-hints">
              <div
                v-for="hint in ruleHints"
                :key="hint"
                class="feishu-rule-hint"
              >
                <span class="feishu-rule-hint__dot"></span>
                <span>{{ hint }}</span>
              </div>
            </div>
          </section>

          <div class="feishu-admin-footer">
            <p>
              最近更新：{{ formatUpdatedAt(config?.updated_at ?? null) }}
            </p>
            <div class="feishu-admin-footer__actions">
              <SecondaryButton
                v-if="isConfigured"
                :disabled="isClearing || isSaving"
                @click="handleClear"
              >
                {{ isClearing ? '清除中…' : '清除配置' }}
              </SecondaryButton>
              <SecondaryButton
                v-if="isConfigured"
                :disabled="isSaving"
                @click="handleOpenTest"
              >
                测试发送
              </SecondaryButton>
              <PrimaryButton
                :disabled="isSaveDisabled"
                @click="handleSave('footer')"
              >
                {{ isSaving ? '保存中…' : '保存配置' }}
              </PrimaryButton>
            </div>
          </div>
        </div>
      </div>
    </div>

    <FeishuBotTestSendDialog
      v-model="isTestDialogVisible"
      :project-id="props.projectId"
      :default-chat-id="config?.default_chat_id ?? ''"
      :configured="isConfigured"
    />
  </AppCard>
</template>

<style scoped>
.feishu-admin-panel,
.feishu-admin-section,
.feishu-admin-two-column {
  min-width: 0;
}

.feishu-admin-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.feishu-form-errors {
  display: flex;
  flex-direction: column;
  gap: 6px;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #991b1b;
  background: #fef2f2;
  font-size: 13px;
  line-height: 1.45;
  padding: 12px 14px;
}

.feishu-form-errors strong {
  color: #7f1d1d;
  font-weight: 850;
}

.feishu-section-errors {
  margin-bottom: 14px;
}

.feishu-admin-section {
  border: 1px solid #eef2f7;
  border-radius: 10px;
  background: #fbfcff;
  padding: 16px;
}

.feishu-admin-section__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.feishu-admin-section__head h3 {
  margin: 0;
  color: var(--color-text-main);
  font-size: 15px;
  font-weight: 850;
  line-height: 1.3;
}

.feishu-admin-section__head p {
  margin: 5px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.5;
}

.feishu-section-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.feishu-admin-project {
  display: inline-flex;
  min-height: 28px;
  flex: 0 0 auto;
  align-items: center;
  border-radius: var(--radius-pill);
  color: var(--color-primary-hover);
  background: var(--color-primary-soft);
  font-size: 12px;
  font-weight: 800;
  padding: 0 10px;
}

.feishu-admin-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.feishu-admin-form-grid label,
.feishu-ai-param-list label,
.feishu-credential-edit label,
.feishu-ai-form-grid label {
  display: block;
  margin-bottom: 6px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.35;
}

.feishu-admin-form-grid__wide {
  grid-column: 1 / -1;
}

.feishu-chat-tags {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  gap: 10px;
}

.feishu-chat-tag {
  display: inline-flex;
  min-height: 30px;
  max-width: 100%;
  align-items: center;
  overflow: hidden;
  border: 1px solid #dbe5f3;
  border-radius: 7px;
  color: #334155;
  background: #ffffff;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 0 10px;
}

.feishu-inline-tip {
  display: inline-flex;
  width: fit-content;
  max-width: 100%;
  align-items: center;
  margin-top: 12px;
  border-radius: 8px;
  color: var(--color-primary-hover);
  background: var(--color-primary-soft);
  font-size: 12px;
  font-weight: 750;
  line-height: 1.4;
  padding: 8px 10px;
}

.feishu-query-root-status {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.feishu-admin-two-column {
  display: grid;
  grid-template-columns: 1fr;
  gap: 14px;
}

.feishu-credential-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.feishu-credential-item {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid var(--color-border-light);
  border-radius: 8px;
  background: #ffffff;
  padding: 14px;
}

.feishu-credential-item__main {
  min-width: 0;
}

.feishu-credential-item__title {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.feishu-credential-item__title strong {
  color: var(--color-text-main);
  font-size: 14px;
  font-weight: 850;
}

.feishu-credential-item p {
  margin: 7px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.35;
}

.feishu-credential-item__actions,
.feishu-admin-footer__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.feishu-svn-test-result {
  display: flex;
  flex-direction: column;
  gap: 10px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  color: #1e3a8a;
  background: #eff6ff;
  font-size: 12px;
  line-height: 1.45;
  padding: 12px;
}

.feishu-svn-test-result strong {
  color: #1e40af;
  font-size: 13px;
  font-weight: 850;
}

.feishu-svn-test-result--failed {
  border-color: #fecaca;
  color: #991b1b;
  background: #fef2f2;
}

.feishu-svn-test-result--failed strong {
  color: #7f1d1d;
}

.feishu-svn-test-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.feishu-svn-test-item {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.feishu-svn-test-item__alias {
  color: var(--color-text-main);
  font-family: var(--font-mono);
  font-weight: 800;
}

.feishu-svn-test-item__message {
  min-width: 0;
  color: #475569;
  overflow-wrap: anywhere;
}

.feishu-credential-edit {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fbff;
  padding: 14px;
}

.feishu-project-ai-errors {
  margin-bottom: 12px;
}

.feishu-project-ai-status {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 14px;
  border: 1px solid var(--color-border-light);
  border-radius: 8px;
  background: #ffffff;
  padding: 12px;
}

.feishu-project-ai-status p {
  min-width: 0;
  overflow: hidden;
  margin: 0;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.feishu-ai-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.feishu-project-ai-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.feishu-credential-edit label {
  margin-bottom: 0;
}

.feishu-credential-edit label > span {
  display: block;
  margin-bottom: 6px;
}

.feishu-credential-edit__wide {
  grid-column: 1 / -1;
}

.feishu-ai-param-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.feishu-ai-param-list label {
  margin-bottom: 0;
}

.feishu-ai-param-list label > span {
  display: block;
  margin-bottom: 6px;
}

.feishu-rule-hints {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px 24px;
}

.feishu-rule-hint {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  gap: 8px;
  color: #475569;
  font-size: 13px;
  line-height: 1.55;
}

.feishu-rule-hint__dot {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: var(--radius-pill);
  background: var(--color-success);
  margin-top: 6px;
}

.feishu-admin-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-top: 1px solid var(--color-border);
  padding-top: 16px;
}

.feishu-admin-footer p {
  margin: 0;
  color: #64748b;
  font-size: 12px;
}

:deep(.ui-data-table) {
  width: 100%;
}

:deep(.ui-data-table td),
:deep(.ui-data-table th) {
  white-space: normal;
}

@media (max-width: 1180px) {
  .feishu-admin-two-column {
    grid-template-columns: 1fr;
  }

  .feishu-rule-hints {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .feishu-admin-section__head,
  .feishu-credential-item,
  .feishu-admin-footer {
    align-items: stretch;
    flex-direction: column;
  }

  .feishu-admin-form-grid {
    grid-template-columns: 1fr;
  }

  .feishu-ai-form-grid,
  .feishu-ai-param-list {
    grid-template-columns: 1fr;
  }

  .feishu-credential-edit {
    grid-template-columns: 1fr;
  }

  .feishu-credential-item__actions,
  .feishu-admin-footer__actions {
    justify-content: flex-start;
  }

  .feishu-chat-tag {
    width: 100%;
  }
}
</style>
