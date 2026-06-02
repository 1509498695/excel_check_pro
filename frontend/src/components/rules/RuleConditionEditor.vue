<script setup lang="ts">
import type { CompositeCondition } from '../../types/fixedRules'
import type { FieldOption } from '../../rules'

const props = defineProps<{
  condition: CompositeCondition
  fieldOptions: FieldOption[]
  operatorOptions: Array<{ label: string; value: string }>
}>()

const emit = defineEmits<{
  (event: 'update:condition', value: CompositeCondition): void
}>()

function updateCondition(patch: Partial<CompositeCondition>): void {
  emit('update:condition', { ...props.condition, ...patch })
}

function updateOperator(value: unknown): void {
  updateCondition({ operator: String(value ?? '') as CompositeCondition['operator'] })
}
</script>

<template>
  <div class="grid grid-cols-3 gap-3">
    <el-select
      :model-value="condition.field"
      filterable
      placeholder="字段"
      @update:model-value="updateCondition({ field: String($event ?? '') })"
    >
      <el-option
        v-for="field in fieldOptions"
        :key="field.value"
        :label="field.label"
        :value="field.value"
      />
    </el-select>
    <el-select
      :model-value="condition.operator"
      placeholder="条件"
      @update:model-value="updateOperator"
    >
      <el-option
        v-for="option in operatorOptions"
        :key="option.value"
        :label="option.label"
        :value="option.value"
      />
    </el-select>
    <el-input
      :model-value="condition.expected_value"
      placeholder="比较值"
      @update:model-value="updateCondition({ expected_value: String($event ?? '') })"
    />
  </div>
</template>
