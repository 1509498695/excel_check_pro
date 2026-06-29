// @vitest-environment happy-dom

import { mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createReferenceCategory,
  deleteReferenceFile,
  exportTestCaseWorkbook,
  fetchReferenceCategories,
  fetchReferenceFiles,
  generateTestCases,
  readPlanningSnapshot,
  readPlanningSnapshotBrief,
  setRecommendedPrimaryReference,
  uploadReferenceFile,
} from '../../src/api/testCases'
import { fetchSourceMetadata, fetchWorkbenchConfig, saveWorkbenchConfig } from '../../src/api/workbench'
import TestCaseGeneratorView from '../../src/views/TestCaseGeneratorView.vue'

vi.mock('../../src/api/testCases', () => ({
  createReferenceCategory: vi.fn(),
  deleteReferenceFile: vi.fn(),
  exportTestCaseWorkbook: vi.fn(),
  fetchReferenceCategories: vi.fn(),
  fetchReferenceFiles: vi.fn(),
  generateTestCases: vi.fn(),
  readPlanningSnapshot: vi.fn(),
  readPlanningSnapshotBrief: vi.fn(),
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

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

const readPlanningSnapshotMock = vi.mocked(readPlanningSnapshot)
const readPlanningSnapshotBriefMock = vi.mocked(readPlanningSnapshotBrief)
const generateTestCasesMock = vi.mocked(generateTestCases)
const exportTestCaseWorkbookMock = vi.mocked(exportTestCaseWorkbook)
const fetchReferenceCategoriesMock = vi.mocked(fetchReferenceCategories)
const fetchReferenceFilesMock = vi.mocked(fetchReferenceFiles)
const createReferenceCategoryMock = vi.mocked(createReferenceCategory)
const uploadReferenceFileMock = vi.mocked(uploadReferenceFile)
const setRecommendedPrimaryReferenceMock = vi.mocked(setRecommendedPrimaryReference)
const deleteReferenceFileMock = vi.mocked(deleteReferenceFile)
const fetchSourceMetadataMock = vi.mocked(fetchSourceMetadata)
const fetchWorkbenchConfigMock = vi.mocked(fetchWorkbenchConfig)
const saveWorkbenchConfigMock = vi.mocked(saveWorkbenchConfig)

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
    template: '<div class="el-select-stub" :data-disabled="disabled ? \'true\' : \'false\'"><slot /></div>',
  },
  'el-option': {
    props: ['label', 'value'],
    template: '<span class="el-option-stub" :data-value="value">{{ label }}</span>',
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

function findButton(wrapper: VueWrapper | DOMWrapper<Element>, text: string) {
  return wrapper.findAll('button').find((button) => button.text().includes(text))
}

function findReferenceRow(wrapper: VueWrapper, referenceId: string): DOMWrapper<Element> {
  return wrapper.find(`[data-test="reference-file-row"][data-reference-id="${referenceId}"]`)
}

async function selectCategory(wrapper: VueWrapper, categoryName: string): Promise<void> {
  await findButton(wrapper, categoryName)?.trigger('click')
}

async function addPlanningSource(wrapper: VueWrapper): Promise<void> {
  await findButton(wrapper, '模拟保存策划案来源')?.trigger('click')
  await flushPromises()
}

describe('TestCaseGeneratorView', () => {
  beforeEach(() => {
    readPlanningSnapshotMock.mockReset()
    readPlanningSnapshotBriefMock.mockReset()
    generateTestCasesMock.mockReset()
    exportTestCaseWorkbookMock.mockReset()
    fetchReferenceCategoriesMock.mockReset()
    fetchReferenceFilesMock.mockReset()
    createReferenceCategoryMock.mockReset()
    uploadReferenceFileMock.mockReset()
    setRecommendedPrimaryReferenceMock.mockReset()
    deleteReferenceFileMock.mockReset()
    fetchWorkbenchConfigMock.mockReset()
    fetchSourceMetadataMock.mockReset()
    saveWorkbenchConfigMock.mockReset()
    fetchWorkbenchConfigMock.mockResolvedValue({ code: 200, msg: 'ok', data: {} })
    readPlanningSnapshotMock.mockResolvedValue(snapshotResponse)
    readPlanningSnapshotBriefMock.mockResolvedValue(snapshotBriefResponse)
    generateTestCasesMock.mockResolvedValue(generationResponse)
    saveWorkbenchConfigMock.mockResolvedValue({ code: 200, msg: 'ok' })
    exportTestCaseWorkbookMock.mockResolvedValue({
      blob: new Blob(['xlsx']),
      filename: 'test-cases-v1.xlsx',
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
        source_type: 'local_excel',
        sheets: [{ name: '新增Sheet', columns: ['模块', '需求点'] }],
      },
    })
  })

  it('renders the V1 test case generation workspace with reference data from API', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('用例生成')
    expect(wrapper.text()).toContain('策划案来源')
    expect(wrapper.text()).toContain('参考案例库')
    expect(wrapper.text()).toContain('主参考设置')
    expect(wrapper.text()).toContain('项目 AI 可用')
    expect(wrapper.text()).toContain('活动回归模板.xlsx')
    expect(wrapper.text()).toContain('参考用例数量')
    expect(wrapper.text()).toContain('约 120 条')
    expect(wrapper.text()).toContain('生成前先读取策划案快照')
    expect(wrapper.text()).toContain('核对整理稿、测试用例和限制提示，确认后导出 Excel。')
  })

  it('renders the planning source data module without seeded demo data', () => {
    const wrapper = mountView()

    expect(wrapper.text()).toContain('01')
    expect(wrapper.text()).toContain('数据源')
    expect(wrapper.text()).toContain('新增来源')
    expect(wrapper.text()).toContain('策划案来源')
    expect(wrapper.text()).toContain('请先添加策划案来源')
    expect(wrapper.text()).toContain('当前来源无可选 Sheet')
    expect(wrapper.text()).not.toContain('plan_feishu')
    expect(wrapper.text()).not.toContain('example.feishu.cn')
    expect(wrapper.text()).not.toContain('活动策划案 / Sheet1')
    expect(wrapper.text()).not.toContain('奖励配置 / Sheet2')
    expect(wrapper.find('[data-test="read-snapshot-button"]').attributes('disabled')).toBeDefined()
  })

  it('adds a planning source through the embedded source panel store', async () => {
    const wrapper = mountView()

    await findButton(wrapper, '模拟保存策划案来源')?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('new_plan')
    expect(wrapper.text()).toContain('新增Sheet')
    expect(fetchSourceMetadataMock).toHaveBeenCalled()
  })

  it('restores persisted planning sources for the current project user', async () => {
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
    fetchSourceMetadataMock.mockResolvedValueOnce({
      code: 200,
      msg: 'ok',
      data: {
        source_id: 'persisted_plan',
        source_type: 'local_excel',
        sheets: [{ name: '策划Sheet', columns: ['模块', '需求点'] }],
      },
    })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('[data-source-id="persisted_plan"]').exists()).toBe(true)

    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(readPlanningSnapshotMock).toHaveBeenCalledWith({
      source_type: 'uploaded_excel',
      source: persistedSource,
      sheet_name: '策划Sheet',
    })
  })

  it('persists planning sources without overwriting existing workbench config', async () => {
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
          planning_sources: [],
          preferred_planning_source_id: null,
          selected_planning_sheet_name: null,
        },
      },
    })
    const wrapper = mountView()
    await flushPromises()

    await addPlanningSource(wrapper)

    const savedPayload = saveWorkbenchConfigMock.mock.calls.at(-1)?.[0] as Record<string, unknown>
    expect(savedPayload.sources).toEqual(personalSources)
    expect(savedPayload.variables).toEqual(variables)
    expect(savedPayload.ruleGroups).toEqual([{ id: 'ungrouped', name: '未分组' }])
    expect(savedPayload.test_case_generation).toEqual({
      planning_sources: [{ id: 'new_plan', type: 'local_excel', pathOrUrl: 'D:/plan/new_plan.xlsx' }],
      preferred_planning_source_id: 'new_plan',
      selected_planning_sheet_name: '新增Sheet',
    })
  })

  it('persists planning source removal without relying on the saved event', async () => {
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

    await wrapper.find('[data-test="delete-source-persisted_plan"]').trigger('click')
    await flushPromises()

    const savedPayload = saveWorkbenchConfigMock.mock.calls.at(-1)?.[0] as Record<string, unknown>
    expect(savedPayload.test_case_generation).toEqual({
      planning_sources: [],
      preferred_planning_source_id: null,
      selected_planning_sheet_name: null,
    })
  })

  it('renders generation input and preview as full-width modules', () => {
    const wrapper = mountView()

    expect(wrapper.find('.tcg-content > [data-test="generation-input-module"]').exists()).toBe(true)
    expect(wrapper.find('.tcg-setup').exists()).toBe(false)
    expect(wrapper.find('.tcg-workspace').exists()).toBe(false)
    expect(wrapper.find('[data-test="generation-input-module"]').text()).toContain('策划案来源')
    expect(wrapper.find('[data-test="generation-input-module"]').text()).toContain('主参考设置')
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
    expect(previewActions.text()).toContain('核对整理稿、测试用例和限制提示，确认后导出 Excel。')
    expect(previewActions.text()).toContain('生成用例')
    expect(previewActions.text()).toContain('导出 Excel')
    expect(previewText.indexOf('结果预览')).toBeLessThan(previewText.indexOf('策划案快照'))
  })

  it('keeps preview tabs focused on brief, generated cases and warnings', () => {
    const wrapper = mountView()
    const previewTabs = wrapper.find('.tcg-preview__tabs')

    expect(previewTabs.text()).toContain('AI 整理稿')
    expect(previewTabs.text()).toContain('测试用例')
    expect(previewTabs.text()).toContain('限制提示')
    expect(previewTabs.text()).not.toContain('原始表格/追踪视图')
    expect(previewTabs.text()).not.toContain('用例蓝图')
    expect(wrapper.find('.tcg-blueprint-summary').exists()).toBe(false)
  })

  it('keeps generation disabled until a snapshot is read', async () => {
    const wrapper = mountView()

    expect(wrapper.find('[data-test="preview-generate-button"]').attributes('disabled')).toBeDefined()

    await addPlanningSource(wrapper)
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(readPlanningSnapshotMock).toHaveBeenCalledWith({
      source_type: 'uploaded_excel',
      source: {
        id: 'new_plan',
        type: 'local_excel',
        pathOrUrl: 'D:/plan/new_plan.xlsx',
      },
      sheet_name: '新增Sheet',
    })
    expect(wrapper.find('[data-test="preview-generate-button"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('按配置开放入口')
  })

  it('automatically requests a snapshot brief after reading the planning snapshot', async () => {
    const wrapper = mountView()
    await flushPromises()

    await addPlanningSource(wrapper)
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(readPlanningSnapshotBriefMock).toHaveBeenCalledTimes(1)
    expect(readPlanningSnapshotBriefMock).toHaveBeenCalledWith({
      planning_snapshot: snapshotResponse.data,
    })
  })

  it('keeps the planning snapshot and allows generation when snapshot brief fails', async () => {
    readPlanningSnapshotBriefMock.mockRejectedValueOnce(new Error('brief failed'))
    const wrapper = mountView()
    await flushPromises()

    await addPlanningSource(wrapper)
    await selectCategory(wrapper, '礼包用例')
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(readPlanningSnapshotBriefMock).toHaveBeenCalledWith({
      planning_snapshot: snapshotResponse.data,
    })
    expect(wrapper.text()).toContain('按配置开放入口')
    expect(wrapper.find('[data-test="preview-generate-button"]').attributes('disabled')).toBeUndefined()

    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(generateTestCasesMock).toHaveBeenCalledWith({
      planning_snapshot: snapshotResponse.data,
      reference_ids: [],
      primary_reference_id: null,
      primary_reference_sheet_name: null,
    })
    expect(generateTestCasesMock.mock.calls[0][0]).not.toHaveProperty('snapshot_brief_markdown')
    expect(generateTestCasesMock.mock.calls[0][0]).not.toHaveProperty('generation_options')
  })

  it('does not wait for a pending snapshot brief before generating cases', async () => {
    let resolveSnapshotBrief!: (value: typeof snapshotBriefResponse) => void
    const pendingSnapshotBrief = new Promise<typeof snapshotBriefResponse>((resolve) => {
      resolveSnapshotBrief = resolve
    })
    readPlanningSnapshotBriefMock.mockReturnValueOnce(pendingSnapshotBrief)
    const wrapper = mountView()
    await flushPromises()

    await addPlanningSource(wrapper)
    await selectCategory(wrapper, '礼包用例')
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(readPlanningSnapshotBriefMock).toHaveBeenCalledWith({
      planning_snapshot: snapshotResponse.data,
    })

    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await Promise.resolve()

    expect(generateTestCasesMock).toHaveBeenCalledWith({
      planning_snapshot: snapshotResponse.data,
      reference_ids: [],
      primary_reference_id: null,
      primary_reference_sheet_name: null,
    })
    expect(generateTestCasesMock.mock.calls[0][0]).not.toHaveProperty('snapshot_brief_markdown')
    resolveSnapshotBrief(snapshotBriefResponse)
    await flushPromises()
  })

  it('generates cases without reference selection and renders result sections', async () => {
    const wrapper = mountView()
    await flushPromises()

    await addPlanningSource(wrapper)
    await selectCategory(wrapper, '礼包用例')

    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(generateTestCasesMock).toHaveBeenCalledWith({
      planning_snapshot: snapshotResponse.data,
      reference_ids: [],
      primary_reference_id: null,
      primary_reference_sheet_name: null,
      snapshot_brief_markdown: snapshotBriefMarkdown,
    })
    expect(wrapper.text()).toContain('活动入口按配置展示')
    expect(wrapper.text()).toContain('入口图语义未读取，需人工确认。')
    expect(wrapper.text()).toContain('未使用参考案例增强。')
    expect(wrapper.text()).toContain('用例总数 1')
  })

  it('passes selected reference ids and primary reference sheet to generation', async () => {
    const wrapper = mountView()
    await flushPromises()

    await addPlanningSource(wrapper)
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(generateTestCasesMock).toHaveBeenCalledWith({
      planning_snapshot: snapshotResponse.data,
      reference_ids: [201],
      primary_reference_id: 201,
      primary_reference_sheet_name: '测试用例',
      snapshot_brief_markdown: snapshotBriefMarkdown,
    })
  })

  it('passes completed snapshot brief markdown as top-level generation context', async () => {
    const wrapper = mountView()
    await flushPromises()

    await addPlanningSource(wrapper)
    await selectCategory(wrapper, '礼包用例')
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(generateTestCasesMock).toHaveBeenCalledWith({
      planning_snapshot: snapshotResponse.data,
      reference_ids: [],
      primary_reference_id: null,
      primary_reference_sheet_name: null,
      snapshot_brief_markdown: snapshotBriefMarkdown,
    })
    expect(generateTestCasesMock.mock.calls[0][0]).not.toHaveProperty('generation_options')
  })

  it('copies generated snapshot brief markdown', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(globalThis.navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    const wrapper = mountView()
    await flushPromises()

    await addPlanningSource(wrapper)
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="copy-snapshot-brief-button"]').trigger('click')
    await flushPromises()

    expect(writeText).toHaveBeenCalledWith(snapshotBriefMarkdown)
  })

  it('retries snapshot brief generation from the failure state', async () => {
    readPlanningSnapshotBriefMock.mockRejectedValueOnce(new Error('brief failed'))
    const wrapper = mountView()
    await flushPromises()

    await addPlanningSource(wrapper)
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('brief failed')
    expect(readPlanningSnapshotBriefMock).toHaveBeenCalledTimes(1)

    await wrapper.find('[data-test="retry-snapshot-brief-error-button"]').trigger('click')
    await flushPromises()

    expect(readPlanningSnapshotBriefMock).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-test="snapshot-brief-markdown"]').text()).toContain('按配置开放活动入口')
  })

  it('exports using the current in-memory generation result', async () => {
    generateTestCasesMock.mockResolvedValueOnce(generationWithReferenceResponse)
    const wrapper = mountView()
    await flushPromises()

    await addPlanningSource(wrapper)
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-export-button"]').trigger('click')
    await flushPromises()

    expect(exportTestCaseWorkbookMock).toHaveBeenCalledWith({
      blueprint: generationResponse.data.blueprint,
      cases: generationResponse.data.cases,
      warnings: generationResponse.data.warnings,
      stats: generationResponse.data.stats,
      export_columns: generationWithReferenceResponse.data.export_columns,
      primary_reference_profile: generationWithReferenceResponse.data.primary_reference_profile,
      source_summary: snapshotResponse.data.source_summary,
    })
  })

  it('disables export after reference settings make the generated result stale', async () => {
    const wrapper = mountView()
    await flushPromises()

    await addPlanningSource(wrapper)
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="preview-export-button"]').attributes('disabled')).toBeUndefined()

    await findButton(findReferenceRow(wrapper, '202'), '设为主参考')?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('主参考案例已切换，需要重新生成。')
    expect(wrapper.find('[data-test="preview-export-button"]').attributes('disabled')).toBeDefined()
    await wrapper.find('[data-test="preview-export-button"]').trigger('click')
    expect(exportTestCaseWorkbookMock).not.toHaveBeenCalled()
  })

  it('clears snapshot and generated result after switching planning source', async () => {
    const wrapper = mountView()

    await addPlanningSource(wrapper)
    await wrapper.find('[data-test="read-snapshot-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="preview-generate-button"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('活动入口按配置展示')

    await addPlanningSource(wrapper)

    expect(wrapper.text()).not.toContain('活动入口按配置展示')
    expect(wrapper.text()).toContain('生成前先读取策划案快照')
    expect(wrapper.find('[data-test="preview-generate-button"]').attributes('disabled')).toBeDefined()
  })

  it('keeps the preview module on the page scroll flow instead of clipping it internally', () => {
    const source = readFileSync('src/views/TestCaseGeneratorView.vue', 'utf-8')

    expect(source).not.toMatch(/\.tcg-preview\s*\{[^}]*max-height/s)
    expect(source).not.toMatch(/\.tcg-preview\s*\{[^}]*overflow:\s*hidden/s)
    expect(source).toMatch(/\.tcg-content\s*\{[^}]*overflow-y:\s*auto/s)
  })

  it('loads reference categories and files on page load', async () => {
    const wrapper = mountView()
    await flushPromises()

    const categoryPills = wrapper.findAll('[data-test="reference-category-pill"]').map((pill) => pill.text())

    expect(fetchReferenceCategoriesMock).toHaveBeenCalled()
    expect(fetchReferenceFilesMock).toHaveBeenCalledWith()
    expect(wrapper.find('.tcg-content > [data-test="reference-library"]').exists()).toBe(true)
    expect(wrapper.find('.tcg-setup [data-test="reference-library"]').exists()).toBe(false)
    expect(categoryPills).toEqual(expect.arrayContaining(['活动用例3', '礼包用例6', 'UI 通用1', '未分类1']))
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

  it('clears selected references and primary reference when switching to a category without recommended primary', async () => {
    const wrapper = mountView()
    await flushPromises()

    await selectCategory(wrapper, '礼包用例')

    const primarySelect = wrapper.find('[data-test="primary-reference-select"]')
    expect(primarySelect.attributes('data-disabled')).toBe('true')
    expect(primarySelect.text()).toContain('可选：先选择参考案例后指定主参考')
    expect(wrapper.text()).toContain('当前分类未选择参考案例')
    expect(wrapper.text()).toContain('参考案例分类已切换，本次将按 qa-case 标准逻辑生成。')
  })

  it('selects the recommended primary reference by default when switching to a category that has one', async () => {
    const wrapper = mountView()
    await flushPromises()

    await selectCategory(wrapper, '礼包用例')
    await selectCategory(wrapper, 'UI 通用')

    const uiPrimaryRow = findReferenceRow(wrapper, '204')
    const primarySelect = wrapper.find('[data-test="primary-reference-select"]')

    expect((uiPrimaryRow.find('[data-test="reference-checkbox"]').element as HTMLInputElement).checked).toBe(true)
    expect(uiPrimaryRow.classes()).toContain('is-primary')
    expect(primarySelect.attributes('data-disabled')).toBe('false')
    expect(primarySelect.text()).toContain('UI 通用冒烟.xlsx')
  })

  it('allows selecting multiple references within the same category', async () => {
    const wrapper = mountView()
    await flushPromises()

    const markdownRow = findReferenceRow(wrapper, '202')
    const txtRow = findReferenceRow(wrapper, '203')

    await markdownRow.find('[data-test="reference-checkbox"]').setValue(true)
    await txtRow.find('[data-test="reference-checkbox"]').setValue(true)

    expect((markdownRow.find('[data-test="reference-checkbox"]').element as HTMLInputElement).checked).toBe(true)
    expect((txtRow.find('[data-test="reference-checkbox"]').element as HTMLInputElement).checked).toBe(true)
    expect(wrapper.find('[data-test="primary-reference-select"]').text()).toContain('活动回归模板.xlsx')
    expect(wrapper.find('[data-test="primary-reference-select"]').text()).toContain('礼包活动边界.md')
    expect(wrapper.find('[data-test="primary-reference-select"]').text()).toContain('UI 通用检查.txt')
  })

  it('setting a file as primary reference automatically selects it', async () => {
    const wrapper = mountView()
    await flushPromises()

    const txtRow = findReferenceRow(wrapper, '203')

    await findButton(txtRow, '设为主参考')?.trigger('click')

    expect((txtRow.find('[data-test="reference-checkbox"]').element as HTMLInputElement).checked).toBe(true)
    expect(txtRow.classes()).toContain('is-primary')
    expect(wrapper.find('[data-test="primary-reference-select"]').text()).toContain('UI 通用检查.txt')
    expect(wrapper.text()).toContain('主参考案例已切换，需要重新生成。')
  })

  it('calls backend-admin reference actions from the more dialog', async () => {
    const wrapper = mountView()
    await flushPromises()

    await findReferenceRow(wrapper, '203').findAll('button')[2]?.trigger('click')
    await findButton(wrapper, '设为推荐主参考')?.trigger('click')
    await flushPromises()

    expect(setRecommendedPrimaryReferenceMock).toHaveBeenCalledWith(203)

    await findReferenceRow(wrapper, '203').findAll('button')[2]?.trigger('click')
    await findButton(wrapper, '删除文件')?.trigger('click')
    await flushPromises()

    expect(deleteReferenceFileMock).toHaveBeenCalledWith(203)
  })

  it('only lists selected references in the primary reference select', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('[data-test="primary-reference-select"]').text()).toContain('活动回归模板.xlsx')
    expect(wrapper.find('[data-test="primary-reference-select"]').text()).not.toContain('礼包活动边界.md')

    await findReferenceRow(wrapper, '202').find('[data-test="reference-checkbox"]').setValue(true)

    expect(wrapper.find('[data-test="primary-reference-select"]').text()).toContain('活动回归模板.xlsx')
    expect(wrapper.find('[data-test="primary-reference-select"]').text()).toContain('礼包活动边界.md')
    expect(wrapper.find('[data-test="primary-reference-select"]').text()).not.toContain('UI 通用检查.txt')
  })

  it('shows sheet options for Excel primary reference and disables sheet selection for Markdown/TXT', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('[data-test="primary-reference-sheet-select"]').attributes('data-disabled')).toBe('false')
    expect(wrapper.text()).toContain('测试用例')
    expect(wrapper.text()).toContain('历史回归')

    await findButton(findReferenceRow(wrapper, '202'), '设为主参考')?.trigger('click')

    const sheetSelect = wrapper.find('[data-test="primary-reference-sheet-select"]')
    expect(sheetSelect.attributes('data-disabled')).toBe('true')
    expect(sheetSelect.text()).toContain('当前参考案例无 Sheet')
  })

  it('shows empty state when search has no reference matches', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('[data-test="reference-search"]').setValue('不存在的画像')

    expect(wrapper.text()).toContain('没有匹配的参考案例')
    expect(wrapper.text()).toContain('清空筛选')
  })

  it('paginates reference files in pages of five', async () => {
    const wrapper = mountView()
    await flushPromises()

    await selectCategory(wrapper, '礼包用例')

    expect(wrapper.findAll('[data-test="reference-file-row"]')).toHaveLength(5)
    expect(wrapper.text()).toContain('第 1-5 条 / 共 6 条')
    expect(wrapper.findAll('[data-test="reference-page-number"]').map((button) => button.text())).toEqual([
      '1',
      '2',
    ])

    await wrapper.find('[data-test="reference-page-next"]').trigger('click')

    expect(wrapper.findAll('[data-test="reference-file-row"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('第 6-6 条 / 共 6 条')
  })
})
