<script lang="ts">
import type { FixedRuleGroup } from '../../types/fixedRules'
import type { DataSource, SourceMetadata, SourceSheetMetadata, VariableTag } from '../../types/workbench'

export type EventTaskRuleDialogMode = 'create' | 'edit'
export type EventTaskParseStrategy = 'group_desc'
export type EventTaskAiParseMode = 'auto' | 'enabled' | 'disabled'
export type EventTaskValidationScope = 'all' | 'specified'

export interface EventTaskRuleDialogDraft {
  rule_id?: string
  group_id: string
  rule_name: string
  enabled: boolean
  description: string
  feishu_source_id: string
  feishu_sheet_id: string
  feishu_sheet_name: string
  config_variable_tag: string
  parse_strategy: EventTaskParseStrategy
  ai_parse_mode: EventTaskAiParseMode
  validation_scope: EventTaskValidationScope
  task_group_id_filter: string
  key_delimiter: string
  fallback_match_field: string
}

export type EventTaskFeishuAuthorizationStatus =
  | 'checking'
  | 'authorized'
  | 'pending_authorization'
  | 'error'
  | 'unknown'

export interface EventTaskFeishuAuthorizationState {
  status: EventTaskFeishuAuthorizationStatus
  message?: string
}

export interface EventTaskRuleDialogProps {
  visible: boolean
  mode: EventTaskRuleDialogMode
  draft?: Partial<EventTaskRuleDialogDraft>
  groups?: FixedRuleGroup[]
  feishuSources?: DataSource[]
  sourceMetadataMap?: Record<string, SourceMetadata>
  feishuAuthorizationMap?: Record<string, EventTaskFeishuAuthorizationState>
  taskVariables?: VariableTag[]
  compositeVariables?: VariableTag[]
  saving?: boolean
  refreshingSheets?: boolean
}
</script>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = withDefaults(defineProps<EventTaskRuleDialogProps>(), {
  draft: undefined,
  groups: () => [],
  feishuSources: () => [],
  sourceMetadataMap: () => ({}),
  feishuAuthorizationMap: () => ({}),
  taskVariables: () => [],
  compositeVariables: () => [],
  saving: false,
  refreshingSheets: false,
})

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'save', payload: EventTaskRuleDialogDraft): void
  (event: 'refresh-sheets', sourceId: string, forceRefresh?: boolean): void
}>()

const DEFAULT_RULE_DESCRIPTION =
  '节日任务表与项目任务配置表一致性校验规则，校验任务组ID、任务描述及 STR_Loot 奖励内容是否一致。'
const DEFAULT_RULE_NAME = '节日任务校验'
const RULE_DESCRIPTION_MAX_LENGTH = 500
const MOCK_PREVIEW_LINES = [
  '识别到任务组 ID（预览）：26051802，26051803，26051804',
  '识别到任务明细数：34 行',
  '示例匹配：26051802_4476 → 任务组ID 26051802 / 任务描述 累计登陆1天',
]

const form = reactive<EventTaskRuleDialogDraft>(createEmptyDraft())

const dialogVisible = computed({
  get: () => props.visible,
  set: (value: boolean) => {
    if (!value) {
      emit('close')
    }
  },
})

const dialogTitle = computed(() =>
  props.mode === 'edit' ? '编辑节日任务校验规则' : '新增节日任务校验规则',
)

const feishuSourceOptions = computed(() =>
  props.feishuSources.filter((source) => source.type === 'feishu'),
)

const compositeVariableOptions = computed(() =>
  props.compositeVariables.filter((variable) => (variable.variable_kind ?? 'single') === 'composite'),
)

const selectedFeishuSource = computed(
  () => feishuSourceOptions.value.find((source) => source.id === form.feishu_source_id) ?? null,
)

const selectedSourceMetadata = computed(() => props.sourceMetadataMap[form.feishu_source_id] ?? null)
const selectedAuthorizationState = computed(
  () => props.feishuAuthorizationMap[form.feishu_source_id] ?? { status: 'unknown' as const },
)

