<script setup lang="ts">
import type { FixedRuleDefinition } from '../../types/fixedRules'

defineProps<{
  rule: FixedRuleDefinition
  invalid: boolean
  selected: boolean
  conditionSummary: string
  variableSummary: string
  sourcePathSummary: string
  selectionSummary: string
  compareValueSummary: string
}>()

const emit = defineEmits<{
  (e: 'edit', rule: FixedRuleDefinition): void
  (e: 'remove', rule: FixedRuleDefinition): void
  (e: 'toggle', ruleId: string): void
}>()
</script>

<template>
  <tr class="bg-card text-ink-700">
    <td class="align-top">
      <div
        class="font-medium truncate"
        :class="invalid ? 'text-danger' : 'text-ink-900'"
      >
        {{ rule.rule_name }}
      </div>
      <div class="mt-1 text-[12px] text-ink-500 line-clamp-2">
        {{ conditionSummary }}
      </div>
    </td>
    <td class="align-top">
      <div class="font-mono text-[12px] text-ink-900 truncate">
        {{ rule.target_variable_tag }}
      </div>
      <div class="mt-1 text-[12px] text-ink-500 truncate">
        {{ variableSummary }}
      </div>
      <div class="text-[11px] text-ink-500 truncate">
        {{ sourcePathSummary }}
      </div>
    </td>
    <td class="align-top">
      <div class="text-ink-700">{{ selectionSummary }}</div>
      <div class="mt-1 font-mono text-[12px] text-ink-500">
        {{ compareValueSummary }}
      </div>
    </td>
    <td class="text-left align-top text-[12px]">
      <div class="table-actions">
        <button
          type="button"
          class="ec-action-link workbench-rule-action-link"
          @click="emit('edit', rule)"
        >
          编辑
        </button>
        <button
          type="button"
          class="ec-action-link-danger workbench-rule-action-link"
          @click="emit('remove', rule)"
        >
          删除
        </button>
      </div>
    </td>
    <td class="text-left align-top">
      <el-checkbox
        :model-value="selected"
        :data-testid="`rule-select-${rule.rule_id}`"
        :data-rule-name="rule.rule_name"
        @change="emit('toggle', rule.rule_id)"
        @click.stop
      />
    </td>
  </tr>
</template>
