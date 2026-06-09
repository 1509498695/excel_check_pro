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

interface QueryRootRow {
  alias: string
  displayName: string
  svnRoot: string
  statusLabel: string
  badgeType: StatusBadgeType
}

interface CredentialStatusRow {
  label: string
  statusLabel: string
  badgeType: StatusBadgeType
  accountLabel: string
  secretLabel: string
  updatedAt: string
}

interface AiMatchParam {
  label: string
  value: string
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

const boundChatIds = [
  'oc_7c1b9f8e9f1f4c7b9c1827d9f6a2b8c5',
  'oc_a9d3e6f1b8c24d9e7a3c5f1b2d6e9a7c',
]

const queryRoots: QueryRootRow[] = [
  {
    alias: 'game_datas',
    displayName: '游戏配置主目录',
    svnRoot: 'https://samosvn.company.com/svn/GameDatas',
    statusLabel: '已启用',
    badgeType: 'success',
  },
  {
    alias: 'activity_datas',
    displayName: '活动配置目录',
    svnRoot: 'https://samosvn.company.com/svn/ActivityDatas',
    statusLabel: '已启用',
    badgeType: 'success',
  },
]

const credentialStatuses: CredentialStatusRow[] = [
  {
    label: 'SVN 凭据状态',
    statusLabel: '已连接',
    badgeType: 'success',
    accountLabel: '账号：s******n',
    secretLabel: '密码：********',
    updatedAt: '2024/05/27 01:20:11',
  },
  {
    label: 'AI 凭据状态',
    statusLabel: '已连接',
    badgeType: 'success',
    accountLabel: '模型：gpt-compatible',
    secretLabel: '密钥：************',
    updatedAt: '2024/05/27 01:20:11',
  },
]

const aiMatchParams: AiMatchParam[] = [
  { label: '高置信自动返回阈值', value: '0.90' },
  { label: '候选列表阈值', value: '0.60' },
  { label: '最大候选数量', value: '10' },
]

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

function showStaticNotice(label: string): void {
  ElMessage.info(`${label}将在后续阶段接入`)
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
          <section class="feishu-admin-section">
            <div class="feishu-admin-section__head">
              <div>
                <h3>基础连接信息</h3>
                <p>保留现有保存逻辑，以下字段仍写入当前项目的飞书机器人配置。</p>
              </div>
              <span class="feishu-admin-project">{{ props.projectName || '当前项目' }}</span>
            </div>

            <div class="feishu-admin-form-grid">
              <div>
                <label>App ID（必填）</label>
                <el-input
                  v-model="form.appId"
                  placeholder="例如：cli_abcdef1234567890"
                  maxlength="64"
                  show-word-limit
                />
              </div>

              <div>
                <label>App Secret{{ hasAppSecret ? '（留空表示保持原值）' : '（首次必填）' }}</label>
                <el-input
                  v-model="form.appSecret"
                  :placeholder="hasAppSecret ? '已保存，留空保持原值' : '请填写飞书自建应用 App Secret'"
                  show-password
                  maxlength="256"
                />
              </div>

              <div>
                <label>默认 chat_id（可选，用于测试发送默认回填）</label>
                <el-input
                  v-model="form.defaultChatId"
                  placeholder="例如：oc_1234567890abcdef"
                  maxlength="128"
                />
              </div>

              <div>
                <label>触发权限白名单 open_id（每行或英文逗号分隔，留空表示不限制）</label>
                <el-input
                  v-model="form.allowedOpenIds"
                  type="textarea"
                  :rows="4"
                  placeholder="例如：&#10;ou_aaa&#10;ou_bbb"
                  maxlength="2048"
                />
              </div>

              <div>
                <label>本地下载根目录（每行或英文逗号分隔）</label>
                <el-input
                  v-model="form.localDownloadRoots"
                  type="textarea"
                  :rows="4"
                  placeholder="例如：&#10;D:\project\configs"
                  maxlength="4096"
                />
              </div>

              <div>
                <label>SVN 下载根目录 / 工作副本目录（旧功能下载、目录查询使用）</label>
                <el-input
                  v-model="form.svnDownloadRoots"
                  type="textarea"
                  :rows="4"
                  placeholder="例如：&#10;D:\svn\game-configs"
                  maxlength="4096"
                />
              </div>

              <div class="feishu-admin-form-grid__wide">
                <label>允许下载后缀（每行或英文逗号分隔，留空恢复默认）</label>
                <el-input
                  v-model="form.allowedDownloadSuffixes"
                  placeholder=".xls,.xlsx,.csv,.json,.xml,.txt"
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
              <SecondaryButton size="sm" @click="showStaticNotice('添加绑定群')">
                添加绑定群
              </SecondaryButton>
            </div>
            <div class="feishu-chat-tags">
              <span
                v-for="chatId in boundChatIds"
                :key="chatId"
                class="feishu-chat-tag"
              >
                {{ chatId }}
              </span>
            </div>
            <div class="feishu-inline-tip">
              default_chat_id 必须包含在绑定群列表中
            </div>
          </section>

          <section class="feishu-admin-section">
            <div class="feishu-admin-section__head">
              <div>
                <h3>配置表查询数据根 query_roots</h3>
                <p>query_roots 仅用于配置表查询读取 SVN 配置文件，与 SVN 下载根目录分开展示。</p>
              </div>
              <PrimaryButton size="sm" @click="showStaticNotice('新增数据根')">
                新增数据根
              </PrimaryButton>
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
                  v-for="root in queryRoots"
                  :key="root.alias"
                  class="bg-white transition hover:bg-gray-50"
                >
                  <td class="font-mono font-semibold text-ink-900">{{ root.alias }}</td>
                  <td>{{ root.displayName }}</td>
                  <td class="font-mono text-[12px] text-ink-500">{{ root.svnRoot }}</td>
                  <td>
                    <StatusBadge :type="root.badgeType" :label="root.statusLabel" />
                  </td>
                  <td>
                    <div class="table-actions">
                      <button type="button" class="ec-action-link" @click="showStaticNotice('编辑数据根')">
                        编辑
                      </button>
                      <button type="button" class="ec-action-link-danger" @click="showStaticNotice('删除数据根')">
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
                  <p>凭据内容脱敏展示，当前区域为静态状态信息。</p>
                </div>
              </div>
              <div class="feishu-credential-list">
                <div
                  v-for="item in credentialStatuses"
                  :key="item.label"
                  class="feishu-credential-item"
                >
                  <div class="feishu-credential-item__main">
                    <div class="feishu-credential-item__title">
                      <strong>{{ item.label }}</strong>
                      <StatusBadge :type="item.badgeType" :label="item.statusLabel" />
                    </div>
                    <p>{{ item.accountLabel }}</p>
                    <p>{{ item.secretLabel }}</p>
                    <p>最后更新：{{ item.updatedAt }}</p>
                  </div>
                  <div class="feishu-credential-item__actions">
                    <SecondaryButton size="sm" @click="showStaticNotice(`${item.label}更新凭据`)">
                      更新凭据
                    </SecondaryButton>
                    <SecondaryButton size="sm" @click="showStaticNotice(`${item.label}连接测试`)">
                      连接测试
                    </SecondaryButton>
                  </div>
                </div>
              </div>
            </section>

            <section class="feishu-admin-section">
              <div class="feishu-admin-section__head">
                <div>
                  <h3>AI 名称匹配默认参数</h3>
                  <p>用于配置表查询中的名称匹配候选排序，当前仅静态展示。</p>
                </div>
              </div>
              <div class="feishu-ai-param-list">
                <label
                  v-for="param in aiMatchParams"
                  :key="param.label"
                >
                  <span>{{ param.label }}</span>
                  <el-input :model-value="param.value" readonly />
                </label>
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
.feishu-ai-param-list label {
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
  font-family: 'JetBrains Mono', ui-monospace, Consolas, monospace;
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

.feishu-admin-two-column {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 0.85fr);
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

.feishu-ai-param-list {
  display: flex;
  flex-direction: column;
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

  .feishu-credential-item__actions,
  .feishu-admin-footer__actions {
    justify-content: flex-start;
  }

  .feishu-chat-tag {
    width: 100%;
  }
}
</style>
