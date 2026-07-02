<script setup lang="ts">
import { computed, h, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'

import AppCard from '../components/shell/AppCard.vue'
import MetricCard from '../components/shell/MetricCard.vue'
import PageHeader from '../components/shell/PageHeader.vue'
import PrimaryButton from '../components/shell/PrimaryButton.vue'
import SecondaryButton from '../components/shell/SecondaryButton.vue'
import StatusBadge from '../components/shell/StatusBadge.vue'
import {
  createConfigLookupRuleListState,
  formatDateTime,
  getRuleConfigBadgeType,
  getRuleConfigStatusLabel,
  getRuleFileName,
  getRulePageCount,
  getRuleQueryRoot,
  type CreateRuleInput,
} from '../features/rule-configs/useConfigLookupRule'
import type { RuleConfigRecord } from '../types/ruleConfigs'

const router = useRouter()
const ruleListState = createConfigLookupRuleListState()
const keyword = ref('')
const statusFilter = ref('all')
const createDialogVisible = ref(false)
const createForm = reactive<CreateRuleInput>({
  queryType: '',
  queryRoot: 'game_datas',
  fileName: 'IAPConfig.xls',
})

const kpiItems = computed(() => ruleListState.kpiItems.value)

const filteredRules = computed(() => {
  const normalizedKeyword = keyword.value.trim().toLowerCase()
  return ruleListState.rules.value.filter((rule) => {
    const matchesStatus = statusFilter.value === 'all' || rule.status === statusFilter.value
    const queryRoot = getRuleQueryRoot(rule)
    const fileName = getRuleFileName(rule)
    const matchesKeyword =
      !normalizedKeyword ||
      rule.query_type.toLowerCase().includes(normalizedKeyword) ||
      queryRoot.toLowerCase().includes(normalizedKeyword) ||
      fileName.toLowerCase().includes(normalizedKeyword)
    return matchesStatus && matchesKeyword
  })
})

onMounted(() => {
  void ruleListState.load()
})

function openRuleDetail(rule: RuleConfigRecord): void {
  router.push({ name: 'rule-config-lookup', params: { ruleId: String(rule.rule_id) } })
}

function openCreateDialog(): void {
  createDialogVisible.value = true
}

async function handleDeleteRule(rule: RuleConfigRecord): Promise<void> {
  try {
    await ElMessageBox.confirm(
      h('div', { class: 'rule-config-delete-confirm' }, [
        h('div', { class: 'rule-config-delete-confirm__icon', 'aria-hidden': 'true' }, [
          h(
            'svg',
            {
              viewBox: '0 0 24 24',
              fill: 'none',
              stroke: 'currentColor',
              'stroke-width': '2',
              'stroke-linecap': 'round',
              'stroke-linejoin': 'round',
            },
            [
              h('path', {
                d: 'M10.3 3.6 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0Z',
              }),
              h('path', { d: 'M12 9v4' }),
              h('path', { d: 'M12 17h.01' }),
            ],
          ),
        ]),
        h('div', { class: 'rule-config-delete-confirm__body' }, [
          h('p', { class: 'rule-config-delete-confirm__title' }, [
            '确认删除 ',
            h('strong', `「${rule.query_type}」`),
            ' 规则？',
          ]),
          h(
            'p',
            { class: 'rule-config-delete-confirm__desc' },
            '删除后该查询类型的机器人查询将不可用，已发布版本也不会再参与运行时查询。',
          ),
          h('div', { class: 'rule-config-delete-confirm__meta' }, [
            h('span', `规则族：${rule.rule_family}`),
            h('span', `当前版本：v${rule.draft_version || 0}`),
          ]),
        ]),
      ]),
      '删除查询规则',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        customClass: 'rule-config-delete-message-box',
        confirmButtonClass: 'rule-config-delete-message-box__confirm',
        cancelButtonClass: 'rule-config-delete-message-box__cancel',
        closeOnClickModal: false,
        closeOnPressEscape: true,
        distinguishCancelAndClose: true,
      },
    )
  } catch {
    return
  }

  const result = await ruleListState.deleteRule(rule)
  if (result.ok) {
    ElMessage.success(result.message)
    return
  }
  ElMessage.error(result.message)
}

