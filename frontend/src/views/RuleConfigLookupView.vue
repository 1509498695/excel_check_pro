<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'

import AppCard from '../components/shell/AppCard.vue'
import DataTable from '../components/shell/DataTable.vue'
import PageHeader from '../components/shell/PageHeader.vue'
import PrimaryButton from '../components/shell/PrimaryButton.vue'
import SecondaryButton from '../components/shell/SecondaryButton.vue'
import StatusBadge from '../components/shell/StatusBadge.vue'
import { useAuthStore } from '../store/auth'
import type { StatusBadgeType } from '../components/shell/types'
import {
  CONFIG_LOOKUP_SAMPLE_MARKDOWN,
  buildCredentialRows,
  createConfigLookupRuleState,
  createEmptyCredentialsStatus,
  formatDateTime,
  type VersionRow,
} from '../features/rule-configs/useConfigLookupRule'

interface RuleOverviewItem {
  label: string
  value: string
  badge?: { label: string; type: StatusBadgeType }
}

interface ValidationItem {
  label: string
  type: 'success' | 'warning'
}

const router = useRouter()
const auth = useAuthStore()
const projectId = ref('default')
const keyword = ref('')
const useDraftTrial = ref(true)
const trialForm = ref({
  queryType: '礼包',
  versionFolder: '/datas_qa88',
  queryText: '1001',
})
const ruleState = createConfigLookupRuleState()
const {
  record,
  contentMd,
  validation,
  credentials,
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
  validationErrors,
  versionRows,
  load,
  validate: validateRuleConfig,
  saveDraft,
  publish,
  rollback,
  runTrial,
} = ruleState

const ruleOverview = computed<RuleOverviewItem[]>(() => [
  {
    label: '规则分组',
    value: '配置表查询（config_lookup）',
    badge: { label: getRecordStatusLabel(), type: getRecordBadgeType() },
  },
  {
    label: '当前版本',
    value: record.value.draft_version > 0 ? `v${record.value.draft_version}` : '-',
  },
  {
    label: '已发布版本',
    value: record.value.published_version ? `v${record.value.published_version}` : '-',
  },
  {
    label: '最后更新人',
    value: record.value.updated_by === null ? '-' : `用户 #${record.value.updated_by}`,
  },
  {
    label: '发布时间',
    value: formatDateTime(record.value.published_at),
  },
])

const hasDraftUpdate = computed(() => {
  return record.value.status !== 'empty' && record.value.draft_version > (record.value.published_version ?? 0)
})

const validationItems = computed<ValidationItem[]>(() => {
  if (validationErrors.value.length > 0) {
    return validationErrors.value.map((label) => ({ label, type: 'warning' }))
  }
  if (validation.value?.ok) {
    return [
      { label: '中文配置项合法', type: 'success' },
      { label: '必填字段完整', type: 'success' },
      { label: 'query_root 引用有效', type: 'success' },
      { label: '路径字段安全', type: 'success' },
    ]
  }
  return [{ label: '尚未执行结构校验', type: 'warning' }]
})

const parseSummaryItems = computed(() => {
  if (validation.value?.summary) {
    const summary = validation.value.summary
    return [
      { label: '查询类型', value: summary.query_types.join('、') || '-' },
      { label: '数据根', value: summary.query_roots.join('、') || '-' },
      { label: '主配置文件', value: summary.primary_files.join('、') || '-' },
      {
        label: '分页设置',
        value: summary.pages.flatMap((page) => page.names).join('、') || '-',
      },
      {
        label: '引用配置',
        value: summary.references
          .map((reference) => `${reference.name} -> ${reference.file} / ${reference.page}`)
          .join('、') || '-',
      },
    ]
  }
  const summary = buildSummaryFromParsedConfig()
  return [
    { label: '查询类型', value: summary.queryTypes || '-' },
    { label: '数据根', value: summary.queryRoots || '-' },
    { label: '主配置文件', value: summary.primaryFiles || '-' },
    { label: '分页设置', value: summary.pages || '-' },
    { label: '引用配置', value: summary.references || '-' },
  ]
})

const credentialRows = computed(() => {
  return buildCredentialRows(credentials.value ?? createEmptyCredentialsStatus(), auth.isProjectAdmin)
})

