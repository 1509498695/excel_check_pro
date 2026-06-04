import type { WorkbenchState } from './state'
import { fetchColumnPreview, fetchCompositePreview, fetchSourceMetadata } from '../../api/workbench'
import { COMPOSITE_PREVIEW_PAGE_SIZE, type VariablePreviewLoadOptions } from './variableActions'
import type { DataSource } from '../../types/workbench'
import type { SourcePathReplacementGroup } from '../../utils/sourcePathReplacement'
import {
  extractSourceBasename,
  getSourceLocator,
  isAffectedVariable,
  isLocalPathManagedSource,
  isSvnPathManagedSource,
  joinDirectoryAndBasename,
  joinSvnDirectoryAndBasename,
  normalizeReplacementPreset,
} from '../../utils/sourcePathReplacement'

export function getPresetListByGroup(
  state: Pick<
    WorkbenchState,
    | 'localPathReplacementPresets'
    | 'selectedLocalPathReplacementPreset'
    | 'svnPathReplacementPresets'
    | 'selectedSvnPathReplacementPreset'
  >,
  group: SourcePathReplacementGroup,
): string[] {
  return group === 'svn' ? state.svnPathReplacementPresets : state.localPathReplacementPresets
}

export function setPresetListByGroup(
  state: WorkbenchState,
  group: SourcePathReplacementGroup,
  presets: string[],
): void {
  if (group === 'svn') {
    state.svnPathReplacementPresets = presets
    return
  }
  state.localPathReplacementPresets = presets
}

export function getSelectedPresetByGroup(
  state: Pick<
    WorkbenchState,
    | 'selectedLocalPathReplacementPreset'
    | 'selectedSvnPathReplacementPreset'
  >,
  group: SourcePathReplacementGroup,
): string | null {
  return group === 'svn'
    ? state.selectedSvnPathReplacementPreset
    : state.selectedLocalPathReplacementPreset
}

export function setSelectedPresetByGroup(
  state: WorkbenchState,
  group: SourcePathReplacementGroup,
  selectedPreset: string | null,
): void {
  if (group === 'svn') {
    state.selectedSvnPathReplacementPreset = selectedPreset
    return
  }
  state.selectedLocalPathReplacementPreset = selectedPreset
}

type WorkbenchPathReplacementContext = WorkbenchState & {
  upsertSource(source: DataSource, originalId?: string): void
  addPathReplacementPreset(group: SourcePathReplacementGroup, path: string): void
  setSelectedPathReplacementPreset(group: SourcePathReplacementGroup, path: string | null): void
  saveConfigNow(): Promise<void>
  loadSourceMetadata(sourceId: string, forceRefresh?: boolean): Promise<unknown>
  loadVariablePreview(
    variable: any,
    options?: number | VariablePreviewLoadOptions,
    force?: boolean,
  ): Promise<unknown>
  clearExecutionResult(): void
  clearPageError(): void
}

