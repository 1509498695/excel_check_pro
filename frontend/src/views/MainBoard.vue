<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

import AppCard from '../components/shell/AppCard.vue'
import CollapsibleSection from '../components/shell/CollapsibleSection.vue'
import MetricCard from '../components/shell/MetricCard.vue'
import DataSourcePanel from '../components/workbench/DataSourcePanel.vue'
import ResultBoardPanel from '../components/workbench/ResultBoardPanel.vue'
import SourcePathReplacementDialog from '../components/workbench/SourcePathReplacementDialog.vue'
import WorkbenchRuleOrchestrationPanel from '../components/workbench/WorkbenchRuleOrchestrationPanel.vue'
import VariablePoolPanel from '../components/workbench/VariablePoolPanel.vue'
import { ImportPersonalRulesDialog } from '../features/fixed-rules-import'
import PageHeader from '../components/shell/PageHeader.vue'
import PrimaryButton from '../components/shell/PrimaryButton.vue'
import SecondaryButton from '../components/shell/SecondaryButton.vue'
import type { StatusBadgeType } from '../components/shell'
import { useWorkbenchStore } from '../store/workbench'
import { useFixedRulesStore } from '../store/fixedRules'

// 保持原有逻辑不变：工作台的数据加载、自动保存、执行与滚动行为全部维持现状。
const store = useWorkbenchStore()
const fixedRulesStore = useFixedRulesStore()
const router = useRouter()

type StepIndex = 1 | 2 | 3 | 4
type SectionStatus = 'pending' | 'active' | 'done'
type StatTone = 'pending' | 'active' | 'done' | 'warn' | 'error'
type SectionKey = 'source' | 'variable' | 'rule' | 'result'

const selectedGuideStep = ref<StepIndex | null>(null)
const hasManuallySelectedGuideStep = ref(false)
const selectedRuleIds = ref<string[]>([])
const importDialogVisible = ref(false)

onMounted(async () => {
  // 保留原有业务逻辑：工作台初始化仍并行读取能力与服务端配置。
  await Promise.all([store.loadCapabilities(), store.loadFromServer()])
})

watch(
  () => [store.sources, store.variables, store.ruleGroups, store.orchestrationRules],
  () => {
    store.triggerAutoSave()
  },
  { deep: true },
)

watch(
  () => store.orchestrationRules.map((rule) => rule.rule_id),
  (nextRuleIds, previousRuleIds = []) => {
    const validRuleIds = new Set(nextRuleIds)
    const previousRuleIdSet = new Set(previousRuleIds)
    const nextSelectedRuleIdSet = new Set(
      selectedRuleIds.value.filter((ruleId) => validRuleIds.has(ruleId)),
    )

    nextRuleIds.forEach((ruleId) => {
      if (!previousRuleIdSet.has(ruleId)) {
        nextSelectedRuleIdSet.add(ruleId)
      }
    })

    selectedRuleIds.value = nextRuleIds.filter((ruleId) =>
      nextSelectedRuleIdSet.has(ruleId),
    )
  },
  { immediate: true },
)

const sourceStepRef = ref<HTMLElement | null>(null)
const variableStepRef = ref<HTMLElement | null>(null)
const ruleStepRef = ref<HTMLElement | null>(null)
const resultStepRef = ref<HTMLElement | null>(null)
const dataSourcePanelRef = ref<{ openCreateDialog: () => void } | null>(null)
const sourcePathReplacementDialogRef = ref<{ openDialog: () => void } | null>(null)
const variablePoolPanelRef = ref<{
  openSingleCreateTab: () => Promise<void>
  openCompositeCreateTab: () => Promise<void>
} | null>(null)
const collapsedSections = reactive<Record<SectionKey, boolean>>({
  source: false,
  variable: false,
  rule: false,
  result: false,
})

const overviewItems = computed<
  Array<{
    label: string
    value: number
    pendingHint: string
    readyHint: string
    pendingTone: StatTone
    readyTone: StatTone
  }>
