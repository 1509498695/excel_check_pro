import type { DataSource, TaskTree, ValidationRule, VariableTag } from '../types/workbench'

function trimValue(value?: string | null): string {
  return value?.trim() ?? ''
}

function requireNonBlankPreservedValue(
  value: string | null | undefined,
  errorMessage: string,
): string {
  const rawValue = value ?? ''
  if (!rawValue.trim()) {
    throw new Error(errorMessage)
  }
  return rawValue
}

function createCleanObject<T extends Record<string, unknown>>(value: T): T {
  const entries = Object.entries(value).filter(([, item]) => item !== undefined && item !== '')
  return Object.fromEntries(entries) as T
}

function normalizeSource(source: DataSource): DataSource {
  const id = trimValue(source.id)
  const pathOrUrl = trimValue(source.pathOrUrl ?? source.path ?? source.url)
  const token = trimValue(source.token)

  if (!id) {
    throw new Error('步骤 1 中存在未填写的数据源标识。')
  }

  if (!pathOrUrl) {
    throw new Error(`数据源 "${id}" 缺少路径或链接。`)
  }

  if (source.type === 'feishu') {
    return createCleanObject({
      id,
      type: source.type,
      url: pathOrUrl,
      pathOrUrl,
      token: token || undefined,
    })
  }

  return createCleanObject({
    id,
    type: source.type,
    path: pathOrUrl,
    pathOrUrl,
    token: token || undefined,
  })
}

function normalizeVariable(variable: VariableTag, sourceIds: Set<string>): VariableTag {
  const tag = trimValue(variable.tag)
  const sourceId = trimValue(variable.source_id)
  const sheet = requireNonBlankPreservedValue(variable.sheet, `变量 "${tag}" 缺少 sheet。`)
  const variableKind = variable.variable_kind ?? 'single'
  const expectedType = variableKind === 'composite' ? 'json' : variable.expected_type ?? undefined

  if (!tag) {
    throw new Error('步骤 2 中存在未填写的变量标签。')
  }

  if (!sourceId) {
    throw new Error(`变量 "${tag}" 缺少 source_id。`)
  }

  if (!sourceIds.has(sourceId)) {
    throw new Error(`变量 "${tag}" 引用了不存在的数据源 "${sourceId}"。`)
  }

  if (variableKind === 'composite') {
    const columns = Array.isArray(variable.columns)
      ? [...new Set(variable.columns.filter((item): item is string => !!item && !!item.trim()))]
      : []
    const keyColumn = requireNonBlankPreservedValue(
      variable.key_column,
      `组合变量 "${tag}" 缺少 key_column。`,
    )

    if (columns.length < 2) {
      throw new Error(`组合变量 "${tag}" 至少需要选择 2 列。`)
    }

    if (!columns.includes(keyColumn)) {
      throw new Error(`组合变量 "${tag}" 的 key_column 必须包含在 columns 中。`)
    }

    return createCleanObject({
      tag,
      source_id: sourceId,
      sheet,
      variable_kind: 'composite' as const,
      columns,
      key_column: keyColumn,
      append_index_to_key: variable.append_index_to_key ?? undefined,
      expected_type: 'json' as const,
    })
  }

  const column = requireNonBlankPreservedValue(variable.column, `变量 "${tag}" 缺少 column。`)

  return createCleanObject({
    tag,
    source_id: sourceId,
    sheet,
    variable_kind: 'single' as const,
    column,
    expected_type: expectedType,
  })
}

