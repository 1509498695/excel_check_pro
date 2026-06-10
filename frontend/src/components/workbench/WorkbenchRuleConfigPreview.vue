<script setup lang="ts">
import { computed } from 'vue'

import type {
  CompositeCondition,
  FixedRuleDefinition,
  FixedRuleGroup,
  MultiCompositeMappingFilter,
} from '../../types/fixedRules'
import type { DataSource, VariableTag } from '../../types/workbench'
import {
  buildDisplayFieldOptions,
  buildRuleCompareValueSummary,
  buildRuleCondition,
  buildRuleSelectionSummary,
  buildRuleSourcePathSummary,
  buildRuleVariableSummary,
  createEditWorkbenchRuleDialogState,
  getCompositeFieldLabel,
  getDualCompositeKeyCheckModeLabel,
  getDualCompositeOperatorLabel,
  getRuleSelectionLabel,
  getRuleSelectionValue,
  getSequenceDirectionLabel,
  getSourcePath,
  getVariableColumnSummary,
  summarizeCondition,
  type WorkbenchRuleEntryType,
} from '../../utils/workbenchRuleForm'

const props = defineProps<{
  rule: FixedRuleDefinition
  variables: VariableTag[]
  sources: DataSource[]
  groups: FixedRuleGroup[]
}>()

const variableMap = computed(() => new Map(props.variables.map((variable) => [variable.tag, variable])))
const sourceMap = computed(() => new Map(props.sources.map((source) => [source.id, source])))
const compositeVariables = computed(() =>
  props.variables.filter((variable) => (variable.variable_kind ?? 'single') === 'composite'),
)
const formSnapshot = computed(() => createEditWorkbenchRuleDialogState(props.rule, compositeVariables.value))
const form = computed(() => formSnapshot.value.form)
const targetVariable = computed(() => variableMap.value.get(props.rule.target_variable_tag) ?? null)
const referenceVariable = computed(() =>
  variableMap.value.get(props.rule.reference_variable_tag?.trim() ?? '') ?? null,
)
const referenceSource = computed(() =>
  referenceVariable.value ? sourceMap.value.get(referenceVariable.value.source_id) ?? null : null,
)
const groupLabel = computed(
  () =>
    props.groups.find((group) => group.group_id === props.rule.group_id)?.group_name ??
    (props.rule.group_id || '未分组'),
)
const ruleEntryTypeLabel = computed(() => getRuleEntryTypeLabel(form.value.rule_entry_type))
const ruleSelectionLabel = computed(() => buildRuleSelectionSummary(props.rule))
const displayFieldLabel = computed(() => {
  const value = props.rule.display_field?.trim()
  if (!value) return '默认不显示'
  const options = buildDisplayFieldOptions(targetVariable.value)
  return options.find((option) => option.value === value)?.label ?? value
})
const ruleSummary = computed(() => buildRuleCondition(props.rule, variableMap.value))
const valueSummary = computed(() => buildRuleCompareValueSummary(props.rule, variableMap.value))
const variableSummary = computed(() => buildRuleVariableSummary(props.rule, variableMap.value))
const sourceSummary = computed(() => buildRuleSourcePathSummary(props.rule, variableMap.value, sourceMap.value))

function getRuleEntryTypeLabel(value: WorkbenchRuleEntryType): string {
  const labels: Record<WorkbenchRuleEntryType, string> = {
    single: '单一变量校验',
    composite: '组合分支校验',
    dual_composite: '跨组变量校验',
    multi_composite_pipeline: '多组串行校验',
    multi_composite_mapping: '多组映射校验',
  }
  return labels[value] ?? value
}

function formatVariable(variable: VariableTag | null): string {
  if (!variable) return '未绑定变量'
  return variable.tag
}

function formatVariableMeta(variable: VariableTag | null): string {
  if (!variable) return ''
  return `${variable.source_id} / ${variable.sheet} / ${getVariableColumnSummary(variable)}`
}

function formatSource(source: DataSource | null): string {
  if (!source) return '未记录数据源'
  return getSourcePath(source) || source.id
}