const trialBadge = computed(() => {
  if (trialErrorMessage.value) {
    return { type: 'danger' as StatusBadgeType, label: '试查失败' }
  }
  if (!trialResult.value) {
    return { type: 'neutral' as StatusBadgeType, label: '未试查' }
  }
  if (trialResult.value.status === 'hit') {
    return {
      type: 'success' as StatusBadgeType,
      label: `命中 ${trialResult.value.results.length} 条`,
    }
  }
  if (trialResult.value.status === 'candidates') {
    return {
      type: 'warning' as StatusBadgeType,
      label: `候选 ${trialResult.value.candidates.length} 条`,
    }
  }
  if (trialResult.value.status === 'ai_unavailable') {
    return { type: 'warning' as StatusBadgeType, label: 'AI 不可用' }
  }
  return { type: 'neutral' as StatusBadgeType, label: '未命中' }
})

function backToRuleConfigs(): void {
  router.push({ name: 'rule-configs' })
}

function showStaticNotice(label: string): void {
  ElMessage.info(`${label}将在后续阶段接入`)
}

function showOnlyConfigLookupNotice(): void {
  ElMessage.info('当前仅支持配置表查询规则')
}

async function handleTrial(): Promise<void> {
  const queryType = trialForm.value.queryType.trim()
  const versionedConfigFolder = trialForm.value.versionFolder.trim()
  const lookupInput = trialForm.value.queryText.trim()
  if (!queryType || !versionedConfigFolder || !lookupInput) {
    ElMessage.warning('请填写查询类型、版本目录和查询内容')
    return
  }
  const result = await runTrial({
    queryType,
    versionedConfigFolder,
    lookupInput,
    useCurrentDraft: useDraftTrial.value,
  })
  if (result.ok) {
    ElMessage.success(result.message)
  } else if (result.message) {
    ElMessage.warning(result.message)
  }
}

function insertSampleTemplate(): void {
  contentMd.value = CONFIG_LOOKUP_SAMPLE_MARKDOWN
  ElMessage.success('已插入示例模板')
}

async function handleValidate(): Promise<void> {
  const result = await validateRuleConfig()
  if (result.ok) {
    ElMessage.success(result.message)
  } else {
    ElMessage.warning(result.message)
  }
}

async function handleSaveDraft(): Promise<void> {
  const result = await saveDraft()
  if (result.ok) {
    ElMessage.success(result.message)
  } else if (result.message) {
    ElMessage.warning(result.message)
  }
}

async function handlePublish(): Promise<void> {
  const result = await publish()
  if (result.ok) {
    ElMessage.success(result.message)
  } else if (result.message) {
    ElMessage.warning(result.message)
  }
}

async function handleRollback(version: number): Promise<void> {
  const result = await rollback(version)
  if (result.ok) {
    ElMessage.success(result.message)
  } else if (result.message) {
    ElMessage.warning(result.message)
  }
}

function handleVersionAction(action: string, row: VersionRow): void {
  if (action === '发布') {
    void handlePublish()
    return
  }
  if (action === '回滚') {
    void handleRollback(row.versionNumber)
    return
  }
  showStaticNotice(action)
}

function getRecordStatusLabel(): string {
  if (record.value.status === 'published') return '已发布'
  if (record.value.status === 'draft') return '草稿'
  return '未发布'
}

function getRecordBadgeType(): StatusBadgeType {
  if (record.value.status === 'published') return 'success'
  if (record.value.status === 'draft') return 'warning'
  return 'neutral'
}