const documentAddress = computed(() => {
  const source = selectedFeishuSource.value
  if (!source) {
    return ''
  }
  return getSourceLocator(source)
})

const documentAddressHref = computed(() =>
  /^https?:\/\//i.test(documentAddress.value) ? documentAddress.value : '',
)

const authorizationStatusLabel = computed(() => {
  const metadata = selectedSourceMetadata.value
  const authorizationStatus = selectedAuthorizationState.value.status
  if (!form.feishu_source_id) {
    return '未选择'
  }
  if (authorizationStatus === 'checking') {
    return '检测中'
  }
  if (authorizationStatus === 'pending_authorization') {
    return '未授权'
  }
  if (authorizationStatus === 'error') {
    return '授权异常'
  }
  if (
    authorizationStatus === 'authorized' ||
    metadata?.authorization_status === 'authorized' ||
    (metadata?.sheets?.length ?? 0) > 0
  ) {
    return '已授权'
  }
  if (props.refreshingSheets) {
    return '检测中'
  }
  return '待读取'
})

const isAuthorized = computed(() => {
  const metadata = selectedSourceMetadata.value
  const authorizationStatus = selectedAuthorizationState.value.status
  if (
    authorizationStatus === 'checking' ||
    authorizationStatus === 'pending_authorization' ||
    authorizationStatus === 'error'
  ) {
    return false
  }
  return (
    authorizationStatus === 'authorized' ||
    metadata?.authorization_status === 'authorized' ||
    (metadata?.sheets?.length ?? 0) > 0
  )
})

interface TaskSheetOption {
  sheet_id: string
  name: string
}

const feishuSheetOptions = computed<TaskSheetOption[]>(() => {
  return buildSheetOptions(form.feishu_source_id, form.feishu_sheet_id, form.feishu_sheet_name)
})

const selectedFeishuSheet = computed(
  () => feishuSheetOptions.value.find((sheet) => sheet.sheet_id === form.feishu_sheet_id) ?? null,
)

const selectedConfigVariable = computed(
  () => compositeVariableOptions.value.find((variable) => variable.tag === form.config_variable_tag) ?? null,
)

const ruleDescriptionCount = computed(() => form.description.length)

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      resetForm()
    }
  },
  { immediate: true },
)

watch(
  () => props.draft,
  () => {
    if (props.visible) {
      resetForm()
    }
  },
  { deep: true },
)

watch(
  () => form.feishu_source_id,
  () => {
    requestSheetRefreshIfNeeded(form.feishu_source_id)
    const sourceSheetOptions = buildSheetOptions(form.feishu_source_id)
    if (
      !form.feishu_sheet_id ||
      !sourceSheetOptions.some((sheet) => sheet.sheet_id === form.feishu_sheet_id)
    ) {
      const firstSheet = sourceSheetOptions[0]
      form.feishu_sheet_id = firstSheet?.sheet_id ?? ''
      form.feishu_sheet_name = firstSheet?.name ?? ''
    }
  },
)

watch(
  () => form.feishu_sheet_id,
  () => {
    const selectedSheet = selectedFeishuSheet.value
    form.feishu_sheet_name = selectedSheet?.name ?? form.feishu_sheet_name
  },
)

watch(
  feishuSheetOptions,
  (options) => {
    if (form.feishu_sheet_id && options.some((sheet) => sheet.sheet_id === form.feishu_sheet_id)) {
      return
    }
    const firstSheet = options[0]
    form.feishu_sheet_id = firstSheet?.sheet_id ?? ''
    form.feishu_sheet_name = firstSheet?.name ?? ''
  },
)

