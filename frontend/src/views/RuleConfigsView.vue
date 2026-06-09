<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'

import AppCard from '../components/shell/AppCard.vue'
import DataTable from '../components/shell/DataTable.vue'
import PageHeader from '../components/shell/PageHeader.vue'
import PrimaryButton from '../components/shell/PrimaryButton.vue'
import SecondaryButton from '../components/shell/SecondaryButton.vue'
import StatusBadge from '../components/shell/StatusBadge.vue'
import type { StatusBadgeType } from '../components/shell/types'

type RuleStatus = 'published' | 'draft' | 'unpublished'
type OverviewTone = 'default' | 'success' | 'warning' | 'danger'

interface RuleOverviewItem {
  label: string
  value: string
  tone: OverviewTone
}

interface RuleItem {
  id: string
  title: string
  family: string
  status: RuleStatus
  statusLabel: string
  badgeType: StatusBadgeType
  description: string
  updatedAt: string
  supported: boolean
  futureLabel?: string
}

interface VersionItem {
  version: string
  statusLabel: string
  badgeType: StatusBadgeType
  operator: string
  updatedAt: string
  description: string
}

const router = useRouter()
const keyword = ref('')
const activeTab = ref('all')
const selectedRuleId = ref('config_lookup')
const familyFilter = ref('all')

const overviewItems: RuleOverviewItem[] = [
  { label: '全部规则', value: '3', tone: 'default' },
  { label: '已发布', value: '2', tone: 'success' },
  { label: '草稿中', value: '1', tone: 'warning' },
  { label: '校验失败', value: '0', tone: 'danger' },
  { label: '最近发布', value: '2024/05/27 02:32:18', tone: 'default' },
]

const tabs = [
  { id: 'all', label: '全部规则' },
  { id: 'config_lookup', label: '配置表查询' },
  { id: 'future', label: '其他规则（未来扩展）' },
]

const rules: RuleItem[] = [
  {
    id: 'config_lookup',
    title: '配置表查询',
    family: 'config_lookup',
    status: 'published',
    statusLabel: '已发布',
    badgeType: 'success',
    description: '用于通过飞书机器人按配置表查询命令读取数据，支持多分页查询与引用关联。',
    updatedAt: '2024/05/27 02:32:18',
    supported: true,
  },
  {
    id: 'project_check',
    title: '项目校验规则',
    family: 'project_check',
    status: 'draft',
    statusLabel: '草稿',
    badgeType: 'warning',
    description: '项目级固定校验规则配置，当前仅作为未来扩展入口展示。',
    updatedAt: '2024/05/26 18:15:42',
    supported: false,
    futureLabel: '未来扩展',
  },
  {
    id: 'directory_query',
    title: '目录查询规则',
    family: 'directory_query',
    status: 'unpublished',
    statusLabel: '未发布',
    badgeType: 'neutral',
    description: '目录级文件查询规则配置，当前仅作为未来扩展入口展示。',
    updatedAt: '2024/05/24 10:09:31',
    supported: false,
    futureLabel: '未来扩展',
  },
]

const versions: VersionItem[] = [
  {
    version: 'v1.3',
    statusLabel: '已发布',
    badgeType: 'success',
    operator: 'admin',
    updatedAt: '2024/05/27 02:32:18',
    description: '优化输出字段，补充 price 字段',
  },
  {
    version: 'v1.2',
    statusLabel: '草稿',
    badgeType: 'warning',
    operator: 'admin',
    updatedAt: '2024/05/26 18:15:42',
    description: '调整分页默认条数为 50',
  },
  {
    version: 'v1.1',
    statusLabel: '已发布',
    badgeType: 'success',
    operator: 'admin',
    updatedAt: '2024/05/24 10:09:31',
    description: '初始版本发布',
  },
  {
    version: 'v1.0',
    statusLabel: '已归档',
    badgeType: 'neutral',
    operator: 'admin',
    updatedAt: '2024/05/23 09:41:07',
    description: '初始草稿',
  },
]

