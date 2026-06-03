<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowDown, ArrowUp } from '@element-plus/icons-vue'

import type { DataSource, VariableTag } from '../../types/workbench'
import type { SmartRuleWorkflowHintsState } from '../../utils/aiRuleInputDraft'
import { getSourceTypeLabel } from '../../utils/workbenchMeta'

const props = defineProps<{
  hints: SmartRuleWorkflowHintsState
  sources: DataSource[]
  variables: VariableTag[]
  selectedVariableTags: string[]
}>()

const emit = defineEmits<{
  (e: 'update-hint', key: keyof SmartRuleWorkflowHintsState, value: string): void
  (e: 'update-selected-variable-tags', value: string[]): void
}>()

const expanded = ref(true)
const advancedExpanded = ref(false)

const ruleTypeOptions = [
  { label: '非空校验', value: 'not_null' },
  { label: '唯一校验', value: 'unique' },
  { label: '固定值比较', value: 'fixed_value_compare' },
  { label: '正则校验', value: 'regex_check' },
  { label: '顺序校验', value: 'sequence_order_check' },
  { label: '包含(in)', value: 'cross_table_mapping' },
  { label: '组合分支校验', value: 'composite_condition_check' },
  { label: '跨组变量校验', value: 'dual_composite_compare' },
  { label: '多组串行校验', value: 'multi_composite_pipeline_check' },
  { label: '多组映射校验', value: 'multi_composite_mapping_check' },
  { label: 'IAP礼包校验', value: 'package_items_compare' },
]

const sourceOptions = computed(() =>
  props.sources.map((source) => ({
    label: `${source.id}（${getSourceTypeLabel(source.type)}）`,
    value: source.id,
  })),
)

const variableOptions = computed(() =>
  props.variables.map((variable) => ({
    label: buildVariableLabel(variable),
    value: variable.tag,
    variable,
  })),
)

const targetVariableOptions = computed(() =>
  variableOptions.value.filter((item) => isVariableCompatibleWithRule(item.variable, props.hints.ruleTypeHint)),
)

const singleVariableOptions = computed(() =>
  variableOptions.value.filter((item) => (item.variable.variable_kind ?? 'single') === 'single'),
)

const compositeVariableOptions = computed(() =>
  variableOptions.value.filter((item) => (item.variable.variable_kind ?? 'single') === 'composite'),
)

function updateHint(key: keyof SmartRuleWorkflowHintsState, value: string): void {
  emit('update-hint', key, value)
}

function updateSelectedVariableTags(value: string[]): void {
  emit(
    'update-selected-variable-tags',
    Array.from(new Set(value.map((item) => item.trim()).filter(Boolean))),
  )
}

function updateRoleVariable(key: keyof SmartRuleWorkflowHintsState, value: string): void {
  updateHint(key, value)
  const merged = new Set(props.selectedVariableTags)
  if (value) merged.add(value)
  updateSelectedVariableTags(Array.from(merged))
  const variable = props.variables.find((item) => item.tag === value)
  if (!variable) return
  updateHint('sourceId', variable.source_id)
  updateHint('sheet', variable.sheet)
  if ((variable.variable_kind ?? 'single') === 'composite') {
    updateHint('keyColumn', variable.key_column ?? '')
    updateHint('compositeColumns', (variable.columns ?? []).join(','))
  } else {
    updateHint('targetField', variable.column ?? '')
  }
}

function buildVariableLabel(variable: VariableTag): string {
  const kind = (variable.variable_kind ?? 'single') === 'composite' ? '组合' : '单列'
  const field =
    (variable.variable_kind ?? 'single') === 'composite'
      ? `${variable.key_column ?? '-'} / ${(variable.columns ?? []).join(',')}`
      : variable.column ?? '-'
  return `${variable.tag}（${kind} ${variable.sheet} / ${field}）`
}

function isVariableCompatibleWithRule(variable: VariableTag, ruleType: string): boolean {
  const kind = variable.variable_kind ?? 'single'
  if (
    [
      'composite_condition_check',
      'dual_composite_compare',
      'multi_composite_pipeline_check',
      'multi_composite_mapping_check',
      'package_items_compare',
    ].includes(ruleType)
  ) {
    return kind === 'composite'
  }
  if (
    ['not_null', 'unique', 'fixed_value_compare', 'regex_check', 'sequence_order_check', 'cross_table_mapping'].includes(
      ruleType,
    )
  ) {
    return kind === 'single'
  }
  return true
}
</script>