function buildSummaryFromParsedConfig(): {
  queryTypes: string
  queryRoots: string
  primaryFiles: string
  pages: string
  references: string
} {
  const queries = record.value.parsed_config_json.queries
  if (!Array.isArray(queries)) {
    return { queryTypes: '', queryRoots: '', primaryFiles: '', pages: '', references: '' }
  }
  const queryTypes: string[] = []
  const queryRoots: string[] = []
  const primaryFiles: string[] = []
  const pages: string[] = []
  const references: string[] = []
  for (const query of queries) {
    if (!query || typeof query !== 'object') continue
    const payload = query as Record<string, unknown>
    queryTypes.push(String(payload.query_type ?? ''))
    queryRoots.push(String(payload.query_root ?? ''))
    primaryFiles.push(String(payload.file ?? ''))
    if (Array.isArray(payload.pages)) {
      pages.push(
        ...payload.pages
          .filter((page): page is Record<string, unknown> => !!page && typeof page === 'object')
          .map((page) => String(page.name ?? '')),
      )
    }
    if (Array.isArray(payload.references)) {
      references.push(
        ...payload.references
          .filter((reference): reference is Record<string, unknown> => {
            return !!reference && typeof reference === 'object'
          })
          .map((reference) => {
            return `${String(reference.name ?? '')} -> ${String(reference.file ?? '')} / ${String(reference.page ?? '')}`
          }),
      )
    }
  }
  return {
    queryTypes: queryTypes.filter(Boolean).join('、'),
    queryRoots: queryRoots.filter(Boolean).join('、'),
    primaryFiles: primaryFiles.filter(Boolean).join('、'),
    pages: pages.filter(Boolean).join('、'),
    references: references.filter(Boolean).join('、'),
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="admin-dashboard-page rule-lookup-page flex h-full flex-col bg-canvas font-sans text-ink-700">
    <PageHeader breadcrumb="主页 / 规则配置 / 配置表查询" title="规则配置">
      <template #actions>
        <el-select v-model="projectId" class="rule-lookup-project-select" size="default">
          <el-option label="默认项目" value="default" />
        </el-select>
        <el-input
          v-model="keyword"
          placeholder="搜索规则"
          :prefix-icon="Search"
          clearable
          size="default"
          class="admin-dashboard-search rule-lookup-search"
        />
        <PrimaryButton @click="showOnlyConfigLookupNotice">
          <template #icon><Plus /></template>
          新建规则
        </PrimaryButton>
        <SecondaryButton @click="backToRuleConfigs">
          返回规则列表
        </SecondaryButton>
      </template>
    </PageHeader>

    <div
      v-loading="loading"
      class="admin-dashboard-content rule-lookup-content flex flex-1 flex-col overflow-y-auto px-8 py-8"
    >
      <el-alert
        v-if="fallbackActive"
        title="当前使用开发 fallback，后端规则配置接口不可用。"
        type="warning"
        show-icon
        :closable="false"
      />
      <el-alert
        v-if="conflictMessage"
        :title="conflictMessage"
        type="warning"
        show-icon
        :closable="false"
      >
        <template #default>
          <SecondaryButton size="sm" @click="load">刷新规则配置</SecondaryButton>
        </template>
      </el-alert>
      <AppCard
        v-if="errorMessage"
        as="section"
        padding="none"
        class="admin-dashboard-card rule-lookup-alert-card"
      >
        <div class="rule-lookup-alert-card__body">
          <span>{{ errorMessage }}</span>
          <SecondaryButton size="sm" @click="load">重新加载</SecondaryButton>
        </div>
      </AppCard>

      <AppCard as="section" padding="none" class="admin-dashboard-card rule-lookup-overview-card">
        <div class="rule-lookup-overview">
          <div class="rule-lookup-overview__main">
            <span class="rule-lookup-step">01</span>
            <div class="min-w-0">
              <div class="rule-lookup-overview__title-row">
                <h2>规则概览</h2>
                <StatusBadge :type="getRecordBadgeType()" :label="getRecordStatusLabel()" />
                <StatusBadge v-if="hasDraftUpdate" type="warning" label="草稿有更新" />
              </div>
              <p>配置表查询规则发布后立即生效，草稿变更可保存后继续发布。</p>
            </div>
          </div>

          <div class="rule-lookup-overview__facts">
            <div v-for="item in ruleOverview" :key="item.label" class="rule-lookup-overview__fact">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
              <StatusBadge
                v-if="item.badge"
                :type="item.badge.type"
                :label="item.badge.label"
              />
            </div>
          </div>

          <div class="rule-lookup-live-state">
            <StatusBadge type="success" label="发布后立即生效，无需重启机器人" />
          </div>
        </div>
      </AppCard>

      <div class="rule-lookup-editor-grid">
        <AppCard as="section" padding="none" class="admin-dashboard-card rule-lookup-editor-card">
          <div class="rule-lookup-card-header">
            <div class="rule-lookup-heading">
              <span class="rule-lookup-step">02</span>
              <h2>Markdown 规则编辑</h2>
            </div>
            <div class="rule-lookup-card-actions">
              <SecondaryButton size="sm" @click="insertSampleTemplate">
                插入示例模板
              </SecondaryButton>
              <SecondaryButton size="sm" :loading="validating" @click="handleValidate">
                结构校验
              </SecondaryButton>
              <SecondaryButton size="sm" :loading="saving" @click="handleSaveDraft">
                保存草稿
              </SecondaryButton>
              <PrimaryButton size="sm" :loading="publishing" @click="handlePublish">
                发布
              </PrimaryButton>
            </div>
          </div>

          <div class="rule-lookup-code-editor" aria-label="Markdown 规则编辑">
            <el-input
              v-model="contentMd"
              type="textarea"
              resize="none"
              :autosize="{ minRows: 18, maxRows: 34 }"
              class="rule-lookup-markdown-input"
              spellcheck="false"
            />
          </div>
        </AppCard>

        <AppCard as="section" padding="none" class="admin-dashboard-card rule-lookup-validation-card">
          <div class="rule-lookup-card-header">
            <div class="rule-lookup-heading">
              <span class="rule-lookup-step">03</span>
              <h2>结构校验结果</h2>
            </div>
          </div>

          <div class="rule-lookup-validation-list">
            <div
              v-for="item in validationItems"
              :key="item.label"
              class="rule-lookup-validation-item"
            >
              <span class="rule-lookup-check" :class="`rule-lookup-check--${item.type}`">
                {{ item.type === 'success' ? '✓' : '!' }}
              </span>
              <span>{{ item.label }}</span>
            </div>
          </div>

          <div class="rule-lookup-parse-summary">
            <h3>解析摘要</h3>
            <div
              v-for="item in parseSummaryItems"
              :key="item.label"
              class="rule-lookup-summary-row"
            >
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </AppCard>
      </div>

      <AppCard as="section" padding="none" class="admin-dashboard-card rule-lookup-history-card">
        <div class="rule-lookup-card-header">
          <div class="rule-lookup-heading">
            <span class="rule-lookup-step">04</span>
            <h2>版本历史</h2>
          </div>
        </div>

        <DataTable aria-label="版本历史">
          <template #head>
            <tr>
              <th class="w-[96px]">版本号</th>
              <th class="w-[120px]">状态</th>
              <th class="w-[120px]">操作人</th>
              <th class="w-[190px]">时间</th>
              <th>说明</th>
              <th class="w-[220px]">操作</th>
            </tr>
          </template>
          <template #body>
            <tr v-for="row in versionRows" :key="row.version" class="bg-white transition hover:bg-gray-50">
              <td class="font-mono font-semibold text-ink-900">{{ row.version }}</td>
              <td>
                <StatusBadge :type="row.badgeType" :label="row.statusLabel" />
              </td>
              <td>{{ row.operator }}</td>
              <td class="font-mono text-[12px] text-ink-500">{{ row.updatedAt }}</td>
              <td>
                <span class="truncate-line">{{ row.description }}</span>
              </td>
              <td>
                <div class="table-actions">
                  <button
                    v-for="action in row.actions"
                    :key="`${row.version}-${action}`"
                    type="button"
                    class="ec-action-link"
                    :disabled="rollingBack && action === '回滚'"
                    @click="handleVersionAction(action, row)"
                  >
                    {{ action }}
                  </button>
                </div>
              </td>
            </tr>
          </template>
        </DataTable>
      </AppCard>

      <div class="rule-lookup-bottom-grid">
        <AppCard as="section" padding="none" class="admin-dashboard-card rule-lookup-credential-card">
          <div class="rule-lookup-card-header">
            <div class="rule-lookup-heading">
              <span class="rule-lookup-step">05</span>
              <h2>项目凭据状态</h2>
            </div>
          </div>
          <p class="rule-lookup-muted">
            普通成员仅可查看凭据连接状态，无法查看或修改完整凭据信息。
          </p>

          <div class="rule-lookup-credential-list">
            <div
              v-for="row in credentialRows"
              :key="row.label"
              class="rule-lookup-credential-row"
            >
              <div>
                <div class="rule-lookup-credential-row__title">
                  <strong>{{ row.label }}</strong>
                  <StatusBadge type="success" :label="row.statusLabel" />
                </div>
                <p>{{ row.accountLabel }}</p>
                <p>{{ row.secretLabel }}</p>
                <p>最后更新：{{ row.updatedAt }}</p>
              </div>
              <div v-if="row.canManage" class="rule-lookup-credential-actions">
                <SecondaryButton size="sm" @click="showStaticNotice(`${row.label}更新凭据`)">
                  更新凭据
                </SecondaryButton>
                <SecondaryButton size="sm" @click="showStaticNotice(`${row.label}连接测试`)">
                  连接测试
                </SecondaryButton>
              </div>
            </div>
          </div>
        </AppCard>

        <AppCard as="section" padding="none" class="admin-dashboard-card rule-lookup-trial-card">
          <div class="rule-lookup-card-header">
            <div class="rule-lookup-heading">
              <span class="rule-lookup-step">06</span>
              <h2>试查</h2>
            </div>
            <PrimaryButton size="sm" :loading="trialLoading" @click="handleTrial">
              开始试查
            </PrimaryButton>
          </div>

          <div class="rule-lookup-trial-form">
            <label>
              <span>查询类型</span>
              <el-input v-model="trialForm.queryType" placeholder="例如：礼包" />
            </label>
            <label>
              <span>版本目录</span>
              <el-input v-model="trialForm.versionFolder" placeholder="/datas_qa88" />
            </label>
            <label>
              <span>查询内容</span>
              <el-input v-model="trialForm.queryText" placeholder="输入 ID 或名称" />
            </label>
            <el-checkbox v-model="useDraftTrial">
              使用当前草稿试查
            </el-checkbox>
          </div>

          <div class="rule-lookup-trial-result">
            <div class="rule-lookup-trial-result__head">
              <span>试查结果</span>
              <StatusBadge :type="trialBadge.type" :label="trialBadge.label" />
            </div>

            <el-alert
              v-if="trialErrorMessage"
              :title="trialErrorMessage"
              type="warning"
              show-icon
              :closable="false"
              class="rule-lookup-trial-alert"
            >
              <template v-if="trialErrorLines.length > 0" #default>
                <ul class="rule-lookup-trial-errors">
                  <li v-for="line in trialErrorLines" :key="line">{{ line }}</li>
                </ul>
              </template>
            </el-alert>

            <div v-else-if="trialResult?.status === 'hit'" class="rule-lookup-trial-hits">
              <div
                v-for="item in trialResult.results"
                :key="`${item.page}-${item.id_value}-${item.name_value}`"
                class="rule-lookup-trial-hit"
              >
                <div class="rule-lookup-trial-hit__head">
                  <div>
                    <strong>{{ item.name_value || '-' }}</strong>
                    <span>{{ item.page }} / ID：{{ item.id_value || '-' }}</span>
                  </div>
                  <StatusBadge type="success" :label="item.query_type" />
                </div>
                <el-alert
                  v-if="item.warnings.length > 0"
                  type="warning"
                  show-icon
                  :closable="false"
                  class="rule-lookup-trial-alert"
                >
                  <template #default>
                    {{ item.warnings.join('；') }}
                  </template>
                </el-alert>
                <DataTable aria-label="试查命中字段">
                  <template #head>
                    <tr>
                      <th class="w-[160px]">字段</th>
                      <th class="w-[160px]">显示名</th>
                      <th>值</th>
                    </tr>
                  </template>
                  <template #body>
                    <tr
                      v-for="field in item.fields"
                      :key="`${item.page}-${item.id_value}-${field.field}-${field.label}`"
                      class="bg-white transition hover:bg-gray-50"
                    >
                      <td class="font-mono text-ink-900">{{ field.field }}</td>
                      <td>{{ field.label }}</td>
                      <td>{{ field.value || '-' }}</td>
                    </tr>
                  </template>
                </DataTable>
              </div>
            </div>

            <DataTable v-else-if="trialResult?.status === 'candidates'" aria-label="AI 候选列表">
              <template #head>
                <tr>
                  <th>分页</th>
                  <th>ID</th>
                  <th>名称</th>
                  <th class="w-[120px]">置信度</th>
                </tr>
              </template>
              <template #body>
                <tr
                  v-for="candidate in trialResult.candidates"
                  :key="candidate.key"
                  class="bg-white transition hover:bg-gray-50"
                >
                  <td>{{ candidate.page }}</td>
                  <td class="font-mono text-ink-900">{{ candidate.id_value }}</td>
                  <td>{{ candidate.name_value }}</td>
                  <td>{{ Math.round(candidate.score * 100) }}%</td>
                </tr>
              </template>
            </DataTable>

            <el-alert
              v-else-if="trialResult"
              :title="trialResult.message"
              :type="trialResult.status === 'ai_unavailable' ? 'warning' : 'info'"
              show-icon
              :closable="false"
              class="rule-lookup-trial-alert"
            />

            <el-empty v-else description="输入条件后开始试查" :image-size="72" />
          </div>
        </AppCard>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rule-lookup-page,
.rule-lookup-content,
.rule-lookup-editor-grid,
.rule-lookup-bottom-grid,
.rule-lookup-editor-card,
.rule-lookup-validation-card,
.rule-lookup-history-card,
.rule-lookup-credential-card,
.rule-lookup-trial-card {
  min-width: 0;
}

.rule-lookup-project-select {
  width: 132px;
  flex: 0 0 auto;
}

.rule-lookup-alert-card {
  padding: 14px 18px;
}

.rule-lookup-alert-card__body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--color-danger);
  font-size: 13px;
  font-weight: 700;
}