const guideItems = [
  '一个项目可以有多种规则，当前仅支持“配置表查询”规则族。',
  '所有规则发布后立即生效，无需重启机器人。',
  '普通成员可编辑、发布、回滚规则，但不可修改项目级凭据。',
  '规则配置采用 Markdown 格式，发布前会进行结构校验。',
]

const filteredRules = computed(() => {
  const normalizedKeyword = keyword.value.trim().toLowerCase()
  return rules.filter((rule) => {
    const matchesTab =
      activeTab.value === 'all' ||
      (activeTab.value === 'config_lookup' && rule.family === 'config_lookup') ||
      (activeTab.value === 'future' && rule.family !== 'config_lookup')
    const matchesFamily = familyFilter.value === 'all' || rule.family === familyFilter.value
    const matchesKeyword =
      !normalizedKeyword ||
      rule.title.toLowerCase().includes(normalizedKeyword) ||
      rule.family.toLowerCase().includes(normalizedKeyword)
    return matchesTab && matchesFamily && matchesKeyword
  })
})

const selectedRule = computed(() => rules.find((rule) => rule.id === selectedRuleId.value) ?? rules[0])

function getOverviewValueClass(tone: OverviewTone): string {
  if (tone === 'success') return 'rule-config-overview__value--success'
  if (tone === 'warning') return 'rule-config-overview__value--warning'
  if (tone === 'danger') return 'rule-config-overview__value--danger'
  return ''
}

function selectRule(rule: RuleItem): void {
  if (!rule.supported) {
    ElMessage.info('当前版本暂不支持该规则族')
    return
  }
  selectedRuleId.value = rule.id
}

function openRuleDetail(rule: RuleItem = selectedRule.value): void {
  if (!rule.supported) {
    ElMessage.info('当前版本暂不支持该规则族')
    return
  }
  router.push({ name: 'rule-config-lookup' })
}

function showStaticNotice(label: string): void {
  ElMessage.info(`${label}将在后续阶段接入`)
}
</script>

