<script setup lang="ts">
import type { DualCompositeComparison, FixedRuleOperator } from '../../types/fixedRules'
import type { FieldOption } from '../../rules'

const props = defineProps<{
  comparison: DualCompositeComparison
  leftFieldOptions: FieldOption[]
  rightFieldOptions: FieldOption[]
  operatorOptions: Array<{ label: string; value: FixedRuleOperator | 'not_null' }>
}>()

const emit = defineEmits<{
  (event: 'update:comparison', value: DualCompositeComparison): void
}>()

function updateComparison(patch: Partial<DualCompositeComparison>): void {
  emit('update:comparison', { ...props.comparison, ...patch })
}
</script>

<template>
  <div class="grid grid-cols-3 gap-3">
    <el-select
      :model-value="comparison.left_field"
      filterable
      placeholder="左侧字段"
      @update:model-value="updateComparison({ left_field: String($event ?? '') })"
    >
      <el-option
        v-for="field in leftFieldOptions"
        :key="field.value"
        :label="field.label"
        :value="field.value"
      />
    </el-select>
    <el-select
      :model-value="comparison.operator"
      placeholder="比较"
      @update:model-value="updateComparison({ operator: $event as FixedRuleOperator | 'not_null' })"
    >
      <el-option
        v-for="option in operatorOptions"
        :key="option.value"
        :label="option.label"
        :value="option.value"
      />
    </el-select>
    <el-select
      :model-value="comparison.right_field"
      filterable
      placeholder="右侧字段"
      @update:model-value="updateComparison({ right_field: String($event ?? '') })"
    >
      <el-option
        v-for="field in rightFieldOptions"
        :key="field.value"
        :label="field.label"
        :value="field.value"
      />
    </el-select>
  </div>
</template>
