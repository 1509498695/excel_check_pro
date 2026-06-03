<script lang="ts">
import type {
  PackageItemsFieldMapping,
  FixedRuleGroup,
  PackageAiParseMode,
  PackageItemsPreviewRow,
  PackageParseStrategy,
} from '../../types/fixedRules'
import type { DataSource, SourceMetadata, SourceSheetMetadata, VariableTag } from '../../types/workbench'

export type PackageItemsRuleDialogMode = 'create' | 'edit'
export type PackageItemsValidationScope = 'all' | 'specified'

export interface PackageItemsRuleDialogDraft {
  rule_id?: string
  group_id: string
  rule_name: string
  feishu_source_id: string
  feishu_sheet_id: string
  feishu_sheet_name: string
  detail_variable_tag: string
  config_variable_tag: string
  parse_strategy: PackageParseStrategy
  ai_parse_mode: PackageAiParseMode
  validation_scope: PackageItemsValidationScope
  package_id_filter: string
}

export interface PackageItemsRuleDialogPreview {
  status?: 'idle' | 'success' | 'failed'
  parseStatus?: 'success' | 'failed'
  fieldMapping?: PackageItemsFieldMapping
  warnings?: string[]
  errorMessage?: string
  sourceId?: string
  sheetId?: string
  parseStrategy?: PackageParseStrategy
  aiParseMode?: PackageAiParseMode
  validationScope?: PackageItemsValidationScope
  packageIdFilter?: string
  parseMode?: 'rule' | 'ai'
  aiUsed?: boolean
  confidence?: number
  packageIds?: string[]
  detailRowCount?: number
  errors?: string[]
  previewRows?: PackageItemsPreviewRow[]
}

export type PackageItemsFeishuAuthorizationStatus =
  | 'checking'
  | 'authorized'
  | 'pending_authorization'
  | 'error'
  | 'unknown'

export interface PackageItemsFeishuAuthorizationState {
  status: PackageItemsFeishuAuthorizationStatus
  message?: string
}

export interface PackageItemsRuleDialogProps {
  visible: boolean
  mode: PackageItemsRuleDialogMode
  draft?: Partial<PackageItemsRuleDialogDraft>
  groups?: FixedRuleGroup[]
  feishuSources?: DataSource[]
  sourceMetadataMap?: Record<string, SourceMetadata>
  feishuAuthorizationMap?: Record<string, PackageItemsFeishuAuthorizationState>
  detailVariables?: VariableTag[]
  compositeVariables?: VariableTag[]
  preview?: PackageItemsRuleDialogPreview
  saving?: boolean
  previewing?: boolean
  refreshingSheets?: boolean
  backendReady?: boolean
}
</script>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = withDefaults(defineProps<PackageItemsRuleDialogProps>(), {
  draft: undefined,
  groups: () => [],
  feishuSources: () => [],
  sourceMetadataMap: () => ({}),
  feishuAuthorizationMap: () => ({}),
  detailVariables: () => [],
  compositeVariables: () => [],
  preview: undefined,
  saving: false,
  previewing: false,
  refreshingSheets: false,
  backendReady: true,
})

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'save', payload: PackageItemsRuleDialogDraft): void
  (event: 'preview', payload: PackageItemsRuleDialogDraft): void
  (event: 'refresh-sheets', sourceId: string, forceRefresh?: boolean): void
}>()

const DEFAULT_RULE_DESCRIPTION = '登峰礼包规划表与项目礼包配置表一致性校验规则'
const RULE_DESCRIPTION_MAX_LENGTH = 500

const form = reactive<PackageItemsRuleDialogDraft>(createEmptyDraft())
const uiState = reactive({
  enabled: true,
  ruleDescription: DEFAULT_RULE_DESCRIPTION,
})

const dialogVisible = computed({
  get: () => props.visible,
  set: (value: boolean) => {
    if (!value) {
      emit('close')
    }
  },
})