<template>
  <div class="admin-dashboard-page rule-config-page flex h-full flex-col bg-canvas font-sans text-ink-700">
    <PageHeader
      breadcrumb="主页 / 规则配置"
      title="规则配置"
      description="在这里管理本项目的各类规则配置，规则发布后立即生效，无需重启机器人。"
    >
      <template #actions>
        <el-input
          v-model="keyword"
          placeholder="搜索规则"
          :prefix-icon="Search"
          clearable
          size="default"
          class="admin-dashboard-search rule-config-search"
        />
        <PrimaryButton @click="showStaticNotice('新建规则')">
          <template #icon><Plus /></template>
          新建规则
        </PrimaryButton>
      </template>
    </PageHeader>

    <div class="admin-dashboard-content rule-config-content flex flex-1 flex-col overflow-y-auto px-8 py-8">
      <AppCard as="section" padding="none" class="admin-dashboard-card rule-config-overview-card">
        <div class="rule-config-overview">
          <div
            v-for="item in overviewItems"
            :key="item.label"
            class="rule-config-overview__item"
          >
            <div class="rule-config-overview__label">{{ item.label }}</div>
            <div
              class="rule-config-overview__value"
              :class="getOverviewValueClass(item.tone)"
            >
              {{ item.value }}
            </div>
          </div>
        </div>
      </AppCard>

      <AppCard as="section" padding="none" class="admin-dashboard-card rule-config-workspace">
        <div class="rule-config-workspace__toolbar">
          <div class="rule-config-tabs" aria-label="规则分类">
            <button
              v-for="tab in tabs"
              :key="tab.id"
              type="button"
              class="rule-config-tab"
              :class="{ 'rule-config-tab--active': activeTab === tab.id }"
              @click="activeTab = tab.id"
            >
              {{ tab.label }}
            </button>
          </div>

          <el-select v-model="familyFilter" class="rule-config-family-select" size="default">
            <el-option label="规则族：全部" value="all" />
            <el-option label="配置表查询" value="config_lookup" />
            <el-option label="项目校验规则" value="project_check" />
            <el-option label="目录查询规则" value="directory_query" />
          </el-select>
        </div>

        <div class="rule-config-workspace__body">
          <aside class="rule-config-list-panel">
            <div class="rule-config-panel-title">规则列表</div>

            <div class="rule-config-rule-list">
              <article
                v-for="rule in filteredRules"
                :key="rule.id"
                class="rule-config-rule"
                :class="{
                  'rule-config-rule--active': selectedRule.id === rule.id,
                  'rule-config-rule--disabled': !rule.supported,
                }"
                @click="selectRule(rule)"
              >
                <div class="rule-config-rule__icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M4 5h16v14H4z M4 10h16 M9 5v14" />
                  </svg>
                </div>

                <div class="rule-config-rule__main">
                  <div class="rule-config-rule__title-row">
                    <h2 class="rule-config-rule__title">
                      {{ rule.title }}（{{ rule.family }}）
                    </h2>
                    <StatusBadge :type="rule.badgeType" :label="rule.statusLabel" />
                    <span v-if="rule.futureLabel" class="rule-config-future-badge">
                      {{ rule.futureLabel }}
                    </span>
                  </div>
                  <p class="rule-config-rule__meta">
                    规则族：{{ rule.family }}
                  </p>
                  <p class="rule-config-rule__meta">
                    最后更新：{{ rule.updatedAt }}
                  </p>
                </div>

                <div class="rule-config-rule__actions">
                  <button
                    type="button"
                    class="ec-action-link"
                    :class="{ 'rule-config-rule__action--disabled': !rule.supported }"
                    @click.stop="openRuleDetail(rule)"
                  >
                    {{ rule.supported ? '查看详情' : '暂未开放' }}
                  </button>
                </div>
              </article>
            </div>

            <div class="rule-config-list-count">共 {{ filteredRules.length }} 条</div>
          </aside>

          <section class="rule-config-summary">
            <div class="rule-config-summary__head">
              <div class="min-w-0">
                <div class="rule-config-summary__title-row">
                  <h2 class="rule-config-summary__title">
                    {{ selectedRule.title }}（{{ selectedRule.family }}）
                  </h2>
                  <StatusBadge :type="selectedRule.badgeType" :label="selectedRule.statusLabel" />
                </div>
                <p class="rule-config-summary__description">
                  {{ selectedRule.description }}
                </p>
              </div>
              <PrimaryButton size="sm" @click="openRuleDetail()">
                进入编辑
              </PrimaryButton>
            </div>

            <div class="rule-config-summary-grid">
              <div>
                <span>规则族</span>
                <strong>{{ selectedRule.family }}</strong>
              </div>
              <div>
                <span>查询类型数量</span>
                <strong>5 个</strong>
              </div>
              <div>
                <span>当前版本</span>
                <strong>v1.3</strong>
              </div>
              <div>
                <span>发布者</span>
                <strong>admin</strong>
              </div>
              <div>
                <span>发布时间</span>
                <strong>2024/05/27 02:32:18</strong>
              </div>
            </div>

            <div class="rule-config-state-row">
              <StatusBadge type="success" label="发布后立即生效，无需重启机器人" />
              <div class="rule-config-summary-actions">
                <SecondaryButton size="sm" @click="showStaticNotice('版本历史')">
                  版本历史
                </SecondaryButton>
                <SecondaryButton size="sm" @click="showStaticNotice('回滚版本')">
                  回滚版本
                </SecondaryButton>
                <PrimaryButton size="sm" @click="openRuleDetail()">
                  试查规则
                </PrimaryButton>
              </div>
            </div>

            <div class="rule-config-version-block">
              <div class="rule-config-panel-title">最近版本</div>
              <DataTable aria-label="最近版本">
                <template #head>
                  <tr>
                    <th class="w-[90px]">版本号</th>
                    <th class="w-[110px]">状态</th>
                    <th class="w-[120px]">操作人</th>
                    <th class="w-[180px]">更新时间</th>
                    <th>说明</th>
                    <th class="w-[90px]">操作</th>
                  </tr>
                </template>
                <template #body>
                  <tr
                    v-for="version in versions"
                    :key="version.version"
                    class="bg-white transition hover:bg-gray-50"
                  >
                    <td class="font-mono font-semibold text-ink-900">{{ version.version }}</td>
                    <td>
                      <StatusBadge :type="version.badgeType" :label="version.statusLabel" />
                    </td>
                    <td>{{ version.operator }}</td>
                    <td class="font-mono text-[12px] text-ink-500">{{ version.updatedAt }}</td>
                    <td>
                      <span class="truncate-line">{{ version.description }}</span>
                    </td>
                    <td>
                      <button type="button" class="ec-action-link" @click="showStaticNotice('版本详情')">
                        详情
                      </button>
                    </td>
                  </tr>
                </template>
              </DataTable>
            </div>
          </section>
        </div>
      </AppCard>

      <AppCard as="section" padding="none" class="admin-dashboard-card rule-config-guide">
        <div class="rule-config-guide__title">规则说明</div>
        <div class="rule-config-guide__grid">
          <div
            v-for="item in guideItems"
            :key="item"
            class="rule-config-guide__item"
          >
            <span class="rule-config-guide__dot"></span>
            <span>{{ item }}</span>
          </div>
        </div>
      </AppCard>
    </div>
  </div>
