<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'

import AppCard from '../components/shell/AppCard.vue'
import DataTable from '../components/shell/DataTable.vue'
import PageHeader from '../components/shell/PageHeader.vue'
import PrimaryButton from '../components/shell/PrimaryButton.vue'
import SecondaryButton from '../components/shell/SecondaryButton.vue'
import StatusBadge from '../components/shell/StatusBadge.vue'
import type { StatusBadgeType } from '../components/shell/types'
import {
  buildCreateRuleMarkdown,
  createConfigLookupRuleDetailState,
  formatDateTime,
  getRuleConfigBadgeType,
  getRuleConfigStatusLabel,
  getRuleFileName,
  getRuleQueryRoot,
} from '../features/rule-configs/useConfigLookupRule'
import type { RuleConfigSummary } from '../types/ruleConfigs'

const route = useRoute()
const router = useRouter()
const projectId = ref('default')
const keyword = ref('')
const useDraftTrial = ref(true)

const routeRuleId = computed(() => {
  const raw = route.params.ruleId
  return Array.isArray(raw) ? (raw[0] ?? '') : (raw ?? '')
})

const ruleState = createConfigLookupRuleDetailState(routeRuleId)
const {
  record,
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
  versionRows,
  isQueryTypeLocked,
} = ruleState

const trialForm = ref({
  queryType: '',
  versionFolder: '/datas_qa88',
  queryText: '',
})

const pageTitle = computed(() => record.value?.query_type || '配置表查询')
const canOperate = computed(() => Boolean(record.value))

const ruleOverview = computed(() => [
  {
    label: '查询类型',
    value: record.value?.query_type || '-',
    badge: {
      label: getRuleConfigStatusLabel(record.value?.status ?? ''),
      type: getRuleConfigBadgeType(record.value?.status ?? ''),
    },
  },
  { label: '数据根', value: getRuleQueryRoot(record.value) },
  { label: '配置文件', value: getRuleFileName(record.value) },
  { label: '当前版本', value: `v${record.value?.draft_version ?? 0}` },
  { label: '发布时间', value: formatDateTime(record.value?.published_at) },
])

const validationItems = computed(() => {
  if (!validation.value) {
    return [{ label: '尚未执行结构校验', type: 'warning' as const }]
  }
  if (!validation.value.ok) {
    return validation.value.errors.map((label) => ({ label, type: 'danger' as const }))
  }
  return [
    { label: '中文配置项合法', type: 'success' as const },
    { label: '必填字段完整', type: 'success' as const },
    { label: '数据根引用有效', type: 'success' as const },
    { label: '路径字段安全', type: 'success' as const },
  ]
})

const parseSummaryItems = computed(() => {
  const summary = validation.value?.summary
  return [
    { label: '查询类型', value: firstValue(summary?.query_types) || record.value?.query_type || '-' },
    { label: '数据根', value: firstValue(summary?.query_roots) || getRuleQueryRoot(record.value) },
    { label: '主配置文件', value: firstValue(summary?.primary_files) || getRuleFileName(record.value) },
    { label: '分页设置', value: formatPages(summary, record.value?.parsed_config_json) },
    { label: '引用配置', value: formatReferences(summary) },
  ]
})

const trialStatusType = computed<StatusBadgeType>(() => {
  if (!trialResult.value) return 'neutral'
  if (trialResult.value.status === 'hit' || trialResult.value.status === 'candidates') return 'success'
  if (trialResult.value.status === 'ai_unavailable') return 'warning'
  return 'danger'
})

onMounted(() => {
  void loadRule()
})

watch(routeRuleId, () => {
  void loadRule()
})

watch(
  () => record.value?.query_type,
  (queryType) => {
    trialForm.value.queryType = queryType || ''
    if (!trialForm.value.queryText) {
      trialForm.value.queryText = '1001'
    }
  },
  { immediate: true },
)

