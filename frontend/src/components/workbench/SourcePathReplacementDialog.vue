<script setup lang="ts">
import { computed, nextTick, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { listSvnDirectory } from '../../api/svn'
import type { SourcePathReplacementStoreLike } from '../../types/panelStores'
import type { SourcePathReplacementGroup } from '../../utils/sourcePathReplacement'

const props = withDefaults(
  defineProps<{
    store: SourcePathReplacementStoreLike
    variant?: 'workbench' | 'fixed-rules'
  }>(),
  {
    variant: 'workbench',
  },
)

type ManagedInputInstance = {
  focus?: () => void
}

type ManagedPathGroup = Extract<SourcePathReplacementGroup, 'svn'>

type GroupFormState = {
  selectedDirectory: string
  addingDraft: string | null
  editingOriginalPath: string | null
  editingValue: string
  isSavingPreset: boolean
  isApplying: boolean
}

const dialogVisible = ref(false)
const activeGroup = ref<ManagedPathGroup>('svn')
const inputRefs = reactive<Record<string, ManagedInputInstance | null>>({})
const formState = reactive<Record<ManagedPathGroup, GroupFormState>>({
  svn: {
    selectedDirectory: '',
    addingDraft: null,
    editingOriginalPath: null,
    editingValue: '',
    isSavingPreset: false,
    isApplying: false,
  },
})

const copy = computed(() => ({
  title: props.variant === 'fixed-rules' ? '项目校验数据源路径管理' : '个人校验数据源路径管理',
  subtitle:
    '管理远端 SVN 目录 URL。只替换文件名前的目录路径，保留原文件名不变，并在完成后立即刷新当前已接入 SVN 数据源的元数据与变量预览。',
}))

type GroupCopy = {
  chooseTitle: string
  choosePlaceholder: string
  addButtonLabel: string
  addPlaceholder: string
  saveButtonLabel: string
  emptyText: string
  listHint: string
  applyButtonLabel: string
  noCandidateText: string
  successText: (updatedCount: number, failedCount: number) => string
  failureTitle: string
  saveSuccessText: string
  updateSuccessText: string
  removeSuccessText: string
  duplicateText: string
  missingSelectionText: string
  deleteConfirmText: string
  invalidInputText: string
}

const groupCopy: Record<ManagedPathGroup, GroupCopy> = {
  svn: {
    chooseTitle: '当前用于替换的 SVN 目录',
    choosePlaceholder: '从已保存的 SVN 目录 URL 中选择',
    addButtonLabel: '+ 添加新目录',
    addPlaceholder: '输入 SVN 目录 URL，例如 https://samosvn/data/project/samo/GameDatas/datas_qa89/',
    saveButtonLabel: '保存',
    emptyText: '还没有保存 SVN 目录。点击右上角“+ 添加新目录”后，就可以把常用版本目录保存在这里。',
    listHint: '点击列表项即可切换当前替换目录；支持行内编辑与删除。',
    applyButtonLabel: 'SVN 路径替换',
    noCandidateText: '当前没有可替换的远端 SVN 数据源。',
    successText: (updatedCount, failedCount) =>
      failedCount > 0
        ? `已替换 ${updatedCount} 个 SVN 数据源，其中 ${failedCount} 个刷新失败，请检查数据源状态提示。`
        : `已替换并刷新 ${updatedCount} 个 SVN 数据源，请重新执行校验。`,
    failureTitle: 'SVN 路径替换失败',
    saveSuccessText: 'SVN 目录已保存。',
    updateSuccessText: 'SVN 目录已更新。',
    removeSuccessText: 'SVN 目录已删除。',
    duplicateText: '该 SVN 目录已存在，请直接选择或修改为新的目录。',
    missingSelectionText: '请先选择一个 SVN 目录 URL。',
    deleteConfirmText: '确定要删除该保存的 SVN 目录吗？',
    invalidInputText: '请先输入需要保存的 SVN 目录 URL。',
  },
}

function getGroupState(group: ManagedPathGroup): GroupFormState {
  return formState[group]
}

function getPresetList(_group: ManagedPathGroup): string[] {
  return props.store.svnPathReplacementPresets
}

function getSelectedPreset(_group: ManagedPathGroup): string | null {
  return props.store.selectedSvnPathReplacementPreset
}

function syncSelectedDirectory(group: ManagedPathGroup): void {
  getGroupState(group).selectedDirectory = getSelectedPreset(group) ?? ''
}

function resetGroupDrafts(group: ManagedPathGroup): void {
  const state = getGroupState(group)
  state.addingDraft = null
  state.editingOriginalPath = null
  state.editingValue = ''
}

function bindManagedInputRef(key: string, instance: ManagedInputInstance | null): void {
  inputRefs[key] = instance
}

function bindAddInputRef(
  group: ManagedPathGroup,
  instance: ManagedInputInstance | null,
): void {
  bindManagedInputRef(`add:${group}`, instance)
}

function bindEditInputRef(
  group: ManagedPathGroup,
  preset: string,
  instance: ManagedInputInstance | null,
): void {
  bindManagedInputRef(`edit:${group}:${preset}`, instance)
}

function getAddInputRefBinder(
  group: ManagedPathGroup,
): (instance: ManagedInputInstance | null) => void {
  return (instance) => bindAddInputRef(group, instance)
}

function getEditInputRefBinder(
  group: ManagedPathGroup,
  preset: string,
): (instance: ManagedInputInstance | null) => void {
  return (instance) => bindEditInputRef(group, preset, instance)
}

function focusManagedInput(key: string): void {
  nextTick(() => {
    inputRefs[key]?.focus?.()
  })
}

function focusAddInput(group: ManagedPathGroup): void {
  focusManagedInput(`add:${group}`)
}

function focusEditInput(group: ManagedPathGroup, preset: string): void {
  focusManagedInput(`edit:${group}:${preset}`)
}

function openDialog(): void {
  activeGroup.value = 'svn'
  syncSelectedDirectory('svn')
  resetGroupDrafts('svn')
  dialogVisible.value = true
}

async function normalizeDirectoryPath(
  _group: ManagedPathGroup,
  rawDirectoryPath: string,
): Promise<string> {
  const normalizedDirUrl = rawDirectoryPath.trim()
  if (!normalizedDirUrl) {
    throw new Error('SVN 目录 URL 不能为空。')
  }
  const response = await listSvnDirectory(normalizedDirUrl)
  return response.data.dir_url
}

function isDuplicatePreset(
  group: ManagedPathGroup,
  normalizedPath: string,
  excludePath?: string | null,
): boolean {
  const normalizedExclude = excludePath?.trim().toLowerCase() ?? null
  return getPresetList(group).some((preset) => {
    const presetKey = preset.toLowerCase()
    return presetKey === normalizedPath.toLowerCase() && presetKey !== normalizedExclude
  })
}

function handleSelectPreset(group: ManagedPathGroup, preset: string): void {
  getGroupState(group).selectedDirectory = preset
}

function handleStartAdd(group: ManagedPathGroup): void {
  const state = getGroupState(group)
  state.editingOriginalPath = null
  state.editingValue = ''
  state.addingDraft = ''
  focusAddInput(group)
}

function handleCancelAdd(group: ManagedPathGroup): void {
  getGroupState(group).addingDraft = null
}

async function handleSaveNewPreset(group: ManagedPathGroup): Promise<void> {
  const state = getGroupState(group)
  const candidatePath = state.addingDraft?.trim() ?? ''
  if (!candidatePath) {
    ElMessage.warning(groupCopy[group].invalidInputText)
    return
  }

  state.isSavingPreset = true
  try {
    const normalizedPath = await normalizeDirectoryPath(group, candidatePath)
    if (isDuplicatePreset(group, normalizedPath)) {
      ElMessage.warning(groupCopy[group].duplicateText)
      return
    }

    props.store.addPathReplacementPreset(group, normalizedPath)
    props.store.setSelectedPathReplacementPreset(group, normalizedPath)
    await props.store.saveConfigNow()
    state.selectedDirectory = normalizedPath
    state.addingDraft = null
    ElMessage.success(groupCopy[group].saveSuccessText)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '保存目录失败。')
  } finally {
    state.isSavingPreset = false
  }
}