function formatCondition(condition: CompositeCondition, variable: VariableTag | null): string {
  return summarizeCondition(condition, variable)
}

function formatConditionList(conditions: CompositeCondition[], variable: VariableTag | null): string[] {
  return conditions.map((condition) => formatCondition(condition, variable))
}

function formatField(field: string | undefined, variable: VariableTag | null): string {
  const normalized = field?.trim() ?? ''
  return normalized ? getCompositeFieldLabel(normalized, variable) : '未配置'
}

function formatSingleRuleParameter(): Array<{ label: string; value: string }> {
  const rule = props.rule
  if (rule.rule_type === 'fixed_value_compare') {
    return [
      { label: '规则选择', value: getRuleSelectionLabel(getRuleSelectionValue(rule)) },
      { label: '比较值类型', value: rule.expected_value_mode === 'set' ? '集合值' : '单值' },
      { label: '比较值', value: rule.expected_value || '未配置' },
    ]
  }
  if (rule.rule_type === 'regex_check') {
    return [
      { label: '规则选择', value: '正则校验' },
      { label: '正则表达式', value: rule.expected_value || '未配置' },
    ]
  }
  if (rule.rule_type === 'cross_table_mapping') {
    return [
      { label: '规则选择', value: '包含于基础字典' },
      { label: '基础字典变量', value: formatVariable(referenceVariable.value) },
      { label: '基础字典来源', value: formatSource(referenceSource.value) },
    ]
  }
  if (rule.rule_type === 'sequence_order_check') {
    return [
      { label: '规则选择', value: '顺序校验' },
      { label: '顺序方向', value: getSequenceDirectionLabel(rule.sequence_direction) },
      { label: '步长', value: rule.sequence_step || '1' },
      {
        label: '起始值',
        value:
          rule.sequence_start_mode === 'manual'
            ? rule.sequence_start_value || '未配置'
            : '自动取首行',
      },
    ]
  }
  if (rule.rule_type === 'not_null') {
    return [{ label: '规则选择', value: '非空校验' }]
  }
  if (rule.rule_type === 'unique') {
    return [{ label: '规则选择', value: '唯一校验' }]
  }
  return [{ label: '规则参数', value: valueSummary.value || '—' }]
}

function getMappingFilterRanges(condition: MultiCompositeMappingFilter): string {
  const ranges = condition.exclusion_ranges ?? []
  if (!ranges.length) return '未配置排除范围'
  return ranges
    .map((range) => `${range.start_row}-${range.end_row}${range.expected_value ? `：${range.expected_value}` : ''}`)
    .join('；')
}
</script>

