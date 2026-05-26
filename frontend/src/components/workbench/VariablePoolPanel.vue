<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

import { fetchCompositePreview } from '../../api/workbench'
import EmptyState from '../shell/EmptyState.vue'
import { useWorkbenchStore } from '../../store/workbench'
import type { VariablePoolStoreLike } from '../../types/panelStores'
import type {
  CompositeVariablePreviewData,
  DataSource,
  ExpectedType,
  VariableTag,
  VariablePreviewData,
} from '../../types/workbench'
import { EXPECTED_TYPE_OPTIONS } from '../../utils/workbenchMeta'

export interface SingleVariablePrefill {
  source_id?: string
  sheet?: string
  column?: string
  tag?: string
  expected_type?: ExpectedType | null
}

export interface CompositeVariablePrefill {
  source_id?: string
  sheet?: string
  columns?: string[]
  key_column?: string
  tag?: string
  append_index_to_key?: boolean
}

const props = withDefaults(
  defineProps<{
    store?: VariablePoolStoreLike
    variant?: 'workbench' | 'fixed-rules'
    toolbarMode?: 'embedded' | 'hidden'
  }>(),
  {
    variant: 'workbench',
    toolbarMode: 'embedded',
  },
)
const emit = defineEmits<{ saved: [tag: string]; changed: [] }>()

const defaultStore = useWorkbenchStore()
const store = props.store ?? defaultStore

const singleDialogVisible = ref(false)
const compositeDialogVisible = ref(false)
const singleEditingTag = ref<string | null>(null)
const compositeEditingTag = ref<string | null>(null)
const singleTagTouched = ref(false)
const compositeTagTouched = ref(false)
const singleMetadataLoading = ref(false)
const compositeMetadataLoading = ref(false)
const singleMetadataError = ref('')
const compositeMetadataError = ref('')
const compositePreviewLoading = ref(false)
const compositePreviewError = ref('')
const compositePreview = ref<CompositeVariablePreviewData | null>(null)

const detailDialogVisible = ref(false)
const detailDialogTag = ref<string | null>(null)
const detailLoading = ref(false)
const detailError = ref('')

const singleDraft = reactive<VariableTag>({
  tag: '',
  source_id: '',
  sheet: '',
  variable_kind: 'single',
  column: '',
  expected_type: 'str',
})
const compositeDraft = reactive<VariableTag>({
  tag: '',
  source_id: '',
  sheet: '',
  variable_kind: 'composite',
  columns: [],
  key_column: '',
  append_index_to_key: false,
  expected_type: 'json',
})
const singleErrors = reactive({ source_id: '', sheet: '', column: '', tag: '', expected_type: '' })
const compositeErrors = reactive({
  source_id: '',
  sheet: '',
  columns: '',
  key_column: '',
  tag: '',
})

const sourceOptions = computed<DataSource[]>(() => store.sources)
const compositeDialogTitle = computed(() =>
  compositeEditingTag.value ? '编辑组合变量' : '添加组合变量',
)
const isFixedRulesVariant = computed(() => props.variant === 'fixed-rules')
const panelCopy = computed(() => ({
  emptyText: '请先添加单个变量或组合变量。',
  sourceTypeError: isFixedRulesVariant.value
    ? '当前项目校验页的字段映射提取支持本地 Excel、SVN Excel 与飞书电子表格。'
    : '当前步骤 2 的字段映射提取支持本地 Excel、SVN Excel 与飞书电子表格。',
  compositeTypeError: isFixedRulesVariant.value
    ? '当前项目校验页的组合变量提取支持本地 Excel、SVN Excel 与飞书电子表格。'
    : '当前步骤 2 的组合变量提取支持本地 Excel、SVN Excel 与飞书电子表格。',
}))

function getSourceLocator(source: DataSource | null | undefined): string {
  return (source?.pathOrUrl ?? source?.path ?? source?.url ?? '').trim()
}