async function submitCreateRule(): Promise<void> {
  if (!createForm.queryType.trim() || !createForm.queryRoot.trim() || !createForm.fileName.trim()) {
    ElMessage.error('请填写查询类型、数据根和配置文件')
    return
  }
  const result = await ruleListState.createRule({
    queryType: createForm.queryType,
    queryRoot: createForm.queryRoot,
    fileName: createForm.fileName,
  })
  if (!result.ok) {
    ElMessage.error(result.message)
    return
  }
  ElMessage.success(result.message)
  createDialogVisible.value = false
  if (result.ruleId !== undefined) {
    router.push({ name: 'rule-config-lookup', params: { ruleId: String(result.ruleId) } })
  }
}
</script>

<template>
  <div class="admin-dashboard-page rule-config-page flex h-full flex-col bg-canvas font-sans text-ink-700">
    <PageHeader
      breadcrumb="主页 / 查询配置"
      title="查询配置"
      description="按查询类型维护配置表查询规则。规则发布后立即生效，无需重启机器人。"
    >
      <template #actions>
        <el-input
          v-model="keyword"
          name="query-rule-search"
          autocomplete="off"
          placeholder="搜索查询类型、数据根或文件…"
          :prefix-icon="Search"
          clearable
          size="default"
          class="admin-dashboard-search rule-config-search"
        />
        <PrimaryButton @click="openCreateDialog">
          <template #icon><Plus /></template>
          新建规则
        </PrimaryButton>
      </template>
    </PageHeader>

    <div class="admin-dashboard-content rule-config-content flex flex-1 flex-col overflow-y-auto px-8 py-8">
      <section aria-label="规则概览" class="rule-config-overview">
        <MetricCard
          v-for="item in kpiItems"
          :key="item.label"
          :label="item.label"
          :value="item.value"
          :status-label="item.statusLabel"
          :status-type="item.statusType"
          :icon-tone="item.iconTone"
          :class="{ 'rule-config-overview__metric--datetime': item.label === '最近发布' }"
        >
          <template #icon>
            <svg
              v-if="item.label === '全部查询规则'"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M8 6h13" />
              <path d="M8 12h13" />
              <path d="M8 18h13" />
              <path d="M3 6h.01" />
              <path d="M3 12h.01" />
              <path d="M3 18h.01" />
            </svg>
            <svg
              v-else-if="item.label === '已发布'"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M20 6 9 17l-5-5" />
              <circle cx="12" cy="12" r="10" />
            </svg>
            <svg
              v-else-if="item.label === '草稿中'"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
            </svg>
            <svg
              v-else-if="item.label === '校验失败'"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M10.3 3.6 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0Z" />
              <path d="M12 9v4" />
              <path d="M12 17h.01" />
            </svg>
            <svg
              v-else
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="10" />
              <path d="M12 6v6l4 2" />
            </svg>
          </template>
        </MetricCard>
      </section>

      <AppCard as="section" padding="none" class="admin-dashboard-card query-rule-list-card">
        <div class="query-rule-list-head">
          <div>
            <h2>配置表查询规则列表</h2>
            <p>每条规则对应一个查询类型。列表仅保留编辑和删除入口，其余操作在详情页中完成。</p>
          </div>
          <div class="query-rule-list-head__tools">
            <span>共 {{ filteredRules.length }} 条</span>
            <el-select v-model="statusFilter" class="query-rule-status-filter" size="default">
              <el-option label="状态：全部" value="all" />
              <el-option label="已发布" value="published" />
              <el-option label="草稿中" value="draft" />
              <el-option label="校验失败" value="validation_failed" />
            </el-select>
          </div>
        </div>

        <el-alert
          v-if="ruleListState.errorMessage.value"
          :title="ruleListState.errorMessage.value"
          type="error"
          show-icon
          :closable="false"
          class="query-rule-error"
        />

        <div v-loading="ruleListState.loading.value" class="query-rule-list">
          <article v-for="rule in filteredRules" :key="rule.id" class="query-rule-row">
            <div class="query-rule-row__icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M4 5h16v14H4z M4 10h16 M9 5v14" />
              </svg>
            </div>

            <div class="query-rule-row__main">
              <div class="query-rule-row__title">
                <h3>{{ rule.query_type }}</h3>
                <StatusBadge :type="getRuleConfigBadgeType(rule.status)" :label="getRuleConfigStatusLabel(rule.status)" />
              </div>
              <p>通过飞书机器人按“{{ rule.query_type }} 查询”命令读取配置表数据。</p>
              <div class="query-rule-row__meta">
                <span>规则族：{{ rule.rule_family }}</span>
                <span>数据根：{{ getRuleQueryRoot(rule) }}</span>
                <span>配置文件：{{ getRuleFileName(rule) }}</span>
                <span>分页数：{{ getRulePageCount(rule) }}</span>
              </div>
            </div>

            <div class="query-rule-row__facts">
              <div>
                <span>当前版本</span>
                <strong>v{{ rule.draft_version || 0 }}</strong>
              </div>
              <div>
                <span>最近发布</span>
                <strong>{{ formatDateTime(rule.published_at) }}</strong>
              </div>
              <div>
                <span>更新人</span>
                <strong>{{ rule.updated_by === null ? '-' : `用户 #${rule.updated_by}` }}</strong>
              </div>
            </div>

            <div class="query-rule-row__actions">
              <PrimaryButton size="sm" @click="openRuleDetail(rule)">编辑</PrimaryButton>
              <SecondaryButton
                class="query-rule-row__delete-button"
                size="sm"
                :loading="ruleListState.deletingRuleId.value === rule.rule_id"
                @click="handleDeleteRule(rule)"
              >
                删除
              </SecondaryButton>
            </div>
          </article>
        </div>

        <el-empty
          v-if="!ruleListState.loading.value && filteredRules.length === 0"
          description="没有匹配的查询规则"
          :image-size="72"
        />
      </AppCard>

      <el-dialog v-model="createDialogVisible" title="新建配置表查询规则" width="520px">
        <div class="query-rule-create-form">
          <label>
            <span>查询类型</span>
            <el-input v-model="createForm.queryType" name="query-type" autocomplete="off" placeholder="例如：礼包…" />
          </label>
          <label>
            <span>数据根</span>
            <el-input v-model="createForm.queryRoot" name="query-root" autocomplete="off" spellcheck="false" placeholder="例如：game_datas…" />
          </label>
          <label>
            <span>配置文件</span>
            <el-input v-model="createForm.fileName" name="query-file-name" autocomplete="off" spellcheck="false" placeholder="例如：IAPConfig.xls…" />
          </label>
          <p>系统会根据以上字段生成单条查询规则 Markdown 模板，创建成功后进入详情页继续编辑。</p>
        </div>
        <template #footer>
          <SecondaryButton @click="createDialogVisible = false">取消</SecondaryButton>
          <PrimaryButton :loading="ruleListState.creating.value" @click="submitCreateRule">
            创建规则
          </PrimaryButton>
        </template>
      </el-dialog>
    </div>
  </div>