function normalizeKnownRule(rule: ValidationRule, availableTags: Set<string>): ValidationRule {
  if (rule.rule_type === 'not_null' || rule.rule_type === 'unique') {
    const rawTags = rule.params.target_tags
    if (!Array.isArray(rawTags) || rawTags.length === 0) {
      throw new Error(`规则 "${rule.rule_type}" 需要至少选择一个目标变量。`)
    }

    const targetTags = rawTags
      .map((item) => (typeof item === 'string' ? item.trim() : ''))
      .filter(Boolean)

    if (targetTags.length === 0) {
      throw new Error(`规则 "${rule.rule_type}" 需要至少选择一个目标变量。`)
    }

    const unknownTag = targetTags.find((item) => !availableTags.has(item))
    if (unknownTag) {
      throw new Error(`规则 "${rule.rule_type}" 引用了不存在的变量 "${unknownTag}"。`)
    }

    const params: Record<string, unknown> = { target_tags: targetTags }
    const ruleName = rule.params.rule_name
    if (typeof ruleName === 'string' && ruleName.trim()) {
      params.rule_name = ruleName.trim()
    }
    const location = rule.params.location
    if (typeof location === 'string' && location.trim()) {
      params.location = location.trim()
    }

    return {
      rule_id: rule.rule_id,
      rule_type: rule.rule_type,
      params,
    }
  }

  if (rule.rule_type === 'fixed_value_compare') {
    const targetTag = typeof rule.params.target_tag === 'string' ? rule.params.target_tag.trim() : ''
    const operator = typeof rule.params.operator === 'string' ? rule.params.operator.trim() : ''
    const expectedValue =
      typeof rule.params.expected_value === 'string' ? rule.params.expected_value.trim() : ''
    const ruleName = typeof rule.params.rule_name === 'string' ? rule.params.rule_name.trim() : ''
    const location = typeof rule.params.location === 'string' ? rule.params.location.trim() : ''

    if (!targetTag) {
      throw new Error('规则 "fixed_value_compare" 缺少 target_tag。')
    }
    if (!availableTags.has(targetTag)) {
      throw new Error(`规则 "fixed_value_compare" 引用了不存在的变量 "${targetTag}"。`)
    }
    if (!['eq', 'ne', 'gt', 'lt'].includes(operator)) {
      throw new Error(`规则 "fixed_value_compare" 的 operator 无效。`)
    }
    if (!expectedValue) {
      throw new Error('规则 "fixed_value_compare" 缺少 expected_value。')
    }
    if ((operator === 'gt' || operator === 'lt') && Number.isNaN(Number(expectedValue))) {
      throw new Error('规则 "fixed_value_compare" 的大于/小于阈值必须是合法数字。')
    }
    if (!ruleName) {
      throw new Error('规则 "fixed_value_compare" 缺少 rule_name。')
    }

    return {
      rule_id: rule.rule_id,
      rule_type: rule.rule_type,
      params: {
        target_tag: targetTag,
        operator,
        expected_value: expectedValue,
        rule_name: ruleName,
        location: location || undefined,
      },
    }
  }

  if (rule.rule_type === 'regex_check') {
    const targetTag = typeof rule.params.target_tag === 'string' ? rule.params.target_tag.trim() : ''
    const pattern = typeof rule.params.pattern === 'string' ? rule.params.pattern.trim() : ''
    const ruleName = typeof rule.params.rule_name === 'string' ? rule.params.rule_name.trim() : ''
    const location = typeof rule.params.location === 'string' ? rule.params.location.trim() : ''

    if (!targetTag) {
      throw new Error('规则 "regex_check" 缺少 target_tag。')
    }
    if (!availableTags.has(targetTag)) {
      throw new Error(`规则 "regex_check" 引用了不存在的变量 "${targetTag}"。`)
    }
    if (!pattern) {
      throw new Error('规则 "regex_check" 缺少 pattern。')
    }
    if (!ruleName) {
      throw new Error('规则 "regex_check" 缺少 rule_name。')
    }

    return {
      rule_id: rule.rule_id,
      rule_type: rule.rule_type,
      params: createCleanObject({
        target_tag: targetTag,
        pattern,
        rule_name: ruleName,
        location: location || undefined,
      }),
    }
  }

  if (rule.rule_type === 'composite_condition_check') {
    const targetTag = typeof rule.params.target_tag === 'string' ? rule.params.target_tag.trim() : ''
    const ruleName = typeof rule.params.rule_name === 'string' ? rule.params.rule_name.trim() : ''
    const compositeConfig = rule.params.composite_config

    if (!targetTag) {
      throw new Error('规则 "composite_condition_check" 缺少 target_tag。')
    }
    if (!availableTags.has(targetTag)) {
      throw new Error(`规则 "composite_condition_check" 引用了不存在的变量 "${targetTag}"。`)
    }
    if (!ruleName) {
      throw new Error('规则 "composite_condition_check" 缺少 rule_name。')
    }
    if (compositeConfig == null || typeof compositeConfig !== 'object') {
      throw new Error('规则 "composite_condition_check" 缺少 composite_config。')
    }

    return {
      rule_id: rule.rule_id,
      rule_type: rule.rule_type,
      params: {
        target_tag: targetTag,
        rule_name: ruleName,
        composite_config: compositeConfig as Record<string, unknown>,
      },
    }
  }

  if (rule.rule_type === 'dual_composite_compare') {
    const targetTag = typeof rule.params.target_tag === 'string' ? rule.params.target_tag.trim() : ''
    const referenceTag =
      typeof rule.params.reference_tag === 'string' ? rule.params.reference_tag.trim() : ''
    const keyCheckMode =
      typeof rule.params.key_check_mode === 'string' ? rule.params.key_check_mode.trim() : ''
    const leftKeyField =
      typeof rule.params.left_key_field === 'string' && rule.params.left_key_field.trim()
        ? rule.params.left_key_field.trim()
        : '__key__'
    const rightKeyField =
      typeof rule.params.right_key_field === 'string' && rule.params.right_key_field.trim()
        ? rule.params.right_key_field.trim()
        : '__key__'
    const comparisons = Array.isArray(rule.params.comparisons) ? rule.params.comparisons : []
    const leftFilters = Array.isArray(rule.params.left_filters) ? rule.params.left_filters : []
    const rightFilters = Array.isArray(rule.params.right_filters) ? rule.params.right_filters : []
    const ruleName = typeof rule.params.rule_name === 'string' ? rule.params.rule_name.trim() : ''

    if (!targetTag) {
      throw new Error('规则 "dual_composite_compare" 缺少基准变量。')
    }
    if (!referenceTag) {
      throw new Error('规则 "dual_composite_compare" 缺少目标变量。')
    }
    if (!availableTags.has(targetTag)) {
      throw new Error(`规则 "dual_composite_compare" 引用了不存在的变量 "${targetTag}"。`)
    }
    if (!availableTags.has(referenceTag)) {
      throw new Error(`规则 "dual_composite_compare" 引用了不存在的变量 "${referenceTag}"。`)
    }
    if (!['baseline_only', 'bidirectional'].includes(keyCheckMode)) {
      throw new Error('规则 "dual_composite_compare" 的 key_check_mode 无效。')
    }
    if (!comparisons.length) {
      throw new Error('规则 "dual_composite_compare" 缺少字段比对规则。')
    }
    if (!ruleName) {
      throw new Error('规则 "dual_composite_compare" 缺少 rule_name。')
    }

    return {
      rule_id: rule.rule_id,
      rule_type: rule.rule_type,
      params: {
        target_tag: targetTag,
        reference_tag: referenceTag,
        key_check_mode: keyCheckMode,
        left_key_field: leftKeyField,
        right_key_field: rightKeyField,
        comparisons,
        left_filters: leftFilters,
        right_filters: rightFilters,
        rule_name: ruleName,
      },
    }
  }

  if (rule.rule_type === 'package_items_compare') {
    const referenceTag =
      typeof rule.params.reference_variable_tag === 'string'
        ? rule.params.reference_variable_tag.trim()
        : typeof rule.params.right_tag === 'string'
          ? rule.params.right_tag.trim()
          : ''
    const ruleName = typeof rule.params.rule_name === 'string' ? rule.params.rule_name.trim() : ''
    const rightPackageField =
      typeof rule.params.right_package_field === 'string'
        ? rule.params.right_package_field.trim()
        : ''
    const rightItemsField =
      typeof rule.params.right_items_field === 'string' ? rule.params.right_items_field.trim() : ''
    const leftPackageField =
      typeof rule.params.left_package_field === 'string'
        ? rule.params.left_package_field.trim()
        : '礼包id'
    const leftItemField =
      typeof rule.params.left_item_field === 'string' ? rule.params.left_item_field.trim() : '道具ID'
    const leftCountField =
      typeof rule.params.left_count_field === 'string' ? rule.params.left_count_field.trim() : '个数'
    const packageIdFilter =
      typeof rule.params.package_id_filter === 'string' ? rule.params.package_id_filter.trim() : ''
    const parseConfig =
      rule.params.package_parse_config != null && typeof rule.params.package_parse_config === 'object'
        ? (rule.params.package_parse_config as Record<string, unknown>)
        : null
    const feishuSourceId =
      typeof parseConfig?.feishu_source_id === 'string' ? parseConfig.feishu_source_id.trim() : ''
    const feishuSheetId =
      typeof parseConfig?.feishu_sheet_id === 'string' ? parseConfig.feishu_sheet_id.trim() : ''
    const feishuSheetName =
      typeof parseConfig?.feishu_sheet_name === 'string' ? parseConfig.feishu_sheet_name.trim() : ''
    const parseStrategy =
      typeof parseConfig?.parse_strategy === 'string' ? parseConfig.parse_strategy.trim() : 'auto'
    const aiParseMode =
      typeof parseConfig?.ai_parse_mode === 'string' ? parseConfig.ai_parse_mode.trim() : 'auto'
    const validationScope =
      typeof parseConfig?.validation_scope === 'string' ? parseConfig.validation_scope.trim() : 'all'
    const parseConfigPackageIdFilter =
      typeof parseConfig?.package_id_filter === 'string'
        ? parseConfig.package_id_filter.trim()
        : ''

    if (!referenceTag) {
      throw new Error('规则 "package_items_compare" 缺少礼包配置组合变量。')
    }
    if (!availableTags.has(referenceTag)) {
      throw new Error(`规则 "package_items_compare" 引用了不存在的变量 "${referenceTag}"。`)
    }
    if (!rightPackageField || !rightItemsField) {
      throw new Error('规则 "package_items_compare" 缺少右侧礼包字段配置。')
    }
    if (!leftPackageField || !leftItemField || !leftCountField) {
      throw new Error('规则 "package_items_compare" 缺少左侧礼包字段配置。')
    }
    if (!ruleName) {
      throw new Error('规则 "package_items_compare" 缺少 rule_name。')
    }
    if (!feishuSourceId || !feishuSheetId) {
      throw new Error('规则 "package_items_compare" 缺少飞书礼包规划解析配置。')
    }
    if (!['auto', 'rule', 'ai'].includes(parseStrategy)) {
      throw new Error('规则 "package_items_compare" 的 parse_strategy 无效。')
    }
    if (!['auto', 'enabled', 'disabled'].includes(aiParseMode)) {
      throw new Error('规则 "package_items_compare" 的 ai_parse_mode 无效。')
    }
    if (!['all', 'specified'].includes(validationScope)) {
      throw new Error('规则 "package_items_compare" 的 validation_scope 无效。')
    }
    if (validationScope === 'specified' && !parseConfigPackageIdFilter && !packageIdFilter) {
      throw new Error('规则 "package_items_compare" 缺少指定礼包 ID。')
    }

    const effectivePackageIdFilter =
      validationScope === 'specified' ? packageIdFilter || parseConfigPackageIdFilter : ''

    return {
      rule_id: rule.rule_id,
      rule_type: 'package_items_compare',
      params: createCleanObject({
        reference_variable_tag: referenceTag,
        right_package_field: rightPackageField,
        right_items_field: rightItemsField,
        left_package_field: leftPackageField,
        left_item_field: leftItemField,
        left_count_field: leftCountField,
        package_id_filter: effectivePackageIdFilter || undefined,
        rule_name: ruleName,
        display_field:
          typeof rule.params.display_field === 'string' && rule.params.display_field.trim()
            ? rule.params.display_field.trim()
            : undefined,
        package_parse_config: createCleanObject({
          feishu_source_id: feishuSourceId,
          feishu_sheet_id: feishuSheetId,
          feishu_sheet_name: feishuSheetName || undefined,
          parse_strategy: parseStrategy,
          ai_parse_mode: aiParseMode,
          validation_scope: validationScope,
          package_id_filter: effectivePackageIdFilter || undefined,
        }),
      }),
    }
  }

  if (rule.rule_type === 'event_task_reward' || rule.rule_type === 'event_task_validation') {
    const referenceTag =
      typeof rule.params.reference_variable_tag === 'string'
        ? rule.params.reference_variable_tag.trim()
        : typeof rule.params.right_tag === 'string'
          ? rule.params.right_tag.trim()
          : ''
    const ruleName = typeof rule.params.rule_name === 'string' ? rule.params.rule_name.trim() : ''
    const rightTaskGroupField =
      typeof rule.params.right_task_group_field === 'string'
        ? rule.params.right_task_group_field.trim()
        : 'INT_ID'
    const rightTaskIdField =
      typeof rule.params.right_task_id_field === 'string'
        ? rule.params.right_task_id_field.trim()
        : 'INT_TaskID'
    const rightTaskDescField =
      typeof rule.params.right_task_desc_field === 'string'
        ? rule.params.right_task_desc_field.trim()
        : 'STR_Desc'
    const rightTaskLootField =
      typeof rule.params.right_task_loot_field === 'string'
        ? rule.params.right_task_loot_field.trim()
        : 'STR_Loot'
    const leftTaskGroupField =
      typeof rule.params.left_task_group_field === 'string'
        ? rule.params.left_task_group_field.trim()
        : '任务组ID'
    const leftTaskIdField =
      typeof rule.params.left_task_id_field === 'string'
        ? rule.params.left_task_id_field.trim()
        : 'INT_TaskID'
    const leftTaskDescField =
      typeof rule.params.left_task_desc_field === 'string'
        ? rule.params.left_task_desc_field.trim()
        : '任务描述'
    const leftTaskLootField =
      typeof rule.params.left_task_loot_field === 'string'
        ? rule.params.left_task_loot_field.trim()
        : 'STR_Loot'
    const matchStrategy =
      typeof rule.params.event_task_match_strategy === 'string'
        ? rule.params.event_task_match_strategy.trim()
        : typeof rule.params.match_strategy === 'string'
          ? rule.params.match_strategy.trim()
          : 'groupId_desc_then_taskId'
    const aiAssistMode =
      typeof rule.params.ai_assist_mode === 'string' ? rule.params.ai_assist_mode.trim() : 'auto'
    const taskGroupIdFilter =
      typeof rule.params.task_group_id_filter === 'string'
        ? rule.params.task_group_id_filter.trim()
        : ''
    const parseConfig =
      rule.params.event_task_parse_config != null && typeof rule.params.event_task_parse_config === 'object'
        ? (rule.params.event_task_parse_config as Record<string, unknown>)
        : null
    const feishuSourceId =
      typeof parseConfig?.feishu_source_id === 'string' ? parseConfig.feishu_source_id.trim() : ''
    const feishuSheetId =
      typeof parseConfig?.feishu_sheet_id === 'string' ? parseConfig.feishu_sheet_id.trim() : ''
    const feishuSheetName =
      typeof parseConfig?.feishu_sheet_name === 'string' ? parseConfig.feishu_sheet_name.trim() : ''
    const parseStrategy =
      typeof parseConfig?.parse_strategy === 'string' ? parseConfig.parse_strategy.trim() : 'group_desc'
    const aiParseMode =
      typeof parseConfig?.ai_parse_mode === 'string' ? parseConfig.ai_parse_mode.trim() : 'auto'
    const validationScope =
      typeof parseConfig?.validation_scope === 'string' ? parseConfig.validation_scope.trim() : 'all'
    const parseConfigTaskGroupFilter =
      typeof parseConfig?.task_group_id_filter === 'string'
        ? parseConfig.task_group_id_filter.trim()
        : ''
    const keyDelimiter =
      typeof parseConfig?.key_delimiter === 'string' ? parseConfig.key_delimiter.trim() : '_'
    const fallbackMatchField =
      typeof parseConfig?.fallback_match_field === 'string'
        ? parseConfig.fallback_match_field.trim()
        : 'INT_TaskID'
    const eventTaskFieldMapping =
      parseConfig?.event_task_field_mapping != null &&
      typeof parseConfig.event_task_field_mapping === 'object'
        ? JSON.parse(JSON.stringify(parseConfig.event_task_field_mapping))
        : undefined

    if (!referenceTag) {
      throw new Error(`规则 "${rule.rule_type}" 缺少 EventTask 配置组合变量。`)
    }
    if (!availableTags.has(referenceTag)) {
      throw new Error(`规则 "${rule.rule_type}" 引用了不存在的变量 "${referenceTag}"。`)
    }
    if (!rightTaskGroupField || !rightTaskIdField || !rightTaskDescField || !rightTaskLootField) {
      throw new Error(`规则 "${rule.rule_type}" 缺少右侧 EventTask 字段配置。`)
    }
    if (!leftTaskGroupField || !leftTaskIdField || !leftTaskDescField || !leftTaskLootField) {
      throw new Error(`规则 "${rule.rule_type}" 缺少左侧节日任务字段配置。`)
    }
    if (!ruleName) {
      throw new Error(`规则 "${rule.rule_type}" 缺少 rule_name。`)
    }
    if (!feishuSourceId || !feishuSheetId) {
      throw new Error(`规则 "${rule.rule_type}" 缺少飞书节日任务解析配置。`)
    }
    if (!['group_desc'].includes(parseStrategy)) {
      throw new Error(`规则 "${rule.rule_type}" 的 parse_strategy 无效。`)
    }
    if (!['auto', 'enabled', 'disabled'].includes(aiParseMode)) {
      throw new Error(`规则 "${rule.rule_type}" 的 ai_parse_mode 无效。`)
    }
    if (!['auto', 'on', 'off'].includes(aiAssistMode)) {
      throw new Error(`规则 "${rule.rule_type}" 的 ai_assist_mode 无效。`)
    }
    if (
      !['groupId_desc', 'groupId_taskId', 'groupId_desc_then_taskId'].includes(matchStrategy)
    ) {
      throw new Error(`规则 "${rule.rule_type}" 的 match_strategy 无效。`)
    }
    if (!['all', 'specified'].includes(validationScope)) {
      throw new Error(`规则 "${rule.rule_type}" 的 validation_scope 无效。`)
    }
    if (validationScope === 'specified' && !parseConfigTaskGroupFilter && !taskGroupIdFilter) {
      throw new Error(`规则 "${rule.rule_type}" 缺少指定任务组 ID。`)
    }

    const effectiveTaskGroupFilter =
      validationScope === 'specified' ? taskGroupIdFilter || parseConfigTaskGroupFilter : ''

    return {
      rule_id: rule.rule_id,
      rule_type: rule.rule_type,
      params: createCleanObject({
        reference_variable_tag: referenceTag,
        right_task_group_field: rightTaskGroupField,
        right_task_id_field: rightTaskIdField,
        right_task_desc_field: rightTaskDescField,
        right_task_loot_field: rightTaskLootField,
        left_task_group_field: leftTaskGroupField,
        left_task_id_field: leftTaskIdField,
        left_task_desc_field: leftTaskDescField,
        left_task_loot_field: leftTaskLootField,
        event_task_match_strategy: matchStrategy,
        match_strategy: matchStrategy,
        ai_assist_mode: aiAssistMode,
        task_group_id_filter: effectiveTaskGroupFilter || undefined,
        rule_name: ruleName,
        display_field:
          typeof rule.params.display_field === 'string' && rule.params.display_field.trim()
            ? rule.params.display_field.trim()
            : undefined,
        event_task_parse_config: createCleanObject({
          feishu_source_id: feishuSourceId,
          feishu_sheet_id: feishuSheetId,
          feishu_sheet_name: feishuSheetName || undefined,
          parse_strategy: parseStrategy,
          ai_parse_mode: aiParseMode,
          validation_scope: validationScope,
          task_group_id_filter: effectiveTaskGroupFilter || undefined,
          key_delimiter: keyDelimiter || '_',
          fallback_match_field: fallbackMatchField || 'INT_TaskID',
          event_task_field_mapping: eventTaskFieldMapping,
        }),
      }),
    }
  }

  if (rule.rule_type === 'multi_composite_pipeline_check') {
    const targetTag = typeof rule.params.target_tag === 'string' ? rule.params.target_tag.trim() : ''
    const ruleName = typeof rule.params.rule_name === 'string' ? rule.params.rule_name.trim() : ''
    const pipelineConfig = rule.params.pipeline_config

    if (!targetTag) {
      throw new Error('规则 "multi_composite_pipeline_check" 缺少目标变量。')
    }
    if (!availableTags.has(targetTag)) {
      throw new Error(`规则 "multi_composite_pipeline_check" 引用了不存在的变量 "${targetTag}"。`)
    }
    if (!ruleName) {
      throw new Error('规则 "multi_composite_pipeline_check" 缺少 rule_name。')
    }
    if (pipelineConfig == null || typeof pipelineConfig !== 'object') {
      throw new Error('规则 "multi_composite_pipeline_check" 缺少 pipeline_config。')
    }

    return {
      rule_id: rule.rule_id,
      rule_type: rule.rule_type,
      params: {
        target_tag: targetTag,
        rule_name: ruleName,
        pipeline_config: pipelineConfig as Record<string, unknown>,
      },
    }
  }

  if (rule.rule_type === 'cross_table_mapping') {
    const dictTag = typeof rule.params.dict_tag === 'string' ? rule.params.dict_tag.trim() : ''
    const targetTag =
      typeof rule.params.target_tag === 'string' ? rule.params.target_tag.trim() : ''
    const ruleName = typeof rule.params.rule_name === 'string' ? rule.params.rule_name.trim() : ''
    const location = typeof rule.params.location === 'string' ? rule.params.location.trim() : ''

    if (!dictTag) {
      throw new Error('规则 "cross_table_mapping" 缺少字典变量。')
    }

    if (!targetTag) {
      throw new Error('规则 "cross_table_mapping" 缺少目标变量。')
    }

    if (!availableTags.has(dictTag)) {
      throw new Error(`规则 "cross_table_mapping" 引用了不存在的变量 "${dictTag}"。`)
    }

    if (!availableTags.has(targetTag)) {
      throw new Error(`规则 "cross_table_mapping" 引用了不存在的变量 "${targetTag}"。`)
    }

    return {
      rule_id: rule.rule_id,
      rule_type: rule.rule_type,
      params: createCleanObject({
        dict_tag: dictTag,
        target_tag: targetTag,
        rule_name: ruleName || undefined,
        location: location || undefined,
      }),
    }
  }

  return rule
}