function isExcelLocator(locator: string): boolean {
  const normalized = locator.trim().split(/[?#]/, 1)[0] ?? ''
  return /\.xlsx?$/i.test(normalized)
}

function supportsVariableMappingSource(source: DataSource | null | undefined): boolean {
  if (!source) return false
  if (source.type === 'local_excel') return true
  if (source.type === 'feishu') return true
  if (source.type === 'svn') return isExcelLocator(getSourceLocator(source))
  return false
}

function getMetadataErrorMessage(source: DataSource | null, error: unknown): string {
  const message = error instanceof Error ? error.message : '读取数据源结构失败。'
  if (source?.type === 'feishu') {
    return `飞书电子表格元数据读取失败：${message}`
  }
  return message
}

const singleSource = computed<DataSource | null>(
  () => sourceOptions.value.find((item) => item.id === singleDraft.source_id) ?? null,
)
const compositeSource = computed<DataSource | null>(
  () => sourceOptions.value.find((item) => item.id === compositeDraft.source_id) ?? null,
)
const singleMetadata = computed(() => store.sourceMetadataMap[singleDraft.source_id] ?? null)
const compositeMetadata = computed(() => store.sourceMetadataMap[compositeDraft.source_id] ?? null)
const singleSheetOptions = computed(() => singleMetadata.value?.sheets ?? [])
const compositeSheetOptions = computed(() => compositeMetadata.value?.sheets ?? [])
const singleColumnOptions = computed(
  () => singleSheetOptions.value.find((sheet) => sheet.name === singleDraft.sheet)?.columns ?? [],
)
const compositeColumnOptions = computed(
  () =>
    compositeSheetOptions.value.find((sheet) => sheet.name === compositeDraft.sheet)?.columns ?? [],
)
const compositeKeyOptions = computed(() =>
  compositeDraft.columns?.filter((item): item is string => typeof item === 'string' && !!item) ?? [],
)
const hasDuplicateCompositeKeys = computed(() => compositePreview.value?.has_duplicate_keys ?? false)
const showAppendIndexCheckbox = computed(
  () => hasDuplicateCompositeKeys.value || !!compositeDraft.append_index_to_key,
)
const detailVariable = computed<VariableTag | null>(() =>
  detailDialogTag.value
    ? store.variables.find((variable) => variable.tag === detailDialogTag.value) ?? null
    : null,
)
const detailSource = computed<DataSource | null>(() =>
  detailVariable.value
    ? store.sources.find((source) => source.id === detailVariable.value?.source_id) ?? null
    : null,
)
const detailPreview = computed<VariablePreviewData | null>(() =>
  detailVariable.value ? store.variablePreviewMap[detailVariable.value.tag] ?? null : null,
)
const detailLoadedRows = computed(() => {
  const preview = detailPreview.value
  if (!preview) return 0
  return preview.variable_kind === 'single'
    ? preview.preview_rows.length
    : preview.loaded_rows ?? Object.keys(preview.mapping).length
})
const detailSourcePath = computed(
  () =>
    detailPreview.value?.source_path ??
    detailSource.value?.pathOrUrl ??
    detailSource.value?.path ??
    detailSource.value?.url ??
    '',
)
const canSaveSingle = computed(
  () =>
    !singleMetadataLoading.value &&
    supportsVariableMappingSource(singleSource.value) &&
    !!singleDraft.source_id.trim() &&
    !!singleDraft.sheet.trim() &&
    !!singleDraft.column?.trim() &&
    !!singleDraft.tag.trim() &&
    !!singleDraft.expected_type,
)
const canSaveComposite = computed(
  () =>
    !compositeMetadataLoading.value &&
    !compositePreviewLoading.value &&
    supportsVariableMappingSource(compositeSource.value) &&
    !!compositeDraft.source_id.trim() &&
    !!compositeDraft.sheet.trim() &&
    !!compositeDraft.tag.trim() &&
    (compositeDraft.columns?.length ?? 0) >= 2 &&
    !!compositeDraft.key_column?.trim() &&
    compositeDraft.columns?.includes(compositeDraft.key_column ?? ''),
)
function getSingleSuggestion(sourceId: string, sheet: string, column: string): string {
  return `[${sourceId || 'source'}-${sheet || 'sheet'}-${column || 'column'}]`
}

function getCompositeSuggestion(sourceId: string, sheet: string, keyColumn: string): string {
  return `[${sourceId || 'source'}-${sheet || 'sheet'}-${keyColumn || 'key'}-mapping]`
}

function shouldForceMetadataRefresh(source: DataSource | null | undefined): boolean {
  if (source?.type !== 'feishu') {
    return false
  }
  const cached = store.sourceMetadataMap[source.id]
  return !cached || cached.authorization_status !== 'authorized' || !cached.sheets?.length
}

function getFirstSheet(metadata: { sheets: Array<{ name: string; columns: string[] }> }) {
  return metadata.sheets[0] ?? null
}

function syncSingleTag(): void {
  if (!singleTagTouched.value) {
    singleDraft.tag = getSingleSuggestion(
      singleDraft.source_id.trim(),
      singleDraft.sheet.trim(),
      singleDraft.column?.trim() ?? '',
    )
  }
}

function syncCompositeTag(): void {
  if (!compositeTagTouched.value) {
    compositeDraft.tag = getCompositeSuggestion(
      compositeDraft.source_id.trim(),
      compositeDraft.sheet.trim(),
      compositeDraft.key_column?.trim() ?? '',
    )
  }
}

function clearSingleErrors(): void {
  singleErrors.source_id = ''
  singleErrors.sheet = ''
  singleErrors.column = ''
  singleErrors.tag = ''
  singleErrors.expected_type = ''
}

function clearCompositeErrors(): void {
  compositeErrors.source_id = ''
  compositeErrors.sheet = ''
  compositeErrors.columns = ''
  compositeErrors.key_column = ''
  compositeErrors.tag = ''
}

function resetSingleDraft(): void {
  singleDraft.tag = ''
  singleDraft.source_id = store.preferredSourceId ?? store.sources[0]?.id ?? ''
  singleDraft.sheet = ''
  singleDraft.column = ''
  singleDraft.variable_kind = 'single'
  singleDraft.expected_type = 'str'
  singleTagTouched.value = false
  singleMetadataError.value = ''
  clearSingleErrors()
  syncSingleTag()
}

function resetCompositeDraft(): void {
  compositeDraft.tag = ''
  compositeDraft.source_id = store.preferredSourceId ?? store.sources[0]?.id ?? ''
  compositeDraft.sheet = ''
  compositeDraft.columns = []
  compositeDraft.key_column = ''
  compositeDraft.append_index_to_key = false
  compositeDraft.variable_kind = 'composite'
  compositeDraft.expected_type = 'json'
  compositeTagTouched.value = false
  compositeMetadataError.value = ''
  compositePreviewError.value = ''
  compositePreview.value = null
  clearCompositeErrors()
  syncCompositeTag()
}

async function prepareSingleEditorForSource(sourceId: string, preserve = false): Promise<void> {
  if (!sourceId) return
  if (!supportsVariableMappingSource(singleSource.value)) {
    singleMetadataError.value = panelCopy.value.sourceTypeError
    if (!preserve) {
      singleDraft.sheet = ''
      singleDraft.column = ''
    }
    syncSingleTag()
    return
  }

  singleMetadataLoading.value = true
  singleMetadataError.value = ''
  try {
    const source = singleSource.value
    const metadata = await store.loadSourceMetadata(sourceId, shouldForceMetadataRefresh(source))
    const matchedSheet = metadata.sheets.find((item) => item.name === singleDraft.sheet)
    const shouldAutoSelect = source?.type === 'feishu'
    if (!preserve || !matchedSheet) {
      if (shouldAutoSelect) {
        const firstSheet = getFirstSheet(metadata)
        singleDraft.sheet = firstSheet?.name ?? ''
        singleDraft.column = firstSheet?.columns[0] ?? ''
      } else {
        singleDraft.sheet = ''
        singleDraft.column = ''
      }
    } else if (!matchedSheet.columns.includes(singleDraft.column ?? '')) {
      singleDraft.column = shouldAutoSelect ? matchedSheet.columns[0] ?? '' : ''
    }
    if (!metadata.sheets.length) singleMetadataError.value = '当前数据源没有读取到可用的 Sheet。'
    syncSingleTag()
  } catch (error) {
    singleMetadataError.value = getMetadataErrorMessage(singleSource.value, error)
    if (!preserve) {
      singleDraft.sheet = ''
      singleDraft.column = ''
    }
    ElMessage.error(singleMetadataError.value)
  } finally {
    singleMetadataLoading.value = false
  }
}

async function prepareCompositeEditorForSource(sourceId: string, preserve = false): Promise<void> {
  if (!sourceId) return
  if (!supportsVariableMappingSource(compositeSource.value)) {
    compositeMetadataError.value = panelCopy.value.compositeTypeError
    if (!preserve) {
      compositeDraft.sheet = ''
      compositeDraft.columns = []
      compositeDraft.key_column = ''
    }
    compositePreview.value = null
    syncCompositeTag()
    return
  }

  compositeMetadataLoading.value = true
  compositeMetadataError.value = ''
  try {
    const source = compositeSource.value
    const metadata = await store.loadSourceMetadata(sourceId, shouldForceMetadataRefresh(source))
    const matchedSheet = metadata.sheets.find((item) => item.name === compositeDraft.sheet)
    const shouldAutoSelect = source?.type === 'feishu'
    if (!preserve || !matchedSheet) {
      compositeDraft.sheet = shouldAutoSelect ? getFirstSheet(metadata)?.name ?? '' : ''
      compositeDraft.columns = []
      compositeDraft.key_column = ''
    } else {
      const validColumns = new Set(matchedSheet.columns)
      compositeDraft.columns = (compositeDraft.columns ?? []).filter((item) => validColumns.has(item))
      if (!compositeDraft.columns.includes(compositeDraft.key_column ?? '')) {
        compositeDraft.key_column = ''
      }
    }
    if (!metadata.sheets.length) compositeMetadataError.value = '当前数据源没有读取到可用的 Sheet。'
    syncCompositeTag()
  } catch (error) {
    compositeMetadataError.value = getMetadataErrorMessage(compositeSource.value, error)
    if (!preserve) {
      compositeDraft.sheet = ''
      compositeDraft.columns = []
      compositeDraft.key_column = ''
    }
    ElMessage.error(compositeMetadataError.value)
  } finally {
    compositeMetadataLoading.value = false
  }
}

async function refreshCompositePreview(): Promise<void> {
  compositePreview.value = null
  compositePreviewError.value = ''
  if (!canSaveComposite.value || !compositeSource.value) return

  compositePreviewLoading.value = true
  try {
    const response = await fetchCompositePreview({
      source: compositeSource.value,
      sheet: compositeDraft.sheet,
      columns: compositeDraft.columns ?? [],
      key_column: compositeDraft.key_column ?? '',
      append_index_to_key: compositeDraft.append_index_to_key ?? false,
    })
    compositePreview.value = response.data
    if (response.data.has_duplicate_keys && !compositeDraft.append_index_to_key) {
      const duplicateText =
        response.data.duplicate_keys_preview?.length
          ? ` '${response.data.duplicate_keys_preview.join("', '")}'`
          : ''
      compositePreviewError.value = `组合变量的 key 列 '${response.data.key_column}' 存在重复值${duplicateText}，无法生成唯一映射。`
    }
    if (!response.data.has_duplicate_keys && compositeEditingTag.value === null) {
      compositeDraft.append_index_to_key = false
    }
  } catch (error) {
    compositePreviewError.value = error instanceof Error ? error.message : '读取组合变量预览失败。'
  } finally {
    compositePreviewLoading.value = false
  }
}

function applySinglePrefill(prefill?: SingleVariablePrefill): void {
  if (!prefill) {
    syncSingleTag()
    return
  }
  singleDraft.source_id = prefill.source_id?.trim() || singleDraft.source_id
  singleDraft.sheet = prefill.sheet?.trim() ?? ''
  singleDraft.column = prefill.column?.trim() ?? ''
  singleDraft.expected_type = prefill.expected_type ?? 'str'
  if (prefill.tag?.trim()) {
    singleDraft.tag = prefill.tag.trim()
    singleTagTouched.value = true
  }
  syncSingleTag()
}

function applyCompositePrefill(prefill?: CompositeVariablePrefill): void {
  if (!prefill) {
    syncCompositeTag()
    return
  }
  compositeDraft.source_id = prefill.source_id?.trim() || compositeDraft.source_id
  compositeDraft.sheet = prefill.sheet?.trim() ?? ''
  compositeDraft.columns = [...new Set((prefill.columns ?? []).map((item) => item.trim()).filter(Boolean))]
  compositeDraft.key_column = prefill.key_column?.trim() ?? ''
  compositeDraft.append_index_to_key = prefill.append_index_to_key ?? false
  if (prefill.tag?.trim()) {
    compositeDraft.tag = prefill.tag.trim()
    compositeTagTouched.value = true
  }
  syncCompositeTag()
}

async function openSingleCreateTab(prefill?: SingleVariablePrefill): Promise<void> {
  resetSingleDraft()
  applySinglePrefill(prefill)
  singleEditingTag.value = null
  singleDialogVisible.value = true
  await prepareSingleEditorForSource(singleDraft.source_id, Boolean(prefill))
}

async function openCompositeCreateTab(prefill?: CompositeVariablePrefill): Promise<void> {
  resetCompositeDraft()
  applyCompositePrefill(prefill)
  compositeEditingTag.value = null
  compositeDialogVisible.value = true
  await prepareCompositeEditorForSource(compositeDraft.source_id, Boolean(prefill))
  await refreshCompositePreview()
}

async function openEditTab(variable: VariableTag): Promise<void> {
  if ((variable.variable_kind ?? 'single') === 'composite') {
    compositeEditingTag.value = variable.tag
    compositeDraft.tag = variable.tag
    compositeDraft.source_id = variable.source_id
    compositeDraft.sheet = variable.sheet
    compositeDraft.columns = [...(variable.columns ?? [])]
    compositeDraft.key_column = variable.key_column ?? ''
    compositeDraft.append_index_to_key = variable.append_index_to_key ?? false
    compositeDraft.expected_type = 'json'
    compositeTagTouched.value =
      variable.tag.trim() !==
      getCompositeSuggestion(
        variable.source_id.trim(),
        variable.sheet.trim(),
        (variable.key_column ?? '').trim(),
      )
    compositeDialogVisible.value = true
    await prepareCompositeEditorForSource(variable.source_id, true)
    await refreshCompositePreview()
    return
  }

  singleEditingTag.value = variable.tag
  singleDraft.tag = variable.tag
  singleDraft.source_id = variable.source_id
  singleDraft.sheet = variable.sheet
  singleDraft.column = variable.column ?? ''
  singleDraft.expected_type = variable.expected_type ?? 'str'
  singleTagTouched.value =
    variable.tag.trim() !==
    getSingleSuggestion(
      variable.source_id.trim(),
      variable.sheet.trim(),
      (variable.column ?? '').trim(),
    )
  singleDialogVisible.value = true
  await prepareSingleEditorForSource(variable.source_id, true)
}

function closeSingleEditorTab(): void {
  singleDialogVisible.value = false
}

function closeCompositeEditorTab(): void {
  compositeDialogVisible.value = false
}

function handleSingleDialogClosed(): void {
  singleEditingTag.value = null
  resetSingleDraft()
}

function handleCompositeDialogClosed(): void {
  compositeEditingTag.value = null
  resetCompositeDraft()
}

async function handleSingleSourceChange(value: string): Promise<void> {
  singleDraft.source_id = value
  singleDraft.sheet = ''
  singleDraft.column = ''
  clearSingleErrors()
  syncSingleTag()
  await prepareSingleEditorForSource(value, false)
}

function handleSingleSheetChange(value: string): void {
  singleDraft.sheet = value
  singleDraft.column = ''
  singleErrors.sheet = ''
  singleErrors.column = ''
  syncSingleTag()
}

function handleSingleColumnChange(value: string): void {
  singleDraft.column = value
  singleErrors.column = ''
  syncSingleTag()
}

function handleSingleTagInput(value: string): void {
  singleDraft.tag = value
  singleErrors.tag = ''
  singleTagTouched.value = true
}

async function handleCompositeSourceChange(value: string): Promise<void> {
  compositeDraft.source_id = value
  compositeDraft.sheet = ''
  compositeDraft.columns = []
  compositeDraft.key_column = ''
  clearCompositeErrors()
  syncCompositeTag()
  await prepareCompositeEditorForSource(value, false)
  await refreshCompositePreview()
}

async function handleCompositeSheetChange(value: string): Promise<void> {
  compositeDraft.sheet = value
  compositeDraft.columns = []
  compositeDraft.key_column = ''
  compositeDraft.append_index_to_key = false
  compositeErrors.sheet = ''
  compositeErrors.columns = ''
  compositeErrors.key_column = ''
  syncCompositeTag()
  await refreshCompositePreview()
}

async function handleCompositeColumnsChange(value: string[]): Promise<void> {
  compositeDraft.columns = [...new Set(value)]
  if (!compositeDraft.columns.includes(compositeDraft.key_column ?? '')) {
    compositeDraft.key_column = ''
    compositeDraft.append_index_to_key = false
  }
  compositeErrors.columns = ''
  compositeErrors.key_column = ''
  syncCompositeTag()
  await refreshCompositePreview()
}

async function handleCompositeKeyChange(value: string): Promise<void> {
  compositeDraft.key_column = value
  if (!value) compositeDraft.append_index_to_key = false
  compositeErrors.key_column = ''
  syncCompositeTag()
  await refreshCompositePreview()
}

async function handleCompositeAppendIndexChange(value: boolean): Promise<void> {
  compositeDraft.append_index_to_key = value
  await refreshCompositePreview()
}

function handleCompositeTagInput(value: string): void {
  compositeDraft.tag = value
  compositeErrors.tag = ''
  compositeTagTouched.value = true
}

function validateSingleDraft(): boolean {
  clearSingleErrors()
  if (!singleDraft.source_id.trim()) singleErrors.source_id = '请选择来源数据。'
  if (!singleDraft.sheet.trim()) singleErrors.sheet = '请选择 Sheet。'
  if (!singleDraft.column?.trim()) singleErrors.column = '请选择列名。'
  if (!singleDraft.tag.trim()) singleErrors.tag = '请输入变量标签。'
  if (
    singleDraft.tag.trim() &&
    store.variables.some(
      (item) => item.tag === singleDraft.tag.trim() && item.tag !== singleEditingTag.value,
    )
  ) {
    singleErrors.tag = '变量标签已存在，请保持唯一。'
  }
  if (!singleDraft.expected_type) singleErrors.expected_type = '请选择期望类型。'
  return !Object.values(singleErrors).some(Boolean)
}

function validateCompositeDraft(): boolean {
  clearCompositeErrors()
  if (!compositeDraft.source_id.trim()) compositeErrors.source_id = '请选择来源数据。'
  if (!compositeDraft.sheet.trim()) compositeErrors.sheet = '请选择 Sheet。'
  if ((compositeDraft.columns?.length ?? 0) < 2) compositeErrors.columns = '至少选择 2 列。'
  if (!compositeDraft.key_column?.trim()) compositeErrors.key_column = '请选择 key 列。'
  if (
    compositeDraft.key_column &&
    !compositeDraft.columns?.includes(compositeDraft.key_column)
  ) {
    compositeErrors.key_column = 'key 列必须来自已选关联列。'
  }
  if (!compositeDraft.tag.trim()) compositeErrors.tag = '请输入变量标签。'
  if (
    compositeDraft.tag.trim() &&
    store.variables.some(
      (item) => item.tag === compositeDraft.tag.trim() && item.tag !== compositeEditingTag.value,
    )
  ) {
    compositeErrors.tag = '变量标签已存在，请保持唯一。'
  }
  return !Object.values(compositeErrors).some(Boolean)
}

async function saveSingleVariable(): Promise<void> {
  if (!validateSingleDraft()) {
    ElMessage.warning('请先完整填写单个变量信息。')
    return
  }
  const nextTag = singleDraft.tag.trim()
  store.upsertVariable(
    {
      tag: nextTag,
      source_id: singleDraft.source_id.trim(),
      sheet: singleDraft.sheet,
      variable_kind: 'single',
      column: singleDraft.column,
      expected_type: singleDraft.expected_type ?? 'str',
    },
    singleEditingTag.value ?? undefined,
  )
  emit('saved', nextTag)
  emit('changed')
  closeSingleEditorTab()
  ElMessage.success(singleEditingTag.value ? '单个变量已更新。' : '单个变量已添加。')
}

async function saveCompositeVariable(): Promise<void> {
  if (!validateCompositeDraft()) {
    ElMessage.warning('请先完整填写组合变量信息。')
    return
  }
  await refreshCompositePreview()
  if (compositePreview.value?.has_duplicate_keys && !compositeDraft.append_index_to_key) {
    ElMessage.warning('当前 Key 列存在重复值，请先开启“Key 后追加序号”。')
    return
  }
  const nextTag = compositeDraft.tag.trim()
  store.upsertVariable(
    {
      tag: nextTag,
      source_id: compositeDraft.source_id.trim(),
      sheet: compositeDraft.sheet,
      variable_kind: 'composite',
      columns: [...(compositeDraft.columns ?? [])],
      key_column: compositeDraft.key_column,
      append_index_to_key: compositeDraft.append_index_to_key ?? false,
      expected_type: 'json',
    },
    compositeEditingTag.value ?? undefined,
  )
  emit('saved', nextTag)
  emit('changed')
  closeCompositeEditorTab()
  ElMessage.success(compositeEditingTag.value ? '组合变量已更新。' : '组合变量已添加。')
}

function removeVariable(tag: string): void {
  store.removeVariable(tag)
  emit('changed')
  if (detailDialogTag.value === tag) detailDialogVisible.value = false
  ElMessage.success('变量已移除。')
}

async function chooseTag(tag: string): Promise<void> {
  const variable = store.variables.find((item) => item.tag === tag)
  if (!variable) return
  detailDialogTag.value = variable.tag
  detailDialogVisible.value = true
  store.setActiveTag(variable.tag)
  detailLoading.value = true
  detailError.value = ''
  try {
    await store.loadVariablePreview(variable, undefined, true)
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : '读取变量详情失败。'
    ElMessage.error(detailError.value)
  } finally {
    detailLoading.value = false
  }
}

function handleDetailDialogClosed(): void {
  detailDialogTag.value = null
  detailError.value = ''
  detailLoading.value = false
}

function formatJsonPreview(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return '[无法格式化 JSON]'
  }
}

function getExpectedTypeLabel(value?: string | null): string {
  return EXPECTED_TYPE_OPTIONS.find((item) => item.value === value)?.label ?? '未指定'
}

function getVariableKindLabel(variable: VariableTag): string {
  return (variable.variable_kind ?? 'single') === 'composite' ? '组合变量 / JSON' : '单个变量'
}

function getVariableFieldSummary(variable: VariableTag): string {
  return (variable.variable_kind ?? 'single') === 'composite'
    ? `key: ${variable.key_column ?? '-'}${variable.append_index_to_key ? ' + _序号' : ''} / 列: ${(variable.columns ?? []).join('、')}`
    : variable.column ?? '-'
}

defineExpose({
  openSingleCreateTab,
  openCompositeCreateTab,
})
</script>

<template>
  <div class="variable-layout">
    <div class="variable-config-panel">
      <div v-if="toolbarMode === 'embedded'" class="workbench-section-toolbar">
        <div class="workbench-section-toolbar__actions">
          <button
            type="button"
            class="ec-btn ec-btn-primary ec-btn-sm"
            :disabled="!store.sources.length"
            @click="() => openSingleCreateTab()"
          >
            <Plus class="h-3.5 w-3.5" />
            添加单个变量
          </button>
          <button
            type="button"
            class="ec-btn ec-btn-primary ec-btn-sm"
            :disabled="!store.sources.length"
            @click="() => openCompositeCreateTab()"
          >
            <Plus class="h-3.5 w-3.5" />
            添加组合变量
          </button>
        </div>
      </div>

      <div class="variable-summary-panel">
        <el-table
          :data="store.variables"
          class="workbench-table"
        >
          <el-table-column label="变量标签" min-width="180">
            <template #default="{ row }">
              <button class="tag-button" type="button" @click="chooseTag(row.tag)">
                {{ row.tag }}
              </button>
            </template>
          </el-table-column>
          <el-table-column prop="source_id" label="来源" min-width="120" />
          <el-table-column prop="sheet" label="Sheet" min-width="120" />
          <el-table-column label="列名 / 类型" min-width="240">
            <template #default="{ row }">{{ getVariableFieldSummary(row) }}</template>
          </el-table-column>
          <el-table-column label="期望类型" min-width="120">
            <template #default="{ row }">{{ getExpectedTypeLabel(row.expected_type) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="210" align="left">
            <template #default="{ row }">
              <div class="table-actions">
                <button type="button" class="ec-action-link" @click="chooseTag(row.tag)">查看详情</button>
                <button type="button" class="ec-action-link" @click="openEditTab(row)">编辑</button>
                <button type="button" class="ec-action-link-danger" @click="removeVariable(row.tag)">删除</button>
              </div>
            </template>
          </el-table-column>
          <template #empty>
            <EmptyState
              variant="table"
              icon-tone="variable"
              title="暂无变量"
              description="请先添加单个变量或组合变量，用于规则编排与校验计算"
              :min-height="136"
            />
          </template>
        </el-table>
      </div>
    </div>
  </div>

  <el-dialog
    v-model="singleDialogVisible"
    :title="singleEditingTag ? '编辑单个变量' : '添加单个变量'"
    width="520px"
    destroy-on-close
    @closed="handleSingleDialogClosed"
  >
    <div class="flex flex-col gap-4">
      <div
        v-if="singleMetadataError"
        role="alert"
        class="rounded-card border border-line border-l-4 border-l-warning bg-warning-soft/40 px-4 py-2.5 text-[12px] text-ink-700"
      >
        {{ singleMetadataError }}
      </div>

      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">来源数据</label>
          <el-select
            :model-value="singleDraft.source_id"
            class="w-full"
            filterable
            placeholder="选择来源数据"
            @update:model-value="handleSingleSourceChange"
          >
            <el-option
              v-for="source in sourceOptions"
              :key="source.id"
              :label="source.id"
              :value="source.id"
            />
          </el-select>
          <div v-if="singleErrors.source_id" class="mt-1 text-[12px] text-danger">{{ singleErrors.source_id }}</div>
        </div>
        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">Sheet</label>
          <el-select
            :model-value="singleDraft.sheet"
            class="w-full"
            filterable
            placeholder="选择 Sheet"
            :loading="singleMetadataLoading"
            :disabled="!singleDraft.source_id || !singleSheetOptions.length"
            @update:model-value="handleSingleSheetChange"
          >
            <el-option
              v-for="sheet in singleSheetOptions"
              :key="sheet.name"
              :label="sheet.name"
              :value="sheet.name"
            />
          </el-select>
          <div v-if="singleErrors.sheet" class="mt-1 text-[12px] text-danger">{{ singleErrors.sheet }}</div>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">列名</label>
          <el-select
            :model-value="singleDraft.column"
            class="w-full"
            filterable
            placeholder="选择列名"
            :disabled="!singleDraft.sheet || !singleColumnOptions.length"
            @update:model-value="handleSingleColumnChange"
          >
            <el-option
              v-for="column in singleColumnOptions"
              :key="column"
              :label="column"
              :value="column"
            />
          </el-select>
          <div v-if="singleErrors.column" class="mt-1 text-[12px] text-danger">{{ singleErrors.column }}</div>
        </div>
        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">期望类型</label>
          <el-select
            v-model="singleDraft.expected_type"
            class="w-full"
            placeholder="选择期望类型"
          >
            <el-option
              v-for="option in EXPECTED_TYPE_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <div v-if="singleErrors.expected_type" class="mt-1 text-[12px] text-danger">{{ singleErrors.expected_type }}</div>
        </div>
      </div>

      <div>
        <label class="mb-1.5 block text-[12px] font-medium text-ink-500">变量标签</label>
        <el-input
          :model-value="singleDraft.tag"
          placeholder="[source-sheet-column]"
          @input="handleSingleTagInput"
        />
        <div
          v-if="singleErrors.tag"
          class="mt-1 text-[12px] text-danger"
        >{{ singleErrors.tag }}</div>
        <div
          v-else
          class="mt-1 text-[12px] text-ink-500"
        >默认按 <span class="font-mono">[来源-Sheet-列名]</span> 自动生成；改后不再覆盖</div>
      </div>
    </div>

    <template #footer>
      <div class="flex justify-end gap-2">
        <button
          type="button"
          class="ec-btn ec-btn-secondary"
          @click="closeSingleEditorTab"
        >
          取消
        </button>
        <button
          type="button"
          class="ec-btn ec-btn-primary"
          :disabled="!canSaveSingle"
          @click="saveSingleVariable"
        >
          保存变量
        </button>
      </div>
    </template>
  </el-dialog>

  <el-dialog
    v-model="compositeDialogVisible"
    :title="compositeDialogTitle"
    width="720px"
    destroy-on-close
    @closed="handleCompositeDialogClosed"
  >
      <div class="mb-4 text-[12px] text-ink-500">同一个数据源、同一 Sheet、至少 2 列；指定 1 列作为 Key</div>
      <div class="grid grid-cols-[1fr_280px] gap-6">
      <!-- 左侧：表单 -->
      <div class="flex flex-col gap-4">
        <div
          v-if="compositeMetadataError"
          role="alert"
          class="rounded-card border border-line border-l-4 border-l-warning bg-warning-soft/40 px-4 py-2.5 text-[12px] text-ink-700"
        >
          {{ compositeMetadataError }}
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="mb-1.5 block text-[12px] font-medium text-ink-500">来源数据</label>
            <el-select
              :model-value="compositeDraft.source_id"
              class="w-full"
              filterable
              placeholder="选择来源数据"
              @update:model-value="handleCompositeSourceChange"
            >
              <el-option
                v-for="source in sourceOptions"
                :key="source.id"
                :label="source.id"
                :value="source.id"
              />
            </el-select>
            <div v-if="compositeErrors.source_id" class="mt-1 text-[12px] text-danger">{{ compositeErrors.source_id }}</div>
          </div>
          <div>
            <label class="mb-1.5 block text-[12px] font-medium text-ink-500">Sheet</label>
            <el-select
              :model-value="compositeDraft.sheet"
              class="w-full"
              filterable
              placeholder="选择 Sheet"
              :loading="compositeMetadataLoading"
              :disabled="!compositeDraft.source_id || !compositeSheetOptions.length"
              @update:model-value="handleCompositeSheetChange"
            >
              <el-option
                v-for="sheet in compositeSheetOptions"
                :key="sheet.name"
                :label="sheet.name"
                :value="sheet.name"
              />
            </el-select>
            <div v-if="compositeErrors.sheet" class="mt-1 text-[12px] text-danger">{{ compositeErrors.sheet }}</div>
          </div>
        </div>

        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">关联列（至少 2 列）</label>
          <el-select
            :model-value="compositeDraft.columns"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            class="w-full"
            placeholder="至少选择 2 列"
            :disabled="!compositeDraft.sheet || !compositeColumnOptions.length"
            @update:model-value="handleCompositeColumnsChange"
          >
            <el-option
              v-for="column in compositeColumnOptions"
              :key="column"
              :label="column"
              :value="column"
            />
          </el-select>
          <div v-if="compositeErrors.columns" class="mt-1 text-[12px] text-danger">{{ compositeErrors.columns }}</div>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="mb-1.5 block text-[12px] font-medium text-ink-500">Key 列（从已选列指定）</label>
            <el-select
              :model-value="compositeDraft.key_column"
              class="w-full"
              placeholder="选择主键 Key 列"
              :disabled="!compositeKeyOptions.length"
              @update:model-value="handleCompositeKeyChange"
            >
              <el-option
                v-for="column in compositeKeyOptions"
                :key="column"
                :label="column"
                :value="column"
              />
            </el-select>
            <div v-if="compositeErrors.key_column" class="mt-1 text-[12px] text-danger">{{ compositeErrors.key_column }}</div>
            <label
              v-if="showAppendIndexCheckbox"
              class="mt-2 flex items-center gap-2 text-[12px] text-ink-600"
            >
              <el-checkbox
                :model-value="compositeDraft.append_index_to_key"
                @update:model-value="handleCompositeAppendIndexChange"
              />
              <span>Key 后追加序号</span>
            </label>
          </div>
          <div>
            <label class="mb-1.5 block text-[12px] font-medium text-ink-500">期望类型</label>
            <el-input model-value="JSON (固定)" disabled />
          </div>
        </div>

        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">变量标签</label>
          <el-input
            :model-value="compositeDraft.tag"
            placeholder="[source-sheet-key-mapping]"
            @input="handleCompositeTagInput"
          />
          <div v-if="compositeErrors.tag" class="mt-1 text-[12px] text-danger">{{ compositeErrors.tag }}</div>
        </div>
      </div>

      <!-- 右侧：JSON 预览 -->
      <div class="flex flex-col gap-2 min-w-0">
        <div class="text-[12px] font-medium text-ink-500">JSON 映射预览</div>

        <div
          v-if="compositePreviewError"
          role="alert"
          class="rounded-card border border-line border-l-4 border-l-warning bg-warning-soft/40 px-3 py-2 text-[12px] text-ink-700"
        >
          {{ compositePreviewError }}
        </div>

        <div
          v-else-if="compositePreviewLoading"
          class="flex-1 rounded-field border border-line bg-canvas px-3 py-6 text-center text-[12px] text-ink-500"
        >
          正在生成预览…
        </div>

        <div
          v-else-if="!compositePreview"
          class="flex-1 rounded-field border border-line bg-canvas px-3 py-6 text-center text-[12px] text-ink-500"
        >
          选择来源、Sheet、关联列和 Key 列后显示
        </div>

        <template v-else>
          <div class="rounded-field border border-line bg-card px-3 py-2 text-[12px] text-ink-500">
            <div>共 <strong class="font-mono text-ink-900">{{ compositePreview.total_rows }}</strong> 行 / <strong class="font-mono text-ink-900">{{ Object.keys(compositePreview.mapping).length }}</strong> 个 key</div>
            <div class="mt-0.5">Key 列：<span class="font-mono text-ink-700">{{ compositePreview.key_column }}</span></div>
            <div class="mt-0.5">Key 生成：<span class="font-mono text-ink-700">{{ compositeDraft.append_index_to_key ? `${compositePreview.key_column}_0` : compositePreview.key_column }}</span></div>
            <div
              v-if="compositePreview.has_duplicate_keys"
              class="mt-0.5 text-warning-ink"
            >当前 Key 列存在重复，可开启“Key 后追加序号”。</div>
          </div>
          <pre class="flex-1 rounded-field border border-line bg-canvas px-3 py-2 font-mono text-[11px] leading-[1.5] text-ink-700 whitespace-pre-wrap break-all overflow-auto max-h-[300px]">{{ formatJsonPreview(compositePreview.mapping) }}</pre>
          <div class="text-[11px] text-ink-500">外层 key 取 Key 列值{{ compositeDraft.append_index_to_key ? '并追加 _序号' : '' }}，内层对象保留其余列</div>
        </template>
      </div>
    </div>

    <template #footer>
      <div class="flex justify-end gap-2">
        <button
          type="button"
          class="ec-btn ec-btn-secondary"
          @click="closeCompositeEditorTab"
        >
          取消
        </button>
        <button
          type="button"
          class="ec-btn ec-btn-primary"
          :disabled="!canSaveComposite"
          @click="saveCompositeVariable"
        >
          保存变量
        </button>
      </div>
    </template>
  </el-dialog>

  <el-dialog
    v-model="detailDialogVisible"
    width="min(1200px, calc(100vw - 24px))"
    top="4vh"
    class="variable-detail-dialog"
    destroy-on-close
    @closed="handleDetailDialogClosed"
  >
    <template #header>
      <div class="detail-dialog-header">
        <strong>{{ detailVariable?.tag ?? '未命名变量' }}</strong>
        <p>查看来源、结构和预览。</p>
      </div>
    </template>

    <div v-if="detailVariable" class="detail-dialog-shell variable-detail-panel">
      <div class="detail-topbar">
        <div class="detail-copy">
          <strong>变量详情</strong>
          <span>单变量显示列预览，组合变量显示 JSON。</span>
        </div>
        <el-button plain @click="chooseTag(detailVariable.tag)">高亮变量</el-button>
      </div>
      <div class="detail-meta-grid" :class="{ 'detail-meta-grid--composite': detailPreview?.variable_kind === 'composite' }">
        <article class="detail-meta-item"><span>来源数据</span><strong>{{ detailVariable.source_id }}</strong></article>
        <article class="detail-meta-item"><span>Sheet</span><strong>{{ detailVariable.sheet }}</strong></article>
        <article class="detail-meta-item"><span>变量类型</span><strong>{{ getVariableKindLabel(detailVariable) }}</strong></article>
        <article class="detail-meta-item"><span>期望类型</span><strong>{{ getExpectedTypeLabel(detailVariable.expected_type) }}</strong></article>
      </div>
      <div class="preview-summary preview-source-summary">
        <span>来源路径</span>
        <strong class="source-path-text">{{ detailSourcePath || '当前没有可展示的来源路径。' }}</strong>
        <small>用于确认当前来源。</small>
      </div>
      <el-alert v-if="detailError" :title="detailError" type="warning" :closable="false" show-icon />
      <div v-else-if="detailLoading" class="empty-pool">正在加载变量详情，请稍候。</div>
      <template v-else>
        <div class="preview-summary">
          <span>预览数据</span>
          <strong>{{ detailVariable.tag }}</strong>
          <small>已加载 {{ detailLoadedRows }} / {{ detailPreview?.total_rows ?? 0 }} 行。</small>
        </div>
        <div v-if="detailPreview?.variable_kind === 'composite'" class="json-preview-shell">
          <div class="preview-summary">
            <span>字段结构</span>
            <strong>key: {{ detailPreview.key_column }}</strong>
            <small>关联列：{{ detailPreview.columns.join('、') }}{{ detailVariable?.append_index_to_key ? ' / Key: 原值_序号' : '' }}</small>
          </div>
          <pre class="json-preview-block detail-json-block">{{ formatJsonPreview(detailPreview.mapping) }}</pre>
        </div>
        <div v-else class="detail-table-shell">
          <el-table :data="detailPreview?.preview_rows ?? []" class="workbench-table preview-table" max-height="560" empty-text="当前没有可展示的预览数据。">
            <el-table-column prop="row_index" label="行号" width="120" />
            <el-table-column label="值" min-width="260">
              <template #default="{ row }"><span class="preview-value">{{ row.value ?? '空值' }}</span></template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </div>
  </el-dialog>
</template>