.rule-lookup-overview {
  display: grid;
  grid-template-columns: minmax(190px, 0.9fr) minmax(0, 2.2fr) minmax(220px, 0.8fr);
  gap: 22px;
  align-items: center;
  padding: 22px 24px;
}

.rule-lookup-overview__main,
.rule-lookup-heading,
.rule-lookup-overview__title-row,
.rule-lookup-credential-row__title,
.rule-lookup-trial-result__head {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
}

.rule-lookup-step {
  display: inline-flex;
  width: 42px;
  height: 42px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: var(--color-primary);
  background: var(--color-primary-soft);
  font-family: 'JetBrains Mono', ui-monospace, Consolas, monospace;
  font-size: 16px;
  font-weight: 850;
}

.rule-lookup-overview h2,
.rule-lookup-heading h2 {
  overflow: hidden;
  margin: 0;
  color: var(--color-text-main);
  font-size: 18px;
  font-weight: 850;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rule-lookup-overview p,
.rule-lookup-muted {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.55;
}

.rule-lookup-overview__facts {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0;
}

.rule-lookup-overview__fact {
  min-width: 0;
  border-right: 1px solid var(--color-border-light);
  padding: 0 14px;
}

.rule-lookup-overview__fact:last-child {
  border-right: 0;
}

.rule-lookup-overview__fact span {
  display: block;
  overflow: hidden;
  color: #64748b;
  font-size: 12px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rule-lookup-overview__fact strong {
  display: block;
  overflow: hidden;
  margin-top: 8px;
  color: var(--color-text-main);
  font-size: 14px;
  font-weight: 850;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rule-lookup-live-state {
  display: flex;
  justify-content: flex-end;
}

.rule-lookup-editor-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(320px, 0.8fr);
  gap: 18px;
}

.rule-lookup-bottom-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr);
  gap: 18px;
}

