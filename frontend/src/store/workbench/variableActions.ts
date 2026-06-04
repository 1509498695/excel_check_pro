import type { VariablePreviewData, VariableTag } from '../../types/workbench'

export const COMPOSITE_PREVIEW_PAGE_SIZE = 20

export interface VariablePreviewLoadOptions {
  limit?: number
  page?: number
  size?: number
}

export function normalizeStoredVariable(variable: VariableTag): VariableTag {
  return {
    ...variable,
    append_index_to_key: variable.append_index_to_key ?? false,
  }
}

export function normalizeVariablePreviewOptions(
  options?: number | VariablePreviewLoadOptions,
): VariablePreviewLoadOptions {
  if (typeof options === 'number') {
    return { limit: options }
  }
  return {
    limit: options?.limit,
    page: options?.page,
    size: options?.size,
  }
}

export function getCompositePreviewPageOptions(
  options: VariablePreviewLoadOptions,
): { page: number; size: number } {
  return {
    page: Math.max(1, options.page ?? 1),
    size: Math.max(1, options.size ?? COMPOSITE_PREVIEW_PAGE_SIZE),
  }
}

export function variablePreviewMatchesRequest(
  preview: VariablePreviewData,
  variable: VariableTag,
  options: VariablePreviewLoadOptions,
): boolean {
  if ((variable.variable_kind ?? 'single') === 'composite') {
    if (preview.variable_kind !== 'composite') return false
    const pageOptions = getCompositePreviewPageOptions(options)
    return (
      preview.source_id === variable.source_id &&
      preview.sheet === variable.sheet &&
      preview.key_column === (variable.key_column ?? '') &&
      (preview.append_index_to_key ?? false) === (variable.append_index_to_key ?? false) &&
      preview.page === pageOptions.page &&
      preview.page_size === pageOptions.size &&
      sameStringList(preview.columns, variable.columns ?? [])
    )
  }

  if (preview.variable_kind !== 'single') return false
  const wantsAllRows = options.limit === undefined || options.limit === null
  const cachedLoadsAllRows =
    preview.loaded_all_rows ?? preview.preview_rows.length === preview.total_rows
  const cachedMatchesLimit = preview.preview_limit === options.limit
  return (wantsAllRows && cachedLoadsAllRows) || (!wantsAllRows && cachedMatchesLimit)
}

function sameStringList(left: string[], right: string[]): boolean {
  if (left.length !== right.length) return false
  return left.every((item, index) => item === right[index])
}