function buildSheetOptions(
  sourceId: string,
  currentSheetId = '',
  currentSheetName = '',
): TaskSheetOption[] {
  const options = new Map<string, TaskSheetOption>()
  const metadataSheets = props.sourceMetadataMap[sourceId]?.sheets ?? []
  metadataSheets.forEach((sheet: SourceSheetMetadata) => {
    const sheetId = sheet.sheet_id?.trim() || sheet.name.trim()
    if (!sheetId) {
      return
    }
    options.set(sheetId, {
      sheet_id: sheetId,
      name: sheet.name.trim() || sheetId,
    })
  })
  props.taskVariables
    .filter((variable) => !sourceId || variable.source_id === sourceId)
    .forEach((variable) => {
      const sheetName = variable.sheet?.trim() ?? ''
      if (!sheetName || options.has(sheetName)) {
        return
      }
      options.set(sheetName, {
        sheet_id: sheetName,
        name: sheetName,
      })
    })
  if (currentSheetId && !options.has(currentSheetId)) {
    options.set(currentSheetId, {
      sheet_id: currentSheetId,
      name: currentSheetName || currentSheetId,
    })
  }
  return [...options.values()]
}

function createEmptyDraft(): EventTaskRuleDialogDraft {
  return {
    group_id: '',
    rule_name: DEFAULT_RULE_NAME,
    enabled: true,
    description: DEFAULT_RULE_DESCRIPTION,
    feishu_source_id: '',
    feishu_sheet_id: '',
    feishu_sheet_name: '',
    config_variable_tag: '',
    parse_strategy: 'group_desc',
    ai_parse_mode: 'auto',
    validation_scope: 'all',
    task_group_id_filter: '',
    key_delimiter: '_',
    fallback_match_field: 'INT_TaskID',
  }
}

function resetForm(): void {
  const draftGroupId = props.draft?.group_id?.trim() ?? ''
  const defaultGroupId =
    props.groups.find((group) => group.group_id === 'ungrouped')?.group_id ??
    props.groups.find((group) => group.group_name === '未分组')?.group_id ??
    props.groups[0]?.group_id ??
    ''
  const draftSourceId = props.draft?.feishu_source_id?.trim() ?? ''
  const firstSourceId = draftSourceId || feishuSourceOptions.value[0]?.id || ''
  const sheetOptions = buildSheetOptions(
    firstSourceId,
    props.draft?.feishu_sheet_id,
    props.draft?.feishu_sheet_name,
  )
  const firstSheet =
    sheetOptions.find((sheet) => sheet.sheet_id === props.draft?.feishu_sheet_id) ?? sheetOptions[0]
  const preferredVariableTag =
    props.draft?.config_variable_tag?.trim() ||
    (compositeVariableOptions.value.find((variable) => variable.sheet === 'EventTask')?.tag ??
      compositeVariableOptions.value.find((variable) => variable.columns?.includes('INT_ID'))?.tag ??
      compositeVariableOptions.value[0]?.tag ??
      '')
  Object.assign(form, {
    ...createEmptyDraft(),
    ...props.draft,
    group_id: draftGroupId || defaultGroupId,
    rule_name: props.draft?.rule_name?.trim() || DEFAULT_RULE_NAME,
    enabled: props.draft?.enabled ?? true,
    description: props.draft?.description ?? DEFAULT_RULE_DESCRIPTION,
    feishu_source_id: firstSourceId,
    feishu_sheet_id: firstSheet?.sheet_id ?? '',
    feishu_sheet_name: firstSheet?.name ?? '',
    config_variable_tag: preferredVariableTag,
    parse_strategy: props.draft?.parse_strategy ?? 'group_desc',
    ai_parse_mode: props.draft?.ai_parse_mode ?? 'auto',
    validation_scope: props.draft?.validation_scope ?? 'all',
    task_group_id_filter: props.draft?.task_group_id_filter ?? '',
    key_delimiter: props.draft?.key_delimiter ?? '_',
    fallback_match_field: props.draft?.fallback_match_field ?? 'INT_TaskID',
  })
  requestSheetRefreshIfNeeded(form.feishu_source_id)
}