.rule-lookup-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--color-border);
  padding: 18px 20px 14px;
}

.rule-lookup-card-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.rule-lookup-code-editor {
  overflow: auto;
  margin: 16px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: #fbfdff;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.78);
  padding: 8px 0;
}

.rule-lookup-markdown-input {
  display: block;
}

.rule-lookup-markdown-input :deep(.el-textarea__inner) {
  border: 0;
  border-radius: 0;
  box-shadow: none;
  background: transparent;
  color: #334155;
  font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, monospace;
  font-size: 13px;
  line-height: 1.6;
  padding: 10px 16px;
}

.rule-lookup-markdown-input :deep(.el-textarea__inner:focus) {
  box-shadow: none;
}

.rule-lookup-code-line {
  display: grid;
  grid-template-columns: 48px minmax(680px, 1fr);
  min-height: 26px;
  align-items: center;
  color: #334155;
  font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, monospace;
  font-size: 13px;
  line-height: 1.55;
}

.rule-lookup-code-line__no {
  color: #94a3b8;
  user-select: none;
  text-align: right;
  padding-right: 14px;
}

.rule-lookup-code-line code {
  display: block;
  border-left: 1px solid var(--color-border-light);
  padding: 0 16px;
  white-space: pre;
}

.rule-lookup-code-key {
  color: var(--color-primary);
  font-weight: 850;
}