export async function replaceSourceBasePathAction(
  state: WorkbenchPathReplacementContext,
  group: SourcePathReplacementGroup,
  baseDirectory: string,
): Promise<{
  updatedCount: number
  skippedCount: number
  failedCount: number
  affectedSourceIds: string[]
}> {
  const normalizedBaseDirectory = normalizeReplacementPreset(baseDirectory, group)
  const candidateSources: Array<{
    sourceId: string
    source: DataSource
    nextSource: DataSource
    nextPath: string
  }> = []
  const affectedSourceIds = new Set<string>()
  let updatedCount = 0
  let skippedCount = 0

  state.sources.slice().forEach((source) => {
    const isManagedSource =
      group === 'svn' ? isSvnPathManagedSource(source) : isLocalPathManagedSource(source)
    if (!isManagedSource) {
      skippedCount += 1
      return
    }

    const currentLocator = getSourceLocator(source)
    const basename = extractSourceBasename(currentLocator)
    if (!basename) {
      skippedCount += 1
      return
    }

    const nextPath =
      group === 'svn'
        ? joinSvnDirectoryAndBasename(normalizedBaseDirectory, basename)
        : joinDirectoryAndBasename(normalizedBaseDirectory, basename)
    candidateSources.push({
      sourceId: source.id,
      source,
      nextSource: {
        ...source,
        path: group === 'svn' ? undefined : nextPath,
        url: group === 'svn' ? nextPath : source.url,
        pathOrUrl: nextPath,
      },
      nextPath,
    })
  })

  if (!candidateSources.length) {
    return {
      updatedCount,
      skippedCount,
      failedCount: 0,
      affectedSourceIds: [],
    }
  }

  const validationFailures: string[] = []
  const metadataValidatedSourceIds = new Set<string>()
  for (const candidate of candidateSources) {
    try {
      await fetchSourceMetadata(candidate.nextSource)
      metadataValidatedSourceIds.add(candidate.sourceId)
    } catch (error) {
      const reason = error instanceof Error ? error.message : '读取数据源元数据失败。'
      validationFailures.push(`- ${candidate.sourceId} -> ${candidate.nextPath}：${reason}`)
    }
  }

  for (const candidate of candidateSources) {
    if (!metadataValidatedSourceIds.has(candidate.sourceId)) {
      continue
    }
    const affectedVariables = state.variables.filter(
      (variable) => variable.source_id === candidate.sourceId,
    )

    for (const variable of affectedVariables) {
      const isComposite = (variable.variable_kind ?? 'single') === 'composite'
      try {
        if (isComposite) {
          await fetchCompositePreview({
            source: candidate.nextSource,
            sheet: variable.sheet,
            columns: variable.columns ?? [],
            key_column: variable.key_column ?? '',
            append_index_to_key: variable.append_index_to_key ?? false,
            page: 1,
            size: COMPOSITE_PREVIEW_PAGE_SIZE,
          })
        } else {
          await fetchColumnPreview({
            source: candidate.nextSource,
            sheet: variable.sheet,
            column: variable.column ?? '',
          })
        }
      } catch (error) {
        const reason = error instanceof Error ? error.message : '变量预览校验失败。'
        validationFailures.push(`- ${candidate.sourceId} / ${variable.tag}：${reason}`)
      }
    }
  }

  if (validationFailures.length) {
    throw new Error(
      [
        `以下${group === 'svn' ? 'SVN 路径' : '本地路径'}替换失败，本次未生效：`,
        ...validationFailures,
      ].join('\n'),
    )
  }

  candidateSources.forEach((candidate) => {
    state.upsertSource(candidate.nextSource, candidate.sourceId)
    delete state.sourceIssues[candidate.sourceId]
    affectedSourceIds.add(candidate.sourceId)
    updatedCount += 1
  })

  state.addPathReplacementPreset(group, normalizedBaseDirectory)
  state.setSelectedPathReplacementPreset(group, normalizedBaseDirectory)
  await state.saveConfigNow()

  let failedCount = 0
  for (const sourceId of affectedSourceIds) {
    try {
      await state.loadSourceMetadata(sourceId)
      delete state.sourceIssues[sourceId]
    } catch (error) {
      failedCount += 1
      state.sourceIssues[sourceId] =
        error instanceof Error ? error.message : '刷新数据源元数据失败。'
    }
  }

  state.clearExecutionResult()
  state.clearPageError()

  const activeVariable = state.variables.find((variable) => variable.tag === state.activeTag)
  if (isAffectedVariable(activeVariable, affectedSourceIds)) {
    try {
      await state.loadVariablePreview(activeVariable, undefined, true)
    } catch {
      // 变量预览失败时保留数据源级提示即可，避免重复打断页面交互。
    }
  }

  return {
    updatedCount,
    skippedCount,
    failedCount,
    affectedSourceIds: [...affectedSourceIds],
  }
}
