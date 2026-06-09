<script setup lang="ts">
import { ref } from 'vue'
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

interface RuleOverviewItem {
  label: string
  value: string
  badge?: { label: string; type: StatusBadgeType }
}

interface MarkdownLine {
  no: number
  text: string
  key?: string
}

interface ValidationItem {
  label: string
  type: 'success' | 'warning'
}

interface VersionRow {
  version: string
  statusLabel: string
  badgeType: StatusBadgeType
  operator: string
  updatedAt: string
  description: string
  actions: string[]
}

interface CredentialRow {
  label: string
  statusLabel: string
  accountLabel: string
  secretLabel: string
  updatedAt: string
}

interface TrialResultRow {
  id: string
  name: string
  price: string
}

const router = useRouter()
const auth = useAuthStore()
const projectId = ref('default')
const keyword = ref('')
const useDraftTrial = ref(true)
const trialStatus = ref<'success' | 'failed'>('success')

const ruleOverview: RuleOverviewItem[] = [
  {
    label: '规则分组',
    value: '配置表查询（config_lookup）',
    badge: { label: '已发布', type: 'success' },
  },
  {
    label: '当前版本',
    value: 'v1.3',
  },
  {
    label: '已发布版本',
    value: 'v1.3',
  },
  {
    label: '最后更新人',
    value: 'admin',
  },
  {
    label: '发布时间',
    value: '2024/05/27 02:32:18',
  },
]

const markdownLines: MarkdownLine[] = [
  { no: 1, text: '查询类型: 礼包', key: '查询类型' },
  { no: 2, text: '数据根: game_datas', key: '数据根' },
  { no: 3, text: '配置文件: IAPConfig.xls', key: '配置文件' },
  { no: 4, text: '' },
  { no: 5, text: '分页:', key: '分页' },
  { no: 6, text: '  - 名称: AbsolutePack', key: '名称' },
  { no: 7, text: '    ID字段: INT_PackageId', key: 'ID字段' },
  { no: 8, text: '    名称字段: DESC', key: '名称字段' },
  { no: 9, text: '    输出字段:', key: '输出字段' },
  { no: 10, text: '      - INT_PackageId' },
  { no: 11, text: '      - DESC' },
  { no: 12, text: '      - STR_ServerCond_US' },
  { no: 13, text: '' },
  { no: 14, text: '  - 名称: Template', key: '名称' },
  { no: 15, text: '    ID字段: INT_PackageId', key: 'ID字段' },
  { no: 16, text: '    名称字段: DESC', key: '名称字段' },
  { no: 17, text: '    输出字段:', key: '输出字段' },
  { no: 18, text: '      - INT_PackageId' },
  { no: 19, text: '      - 字段: DESC', key: '字段' },
  { no: 20, text: '        显示名: 礼包名称', key: '显示名' },
  { no: 21, text: '      - INT_PriceId' },
  { no: 22, text: '' },
  { no: 23, text: '引用:', key: '引用' },
  { no: 24, text: '  - 名称: price', key: '名称' },
  { no: 25, text: '    配置文件: Price.xls', key: '配置文件' },
  { no: 26, text: '    分页: Price', key: '分页' },
  { no: 27, text: '    关联: INT_PriceId=INT_PriceId', key: '关联' },
  { no: 28, text: '    输出字段:', key: '输出字段' },
  { no: 29, text: '      - 字段: INT_Point', key: '字段' },
  { no: 30, text: '        显示名: 价格点数', key: '显示名' },
]

const validationItems: ValidationItem[] = [
  { label: '中文配置项合法', type: 'success' },
  { label: '必填字段完整', type: 'success' },
  { label: 'query_root 引用有效', type: 'success' },
  { label: '路径字段安全', type: 'success' },
]

const parseSummaryItems = [
  { label: '查询类型', value: '礼包' },
  { label: '数据根', value: 'game_datas' },
  { label: '主配置文件', value: 'IAPConfig.xls' },
  { label: '分页设置', value: 'AbsolutePack、Template' },
  { label: '引用配置', value: 'price -> Price.xls / Price' },
]

const versionRows: VersionRow[] = [
  {
    version: 'v1.3',
    statusLabel: '已发布',
    badgeType: 'success',
    operator: 'admin',
    updatedAt: '2024/05/27 02:32:18',
    description: '优化输出字段，补充 price 字段',
    actions: ['查看', '对比'],
  },
  {
    version: 'v1.2',
    statusLabel: '草稿',
    badgeType: 'warning',
    operator: 'admin',
    updatedAt: '2024/05/26 18:15:42',
    description: '调整分页默认条数为 50',
    actions: ['查看', '发布', '对比'],
  },
  {
    version: 'v1.1',
    statusLabel: '已发布',
    badgeType: 'success',
    operator: 'admin',
    updatedAt: '2024/05/24 10:09:31',
    description: '初始版本发布',
    actions: ['查看', '对比'],
  },
  {
    version: 'v1.0',
    statusLabel: '已归档',
    badgeType: 'neutral',
    operator: 'admin',
    updatedAt: '2024/05/23 09:41:07',
    description: '初始草稿',
    actions: ['查看', '回滚', '对比'],
  },
]

