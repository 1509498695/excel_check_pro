<script setup lang="ts">
import { computed, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { usePersonalRulesImport } from '../usePersonalRulesImport'
import ImportConfirmStep from './ImportConfirmStep.vue'
import ImportScopeStep from './ImportScopeStep.vue'

const modelValue = defineModel<boolean>({ default: false })
const props = withDefaults(
  defineProps<{
    initialRuleIds?: string[]
    initialGroupIds?: string[]
  }>(),
  {
    initialRuleIds: () => [],
    initialGroupIds: () => [],
  },
)

const emit = defineEmits<{
  (event: 'imported'): void
}>()

const importer = usePersonalRulesImport({
  initialRuleIds: () => props.initialRuleIds,
  initialGroupIds: () => props.initialGroupIds,
  defaultScopeMode: 'groups',
})
const {
  isLoading,
  isPreviewing,
  isCommitting,
  errorMessage,
  draft,
  preview,
  scope,
  sourceMappings,
  duplicateRuleActions,
  isPreviewStale,
  canPreview,
  canCommit,
  nextDisabledReason,
} = importer

const hasInitialScope = computed(() => Boolean(props.initialRuleIds.length || props.initialGroupIds.length))
const isBusy = computed(() => isLoading.value || isPreviewing.value || isCommitting.value)
const titleHint = computed(() =>
  preview.value ? '确认导入摘要' : '选择要导入到项目校验的个人规则范围',
)
const sourceMappingRows = computed(() => {
  if (!draft.value) {
    return []
  }
  return draft.value.source_mappings.map((sourceDraft) => {
    const mapping = sourceMappings.value.find(
      (item) => item.personal_source_id === sourceDraft.personal_source.id,
    )
    return {
      personalSourceId: sourceDraft.personal_source.id,
      type: sourceDraft.personal_source.type,
      reason: sourceDraft.reason,
      recommendedAction: sourceDraft.recommended_action,
      projectSourceId: sourceDraft.project_source_id,
      requiresConfirmation: sourceDraft.requires_confirmation,
      personalLocator: importer.sourceLocator(sourceDraft.personal_source),
      projectLocator: importer.sourceLocator(sourceDraft.candidates[0]),
      nextLocator: importer.sourceLocator(mapping?.next_source ?? sourceDraft.next_source ?? sourceDraft.personal_source),
    }
  })
})

watch(
  modelValue,
  async (visible) => {
    if (!visible) {
      importer.reset()
      return
    }
    await importer.loadDraft()
    if (hasInitialScope.value) {
      await handlePrepareSummary()
    }
  },
)

async function handlePrepareSummary(): Promise<void> {
  if (!canPreview.value) {
    ElMessage.warning(nextDisabledReason.value || '当前导入范围不可用。')
    return
  }
  await importer.prepareSummary()
}

function handleSourceLocatorInput(personalSourceId: string, value: string): void {
  importer.updateSourceLocator(personalSourceId, value)
}

async function handleCommit(): Promise<void> {
  if (!preview.value) {
    await handlePrepareSummary()
  }
  if (!canCommit.value) {
    ElMessage.warning('导入预览存在阻断问题，请调整范围后重新生成摘要。')
    return
  }
  await importer.commit()
  ElMessage.success('个人校验规则已导入项目校验。')
  modelValue.value = false
  emit('imported')
}
</script>

<template>
  <el-dialog
    v-model="modelValue"
    title="导入个人校验"
    width="min(1180px, calc(100vw - 48px))"
    class="import-personal-rules-dialog"
    data-testid="import-personal-rules-dialog"
    destroy-on-close
    append-to-body
  >
    <div v-loading="isLoading || isPreviewing" class="max-h-[calc(100vh_-_220px)] space-y-5 overflow-y-auto pr-1">
      <div class="rounded-field border border-line bg-subtle p-4">
        <div class="mb-3 text-[14px] font-semibold text-ink-900">{{ titleHint }}</div>
        <ImportScopeStep
          v-if="draft && !preview"
          :mode="scope.mode"
          :group-ids="scope.group_ids"
          :rule-ids="scope.rule_ids"
          :groups="draft.importable_groups"
          :rules="draft.importable_rules"
          @update:mode="scope.mode = $event"
          @update:group-ids="scope.group_ids = $event"
          @update:rule-ids="scope.rule_ids = $event"
        />

        <div v-if="sourceMappingRows.length" class="mt-4 space-y-3">
          <div class="flex items-center justify-between">
            <div class="text-[13px] font-medium text-ink-900">数据源映射</div>
            <div
              v-if="isPreviewStale"
              class="text-[12px] text-warning"
            >
              路径或重复规则处理已变化，正在重新校验或需要重新生成摘要。
            </div>
          </div>
          <div
            v-for="row in sourceMappingRows"
            :key="row.personalSourceId"
            class="rounded-field border border-line bg-card p-3"
          >
            <div class="mb-2 flex items-center justify-between gap-3">
              <div class="min-w-0">
                <div class="truncate text-[13px] font-medium text-ink-900">
                  {{ row.personalSourceId }}
                </div>
                <div class="mt-0.5 text-[12px] text-ink-500">
                  {{ row.reason }}
                </div>
              </div>
              <el-tag
                :type="row.recommendedAction === 'reuse' ? 'success' : row.recommendedAction === 'skip' ? 'info' : 'warning'"
                size="small"
              >
                {{ row.recommendedAction }}
              </el-tag>
            </div>
            <div class="grid grid-cols-1 gap-3 xl:grid-cols-2">
              <div>
                <div class="mb-1 text-[12px] text-ink-500">个人校验路径 / URL</div>
                <div class="min-h-[34px] whitespace-pre-wrap break-all rounded-field bg-subtle px-3 py-2 font-mono text-[12px] leading-5 text-ink-600">
                  {{ row.personalLocator || '—' }}
                </div>
              </div>
              <div>
                <div class="mb-1 text-[12px] text-ink-500">
                  导入项目校验路径 / URL
                </div>
                <el-input
                  :model-value="row.nextLocator"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 5 }"
                  size="small"
                  placeholder="请输入导入项目校验使用的路径或 URL"
                  @input="handleSourceLocatorInput(row.personalSourceId, $event)"
                />
              </div>
            </div>
            <div
              v-if="row.projectSourceId"
              class="mt-2 text-[12px] leading-5 text-ink-500"
            >
              <span>项目候选数据源：{{ row.projectSourceId }}</span>
              <span
                v-if="row.projectLocator"
                class="mt-1 block whitespace-pre-wrap break-all font-mono text-[12px] text-ink-600"
              >
                {{ row.projectLocator }}
              </span>
            </div>
          </div>
        </div>

        <ImportConfirmStep
          v-if="preview"
          class="mt-4"
          :preview="preview"
          :duplicate-rule-actions="duplicateRuleActions"
          @update-duplicate-rule-action="importer.updateDuplicateRuleAction"
        />
      </div>

      <div
        v-if="errorMessage"
        class="rounded-field border border-danger/30 bg-danger-soft/40 p-3 text-[13px] text-ink-700"
      >
        {{ errorMessage }}
      </div>
    </div>

    <template #footer>
      <div class="flex items-center justify-end gap-2">
        <el-button :disabled="isBusy" @click="modelValue = false">取消</el-button>
        <el-button
          v-if="!preview || isPreviewStale"
          data-testid="import-preview-button"
          type="primary"
          :loading="isPreviewing"
          :disabled="isBusy || !canPreview"
          @click="handlePrepareSummary"
        >
          {{ preview ? '重新生成摘要' : '生成导入摘要' }}
        </el-button>
        <el-button
          v-else
          data-testid="import-confirm-button"
          type="primary"
          :loading="isCommitting"
          :disabled="isBusy || !canCommit"
          @click="handleCommit"
        >
          确认导入
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
:global(.import-personal-rules-dialog .el-dialog__body) {
  padding-right: 18px;
}

:global(.import-personal-rules-dialog .el-loading-mask) {
  background: rgba(255, 255, 255, 0.62) !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
}
</style>