<template>
  <div class="rule-config-preview">
    <section class="rule-config-preview__section">
      <div class="rule-config-preview__section-head">
        <div>
          <h3>基本信息</h3>
          <p>规则归属、命名与目标变量</p>
        </div>
      </div>
      <div class="rule-config-preview__grid">
        <div class="rule-config-preview__field">
          <span>规则组</span>
          <strong>{{ groupLabel }}</strong>
        </div>
        <div class="rule-config-preview__field">
          <span>规则名称</span>
          <strong>{{ rule.rule_name || rule.rule_id }}</strong>
        </div>
        <div class="rule-config-preview__field">
          <span>规则类型</span>
          <strong>{{ ruleEntryTypeLabel }}</strong>
        </div>
        <div class="rule-config-preview__field">
          <span>规则选择</span>
          <strong>{{ ruleSelectionLabel }}</strong>
        </div>
        <div class="rule-config-preview__field rule-config-preview__field--wide">
          <span>目标变量</span>
          <strong>{{ formatVariable(targetVariable) }}</strong>
          <em v-if="targetVariable">{{ formatVariableMeta(targetVariable) }}</em>
        </div>
        <div class="rule-config-preview__field rule-config-preview__field--wide">
          <span>数据源</span>
          <strong>{{ sourceSummary }}</strong>
        </div>
        <div class="rule-config-preview__field rule-config-preview__field--wide">
          <span>结果显示字段</span>
          <strong>{{ displayFieldLabel }}</strong>
        </div>
      </div>
    </section>

    <section v-if="form.rule_entry_type === 'single'" class="rule-config-preview__section">
      <div class="rule-config-preview__section-head">
        <div>
          <h3>校验配置</h3>
          <p>单一变量规则参数</p>
        </div>
      </div>
      <div class="rule-config-preview__grid">
        <div
          v-for="item in formatSingleRuleParameter()"
          :key="item.label"
          class="rule-config-preview__field"
        >
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
        <div class="rule-config-preview__field rule-config-preview__field--wide">
          <span>变量摘要</span>
          <strong>{{ variableSummary }}</strong>
        </div>
      </div>
    </section>

    <section v-else-if="rule.rule_type === 'dual_composite_compare'" class="rule-config-preview__section">
      <div class="rule-config-preview__section-head">
        <div>
          <h3>跨组变量校验</h3>
          <p>按 Key 对齐后比较字段值</p>
        </div>
        <span class="rule-config-preview__pill">组合变量已激活</span>
      </div>

      <div class="rule-config-preview__panel">
        <div class="rule-config-preview__grid">
          <div class="rule-config-preview__field">
            <span>基准变量</span>
            <strong>{{ formatVariable(targetVariable) }}</strong>
            <em v-if="targetVariable">{{ formatVariableMeta(targetVariable) }}</em>
          </div>
          <div class="rule-config-preview__field">
            <span>目标变量（变量 2）</span>
            <strong>{{ formatVariable(referenceVariable) }}</strong>
            <em v-if="referenceVariable">{{ formatVariableMeta(referenceVariable) }}</em>
          </div>
          <div class="rule-config-preview__field">
            <span>Key 校验方式</span>
            <strong>{{ getDualCompositeKeyCheckModeLabel(rule.key_check_mode) }}</strong>
          </div>
          <div class="rule-config-preview__field">
            <span>左侧关联 Key 字段</span>
            <strong>{{ formatField(form.left_key_field, targetVariable) }}</strong>
          </div>
          <div class="rule-config-preview__field">
            <span>右侧关联 Key 字段</span>
            <strong>{{ formatField(form.right_key_field, referenceVariable) }}</strong>
          </div>
        </div>
      </div>

      <div class="rule-config-preview__two-columns">
        <div class="rule-config-preview__panel">
          <h4>左侧筛选条件</h4>
          <ul v-if="rule.left_filters?.length">
            <li
              v-for="(condition, index) in formatConditionList(rule.left_filters, targetVariable)"
              :key="`left-${index}`"
            >
              {{ condition }}
            </li>
          </ul>
          <p v-else>未配置左侧筛选</p>
        </div>
        <div class="rule-config-preview__panel">
          <h4>右侧筛选条件</h4>
          <ul v-if="rule.right_filters?.length">
            <li
              v-for="(condition, index) in formatConditionList(rule.right_filters, referenceVariable)"
              :key="`right-${index}`"
            >
              {{ condition }}
            </li>
          </ul>
          <p v-else>未配置右侧筛选</p>
        </div>
      </div>

      <div class="rule-config-preview__panel">
        <h4>字段比对规则</h4>
        <div v-if="rule.comparisons?.length" class="rule-config-preview__comparison-list">
          <div
            v-for="(comparison, index) in rule.comparisons"
            :key="comparison.comparison_id || index"
            class="rule-config-preview__comparison"
          >
            <span>字段比较 {{ index + 1 }}</span>
            <strong>
              {{ formatField(comparison.left_field, targetVariable) }}
              {{ getDualCompositeOperatorLabel(comparison.operator) }}
              {{ formatField(comparison.right_field, referenceVariable) }}
            </strong>
          </div>
        </div>
        <p v-else>暂无字段比对规则</p>
      </div>
    </section>

    <section v-else-if="rule.rule_type === 'composite_condition_check'" class="rule-config-preview__section">
      <div class="rule-config-preview__section-head">
        <div>
          <h3>组合条件规则</h3>
          <p>全局筛选、分支筛选与分支判定</p>
        </div>
        <span class="rule-config-preview__pill">组合变量已激活</span>
      </div>
      <div class="rule-config-preview__panel">
        <h4>全局筛选</h4>
        <ul v-if="rule.composite_config?.global_filters.length">
          <li
            v-for="(condition, index) in formatConditionList(rule.composite_config.global_filters, targetVariable)"
            :key="`global-${index}`"
          >
            {{ condition }}
          </li>
        </ul>
        <p v-else>未配置全局筛选</p>
      </div>
      <div
        v-for="(branch, branchIndex) in rule.composite_config?.branches ?? []"
        :key="branch.branch_id || branchIndex"
        class="rule-config-preview__panel"
      >
        <h4>分支 {{ branchIndex + 1 }}</h4>
        <div class="rule-config-preview__two-columns">
          <div>
            <span class="rule-config-preview__sub-title">筛选条件</span>
            <ul v-if="branch.filters.length">
              <li
                v-for="(condition, index) in formatConditionList(branch.filters, targetVariable)"
                :key="`branch-filter-${branchIndex}-${index}`"
              >
                {{ condition }}
              </li>
            </ul>
            <p v-else>命中全部</p>
          </div>
          <div>
            <span class="rule-config-preview__sub-title">判定条件</span>
            <ul v-if="branch.assertions.length">
              <li
                v-for="(condition, index) in formatConditionList(branch.assertions, targetVariable)"
                :key="`branch-assertion-${branchIndex}-${index}`"
              >
                {{ condition }}
              </li>
            </ul>
            <p v-else>未配置判定</p>
          </div>
        </div>
      </div>
    </section>

    <section v-else-if="rule.rule_type === 'multi_composite_pipeline_check'" class="rule-config-preview__section">
      <div class="rule-config-preview__section-head">
        <div>
          <h3>多组串行校验</h3>
          <p>按节点顺序执行，失败后中断后续节点</p>
        </div>
      </div>
      <div
        v-for="(node, nodeIndex) in rule.pipeline_config?.nodes ?? []"
        :key="node.node_id || nodeIndex"
        class="rule-config-preview__panel"
      >
        <h4>节点 {{ nodeIndex + 1 }}</h4>
        <div class="rule-config-preview__field rule-config-preview__field--block">
          <span>组合变量</span>
          <strong>{{ formatVariable(variableMap.get(node.variable_tag) ?? null) }}</strong>
          <em v-if="variableMap.get(node.variable_tag)">
            {{ formatVariableMeta(variableMap.get(node.variable_tag) ?? null) }}
          </em>
        </div>
        <div class="rule-config-preview__two-columns">
          <div>
            <span class="rule-config-preview__sub-title">前置过滤条件</span>
            <ul v-if="node.filters.length">
              <li
                v-for="(condition, index) in formatConditionList(node.filters, variableMap.get(node.variable_tag) ?? null)"
                :key="`pipeline-filter-${nodeIndex}-${index}`"
              >
                {{ condition }}
              </li>
            </ul>
            <p v-else>命中全部</p>
          </div>
          <div>
            <span class="rule-config-preview__sub-title">最终判定条件</span>
            <ul v-if="node.assertions.length">
              <li
                v-for="(condition, index) in formatConditionList(node.assertions, variableMap.get(node.variable_tag) ?? null)"
                :key="`pipeline-assertion-${nodeIndex}-${index}`"
              >
                {{ condition }}
              </li>
            </ul>
            <p v-else>未配置判定</p>
          </div>
        </div>
      </div>
    </section>

    <section v-else-if="rule.rule_type === 'multi_composite_mapping_check'" class="rule-config-preview__section">
      <div class="rule-config-preview__section-head">
        <div>
          <h3>多组映射校验</h3>
          <p>按节点筛选和排除范围进行映射检查</p>
        </div>
      </div>
      <div
        v-for="(node, nodeIndex) in rule.mapping_config?.nodes ?? []"
        :key="node.node_id || nodeIndex"
        class="rule-config-preview__panel"
      >
        <h4>映射节点 {{ nodeIndex + 1 }}</h4>
        <div class="rule-config-preview__field rule-config-preview__field--block">
          <span>组合变量</span>
          <strong>{{ formatVariable(variableMap.get(node.variable_tag) ?? null) }}</strong>
          <em v-if="variableMap.get(node.variable_tag)">
            {{ formatVariableMeta(variableMap.get(node.variable_tag) ?? null) }}
          </em>
        </div>
        <div v-if="node.filters.length" class="rule-config-preview__comparison-list">
          <div
            v-for="(condition, index) in node.filters"
            :key="condition.condition_id || index"
            class="rule-config-preview__comparison"
          >
            <span>筛选 {{ index + 1 }}</span>
            <strong>
              {{ formatCondition(condition, variableMap.get(node.variable_tag) ?? null) }}
              ｜排除范围：{{ getMappingFilterRanges(condition) }}
            </strong>
          </div>
        </div>
        <p v-else>未配置映射筛选</p>
      </div>
    </section>

    <section class="rule-config-preview__section">
      <div class="rule-config-preview__section-head">
        <div>
          <h3>规则摘要</h3>
          <p>用于快速核对规则配置是否符合预期</p>
        </div>
      </div>
      <div class="rule-config-preview__summary-text">{{ ruleSummary || '暂无摘要' }}</div>
    </section>
  </div>