</template>

<style scoped>
.rule-config-page,
.rule-config-content,
.query-rule-list-card,
.query-rule-row {
  min-width: 0;
}

.rule-config-overview {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 18px;
}

.rule-config-page :deep(.ui-metric-card) {
  min-height: 128px;
  padding: 22px;
}

.rule-config-page :deep(.ui-metric-card__icon) {
  width: 58px;
  height: 58px;
}

.rule-config-page :deep(.ui-metric-card__icon svg) {
  width: 30px;
  height: 30px;
}

.rule-config-page :deep(.ui-metric-card__label) {
  color: var(--color-text-main);
  font-size: 14px;
}

.rule-config-page :deep(.ui-metric-card__value) {
  margin: 7px 0 8px;
  overflow-wrap: anywhere;
  white-space: normal;
}

.rule-config-page :deep(.rule-config-overview__metric--datetime .ui-metric-card__value) {
  font-size: 21px;
  line-height: 1.18;
}

.query-rule-list-card {
  padding: 22px;
}

.query-rule-list-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 18px;
}

.query-rule-list-head h2 {
  margin: 0;
  color: var(--color-text-main);
  font-size: 18px;
  font-weight: 850;
  line-height: 1.3;
}

.query-rule-list-head p {
  margin: 7px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.55;
}