>(() => [
  {
    label: '数据源',
    value: store.sources.length,
    pendingHint: '未接入',
    readyHint: '已接入',
    pendingTone: 'warn',
    readyTone: 'done',
  },
  {
    label: '变量',
    value: store.variables.length,
    pendingHint: '未配置',
    readyHint: '已就绪',
    pendingTone: 'pending',
    readyTone: 'done',
  },
  {
    label: '规则',
    value: store.orchestrationRuleCount,
    pendingHint: '未配置',
    readyHint: '已就绪',
    pendingTone: 'pending',
    readyTone: 'done',
  },
  {
    label: '最近异常',
    value: store.abnormalResultTotal,
    pendingHint: '尚未执行',
    readyHint: '需关注',
    pendingTone: 'pending',
    readyTone: 'warn',
  },
])

const metricIconTones = ['primary', 'success', 'primary', 'warning'] as const

function getStatusBadgeType(tone: StatTone): StatusBadgeType {
  if (tone === 'done' || tone === 'active') return 'success'
  if (tone === 'warn') return 'warning'
  if (tone === 'error') return 'danger'
  return 'neutral'
}

function getMetricIconTone(index: number): (typeof metricIconTones)[number] {
  return metricIconTones[index] ?? 'primary'
}

const stepStatuses = computed<{
  source: SectionStatus
  variable: SectionStatus
  rule: SectionStatus
  result: SectionStatus
}>(() => ({
  source: store.sources.length ? 'done' : 'active',
  variable: !store.sources.length ? 'pending' : store.variables.length ? 'done' : 'active',
  rule: !store.variables.length ? 'pending' : store.orchestrationRuleCount ? 'done' : 'active',
  result: !store.orchestrationRuleCount
    ? 'pending'
    : store.executionMeta || store.pageError || store.svnUpdateSummary || store.svnUpdateResults.length
      ? 'done'
      : 'active',
}))

const stepHints = computed(() => ({
  source: store.sources.length
    ? `已接入 ${store.sources.length} 个数据源`
    : '至少接入 1 个',
  variable: !store.sources.length
    ? `已沉淀 ${store.variables.length} 个变量`
    : `已沉淀 ${store.variables.length} 个变量`,
  rule: !store.variables.length
    ? `已编排 ${store.orchestrationRuleCount} 条规则`
    : `已编排 ${store.orchestrationRuleCount} 条规则`,
  result: '扫描统计与异常明细',
}))

function getSectionStatusLabel(step: StepIndex): string {
  if (step === 4) {
    if (store.pageError) {
      return '需关注'
    }
    return store.executionMeta || store.svnUpdateSummary || store.svnUpdateResults.length
      ? '已完成'
      : '待执行'
  }

  if (step === 1) {
    return store.sources.length ? '已完成' : '待配置'
  }

  if (step === 2) {
    return store.variables.length ? '已完成' : '待配置'
  }

  return store.orchestrationRuleCount ? '已完成' : '待配置'
}

function getSectionStatusTone(step: StepIndex): 'pending' | 'done' | 'warn' {
  if (step === 4 && store.pageError) {
    return 'warn'
  }

  return getSectionStatusLabel(step) === '已完成' ? 'done' : 'pending'
}

const workflowGuide = computed(() => {
  if (!store.sources.length) {
    return { step: 1 as StepIndex, action: 'scroll' as const }
  }
  if (!store.variables.length) {
    return { step: 2 as StepIndex, action: 'scroll' as const }
  }
  if (!store.orchestrationRuleCount) {
    return { step: 3 as StepIndex, action: 'scroll' as const }
  }
  if (
    store.isExecuting ||
    store.isUpdatingSvn ||
    store.pageError ||
    store.executionMeta ||
    store.svnUpdateSummary ||
    store.svnUpdateResults.length
  ) {
    return { step: 4 as StepIndex, action: 'scroll' as const }
  }
  return { step: 4 as StepIndex, action: 'execute' as const }
})

const svnResultStats = computed(() => {
  const successCount = store.svnUpdateResults.filter((item) => item.status === 'success').length
  const failedCount = store.svnUpdateResults.length - successCount
  return { successCount, failedCount }
})