</template>

<style scoped>
.rule-config-page,
.rule-config-content,
.rule-config-workspace,
.rule-config-workspace__body,
.rule-config-list-panel,
.rule-config-summary {
  min-width: 0;
}

.rule-config-overview {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0;
  padding: 24px 26px;
}

.rule-config-overview__item {
  min-width: 0;
  border-right: 1px solid var(--color-border);
  padding: 0 24px;
}

.rule-config-overview__item:first-child {
  padding-left: 0;
}

.rule-config-overview__item:last-child {
  border-right: 0;
  padding-right: 0;
}

.rule-config-overview__label {
  color: #64748b;
  font-size: 13px;
  font-weight: 650;
}

.rule-config-overview__value {
  overflow: hidden;
  margin-top: 10px;
  color: var(--color-text-main);
  font-size: 26px;
  font-weight: 850;
  line-height: 1.15;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rule-config-overview__value--success {
  color: var(--color-success);
}

.rule-config-overview__value--warning {
  color: var(--color-warning);
}

.rule-config-overview__value--danger {
  color: var(--color-danger);
}

.rule-config-workspace__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--color-border);
  padding: 0 16px;
}

.rule-config-tabs {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 4px;
  overflow-x: auto;
  padding-top: 10px;
}

.rule-config-tab {
  min-height: 44px;
  flex: 0 0 auto;
  border: 0;
  border-top: 3px solid transparent;
  background: transparent;
  color: #475569;
  cursor: pointer;
  font-size: 14px;
  font-weight: 750;
  padding: 0 18px;
}

.rule-config-tab--active {
  border-top-color: var(--color-primary);
  color: var(--color-primary);
  background: #ffffff;
  box-shadow: 0 1px 0 #ffffff;
}

.rule-config-family-select {
  width: 160px;
  flex: 0 0 auto;
}

.rule-config-workspace__body {
  display: grid;
  grid-template-columns: minmax(320px, 35%) minmax(0, 1fr);
  min-height: 520px;
}

.rule-config-list-panel {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--color-border);
  padding: 20px 18px;
}

.rule-config-panel-title {
  color: var(--color-text-main);
  font-size: 16px;
  font-weight: 800;
  line-height: 1.3;
}

.rule-config-rule-list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}

.rule-config-rule {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  min-width: 0;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: #ffffff;
  cursor: pointer;
  padding: 16px;
  transition:
    background-color 160ms cubic-bezier(0.2, 0, 0, 1),
    border-color 160ms cubic-bezier(0.2, 0, 0, 1),
    box-shadow 160ms cubic-bezier(0.2, 0, 0, 1),
    transform 160ms cubic-bezier(0.2, 0, 0, 1);
}

.rule-config-rule:hover {
  border-color: #c9d8ee;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.06);
  transform: translateY(-1px);
}

