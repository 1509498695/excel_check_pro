// @vitest-environment happy-dom

import { mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  cancelGenerationRun,
  createLocalFileSourceEvidenceRun,
  createGenerationRun,
  createSourceEvidenceRun,
  createReferenceCategory,
  deleteReferenceFile,
  downloadGenerationRunArtifact,
  exportGenerationRunWorkbook,
  fetchGenerationRunArtifactText,
  exportTestCaseWorkbook,
  fetchSourceEvidenceCapabilities,
  fetchSourceEvidenceResources,
  fetchSourceEvidenceVisualCandidates,
  fetchSourceEvidenceObservations,
  fetchReferenceCategories,
  fetchReferenceFiles,
  fetchSourceEvidenceRun,
  generateTestCases,
  getGenerationRun,
  listGenerationRunAtoms,
  listGenerationRunArtifacts,
  listGenerationRunCases,
  observeSourceEvidenceRun,
  readPlanningSnapshot,
  readPlanningSnapshotBrief,
  readSourceEvidenceSnapshot,
  requestSourceEvidenceAuthorization,
  revokeSourceEvidenceVisualEvidence,
  retryFailedGenerationChunks,
  retryGenerationRunArtifacts,
  retrySourceEvidenceRun,
  adoptSourceEvidenceVisualEvidence,
  saveSourceEvidenceVisualSelections,
  setRecommendedPrimaryReference,
  uploadReferenceFile,
} from '../../src/api/testCases'
import { fetchSvnCredential, listSvnCredentialHosts, listSvnDirectory, SvnApiError } from '../../src/api/svn'
import { fetchSourceMetadata, fetchWorkbenchConfig, saveWorkbenchConfig, uploadSourceFile } from '../../src/api/workbench'
import type { DataSource } from '../../src/types/workbench'
import TestCaseGeneratorView from '../../src/views/TestCaseGeneratorView.vue'

vi.mock('../../src/api/testCases', () => ({
  cancelGenerationRun: vi.fn(),
  createLocalFileSourceEvidenceRun: vi.fn(),
  createGenerationRun: vi.fn(),
  createSourceEvidenceRun: vi.fn(),
  createReferenceCategory: vi.fn(),
  deleteReferenceFile: vi.fn(),
  downloadGenerationRunArtifact: vi.fn(),
  exportGenerationRunWorkbook: vi.fn(),
  fetchGenerationRunArtifactText: vi.fn(),
  exportTestCaseWorkbook: vi.fn(),
  fetchSourceEvidenceCapabilities: vi.fn(),
  fetchSourceEvidenceResources: vi.fn(),
  fetchSourceEvidenceVisualCandidates: vi.fn(),
  fetchSourceEvidenceObservations: vi.fn(),
  fetchReferenceCategories: vi.fn(),
  fetchReferenceFiles: vi.fn(),
  fetchSourceEvidenceRun: vi.fn(),
  generateTestCases: vi.fn(),
  getGenerationRun: vi.fn(),
  listGenerationRunAtoms: vi.fn(),
  listGenerationRunArtifacts: vi.fn(),
  listGenerationRunCases: vi.fn(),
  observeSourceEvidenceRun: vi.fn(),
  readPlanningSnapshot: vi.fn(),
  readPlanningSnapshotBrief: vi.fn(),
  readSourceEvidenceSnapshot: vi.fn(),
  requestSourceEvidenceAuthorization: vi.fn(),
  revokeSourceEvidenceVisualEvidence: vi.fn(),
  retryFailedGenerationChunks: vi.fn(),
  retryGenerationRunArtifacts: vi.fn(),
  retrySourceEvidenceRun: vi.fn(),
  adoptSourceEvidenceVisualEvidence: vi.fn(),
  saveSourceEvidenceVisualSelections: vi.fn(),
  setRecommendedPrimaryReference: vi.fn(),
  uploadReferenceFile: vi.fn(),
}))

vi.mock('../../src/api/workbench', () => ({
  checkFeishuSourcePermission: vi.fn(),
  fetchWorkbenchConfig: vi.fn(),
  fetchSourceMetadata: vi.fn(),
  pickLocalSourcePath: vi.fn(),
  saveWorkbenchConfig: vi.fn(),
  sendFeishuSourceAuthorizationCard: vi.fn(),
  uploadSourceFile: vi.fn(),
}))

vi.mock('../../src/api/svn', () => {
  class MockSvnApiError extends Error {
    status: number
    category: string

    constructor(message: string, status: number, category: string) {
      super(message)
      this.name = 'SvnApiError'
      this.status = status
      this.category = category
    }
  }

  return {
    SvnApiError: MockSvnApiError,
    ensureTrailingSlash: (input: string) => {
      const trimmed = input.trim()
      return trimmed && !trimmed.endsWith('/') ? `${trimmed}/` : trimmed
    },
    fetchSvnCredential: vi.fn(),
    getDefaultSvnCredentialTestDirUrl: vi.fn((host: string) =>
      host === 'samosvn' ? 'https://samosvn/data/project/samo/GameDatas/' : '',
    ),
    isHttpDirUrl: (input: string) => /^https?:\/\/[^\s]+/i.test(input.trim()),
    listSvnCredentialHosts: vi.fn(),
    listSvnDirectory: vi.fn(),
    parseSvnHost: (input: string) => {
      try {
        return new URL(input.trim()).hostname.toLowerCase()
      } catch {
        return ''
      }
    },
  }
})