function buildPayload(): EventTaskRuleDialogDraft {
  const taskGroupFilter =
    form.validation_scope === 'specified'
      ? normalizeTaskGroupIdFilter(form.task_group_id_filter)
      : ''

  return {
    rule_id: form.rule_id?.trim() || undefined,
    group_id: form.group_id.trim(),
    rule_name: form.rule_name.trim(),
    enabled: form.enabled,
    description: form.description.trim(),
    feishu_source_id: form.feishu_source_id.trim(),
    feishu_sheet_id: form.feishu_sheet_id.trim(),
    feishu_sheet_name: form.feishu_sheet_name.trim(),
    config_variable_tag: form.config_variable_tag.trim(),
    parse_strategy: form.parse_strategy,
    ai_parse_mode: form.ai_parse_mode,
    validation_scope: form.validation_scope,
    task_group_id_filter: taskGroupFilter,
    key_delimiter: form.key_delimiter.trim() || '_',
    fallback_match_field: form.fallback_match_field.trim() || 'INT_TaskID',
  }
}

function validateForSave(payload: EventTaskRuleDialogDraft): boolean {
  if (!payload.group_id) {
    ElMessage.warning('请选择规则组。')
    return false
  }
  if (!payload.rule_name) {
    ElMessage.warning('规则名称不能为空。')
    return false
  }
  if (!payload.feishu_source_id) {
    ElMessage.warning('请选择任务数据源。')
    return false
  }
  if (!payload.feishu_sheet_id) {
    ElMessage.warning('请选择任务 Sheet。')
    return false
  }
  if (!payload.config_variable_tag) {
    ElMessage.warning('请选择任务配置组合变量。')
    return false
  }
  if (payload.validation_scope === 'specified' && !payload.task_group_id_filter) {
    ElMessage.warning('请输入指定任务组 ID，多个 ID 用英文逗号分隔。')
    return false
  }
  return true
}

function handleClose(): void {
  emit('close')
}

function handleRefreshSheets(): void {
  const sourceId = form.feishu_source_id.trim()
  if (!sourceId) {
    return
  }
  emit('refresh-sheets', sourceId, true)
}

function handleSave(): void {
  const payload = buildPayload()
  if (!validateForSave(payload)) {
    return
  }
  emit('save', payload)
}

function requestSheetRefreshIfNeeded(sourceId: string): void {
  const normalizedSourceId = sourceId.trim()
  if (!props.visible || !normalizedSourceId || props.sourceMetadataMap[normalizedSourceId]?.sheets?.length) {
    return
  }
  const authorizationState = props.feishuAuthorizationMap[normalizedSourceId]
  if (
    authorizationState?.status === 'checking' ||
    authorizationState?.status === 'pending_authorization' ||
    authorizationState?.status === 'error'
  ) {
    return
  }
  emit('refresh-sheets', normalizedSourceId, false)
}

function getSourceLocator(source: DataSource | null): string {
  if (!source) {
    return '未选择飞书数据源'
  }
  return source.pathOrUrl || source.url || source.path || source.id
}

function buildSourceOptionLabel(source: DataSource): string {
  return source.id
}

function getVariableFieldSummary(variable: VariableTag | null): string {
  if (!variable) {
    return '未选择组合变量'
  }
  const fields = variable.columns?.filter(Boolean) ?? []
  if (fields.length) {
    return fields.join(' / ')
  }
  return variable.key_column || variable.tag
}

function buildVariableOptionLabel(variable: VariableTag): string {
  return `${variable.tag} · ${variable.sheet} · ${getVariableFieldSummary(variable)}`
}

function getVariablePathSummary(variable: VariableTag | null): string {
  if (!variable) {
    return '请先选择任务配置组合变量'
  }
  const availableFields = new Set((variable.columns ?? []).map((field) => field.trim()))
  const preferredSummary = ['INT_ID', 'STR_Desc', 'STR_Loot']
    .filter((field) => availableFields.has(field) || variable.key_column?.trim() === field)
    .join(' / ')
  return `${variable.sheet} · ${preferredSummary || getVariableFieldSummary(variable)}`
}

