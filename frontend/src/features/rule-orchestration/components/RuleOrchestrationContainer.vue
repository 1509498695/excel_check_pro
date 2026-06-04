<script setup lang="ts">
import { computed } from 'vue'
import { Plus } from '@element-plus/icons-vue'

import RuleCard from '../../../components/rules/RuleCard.vue'
import RuleGroupList from '../../../components/rules/RuleGroupList.vue'
import DataTable from '../../../components/shell/DataTable.vue'
import EmptyState from '../../../components/shell/EmptyState.vue'
import PrimaryButton from '../../../components/shell/PrimaryButton.vue'
import SecondaryButton from '../../../components/shell/SecondaryButton.vue'
import type { FixedRuleDefinition, FixedRuleGroup } from '../../../types/fixedRules'

const props = withDefaults(
  defineProps<{
    groups: FixedRuleGroup[]
    selectedGroupId: string
    selectedGroupName: string
    selectedGroupBuiltin: boolean
    keyword: string
    counts: Record<string, number>
    invalidGroupIds: string[]
    invalidRuleIds: string[]
    selectedRuleIds: string[]
    canCreateRule: boolean
    currentGroupRules: FixedRuleDefinition[]
    pagedRules: FixedRuleDefinition[]
    currentGroupRuleTotal: number
    currentPage: number
    currentGroupCount: number
    currentGroupVariableCount: number
    tableLabel: string
    emptyMode?: 'panel' | 'table'
    showPackageItemsRuleButton?: boolean
    showEventTaskRuleButton?: boolean
    buildRuleCondition: (rule: FixedRuleDefinition) => string
    buildRuleVariableSummary: (rule: FixedRuleDefinition) => string
    buildRuleSourcePathSummary: (rule: FixedRuleDefinition) => string
    buildRuleSelectionSummary: (rule: FixedRuleDefinition) => string
    buildRuleCompareValueSummary: (rule: FixedRuleDefinition) => string
  }>(),
  {
    emptyMode: 'table',
    showPackageItemsRuleButton: false,
    showEventTaskRuleButton: false,
  },
)

const emit = defineEmits<{
  (event: 'update:keyword', value: string): void
  (event: 'select-group', groupId: string): void
  (event: 'create-group'): void
  (event: 'rename-group'): void
  (event: 'remove-group'): void
  (event: 'create-package-items-rule'): void
  (event: 'create-event-task-rule'): void
  (event: 'create-rule'): void
  (event: 'edit-rule', rule: FixedRuleDefinition): void
  (event: 'remove-rule', rule: FixedRuleDefinition): void
  (event: 'toggle-rule', ruleId: string): void
  (event: 'toggle-visible-rules', checked: string | number | boolean): void
  (event: 'page-change', page: number): void
}>()

const invalidGroupIdSet = computed(() => new Set(props.invalidGroupIds))
const invalidRuleIdSet = computed(() => new Set(props.invalidRuleIds))
const selectedRuleIdSet = computed(() => new Set(props.selectedRuleIds))
const visibleRuleIds = computed(() => props.pagedRules.map((rule) => rule.rule_id))
const allVisibleRulesSelected = computed(
  () =>
    visibleRuleIds.value.length > 0 &&
    visibleRuleIds.value.every((ruleId) => selectedRuleIdSet.value.has(ruleId)),
)
const partiallySelectedVisibleRules = computed(() => {
  if (!visibleRuleIds.value.length) {
    return false
  }
  const selectedCount = visibleRuleIds.value.filter((ruleId) =>
    selectedRuleIdSet.value.has(ruleId),
  ).length
  return selectedCount > 0 && selectedCount < visibleRuleIds.value.length
})
</script>