function handleStartEdit(group: ManagedPathGroup, preset: string): void {
  const state = getGroupState(group)
  state.addingDraft = null
  state.editingOriginalPath = preset
  state.editingValue = preset
  focusEditInput(group, preset)
}

function handleCancelEdit(group: ManagedPathGroup): void {
  const state = getGroupState(group)
  state.editingOriginalPath = null
  state.editingValue = ''
}

async function handleSaveEditedPreset(group: ManagedPathGroup): Promise<void> {
  const state = getGroupState(group)
  const originalPath = state.editingOriginalPath
  const candidatePath = state.editingValue.trim()
  if (!originalPath) {
    return
  }
  if (!candidatePath) {
    ElMessage.warning(groupCopy[group].invalidInputText)
    return
  }

  state.isSavingPreset = true
  try {
    const normalizedPath = await normalizeDirectoryPath(group, candidatePath)
    if (isDuplicatePreset(group, normalizedPath, originalPath)) {
      ElMessage.warning(groupCopy[group].duplicateText)
      return
    }

    const wasSelected = state.selectedDirectory.toLowerCase() === originalPath.toLowerCase()
    props.store.updatePathReplacementPreset(group, originalPath, normalizedPath)
    await props.store.saveConfigNow()
    if (wasSelected) {
      state.selectedDirectory = normalizedPath
    }
    state.editingOriginalPath = null
    state.editingValue = ''
    ElMessage.success(groupCopy[group].updateSuccessText)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '更新目录失败。')
  } finally {
    state.isSavingPreset = false
  }
}