const activeGuideStep = computed(() => selectedGuideStep.value ?? workflowGuide.value.step)

const stepperItems = computed(() => [
  {
    step: 1 as StepIndex,
    label: '数据源',
    description: stepHints.value.source,
    status: stepStatuses.value.source,
  },
  {
    step: 2 as StepIndex,
    label: '变量池',
    description: stepHints.value.variable,
    status: stepStatuses.value.variable,
  },
  {
    step: 3 as StepIndex,
    label: '规则',
    description: stepHints.value.rule,
    status: stepStatuses.value.rule,
  },
  {
    step: 4 as StepIndex,
    label: '结果',
    description: stepHints.value.result,
    status: stepStatuses.value.result,
  },
])

watch(
  () => workflowGuide.value.step,
  (step) => {
    if (!hasManuallySelectedGuideStep.value) {
      selectedGuideStep.value = step
    }
  },
  { immediate: true },
)

function getStepRef(step: StepIndex): HTMLElement | null {
  if (step === 1) {
    return sourceStepRef.value
  }
  if (step === 2) {
    return variableStepRef.value
  }
  if (step === 3) {
    return ruleStepRef.value
  }
  return resultStepRef.value
}

function getSectionKey(step: StepIndex): SectionKey {
  if (step === 1) {
    return 'source'
  }
  if (step === 2) {
    return 'variable'
  }
  if (step === 3) {
    return 'rule'
  }
  return 'result'
}

function toggleSection(step: StepIndex): void {
  const key = getSectionKey(step)
  collapsedSections[key] = !collapsedSections[key]
}

async function ensureStepExpanded(step: StepIndex): Promise<void> {
  const key = getSectionKey(step)
  if (!collapsedSections[key]) {
    return
  }
  collapsedSections[key] = false
  await nextTick()
}

async function scrollToStep(step: StepIndex): Promise<void> {
  await nextTick()
  getStepRef(step)?.scrollIntoView({
    behavior: 'smooth',
    block: 'start',
  })
}

async function runExecution(): Promise<void> {
  if (store.hasBlockingSourceIssues) {
    ElMessage.warning('当前存在读取失败的数据源，请先修复数据源路径管理中的路径问题或重新接入数据源后再执行校验。')
    await ensureStepExpanded(1)
    await scrollToStep(1)
    return
  }

  if (!selectedRuleIds.value.length) {
    ElMessage.warning('请至少勾选一条需要校验的规则')
    return
  }

  try {
    // 保留原有业务逻辑：执行入口仍调用原有校验接口并沿用原结果刷新流程。
    await store.executeValidation(selectedRuleIds.value)
    await ensureStepExpanded(4)
    await scrollToStep(4)
    ElMessage.success('校验完成，结果已刷新。')
  } catch {
    await ensureStepExpanded(4)
    await scrollToStep(4)
  }
}

async function handleSvnUpdate(): Promise<void> {
  try {
    await store.runSvnUpdate()
    await ensureStepExpanded(4)
    await scrollToStep(4)
    ElMessage.success(store.svnUpdateSummary || 'SVN 更新完成。')
  } catch {
    await ensureStepExpanded(4)
    await scrollToStep(4)
  }
}

function openDataSourceCreate(): void {
  dataSourcePanelRef.value?.openCreateDialog()
}

function openSourcePathReplacementDialog(): void {
  sourcePathReplacementDialogRef.value?.openDialog()
}

function openUserGuide(): void {
  const guideUrl = router.resolve({ name: 'user-guide' }).href
  window.open(guideUrl, '_blank', 'noopener,noreferrer')
}

async function openImportPersonalRulesDialog(): Promise<void> {
  if (!store.orchestrationRuleCount) {
    ElMessage.warning('当前暂无可导入的个人校验规则。')
    return
  }
  await store.saveConfigNow()
  importDialogVisible.value = true
}