<template>
  <div class="smart-rule-hints">
    <button type="button" class="smart-rule-hints__toggle" @click="expanded = !expanded">
      <span>{{ expanded ? '收起' : '补充' }} Sheet / 列 / 变量线索</span>
      <component :is="expanded ? ArrowUp : ArrowDown" class="h-4 w-4" />
    </button>

      <div v-if="expanded" class="smart-rule-hints__body">
        <div class="smart-rule-hints__grid smart-rule-hints__grid--primary">
          <label class="smart-rule-field">
          <span>规则类型</span>
          <el-select
            :model-value="hints.ruleTypeHint"
            clearable
            filterable
            placeholder="请选择规则类型"
            @update:model-value="(value: string) => updateHint('ruleTypeHint', value ?? '')"
          >
            <el-option
              v-for="item in ruleTypeOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </label>
        <label class="smart-rule-field smart-rule-field--wide">
          <span>已选变量池变量</span>
          <el-select
            :model-value="selectedVariableTags"
            multiple
            collapse-tags
            collapse-tags-tooltip
            filterable
            placeholder="选择本次 AI 可使用的变量"
            @update:model-value="(value: string[]) => updateSelectedVariableTags(value)"
          >
            <el-option
              v-for="item in variableOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </label>
        <label class="smart-rule-field">
          <span>目标变量</span>
          <el-select
            :model-value="hints.targetVariableTag"
            clearable
            filterable
            placeholder="目标变量"
            @update:model-value="(value: string) => updateRoleVariable('targetVariableTag', value ?? '')"
          >
            <el-option
              v-for="item in targetVariableOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </label>
        <label class="smart-rule-field">
          <span>目标数据源</span>
          <el-select
            :model-value="hints.sourceId"
            clearable
            filterable
            placeholder="请选择数据源"
            @update:model-value="(value: string) => updateHint('sourceId', value ?? '')"
          >
            <el-option
              v-for="source in sourceOptions"
              :key="source.value"
              :label="source.label"
              :value="source.value"
            />
          </el-select>
        </label>
        <label class="smart-rule-field">
          <span>目标 Sheet</span>
          <el-input
            :model-value="hints.sheet"
            placeholder="如：Quest"
            @update:model-value="(value: string) => updateHint('sheet', value)"
          />
        </label>
        <label class="smart-rule-field">
          <span>目标列名</span>
          <el-input
            :model-value="hints.targetField"
            placeholder="如：STR_ABSwitch"
            @update:model-value="(value: string) => updateHint('targetField', value)"
          />
        </label>
        <label class="smart-rule-field">
          <span>规则组</span>
          <el-input
            :model-value="hints.ruleGroupName"
            placeholder="AI生成规则组"
            @update:model-value="(value: string) => updateHint('ruleGroupName', value)"
          />
        </label>
        <label
          v-if="hints.ruleTypeHint === 'cross_table_mapping'"
          class="smart-rule-field"
        >
          <span>引用变量</span>
          <el-select
            :model-value="hints.referenceVariableTag"
            clearable
            filterable
            placeholder="字典变量"
            @update:model-value="(value: string) => updateRoleVariable('referenceVariableTag', value ?? '')"
          >
            <el-option
              v-for="item in singleVariableOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </label>
        <label
          v-if="hints.ruleTypeHint === 'dual_composite_compare'"
          class="smart-rule-field"
        >
          <span>左侧变量</span>
          <el-select
            :model-value="hints.leftVariableTag"
            clearable
            filterable
            placeholder="基准组合变量"
            @update:model-value="(value: string) => updateRoleVariable('leftVariableTag', value ?? '')"
          >
            <el-option
              v-for="item in compositeVariableOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </label>
        <label
          v-if="hints.ruleTypeHint === 'dual_composite_compare'"
          class="smart-rule-field"
        >
          <span>右侧变量</span>
          <el-select
            :model-value="hints.rightVariableTag"
            clearable
            filterable
            placeholder="对比组合变量"
            @update:model-value="(value: string) => updateRoleVariable('rightVariableTag', value ?? '')"
          >
            <el-option
              v-for="item in compositeVariableOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </label>
      </div>

      <button
        type="button"
        class="smart-rule-hints__advanced-toggle"
        @click="advancedExpanded = !advancedExpanded"
      >
        <span>{{ advancedExpanded ? '收起更多线索' : '更多线索' }}</span>
        <component :is="advancedExpanded ? ArrowUp : ArrowDown" class="h-4 w-4" />
      </button>

      <div v-if="advancedExpanded" class="smart-rule-hints__grid">
        <label class="smart-rule-field smart-rule-field--wide">
          <span>配置表链接</span>
          <el-input
            :model-value="hints.sourceUrl"
            placeholder="SVN 或本地 Excel 路径"
            @update:model-value="(value: string) => updateHint('sourceUrl', value)"
          />
        </label>
        <label class="smart-rule-field smart-rule-field--wide">
          <span>推荐正则</span>
          <el-input
            :model-value="hints.regexPattern"
            placeholder="可选，帮助模型生成 regex_check 或组合分支正则"
            @update:model-value="(value: string) => updateHint('regexPattern', value)"
          />
        </label>
        <label class="smart-rule-field">
          <span>过滤字段</span>
          <el-input
            :model-value="hints.filterField"
            placeholder="如：DES"
            @update:model-value="(value: string) => updateHint('filterField', value)"
          />
        </label>
        <label class="smart-rule-field">
          <span>过滤值</span>
          <el-input
            :model-value="hints.filterValue"
            placeholder="如：废弃"
            @update:model-value="(value: string) => updateHint('filterValue', value)"
          />
        </label>
        <label class="smart-rule-field">
          <span>断言字段</span>
          <el-input
            :model-value="hints.assertionField"
            placeholder="如：STR_ABSwitch"
            @update:model-value="(value: string) => updateHint('assertionField', value)"
          />
        </label>
        <label class="smart-rule-field">
          <span>断言值</span>
          <el-input
            :model-value="hints.assertionValue"
            placeholder="如：GreenServer:0,SLG2:0"
            @update:model-value="
              (value: string) => {
                updateHint('assertionValue', value)
                updateHint('assertionOperator', value.trim() ? 'eq' : '')
              }
            "
          />
        </label>
        <label class="smart-rule-field">
          <span>比较值 / 期望值</span>
          <el-input
            :model-value="hints.expectedValue"
            placeholder="如：0 / 1 / 0,1,2"
            @update:model-value="(value: string) => updateHint('expectedValue', value)"
          />
        </label>
        <label class="smart-rule-field">
          <span>结果显示字段</span>
          <el-input
            :model-value="hints.displayField"
            placeholder="如：STR_Func"
            @update:model-value="(value: string) => updateHint('displayField', value)"
          />
        </label>
        <label class="smart-rule-field">
          <span>组合变量 Key 列</span>
          <el-input
            :model-value="hints.keyColumn"
            placeholder="如：INT_Id"
            @update:model-value="(value: string) => updateHint('keyColumn', value)"
          />
        </label>
        <label class="smart-rule-field smart-rule-field--wide">
          <span>组合变量列</span>
          <el-input
            :model-value="hints.compositeColumns"
            placeholder="英文逗号分隔，如 INT_Id,STR_Func,STR_ServersParam,DES"
            @update:model-value="(value: string) => updateHint('compositeColumns', value)"
          />
        </label>
        <label class="smart-rule-field">
          <span>左侧筛选</span>
          <el-input
            :model-value="
              hints.leftFilterField && hints.leftFilterValue
                ? `${hints.leftFilterField}=${hints.leftFilterValue}`
                : ''
            "
            placeholder="如：INT_Index=1011"
            @update:model-value="
              (value: string) => {
                const [field = '', expected = ''] = value.split('=')
                updateHint('leftFilterField', field.trim())
                updateHint('leftFilterValue', expected.trim())
                updateHint('leftFilterOperator', expected.trim() ? 'eq' : '')
              }
            "
          />
        </label>
        <label class="smart-rule-field">
          <span>右侧筛选</span>
          <el-input
            :model-value="
              hints.rightFilterField && hints.rightFilterValue
                ? `${hints.rightFilterField}=${hints.rightFilterValue}`
                : ''
            "
            placeholder="如：INT_Index=1010"
            @update:model-value="
              (value: string) => {
                const [field = '', expected = ''] = value.split('=')
                updateHint('rightFilterField', field.trim())
                updateHint('rightFilterValue', expected.trim())
                updateHint('rightFilterOperator', expected.trim() ? 'eq' : '')
              }
            "
          />
        </label>
        <label class="smart-rule-field">
          <span>左右 Key 字段</span>
          <el-input
            :model-value="hints.leftKeyField || hints.rightKeyField"
            placeholder="如：INT_Level"
            @update:model-value="
              (value: string) => {
                updateHint('leftKeyField', value)
                updateHint('rightKeyField', value)
              }
            "
          />
        </label>
        <label class="smart-rule-field smart-rule-field--wide">
          <span>跨组比较字段</span>
          <el-input
            :model-value="hints.compareFields"
            placeholder="英文逗号分隔，如 INT_A,INT_B"
            @update:model-value="(value: string) => updateHint('compareFields', value)"
          />
        </label>
      </div>
    </div>
  </div>
</template>