async function handleDeletePreset(
  group: ManagedPathGroup,
  preset: string,
): Promise<void> {
  try {
    const state = getGroupState(group)
    const wasSelected = state.selectedDirectory.toLowerCase() === preset.toLowerCase()
    props.store.removePathReplacementPreset(group, preset)
    await props.store.saveConfigNow()
    if (wasSelected) {
      state.selectedDirectory = ''
    }
    if (state.editingOriginalPath === preset) {
      state.editingOriginalPath = null
      state.editingValue = ''
    }
    ElMessage.success(groupCopy[group].removeSuccessText)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '删除目录失败。')
  }
}

async function handleApplyReplacement(group: ManagedPathGroup): Promise<void> {
  const state = getGroupState(group)
  const candidatePath = state.selectedDirectory.trim()
  if (!candidatePath) {
    ElMessage.warning(groupCopy[group].missingSelectionText)
    return
  }

  state.isApplying = true
  try {
    const normalizedPath = await normalizeDirectoryPath(group, candidatePath)
    state.selectedDirectory = normalizedPath
    props.store.setSelectedPathReplacementPreset(group, normalizedPath)
    const result = await props.store.replaceSourceBasePath(group, normalizedPath)

    if (!result.updatedCount) {
      ElMessage.warning(groupCopy[group].noCandidateText)
      return
    }

    ElMessage.success(groupCopy[group].successText(result.updatedCount, result.failedCount))
    dialogVisible.value = false
  } catch (error) {
    const message = error instanceof Error ? error.message : '数据源路径管理失败。'
    await ElMessageBox.alert(message, groupCopy[group].failureTitle, {
      type: 'error',
      confirmButtonText: '知道了',
    })
  } finally {
    state.isApplying = false
  }
}