.query-rule-list-head__tools {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 12px;
  color: #64748b;
  font-size: 13px;
  font-weight: 700;
}

.query-rule-status-filter {
  width: 132px;
}

.query-rule-list {
  display: grid;
  gap: 14px;
  margin-top: 18px;
  min-height: 120px;
}

.query-rule-error {
  margin-top: 16px;
}

.query-rule-row {
  display: grid;
  grid-template-columns: 52px minmax(220px, 1.55fr) minmax(220px, 0.8fr) minmax(134px, 0.34fr);
  gap: 14px;
  align-items: center;
  border: 1px solid var(--color-border);
  border-radius: 14px;
  background: #ffffff;
  padding: 18px;
  transition:
    border-color 160ms cubic-bezier(0.2, 0, 0, 1),
    box-shadow 160ms cubic-bezier(0.2, 0, 0, 1),
    transform 160ms cubic-bezier(0.2, 0, 0, 1);
}

.query-rule-row:hover {
  border-color: #c9d8ee;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
  transform: translateY(-1px);
}

.query-rule-row__icon {
  display: inline-flex;
  width: 52px;
  height: 52px;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  color: #ffffff;
  background: linear-gradient(180deg, #1b6dff, var(--color-primary));
  box-shadow: 0 12px 24px rgba(15, 98, 254, 0.2);
}

.query-rule-row__icon svg {
  width: 24px;
  height: 24px;
}

.query-rule-row__main,
.query-rule-row__facts {
  min-width: 0;
}

.query-rule-row__title {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.query-rule-row__title h3 {
  overflow: hidden;
  margin: 0;
  color: var(--color-text-main);
  font-size: 18px;
  font-weight: 850;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.query-rule-row__main p {
  display: -webkit-box;
  overflow: hidden;
  margin: 8px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.query-rule-row__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-top: 10px;
  color: #64748b;
  font-size: 12px;
  font-weight: 650;
}

.query-rule-row__facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0;
}

.query-rule-row__facts > div {
  min-width: 0;
  border-right: 1px solid var(--color-border-light);
  padding: 0 12px;
}

.query-rule-row__facts > div:first-child {
  padding-left: 0;
}

.query-rule-row__facts > div:last-child {
  border-right: 0;
  padding-right: 0;
}

.query-rule-row__facts span,
.query-rule-row__facts strong {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.query-rule-row__facts span {
  color: #64748b;
  font-size: 12px;
  font-weight: 650;
}

.query-rule-row__facts strong {
  margin-top: 8px;
  color: var(--color-text-main);
  font-size: 13px;
  font-weight: 800;
}

.query-rule-row__actions {
  display: flex;
  min-width: 0;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
}

.query-rule-row__actions :deep(.ui-button) {
  width: 100%;
  min-width: 0;
  justify-content: center;
  padding-right: 10px;
  padding-left: 10px;
}

.query-rule-row__delete-button {
  color: #dc2626;
  border-color: #fecaca;
  background: #ffffff;
}

.query-rule-row__delete-button:hover:not(:disabled) {
  color: #b91c1c;
  border-color: #fca5a5;
  background: #fef2f2;
}

.query-rule-create-form {
  display: grid;
  gap: 14px;
}

.query-rule-create-form label {
  min-width: 0;
}

.query-rule-create-form label > span {
  display: block;
  margin-bottom: 6px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.query-rule-create-form p {
  margin: 2px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.55;
}

:global(.rule-config-delete-message-box) {
  width: min(460px, calc(100vw - 32px));
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 16px;
  padding: 0;
  overflow: hidden;
  box-shadow:
    0 24px 60px rgba(15, 23, 42, 0.18),
    0 2px 8px rgba(15, 23, 42, 0.08);
}

:global(.rule-config-delete-message-box .el-message-box__header) {
  padding: 22px 24px 0;
}

:global(.rule-config-delete-message-box .el-message-box__title) {
  color: var(--color-text-main);
  font-size: 18px;
  font-weight: 850;
  line-height: 1.35;
}

:global(.rule-config-delete-message-box .el-message-box__headerbtn) {
  top: 18px;
  right: 18px;
}

:global(.rule-config-delete-message-box .el-message-box__content) {
  padding: 18px 24px 4px;
}

:global(.rule-config-delete-message-box .el-message-box__message) {
  width: 100%;
}

:global(.rule-config-delete-confirm) {
  display: flex;
  gap: 14px;
  min-width: 0;
}

:global(.rule-config-delete-confirm__icon) {
  display: inline-flex;
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(248, 113, 113, 0.22);
  border-radius: 14px;
  color: #dc2626;
  background: linear-gradient(180deg, #fff1f2 0%, #fee2e2 100%);
}

:global(.rule-config-delete-confirm__icon svg) {
  width: 22px;
  height: 22px;
}

:global(.rule-config-delete-confirm__body) {
  min-width: 0;
}

:global(.rule-config-delete-confirm__title) {
  margin: 1px 0 0;
  color: var(--color-text-main);
  font-size: 15px;
  font-weight: 750;
  line-height: 1.55;
}

:global(.rule-config-delete-confirm__title strong) {
  font-weight: 850;
}

:global(.rule-config-delete-confirm__desc) {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

:global(.rule-config-delete-confirm__meta) {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

:global(.rule-config-delete-confirm__meta span) {
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #f8fafc;
  padding: 4px 10px;
  color: #475569;
  font-size: 12px;
  font-weight: 700;
}

:global(.rule-config-delete-message-box .el-message-box__btns) {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 20px 24px 24px;
}

:global(.rule-config-delete-message-box .el-message-box__btns .el-button) {
  min-width: 96px;
  height: 38px;
  border-radius: 10px;
  font-weight: 750;
}

:global(.rule-config-delete-message-box__cancel) {
  border-color: #dbe4f0;
  color: #334155;
  background: #ffffff;
}

:global(.rule-config-delete-message-box__cancel:hover) {
  border-color: #cbd5e1;
  color: #0f172a;
  background: #f8fafc;
}

:global(.rule-config-delete-message-box__confirm) {
  border-color: #dc2626;
  color: #ffffff;
  background: #dc2626;
  box-shadow: 0 10px 22px rgba(220, 38, 38, 0.22);
}

:global(.rule-config-delete-message-box__confirm:hover),
:global(.rule-config-delete-message-box__confirm:focus) {
  border-color: #b91c1c;
  color: #ffffff;
  background: #b91c1c;
}

@media (max-width: 1180px) {
  .rule-config-overview {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .query-rule-row {
    grid-template-columns: 52px minmax(0, 1fr);
  }

  .query-rule-row__facts,
  .query-rule-row__actions {
    grid-column: 2;
  }

  .query-rule-row__actions {
    align-items: stretch;
    max-width: 260px;
  }
}

@media (max-width: 900px) {
  .rule-config-overview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .query-rule-list-head {
    align-items: stretch;
    flex-direction: column;
  }

  .query-rule-list-head__tools {
    justify-content: space-between;
  }
}

@media (max-width: 768px) {
  .rule-config-search,
  .query-rule-status-filter {
    width: 100%;
  }

  .query-rule-list-head__tools {
    align-items: stretch;
    flex-direction: column;
  }

  .query-rule-row {
    grid-template-columns: 42px minmax(0, 1fr);
    padding: 14px;
  }

  .query-rule-row__icon {
    width: 42px;
    height: 42px;
    border-radius: 12px;
  }

  .query-rule-row__facts {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .query-rule-row__facts > div {
    border-right: 0;
    padding-right: 0;
    padding-left: 0;
  }

  .query-rule-row__actions {
    max-width: none;
  }
}

@media (max-width: 640px) {
  .rule-config-overview {
    grid-template-columns: 1fr;
  }
}
</style>