const credentialRows: CredentialRow[] = [
  {
    label: 'SVN 凭据',
    statusLabel: '已连接',
    accountLabel: '账号：s******n',
    secretLabel: '密码：********',
    updatedAt: '2024/05/27 01:20:11',
  },
  {
    label: 'AI 凭据',
    statusLabel: '已连接',
    accountLabel: '模型：gpt-compatible',
    secretLabel: '密钥：************',
    updatedAt: '2024/05/27 01:20:11',
  },
]

const trialForm = {
  queryType: '礼包',
  versionFolder: '/datas_qa88',
  queryText: '26051802',
  successText: '命中 2 条',
  failedText: '未找到匹配配置',
}

const trialResultRows: TrialResultRow[] = [
  { id: '26051802', name: '26年7月扭蛋机礼包-99.99', price: '9999' },
  { id: '26051802', name: '26年7月扭蛋机礼包-99.99（模板）', price: '9999' },
]

function backToRuleConfigs(): void {
  router.push({ name: 'rule-configs' })
}

function showStaticNotice(label: string): void {
  ElMessage.info(`${label}将在后续阶段接入`)
}

function showOnlyConfigLookupNotice(): void {
  ElMessage.info('当前仅支持配置表查询规则')
}

function getLineParts(line: MarkdownLine): { prefix: string; key: string; suffix: string } {
  if (!line.key) {
    return { prefix: line.text, key: '', suffix: '' }
  }
  const keyIndex = line.text.indexOf(line.key)
  if (keyIndex < 0) {
    return { prefix: '', key: line.key, suffix: line.text }
  }
  return {
    prefix: line.text.slice(0, keyIndex),
    key: line.key,
    suffix: line.text.slice(keyIndex + line.key.length),
  }
}
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

    <div class="admin-dashboard-content rule-lookup-content flex flex-1 flex-col overflow-y-auto px-8 py-8">
      <AppCard as="section" padding="none" class="admin-dashboard-card rule-lookup-overview-card">
        <div class="rule-lookup-overview">
          <div class="rule-lookup-overview__main">
            <span class="rule-lookup-step">01</span>
            <div class="min-w-0">
              <div class="rule-lookup-overview__title-row">
                <h2>规则概览</h2>
                <StatusBadge type="success" label="已发布" />
                <StatusBadge type="warning" label="草稿有更新" />
              </div>
              <p>配置表查询规则当前处于发布状态，草稿变更可保存后继续发布。</p>
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
              <SecondaryButton size="sm" @click="showStaticNotice('插入示例模板')">
                插入示例模板
              </SecondaryButton>
              <SecondaryButton size="sm" @click="showStaticNotice('结构校验')">
                结构校验
              </SecondaryButton>
              <SecondaryButton size="sm" @click="showStaticNotice('保存草稿')">
                保存草稿
              </SecondaryButton>
              <PrimaryButton size="sm" @click="showStaticNotice('发布')">
                发布
              </PrimaryButton>
            </div>
          </div>

          <div class="rule-lookup-code-editor" aria-label="Markdown 规则示例">
            <div v-for="line in markdownLines" :key="line.no" class="rule-lookup-code-line">
              <span class="rule-lookup-code-line__no">{{ line.no }}</span>
              <code>
                <template v-if="line.key">
                  <span>{{ getLineParts(line).prefix }}</span><span class="rule-lookup-code-key">{{ getLineParts(line).key }}</span><span>{{ getLineParts(line).suffix }}</span>
                </template>
                <template v-else>{{ line.text }}</template>
              </code>
            </div>
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
                    @click="showStaticNotice(action)"
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
              <div v-if="auth.isProjectAdmin" class="rule-lookup-credential-actions">
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
            <PrimaryButton size="sm" @click="showStaticNotice('开始试查')">
              开始试查
            </PrimaryButton>
          </div>

          <div class="rule-lookup-trial-form">
            <label>
              <span>查询类型</span>
              <el-input :model-value="trialForm.queryType" readonly />
            </label>
            <label>
              <span>版本目录</span>
              <el-input :model-value="trialForm.versionFolder" readonly />
            </label>
            <label>
              <span>查询内容</span>
              <el-input :model-value="trialForm.queryText" readonly />
            </label>
            <el-checkbox v-model="useDraftTrial">
              使用当前草稿试查
            </el-checkbox>
          </div>

          <div class="rule-lookup-trial-result">
            <div class="rule-lookup-trial-result__head">
              <span>试查结果</span>
              <StatusBadge
                :type="trialStatus === 'success' ? 'success' : 'danger'"
                :label="trialStatus === 'success' ? trialForm.successText : trialForm.failedText"
              />
            </div>

            <DataTable aria-label="试查结果">
              <template #head>
                <tr>
                  <th>id</th>
                  <th>name</th>
                  <th>price</th>
                </tr>
              </template>
              <template #body>
                <tr v-for="row in trialResultRows" :key="`${row.id}-${row.name}`" class="bg-white transition hover:bg-gray-50">
                  <td class="font-mono text-ink-900">{{ row.id }}</td>
                  <td>{{ row.name }}</td>
                  <td>{{ row.price }}</td>
                </tr>
              </template>
            </DataTable>
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