defineExpose({
  openDialog,
})
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    width="820px"
    :title="copy.title"
    class="source-path-management-dialog"
    destroy-on-close
  >
    <div class="space-y-6">
      <p class="text-[13px] leading-6 text-gray-500">
        {{ copy.subtitle }}
      </p>

      <section class="space-y-3 rounded-lg border border-gray-200 bg-white px-5 py-5">
        <div class="space-y-1">
          <div class="text-[13px] font-semibold text-gray-900">
            {{ groupCopy[activeGroup].chooseTitle }}
          </div>
          <div class="text-[12px] leading-5 text-gray-500">
            选择一个已保存的 SVN 目录 URL，作为当前远端 SVN 数据源的统一替换目标。
          </div>
        </div>
        <el-select
          v-model="formState[activeGroup].selectedDirectory"
          class="w-full"
          :placeholder="groupCopy[activeGroup].choosePlaceholder"
          clearable
          filterable
        >
          <el-option
            v-for="preset in getPresetList(activeGroup)"
            :key="preset"
            :label="preset"
            :value="preset"
          />
        </el-select>
      </section>

      <section class="space-y-4 rounded-lg border border-gray-200 bg-white px-5 py-5">
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="text-[13px] font-semibold text-gray-900">已保存目录列表</div>
            <div class="mt-1 text-[12px] leading-5 text-gray-500">
              {{ groupCopy[activeGroup].listHint }}
            </div>
          </div>
          <div class="flex items-center gap-3">
            <span class="text-[12px] text-gray-500">
              共 {{ getPresetList(activeGroup).length }} 个
            </span>
            <button
              type="button"
              class="ec-btn ec-btn-secondary ec-btn-sm"
              :disabled="formState[activeGroup].isSavingPreset"
              @click="handleStartAdd(activeGroup)"
            >
              {{ groupCopy[activeGroup].addButtonLabel }}
            </button>
          </div>
        </div>

        <div class="rounded-md border border-gray-200 bg-white">
          <div
            v-if="formState[activeGroup].addingDraft !== null"
            class="flex items-center justify-between gap-4 border-b border-gray-100 px-4 py-3"
          >
            <div class="min-w-0 flex-1">
              <el-input
                :ref="getAddInputRefBinder(activeGroup)"
                v-model="formState[activeGroup].addingDraft"
                :placeholder="groupCopy[activeGroup].addPlaceholder"
                clearable
                @keyup.enter="handleSaveNewPreset(activeGroup)"
              />
            </div>
            <div class="flex shrink-0 items-center gap-3">
              <button
                type="button"
                class="ec-btn ec-btn-secondary ec-btn-sm"
                :disabled="formState[activeGroup].isSavingPreset"
                @click="handleSaveNewPreset(activeGroup)"
              >
                {{ groupCopy[activeGroup].saveButtonLabel }}
              </button>
              <button
                type="button"
                class="ec-btn ec-btn-secondary ec-btn-sm"
                :disabled="formState[activeGroup].isSavingPreset"
                @click="handleCancelAdd(activeGroup)"
              >
                取消
              </button>
            </div>
          </div>

          <div
            v-if="getPresetList(activeGroup).length"
            class="max-h-64 divide-y divide-gray-100 overflow-y-auto"
          >
            <div
              v-for="preset in getPresetList(activeGroup)"
              :key="preset"
              class="flex items-center justify-between gap-4 px-4 py-3 transition-colors duration-150 hover:bg-gray-50/50"
            >
              <div class="min-w-0 flex-1">
                <button
                  v-if="formState[activeGroup].editingOriginalPath !== preset"
                  type="button"
                  class="preset-select-button"
                  @click="handleSelectPreset(activeGroup, preset)"
                >
                  <span class="break-all">{{ preset }}</span>
                </button>
                <el-input
                  v-else
                  :ref="getEditInputRefBinder(activeGroup, preset)"
                  v-model="formState[activeGroup].editingValue"
                  @keyup.enter="handleSaveEditedPreset(activeGroup)"
                />
              </div>

              <div class="flex shrink-0 items-center gap-3">
                <span
                  v-if="
                    formState[activeGroup].selectedDirectory === preset &&
                    formState[activeGroup].editingOriginalPath !== preset
                  "
                  class="rounded-full border border-blue-200 px-2.5 py-1 text-[12px] font-medium text-blue-600"
                >
                  当前选择
                </span>

                <template v-if="formState[activeGroup].editingOriginalPath === preset">
                  <button
                    type="button"
                    class="ec-btn ec-btn-secondary ec-btn-sm"
                    :disabled="formState[activeGroup].isSavingPreset"
                    @click="handleSaveEditedPreset(activeGroup)"
                  >
                    保存
                  </button>
                  <button
                    type="button"
                    class="ec-btn ec-btn-secondary ec-btn-sm"
                    :disabled="formState[activeGroup].isSavingPreset"
                    @click="handleCancelEdit(activeGroup)"
                  >
                    取消
                  </button>
                </template>
                <template v-else>
                  <button
                    type="button"
                    class="ec-action-link text-[13px]"
                    @click.stop="handleStartEdit(activeGroup, preset)"
                  >
                    编辑
                  </button>
                  <el-popconfirm
                    width="260"
                    :title="groupCopy[activeGroup].deleteConfirmText"
                    confirm-button-text="删除"
                    cancel-button-text="取消"
                    @confirm="handleDeletePreset(activeGroup, preset)"
                  >
                    <template #reference>
                      <button
                        type="button"
                        class="ec-action-link-danger text-[13px]"
                        @click.stop
                      >
                        删除
                      </button>
                    </template>
                  </el-popconfirm>
                </template>
              </div>
            </div>
          </div>

          <div
            v-else-if="formState[activeGroup].addingDraft === null"
            class="rounded-md border border-dashed border-gray-200 px-4 py-5 text-[13px] leading-6 text-gray-500"
          >
            {{ groupCopy[activeGroup].emptyText }}
          </div>
        </div>
      </section>
    </div>

    <template #footer>
      <div class="flex justify-end gap-3">
        <button
          type="button"
          class="inline-flex min-h-[42px] items-center justify-center rounded-md border border-gray-300 bg-white px-4 text-[14px] font-semibold text-gray-800 transition hover:border-gray-400 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="formState.svn.isApplying || formState.svn.isSavingPreset"
          @click="dialogVisible = false"
        >
          取消
        </button>
        <button
          type="button"
          class="inline-flex min-h-[42px] items-center justify-center rounded-md bg-blue-600 px-4 text-[14px] font-semibold text-white shadow-[0_8px_18px_rgba(37,99,235,0.18)] transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="formState[activeGroup].isApplying"
          @click="handleApplyReplacement(activeGroup)"
        >
          {{ groupCopy[activeGroup].applyButtonLabel }}
        </button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.source-path-management-dialog :deep(.el-input__wrapper),