vi.mock('element-plus', () => ({
  ElMessage: {
    error: vi.fn(),
    info: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

const readPlanningSnapshotMock = vi.mocked(readPlanningSnapshot)
const readPlanningSnapshotBriefMock = vi.mocked(readPlanningSnapshotBrief)
const createLocalFileSourceEvidenceRunMock = vi.mocked(createLocalFileSourceEvidenceRun)
const createSourceEvidenceRunMock = vi.mocked(createSourceEvidenceRun)
const fetchSourceEvidenceRunMock = vi.mocked(fetchSourceEvidenceRun)
const fetchSourceEvidenceResourcesMock = vi.mocked(fetchSourceEvidenceResources)
const fetchSourceEvidenceVisualCandidatesMock = vi.mocked(fetchSourceEvidenceVisualCandidates)
const fetchSourceEvidenceObservationsMock = vi.mocked(fetchSourceEvidenceObservations)
const readSourceEvidenceSnapshotMock = vi.mocked(readSourceEvidenceSnapshot)
const requestSourceEvidenceAuthorizationMock = vi.mocked(requestSourceEvidenceAuthorization)
const observeSourceEvidenceRunMock = vi.mocked(observeSourceEvidenceRun)
const retrySourceEvidenceRunMock = vi.mocked(retrySourceEvidenceRun)
const adoptSourceEvidenceVisualEvidenceMock = vi.mocked(adoptSourceEvidenceVisualEvidence)
const revokeSourceEvidenceVisualEvidenceMock = vi.mocked(revokeSourceEvidenceVisualEvidence)
const saveSourceEvidenceVisualSelectionsMock = vi.mocked(saveSourceEvidenceVisualSelections)
const createGenerationRunMock = vi.mocked(createGenerationRun)
const getGenerationRunMock = vi.mocked(getGenerationRun)
const cancelGenerationRunMock = vi.mocked(cancelGenerationRun)
const retryFailedGenerationChunksMock = vi.mocked(retryFailedGenerationChunks)
const listGenerationRunAtomsMock = vi.mocked(listGenerationRunAtoms)
const listGenerationRunCasesMock = vi.mocked(listGenerationRunCases)
const listGenerationRunArtifactsMock = vi.mocked(listGenerationRunArtifacts)
const downloadGenerationRunArtifactMock = vi.mocked(downloadGenerationRunArtifact)
const fetchGenerationRunArtifactTextMock = vi.mocked(fetchGenerationRunArtifactText)
const retryGenerationRunArtifactsMock = vi.mocked(retryGenerationRunArtifacts)
const exportGenerationRunWorkbookMock = vi.mocked(exportGenerationRunWorkbook)
const generateTestCasesMock = vi.mocked(generateTestCases)
const exportTestCaseWorkbookMock = vi.mocked(exportTestCaseWorkbook)
const fetchSourceEvidenceCapabilitiesMock = vi.mocked(fetchSourceEvidenceCapabilities)
const fetchReferenceCategoriesMock = vi.mocked(fetchReferenceCategories)
const fetchReferenceFilesMock = vi.mocked(fetchReferenceFiles)
const createReferenceCategoryMock = vi.mocked(createReferenceCategory)
const uploadReferenceFileMock = vi.mocked(uploadReferenceFile)
const setRecommendedPrimaryReferenceMock = vi.mocked(setRecommendedPrimaryReference)
const deleteReferenceFileMock = vi.mocked(deleteReferenceFile)
const fetchSourceMetadataMock = vi.mocked(fetchSourceMetadata)
const fetchWorkbenchConfigMock = vi.mocked(fetchWorkbenchConfig)
const saveWorkbenchConfigMock = vi.mocked(saveWorkbenchConfig)
const uploadSourceFileMock = vi.mocked(uploadSourceFile)
const fetchSvnCredentialMock = vi.mocked(fetchSvnCredential)
const listSvnCredentialHostsMock = vi.mocked(listSvnCredentialHosts)
const listSvnDirectoryMock = vi.mocked(listSvnDirectory)

const globalStubs = {
  DataSourcePanel: {
    props: ['store'],
    emits: ['saved'],
    template: `
      <div class="data-source-panel-stub">
        <div v-for="source in store.sources" :key="source.id" class="source-row" :data-source-id="source.id">
          <span>{{ source.id }}</span>
          <button type="button" :data-test="'delete-source-' + source.id" @click="store.removeSource(source.id)">
            模拟删除来源
          </button>
        </div>
        <button
          type="button"
          @click="
            const sourceId = store.sources.length ? 'new_plan_' + String(store.sources.length + 1) : 'new_plan';
            store.upsertSource({ id: sourceId, type: 'local_excel', pathOrUrl: 'D:/plan/' + sourceId + '.xlsx' });
            store.sourceMetadataMap[sourceId] = {
              source_id: sourceId,
              source_type: 'local_excel',
              sheets: [{ name: '新增Sheet', columns: ['模块', '需求点'] }]
            };
            $emit('saved', sourceId)
          "
        >
          模拟保存策划案来源
        </button>
      </div>
    `,
    setup(_props: unknown, { expose }: { expose: (exposed: { openCreateDialog: () => void }) => void }) {
      expose({ openCreateDialog: () => undefined })
    },
  },
  SvnCredentialDialog: {
    props: ['visible', 'host', 'defaultUsername', 'defaultPassword', 'defaultTestDirUrl'],
    emits: ['update:visible', 'saved', 'cancel'],
    template: `
      <section v-if="visible" data-test="svn-credential-dialog">
        <h2>配置 SVN 凭据 — {{ host }}</h2>
        <p>{{ defaultUsername }}</p>
        <p>{{ defaultTestDirUrl }}</p>
        <button type="button" data-test="svn-credential-dialog-save" @click="$emit('saved', host)">
          保存
        </button>
      </section>
    `,
  },
  'el-dialog': {
    props: ['modelValue', 'title'],
    template: `
      <section v-if="modelValue" class="el-dialog-stub">
        <h2>{{ title }}</h2>
        <slot />
        <slot name="footer" />
      </section>
    `,
  },
  'el-drawer': {
    props: ['modelValue', 'title'],
    emits: ['update:modelValue'],
    template: `
      <section v-if="modelValue" class="el-drawer-stub" data-test="source-evidence-resources-drawer">
        <h2>{{ title }}</h2>
        <slot />
      </section>
    `,
  },
  'el-icon': {
    template: '<i><slot /></i>',
  },
  'el-input': {
    props: ['modelValue'],
    template: '<div class="el-input-stub">{{ modelValue }}</div>',
  },
  'el-select': {
    props: ['modelValue', 'disabled'],
    emits: ['update:modelValue', 'change'],
    template: `
      <select
        class="el-select-stub"
        :data-disabled="disabled ? 'true' : 'false'"
        :disabled="disabled"
        :value="modelValue"
        @change="
          $emit('update:modelValue', $event.target.value);
          $emit('change', $event.target.value)
        "
      >
        <slot />
      </select>
    `,
  },
  'el-option': {
    props: ['label', 'value'],
    template: '<option class="el-option-stub" :value="value">{{ label }}</option>',
  },
  'el-tag': {
    template: '<span class="el-tag-stub"><slot /></span>',
  },
  'el-table': {
    props: ['data'],
    template: `
      <table>
        <tbody>
          <tr v-for="row in data" :key="row.id">
            <td>{{ row.id }}</td>
            <td>{{ row.module }}</td>
            <td>{{ row.checkpoint }}</td>
            <td>{{ row.title }}</td>
            <td>{{ row.priority }}</td>
            <td>{{ row.status }}</td>
            <td>{{ row.remarks }}</td>
          </tr>
        </tbody>
      </table>
    `,
  },
  'el-table-column': true,
}

const snapshotResponse = {
  code: 200,
  msg: 'ok',
  data: {
    source_summary: '上传 Excel：planning.xlsx',
    sheet_name: '活动策划案 / Sheet1',
    columns: ['模块', '需求点', '备注'],
    rows: [
      {
        row_index: 1,
        cells: [
          { row_index: 1, column_index: 1, column_name: '模块', value: '活动入口' },
          { row_index: 1, column_index: 2, column_name: '需求点', value: '按配置开放入口' },
          { row_index: 1, column_index: 3, column_name: '备注', value: '入口图未读取' },
        ],
      },
    ],
    non_empty_cell_count: 3,
    truncated: false,
    warnings: [
      {
        source: 'snapshot',
        level: 'warning',
        message: 'V1 仅读取单元格文本，未读取图片、附件、批注或评论语义。',
      },
    ],
  },
}

const snapshotBriefMarkdown = [
  '## 核心目标',
  '- 按配置开放活动入口。',
  '',
  '## 来源索引',
  '- 行 1：活动入口 | 按配置开放入口',
].join('\n')

const snapshotBriefResponse = {
  code: 200,
  msg: 'ok',
  data: {
    brief_markdown: snapshotBriefMarkdown,
    warnings: [],
  },
}

const sourceEvidenceRunResponse = {
  code: 200,
  msg: 'ok',
  data: {
    id: 42,
    status: 'ready',
    source_type: 'feishu',
    source_summary: '飞书 docx：活动富文档',
    source_title: '活动富文档',
    source_identifier: 'docx-token-redacted',
    created_at: '2026-06-29T08:00:00Z',
    expires_at: '2026-07-06T08:00:00Z',
    warnings: [
      {
        source: 'source_evidence',
        level: 'warning' as const,
        message: '隐藏 Sheet 已排除。',
      },
    ],
    resource_count: 2,
    sheet_options: [],
  },
}

const localSourceEvidenceRunResponse = {
  ...sourceEvidenceRunResponse,
  data: {
    ...sourceEvidenceRunResponse.data,
    id: 43,
    source_type: 'local_file',
    source_summary: '本地文件：QuestReward.xlsx',
    source_title: 'QuestReward.xlsx',
    source_identifier: 'sha256-redacted',
    warnings: [
      {
        source: 'local_file',
        level: 'warning' as const,
        message: '隐藏 Sheet 已排除；图片未参与语义理解。',
      },
    ],
    resource_count: 1,
    sheet_options: [
      {
        name: '需求A',
        kind: 'sheet',
        cell_count: 3,
        resource_count: 2,
        is_default: true,
      },
      {
        name: '需求B',
        kind: 'sheet',
        cell_count: 2,
        resource_count: 1,
        is_default: false,
      },
    ],
  },
}

const svnSourceEvidenceRunResponse = {
  ...sourceEvidenceRunResponse,
  data: {
    ...sourceEvidenceRunResponse.data,
    id: 44,
    source_type: 'svn_file',
    source_summary: 'SVN 文件：QuestReward.xls',
    source_title: 'QuestReward.xls',
    source_identifier: 'svn-redacted',
    warnings: [
      {
        source: 'svn_file',
        level: 'warning' as const,
        message: '.xls 图片转换失败；图片未参与语义理解。',
      },
    ],
    resource_count: 1,
    sheet_options: [
      {
        name: '需求A',
        kind: 'sheet',
        cell_count: 3,
        resource_count: 2,
        is_default: true,
      },
      {
        name: '需求B',
        kind: 'sheet',
        cell_count: 2,
        resource_count: 1,
        is_default: false,
      },
    ],
  },
}

const textlessImageSourceEvidenceRunResponse = {
  ...sourceEvidenceRunResponse,
  data: {
    ...sourceEvidenceRunResponse.data,
    id: 45,
    source_type: 'local_file',
    source_summary: '本地图片：ui.png',
    source_title: 'ui.png',
    source_identifier: 'sha256-image-redacted',
    warnings: [
      {
        source: 'local_file',
        level: 'warning' as const,
        message: '独立图片缺少文本主体；生成前需要先观察并采纳视觉证据。图片未参与语义理解。',
      },
    ],
    resource_count: 1,
  },
}

const sourceEvidenceCapabilitiesReadyResponse = {
  code: 200,
  msg: 'ok',
  data: {
    svn_credential_configured: true,
    source_evidence_svn_roots_configured: true,
    vision_ai_configured: true,
    soffice_configured: true,
    soffice_available: true,
    is_project_admin: false,
    items: [
      {
        key: 'vision_ai',
        label: 'Vision AI',
        configured: true,
        available: true,
        status: 'available',
        message: '项目级视觉模型已配置。',
        action: '',
        level: 'info' as const,
      },
    ],
    warnings: [],
  },
}

const sourceEvidenceCapabilitiesMissingResponse = {
  code: 200,
  msg: 'ok',
  data: {
    svn_credential_configured: false,
    source_evidence_svn_roots_configured: false,
    vision_ai_configured: false,
    soffice_configured: false,
    soffice_available: false,
    is_project_admin: false,
    items: [
      {
        key: 'svn_credential',
        label: '项目级 SVN 凭据',
        configured: false,
        available: false,
        status: 'missing',
        message: '当前未配置项目级 SVN 凭据，SVN 文件 Source Evidence 不可用。',
        action: '请联系项目管理员配置项目级 SVN 凭据。',
        level: 'warning' as const,
      },
      {
        key: 'source_evidence_svn_roots',
        label: 'Source Evidence SVN Root',
        configured: false,
        available: false,
        status: 'missing',
        message: '当前未配置 Source Evidence SVN Root，SVN 文件 Source Evidence 不可用。',
        action: '请联系项目管理员配置 Source Evidence SVN Root。',
        level: 'warning' as const,
      },
      {
        key: 'vision_ai',
        label: 'Vision AI',
        configured: false,
        available: false,
        status: 'missing',
        message: '当前未配置视觉模型，图片不会参与语义理解。',
        action: '请联系项目管理员配置 Project Vision AI Credential。',
        level: 'warning' as const,
      },
      {
        key: 'soffice',
        label: 'LibreOffice/soffice',
        configured: false,
        available: false,
        status: 'missing',
        message: '当前未配置 LibreOffice/soffice，.xls 图片不会参与语义理解。',
        action: '请联系项目管理员配置 SOURCE_EVIDENCE_SOFFICE_EXECUTABLE。',
        level: 'warning' as const,
      },
    ],
    warnings: [
      {
        source: 'source_evidence_capabilities',
        level: 'warning' as const,
        message: '当前未配置视觉模型，图片不会参与语义理解，请联系项目管理员。',
      },
    ],
  },
}

const sourceEvidenceCapabilitiesAdminDegradedResponse = {
  code: 200,
  msg: 'ok',
  data: {
    ...sourceEvidenceCapabilitiesMissingResponse.data,
    is_project_admin: true,
    admin_details: {
      config_entry: '/admin',
      enabled_source_evidence_svn_root_count: 0,
      vision_ai_last_test_status: 'failed',
      vision_ai_last_test_at: '2026-07-01T08:00:00Z',
      vision_ai_last_test_error_summary: '连接测试失败',
      soffice_detection_summary: 'LibreOffice/soffice 检测失败：退出码 1',
    },
  },
}

const sourceEvidencePendingPermissionRunResponse = {
  ...sourceEvidenceRunResponse,
  data: {
    ...sourceEvidenceRunResponse.data,
    status: 'pending_permission',
  },
}

const sourceEvidenceResourceListResponse = {
  code: 200,
  msg: 'ok',
  data: {
    items: [
      {
        id: 11,
        ref: 'img_001',
        type: 'image',
        position: 'docx:block:3',
        filename: '入口示意图.png',
        download_status: 'downloaded',
        adoption_status: 'unobserved',
        mime_type: 'image/png',
      },
    ],
    run_status: 'ready',
    warnings: [],
  },
}

const sourceEvidenceAuthorizationSentResponse = {
  code: 200,
  msg: 'ok',
  data: {
    status: 'authorization_sent',
    message: '等待作者授权，授权后请点击重试读取',
    authorization_id: 701,
    target_mode: 'owner_direct',
    sent_targets_count: 1,
    failed_targets_count: 0,
    fallback_to_default_chat: false,
    owner_candidates_truncated: false,
    expires_at: '2026-06-29T08:10:00Z',
    can_retry_read: false,
  },
}

const sourceEvidenceVisualCandidatesResponse = {
  code: 200,
  msg: 'ok',
  data: {
    items: [
      {
        ref: 'img_001',
        type: 'image',
        position: 'docx:block:3',
        filename: '入口示意图.png',
        status: 'ready',
        selectable: true,
        recommended: true,
        selected: true,
        recommendation_reasons: ['附近文本包含视觉关键词'],
        download_status: 'downloaded',
        adoption_status: 'unobserved',
        dimensions: {
          original_width: 800,
          original_height: 600,
          optimized_width: 800,
          optimized_height: 600,
        },
      },
      {
        ref: 'att_001',
        type: 'attachment',
        position: 'docx:block:8',
        filename: '规则说明.pdf',
        status: 'pending_permission',
        selectable: false,
        recommended: false,
        selected: false,
        recommendation_reasons: ['权限不足，暂不可观察'],
        download_status: 'pending_permission',
        adoption_status: 'unobserved',
        dimensions: {},
      },
    ],
    recommended_refs: ['img_001'],
    selected_refs: ['img_001'],
    warnings: [],
  },
}

const sourceEvidenceWorkbookVisualCandidatesForSheetA = {
  code: 200,
  msg: 'ok',
  data: {
    items: [
      {
        ref: 'img_a_001',
        type: 'image',
        position: '需求A!B2',
        filename: '需求A入口.png',
        status: 'ready',
        selectable: true,
        recommended: true,
        selected: true,
        recommendation_reasons: ['当前 Sheet 图片默认选中'],
        download_status: 'downloaded',
        adoption_status: 'unobserved',
        dimensions: {},
      },
      {
        ref: 'img_a_002',
        type: 'image',
        position: '需求A!C8',
        filename: '需求A规则.png',
        status: 'ready',
        selectable: true,
        recommended: false,
        selected: true,
        recommendation_reasons: ['当前 Sheet 图片默认选中'],
        download_status: 'downloaded',
        adoption_status: 'unobserved',
        dimensions: {},
      },
      {
        ref: 'img_b_001',
        type: 'image',
        position: '需求B!B3',
        filename: '需求B入口.png',
        status: 'ready',
        selectable: true,
        recommended: false,
        selected: false,
        recommendation_reasons: [],
        download_status: 'downloaded',
        adoption_status: 'unobserved',
        dimensions: {},
      },
    ],
    recommended_refs: ['img_a_001'],
    selected_refs: ['img_a_001', 'img_a_002'],
    warnings: [],
  },
}

const sourceEvidenceWorkbookManualVisualCandidatesForSheetA = {
  ...sourceEvidenceWorkbookVisualCandidatesForSheetA,
  data: {
    ...sourceEvidenceWorkbookVisualCandidatesForSheetA.data,
    items: sourceEvidenceWorkbookVisualCandidatesForSheetA.data.items.map((candidate) => ({
      ...candidate,
      selected: candidate.ref === 'img_a_002',
    })),
    selected_refs: ['img_a_002'],
  },
}

const sourceEvidenceWorkbookVisualCandidatesForSheetB = {
  ...sourceEvidenceWorkbookVisualCandidatesForSheetA,
  data: {
    ...sourceEvidenceWorkbookVisualCandidatesForSheetA.data,
    items: sourceEvidenceWorkbookVisualCandidatesForSheetA.data.items.map((candidate) => ({
      ...candidate,
      selected: candidate.ref === 'img_b_001',
    })),
    recommended_refs: [],
    selected_refs: ['img_b_001'],
  },
}

const sourceEvidenceObservedResponse = {
  code: 200,
  msg: 'ok',
  data: {
    items: [
      {
        id: 7,
        ref: 'img_001',
        resource_id: 11,
        type: 'image',
        position: 'docx:block:3',
        filename: '入口示意图.png',
        status: 'observed',
        summary: '图中展示活动入口按钮，按钮文案为“参与活动”。',
        visible_text: '参与活动',
        confidence: 0.88,
        limitations: ['只能确认截图可见内容，不能确认配置规则。'],
        source: { provider: 'openai', model: 'gpt-4o-mini' },
        created_by: 1,
        created_at: '2026-06-29T08:10:00Z',
        adopted_by: null,
        adopted_at: null,
        revoked_at: null,
      },
    ],
    warnings: [],
  },
}

const sourceEvidenceAdoptedResponse = {
  ...sourceEvidenceObservedResponse,
  data: {
    ...sourceEvidenceObservedResponse.data,
    items: [
      {
        ...sourceEvidenceObservedResponse.data.items[0],
        status: 'adopted',
        adopted_by: 1,
        adopted_at: '2026-06-29T08:12:00Z',
      },
    ],
  },
}

const sourceEvidenceSnapshotResponse = {
  code: 200,
  msg: 'ok',
  data: {
    source_summary: '飞书 docx：活动富文档',
    sheet_name: 'Source Evidence',
    columns: ['来源类型', '位置', '标题/页签', '内容', '证据状态'],
    rows: [
      {
        row_index: 1,
        cells: [
          { row_index: 1, column_index: 1, column_name: '来源类型', value: 'docx' },
          { row_index: 1, column_index: 2, column_name: '位置', value: 'docx:line:1' },
          { row_index: 1, column_index: 3, column_name: '标题/页签', value: '活动富文档' },
          { row_index: 1, column_index: 4, column_name: '内容', value: '活动入口按配置开放' },
          { row_index: 1, column_index: 5, column_name: '证据状态', value: 'text' },
        ],
      },
      {
        row_index: 2,
        cells: [
          { row_index: 2, column_index: 1, column_name: '来源类型', value: 'resource' },
          { row_index: 2, column_index: 2, column_name: '位置', value: 'docx:block:3' },
          { row_index: 2, column_index: 3, column_name: '标题/页签', value: '活动富文档' },
          { row_index: 2, column_index: 4, column_name: '内容', value: '<image ref="img_001" position="docx:block:3" />' },
          { row_index: 2, column_index: 5, column_name: '证据状态', value: 'pending_visual' },
        ],
      },
    ],
    non_empty_cell_count: 10,
    truncated: false,
    warnings: [
      {
        source: 'source_evidence',
        level: 'warning' as const,
        message: '图片/附件待观察，未作为需求事实。',
      },
    ],
  },
}

const sourceEvidenceSheetASnapshotResponse = {
  ...sourceEvidenceSnapshotResponse,
  data: {
    ...sourceEvidenceSnapshotResponse.data,
    source_summary: '本地文件：QuestReward.xlsx',
    sheet_name: '需求A',
    rows: [
      {
        row_index: 1,
        cells: [
          { row_index: 1, column_index: 1, column_name: '来源类型', value: 'sheet' },
          { row_index: 1, column_index: 2, column_name: '位置', value: '需求A!A1' },
          { row_index: 1, column_index: 3, column_name: '标题/页签', value: '需求A' },
          { row_index: 1, column_index: 4, column_name: '内容', value: '需求A入口按配置开放' },
          { row_index: 1, column_index: 5, column_name: '证据状态', value: 'table' },
        ],
      },
    ],
    non_empty_cell_count: 5,
  },
}

const generationResponse = {
  code: 200,
  msg: 'ok',
  data: {
    blueprint: {
      modules: [{ name: '活动入口' }],
      flows: [{ name: '进入活动页' }],
      requirement_traces: [],
      coverage_dimensions: [{ name: '生命周期' }],
      risks: [{ name: '入口图语义未读取' }],
      unmapped_requirements: [],
      unsupported_or_unfounded_test_points: [],
      open_questions: [],
      warnings: [
        {
          source: 'blueprint',
          level: 'warning',
          message: '入口图语义未读取，需人工确认。',
        },
      ],
    },
    cases: [
      {
        case_id: 'TC-001',
        module: '活动入口',
        feature: '入口开放',
        scenario: '按配置开放入口',
        title: '活动入口按配置展示',
        preconditions: '活动配置已开启',
        steps: '进入主界面并查看活动入口',
        expected_results: '活动入口按配置展示',
        priority: 'P1',
        case_type: '功能',
        source_requirement: '按配置开放入口',
        config_source: '',
        planning_answer: '',
        initial_status: '未执行',
        bug_link: '',
        remarks: '入口图需人工确认',
      },
    ],
    warnings: [
      {
        source: 'snapshot',
        level: 'warning',
        message: 'V1 仅读取单元格文本，未读取图片、附件、批注或评论语义。',
      },
      {
        source: 'cases',
        level: 'warning',
        message: '未使用参考案例增强。',
      },
    ],
    stats: {
      total: 1,
      priority_counts: { P1: 1 },
      module_counts: { 活动入口: 1 },
      case_type_counts: { 功能: 1 },
      warning_count: 2,
    },
    export_columns: ['case_id', 'module', 'title', 'steps', 'expected_results'],
    requirement_trace: [],
    method_context: {
      method_name: 'QA Case Method',
      method_version: 'v1',
      knowledge_library_note: 'V1 未接入项目级 QA 知识库',
      dimensions: [],
    },
    primary_reference_profile: null,
    reference_context: {
      reference_ids: [],
      primary_reference_id: null,
      supplementary_references: [],
    },
  },
}

const excelReferenceProfile = {
  source_type: 'excel' as const,
  source_name: '活动回归模板.xlsx',
  default_sheet_name: '测试用例',
  reference_case_count: 120,
  columns: [
    { index: 1, original_name: '编号', standard_field: 'case_id', standard_label: '用例编号' },
    { index: 2, original_name: '模块', standard_field: 'module', standard_label: '功能模块' },
    { index: 3, original_name: '标题', standard_field: 'title', standard_label: '用例标题' },
  ],
  sheet_options: [
    {
      name: '测试用例',
      reference_case_count: 120,
      is_default: true,
      header_row_index: 1,
      columns: [
        { index: 1, original_name: '编号', standard_field: 'case_id', standard_label: '用例编号' },
        { index: 2, original_name: '模块', standard_field: 'module', standard_label: '功能模块' },
      ],
      warnings: [],
    },
    {
      name: '历史回归',
      reference_case_count: 86,
      is_default: false,
      header_row_index: 1,
      columns: [
        { index: 1, original_name: '编号', standard_field: 'case_id', standard_label: '用例编号' },
        { index: 2, original_name: '标题', standard_field: 'title', standard_label: '用例标题' },
      ],
      warnings: [],
    },
  ],
  warnings: [
    {
      source: 'reference',
      level: 'warning' as const,
      message: '包含历史说明页，已排除不可用 Sheet。',
    },
  ],
}

const markdownReferenceProfile = {
  source_type: 'markdown' as const,
  source_name: '礼包活动边界.md',
  default_sheet_name: null,
  reference_case_count: 42,
  columns: [],
  sheet_options: [],
  warnings: [],
}

const textReferenceProfile = {
  source_type: 'text' as const,
  source_name: 'UI 通用检查.txt',
  default_sheet_name: null,
  reference_case_count: null,
  columns: [],
  sheet_options: [],
  warnings: [
    {
      source: 'reference',
      level: 'warning' as const,
      message: 'TXT 未可靠识别用例数量。',
    },
  ],
}

const referenceCategoriesResponse = {
  code: 200,
  msg: 'ok',
  data: {
    items: [
      { id: 101, name: '活动用例', reference_count: 3 },
      { id: 102, name: '礼包用例', reference_count: 6 },
      { id: 103, name: 'UI 通用', reference_count: 1 },
    ],
  },
}

const giftReferenceItems = Array.from({ length: 6 }, (_, index) => {
  const number = index + 1
  const isExcel = number % 3 === 0
  return {
    id: 300 + number,
    category_id: 102,
    category_name: '礼包用例',
    original_filename: isExcel ? `礼包领取回归 ${number}.xlsx` : `礼包活动边界补充 ${number}.md`,
    suffix: isExcel ? '.xlsx' : '.md',
    size_bytes: 2048 + number,
    profile: isExcel
      ? {
          ...excelReferenceProfile,
          source_name: `礼包领取回归 ${number}.xlsx`,
          default_sheet_name: '礼包用例',
          reference_case_count: 60 + number,
          sheet_options: [
            {
              name: '礼包用例',
              reference_case_count: 60 + number,
              is_default: true,
              header_row_index: 1,
              columns: excelReferenceProfile.columns,
              warnings: [],
            },
          ],
          warnings: [],
        }
      : {
          ...markdownReferenceProfile,
          source_name: `礼包活动边界补充 ${number}.md`,
          reference_case_count: 20 + number,
        },
    reference_case_count: isExcel ? 60 + number : 20 + number,
    default_sheet_name: isExcel ? '礼包用例' : null,
    is_recommended_primary: false,
    created_at: `2026-06-${String(20 - index).padStart(2, '0')}T10:00:00+08:00`,
    updated_at: `2026-06-${String(20 - index).padStart(2, '0')}T10:00:00+08:00`,
  }
})

const referenceFilesResponse = {
  code: 200,
  msg: 'ok',
  data: {
    items: [
      {
        id: 201,
        category_id: 101,
        category_name: '活动用例',
        original_filename: '活动回归模板.xlsx',
        suffix: '.xlsx',
        size_bytes: 4096,
        profile: excelReferenceProfile,
        reference_case_count: 120,
        default_sheet_name: '测试用例',
        is_recommended_primary: true,
        created_at: '2026-06-22T10:18:00+08:00',
        updated_at: '2026-06-22T10:18:00+08:00',
      },
      {
        id: 202,
        category_id: 101,
        category_name: '活动用例',
        original_filename: '礼包活动边界.md',
        suffix: '.md',
        size_bytes: 2048,
        profile: markdownReferenceProfile,
        reference_case_count: 42,
        default_sheet_name: null,
        is_recommended_primary: false,
        created_at: '2026-06-21T16:36:00+08:00',
        updated_at: '2026-06-21T16:36:00+08:00',
      },
      {
        id: 203,
        category_id: 101,
        category_name: '活动用例',
        original_filename: 'UI 通用检查.txt',
        suffix: '.txt',
        size_bytes: 1024,
        profile: textReferenceProfile,
        reference_case_count: null,
        default_sheet_name: null,
        is_recommended_primary: false,
        created_at: '2026-06-20T14:12:00+08:00',
        updated_at: '2026-06-20T14:12:00+08:00',
      },
      {
        id: 204,
        category_id: 103,
        category_name: 'UI 通用',
        original_filename: 'UI 通用冒烟.xlsx',
        suffix: '.xlsx',
        size_bytes: 4096,
        profile: {
          ...excelReferenceProfile,
          source_name: 'UI 通用冒烟.xlsx',
          default_sheet_name: 'UI冒烟',
          reference_case_count: 76,
          sheet_options: [
            {
              name: 'UI冒烟',
              reference_case_count: 76,
              is_default: true,
              header_row_index: 1,
              columns: excelReferenceProfile.columns,
              warnings: [],
            },
            {
              name: '空态检查',
              reference_case_count: 24,
              is_default: false,
              header_row_index: 1,
              columns: excelReferenceProfile.columns,
              warnings: [],
            },
          ],
          warnings: [],
        },
        reference_case_count: 76,
        default_sheet_name: 'UI冒烟',
        is_recommended_primary: true,
        created_at: '2026-06-19T11:08:00+08:00',
        updated_at: '2026-06-19T11:08:00+08:00',
      },
      {
        id: 205,
        category_id: null,
        category_name: '未分类',
        original_filename: '历史活动用例摘录.md',
        suffix: '.md',
        size_bytes: 1024,
        profile: {
          ...markdownReferenceProfile,
          source_name: '历史活动用例摘录.md',
          reference_case_count: 18,
        },
        reference_case_count: 18,
        default_sheet_name: null,
        is_recommended_primary: false,
        created_at: '2026-06-16T15:22:00+08:00',
        updated_at: '2026-06-16T15:22:00+08:00',
      },
      ...giftReferenceItems,
    ],
  },
}

function generationRunResponse(overrides: Record<string, unknown> = {}) {
  return {
    code: 200,
    msg: 'ok',
    data: {
      id: 7001,
      project_id: 1,
      source_evidence_run_id: 43,
      created_by: 1,
      cancelled_by: null,
      status: 'completed',
      planning_sheet_name: '需求A',
      reference_ids: [201],
      primary_reference_id: 201,
      primary_reference_sheet_name: '测试用例',
      strict_mode: false,
      total_chunks: 2,
      completed_chunks: 2,
      failed_chunks: 0,
      atom_count: 2,
      case_count: 1,
      warning_count: 0,
      error_summary: '',
      warnings: [],
      stage_payload: {
        coverage_audit: {
          status: 'completed',
          total_atoms: 2,
          covered_atoms: 2,
          uncovered_atoms: 0,
          failed_chunk_count: 0,
          supplement: {},
          export_limitations: [],
        },
      },
      expires_at: '2026-07-10T08:00:00Z',
      completed_at: '2026-07-03T08:10:00Z',
      cancelled_at: null,
      expired_at: null,
      cleaned_at: null,
      created_at: '2026-07-03T08:00:00Z',
      updated_at: '2026-07-03T08:10:00Z',
      ...overrides,
    },
  }
}

const generationRunQueuedResponse = generationRunResponse({
  status: 'queued',
  completed_chunks: 0,
  atom_count: 0,
  case_count: 0,
  completed_at: null,
  stage_payload: {},
})

const generationRunExtractingResponse = generationRunResponse({
  status: 'extracting_atoms',
  completed_chunks: 1,
  failed_chunks: 1,
  atom_count: 1,
  case_count: 0,
  completed_at: null,
  stage_payload: {
    atom_extraction: {
      status: 'running',
    },
  },
})

const generationRunCancelledResponse = generationRunResponse({
  status: 'cancelled',
  completed_chunks: 1,
  failed_chunks: 1,
  atom_count: 1,
  case_count: 0,
  completed_at: null,
  cancelled_at: '2026-07-03T08:06:00Z',
})

const generationRunPartialResponse = generationRunResponse({
  status: 'partial_completed',
  completed_chunks: 1,
  failed_chunks: 1,
  atom_count: 2,
  case_count: 1,
  warning_count: 2,
  stage_payload: {
    coverage_audit: {
      status: 'partial_completed',
      total_atoms: 2,
      covered_atoms: 1,
      uncovered_atoms: 1,
      failed_chunk_count: 1,
      supplement: { attempted: true, status: 'partial' },
      export_limitations: [
        {
          type: 'uncovered_atoms',
          level: 'warning',
          message: '存在 1 个未覆盖 Requirement Atom。',
          atom_ids: ['ATOM-0002'],
          blocks_export: false,
        },
        {
          type: 'failed_chunks',
          level: 'warning',
          message: '存在 1 个失败 chunk，可能有未知覆盖缺口。',
          failed_chunk_count: 1,
          blocks_export: false,
        },
      ],
    },
  },
})

const generationRunStrictPartialResponse = generationRunResponse({
  ...generationRunPartialResponse.data,
  strict_mode: true,
  stage_payload: {
    coverage_audit: {
      ...((generationRunPartialResponse.data.stage_payload as Record<string, unknown>).coverage_audit as Record<
        string,
        unknown
      >),
      export_limitations: [
        {
          type: 'uncovered_atoms',
          level: 'error',
          message: '严格模式下存在覆盖缺口，不能导出。',
          atom_ids: ['ATOM-0002'],
          blocks_export: true,
        },
      ],
    },
  },
})

const generationRunAtomsResponse = {
  code: 200,
  msg: 'ok',
  data: {
    total: 2,
    items: [
      {
        id: 1,
        atom_id: 'ATOM-0001',
        atom_type: 'rule',
        requirement_text: '活动入口按配置开放',
        source_sheet_name: '需求A',
        source_row_start: 2,
        source_row_end: 2,
        source_columns: ['模块', '规则'],
        visual_evidence_refs: [],
        confidence: 0.95,
        coverage_status: 'covered',
      },
      {
        id: 2,
        atom_id: 'ATOM-0002',
        atom_type: 'timing',
        requirement_text: '奖励每日只能领取一次',
        source_sheet_name: '需求A',
        source_row_start: 5,
        source_row_end: 6,
        source_columns: ['奖励', '次数'],
        visual_evidence_refs: [],
        confidence: 0.9,
        coverage_status: 'unmapped',
      },
    ],
  },
}

const generationRunCasesResponse = {
  code: 200,
  msg: 'ok',
  data: {
    total: 1,
    items: [
      {
        id: 1,
        case_id: 'TC-DB-001',
        fields: {
          case_id: 'TC-DB-001',
          module: '活动入口',
          feature: '入口开放',
          scenario: '按配置开放入口',
          title: '数据库中的活动入口用例',
          preconditions: '活动配置已开启',
          steps: '进入主界面并查看活动入口',
          expected_results: '活动入口按配置展示',
          priority: 'P1',
          case_type: '功能',
          source_requirement: '活动入口按配置开放',
          config_source: '',
          planning_answer: '',
          initial_status: '未执行',
          bug_link: '',
          remarks: 'ATOM-0001',
        },
        atom_refs: ['ATOM-0001'],
        status: 'official',
      },
    ],
  },
}

const generationWithReferenceResponse = {
  ...generationResponse,
  data: {
    ...generationResponse.data,
    export_columns: ['priority', 'module', 'title', 'steps', 'expected_results'],
    primary_reference_profile: {
      ...excelReferenceProfile,
      selected_sheet_name: '测试用例',
      reference_id: 201,
      original_filename: '活动回归模板.xlsx',
      recognized_fields: ['case_id', 'module', 'title'],
    },
    reference_context: {
      reference_ids: [201],
      primary_reference_id: 201,
      primary_reference_sheet_name: '测试用例',
      supplementary_references: [],
    },
  },
}

const defaultPlanningSource: DataSource = {
  id: 'new_plan',
  type: 'feishu',
  pathOrUrl: 'https://example.feishu.cn/sheets/shtcnNewPlan',
}

const secondPlanningSource: DataSource = {
  id: 'second_plan',
  type: 'feishu',
  pathOrUrl: 'https://example.feishu.cn/sheets/shtcnSecondPlan',
}

function mockPlanningSourceConfig(
  sources: DataSource[] = [defaultPlanningSource],
  preferredSourceId = sources[0]?.id ?? null,
  selectedSheetName = '新增Sheet',
): void {
  fetchWorkbenchConfigMock.mockResolvedValueOnce({
    code: 200,
    msg: 'ok',
    data: {
      test_case_generation: {
        planning_sources: sources,
        preferred_planning_source_id: preferredSourceId,
        selected_planning_sheet_name: selectedSheetName,
      },
    },
  })
}

async function flushPromises(): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
}

function mountView(): VueWrapper {
  return mount(TestCaseGeneratorView, {
    global: {
      stubs: globalStubs,
    },
  })
}

async function mountViewWithPlanningSource(
  sources: DataSource[] = [defaultPlanningSource],
  preferredSourceId = sources[0]?.id ?? null,
  selectedSheetName = '新增Sheet',
): Promise<VueWrapper> {
  mockPlanningSourceConfig(sources, preferredSourceId, selectedSheetName)
  const wrapper = mountView()
  await flushPromises()
  return wrapper
}

function findButton(wrapper: VueWrapper | DOMWrapper<Element>, text: string) {
  return wrapper.findAll('button').find((button) => button.text().includes(text))
}

function findReferenceRow(wrapper: VueWrapper, referenceId: string): DOMWrapper<Element> {
  return wrapper.find(`[data-test="reference-file-row"][data-reference-id="${referenceId}"]`)
}

async function selectCategory(wrapper: VueWrapper, categoryName: string): Promise<void> {
  await findButton(wrapper, categoryName)?.trigger('click')
}

async function createFeishuDocumentRun(wrapper: VueWrapper, url = 'https://example.feishu.cn/docx/doc123'): Promise<void> {
  await findButton(wrapper, '飞书文档')?.trigger('click')
  await wrapper.find('[data-test="source-evidence-url-input"]').setValue(url)
  await wrapper.find('[data-test="source-evidence-create-button"]').trigger('click')
  await flushPromises()
}

async function openSvnSourcePanel(wrapper: VueWrapper): Promise<void> {
  await findButton(wrapper, 'SVN 文件')?.trigger('click')
  await flushPromises()
}

async function uploadLocalPlanningFile(wrapper: VueWrapper, file: File): Promise<void> {
  const input = wrapper.find('[data-test="local-source-upload-input"]')
  Object.defineProperty(input.element, 'files', {
    value: [file],
    configurable: true,
  })
  await input.trigger('change')
  await flushPromises()
}

describe('TestCaseGeneratorView', () => {
  beforeEach(() => {
    readPlanningSnapshotMock.mockReset()
    readPlanningSnapshotBriefMock.mockReset()
    createLocalFileSourceEvidenceRunMock.mockReset()
    createSourceEvidenceRunMock.mockReset()
    fetchSourceEvidenceRunMock.mockReset()
    fetchSourceEvidenceResourcesMock.mockReset()
    fetchSourceEvidenceVisualCandidatesMock.mockReset()
    fetchSourceEvidenceObservationsMock.mockReset()
    readSourceEvidenceSnapshotMock.mockReset()
    requestSourceEvidenceAuthorizationMock.mockReset()
    observeSourceEvidenceRunMock.mockReset()
    retrySourceEvidenceRunMock.mockReset()
    adoptSourceEvidenceVisualEvidenceMock.mockReset()
    revokeSourceEvidenceVisualEvidenceMock.mockReset()
    saveSourceEvidenceVisualSelectionsMock.mockReset()
    createGenerationRunMock.mockReset()
    getGenerationRunMock.mockReset()
    cancelGenerationRunMock.mockReset()
    retryFailedGenerationChunksMock.mockReset()
    listGenerationRunAtomsMock.mockReset()
    listGenerationRunCasesMock.mockReset()
    listGenerationRunArtifactsMock.mockReset()
    downloadGenerationRunArtifactMock.mockReset()
    fetchGenerationRunArtifactTextMock.mockReset()
    retryGenerationRunArtifactsMock.mockReset()
    exportGenerationRunWorkbookMock.mockReset()
    generateTestCasesMock.mockReset()
    exportTestCaseWorkbookMock.mockReset()
    fetchSourceEvidenceCapabilitiesMock.mockReset()
    fetchReferenceCategoriesMock.mockReset()
    fetchReferenceFilesMock.mockReset()
    createReferenceCategoryMock.mockReset()
    uploadReferenceFileMock.mockReset()
    setRecommendedPrimaryReferenceMock.mockReset()
    deleteReferenceFileMock.mockReset()
    fetchWorkbenchConfigMock.mockReset()
    fetchSourceMetadataMock.mockReset()
    saveWorkbenchConfigMock.mockReset()
    uploadSourceFileMock.mockReset()
    fetchSvnCredentialMock.mockReset()
    listSvnCredentialHostsMock.mockReset()
    listSvnDirectoryMock.mockReset()
    window.localStorage.clear()
    fetchWorkbenchConfigMock.mockResolvedValue({ code: 200, msg: 'ok', data: {} })
    readPlanningSnapshotMock.mockResolvedValue(snapshotResponse)
    readPlanningSnapshotBriefMock.mockResolvedValue(snapshotBriefResponse)
    createLocalFileSourceEvidenceRunMock.mockResolvedValue(localSourceEvidenceRunResponse)
    createSourceEvidenceRunMock.mockResolvedValue(sourceEvidenceRunResponse)
    fetchSourceEvidenceRunMock.mockResolvedValue(sourceEvidenceRunResponse)
    fetchSourceEvidenceResourcesMock.mockResolvedValue(sourceEvidenceResourceListResponse)
    fetchSourceEvidenceVisualCandidatesMock.mockResolvedValue(sourceEvidenceVisualCandidatesResponse)
    fetchSourceEvidenceObservationsMock.mockResolvedValue({ code: 200, msg: 'ok', data: { items: [], warnings: [] } })
    readSourceEvidenceSnapshotMock.mockResolvedValue(sourceEvidenceSnapshotResponse)
    requestSourceEvidenceAuthorizationMock.mockResolvedValue(sourceEvidenceAuthorizationSentResponse)
    observeSourceEvidenceRunMock.mockResolvedValue(sourceEvidenceObservedResponse)
    retrySourceEvidenceRunMock.mockResolvedValue(sourceEvidenceRunResponse)
    adoptSourceEvidenceVisualEvidenceMock.mockResolvedValue(sourceEvidenceAdoptedResponse)
    revokeSourceEvidenceVisualEvidenceMock.mockResolvedValue(sourceEvidenceObservedResponse)
    saveSourceEvidenceVisualSelectionsMock.mockResolvedValue(sourceEvidenceVisualCandidatesResponse)
    createGenerationRunMock.mockResolvedValue(generationRunQueuedResponse)
    getGenerationRunMock.mockResolvedValue(generationRunResponse())
    cancelGenerationRunMock.mockResolvedValue(generationRunCancelledResponse)
    retryFailedGenerationChunksMock.mockResolvedValue({
      code: 200,
      msg: 'ok',
      data: { run_id: 7001, status: 'chunking', retried_chunk_count: 1 },
    })
    listGenerationRunAtomsMock.mockResolvedValue(generationRunAtomsResponse)
    listGenerationRunCasesMock.mockResolvedValue(generationRunCasesResponse)
    listGenerationRunArtifactsMock.mockResolvedValue({
      code: 200,
      msg: 'ok',
      data: { items: [], total: 0 },
    })
    downloadGenerationRunArtifactMock.mockResolvedValue({
      blob: new Blob(['artifact']),
      filename: '测试用例.xlsx',
    })
    fetchGenerationRunArtifactTextMock.mockResolvedValue('{}')
    retryGenerationRunArtifactsMock.mockResolvedValue({
      code: 200,
      msg: 'ok',
      data: { items: [], total: 0 },
    })
    generateTestCasesMock.mockResolvedValue(generationResponse)
    fetchSourceEvidenceCapabilitiesMock.mockResolvedValue(sourceEvidenceCapabilitiesReadyResponse)
    saveWorkbenchConfigMock.mockResolvedValue({ code: 200, msg: 'ok' })
    exportTestCaseWorkbookMock.mockResolvedValue({
      blob: new Blob(['xlsx']),
      filename: 'test-cases-v1.xlsx',
    })
    exportGenerationRunWorkbookMock.mockResolvedValue({
      blob: new Blob(['xlsx']),
      filename: 'test-cases-v3-run-7001.xlsx',
    })
    fetchReferenceCategoriesMock.mockResolvedValue(referenceCategoriesResponse)
    fetchReferenceFilesMock.mockResolvedValue(referenceFilesResponse)
    createReferenceCategoryMock.mockResolvedValue({
      code: 200,
      msg: 'ok',
      data: { id: 104, name: '新增分类', reference_count: 0 },
    })
    uploadReferenceFileMock.mockResolvedValue({
      code: 200,
      msg: 'ok',
      data: referenceFilesResponse.data.items[0],
    })
    setRecommendedPrimaryReferenceMock.mockResolvedValue({
      code: 200,
      msg: 'ok',
      data: { ...referenceFilesResponse.data.items[1], is_recommended_primary: true },
    })
    deleteReferenceFileMock.mockResolvedValue({
      code: 200,
      msg: 'ok',
      data: { id: 203, deleted: true },
    })
    fetchSourceMetadataMock.mockResolvedValue({
      code: 200,
      msg: 'ok',
      data: {
        source_id: 'new_plan',
        source_type: 'feishu',
        sheets: [{ name: '新增Sheet', columns: ['模块', '需求点'] }],
      },
    })
    fetchSvnCredentialMock.mockResolvedValue(null)
    listSvnCredentialHostsMock.mockResolvedValue({
      code: 200,
      msg: 'ok',
      data: { items: [] },
    })
    listSvnDirectoryMock.mockResolvedValue({
      code: 200,
      msg: 'ok',
      data: {
        dir_url: 'https://samosvn/data/project/samo/GameDatas/',
        host: 'samosvn',
        credential_username: '',
        entries: [],
      },
    })
  })

  it('renders the V3 test case generation workspace with reference data from API', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(fetchSourceEvidenceCapabilitiesMock).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('用例生成')
    expect(wrapper.text()).toContain('当前来源')
    expect(wrapper.text()).toContain('参考案例库')
    expect(wrapper.text()).toContain('参考来源（可选）')
    expect(wrapper.text()).toContain('项目 AI 可用')
    expect(wrapper.text()).toContain('活动回归模板.xlsx')
    expect(wrapper.text()).toContain('参考用例数量')
    expect(wrapper.text()).toContain('约 120 条')
    expect(wrapper.text()).toContain('生成前先读取 Source Evidence')
    expect(wrapper.text()).toContain('V3 读取完整 selected Planning Sheet')
  })

  it('hides Source Evidence runtime capability status when capability check endpoint is unavailable', async () => {
    fetchSourceEvidenceCapabilitiesMock.mockRejectedValueOnce(new Error('Not Found'))

    const wrapper = mountView()
    await flushPromises()

    expect(fetchSourceEvidenceCapabilitiesMock).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-test="source-evidence-capability-status"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Not Found')
  })

  it('shows Source Evidence runtime capability warnings for normal members', async () => {
    fetchSourceEvidenceCapabilitiesMock.mockResolvedValueOnce(sourceEvidenceCapabilitiesMissingResponse)

    const wrapper = mountView()
    await flushPromises()

    const status = wrapper.find('[data-test="source-evidence-capability-status"]')
    expect(status.exists()).toBe(true)
    expect(status.text()).toContain('Source Evidence 运行能力')
    expect(status.text()).toContain('当前未配置视觉模型，图片不会参与语义理解')
    expect(status.text()).toContain('当前未配置 LibreOffice/soffice，.xls 图片不会参与语义理解')
    expect(status.text()).toContain('请联系项目管理员')
    expect(status.text()).not.toContain('去管理后台配置')
  })

  it('shows Source Evidence runtime admin details and configuration entry for project admins', async () => {
    fetchSourceEvidenceCapabilitiesMock.mockResolvedValueOnce(sourceEvidenceCapabilitiesAdminDegradedResponse)

    const wrapper = mountView()
    await flushPromises()

    const status = wrapper.find('[data-test="source-evidence-capability-status"]')
    expect(status.text()).toContain('去管理后台配置')
    expect(status.text()).toContain('LibreOffice/soffice 检测失败：退出码 1')
    expect(status.text()).toContain('连接测试失败')
    expect(status.text()).not.toContain('sk-project-vision-secret')
    expect(status.text()).not.toContain('C:/Sensitive')
  })

  it('disables SVN Source Evidence reading when project SVN capabilities are missing', async () => {
    fetchSourceEvidenceCapabilitiesMock.mockResolvedValueOnce(sourceEvidenceCapabilitiesMissingResponse)
    const wrapper = mountView()
    await flushPromises()

    await openSvnSourcePanel(wrapper)
    await wrapper.find('[data-test="svn-file-url-input"]').setValue('https://samosvn/data/project/samo/GameDatas/QuestReward.xls')
    await flushPromises()

    const readButton = wrapper.find('[data-test="svn-read-data"]')
    expect(readButton.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('SVN 文件 Source Evidence 不可用')
    expect(createSourceEvidenceRunMock).not.toHaveBeenCalled()
  })

  it('does not block text generation when Vision AI capability is missing but disables observation', async () => {
    fetchSourceEvidenceCapabilitiesMock.mockResolvedValueOnce(sourceEvidenceCapabilitiesMissingResponse)
    createLocalFileSourceEvidenceRunMock.mockResolvedValueOnce(localSourceEvidenceRunResponse)
    const wrapper = mountView()
    await flushPromises()

    await uploadLocalPlanningFile(wrapper, new File(['xlsx'], 'QuestReward.xlsx'))
    await wrapper.find('[data-test="source-evidence-resources-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('当前未配置视觉模型，图片不会参与语义理解')
    expect(wrapper.find('[data-test="source-evidence-observe-button"]').attributes('disabled')).toBeDefined()

    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(createGenerationRunMock).toHaveBeenCalledWith(
      expect.objectContaining({
        source_evidence_run_id: 43,
        planning_sheet_name: '需求A',
      }),
    )
    expect(generateTestCasesMock).not.toHaveBeenCalled()
  })

  it('renders the source shell with three source modes and compact summary chips by default', () => {
    const wrapper = mountView()

    expect(wrapper.text()).toContain('01')
    expect(wrapper.text()).toContain('数据源')
    expect(wrapper.find('[data-test="source-mode-local"]').classes()).toContain('is-active')
    expect(wrapper.text()).toContain('本地文件')
    expect(wrapper.text()).toContain('SVN 文件')
    expect(wrapper.text()).toContain('飞书文档')
    expect(wrapper.text()).toContain('上传文件')
    expect(wrapper.text()).toContain('待读取')
    expect(wrapper.text()).toContain('SVN 文件')
    expect(wrapper.text()).toContain('待选择文件')
    expect(wrapper.text()).toContain('拖拽文件到这里，或点击上传')
    expect(wrapper.text()).toContain('支持 .xlsx / .xls / .png / .jpg / .jpeg / .webp')
    expect(findButton(wrapper, '选择文件')).toBeDefined()
    expect(wrapper.find('[data-test="local-source-upload-input"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="source-path-input"]').exists()).toBe(false)
    expect(wrapper.find('.data-source-panel-stub').exists()).toBe(false)
    expect(wrapper.find('[data-test="planning-source-select"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="current-source-card"]').text()).toContain('本地文件')
    expect(wrapper.find('[data-test="current-source-card"]').text()).toContain('等待上传本地文件')
    expect(wrapper.find('[data-test="snapshot-readiness-card"]').text()).toContain('等待上传本地文件')
    expect(wrapper.text()).not.toContain('plan_feishu')
    expect(wrapper.text()).not.toContain('example.feishu.cn')
    expect(wrapper.text()).not.toContain('活动策划案 / Sheet1')
    expect(wrapper.text()).not.toContain('奖励配置 / Sheet2')
    expect(wrapper.find('[data-test="read-snapshot-button"]').attributes('disabled')).toBeDefined()
  })

  it('does not restore persisted local Excel as a V2 Source Evidence input', async () => {
    const wrapper = await mountViewWithPlanningSource([
      { id: 'persisted_plan', type: 'local_excel', pathOrUrl: 'D:/plan/persisted.xlsx' },
    ], 'persisted_plan', '策划Sheet')

    expect(wrapper.find('[data-test="source-mode-local"]').classes()).toContain('is-active')
    expect(wrapper.text()).toContain('本地文件')
    expect(wrapper.text()).toContain('待读取')
    expect(wrapper.text()).toContain('Source Evidence 状态')
    expect(wrapper.text()).not.toContain('D:/plan/persisted.xlsx')
    expect(wrapper.text()).not.toContain('persisted.xlsx')
    expect(wrapper.find('[data-test="read-snapshot-button"]').attributes('disabled')).toBeDefined()
  })

  it('uploads a local file as a Source Evidence Run and does not use legacy source metadata', async () => {
    createLocalFileSourceEvidenceRunMock.mockResolvedValueOnce(localSourceEvidenceRunResponse)
    const wrapper = mountView()
    await flushPromises()
    fetchSourceMetadataMock.mockClear()

    await uploadLocalPlanningFile(wrapper, new File(['excel'], 'QuestReward.xlsx'))

    expect(createLocalFileSourceEvidenceRunMock).toHaveBeenCalledWith(expect.objectContaining({ name: 'QuestReward.xlsx' }))
    expect(uploadSourceFileMock).not.toHaveBeenCalled()
    expect(fetchSourceMetadataMock).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="source-chip-local"]').text()).toContain('本地文件 · 已读取')
    const status = wrapper.find('[data-test="local-source-file-status"]').text()
    expect(status).toContain('Source Evidence 状态')
    expect(status).toContain('QuestReward.xlsx')
    expect(status).toContain('1 个资源')
    expect(wrapper.find('[data-test="source-evidence-document-card"]').text()).toContain('本地文件：QuestReward.xlsx')
    expect(wrapper.find('[data-test="source-evidence-document-card"]').text()).toContain('图片未参与语义理解')
    expect(wrapper.text()).not.toContain('D:/runtime/uploads/project-1/20260701_quest_reward.xlsx')
    expect(wrapper.text()).not.toContain('20260701_quest_reward.xlsx')
    expect(wrapper.find('[data-test="planning-sheet-select"]').exists()).toBe(true)
    expect((wrapper.find('[data-test="planning-sheet-select"]').element as HTMLSelectElement).value).toBe('需求A')

    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(readSourceEvidenceSnapshotMock).toHaveBeenCalledWith(43, { sheet_name: '需求A' })
    expect(readPlanningSnapshotMock).not.toHaveBeenCalled()
  })

  it('clears Source Evidence snapshot, brief, generation and export readiness after switching workbook Sheet', async () => {
    createLocalFileSourceEvidenceRunMock.mockResolvedValueOnce(localSourceEvidenceRunResponse)
    readSourceEvidenceSnapshotMock.mockResolvedValueOnce(sourceEvidenceSheetASnapshotResponse)
    fetchSourceEvidenceVisualCandidatesMock.mockResolvedValueOnce(sourceEvidenceWorkbookVisualCandidatesForSheetB)
    const wrapper = mountView()
    await flushPromises()

    await uploadLocalPlanningFile(wrapper, new File(['excel'], 'QuestReward.xlsx'))
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('活动入口按配置展示')
    expect(wrapper.find('[data-test="preview-export-button"]').attributes('disabled')).toBeUndefined()

    fetchSourceEvidenceVisualCandidatesMock.mockClear()
    await wrapper.find('[data-test="planning-sheet-select"]').setValue('需求B')
    await flushPromises()

    expect(fetchSourceEvidenceVisualCandidatesMock).toHaveBeenCalledWith(43, '需求B')
    expect(wrapper.text()).not.toContain('活动入口按配置展示')
    expect(wrapper.text()).toContain('来源已就绪，点击全量生成用例。')
    expect(wrapper.find('[data-test="preview-generate-button"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-test="preview-export-button"]').attributes('disabled')).toBeDefined()
    expect(readSourceEvidenceSnapshotMock).toHaveBeenCalledTimes(1)
  })

  it('blocks generation for a standalone image Source Evidence run without adopted visual evidence', async () => {
    createLocalFileSourceEvidenceRunMock.mockResolvedValueOnce(textlessImageSourceEvidenceRunResponse)
    readSourceEvidenceSnapshotMock.mockResolvedValueOnce({
      ...sourceEvidenceSnapshotResponse,
      data: {
        ...sourceEvidenceSnapshotResponse.data,
        source_summary: '本地图片：ui.png',
        warnings: [
          {
            source: 'local_file',
            level: 'warning' as const,
            message: '无文本主体，需先观察并采纳视觉证据后才能作为需求事实。',
          },
        ],
      },
    })
    const wrapper = mountView()
    await flushPromises()

    await uploadLocalPlanningFile(wrapper, new File(['png'], 'ui.png', { type: 'image/png' }))
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(createLocalFileSourceEvidenceRunMock).toHaveBeenCalledWith(expect.objectContaining({ name: 'ui.png' }))
    expect(readSourceEvidenceSnapshotMock).toHaveBeenCalledWith(45)
    expect(wrapper.text()).toContain('缺少文本主体')
    expect(wrapper.text()).toContain('图片未参与语义理解')
    expect(wrapper.text()).toContain('先观察并采纳视觉证据')
    expect(wrapper.find('[data-test="preview-generate-button"]').attributes('disabled')).toBeDefined()

    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(generateTestCasesMock).not.toHaveBeenCalled()
  })

  it('updates 02 current source summary when switching V2 Source Evidence source modes', async () => {
    const wrapper = mountView()
    await flushPromises()

    await uploadLocalPlanningFile(wrapper, new File(['excel'], 'QuestReward.xlsx'))

    expect(wrapper.find('[data-test="current-source-card"]').text()).toContain('本地文件')
    expect(wrapper.find('[data-test="current-source-card"]').text()).toContain('QuestReward.xls')
    expect(wrapper.find('[data-test="planning-sheet-select"]').exists()).toBe(true)

    createSourceEvidenceRunMock.mockResolvedValueOnce(svnSourceEvidenceRunResponse)
    await openSvnSourcePanel(wrapper)
    await wrapper.find('[data-test="svn-file-url-input"]').setValue('https://samosvn/data/project/samo/GameDatas/QuestReward.xls')
    await wrapper.find('[data-test="svn-read-data"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="current-source-card"]').text()).toContain('SVN 文件')
    expect(wrapper.find('[data-test="current-source-card"]').text()).toContain('QuestReward.xls')

    await createFeishuDocumentRun(wrapper)

    expect(wrapper.find('[data-test="current-source-card"]').text()).toContain('飞书文档')
    expect(wrapper.find('[data-test="current-source-card"]').text()).toContain('活动富文档')
    expect(wrapper.find('[data-test="snapshot-readiness-card"]').text()).toContain('可生成兼容快照')
  })

  it('clears the current local Source Evidence run without writing legacy planning source config', async () => {
    const wrapper = mountView()
    await flushPromises()

    await uploadLocalPlanningFile(wrapper, new File(['excel'], 'QuestReward.xlsx'))
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('活动入口按配置展示')

    await wrapper.find('[data-test="local-source-clear-file"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="read-snapshot-button"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).not.toContain('活动入口按配置展示')
    expect(wrapper.find('[data-test="source-chip-local"]').text()).toContain('本地文件 · 待读取')
    expect(saveWorkbenchConfigMock).not.toHaveBeenCalled()
  })

  it('shows a safe upload error summary without leaking local paths or tokens', async () => {
    createLocalFileSourceEvidenceRunMock.mockRejectedValueOnce(
      new Error('上传失败 D:/secret/QuestReward.xlsx token=abc123 open_id=ou_123456'),
    )
    const wrapper = mountView()
    await flushPromises()

    await uploadLocalPlanningFile(wrapper, new File(['bad'], 'QuestReward.xlsx'))

    expect(createLocalFileSourceEvidenceRunMock).toHaveBeenCalledTimes(1)
    expect(uploadSourceFileMock).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="local-source-upload-error"]').text()).toContain('上传文件失败')
    expect(wrapper.text()).not.toContain('D:/secret')
    expect(wrapper.text()).not.toContain('abc123')
    expect(wrapper.text()).not.toContain('ou_123456')
  })

  it('does not restore persisted SVN Excel as a V2 Source Evidence input', async () => {
    const svnSource: DataSource = {
      id: 'svn_plan',
      type: 'svn',
      pathOrUrl: 'https://samosvn/data/project/samo/GameDatas/datas_qa88/QuestReward.xlsx',
    }
    const wrapper = await mountViewWithPlanningSource([svnSource], 'svn_plan', 'Reward')

    await openSvnSourcePanel(wrapper)

    expect(wrapper.find('[data-test="source-mode-svn"]').classes()).toContain('is-active')
    expect(wrapper.text()).toContain('SVN 文件')
    expect(wrapper.text()).toContain('待选择文件')
    expect(wrapper.text()).toContain('SVN 文件读取')
    expect(wrapper.text()).not.toContain('https://samosvn')
    expect(wrapper.find('[data-test="read-snapshot-button"]').attributes('disabled')).toBeDefined()
  })

  it('creates an SVN file Source Evidence run from a URL without legacy directory metadata', async () => {
    createSourceEvidenceRunMock.mockResolvedValueOnce(svnSourceEvidenceRunResponse)
    const wrapper = mountView()
    await flushPromises()
    fetchSourceMetadataMock.mockClear()

    await openSvnSourcePanel(wrapper)
    await wrapper.find('[data-test="svn-file-url-input"]').setValue('https://samosvn/data/project/samo/GameDatas/QuestReward.xls')
    await wrapper.find('[data-test="svn-read-data"]').trigger('click')
    await flushPromises()

    expect(createSourceEvidenceRunMock).toHaveBeenCalledWith({
      source_type: 'svn_file',
      source_url: 'https://samosvn/data/project/samo/GameDatas/QuestReward.xls',
    })
    expect(listSvnDirectoryMock).not.toHaveBeenCalled()
    expect(fetchSourceMetadataMock).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="source-chip-svn"]').text()).toContain('SVN 文件 · 已读取')
    expect(wrapper.find('[data-test="current-source-card"]').text()).toContain('QuestReward.xls')
    expect(wrapper.find('[data-test="source-evidence-document-card"]').text()).toContain('SVN 文件：QuestReward.xls')
    expect(wrapper.text()).toContain('图片未参与语义理解')
    expect(wrapper.find('[data-test="planning-sheet-select"]').exists()).toBe(true)
    expect((wrapper.find('[data-test="planning-sheet-select"]').element as HTMLSelectElement).value).toBe('需求A')

    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(readSourceEvidenceSnapshotMock).toHaveBeenCalledWith(44, { sheet_name: '需求A' })
    expect(readPlanningSnapshotMock).not.toHaveBeenCalled()
  })

  it('shows a sanitized SVN Source Evidence creation error without opening personal credential controls', async () => {
    createSourceEvidenceRunMock.mockRejectedValueOnce(
      new Error('缺少项目级 SVN 凭据 Authorization Bearer token=abc123 password=secret'),
    )
    const wrapper = mountView()
    await flushPromises()

    await openSvnSourcePanel(wrapper)
    await wrapper.find('[data-test="svn-file-url-input"]').setValue('https://samosvn/data/project/samo/GameDatas/QuestReward.xls')
    await wrapper.find('[data-test="svn-read-data"]').trigger('click')
    await flushPromises()

    expect(createSourceEvidenceRunMock).toHaveBeenCalledWith({
      source_type: 'svn_file',
      source_url: 'https://samosvn/data/project/samo/GameDatas/QuestReward.xls',
    })
    expect(wrapper.find('[data-test="svn-directory-error"]').text()).toContain('缺少项目级 SVN 凭据')
    expect(wrapper.text()).not.toContain('Authorization')
    expect(wrapper.text()).not.toContain('Bearer')
    expect(wrapper.text()).not.toContain('abc123')
    expect(wrapper.text()).not.toContain('secret')
    expect(listSvnDirectoryMock).not.toHaveBeenCalled()
    expect(fetchSvnCredentialMock).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="svn-credential-dialog"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="svn-main-username-input"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="svn-main-password-input"]').exists()).toBe(false)
  })

  it('does not read persisted SVN sources through uploaded Excel planning snapshot mode', async () => {
    const svnSource: DataSource = {
      id: 'svn_plan',
      type: 'svn',
      pathOrUrl: 'https://samosvn/data/project/samo/GameDatas/datas_qa88/QuestReward.xlsx',
    }
    fetchSourceMetadataMock.mockResolvedValueOnce({
      code: 200,
      msg: 'ok',
      data: {
        source_id: 'svn_plan',
        source_type: 'svn',
        sheets: [{ name: 'Reward', columns: ['ID', '奖励'] }],
      },
    })
    const wrapper = await mountViewWithPlanningSource([svnSource], 'svn_plan', 'Reward')

    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(readPlanningSnapshotMock).not.toHaveBeenCalled()
    expect(readSourceEvidenceSnapshotMock).not.toHaveBeenCalled()
  })

  it('does not restore persisted local planning sources into V2 generation input', async () => {
    const persistedSource = {
      id: 'persisted_plan',
      type: 'local_excel' as const,
      pathOrUrl: 'D:/plan/persisted.xlsx',
    }
    fetchWorkbenchConfigMock.mockResolvedValueOnce({
      code: 200,
      msg: 'ok',
      data: {
        test_case_generation: {
          planning_sources: [persistedSource],
          preferred_planning_source_id: 'persisted_plan',
          selected_planning_sheet_name: '策划Sheet',
        },
      },
    })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('[data-test="source-mode-local"]').classes()).toContain('is-active')
    expect(wrapper.find('.data-source-panel-stub').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('D:/plan/persisted.xlsx')

    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(readPlanningSnapshotMock).not.toHaveBeenCalled()
  })

  it('persists planning sheet selection without overwriting existing workbench config', async () => {
    const personalSources = [{ id: 'personal_check_source', type: 'local_excel' as const, pathOrUrl: 'D:/check.xlsx' }]
    const variables = [{ tag: 'items', source_id: 'personal_check_source', sheet: 'Sheet1', column: 'ID' }]
    fetchWorkbenchConfigMock.mockResolvedValueOnce({
      code: 200,
      msg: 'ok',
      data: {
        sources: personalSources,
        variables,
        ruleGroups: [{ id: 'ungrouped', name: '未分组' }],
        test_case_generation: {
          planning_sources: [defaultPlanningSource, secondPlanningSource],
          preferred_planning_source_id: 'new_plan',
          selected_planning_sheet_name: '新增Sheet',
        },
      },
    })
    fetchSourceMetadataMock.mockResolvedValueOnce({
      code: 200,
      msg: 'ok',
      data: {
        source_id: 'new_plan',
        source_type: 'feishu',
        sheets: [
          { name: '新增Sheet', columns: ['模块'] },
          { name: '第二Sheet', columns: ['模块'] },
        ],
      },
    })
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('[data-test="planning-sheet-select"]').setValue('第二Sheet')
    await flushPromises()

    const savedPayload = saveWorkbenchConfigMock.mock.calls.at(-1)?.[0] as Record<string, unknown>
    expect(savedPayload.sources).toEqual(personalSources)
    expect(savedPayload.variables).toEqual(variables)
    expect(savedPayload.ruleGroups).toEqual([{ id: 'ungrouped', name: '未分组' }])
    expect(savedPayload.test_case_generation).toEqual({
      planning_sources: [defaultPlanningSource, secondPlanningSource],
      preferred_planning_source_id: 'new_plan',
      selected_planning_sheet_name: '第二Sheet',
    })
  })

  it('does not expose the old source management table controls in the 01 shell', async () => {
    const persistedSource = {
      id: 'persisted_plan',
      type: 'local_excel' as const,
      pathOrUrl: 'D:/plan/persisted.xlsx',
    }
    fetchWorkbenchConfigMock.mockResolvedValueOnce({
      code: 200,
      msg: 'ok',
      data: {
        test_case_generation: {
          planning_sources: [persistedSource],
          preferred_planning_source_id: 'persisted_plan',
          selected_planning_sheet_name: '策划Sheet',
        },
      },
    })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('.data-source-panel-stub').exists()).toBe(false)
    expect(wrapper.find('[data-test="delete-source-persisted_plan"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('D:/plan/persisted.xlsx')
  })

  it('renders generation input and preview as full-width modules', () => {
    const wrapper = mountView()

    expect(wrapper.find('.tcg-content > [data-test="generation-input-module"]').exists()).toBe(true)
    expect(wrapper.find('.tcg-setup').exists()).toBe(false)
    expect(wrapper.find('.tcg-workspace').exists()).toBe(false)
    expect(wrapper.find('[data-test="generation-input-module"]').text()).toContain('当前来源')
    expect(wrapper.find('[data-test="generation-input-module"]').text()).toContain('参考来源（可选）')
    expect(wrapper.find('.tcg-content > .tcg-preview').exists()).toBe(true)
    expect(wrapper.find('[data-test="generation-input-module"]').text()).toContain('02')
    expect(wrapper.find('[data-test="reference-library"]').text()).toContain('03')
    expect(wrapper.find('.tcg-preview').text()).toContain('04')
  })

  it('moves generate and export actions above the preview tabs', () => {
    const wrapper = mountView()
    const headerActions = wrapper.find('.ui-page-header__actions')
    const previewActions = wrapper.find('[data-test="preview-action-bar"]')
    const previewText = wrapper.find('.tcg-preview').text()

    expect(headerActions.text()).toContain('项目 AI 可用')
    expect(headerActions.text()).not.toContain('上传参考案例')
    expect(headerActions.text()).not.toContain('生成用例')
    expect(previewActions.exists()).toBe(true)
    expect(previewActions.text()).toContain('结果预览')
    expect(previewActions.text()).toContain('V3 读取完整 selected Planning Sheet')
    expect(previewActions.text()).toContain('全量生成用例')
    expect(previewActions.text()).toContain('下载所选文件')
    expect(previewText.indexOf('结果预览')).toBeLessThan(previewText.indexOf('测试用例'))
  })

  it('keeps preview tabs focused on V3 cases, coverage, atoms and warnings', () => {
    const wrapper = mountView()
    const previewTabs = wrapper.find('.tcg-preview__tabs')

    expect(previewTabs.text()).toContain('AI 整理稿')
    expect(previewTabs.text()).toContain('测试用例')
    expect(previewTabs.text()).toContain('覆盖审计')
    expect(previewTabs.text()).toContain('需求原子')
    expect(previewTabs.text()).toContain('限制提示')
    expect(previewTabs.text()).not.toContain('原始表格/追踪视图')
    expect(previewTabs.text()).not.toContain('用例蓝图')
    expect(wrapper.find('.tcg-blueprint-summary').exists()).toBe(false)
  })

  it('keeps V3 generation disabled for legacy snapshot-only sources', async () => {
    const wrapper = await mountViewWithPlanningSource()

    expect(wrapper.find('[data-test="preview-generate-button"]').attributes('disabled')).toBeDefined()

    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(readPlanningSnapshotMock).toHaveBeenCalledWith({
      source_type: 'feishu',
      source: {
        id: 'new_plan',
        type: 'feishu',
        pathOrUrl: 'https://example.feishu.cn/sheets/shtcnNewPlan',
      },
      sheet_name: '新增Sheet',
    })
    expect(wrapper.find('[data-test="preview-generate-button"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('按配置开放入口')
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    expect(generateTestCasesMock).not.toHaveBeenCalled()
    expect(createGenerationRunMock).not.toHaveBeenCalled()
  })

  it('creates a Source Evidence Run and reads its compatible snapshot', async () => {
    const wrapper = mountView()
    await flushPromises()

    await createFeishuDocumentRun(wrapper)

    expect(createSourceEvidenceRunMock).toHaveBeenCalledWith({
      source_type: 'feishu',
      source_url: 'https://example.feishu.cn/docx/doc123',
    })
    expect(wrapper.text()).toContain('活动富文档')
    expect(wrapper.text()).toContain('飞书 docx：活动富文档')
    expect(wrapper.text()).toContain('ready')
    expect(wrapper.text()).toContain('2026-07-06')
    expect(wrapper.text()).toContain('2 个资源')
    expect(wrapper.text()).toContain('隐藏 Sheet 已排除。')
    expect(wrapper.text()).toContain('文本/表格可继续，图片/附件待观察')
    expect(wrapper.text()).not.toContain('docx-token-redacted')
    expect(wrapper.find('[data-test="planning-sheet-select"]').exists()).toBe(false)

    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(readSourceEvidenceSnapshotMock).toHaveBeenCalledWith(42)
    expect(readPlanningSnapshotMock).not.toHaveBeenCalled()
    expect(readPlanningSnapshotBriefMock).toHaveBeenCalledWith({
      planning_snapshot: sourceEvidenceSnapshotResponse.data,
    })
    expect(wrapper.text()).toContain('快照行数2 行')
  })

  it('renders the redesigned Feishu document source layout with safe status and pipeline', async () => {
    const wrapper = mountView()
    await flushPromises()

    await createFeishuDocumentRun(wrapper)

    const urlInput = wrapper.find('[data-test="source-evidence-url-input"]')
    expect(urlInput.attributes('placeholder')).toBe('粘贴 docx / docs / wiki / sheets / base 链接')

    const readPanel = wrapper.find('[data-test="source-evidence-read-panel"]')
    expect(readPanel.exists()).toBe(true)
    expect(readPanel.text()).toContain('飞书文档读取')

    const summaryCard = wrapper.find('[data-test="source-evidence-document-card"]')
    expect(summaryCard.text()).toContain('活动富文档')
    expect(summaryCard.text()).toContain('飞书 docx：活动富文档')
    expect(summaryCard.text()).toContain('ready')
    expect(summaryCard.text()).toContain('2 个资源')
    expect(summaryCard.text()).toContain('隐藏 Sheet 已排除。')

    const authorizationStatus = wrapper.find('[data-test="source-evidence-authorization-status"]')
    expect(authorizationStatus.text()).toContain('授权与资源状态')
    expect(authorizationStatus.text()).toContain('已可读取')
    expect(authorizationStatus.text()).toContain('仅用于读取正文、表格、下载图片/附件和生成证据，不修改源文档')

    const pipeline = wrapper.find('[data-test="source-evidence-pipeline"]')
    expect(pipeline.exists()).toBe(true)
    for (const step of ['读取链接', '识别 owner/creator', '申请授权', '作者授权', '重试读取', '下载图片/附件', '生成快照']) {
      expect(pipeline.text()).toContain(step)
    }
  })

  it('shows authorization request button for pending permission Source Evidence runs', async () => {
    createSourceEvidenceRunMock.mockResolvedValueOnce(sourceEvidencePendingPermissionRunResponse)
    const wrapper = mountView()
    await flushPromises()

    await createFeishuDocumentRun(wrapper)

    const authorizationButton = wrapper.find('[data-test="source-evidence-authorization-button"]')
    expect(authorizationButton.exists()).toBe(true)
    expect(authorizationButton.attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-test="source-evidence-authorization-status"]').text()).toContain('待作者授权')
    expect(wrapper.find('[data-test="current-source-card"]').text()).toContain('飞书文档')
    expect(wrapper.find('[data-test="snapshot-readiness-card"]').text()).toContain('先申请授权或重试读取')
    expect(wrapper.find('[data-test="read-snapshot-button"]').attributes('disabled')).toBeDefined()

    await authorizationButton.trigger('click')
    await flushPromises()

    expect(requestSourceEvidenceAuthorizationMock).toHaveBeenCalledWith(42)
    expect(wrapper.text()).toContain('等待作者授权，授权后请点击重试读取')
  })

  it('shows authorization request button for readable runs with failed resource downloads', async () => {
    fetchSourceEvidenceResourcesMock.mockResolvedValueOnce({
      ...sourceEvidenceResourceListResponse,
      data: {
        ...sourceEvidenceResourceListResponse.data,
        items: [
          {
            ...sourceEvidenceResourceListResponse.data.items[0],
            download_status: 'download_failed',
          },
        ],
      },
    })
    const wrapper = mountView()
    await flushPromises()

    await createFeishuDocumentRun(wrapper)

    expect(wrapper.find('[data-test="source-evidence-authorization-button"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="snapshot-readiness-card"]').text()).toContain('先申请授权或重试读取')
    expect(wrapper.find('[data-test="read-snapshot-button"]').attributes('disabled')).toBeDefined()
  })

  it('disables duplicate authorization request after already sent response and keeps retry available', async () => {
    createSourceEvidenceRunMock.mockResolvedValueOnce(sourceEvidencePendingPermissionRunResponse)
    requestSourceEvidenceAuthorizationMock.mockResolvedValueOnce({
      ...sourceEvidenceAuthorizationSentResponse,
      data: {
        ...sourceEvidenceAuthorizationSentResponse.data,
        status: 'already_sent',
        message: '该源文档已有未过期的授权卡，不重复发送。',
      },
    })
    const wrapper = mountView()
    await flushPromises()

    await createFeishuDocumentRun(wrapper)
    const authorizationButton = wrapper.find('[data-test="source-evidence-authorization-button"]')
    await authorizationButton.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('等待作者授权，授权后请点击重试读取')
    expect(wrapper.find('[data-test="source-evidence-authorization-status"]').text()).toContain('等待作者授权')
    expect(wrapper.find('[data-test="source-evidence-authorization-button"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="source-evidence-retry-button"]').exists()).toBe(true)

    await wrapper.find('[data-test="source-evidence-authorization-button"]').trigger('click')
    await flushPromises()

    expect(requestSourceEvidenceAuthorizationMock).toHaveBeenCalledTimes(1)
  })

  it('hides authorization request after already authorized response and prompts retry', async () => {
    createSourceEvidenceRunMock.mockResolvedValueOnce(sourceEvidencePendingPermissionRunResponse)
    requestSourceEvidenceAuthorizationMock.mockResolvedValueOnce({
      ...sourceEvidenceAuthorizationSentResponse,
      data: {
        ...sourceEvidenceAuthorizationSentResponse.data,
        status: 'already_authorized',
        message: '该源文档授权仍在有效期内，可回到用例生成页面重试读取。',
        can_retry_read: true,
      },
    })
    const wrapper = mountView()
    await flushPromises()

    await createFeishuDocumentRun(wrapper)
    await wrapper.find('[data-test="source-evidence-authorization-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('已检测到授权，可点击重试读取')
    expect(wrapper.find('[data-test="source-evidence-authorization-status"]').text()).toContain('已可读取')
    expect(wrapper.find('[data-test="source-evidence-authorization-button"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="source-evidence-retry-button"]').exists()).toBe(true)
  })

  it('allows requesting authorization again after send failed response', async () => {
    createSourceEvidenceRunMock.mockResolvedValueOnce(sourceEvidencePendingPermissionRunResponse)
    requestSourceEvidenceAuthorizationMock
      .mockResolvedValueOnce({
        ...sourceEvidenceAuthorizationSentResponse,
        data: {
          ...sourceEvidenceAuthorizationSentResponse.data,
          status: 'send_failed',
          message: '发送授权卡失败：已脱敏错误摘要。',
        },
      })
      .mockResolvedValueOnce(sourceEvidenceAuthorizationSentResponse)
    const wrapper = mountView()
    await flushPromises()

    await createFeishuDocumentRun(wrapper)
    await wrapper.find('[data-test="source-evidence-authorization-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('发送授权卡失败：已脱敏错误摘要。')
    expect(wrapper.find('[data-test="source-evidence-authorization-status"]').text()).toContain('发送失败')
    expect(wrapper.find('[data-test="source-evidence-authorization-button"]').attributes('disabled')).toBeUndefined()

    await wrapper.find('[data-test="source-evidence-authorization-button"]').trigger('click')
    await flushPromises()

    expect(requestSourceEvidenceAuthorizationMock).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('等待作者授权，授权后请点击重试读取')
  })

  it('disables Source Evidence actions after authorization request reports expired or cleaned', async () => {
    fetchSourceEvidenceResourcesMock.mockResolvedValueOnce({
      ...sourceEvidenceResourceListResponse,
      data: {
        ...sourceEvidenceResourceListResponse.data,
        items: [
          {
            ...sourceEvidenceResourceListResponse.data.items[0],
            download_status: 'download_failed',
          },
        ],
      },
    })
    const expiredError = new Error('证据已过期') as Error & {
      payload: { data: typeof sourceEvidenceAuthorizationSentResponse.data }
    }
    expiredError.payload = {
      data: {
        ...sourceEvidenceAuthorizationSentResponse.data,
        status: 'expired_or_cleaned',
        message: '证据已过期或已清理，请重新读取来源。',
      },
    }
    requestSourceEvidenceAuthorizationMock.mockRejectedValueOnce(expiredError)
    const wrapper = mountView()
    await flushPromises()

    await createFeishuDocumentRun(wrapper)
    expect(wrapper.find('[data-test="snapshot-readiness-card"]').text()).toContain('先申请授权或重试读取')
    expect(wrapper.find('[data-test="read-snapshot-button"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="preview-generate-button"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="preview-export-button"]').attributes('disabled')).toBeDefined()

    await wrapper.find('[data-test="source-evidence-authorization-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('证据已过期或已清理，请重新读取来源。')
    expect(wrapper.find('[data-test="source-evidence-authorization-status"]').text()).toContain('证据已过期或已清理')
    expect(wrapper.find('[data-test="source-evidence-authorization-button"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="read-snapshot-button"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="preview-generate-button"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="preview-export-button"]').attributes('disabled')).toBeDefined()
  })

  it('uses source_evidence_run_id for V3 generation and run id export', async () => {
    const wrapper = mountView()
    await flushPromises()

    await createFeishuDocumentRun(wrapper)
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(createGenerationRunMock).toHaveBeenCalledWith({
      source_evidence_run_id: 42,
      planning_sheet_name: 'Source Evidence',
      reference_ids: [201],
      primary_reference_id: 201,
      primary_reference_sheet_name: '测试用例',
      strict_mode: false,
    })
    expect(generateTestCasesMock).not.toHaveBeenCalled()

    await wrapper.find('[data-test="preview-export-button"]').trigger('click')
    await flushPromises()

    expect(exportGenerationRunWorkbookMock).toHaveBeenCalledWith(7001)
    expect(exportTestCaseWorkbookMock).not.toHaveBeenCalled()
  })

  it('creates a V3 generation run with source evidence scope and reference selection', async () => {
    createGenerationRunMock.mockResolvedValueOnce(generationRunQueuedResponse)
    getGenerationRunMock.mockResolvedValueOnce(generationRunResponse())
    const wrapper = mountView()
    await flushPromises()

    await uploadLocalPlanningFile(wrapper, new File(['excel'], 'QuestReward.xlsx'))
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(createGenerationRunMock).toHaveBeenCalledWith({
      source_evidence_run_id: 43,
      planning_sheet_name: '需求A',
      reference_ids: [201],
      primary_reference_id: 201,
      primary_reference_sheet_name: '测试用例',
      strict_mode: false,
    })
    expect(generateTestCasesMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('全量生成用例')
    expect(wrapper.text()).toContain('读取来源')
    expect(wrapper.text()).toContain('结构切片')
    expect(wrapper.text()).toContain('抽取需求')
    expect(wrapper.text()).toContain('生成用例')
    expect(wrapper.text()).toContain('覆盖审计')
    expect(wrapper.text()).toContain('数据库中的活动入口用例')
    expect(wrapper.text()).toContain('Requirement Atom')
  })

  it('cancels an active V3 generation run', async () => {
    createGenerationRunMock.mockResolvedValueOnce(generationRunExtractingResponse)
    getGenerationRunMock.mockResolvedValueOnce(generationRunExtractingResponse)
    const wrapper = mountView()
    await flushPromises()

    await uploadLocalPlanningFile(wrapper, new File(['excel'], 'QuestReward.xlsx'))
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="generation-run-cancel-button"]').trigger('click')
    await flushPromises()

    expect(cancelGenerationRunMock).toHaveBeenCalledWith(7001)
    expect(wrapper.text()).toContain('已取消')
  })

  it('retries failed chunks for a partial V3 generation run', async () => {
    createGenerationRunMock.mockResolvedValueOnce(generationRunPartialResponse)
    getGenerationRunMock.mockResolvedValueOnce(generationRunPartialResponse)
    const wrapper = mountView()
    await flushPromises()

    await uploadLocalPlanningFile(wrapper, new File(['excel'], 'QuestReward.xlsx'))
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="generation-run-retry-button"]').trigger('click')
    await flushPromises()

    expect(retryFailedGenerationChunksMock).toHaveBeenCalledWith(7001)
  })

  it('renders completed V3 cases, coverage audit and requirement atoms', async () => {
    createGenerationRunMock.mockResolvedValueOnce(generationRunResponse())
    const wrapper = mountView()
    await flushPromises()

    await uploadLocalPlanningFile(wrapper, new File(['excel'], 'QuestReward.xlsx'))
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(listGenerationRunCasesMock).toHaveBeenCalledWith(7001)
    expect(listGenerationRunAtomsMock).toHaveBeenCalledWith(7001)
    expect(wrapper.text()).toContain('数据库中的活动入口用例')

    await wrapper.find('[data-test="preview-tab-coverage"]').trigger('click')
    expect(wrapper.text()).toContain('覆盖 2 / 2')
    expect(wrapper.text()).toContain('失败 chunk 0')

    await wrapper.find('[data-test="preview-tab-atoms"]').trigger('click')
    expect(wrapper.text()).toContain('ATOM-0001')
    expect(wrapper.text()).toContain('活动入口按配置开放')
  })

  it('shows partial completed limitations and blocks strict export with uncovered atoms', async () => {
    createGenerationRunMock.mockResolvedValueOnce(generationRunStrictPartialResponse)
    getGenerationRunMock.mockResolvedValueOnce(generationRunStrictPartialResponse)
    const wrapper = mountView()
    await flushPromises()

    await uploadLocalPlanningFile(wrapper, new File(['excel'], 'QuestReward.xlsx'))
    await wrapper.find('[data-test="generation-strict-mode-checkbox"]').setValue(true)
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(createGenerationRunMock.mock.calls[0][0]).toMatchObject({ strict_mode: true })
    expect(wrapper.text()).toContain('partial_completed')
    expect(wrapper.text()).toContain('严格模式下存在覆盖缺口')
    expect(wrapper.find('[data-test="preview-export-button"]').attributes('disabled')).toBeDefined()
    await wrapper.find('[data-test="preview-export-button"]').trigger('click')
    expect(exportGenerationRunWorkbookMock).not.toHaveBeenCalled()
  })

  it('exports V3 workbook by run id without posting generated cases', async () => {
    createGenerationRunMock.mockResolvedValueOnce(generationRunPartialResponse)
    getGenerationRunMock.mockResolvedValueOnce(generationRunPartialResponse)
    const wrapper = mountView()
    await flushPromises()

    await uploadLocalPlanningFile(wrapper, new File(['excel'], 'QuestReward.xlsx'))
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-export-button"]').trigger('click')
    await flushPromises()

    expect(exportGenerationRunWorkbookMock).toHaveBeenCalledWith(7001)
    expect(exportTestCaseWorkbookMock).not.toHaveBeenCalled()
  })

  it('restores the latest short-lived V3 run from local storage after refresh', async () => {
    window.localStorage.setItem('test-case-generation:v3:last-run-id', '7001')
    getGenerationRunMock.mockResolvedValueOnce(generationRunResponse())

    const wrapper = mountView()
    await flushPromises()

    expect(getGenerationRunMock).toHaveBeenCalledWith(7001)
    expect(listGenerationRunCasesMock).toHaveBeenCalledWith(7001)
    expect(listGenerationRunAtomsMock).toHaveBeenCalledWith(7001)
    expect(wrapper.text()).toContain('数据库中的活动入口用例')
  })

  it('shows Source Evidence visual candidates in a drawer and saves selection', async () => {
    const wrapper = mountView()
    await flushPromises()

    await createFeishuDocumentRun(wrapper)
    await wrapper.find('[data-test="source-evidence-resources-button"]').trigger('click')
    await flushPromises()

    expect(fetchSourceEvidenceVisualCandidatesMock).toHaveBeenCalledWith(42)
    expect(fetchSourceEvidenceObservationsMock).toHaveBeenCalledWith(42)
    const drawer = wrapper.find('[data-test="source-evidence-resources-drawer"]')
    expect(drawer.exists()).toBe(true)
    expect(drawer.text()).toContain('img_001')
    expect(drawer.text()).toContain('image')
    expect(drawer.text()).toContain('docx:block:3')
    expect(drawer.text()).toContain('系统推荐')
    expect(drawer.text()).toContain('已选')
    expect(drawer.text()).toContain('附近文本包含视觉关键词')
    expect(drawer.text()).toContain('权限不足')
    expect(drawer.text()).toContain('unobserved')

    const imageCheckbox = wrapper.find('[data-test="visual-candidate-checkbox-img_001"]')
    expect((imageCheckbox.element as HTMLInputElement).checked).toBe(true)
    await imageCheckbox.setValue(false)
    await wrapper.find('[data-test="source-evidence-visual-selection-save-button"]').trigger('click')
    await flushPromises()

    expect(saveSourceEvidenceVisualSelectionsMock).toHaveBeenCalledWith(42, { selected_refs: [] })
  })

  it('defaults current workbook Sheet visual candidates and preserves manual selection until switching Sheet', async () => {
    createLocalFileSourceEvidenceRunMock.mockResolvedValueOnce(localSourceEvidenceRunResponse)
    fetchSourceEvidenceVisualCandidatesMock.mockResolvedValueOnce(sourceEvidenceWorkbookVisualCandidatesForSheetA)
    saveSourceEvidenceVisualSelectionsMock.mockResolvedValueOnce(sourceEvidenceWorkbookManualVisualCandidatesForSheetA)
    fetchSourceEvidenceVisualCandidatesMock.mockResolvedValueOnce(sourceEvidenceWorkbookVisualCandidatesForSheetB)
    const wrapper = mountView()
    await flushPromises()

    await uploadLocalPlanningFile(wrapper, new File(['excel'], 'QuestReward.xlsx'))
    await wrapper.find('[data-test="source-evidence-resources-button"]').trigger('click')
    await flushPromises()

    expect(fetchSourceEvidenceVisualCandidatesMock).toHaveBeenCalledWith(43, '需求A')
    expect((wrapper.find('[data-test="visual-candidate-checkbox-img_a_001"]').element as HTMLInputElement).checked).toBe(true)
    expect((wrapper.find('[data-test="visual-candidate-checkbox-img_a_002"]').element as HTMLInputElement).checked).toBe(true)
    expect((wrapper.find('[data-test="visual-candidate-checkbox-img_b_001"]').element as HTMLInputElement).checked).toBe(false)

    fetchSourceEvidenceVisualCandidatesMock.mockClear()
    await wrapper.find('[data-test="visual-candidate-checkbox-img_a_001"]').setValue(false)
    await wrapper.find('[data-test="source-evidence-visual-selection-save-button"]').trigger('click')
    await flushPromises()

    expect(saveSourceEvidenceVisualSelectionsMock).toHaveBeenCalledWith(43, {
      selected_refs: ['img_a_002'],
      sheet_name: '需求A',
    })
    expect(fetchSourceEvidenceVisualCandidatesMock).not.toHaveBeenCalled()
    expect((wrapper.find('[data-test="visual-candidate-checkbox-img_a_001"]').element as HTMLInputElement).checked).toBe(false)
    expect((wrapper.find('[data-test="visual-candidate-checkbox-img_a_002"]').element as HTMLInputElement).checked).toBe(true)

    await wrapper.find('[data-test="planning-sheet-select"]').setValue('需求B')
    await flushPromises()

    expect(fetchSourceEvidenceVisualCandidatesMock).toHaveBeenCalledWith(43, '需求B')
    expect((wrapper.find('[data-test="visual-candidate-checkbox-img_a_001"]').element as HTMLInputElement).checked).toBe(false)
    expect((wrapper.find('[data-test="visual-candidate-checkbox-img_a_002"]').element as HTMLInputElement).checked).toBe(false)
    expect((wrapper.find('[data-test="visual-candidate-checkbox-img_b_001"]').element as HTMLInputElement).checked).toBe(true)
  })

  it('observes selected visual candidates and adopts evidence for generation/export', async () => {
    const wrapper = mountView()
    await flushPromises()

    await createFeishuDocumentRun(wrapper)
    await wrapper.find('[data-test="source-evidence-resources-button"]').trigger('click')
    await flushPromises()

    await wrapper.find('[data-test="source-evidence-observe-button"]').trigger('click')
    await flushPromises()

    expect(saveSourceEvidenceVisualSelectionsMock).toHaveBeenCalledWith(42, { selected_refs: ['img_001'] })
    expect(observeSourceEvidenceRunMock).toHaveBeenCalledWith(42)
    expect(wrapper.text()).toContain('图中展示活动入口按钮')
    expect(wrapper.text()).toContain('只能确认截图可见内容')

    await wrapper.find('[data-test="source-evidence-adopt-observation-7"]').trigger('click')
    await flushPromises()

    expect(adoptSourceEvidenceVisualEvidenceMock).toHaveBeenCalledWith(42, { observation_ids: [7] })
    expect(wrapper.text()).toContain('已采纳 1 个')

    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(createGenerationRunMock).toHaveBeenCalledWith(
      expect.objectContaining({
        source_evidence_run_id: 42,
        planning_sheet_name: 'Source Evidence',
      }),
    )
    expect(generateTestCasesMock).not.toHaveBeenCalled()

    await wrapper.find('[data-test="preview-export-button"]').trigger('click')
    await flushPromises()

    expect(exportGenerationRunWorkbookMock).toHaveBeenCalledWith(7001)
    expect(exportTestCaseWorkbookMock).not.toHaveBeenCalled()
  })

  it('revokes adopted visual evidence and marks generated result stale', async () => {
    fetchSourceEvidenceObservationsMock.mockResolvedValueOnce(sourceEvidenceAdoptedResponse)
    const wrapper = mountView()
    await flushPromises()

    await createFeishuDocumentRun(wrapper)
    await wrapper.find('[data-test="source-evidence-resources-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="preview-export-button"]').attributes('disabled')).toBeUndefined()

    await wrapper.find('[data-test="source-evidence-revoke-observation-7"]').trigger('click')
    await flushPromises()

    expect(revokeSourceEvidenceVisualEvidenceMock).toHaveBeenCalledWith(42, 7)
    expect(wrapper.text()).toContain('已采纳视觉证据已变化，需要重新生成。')
    expect(wrapper.find('[data-test="preview-export-button"]').attributes('disabled')).toBeDefined()
  })

  it('marks generated result stale after saving visual selection', async () => {
    const wrapper = mountView()
    await flushPromises()

    await createFeishuDocumentRun(wrapper)
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="preview-export-button"]').attributes('disabled')).toBeUndefined()

    await wrapper.find('[data-test="source-evidence-resources-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="visual-candidate-checkbox-img_001"]').setValue(false)
    await wrapper.find('[data-test="source-evidence-visual-selection-save-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('视觉观察选择已变化，需要重新生成。')
    expect(wrapper.find('[data-test="preview-export-button"]').attributes('disabled')).toBeDefined()
  })

  it('disables generation for expired or cleaned Source Evidence runs', async () => {
    createSourceEvidenceRunMock.mockResolvedValueOnce({
      ...sourceEvidenceRunResponse,
      data: {
        ...sourceEvidenceRunResponse.data,
        status: 'expired',
      },
    })
    const wrapper = mountView()
    await flushPromises()

    await createFeishuDocumentRun(wrapper)

    expect(wrapper.text()).toContain('证据已过期或已清理，请重新读取来源。')
    expect(wrapper.find('[data-test="source-evidence-authorization-status"]').text()).toContain('证据已过期或已清理')
    expect(wrapper.find('[data-test="read-snapshot-button"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="preview-generate-button"]').attributes('disabled')).toBeDefined()
  })

  it('keeps legacy Feishu spreadsheet snapshot compatibility without restoring the source dropdown', async () => {
    const legacyFeishuSource: DataSource = {
      id: 'legacy_feishu',
      type: 'feishu',
      pathOrUrl: 'https://example.feishu.cn/sheets/shtcnSecretToken',
    }
    fetchSourceMetadataMock.mockResolvedValueOnce({
      code: 200,
      msg: 'ok',
      data: {
        source_id: 'legacy_feishu',
        source_type: 'feishu',
        sheets: [{ name: '需求Sheet', columns: ['模块', '需求点'] }],
      },
    })
    const wrapper = await mountViewWithPlanningSource([legacyFeishuSource], 'legacy_feishu', '需求Sheet')

    expect(wrapper.find('[data-test="planning-source-select"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="current-source-card"]').text()).toContain('飞书电子表格')
    expect(wrapper.text()).not.toContain('shtcnSecretToken')

    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(readPlanningSnapshotMock).toHaveBeenCalledWith({
      source_type: 'feishu',
      source: legacyFeishuSource,
      sheet_name: '需求Sheet',
    })
  })

  it('sanitizes Feishu document source summaries, warnings and authorization errors', async () => {
    createSourceEvidenceRunMock.mockResolvedValueOnce({
      ...sourceEvidencePendingPermissionRunResponse,
      data: {
        ...sourceEvidencePendingPermissionRunResponse.data,
        source_title: 'https://example.feishu.cn/docx/doccnSecret123 活动文档',
        source_summary: 'wiki token=wikiSecret file_token=fileSecret open_id=ou_secret_user',
        warnings: [
          {
            source: 'source_evidence',
            level: 'warning' as const,
            message: 'Authorization Bearer abc.def token=docSecret open_id=ou_warning_user',
          },
        ],
      },
    })
    requestSourceEvidenceAuthorizationMock.mockResolvedValueOnce({
      ...sourceEvidenceAuthorizationSentResponse,
      data: {
        ...sourceEvidenceAuthorizationSentResponse.data,
        status: 'send_failed',
        message: 'send failed Bearer secret.jwt token=authSecret open_id=ou_auth_user',
      },
    })
    const wrapper = mountView()
    await flushPromises()

    await createFeishuDocumentRun(wrapper, 'https://example.feishu.cn/docx/doccnSourceUrlSecret')
    await wrapper.find('[data-test="source-evidence-authorization-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('[已隐藏URL]')
    expect(wrapper.text()).toContain('[已隐藏敏感字段]')
    expect(wrapper.text()).not.toContain('doccnSecret123')
    expect(wrapper.text()).not.toContain('doccnSourceUrlSecret')
    expect(wrapper.text()).not.toContain('wikiSecret')
    expect(wrapper.text()).not.toContain('fileSecret')
    expect(wrapper.text()).not.toContain('ou_secret_user')
    expect(wrapper.text()).not.toContain('Bearer')
    expect(wrapper.text()).not.toContain('Authorization')
    expect(wrapper.text()).not.toContain('authSecret')
    expect(wrapper.text()).not.toContain('ou_auth_user')
  })

  it('automatically requests a snapshot brief after reading the planning snapshot', async () => {
    const wrapper = await mountViewWithPlanningSource()

    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(readPlanningSnapshotBriefMock).toHaveBeenCalledTimes(1)
    expect(readPlanningSnapshotBriefMock).toHaveBeenCalledWith({
      planning_snapshot: snapshotResponse.data,
    })
  })

  it('keeps the planning snapshot preview when snapshot brief fails but does not unlock V3 generation', async () => {
    readPlanningSnapshotBriefMock.mockRejectedValueOnce(new Error('brief failed'))
    const wrapper = await mountViewWithPlanningSource()

    await selectCategory(wrapper, '礼包用例')
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(readPlanningSnapshotBriefMock).toHaveBeenCalledWith({
      planning_snapshot: snapshotResponse.data,
    })
    expect(wrapper.text()).toContain('按配置开放入口')
    expect(wrapper.find('[data-test="preview-generate-button"]').attributes('disabled')).toBeDefined()

    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(generateTestCasesMock).not.toHaveBeenCalled()
    expect(createGenerationRunMock).not.toHaveBeenCalled()
  })

  it('does not start V3 generation from a pending legacy snapshot brief', async () => {
    let resolveSnapshotBrief!: (value: typeof snapshotBriefResponse) => void
    const pendingSnapshotBrief = new Promise<typeof snapshotBriefResponse>((resolve) => {
      resolveSnapshotBrief = resolve
    })
    readPlanningSnapshotBriefMock.mockReturnValueOnce(pendingSnapshotBrief)
    const wrapper = await mountViewWithPlanningSource()

    await selectCategory(wrapper, '礼包用例')
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(readPlanningSnapshotBriefMock).toHaveBeenCalledWith({
      planning_snapshot: snapshotResponse.data,
    })

    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await Promise.resolve()

    expect(generateTestCasesMock).not.toHaveBeenCalled()
    expect(createGenerationRunMock).not.toHaveBeenCalled()
    resolveSnapshotBrief(snapshotBriefResponse)
    await flushPromises()
  })

  it('keeps legacy snapshot preview separate from V3 generation without reference selection', async () => {
    const wrapper = await mountViewWithPlanningSource()

    await selectCategory(wrapper, '礼包用例')

    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(generateTestCasesMock).not.toHaveBeenCalled()
    expect(createGenerationRunMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('按配置开放入口')
    expect(wrapper.text()).toContain('V3 生成读取完整 selected Planning Sheet')
  })

  it('does not pass legacy snapshot facts to V3 generation', async () => {
    const wrapper = await mountViewWithPlanningSource()

    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(generateTestCasesMock).not.toHaveBeenCalled()
    expect(createGenerationRunMock).not.toHaveBeenCalled()
  })

  it('does not pass completed snapshot brief markdown as V3 generation facts', async () => {
    const wrapper = await mountViewWithPlanningSource()

    await selectCategory(wrapper, '礼包用例')
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(generateTestCasesMock).not.toHaveBeenCalled()
    expect(createGenerationRunMock).not.toHaveBeenCalled()
  })

  it('copies generated snapshot brief markdown', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(globalThis.navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    const wrapper = await mountViewWithPlanningSource()

    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="copy-snapshot-brief-button"]').trigger('click')
    await flushPromises()

    expect(writeText).toHaveBeenCalledWith(snapshotBriefMarkdown)
  })

  it('retries snapshot brief generation from the failure state', async () => {
    readPlanningSnapshotBriefMock.mockRejectedValueOnce(new Error('brief failed'))
    const wrapper = await mountViewWithPlanningSource()

    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('brief failed')
    expect(readPlanningSnapshotBriefMock).toHaveBeenCalledTimes(1)

    await wrapper.find('[data-test="retry-snapshot-brief-error-button"]').trigger('click')
    await flushPromises()

    expect(readPlanningSnapshotBriefMock).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-test="snapshot-brief-markdown"]').text()).toContain('按配置开放活动入口')
  })

  it('exports using the persisted V3 generation run result', async () => {
    const wrapper = mountView()
    await flushPromises()

    await uploadLocalPlanningFile(wrapper, new File(['excel'], 'QuestReward.xlsx'))
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-export-button"]').trigger('click')
    await flushPromises()

    expect(exportGenerationRunWorkbookMock).toHaveBeenCalledWith(7001)
    expect(exportTestCaseWorkbookMock).not.toHaveBeenCalled()
  })

  it('disables export after reference settings make the generated result stale', async () => {
    const wrapper = mountView()
    await flushPromises()

    await uploadLocalPlanningFile(wrapper, new File(['excel'], 'QuestReward.xlsx'))
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="preview-export-button"]').attributes('disabled')).toBeUndefined()

    await selectCategory(wrapper, '礼包用例')
    await findButton(findReferenceRow(wrapper, '303'), '设为主参考')?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('主参考案例已切换，需要重新生成。')
    expect(wrapper.find('[data-test="preview-export-button"]').attributes('disabled')).toBeDefined()
    await wrapper.find('[data-test="preview-export-button"]').trigger('click')
    expect(exportGenerationRunWorkbookMock).not.toHaveBeenCalled()
    expect(exportTestCaseWorkbookMock).not.toHaveBeenCalled()
  })

  it('clears snapshot preview after switching the active 01 source', async () => {
    const wrapper = await mountViewWithPlanningSource()

    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('按配置开放入口')

    await openSvnSourcePanel(wrapper)
    await flushPromises()

    expect(wrapper.text()).not.toContain('活动入口按配置展示')
    expect(wrapper.find('[data-test="current-source-card"]').text()).toContain('SVN 文件')
    expect(wrapper.text()).toContain('读取来源预览后可查看整理稿')
    expect(wrapper.find('[data-test="preview-generate-button"]').attributes('disabled')).toBeDefined()
  })

  it('keeps the preview module on the page scroll flow instead of clipping it internally', () => {
    const source = readFileSync('src/views/TestCaseGeneratorView.vue', 'utf-8')

    expect(source).not.toMatch(/\.tcg-preview\s*\{[^}]*max-height/s)
    expect(source).not.toMatch(/\.tcg-preview\s*\{[^}]*overflow:\s*hidden/s)
    expect(source).toMatch(/\.tcg-content\s*\{[^}]*overflow-y:\s*auto/s)
  })

  it('renders the generation workflow stepper before the metric cards', async () => {
    const wrapper = mountView()
    await flushPromises()

    const content = wrapper.find('.tcg-content')
    const progressCard = wrapper.find('[data-test="test-case-progress-stepper"]')
    const metricSection = wrapper.find('.tcg-metrics')

    expect(progressCard.exists()).toBe(true)
    expect(metricSection.exists()).toBe(true)
    expect(
      Array.from(content.element.children).indexOf(progressCard.element),
    ).toBeLessThan(Array.from(content.element.children).indexOf(metricSection.element))
    expect(progressCard.findAll('[data-test="test-case-progress-step"]')).toHaveLength(4)
    expect(progressCard.text()).toContain('数据源')
    expect(progressCard.text()).toContain('参考')
    expect(progressCard.text()).toContain('生成')
    expect(progressCard.text()).toContain('导出')
  })

  it('loads reference categories and files on page load', async () => {
    const wrapper = mountView()
    await flushPromises()

    const categoryPills = wrapper.findAll('[data-test="reference-category-pill"]').map((pill) => pill.text())
    const referenceLibrary = wrapper.find('[data-test="reference-library"]')

    expect(fetchReferenceCategoriesMock).toHaveBeenCalled()
    expect(fetchReferenceFilesMock).toHaveBeenCalledWith()
    expect(wrapper.find('.tcg-content > [data-test="reference-library"]').exists()).toBe(true)
    expect(wrapper.find('.tcg-setup [data-test="reference-library"]').exists()).toBe(false)
    expect(categoryPills).toEqual(expect.arrayContaining(['活动用例1', '礼包用例2', 'UI 通用1', '未分类0']))
    expect(referenceLibrary.find('[data-test="reference-category-list"]').exists()).toBe(true)
    expect(referenceLibrary.find('[data-test="reference-excel-table"]').exists()).toBe(true)
    expect(referenceLibrary.find('[data-test="reference-selection-summary"]').exists()).toBe(true)
    expect(referenceLibrary.text()).toContain('活动回归模板.xlsx')
    expect(referenceLibrary.text()).not.toContain('礼包活动边界.md')
    expect(referenceLibrary.text()).not.toContain('UI 通用检查.txt')
    expect(referenceLibrary.text()).not.toContain('Markdown')
    expect(referenceLibrary.text()).not.toContain('TXT')
  })

  it('creates a reference category through the API', async () => {
    const wrapper = mountView()
    await flushPromises()

    await findButton(wrapper, '新建分类')?.trigger('click')
    await wrapper.find('input[name="reference-category-name"]').setValue('新增分类')
    await findButton(wrapper, '创建分类')?.trigger('click')
    await flushPromises()

    expect(createReferenceCategoryMock).toHaveBeenCalledWith({ name: '新增分类' })
  })

  it('uploads a reference file through the API for the current category', async () => {
    const wrapper = mountView()
    await flushPromises()
    const file = new File(['case'], 'new-reference.xlsx')

    await findButton(wrapper, '上传参考案例')?.trigger('click')
    const input = wrapper.find('[data-test="reference-upload-input"]')
    Object.defineProperty(input.element, 'files', {
      value: [file],
      configurable: true,
    })
    await input.trigger('change')
    await wrapper.find('[data-test="reference-upload-submit"]').trigger('click')
    await flushPromises()

    expect(uploadReferenceFileMock).toHaveBeenCalledWith(file, 101)
  })

  it('rejects non-Excel reference uploads before calling the API', async () => {
    const wrapper = mountView()
    await flushPromises()
    const file = new File(['case'], 'legacy-reference.md')

    await findButton(wrapper, '上传参考案例')?.trigger('click')
    const input = wrapper.find('[data-test="reference-upload-input"]')
    Object.defineProperty(input.element, 'files', {
      value: [file],
      configurable: true,
    })
    await input.trigger('change')
    await wrapper.find('[data-test="reference-upload-submit"]').trigger('click')
    await flushPromises()

    expect(uploadReferenceFileMock).not.toHaveBeenCalled()
    expect(wrapper.find('.tcg-dialog-error').text()).toContain('请选择一个 .xlsx 或 .xls Excel 参考案例文件。')
  })

  it('clears selected references and primary reference when switching to a category without recommended primary', async () => {
    const wrapper = mountView()
    await flushPromises()

    await selectCategory(wrapper, '礼包用例')

    expect(wrapper.find('[data-test="primary-reference-select"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="reference-entry-card"]').text()).toContain('未选择参考案例')
    expect(wrapper.text()).toContain('当前分类未选择参考案例')
    expect(wrapper.text()).toContain('参考案例分类已切换，本次将按 qa-case 标准逻辑生成。')
  })

  it('selects the recommended primary reference by default when switching to a category that has one', async () => {
    const wrapper = mountView()
    await flushPromises()

    await selectCategory(wrapper, '礼包用例')
    await selectCategory(wrapper, 'UI 通用')

    const uiPrimaryRow = findReferenceRow(wrapper, '204')

    expect((uiPrimaryRow.find('[data-test="reference-checkbox"]').element as HTMLInputElement).checked).toBe(true)
    expect(uiPrimaryRow.classes()).toContain('is-primary')
    expect(wrapper.find('[data-test="reference-entry-card"]').text()).toContain('UI 通用冒烟.xlsx')
  })

  it('allows selecting multiple references within the same category', async () => {
    const wrapper = mountView()
    await flushPromises()

    await selectCategory(wrapper, '礼包用例')
    const firstExcelRow = findReferenceRow(wrapper, '303')
    const secondExcelRow = findReferenceRow(wrapper, '306')

    await firstExcelRow.find('[data-test="reference-checkbox"]').setValue(true)
    await secondExcelRow.find('[data-test="reference-checkbox"]').setValue(true)

    expect((firstExcelRow.find('[data-test="reference-checkbox"]').element as HTMLInputElement).checked).toBe(true)
    expect((secondExcelRow.find('[data-test="reference-checkbox"]').element as HTMLInputElement).checked).toBe(true)
    expect(wrapper.find('[data-test="reference-entry-card"]').text()).toContain('已选 2 个')
    expect(wrapper.find('[data-test="reference-selection-summary"]').text()).toContain('已选 2 个')
    expect(wrapper.find('[data-test="reference-selection-summary"]').text()).toContain('来源 Excel')
  })

  it('setting a file as primary reference automatically selects it', async () => {
    const wrapper = mountView()
    await flushPromises()

    await selectCategory(wrapper, '礼包用例')
    const excelRow = findReferenceRow(wrapper, '303')

    await findButton(excelRow, '设为主参考')?.trigger('click')

    expect((excelRow.find('[data-test="reference-checkbox"]').element as HTMLInputElement).checked).toBe(true)
    expect(excelRow.classes()).toContain('is-primary')
    expect(wrapper.find('[data-test="reference-entry-card"]').text()).toContain('礼包领取回归 3.xlsx')
    expect(wrapper.text()).toContain('主参考案例已切换，需要重新生成。')
  })

  it('calls backend-admin reference actions from the more dialog', async () => {
    const wrapper = mountView()
    await flushPromises()

    await selectCategory(wrapper, '礼包用例')
    await findReferenceRow(wrapper, '303').findAll('button')[2]?.trigger('click')
    await findButton(wrapper, '设为推荐主参考')?.trigger('click')
    await flushPromises()

    expect(setRecommendedPrimaryReferenceMock).toHaveBeenCalledWith(303)

    await findReferenceRow(wrapper, '303').findAll('button')[2]?.trigger('click')
    await findButton(wrapper, '删除文件')?.trigger('click')
    await flushPromises()

    expect(deleteReferenceFileMock).toHaveBeenCalledWith(303)
  })

  it('shows a lightweight reference entry in 02 and keeps primary selection in 03', async () => {
    const wrapper = mountView()
    await flushPromises()

    const referenceEntry = wrapper.find('[data-test="reference-entry-card"]')
    expect(referenceEntry.text()).toContain('参考来源（可选）')
    expect(referenceEntry.text()).toContain('活动回归模板.xlsx')
    expect(referenceEntry.text()).toContain('前往选择')
    expect(wrapper.find('[data-test="primary-reference-select"]').exists()).toBe(false)

    await selectCategory(wrapper, '礼包用例')
    await findReferenceRow(wrapper, '303').find('[data-test="reference-checkbox"]').setValue(true)

    expect(wrapper.find('[data-test="reference-entry-card"]').text()).toContain('已选 1 个')
    expect(wrapper.find('[data-test="reference-entry-card"]').text()).not.toContain('UI 通用检查.txt')
  })

  it('updates the lightweight reference entry when the primary reference changes in 03', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('[data-test="reference-entry-card"]').text()).toContain('活动回归模板.xlsx')

    await selectCategory(wrapper, '礼包用例')
    await findButton(findReferenceRow(wrapper, '303'), '设为主参考')?.trigger('click')

    expect(wrapper.find('[data-test="reference-entry-card"]').text()).toContain('礼包领取回归 3.xlsx')
    expect(wrapper.find('[data-test="primary-reference-sheet-select"]').exists()).toBe(false)
  })

  it('shows empty state when search has no reference matches', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('[data-test="reference-search"]').setValue('不存在的画像')

    expect(wrapper.text()).toContain('没有匹配的参考案例')
    expect(wrapper.text()).toContain('清空筛选')
  })

  it('excludes hidden non-Excel records from the reference table count', async () => {
    const wrapper = mountView()
    await flushPromises()

    await selectCategory(wrapper, '礼包用例')

    const libraryText = wrapper.find('[data-test="reference-library"]').text()
    expect(wrapper.findAll('[data-test="reference-file-row"]')).toHaveLength(2)
    expect(libraryText).toContain('第 1-2 条 / 共 2 条')
    expect(libraryText).toContain('礼包领取回归 3.xlsx')
    expect(libraryText).toContain('礼包领取回归 6.xlsx')
    expect(libraryText).not.toContain('礼包活动边界补充')
  })
})