async function loadRule(): Promise<void> {
  await ruleState.load()
}

function backToRuleConfigs(): void {
  router.push({ name: 'rule-configs' })
}

function insertSampleTemplate(): void {
  contentMd.value = buildCreateRuleMarkdown({
    queryType: record.value?.query_type || '礼包',
    queryRoot: getRuleQueryRoot(record.value) === '-' ? 'game_datas' : getRuleQueryRoot(record.value),
    fileName: getRuleFileName(record.value) === '-' ? 'IAPConfig.xls' : getRuleFileName(record.value),
  })
  ElMessage.success('已插入单条查询规则示例模板')
}

function showOnlyConfigLookupNotice(): void {
  ElMessage.info('请在规则列表页新建配置表查询规则')
}

async function handleValidate(): Promise<void> {
  const result = await ruleState.validate()
  if (result.ok) {
    ElMessage.success(result.message)
  } else {
    ElMessage.error(result.message)
  }
}

async function handleSaveDraft(): Promise<void> {
  const result = await ruleState.saveDraft()
  if (result.ok) {
    ElMessage.success(result.message)
  } else {
    ElMessage.error(result.message)
  }
}

async function handlePublish(): Promise<void> {
  const result = await ruleState.publish()
  if (result.ok) {
    ElMessage.success(result.message)
  } else {
    ElMessage.error(result.message)
  }
}

async function handleTrial(): Promise<void> {
  const result = await ruleState.runTrial({
    queryType: trialForm.value.queryType,
    versionedConfigFolder: trialForm.value.versionFolder,
    lookupInput: trialForm.value.queryText,
    useCurrentDraft: useDraftTrial.value,
  })
  if (result.ok) {
    ElMessage.success(result.message || '试查完成')
  } else {
    ElMessage.error(result.message)
  }
}

async function handleVersionAction(action: string, versionNumber: number): Promise<void> {
  if (action !== '回滚') {
    ElMessage.info(`${action}功能暂未展开为独立面板`)
    return
  }
  const result = await ruleState.rollback(versionNumber)
  if (result.ok) {
    ElMessage.success(result.message)
  } else {
    ElMessage.error(result.message)
  }
}

function firstValue(values: string[] | undefined): string {
  return values?.find((value) => value.trim()) ?? ''
}

function formatPages(
  summary: RuleConfigSummary | undefined,
  parsedConfig: Record<string, unknown> | undefined,
): string {
  const summaryNames = summary?.pages.flatMap((page) => page.names) ?? []
  if (summaryNames.length > 0) {
    return summaryNames.join('、')
  }
  const pages = parsedConfig?.pages
  if (!Array.isArray(pages)) return '-'
  const names = pages
    .map((page) => (page && typeof page === 'object' ? (page as { name?: unknown }).name : ''))
    .filter((name): name is string => typeof name === 'string' && Boolean(name.trim()))
  return names.length > 0 ? names.join('、') : '-'
}

function formatReferences(summary: RuleConfigSummary | undefined): string {
  const references = summary?.references ?? []
  if (references.length === 0) return '-'
  return references.map((item) => `${item.name} -> ${item.file} / ${item.page}`).join('、')
}
</script>