<template>
  <div class="workbench-rule-shell">
    <div class="workbench-rule-layout">
      <aside class="workbench-rule-sidebar">
        <RuleGroupList
          :groups="groups"
          :selected-group-id="selectedGroupId"
          :keyword="keyword"
          :counts="counts"
          :invalid-group-ids="invalidGroupIdSet"
          @update:keyword="emit('update:keyword', $event)"
          @select="emit('select-group', $event)"
          @create="emit('create-group')"
        />
      </aside>

      <div class="workbench-rule-main">
        <div class="workbench-rule-header">
          <div class="min-w-0">
            <div class="truncate text-[14px] font-semibold text-ink-900">
              {{ selectedGroupName }}
            </div>
            <div class="text-[12px] text-ink-500">
              共 {{ currentGroupCount }} 条规则 · {{ currentGroupVariableCount }} 个变量
            </div>
          </div>
          <div class="workbench-rule-header__actions">
            <SecondaryButton
              size="sm"
              :disabled="selectedGroupBuiltin"
              @click="emit('rename-group')"
            >
              重命名
            </SecondaryButton>
            <SecondaryButton
              size="sm"
              :disabled="selectedGroupBuiltin"
              @click="emit('remove-group')"
            >
              删除组
            </SecondaryButton>
            <SecondaryButton
              v-if="showPackageItemsRuleButton"
              size="sm"
              :disabled="!canCreateRule"
              @click="emit('create-package-items-rule')"
            >
              IAP礼包校验
            </SecondaryButton>
            <SecondaryButton
              v-if="showEventTaskRuleButton"
              size="sm"
              :disabled="!canCreateRule"
              @click="emit('create-event-task-rule')"
            >
              节日任务校验
            </SecondaryButton>
            <PrimaryButton
              size="sm"
              :disabled="!canCreateRule"
              data-testid="rule-create-button"
              @click="emit('create-rule')"
            >
              <template #icon><Plus /></template>
              新增规则
            </PrimaryButton>
          </div>
        </div>

        <div v-if="!canCreateRule && emptyMode === 'panel'" class="workbench-rule-empty">
          <EmptyState
            variant="panel"
            icon-tone="rule"
            title="暂无规则"
            description="请先在上方变量池保存变量，随后新建校验规则"
            :min-height="260"
          />
        </div>

        <DataTable v-else :aria-label="tableLabel">
          <template #head>
            <tr>
              <th class="w-[28%]">规则名称</th>
              <th>目标变量</th>
              <th class="w-[20%]">规则选择</th>
              <th class="w-[20%]">操作</th>
              <th class="w-[72px]">
                <el-checkbox
                  :model-value="allVisibleRulesSelected"
                  :indeterminate="partiallySelectedVisibleRules"
                  :disabled="!visibleRuleIds.length"
                  @change="emit('toggle-visible-rules', $event)"
                />
              </th>
            </tr>
          </template>
          <template #body>
            <tr v-if="!canCreateRule || !currentGroupRules.length">
              <td colspan="5" class="bg-card">
                <EmptyState
                  variant="table"
                  icon-tone="rule"
                  title="暂无规则"
                  description="请先在上方变量池保存变量，随后新建校验规则"
                  :min-height="260"
                />
              </td>
            </tr>
            <template v-else>
              <RuleCard
                v-for="row in pagedRules"
                :key="row.rule_id"
                :rule="row"
                :invalid="invalidRuleIdSet.has(row.rule_id)"
                :selected="selectedRuleIdSet.has(row.rule_id)"
                :condition-summary="buildRuleCondition(row)"
                :variable-summary="buildRuleVariableSummary(row)"
                :source-path-summary="buildRuleSourcePathSummary(row)"
                :selection-summary="buildRuleSelectionSummary(row)"
                :compare-value-summary="buildRuleCompareValueSummary(row)"
                @edit="emit('edit-rule', $event)"
                @remove="emit('remove-rule', $event)"
                @toggle="emit('toggle-rule', $event)"
              />
            </template>
          </template>
        </DataTable>

        <div
          v-if="currentGroupRuleTotal > 20"
          class="flex items-center justify-between gap-3 pt-2"
        >
          <span class="text-[12px] text-ink-500">
            第 {{ currentPage }} 页 / 共 {{ currentGroupRuleTotal }} 条
          </span>
          <el-pagination
            layout="prev, pager, next"
            :page-size="20"
            :total="currentGroupRuleTotal"
            :current-page="currentPage"
            @current-change="emit('page-change', $event)"
          />
        </div>

        <slot name="footer" />
      </div>
    </div>
  </div>
</template>