const dialogTitle = computed(() =>
  props.mode === 'edit' ? '编辑礼包校验规则' : '新增礼包校验规则',
)

const feishuSourceOptions = computed(() =>
  props.feishuSources.filter((source) => source.type === 'feishu'),
)

const detailVariableOptions = computed(() =>
  props.detailVariables.filter((variable) => (variable.variable_kind ?? 'single') === 'composite'),
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

interface PackageSheetOption {
  sheet_id: string
  name: string
}

const feishuSheetOptions = computed<PackageSheetOption[]>(() => {
  return buildSheetOptions(form.feishu_source_id, form.feishu_sheet_id, form.feishu_sheet_name)
})

function buildSheetOptions(
  sourceId: string,
  currentSheetId = '',
  currentSheetName = '',
): PackageSheetOption[] {
  const options = new Map<string, PackageSheetOption>()
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
  props.detailVariables
    .filter((variable) => !sourceId || variable.source_id === sourceId)
    .forEach((variable) => {
      const sheetName = variable.sheet?.trim() ?? ''
      if (!sheetName) {
        return
      }
      if (!options.has(sheetName)) {
        options.set(sheetName, {
          sheet_id: sheetName,
          name: sheetName,
        })
      }
    })
  if (currentSheetId && !options.has(currentSheetId)) {
    options.set(currentSheetId, {
      sheet_id: currentSheetId,
      name: currentSheetName || currentSheetId,
    })
  }
  return [...options.values()]
}

const selectedFeishuSheet = computed(
  () => feishuSheetOptions.value.find((sheet) => sheet.sheet_id === form.feishu_sheet_id) ?? null,
)

const selectedConfigVariable = computed(
  () => compositeVariableOptions.value.find((variable) => variable.tag === form.config_variable_tag) ?? null,
)

const currentPreview = computed(() => {
  const preview = props.preview
  if (!preview) {
    return null
  }
  const packageFilter = form.validation_scope === 'specified' ? normalizePackageIdFilter(form.package_id_filter) : ''
  if (
    preview.sourceId !== form.feishu_source_id ||
    preview.sheetId !== form.feishu_sheet_id ||
    preview.parseStrategy !== form.parse_strategy ||
    preview.aiParseMode !== form.ai_parse_mode ||
    preview.validationScope !== form.validation_scope ||
    (preview.packageIdFilter ?? '') !== packageFilter
  ) {
    return null
  }
  return preview
})

const hasPreviewSelection = computed(() => Boolean(form.feishu_source_id && form.feishu_sheet_id))

const isPreviewSuccessful = computed(
  () => currentPreview.value?.status === 'success' && currentPreview.value.parseStatus === 'success',
)

const previewPackageIds = computed(() =>
  isPreviewSuccessful.value ? currentPreview.value?.packageIds ?? [] : [],
)

const previewDetailRowCount = computed(() =>
  isPreviewSuccessful.value ? currentPreview.value?.detailRowCount ?? 0 : 0,
)

const previewWarnings = computed(() => currentPreview.value?.warnings ?? [])

const previewErrors = computed(() => currentPreview.value?.errors ?? [])

const ruleDescriptionCount = computed(() => uiState.ruleDescription.length)

const previewInfoLines = computed(() => {
  if (isPreviewSuccessful.value) {
    return [
      `识别到礼包 ID（预览）：${
        previewPackageIds.value.length ? previewPackageIds.value.join('、') : '未识别到礼包 ID'
      }`,
      `识别到明细行数：${previewDetailRowCount.value} 行`,
    ]
  }
  if (previewErrorMessage.value) {
    return [previewErrorMessage.value]
  }
  return ['尚未生成当前配置的解析预览。']
})

const previewErrorMessage = computed(() => {
  if (!props.backendReady) {
    return '当前环境未启用 IAP礼包校验能力，无法生成解析预览或保存规则。'
  }
  if (!hasPreviewSelection.value) {
    return '请先选择飞书数据源和礼包规划 Sheet。'
  }
  if (!currentPreview.value) {
    return '尚未生成当前配置的解析预览。'
  }
  if (currentPreview.value.status === 'failed') {
    return currentPreview.value.errorMessage || '解析预览失败，请检查飞书数据源和 Sheet。'
  }
  if (currentPreview.value.parseStatus === 'failed') {
    return currentPreview.value.errorMessage || previewErrors.value[0] || '未识别到有效的礼包明细表头。'
  }
  return ''
})

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
    if (
      form.detail_variable_tag &&
      detailVariableOptions.value.some((variable) => variable.tag === form.detail_variable_tag)
    ) {
      return
    }
    form.detail_variable_tag = detailVariableOptions.value[0]?.tag ?? ''
  },
)