async function handleImportFinished(): Promise<void> {
  await fixedRulesStore.loadConfig()
  ElMessage.success('项目校验配置已刷新。')
}

function openSingleVariableCreate(): void {
  void variablePoolPanelRef.value?.openSingleCreateTab()
}

function openCompositeVariableCreate(): void {
  void variablePoolPanelRef.value?.openCompositeCreateTab()
}

async function handleStepperClick(step: StepIndex): Promise<void> {
  hasManuallySelectedGuideStep.value = true
  selectedGuideStep.value = step
  await ensureStepExpanded(step)
  await scrollToStep(step)
}

async function handleSourceSaved(_sourceId: string): Promise<void> {
  await ensureStepExpanded(2)
  await scrollToStep(2)
}

async function handleVariableSaved(_tag: string): Promise<void> {
  await ensureStepExpanded(2)
  await scrollToStep(2)
}

function buildOrderedSelectedRuleIds(nextSelectedRuleIdSet: Set<string>): string[] {
  return store.orchestrationRules
    .map((rule) => rule.rule_id)
    .filter((ruleId) => nextSelectedRuleIdSet.has(ruleId))
}

function handleToggleRuleSelection(ruleId: string): void {
  const nextSelectedRuleIdSet = new Set(selectedRuleIds.value)
  if (nextSelectedRuleIdSet.has(ruleId)) {
    nextSelectedRuleIdSet.delete(ruleId)
  } else {
    nextSelectedRuleIdSet.add(ruleId)
  }
  selectedRuleIds.value = buildOrderedSelectedRuleIds(nextSelectedRuleIdSet)
}

function handleToggleVisibleRuleSelection(payload: {
  ruleIds: string[]
  checked: boolean
}): void {
  const nextSelectedRuleIdSet = new Set(selectedRuleIds.value)
  payload.ruleIds.forEach((ruleId) => {
    if (payload.checked) {
      nextSelectedRuleIdSet.add(ruleId)
      return
    }
    nextSelectedRuleIdSet.delete(ruleId)
  })
  selectedRuleIds.value = buildOrderedSelectedRuleIds(nextSelectedRuleIdSet)
}
</script>