<template>
  <div class="admin-dashboard-page rule-lookup-page flex h-full flex-col bg-canvas font-sans text-ink-700">
    <PageHeader :breadcrumb="`主页 / 规则配置 / 配置表查询 / ${pageTitle}`" title="规则配置">
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

    <div class="admin-dashboard-content rule-lookup-content flex flex-1 flex-col overflow-y-auto px-8 py-8">
      <el-alert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        show-icon
        :closable="false"
        class="rule-lookup-page-alert"
      >
        <template #default>
          <SecondaryButton size="sm" @click="loadRule">重新加载</SecondaryButton>
          <SecondaryButton size="sm" @click="backToRuleConfigs">返回规则列表</SecondaryButton>
        </template>
      </el-alert>

      <el-alert
        v-if="conflictMessage"
        :title="conflictMessage"
        type="warning"
        show-icon
        :closable="true"
        class="rule-lookup-page-alert"
        @close="ruleState.resetConflict"
      />

      <AppCard as="section" padding="none" class="admin-dashboard-card rule-lookup-overview-card">
        <div v-loading="loading" class="rule-lookup-overview">
          <div class="rule-lookup-overview__main">
            <span class="rule-lookup-step">01</span>
            <div class="min-w-0">
              <div class="rule-lookup-overview__title-row">
                <h2>{{ pageTitle }} 查询规则</h2>
                <StatusBadge
                  :type="getRuleConfigBadgeType(record?.status ?? '')"
                  :label="getRuleConfigStatusLabel(record?.status ?? '')"
                />
              </div>
              <p>本页只编辑一条查询类型规则。发布后飞书机器人立即读取已发布版本。</p>
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
              <SecondaryButton size="sm" :disabled="!canOperate" @click="insertSampleTemplate">
                插入示例模板
              </SecondaryButton>
              <SecondaryButton size="sm" :disabled="!canOperate" :loading="validating" @click="handleValidate">
                结构校验
              </SecondaryButton>
              <SecondaryButton size="sm" :disabled="!canOperate" :loading="saving" @click="handleSaveDraft">
                保存草稿
              </SecondaryButton>
              <PrimaryButton size="sm" :disabled="!canOperate" :loading="publishing" @click="handlePublish">
                发布
              </PrimaryButton>
            </div>
          </div>

          <el-alert
            v-if="isQueryTypeLocked"
            title="已发布过的规则不允许直接修改查询类型；如需新查询类型，请返回列表新建规则。"
            type="info"
            show-icon
            :closable="false"
            class="rule-lookup-editor-notice"
          />
          <el-alert
            v-else
            title="未发布草稿允许修改查询类型，但同项目内查询类型必须唯一。"
            type="info"
            show-icon
            :closable="false"
            class="rule-lookup-editor-notice"
          />

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
              <span
                class="rule-lookup-check"
                :class="item.type === 'success' ? 'rule-lookup-check--success' : item.type === 'danger' ? 'rule-lookup-check--danger' : 'rule-lookup-check--warning'"
              >
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
                    @click="handleVersionAction(action, row.versionNumber)"
                  >
                    {{ action }}
                  </button>
                </div>
              </td>
            </tr>
          </template>
        </DataTable>
        <el-empty v-if="!loading && versionRows.length === 0" description="暂无版本历史" :image-size="72" />
      </AppCard>

      <div class="rule-lookup-bottom-grid">
        <AppCard as="section" padding="none" class="admin-dashboard-card rule-lookup-trial-card">
          <div class="rule-lookup-card-header">
            <div class="rule-lookup-heading">
              <span class="rule-lookup-step">05</span>
              <h2>试查</h2>
            </div>
            <PrimaryButton size="sm" :disabled="!canOperate" :loading="trialLoading" @click="handleTrial">
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
              <StatusBadge
                :type="trialStatusType"
                :label="trialResult ? trialResult.message : '未试查'"
              />
            </div>

            <el-alert
              v-if="trialErrorMessage || trialErrorLines.length"
              :title="trialErrorMessage || '试查失败'"
              type="error"
              show-icon
              :closable="false"
              class="rule-lookup-trial-alert"
            >
              <ul v-if="trialErrorLines.length" class="rule-lookup-error-list">
                <li v-for="line in trialErrorLines" :key="line">{{ line }}</li>
              </ul>
            </el-alert>

            <div v-if="trialResult?.status === 'hit'" class="rule-lookup-trial-hits">
              <article
                v-for="item in trialResult.results"
                :key="`${item.page}-${item.id_value}-${item.name_value}`"
                class="rule-lookup-trial-hit"
              >
                <div class="rule-lookup-trial-hit__head">
                  <div>
                    <h3>{{ item.name_value || item.id_value }}</h3>
                    <p>{{ item.page }} / ID：{{ item.id_value }}</p>
                  </div>
                  <StatusBadge type="success" :label="item.query_type" />
                </div>
                <DataTable :aria-label="`${item.name_value} 字段结果`">
                  <template #head>
                    <tr>
                      <th>字段</th>
                      <th>显示名</th>
                      <th>值</th>
                    </tr>
                  </template>
                  <template #body>
                    <tr v-for="field in item.fields" :key="`${item.page}-${field.field}-${field.label}`">
                      <td class="font-mono">{{ field.field }}</td>
                      <td>{{ field.label }}</td>
                      <td>{{ field.value }}</td>
                    </tr>
                  </template>
                </DataTable>
                <el-alert
                  v-if="item.warnings.length"
                  :title="item.warnings.join('；')"
                  type="warning"
                  show-icon
                  :closable="false"
                  class="rule-lookup-trial-alert"
                />
              </article>
            </div>

            <DataTable v-else-if="trialResult?.status === 'candidates'" aria-label="AI 候选列表">
              <template #head>
                <tr>
                  <th>分页</th>
                  <th>ID</th>
                  <th>名称</th>
                  <th>置信度</th>
                </tr>
              </template>
              <template #body>
                <tr v-for="candidate in trialResult.candidates" :key="candidate.key">
                  <td>{{ candidate.page }}</td>
                  <td class="font-mono">{{ candidate.id_value }}</td>
                  <td>{{ candidate.name_value }}</td>
                  <td>{{ Math.round(candidate.score * 100) }}%</td>
                </tr>
              </template>
            </DataTable>

            <el-empty v-else description="输入查询条件后点击开始试查" :image-size="72" />
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
.rule-lookup-trial-card {
  min-width: 0;
}