watch(
  () => form.feishu_sheet_id,
  () => {
    const selectedSheet = selectedFeishuSheet.value
    form.feishu_sheet_name = selectedSheet?.name ?? form.feishu_sheet_name
    if (
      form.detail_variable_tag &&
      detailVariableOptions.value.some((variable) => variable.tag === form.detail_variable_tag)
    ) {
      return
    }
    form.detail_variable_tag = detailVariableOptions.value[0]?.tag ?? ''
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

function createEmptyDraft(): PackageItemsRuleDialogDraft {
  return {
    group_id: '',
    rule_name: '',
    feishu_source_id: '',
    feishu_sheet_id: '',
    feishu_sheet_name: '',
    detail_variable_tag: '',
    config_variable_tag: '',
    parse_strategy: 'auto',
    ai_parse_mode: 'auto',
    validation_scope: 'all',
    package_id_filter: '',
  }
}

function resetForm(): void {
  const firstGroupId = props.groups[0]?.group_id ?? ''
  const firstSourceId = props.draft?.feishu_source_id ?? feishuSourceOptions.value[0]?.id ?? ''
  const sheetOptions = buildSheetOptions(
    firstSourceId,
    props.draft?.feishu_sheet_id,
    props.draft?.feishu_sheet_name,
  )
  const firstSheet =
    sheetOptions.find((sheet) => sheet.sheet_id === props.draft?.feishu_sheet_id) ?? sheetOptions[0]
  const firstDetailVariableTag =
    props.detailVariables.find(
      (variable) =>
        (!firstSourceId || variable.source_id === firstSourceId) &&
        (!firstSheet || variable.sheet === firstSheet.name || variable.sheet === firstSheet.sheet_id),
    )?.tag ??
    detailVariableOptions.value[0]?.tag ??
    ''
  const firstVariableTag = compositeVariableOptions.value[0]?.tag ?? ''
  Object.assign(form, {
    ...createEmptyDraft(),
    group_id: firstGroupId,
    feishu_source_id: firstSourceId,
    feishu_sheet_id: firstSheet?.sheet_id ?? '',
    feishu_sheet_name: firstSheet?.name ?? '',
    detail_variable_tag: firstDetailVariableTag,
    config_variable_tag: firstVariableTag,
    ...props.draft,
    parse_strategy: props.draft?.parse_strategy ?? 'auto',
    ai_parse_mode: props.draft?.ai_parse_mode ?? 'auto',
    validation_scope: props.draft?.validation_scope ?? 'all',
    package_id_filter: props.draft?.package_id_filter ?? '',
  })
  uiState.enabled = true
  uiState.ruleDescription = DEFAULT_RULE_DESCRIPTION
  requestSheetRefreshIfNeeded(form.feishu_source_id)
}

function buildPayload(): PackageItemsRuleDialogDraft {
  const packageFilter =
    form.validation_scope === 'specified'
      ? normalizePackageIdFilter(form.package_id_filter)
      : ''

  return {
    rule_id: form.rule_id?.trim() || undefined,
    group_id: form.group_id.trim(),
    rule_name: form.rule_name.trim(),
    feishu_source_id: form.feishu_source_id.trim(),
    feishu_sheet_id: form.feishu_sheet_id.trim(),
    feishu_sheet_name: form.feishu_sheet_name.trim(),
    detail_variable_tag: form.detail_variable_tag.trim(),
    config_variable_tag: form.config_variable_tag.trim(),
    parse_strategy: form.parse_strategy,
    ai_parse_mode: form.ai_parse_mode,
    validation_scope: form.validation_scope,
    package_id_filter: packageFilter,
  }
}

function validateForSave(payload: PackageItemsRuleDialogDraft): boolean {
  if (!payload.rule_name) {
    ElMessage.warning('规则名称不能为空。')
    return false
  }
  if (!payload.feishu_source_id) {
    ElMessage.warning('请选择礼包规划数据源。')
    return false
  }
  if (!payload.feishu_sheet_id) {
    ElMessage.warning('请选择礼包规划 Sheet。')
    return false
  }
  if (!payload.config_variable_tag) {
    ElMessage.warning('请选择礼包配置组合变量。')
    return false
  }
  if (payload.validation_scope === 'specified' && !payload.package_id_filter) {
    ElMessage.warning('请输入指定礼包 ID，多个 ID 用英文逗号分隔。')
    return false
  }
  return true
}

function handleClose(): void {
  emit('close')
}

function handlePreview(): void {
  if (!props.backendReady) {
    ElMessage.info('当前环境未启用 IAP礼包校验能力，无法生成解析预览。')
    return
  }
  emit('preview', buildPayload())
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
  if (!props.backendReady) {
    ElMessage.info('当前环境未启用 IAP礼包校验能力，无法保存规则。')
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

function getVariablePathSummary(
  variable: VariableTag | null,
  preferredFields?: string[],
  emptyLabel = '请先选择组合变量',
): string {
  if (!variable) {
    return emptyLabel
  }
  const availableFields = new Set((variable.columns ?? []).map((field) => field.trim()))
  const preferredSummary = preferredFields
    ?.filter((field) => availableFields.has(field) || variable.key_column?.trim() === field)
    .join(' / ')
  return `${variable.source_id} · ${variable.sheet} · ${
    preferredSummary || getVariableFieldSummary(variable)
  }`
}

function normalizePackageIdFilter(value: string): string {
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
    class="package-items-rule-dialog"
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
            <el-input v-model="form.rule_name" placeholder="例如：登峰礼包规划 vs 礼包配置校验" />
          </div>
          <div class="package-items-rule-dialog__field package-items-rule-dialog__field--switch">
            <label>启用状态</label>
            <el-switch v-model="uiState.enabled" />
          </div>
        </div>
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>礼包规划数据源（飞书）</h3>
            <p>用于读取礼包规划明细并解析礼包 ID、道具 ID 与数量</p>
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
            <h3>礼包配置组合变量</h3>
            <p>选择包含 INT_PackageId 与 STR_Items 的组合变量</p>
          </div>
        </div>
        <div class="package-items-rule-dialog__field">
          <label>组合变量</label>
          <el-select
            v-model="form.config_variable_tag"
            class="w-full"
            filterable
            placeholder="选择礼包配置组合变量"
          >
            <el-option
              v-for="variable in compositeVariableOptions"
              :key="variable.tag"
              :label="buildVariableOptionLabel(variable)"
              :value="variable.tag"
            />
          </el-select>
          <div class="package-items-rule-dialog__field-path">
            {{
              getVariablePathSummary(
                selectedConfigVariable,
                ['INT_PackageId', 'STR_Items'],
                '请先选择礼包配置组合变量',
              )
            }}
          </div>
        </div>
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>解析策略</h3>
            <p>规则优先解析，必要时可启用 AI 辅助</p>
          </div>
        </div>
        <div class="package-items-rule-dialog__strategy-grid">
          <div class="package-items-rule-dialog__field">
            <label>解析方式</label>
            <el-select v-model="form.parse_strategy" class="w-full">
              <el-option label="自动识别（规则优先，AI 辅助）" value="auto" />
              <el-option label="仅规则解析" value="rule" />
              <el-option label="仅 AI 解析" value="ai" />
            </el-select>
          </div>
          <div class="package-items-rule-dialog__field">
            <label>AI 辅助解析</label>
            <el-segmented
              v-model="form.ai_parse_mode"
              :options="[
                { label: '自动', value: 'auto' },
                { label: '开启', value: 'enabled' },
                { label: '关闭', value: 'disabled' },
              ]"
              class="w-full"
            />
          </div>
        </div>
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>校验范围</h3>
            <p>默认检查飞书页签全部礼包，也可只检查指定礼包 ID</p>
          </div>
        </div>
        <el-radio-group v-model="form.validation_scope" class="package-items-rule-dialog__scope-radios">
          <el-radio label="all">全部礼包</el-radio>
          <el-radio label="specified">指定礼包 ID</el-radio>
        </el-radio-group>
        <el-input
          v-if="form.validation_scope === 'specified'"
          v-model="form.package_id_filter"
          class="package-items-rule-dialog__scope-input"
          placeholder="请输入礼包 ID，多个用英文逗号分隔"
        />
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>解析预览</h3>
            <p>展示当前规划数据源的识别结果</p>
          </div>
          <el-button
            size="small"
            :loading="previewing"
            :disabled="!backendReady || !hasPreviewSelection"
            @click="handlePreview"
          >
            生成预览
          </el-button>
        </div>
        <div v-if="previewing" class="package-items-rule-dialog__preview-state">
          正在解析飞书礼包规划表...
        </div>
        <div v-else class="package-items-rule-dialog__preview-box">
          <div v-for="line in previewInfoLines" :key="line">{{ line }}</div>
        </div>
        <div v-if="previewWarnings.length" class="package-items-rule-dialog__warnings">
          <div
            v-for="warning in previewWarnings"
            :key="warning"
            class="package-items-rule-dialog__warning"
          >
            {{ warning }}
          </div>
        </div>
        <div v-if="previewErrors.length" class="package-items-rule-dialog__errors">
          <div
            v-for="error in previewErrors"
            :key="error"
            class="package-items-rule-dialog__error"
          >
            {{ error }}
          </div>
        </div>
      </section>

      <section class="package-items-rule-dialog__section">
        <div class="package-items-rule-dialog__section-head">
          <div>
            <h3>规则说明</h3>
            <p>保存后将按礼包 ID 对齐规划明细与配置变量</p>
          </div>
        </div>
        <div class="package-items-rule-dialog__textarea-wrap">
          <el-input
            v-model="uiState.ruleDescription"
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
        <el-button type="primary" :loading="saving" :disabled="!backendReady" @click="handleSave">保存规则</el-button>
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

.package-items-rule-dialog__preview-state {
  border-radius: 6px;
  background: #f5f7fb;
  padding: 12px 16px;
  color: var(--color-ink-500, #6b7280);
  font-size: 13px;
  line-height: 20px;
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

.package-items-rule-dialog__warnings {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.package-items-rule-dialog__errors {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.package-items-rule-dialog__warning {
  border: 1px solid #fde68a;
  border-radius: 8px;
  background: #fffbeb;
  padding: 8px 10px;
  color: #92400e;
  font-size: 12px;
  line-height: 18px;
}

.package-items-rule-dialog__error {
  border: 1px solid #fecaca;
  border-radius: 8px;
  background: #fef2f2;
  padding: 8px 10px;
  color: #b91c1c;
  font-size: 12px;
  line-height: 18px;
}

.package-items-rule-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: 16px;
}

:global(.package-items-rule-dialog .el-dialog__body) {
  padding: 18px 24px 0;
}

:global(.package-items-rule-dialog .el-dialog__footer) {
  margin-top: 0;
  border-top: 1px solid var(--color-border, #e5e7eb);
  padding: 16px 24px 18px;
}

:global(.package-items-rule-dialog .el-textarea__inner) {
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