.rule-config-rule--active {
  border-color: rgba(15, 98, 254, 0.58);
  background: linear-gradient(180deg, #ffffff, #f4f8ff);
  box-shadow: 0 10px 24px rgba(15, 98, 254, 0.11);
}

.rule-config-rule--disabled {
  background: #fbfcff;
}

.rule-config-rule__icon {
  display: inline-flex;
  width: 38px;
  height: 38px;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: #ffffff;
  background: var(--color-primary);
  box-shadow: 0 8px 16px rgba(15, 98, 254, 0.18);
}

.rule-config-rule--disabled .rule-config-rule__icon {
  background: #64748b;
  box-shadow: none;
}

.rule-config-rule__icon svg {
  width: 18px;
  height: 18px;
}

.rule-config-rule__main {
  min-width: 0;
}

.rule-config-rule__title-row,
.rule-config-summary__title-row {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.rule-config-rule__title,
.rule-config-summary__title {
  overflow: hidden;
  margin: 0;
  color: var(--color-text-main);
  font-size: 15px;
  font-weight: 850;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rule-config-rule__meta {
  overflow: hidden;
  margin: 6px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rule-config-rule__actions {
  display: flex;
  align-items: center;
}

.rule-config-rule__action--disabled {
  color: #94a3b8 !important;
}

.rule-config-future-badge {
  display: inline-flex;
  min-height: 22px;
  align-items: center;
  border-radius: var(--radius-pill);
  color: var(--color-warning);
  background: var(--color-warning-soft);
  font-size: 12px;
  font-weight: 750;
  line-height: 1;
  padding: 0 9px;
}

.rule-config-list-count {
  margin-top: 18px;
  color: #64748b;
  font-size: 13px;
}

.rule-config-summary {
  padding: 22px 24px 24px;
}

.rule-config-summary__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.rule-config-summary__description {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.55;
}

.rule-config-summary-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0;
  margin-top: 22px;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 20px;
}

.rule-config-summary-grid > div {
  min-width: 0;
  border-right: 1px solid var(--color-border-light);
  padding: 0 18px;
}

.rule-config-summary-grid > div:first-child {
  padding-left: 0;
}

.rule-config-summary-grid > div:last-child {
  border-right: 0;
  padding-right: 0;
}

.rule-config-summary-grid span {
  display: block;
  overflow: hidden;
  color: #64748b;
  font-size: 12px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rule-config-summary-grid strong {
  display: block;
  overflow: hidden;
  margin-top: 10px;
  color: var(--color-text-main);
  font-size: 14px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rule-config-state-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  border-bottom: 1px solid var(--color-border);
  padding: 18px 0;
}

.rule-config-summary-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.rule-config-version-block {
  margin-top: 18px;
}

.rule-config-version-block .ui-data-table {
  margin-top: 12px;
}

.rule-config-guide {
  padding: 18px 22px;
}

.rule-config-guide__title {
  color: var(--color-primary);
  font-size: 15px;
  font-weight: 850;
}

.rule-config-guide__grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px 24px;
  margin-top: 14px;
}

.rule-config-guide__item {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  gap: 8px;
  color: #475569;
  font-size: 13px;
  line-height: 1.55;
}

.rule-config-guide__dot {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: var(--radius-pill);
  background: var(--color-success);
  margin-top: 6px;
}

@media (max-width: 1366px) {
  .rule-config-summary-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 16px 0;
  }

  .rule-config-guide__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 1180px) {
  .rule-config-workspace__body {
    grid-template-columns: 1fr;
  }

  .rule-config-list-panel {
    border-right: 0;
    border-bottom: 1px solid var(--color-border);
  }

  .rule-config-overview {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 20px 0;
  }

  .rule-config-overview__item {
    border-right: 0;
    padding-right: 18px;
    padding-left: 0;
  }
}

@media (max-width: 768px) {
  .rule-config-workspace__toolbar,
  .rule-config-summary__head,
  .rule-config-state-row {
    align-items: stretch;
    flex-direction: column;
  }

  .rule-config-family-select,
  .rule-config-search {
    width: 100%;
  }

  .rule-config-rule {
    grid-template-columns: 38px minmax(0, 1fr);
  }

  .rule-config-rule__actions {
    grid-column: 2;
  }

  .rule-config-overview,
  .rule-config-summary-grid,
  .rule-config-guide__grid {
    grid-template-columns: 1fr;
  }

  .rule-config-summary-grid > div {
    border-right: 0;
    padding-right: 0;
    padding-left: 0;
  }
}
</style>
