import type {
  DataSource,
  SourceMetadata,
  SourceType,
  VariablePreviewData,
  VariableTag,
} from './workbench'
import type { SourcePathReplacementGroup } from '../utils/sourcePathReplacement'

export interface SourceManagementStoreLike {
  sources: DataSource[]
  capabilities: SourceType[]
  preferredSourceId: string | null
  sourceMetadataMap?: Record<string, SourceMetadata>
  svnPathReplacementPresets?: string[]
  selectedSvnPathReplacementPreset?: string | null
  loadSourceMetadata?(sourceId: string, forceRefresh?: boolean): Promise<SourceMetadata>
  upsertSource(source: DataSource, originalId?: string): void
  removeSource(sourceId: string): void
  useSampleSource(): void
}

export interface VariablePoolStoreLike extends SourceManagementStoreLike {
  variables: VariableTag[]
  activeTag: string | null
  sourceMetadataMap: Record<string, SourceMetadata>
  variablePreviewMap: Record<string, VariablePreviewData>
  setActiveTag(tag: string | null): void
  loadSourceMetadata(sourceId: string, forceRefresh?: boolean): Promise<SourceMetadata>
  loadVariablePreview(
    variable: VariableTag,
    limit?: number,
    forceRefresh?: boolean,
  ): Promise<VariablePreviewData>
  upsertVariable(variable: VariableTag, originalTag?: string): void
  removeVariable(tag: string): void
}

export interface SourcePathReplacementResult {
  updatedCount: number
  skippedCount: number
  failedCount: number
  affectedSourceIds: string[]
}

export interface SourcePathReplacementStoreLike extends SourceManagementStoreLike {
  variables: VariableTag[]
  activeTag: string | null
  localPathReplacementPresets: string[]
  selectedLocalPathReplacementPreset: string | null
  svnPathReplacementPresets: string[]
  selectedSvnPathReplacementPreset: string | null
  saveConfigNow(): Promise<void>
  setSelectedPathReplacementPreset(group: SourcePathReplacementGroup, path: string | null): void
  addPathReplacementPreset(group: SourcePathReplacementGroup, path: string): void
  updatePathReplacementPreset(
    group: SourcePathReplacementGroup,
    originalPath: string,
    nextPath: string,
  ): void
  removePathReplacementPreset(group: SourcePathReplacementGroup, path: string): void
  replaceSourceBasePath(
    group: SourcePathReplacementGroup,
    baseDirectory: string,
  ): Promise<SourcePathReplacementResult>
}