function normalizeTaskGroupIdFilter(value: string): string {
  return value
    .replace(/，/g, ',')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
    .join(', ')
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    :title="dialogTitle"
    width="1080px"
    class="package-items-rule-dialog event-task-rule-dialog"
    append-to-body
    destroy-on-close
  >
    <div class="package-items-rule-dialog__body">
      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>基本信息</h3>
            <p>规则归属、命名与启用状态</p>
          </div>
        </div>
        <div class="package-items-rule-dialog__basic-grid">
          <div class="package-items-rule-dialog__field package-items-rule-dialog__field--group">
            <label>规则组</label>
            <el-select v-model="form.group_id" class="w-full" placeholder="选择规则组">
              <el-option
                v-for="group in groups"
                :key="group.group_id"
                :label="group.group_name"
                :value="group.group_id"
              />
            </el-select>
          </div>
          <div class="package-items-rule-dialog__field package-items-rule-dialog__field--name">
            <label>规则名称</label>
            <el-input v-model="form.rule_name" placeholder="例如：26年7月节日任务奖励 vs 配置表校验" />
          </div>
          <div class="package-items-rule-dialog__field package-items-rule-dialog__field--switch">
            <label>启用状态</label>
            <el-switch v-model="form.enabled" />
          </div>
        </div>
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>任务数据源（飞书）</h3>
          </div>
        </div>
        <div class="package-items-rule-dialog__source-grid">
          <div class="package-items-rule-dialog__field">
            <label>飞书数据源</label>
            <el-select
              v-model="form.feishu_source_id"
              class="w-full"
              filterable
              placeholder="选择飞书数据源"
            >
              <el-option
                v-for="source in feishuSourceOptions"
                :key="source.id"
                :label="buildSourceOptionLabel(source)"
                :value="source.id"
              />
            </el-select>
          </div>
          <div class="package-items-rule-dialog__field">
            <label>Sheet 页</label>
            <el-select
              v-model="form.feishu_sheet_id"
              class="w-full"
              filterable
              placeholder="选择飞书 Sheet"
            >
              <el-option
                v-for="sheet in feishuSheetOptions"
                :key="sheet.sheet_id"
                :label="sheet.name"
                :value="sheet.sheet_id"
              />
            </el-select>
          </div>
          <div class="package-items-rule-dialog__field package-items-rule-dialog__field--status">
            <label>授权状态</label>
            <span
              class="package-items-rule-dialog__auth-status"
              :class="{
                'package-items-rule-dialog__auth-status--success': isAuthorized,
                'package-items-rule-dialog__auth-status--warning': !isAuthorized,
              }"
            >
              {{ authorizationStatusLabel }}
            </span>
          </div>
        </div>
        <div class="package-items-rule-dialog__link-row">
          <div class="package-items-rule-dialog__document-link">
            <span>文档地址</span>
            <a
              v-if="documentAddressHref"
              :href="documentAddressHref"
              target="_blank"
              rel="noreferrer"
            >
              {{ documentAddress }}
            </a>
            <strong v-else>{{ documentAddress || '未选择飞书数据源' }}</strong>
          </div>
          <el-button
            size="small"
            :loading="refreshingSheets"
            :disabled="!form.feishu_source_id"
            @click="handleRefreshSheets"
          >
            刷新 Sheet 列表
          </el-button>
        </div>
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>任务配置组合变量</h3>
          </div>
        </div>
        <div class="package-items-rule-dialog__field">
          <label>组合变量</label>
          <el-select
            v-model="form.config_variable_tag"
            class="w-full"
            filterable
            placeholder="选择任务配置组合变量"
          >
            <el-option
              v-for="variable in compositeVariableOptions"
              :key="variable.tag"
              :label="buildVariableOptionLabel(variable)"
              :value="variable.tag"
            />
          </el-select>
          <div class="package-items-rule-dialog__field-path">
            {{ getVariablePathSummary(selectedConfigVariable) }}
          </div>
        </div>
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>匹配策略</h3>
          </div>
        </div>
        <div class="package-items-rule-dialog__strategy-grid">
          <div class="package-items-rule-dialog__field">
            <label>解析方式</label>
            <el-select v-model="form.parse_strategy" class="w-full">
              <el-option label="任务组ID + 任务描述双重匹配（推荐）" value="group_desc" />
            </el-select>
          </div>
          <div class="package-items-rule-dialog__field">
            <label>AI 辅助解析</label>
            <el-radio-group v-model="form.ai_parse_mode" class="event-task-rule-dialog__mode-radios">
              <el-radio label="auto">自动</el-radio>
              <el-radio label="enabled">开启</el-radio>
              <el-radio label="disabled">关闭</el-radio>
            </el-radio-group>
          </div>
        </div>
        <div class="event-task-rule-dialog__strategy-help">
          <span>key 分隔符：{{ form.key_delimiter || '_' }}</span>
          <span>任务组ID：取 key 前缀</span>
          <span>备用匹配：{{ form.fallback_match_field || 'INT_TaskID' }}</span>
        </div>
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>校验范围</h3>
          </div>
        </div>
        <el-radio-group v-model="form.validation_scope" class="package-items-rule-dialog__scope-radios">
          <el-radio label="all">全部任务</el-radio>
          <el-radio label="specified">指定任务组 ID</el-radio>
        </el-radio-group>
        <el-input
          v-if="form.validation_scope === 'specified'"
          v-model="form.task_group_id_filter"
          class="package-items-rule-dialog__scope-input"
          placeholder="请输入任务组ID，多个用英文逗号分隔"
        />
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>解析预览</h3>
          </div>
        </div>
        <div class="package-items-rule-dialog__preview-box">
          <div v-for="line in MOCK_PREVIEW_LINES" :key="line">{{ line }}</div>
        </div>
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>规则说明</h3>
          </div>
        </div>
        <div class="package-items-rule-dialog__textarea-wrap">
          <el-input
            v-model="form.description"
            type="textarea"
            :maxlength="RULE_DESCRIPTION_MAX_LENGTH"
            :rows="3"
            resize="none"
          />
          <div class="package-items-rule-dialog__counter">
            {{ ruleDescriptionCount }} / {{ RULE_DESCRIPTION_MAX_LENGTH }}
          </div>
        </div>
      </section>
    </div>

    <template #footer>
      <div class="package-items-rule-dialog__footer">
        <el-button :disabled="saving" @click="handleClose">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存规则</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.package-items-rule-dialog__body {
  max-height: calc(100vh - 190px);
  overflow-y: auto;
  padding: 0 6px 0 0;
}