.rule-lookup-validation-list,
.rule-lookup-parse-summary,
.rule-lookup-credential-list,
.rule-lookup-trial-result {
  margin: 16px 20px 20px;
}

.rule-lookup-validation-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rule-lookup-validation-item {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #334155;
  font-size: 14px;
}

.rule-lookup-check {
  display: inline-flex;
  width: 20px;
  height: 20px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  font-size: 12px;
  font-weight: 850;
}

.rule-lookup-check--success {
  color: var(--color-success);
  background: var(--color-success-soft);
}

.rule-lookup-check--warning {
  color: var(--color-warning);
  background: var(--color-warning-soft);
}

.rule-lookup-parse-summary {
  border-top: 1px solid var(--color-border);
  padding-top: 16px;
}

.rule-lookup-parse-summary h3 {
  margin: 0 0 12px;
  color: #64748b;
  font-size: 13px;
  font-weight: 800;
}

.rule-lookup-summary-row {
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr);
  gap: 12px;
  min-width: 0;
  padding: 7px 0;
  color: #64748b;
  font-size: 13px;
}

.rule-lookup-summary-row strong {
  overflow: hidden;
  color: var(--color-text-main);
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rule-lookup-history-card .ui-data-table,
.rule-lookup-trial-result .ui-data-table {
  border-radius: 0;
  border-right: 0;
  border-bottom: 0;
  border-left: 0;
  box-shadow: none;
}

.rule-lookup-credential-card,
.rule-lookup-trial-card {
  padding-bottom: 18px;
}

.rule-lookup-credential-card .rule-lookup-muted {
  margin: 14px 20px 0;
}

.rule-lookup-credential-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.rule-lookup-credential-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: #ffffff;
  padding: 14px 16px;
}