<template>
  <div class="personal-check-page flex h-full flex-col bg-canvas font-sans text-ink-700">
    <!-- TopBar：极简，左面包屑+标题，右动作 -->
    <PageHeader breadcrumb="主页 / 个人校验" title="配置表个人校验">
      <template #actions>
        <SecondaryButton
          :disabled="store.isUpdatingSvn || !store.canRunSvnUpdate"
          @click="handleSvnUpdate"
        >
          {{ store.isUpdatingSvn ? 'SVN 更新中…' : 'SVN 更新' }}
        </SecondaryButton>
        <PrimaryButton @click="openUserGuide">
          <template #icon>
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M4 19.5V5a2 2 0 0 1 2-2h10.5L20 6.5V19a2 2 0 0 1-2 2H6a2 2 0 0 1-2-1.5Z" />
              <path d="M15 3v5h5" />
              <path d="M8 12h8" />
              <path d="M8 16h6" />
            </svg>
          </template>
          系统使用说明
        </PrimaryButton>
        <SecondaryButton
          v-if="store.pageError"
          @click="store.clearPageError()"
        >
          <template #icon>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M5 13l4 4L19 7" />
            </svg>
          </template>
          清除错误
        </SecondaryButton>
      </template>
    </PageHeader>

    <!-- 主滚动区 -->
    <div class="personal-check-content flex flex-1 flex-col gap-6 overflow-y-auto px-8 py-8">
      <!-- Stepper -->
      <AppCard as="section" aria-label="进度" padding="none" class="personal-stepper-card">
        <div class="personal-stepper">
          <!-- 保留原有业务逻辑：步骤进度仍基于 stepperItems 计算结果遍历渲染 -->
          <template v-for="(item, index) in stepperItems" :key="item.step">
            <button
              type="button"
              class="personal-stepper__item"
              :class="[
                item.status === 'done' ? 'personal-stepper__item--done' : '',
                item.step === activeGuideStep ? 'personal-stepper__item--active' : '',
                item.status === 'pending' ? 'personal-stepper__item--pending' : '',
              ]"
              @click="handleStepperClick(item.step)"
            >
              <span class="personal-stepper__badge">
                {{ item.step }}
              </span>
              <div class="personal-stepper__copy">
                <div class="personal-stepper__title">{{ item.label }}</div>
                <div class="personal-stepper__description">{{ item.description }}</div>
              </div>
            </button>
            <div
              v-if="index < stepperItems.length - 1"
              class="personal-stepper__line"
              :class="item.status === 'done' ? 'personal-stepper__line--done' : ''"
            ></div>
          </template>
        </div>
      </AppCard>

      <!-- KPI 4 列：StatPill；不浮起 -->
      <section aria-label="概览" class="grid grid-cols-4 gap-4">
        <!-- 保留原有业务逻辑：概览卡仍基于 overviewItems 计算结果遍历渲染 -->
        <MetricCard
          v-for="(item, index) in overviewItems"
          :key="item.label"
          :label="item.label"
          :value="item.value"
          :status-label="item.value > 0 ? item.readyHint : item.pendingHint"
          :status-type="getStatusBadgeType(item.value > 0 ? item.readyTone : item.pendingTone)"
          :icon-tone="getMetricIconTone(index)"
        >
          <template #icon>
            <svg v-if="item.label === '数据源'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <ellipse cx="12" cy="5" rx="7" ry="3" />
              <path d="M5 5v6c0 1.66 3.13 3 7 3s7-1.34 7-3V5" />
              <path d="M5 11v6c0 1.66 3.13 3 7 3s7-1.34 7-3v-6" />
            </svg>
            <svg v-else-if="item.label === '变量'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="m8 8-4 4 4 4" />
              <path d="m16 8 4 4-4 4" />
            </svg>
            <svg v-else-if="item.label === '规则'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 4v5" />
              <path d="M6 20v-4a3 3 0 0 1 3-3h6a3 3 0 0 1 3 3v4" />
              <rect x="9" y="9" width="6" height="5" rx="1" />
              <path d="M6 20h0M18 20h0" />
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 7v6" />
              <path d="M12 17h.01" />
            </svg>
          </template>
        </MetricCard>
      </section>

      <!-- 4 个步骤工作区 -->
      <div ref="sourceStepRef">
        <CollapsibleSection
          step="01"
          title="数据源"
          description="接入 Excel、SVN 或飞书电子表格来源"
          :status-label="getSectionStatusLabel(1)"
          :status-tone="getSectionStatusTone(1)"
          :active="activeGuideStep === 1"
          :collapsed="collapsedSections.source"
          content-class="pt-1"
          @toggle="toggleSection(1)"
        >
          <template #actions>
            <SecondaryButton
              size="sm"
              @click="openSourcePathReplacementDialog"
            >
              数据源路径管理
            </SecondaryButton>
            <PrimaryButton
              size="sm"
              @click="openDataSourceCreate"
            >
              <template #icon><Plus /></template>
              新增数据源
            </PrimaryButton>
          </template>

          <DataSourcePanel
            ref="dataSourcePanelRef"
            toolbar-mode="hidden"
            :source-issues="store.sourceIssues"
            @saved="handleSourceSaved"
          />
        </CollapsibleSection>
      </div>

      <div ref="variableStepRef">
        <CollapsibleSection
          step="02"
          title="变量池"
          description="沉淀后续规则编排会复用的字段与组合变量"
          :status-label="getSectionStatusLabel(2)"
          :status-tone="getSectionStatusTone(2)"
          :active="activeGuideStep === 2"
          :collapsed="collapsedSections.variable"
          content-class="pt-1"
          @toggle="toggleSection(2)"
        >
          <template #actions>
            <PrimaryButton
              size="sm"
              :disabled="!store.sources.length"
              @click="openSingleVariableCreate"
            >
              <template #icon><Plus /></template>
              添加单个变量
            </PrimaryButton>
            <PrimaryButton
              size="sm"
              :disabled="!store.sources.length"
              @click="openCompositeVariableCreate"
            >
              <template #icon><Plus /></template>
              添加组合变量
            </PrimaryButton>
          </template>

          <VariablePoolPanel ref="variablePoolPanelRef" toolbar-mode="hidden" @saved="handleVariableSaved" />
        </CollapsibleSection>
      </div>

      <div ref="ruleStepRef">
        <CollapsibleSection
          step="03"
          title="规则"
          description="按组组织比较、非空、唯一和组合变量规则"
          :status-label="getSectionStatusLabel(3)"
          :status-tone="getSectionStatusTone(3)"
          :active="activeGuideStep === 3"
          :collapsed="collapsedSections.rule"
          content-class="pt-3"
          @toggle="toggleSection(3)"
        >
          <WorkbenchRuleOrchestrationPanel
            :selected-rule-ids="selectedRuleIds"
            @toggle-rule-selection="handleToggleRuleSelection"
            @toggle-visible-rule-selection="handleToggleVisibleRuleSelection"
          />
          <div class="personal-rule-actions">
            <SecondaryButton
              :disabled="store.isExecuting || !store.orchestrationRuleCount"
              @click="openImportPersonalRulesDialog"
            >
              一键导入到项目校验
            </SecondaryButton>
            <PrimaryButton
              :disabled="store.isExecuting"
              @click="runExecution"
            >
              <template #icon>
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M8 5v14l11-7z" />
                </svg>
              </template>
              {{ store.isExecuting ? '执行中...' : '执行校验' }}
            </PrimaryButton>
          </div>
        </CollapsibleSection>
      </div>

      <div ref="resultStepRef">
        <CollapsibleSection
          step="04"
          title="结果"
          description="查看扫描统计、失败来源和异常明细"
          :status-label="getSectionStatusLabel(4)"
          :status-tone="getSectionStatusTone(4)"
          :active="activeGuideStep === 4"
          :collapsed="collapsedSections.result"
          header-class="border-b border-line pb-4"
          content-class="pt-4"
          @toggle="toggleSection(4)"
        >
          <ResultBoardPanel :store="store" :rule-count="store.orchestrationRuleCount" variant="personal">
            <template #extra>
              <div
                v-if="store.svnUpdateSummary"
                class="rounded-card border border-line border-l-4 border-l-accent bg-accent-soft/40 px-5 py-3"
              >
                <div class="text-[13px] font-medium text-ink-900">{{ store.svnUpdateSummary }}</div>
                <div class="mt-1 text-[12px] text-ink-500">
                  成功 {{ svnResultStats.successCount }} 个，失败 {{ svnResultStats.failedCount }} 个
                </div>
              </div>

              <div v-if="store.svnUpdateResults.length" class="flex flex-col gap-2">
                <article
                  v-for="item in store.svnUpdateResults"
                  :key="item.working_copy"
                  class="rounded-field border border-line px-4 py-3"
                  :class="item.status === 'error' ? 'border-l-4 border-l-danger bg-danger-soft/30' : 'bg-canvas'"
                >
                  <div class="truncate font-mono text-[12px] text-ink-900">{{ item.working_copy }}</div>
                  <div class="mt-1 text-[12px]" :class="item.status === 'error' ? 'text-danger' : 'text-success'">
                    {{ item.status === 'success' ? '更新成功' : '更新失败' }}
                  </div>
                  <div class="mt-1 whitespace-pre-wrap break-all text-[12px] text-ink-500">
                    {{ item.output || item.error || '无额外输出' }}
                  </div>
                </article>
              </div>
            </template>
          </ResultBoardPanel>
        </CollapsibleSection>
      </div>

      <SourcePathReplacementDialog
        ref="sourcePathReplacementDialogRef"
        :store="store"
        variant="workbench"
      />
      <ImportPersonalRulesDialog
        v-model="importDialogVisible"
        :initial-rule-ids="selectedRuleIds"
        @imported="handleImportFinished"
      />
    </div>
  </div>
</template>