</template>

<style scoped>
.rule-config-preview {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.rule-config-preview__section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rule-config-preview__section-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--ec-line, #e5e7eb);
  padding-bottom: 8px;
}

.rule-config-preview__section-head h3 {
  margin: 0;
  color: var(--ec-ink-900, #0f172a);
  font-size: 14px;
  font-weight: 600;
}

.rule-config-preview__section-head p {
  margin: 2px 0 0;
  color: var(--ec-ink-500, #64748b);
  font-size: 12px;
}

.rule-config-preview__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.rule-config-preview__field {
  min-width: 0;
  border: 1px solid var(--ec-line, #e5e7eb);
  border-radius: 8px;
  background: var(--ec-card, #ffffff);
  padding: 10px 12px;
}

.rule-config-preview__field--wide,
.rule-config-preview__field--block {
  grid-column: 1 / -1;
}

.rule-config-preview__field span,
.rule-config-preview__comparison span,
.rule-config-preview__sub-title {
  display: block;
  color: var(--ec-ink-500, #64748b);
  font-size: 12px;
  line-height: 1.5;
}

.rule-config-preview__field strong,
.rule-config-preview__comparison strong {
  display: block;
  margin-top: 4px;
  overflow-wrap: anywhere;
  color: var(--ec-ink-900, #0f172a);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.55;
}

.rule-config-preview__field em {
  display: block;
  margin-top: 4px;
  overflow-wrap: anywhere;
  color: var(--ec-ink-500, #64748b);
  font-size: 12px;
  font-style: normal;
  font-weight: 400;
  line-height: 1.5;
}

.rule-config-preview__panel {
  border-radius: 8px;
  background: var(--ec-subtle, #f8fafc);
  padding: 14px;
}

.rule-config-preview__panel h4 {
  margin: 0 0 10px;
  color: var(--ec-ink-900, #0f172a);
  font-size: 13px;
  font-weight: 600;
}

.rule-config-preview__panel p,
.rule-config-preview__panel li {
  color: var(--ec-ink-600, #475569);
  font-size: 12px;
  line-height: 1.7;
}

.rule-config-preview__panel p {
  margin: 0;
}

.rule-config-preview__panel ul {
  margin: 0;
  padding-left: 18px;
}

.rule-config-preview__two-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.rule-config-preview__pill {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  background: #eff6ff;
  color: #2563eb;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 600;
}

.rule-config-preview__comparison-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rule-config-preview__comparison {
  border: 1px solid var(--ec-line, #e5e7eb);
  border-radius: 8px;
  background: var(--ec-card, #ffffff);
  padding: 10px 12px;
}

.rule-config-preview__summary-text {
  border-radius: 8px;
  background: var(--ec-subtle, #f8fafc);
  color: var(--ec-ink-700, #334155);
  font-size: 13px;
  line-height: 1.7;
  overflow-wrap: anywhere;
  padding: 12px 14px;
}

@media (max-width: 720px) {
  .rule-config-preview__grid,
  .rule-config-preview__two-columns {
    grid-template-columns: 1fr;
  }
}
</style>