export function buildTaskTreePayload(
  sources: DataSource[],
  variables: VariableTag[],
  rules: ValidationRule[],
  selectedRuleIds?: string[],
  page?: number,
  size?: number,
): TaskTree {
  const normalizedSources = sources.map(normalizeSource)
  const sourceIds = new Set<string>()

  normalizedSources.forEach((source) => {
    if (sourceIds.has(source.id)) {
      throw new Error(`数据源标识 "${source.id}" 重复，请保持唯一。`)
    }
    sourceIds.add(source.id)
  })

  const normalizedVariables = variables.map((variable) => normalizeVariable(variable, sourceIds))
  const variableTags = new Set<string>()

  normalizedVariables.forEach((variable) => {
    if (variableTags.has(variable.tag)) {
      throw new Error(`变量标签 "${variable.tag}" 重复，请保持唯一。`)
    }
    variableTags.add(variable.tag)
  })

  const normalizedRules = rules
    .filter((rule) => rule.mode !== 'dynamic')
    .map((rule) => normalizeKnownRule(rule, variableTags))

  const payload: TaskTree = {
    sources: normalizedSources,
    variables: normalizedVariables,
    rules: normalizedRules,
  }

  if (selectedRuleIds) {
    const normalizedSelectedRuleIds = [...new Set(selectedRuleIds.map(trimValue).filter(Boolean))]
    payload.selected_rule_ids = normalizedSelectedRuleIds
  }

  if (page) {
    payload.page = page
  }

  if (size) {
    payload.size = size
  }

  return payload
}

export function createRuleId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}