.rule-lookup-credential-row strong {
  color: var(--color-text-main);
  font-size: 14px;
}

.rule-lookup-credential-row p {
  margin: 7px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.35;
}

.rule-lookup-credential-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.rule-lookup-trial-form {
  display: grid;
  grid-template-columns: 120px 150px minmax(180px, 1fr) auto;
  gap: 12px;
  align-items: end;
  margin: 18px 20px 0;
}

.rule-lookup-trial-form label {
  min-width: 0;
}

.rule-lookup-trial-form label > span {
  display: block;
  margin-bottom: 6px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.rule-lookup-trial-result__head {
  justify-content: space-between;
  margin-bottom: 12px;
  color: var(--color-text-main);
  font-size: 14px;
  font-weight: 800;
}

.rule-lookup-trial-alert {
  margin-bottom: 12px;
}

.rule-lookup-trial-errors {
  margin: 6px 0 0;
  padding-left: 18px;
  color: #92400e;
  font-size: 13px;
  line-height: 1.55;
}

.rule-lookup-trial-hits {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.rule-lookup-trial-hit {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: #ffffff;
}

.rule-lookup-trial-hit__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--color-border-light);
  padding: 12px 14px;
}

.rule-lookup-trial-hit__head strong,
.rule-lookup-trial-hit__head span {
  display: block;
}

.rule-lookup-trial-hit__head strong {
  color: var(--color-text-main);
  font-size: 14px;
  font-weight: 850;
}

.rule-lookup-trial-hit__head span {
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
}

.rule-lookup-trial-hit .rule-lookup-trial-alert {
  margin: 12px 14px;
}

.rule-lookup-trial-hit .ui-data-table {
  border-right: 0;
  border-bottom: 0;
  border-left: 0;
}

@media (max-width: 1366px) {
  .rule-lookup-overview {
    gap: 14px;
    padding: 20px;
  }

  .rule-lookup-overview__fact {
    padding: 0 8px;
  }
}

@media (max-width: 1180px) {
  .rule-lookup-overview {
    grid-template-columns: 1fr;
  }

  .rule-lookup-live-state {
    justify-content: flex-start;
  }

  .rule-lookup-overview__facts {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px 0;
  }

  .rule-lookup-editor-grid,
  .rule-lookup-bottom-grid {
    grid-template-columns: 1fr;
  }

  .rule-lookup-trial-form {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .rule-lookup-project-select,
  .rule-lookup-search {
    width: 100%;
  }

  .rule-lookup-card-header,
  .rule-lookup-credential-row {
    align-items: stretch;
    flex-direction: column;
  }

  .rule-lookup-card-actions,
  .rule-lookup-credential-actions {
    justify-content: flex-start;
  }

  .rule-lookup-overview__facts,
  .rule-lookup-trial-form {
    grid-template-columns: 1fr;
  }

  .rule-lookup-overview__fact {
    border-right: 0;
    padding-right: 0;
    padding-left: 0;
  }

  .rule-lookup-code-line {
    grid-template-columns: 42px minmax(560px, 1fr);
  }

  .rule-lookup-summary-row {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
</style>