.source-path-management-dialog :deep(.el-select__wrapper) {
  min-height: var(--ui-control-height-md, 42px);
  border: 1px solid var(--color-border, #d1d5db) !important;
  border-radius: var(--radius-sm, 8px) !important;
  background: var(--color-bg-card, #ffffff) !important;
  box-shadow: none !important;
  transition:
    border-color 160ms cubic-bezier(0.2, 0, 0, 1),
    box-shadow 160ms cubic-bezier(0.2, 0, 0, 1) !important;
}

.source-path-management-dialog :deep(.el-input__wrapper:hover),
.source-path-management-dialog :deep(.el-select__wrapper:hover) {
  border-color: var(--border-strong, #9ca3af) !important;
}

.source-path-management-dialog :deep(.el-input__wrapper.is-focus),
.source-path-management-dialog :deep(.el-select__wrapper.is-focused),
.source-path-management-dialog :deep(.el-input.is-focus .el-input__wrapper) {
  border-color: var(--color-primary, #3b82f6) !important;
  box-shadow: 0 0 0 1px var(--color-primary, #3b82f6) inset !important;
}

.source-path-management-dialog :deep(.el-input__inner),
.source-path-management-dialog :deep(.el-select__placeholder) {
  color: var(--color-text-main, #111827);
  font-size: 14px;
}

.preset-select-button {
  width: 100%;
  min-height: var(--ui-control-height-md, 42px);
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: var(--radius-sm, 8px);
  background: var(--color-bg-card, #ffffff);
  padding: 9px 12px;
  color: var(--color-text-main, #111827);
  font-size: 14px;
  line-height: 1.5;
  text-align: left;
  transition:
    border-color 160ms cubic-bezier(0.2, 0, 0, 1),
    box-shadow 160ms cubic-bezier(0.2, 0, 0, 1);
}

.preset-select-button:hover {
  border-color: var(--border-strong, #9ca3af);
}

.preset-select-button:focus-visible {
  outline: 2px solid rgba(59, 130, 246, 0.32);
  outline-offset: 2px;
  border-color: var(--color-primary, #3b82f6);
  box-shadow: 0 0 0 1px var(--color-primary, #3b82f6) inset;
}
</style>
