<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  apiDeleteFeishuBotConfig,
  apiGetFeishuBotConfig,
  apiUpsertFeishuBotConfig,
} from '../../api/admin'
import type {
  FeishuBotConfig,
  FeishuBotConfigPayload,
} from '../../types/admin'
import AppCard from '../shell/AppCard.vue'
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

const props = withDefaults(defineProps<Props>(), {
  projectName: '',
})

interface BotForm {
  appId: string
  appSecret: string
  defaultChatId: string
  allowedOpenIds: string
  localDownloadRoots: string
  svnDownloadRoots: string
  allowedDownloadSuffixes: string
}

const config = ref<FeishuBotConfig | null>(null)
const isLoading = ref(false)
const isSaving = ref(false)
const isClearing = ref(false)
const isTestDialogVisible = ref(false)

const form = reactive<BotForm>({
  appId: '',
  appSecret: '',
  defaultChatId: '',
  allowedOpenIds: '',
  localDownloadRoots: '',
  svnDownloadRoots: '',
  allowedDownloadSuffixes: '.xls,.xlsx,.csv,.json,.xml,.txt',
})

watch(
  () => props.projectId,
  async (next) => {
    if (next === null) {
      resetForm()
      config.value = null
      return
    }
    await loadConfig(next)
  },
  { immediate: true },
)

function resetForm(): void {
  form.appId = ''
  form.appSecret = ''
  form.defaultChatId = ''
  form.allowedOpenIds = ''
  form.localDownloadRoots = ''
  form.svnDownloadRoots = ''
  form.allowedDownloadSuffixes = '.xls,.xlsx,.csv,.json,.xml,.txt'
}

function applyConfigToForm(next: FeishuBotConfig): void {
  // appSecret 永远不会从后端回传，回填时统一留空：留空 = 保持原值。
  form.appId = next.app_id
  form.appSecret = ''
  form.defaultChatId = next.default_chat_id
  form.allowedOpenIds = next.allowed_open_ids.join('\n')
  form.localDownloadRoots = next.local_download_roots.join('\n')
  form.svnDownloadRoots = next.svn_download_roots.join('\n')
  form.allowedDownloadSuffixes = next.allowed_download_suffixes.join(',')
}

async function loadConfig(projectId: number): Promise<void> {
  isLoading.value = true
  try {
    const response = await apiGetFeishuBotConfig(projectId)
    config.value = response.data
    applyConfigToForm(response.data)
  } catch (error) {
    ElMessage.error(
      error instanceof Error ? error.message : '加载飞书机器人配置失败',
    )
    config.value = null
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

const canSave = computed(() => {
  if (props.projectId === null) return false
  if (!form.appId.trim()) return false
  if (!hasAppSecret.value && !form.appSecret.trim()) return false
  return true
})

function buildPayload(): FeishuBotConfigPayload {
  const payload: FeishuBotConfigPayload = { app_id: form.appId.trim() }
  // appSecret 留空时显式传 null：等价于「保持原值」；后端首次创建会拒绝 null。
  payload.app_secret = form.appSecret.trim() ? form.appSecret : null
  // default_chat_id 始终下发（含空串），允许把已有值改成空。
  payload.default_chat_id = form.defaultChatId.trim()
  // allowed_open_ids 同样始终下发原文，由后端做去重 / 拼接。
  payload.allowed_open_ids = form.allowedOpenIds
  payload.local_download_roots = form.localDownloadRoots
  payload.svn_download_roots = form.svnDownloadRoots
  payload.allowed_download_suffixes = form.allowedDownloadSuffixes
  return payload
}

async function handleSave(): Promise<void> {
  if (props.projectId === null) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (!canSave.value) {
    ElMessage.warning(
      hasAppSecret.value
        ? '请填写 App ID'
        : '首次保存请填写 App ID 与 App Secret',
    )
    return
  }
  isSaving.value = true
  try {
    await apiUpsertFeishuBotConfig(props.projectId, buildPayload())
    ElMessage.success('飞书机器人配置已保存')
    await loadConfig(props.projectId)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '保存配置失败')
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
          title="飞书机器人"
          description="项目级飞书自建应用机器人，长连接接入飞书，无需公网回调地址；仅作用于项目校验侧。"
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

        <div v-else class="flex flex-col gap-4">
          <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label class="mb-1.5 block text-[12px] font-medium text-ink-500">
                App ID（必填）
              </label>
              <el-input
                v-model="form.appId"
                placeholder="例如：cli_abcdef1234567890"
                maxlength="64"
                show-word-limit
              />
            </div>

            <div>
              <label class="mb-1.5 block text-[12px] font-medium text-ink-500">
                App Secret{{ hasAppSecret ? '（留空表示保持原值）' : '（首次必填）' }}
              </label>
              <el-input
                v-model="form.appSecret"
                :placeholder="hasAppSecret ? '已保存，留空保持原值' : '请填写飞书自建应用 App Secret'"
                show-password
                maxlength="256"
              />
            </div>

            <div>
              <label class="mb-1.5 block text-[12px] font-medium text-ink-500">
                默认 chat_id（可选，用于测试发送默认回填）
              </label>
              <el-input
                v-model="form.defaultChatId"
                placeholder="例如：oc_1234567890abcdef"
                maxlength="128"
              />
            </div>

            <div>
              <label class="mb-1.5 block text-[12px] font-medium text-ink-500">
                触发权限白名单 open_id（每行或英文逗号分隔，留空表示不限制）
              </label>
              <el-input
                v-model="form.allowedOpenIds"
                type="textarea"
                :rows="4"
                placeholder="例如：&#10;ou_aaa&#10;ou_bbb"
                maxlength="2048"
              />
            </div>
          </div>

          <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label class="mb-1.5 block text-[12px] font-medium text-ink-500">
                本地下载根目录（每行或英文逗号分隔）
              </label>
              <el-input
                v-model="form.localDownloadRoots"
                type="textarea"
                :rows="4"
                placeholder="例如：&#10;D:\project\configs"
                maxlength="4096"
              />
            </div>

            <div>
              <label class="mb-1.5 block text-[12px] font-medium text-ink-500">
                SVN 工作副本根目录（每行或英文逗号分隔）
              </label>
              <el-input
                v-model="form.svnDownloadRoots"
                type="textarea"
                :rows="4"
                placeholder="例如：&#10;D:\svn\game-configs"
                maxlength="4096"
              />
            </div>

            <div class="md:col-span-2">
              <label class="mb-1.5 block text-[12px] font-medium text-ink-500">
                允许下载后缀（每行或英文逗号分隔，留空恢复默认）
              </label>
              <el-input
                v-model="form.allowedDownloadSuffixes"
                placeholder=".xls,.xlsx,.csv,.json,.xml,.txt"
                maxlength="1024"
              />
            </div>
          </div>

          <div class="flex items-center justify-between gap-3">
            <p class="text-[12px] text-ink-500">
              最近更新：{{ formatUpdatedAt(config?.updated_at ?? null) }}
            </p>
            <div class="flex items-center gap-2">
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
                :disabled="!canSave || isSaving"
                @click="handleSave"
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