.rule-lookup-project-select {
  width: 132px;
  flex: 0 0 auto;
}

.rule-lookup-page-alert {
  margin-bottom: 16px;
}

.rule-lookup-overview {
  display: grid;
  grid-template-columns: minmax(190px, 0.9fr) minmax(0, 2.2fr) minmax(220px, 0.8fr);
  gap: 22px;
  align-items: center;
  min-height: 120px;
  padding: 22px 24px;
}

.rule-lookup-overview__main,
.rule-lookup-heading,
.rule-lookup-overview__title-row,
.rule-lookup-trial-result__head,
.rule-lookup-trial-hit__head {
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

.rule-lookup-overview p {
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
  grid-template-columns: minmax(0, 1fr);
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

.rule-lookup-editor-notice {
  margin: 16px 16px 0;
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

.rule-lookup-validation-list,
.rule-lookup-parse-summary,
.rule-lookup-trial-result {
  margin: 16px 20px 20px;
}

.rule-lookup-validation-list,
.rule-lookup-trial-hits {
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

.rule-lookup-check--danger {
  color: var(--color-danger);
  background: var(--color-danger-soft);
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

.rule-lookup-trial-card {
  padding-bottom: 18px;
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

.rule-lookup-trial-hit {
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: #ffffff;
}

.rule-lookup-trial-hit__head {
  justify-content: space-between;
  padding: 14px 16px;
}

.rule-lookup-trial-hit__head h3 {
  margin: 0;
  color: var(--color-text-main);
  font-size: 15px;
  font-weight: 850;
}

.rule-lookup-trial-hit__head p {
  margin: 5px 0 0;
  color: #64748b;
  font-size: 12px;
}

.rule-lookup-trial-alert {
  margin-top: 12px;
}

.rule-lookup-error-list {
  margin: 6px 0 0;
  padding-left: 18px;
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

  .rule-lookup-card-header {
    align-items: stretch;
    flex-direction: column;
  }

  .rule-lookup-card-actions {
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

  .rule-lookup-summary-row {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
</style>