.package-items-rule-dialog__section {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 14px 0;
  border-bottom: 1px solid var(--color-border, #e5e7eb);
}

.package-items-rule-dialog__section:first-child {
  padding-top: 0;
}

.package-items-rule-dialog__section:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.package-items-rule-dialog__section-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
}

.package-items-rule-dialog__section-head h3 {
  margin: 0;
  color: var(--color-ink-900, #111827);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0;
}

.package-items-rule-dialog__section-head p {
  margin: 2px 0 0;
  color: var(--color-ink-500, #6b7280);
  font-size: 12px;
}

.package-items-rule-dialog__basic-grid {
  display: grid;
  grid-template-columns: minmax(240px, 320px) minmax(300px, 400px) minmax(110px, 140px);
  align-items: end;
  gap: 24px;
}

.package-items-rule-dialog__source-grid {
  display: grid;
  grid-template-columns: minmax(240px, 320px) minmax(240px, 320px) minmax(110px, 160px);
  align-items: end;
  gap: 24px;
}

.package-items-rule-dialog__strategy-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 0.55fr);
  gap: 24px;
}

.package-items-rule-dialog__field {
  min-width: 0;
}

.package-items-rule-dialog__field label {
  display: block;
  margin-bottom: 6px;
  color: var(--color-ink-500, #64748b);
  font-size: 12px;
  font-weight: 500;
  line-height: 18px;
}

.package-items-rule-dialog__field--switch {
  justify-self: end;
  min-width: 110px;
}

.package-items-rule-dialog__field--status {
  align-self: end;
}

.package-items-rule-dialog__auth-status {
  display: inline-flex;
  min-height: 32px;
  align-items: center;
  color: var(--color-ink-500, #6b7280);
  font-size: 13px;
  font-weight: 600;
}

.package-items-rule-dialog__auth-status--success {
  color: #16a34a;
}

.package-items-rule-dialog__auth-status--warning {
  color: #d97706;
}

.package-items-rule-dialog__link-row {
  display: flex;
  min-height: 24px;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px 24px;
  font-size: 13px;
  line-height: 20px;
}

.package-items-rule-dialog__document-link {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 18px;
}

.package-items-rule-dialog__document-link span {
  flex: 0 0 auto;
  color: var(--color-ink-500, #6b7280);
  font-weight: 500;
}

.package-items-rule-dialog__document-link a {
  color: #0f62fe;
  text-decoration: none;
  word-break: break-all;
}

.package-items-rule-dialog__document-link a:hover {
  text-decoration: underline;
}

.package-items-rule-dialog__document-link strong {
  color: var(--color-ink-700, #334155);
  font-weight: 500;
  word-break: break-all;
}

.package-items-rule-dialog__field-path {
  margin-top: 8px;
  color: var(--color-ink-500, #64748b);
  font-size: 12px;
  line-height: 18px;
  word-break: break-all;
}

.event-task-rule-dialog__mode-radios {
  display: flex;
  min-height: 32px;
  align-items: center;
  flex-wrap: wrap;
  gap: 28px;
}

.event-task-rule-dialog__strategy-help {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 28px;
  border-radius: 6px;
  background: #f5f7fb;
  padding: 10px 14px;
  color: var(--color-ink-500, #64748b);
  font-size: 12px;
  line-height: 18px;
}

.package-items-rule-dialog__scope-input {
  margin-top: 10px;
  max-width: 520px;
}

.package-items-rule-dialog__scope-radios {
  display: flex;
  flex-wrap: wrap;
  gap: 28px;
}

.package-items-rule-dialog__preview-box {
  border-radius: 6px;
  background: #f5f7fb;
  padding: 12px 16px;
  color: var(--color-ink-600, #475569);
  font-size: 13px;
  line-height: 24px;
}

.package-items-rule-dialog__textarea-wrap {
  position: relative;
}

.package-items-rule-dialog__counter {
  position: absolute;
  right: 12px;
  bottom: 8px;
  color: var(--color-ink-500, #64748b);
  font-size: 12px;
  line-height: 16px;
}

.package-items-rule-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: 16px;
}

:global(.event-task-rule-dialog .el-dialog__body) {
  padding: 18px 24px 0;
}

:global(.event-task-rule-dialog .el-dialog__footer) {
  margin-top: 0;
  border-top: 1px solid var(--color-border, #e5e7eb);
  padding: 16px 24px 18px;
}

:global(.event-task-rule-dialog .el-textarea__inner) {
  min-height: var(--ui-textarea-min-height-md, 80px) !important;
  padding-bottom: 28px;
}

@media (max-width: 900px) {
  .package-items-rule-dialog__basic-grid,
  .package-items-rule-dialog__source-grid,
  .package-items-rule-dialog__strategy-grid {
    grid-template-columns: 1fr;
  }

  .package-items-rule-dialog__field--switch {
    justify-self: start;
  }

  .package-items-rule-dialog__section-head {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
