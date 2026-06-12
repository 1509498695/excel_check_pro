import { describe, expect, it, vi } from 'vitest'

import {
  CONFIG_LOOKUP_SAMPLE_MARKDOWN,
  buildCreateRuleMarkdown,
  createConfigLookupRuleDetailState,
  createConfigLookupRuleListState,
} from '../../src/features/rule-configs/useConfigLookupRule'
import type {
  RuleConfigRecord,
  RuleConfigVersion,
} from '../../src/types/ruleConfigs'
import { ApiRequestError } from '../../src/utils/apiFetch'

const publishedRecord: RuleConfigRecord = {
  id: 12,
  rule_id: 12,
  project_id: 1,
  rule_family: 'config_lookup',
  query_type: '礼包',
  content_md: '查询类型: 礼包',
  parsed_config_json: {
    rule_family: 'config_lookup',
    query_type: '礼包',
    query_root: 'game_datas',
    file: 'IAPConfig.xls',
    pages: [{ name: 'AbsolutePack', id_field: 'INT_PackageId', name_field: 'DESC' }],
  },
  status: 'published',
  draft_version: 2,
  published_version: 2,
  created_by: 1,
  updated_by: 2,
  published_by: 2,
  published_at: '2024-05-27T02:32:18',
  optimistic_lock_version: 6,
  created_at: '2024-05-26T18:15:42',
  updated_at: '2024-05-27T02:32:18',
}

const draftRecord: RuleConfigRecord = {
  ...publishedRecord,
  id: 13,
  rule_id: 13,
  query_type: '玩法开关',
  content_md: '查询类型: 玩法开关',
  status: 'draft',
  draft_version: 1,
  published_version: null,
  published_by: null,
  published_at: null,
  optimistic_lock_version: 1,
}

const versions: RuleConfigVersion[] = [
  {
    id: 20,
    rule_config_id: 12,
    rule_id: 12,
    project_id: 1,
    rule_family: 'config_lookup',
    query_type: '礼包',
    version: 2,
    content_md: '查询类型: 礼包',
    parsed_config_json: publishedRecord.parsed_config_json,
    status: 'published',
    action: 'publish',
    operator: 2,
    description: '发布规则',
    created_at: '2024-05-27T02:32:18',
  },
  {
    id: 19,
    rule_config_id: 12,
    rule_id: 12,
    project_id: 1,
    rule_family: 'config_lookup',
    query_type: '礼包',
    version: 1,
    content_md: '查询类型: 礼包',
    parsed_config_json: publishedRecord.parsed_config_json,
    status: 'draft',
    action: 'save_draft',
    operator: 1,
    description: '保存草稿',
    created_at: '2024-05-26T18:15:42',
  },
]

function response<T>(data: T) {
  return { code: 200, msg: 'ok', data }
}

function createListApi(overrides: Partial<ReturnType<typeof createBaseListApi>> = {}) {
  return { ...createBaseListApi(), ...overrides }
}

function createBaseListApi() {
  return {
    listRules: vi.fn().mockResolvedValue(response({
      items: [publishedRecord, draftRecord],
      total: 2,
    })),
    createRule: vi.fn().mockResolvedValue(response(draftRecord)),
  }
}

function createDetailApi(overrides: Partial<ReturnType<typeof createBaseDetailApi>> = {}) {
  return { ...createBaseDetailApi(), ...overrides }
}

function createBaseDetailApi() {
  return {
    getRule: vi.fn().mockResolvedValue(response(publishedRecord)),
    listVersions: vi.fn().mockResolvedValue(response({ items: versions, total: versions.length })),
    validate: vi.fn().mockResolvedValue(response({
      ok: true,
      parsed_config_json: publishedRecord.parsed_config_json,
      errors: [],
      summary: {
        query_count: 1,
        query_types: ['礼包'],
        query_roots: ['game_datas'],
        primary_files: ['IAPConfig.xls'],
        pages: [{ query_type: '礼包', names: ['AbsolutePack'] }],
        references: [],
      },
    })),
    saveDraft: vi.fn().mockResolvedValue(response({ ...publishedRecord, status: 'draft', optimistic_lock_version: 7 })),
    publish: vi.fn().mockResolvedValue(response({
      ...publishedRecord,
      status: 'published',
      optimistic_lock_version: 8,
      validation: {
        ok: true,
        parsed_config_json: publishedRecord.parsed_config_json,
        errors: [],
        summary: {
          query_count: 1,
          query_types: ['礼包'],
          query_roots: ['game_datas'],
          primary_files: ['IAPConfig.xls'],
          pages: [{ query_type: '礼包', names: ['AbsolutePack'] }],
          references: [],
        },
      },
    })),
    rollback: vi.fn().mockResolvedValue(response({ ...publishedRecord, status: 'draft', optimistic_lock_version: 9 })),
    trial: vi.fn().mockResolvedValue(response({
      status: 'hit',
      message: '查询命中',
      results: [
        {
          query_type: '礼包',
          page: 'AbsolutePack',
          id_value: '1001',
          name_value: '月卡',
          fields: [
            { field: 'INT_PackageId', label: 'ID字段', value: '1001' },
            { field: 'DESC', label: '礼包名称', value: '月卡' },
          ],
          warnings: [],
        },
      ],
      candidates: [],
      ai: {
        used: false,
        thresholds: {
          auto_match_threshold: 0.9,
          candidate_threshold: 0.6,
          max_candidates: 10,
        },
      },
    })),
  }
}

describe('rule config view model', () => {
  it('loads query rule list and builds KPI values from records', async () => {
    const api = createListApi()
    const state = createConfigLookupRuleListState(api)

    await state.load()

    expect(api.listRules).toHaveBeenCalled()
    expect(state.rules.value.map((rule) => rule.query_type)).toEqual(['礼包', '玩法开关'])
    expect(state.kpiItems.value.map((item) => item.value)).toEqual([
      '2',
      '1',
      '1',
      '0',
      '2024/05/27 02:32:18',
    ])
  })

  it('creates a rule from query type, query root and file name', async () => {
    const api = createListApi()
    const state = createConfigLookupRuleListState(api)

    const result = await state.createRule({
      queryType: '礼包',
      queryRoot: 'game_datas',
      fileName: 'IAPConfig.xls',
    })

    expect(result.ok).toBe(true)
    expect(result.ruleId).toBe(13)
    expect(api.createRule).toHaveBeenCalledWith({
      contentMd: buildCreateRuleMarkdown({
        queryType: '礼包',
        queryRoot: 'game_datas',
        fileName: 'IAPConfig.xls',
      }),
      description: '创建礼包查询规则',
    })
  })

  it('loads single rule detail, versions, markdown and baseVersion', async () => {
    const api = createDetailApi()
    const state = createConfigLookupRuleDetailState(12, api)

    await state.load()

    expect(api.getRule).toHaveBeenCalledWith(12)
    expect(api.listVersions).toHaveBeenCalledWith(12)
    expect(state.record.value?.rule_id).toBe(12)
    expect(state.contentMd.value).toBe('查询类型: 礼包')
    expect(state.baseVersion.value).toBe(6)
    expect(state.versionRows.value).toHaveLength(2)
  })

  it('uses sample markdown for empty rule content', async () => {
    const api = createDetailApi({
      getRule: vi.fn().mockResolvedValue(response({ ...publishedRecord, content_md: '' })),
    })
    const state = createConfigLookupRuleDetailState(12, api)

    await state.load()

    expect(state.contentMd.value).toContain(CONFIG_LOOKUP_SAMPLE_MARKDOWN.split('\n')[0])
  })

  it('marks published rules as query type locked and draft rules as editable', async () => {
    const publishedState = createConfigLookupRuleDetailState(12, createDetailApi())
    await publishedState.load()

    const draftState = createConfigLookupRuleDetailState(13, createDetailApi({
      getRule: vi.fn().mockResolvedValue(response(draftRecord)),
    }))
    await draftState.load()

    expect(publishedState.isQueryTypeLocked.value).toBe(true)
    expect(draftState.isQueryTypeLocked.value).toBe(false)
  })

  it('saves draft with current baseVersion and updates state', async () => {
    const api = createDetailApi()
    const state = createConfigLookupRuleDetailState(12, api)
    await state.load()

    const result = await state.saveDraft()

    expect(result.ok).toBe(true)
    expect(api.saveDraft).toHaveBeenCalledWith(12, {
      contentMd: '查询类型: 礼包',
      baseVersion: 6,
      description: '保存草稿',
    })
    expect(state.baseVersion.value).toBe(7)
  })

  it('prevents changing query type for rules that have been published', async () => {
    const api = createDetailApi()
    const state = createConfigLookupRuleDetailState(12, api)
    await state.load()
    state.contentMd.value = '查询类型: 新礼包'

    const result = await state.saveDraft()

    expect(result.ok).toBe(false)
    expect(result.message).toBe('已发布过的查询类型不允许直接改名')
    expect(state.validationErrors.value).toEqual(['已发布过的查询类型不允许直接改名'])
    expect(api.saveDraft).not.toHaveBeenCalled()
  })

  it('publishes successfully and returns immediate-effect message', async () => {
    const api = createDetailApi()
    const state = createConfigLookupRuleDetailState(12, api)
    await state.load()

    const result = await state.publish()

    expect(result).toEqual({
      ok: true,
      message: '发布后已立即生效，无需重启机器人。',
    })
    expect(api.publish).toHaveBeenCalledWith(12, {
      contentMd: '查询类型: 礼包',
      baseVersion: 6,
      description: '发布规则',
    })
    expect(state.baseVersion.value).toBe(8)
  })

  it('shows validation errors when publish fails', async () => {
    const error = new ApiRequestError('规则结构校验失败', 400, {
      code: 'RULE_CONFIG_VALIDATION_FAILED',
      errors: ['缺少必填字段：数据根'],
      summary: {},
    })
    const api = createDetailApi({ publish: vi.fn().mockRejectedValue(error) })
    const state = createConfigLookupRuleDetailState(12, api)
    await state.load()

    const result = await state.publish()

    expect(result.ok).toBe(false)
    expect(state.validationErrors.value).toEqual(['缺少必填字段：数据根'])
    expect(state.conflictMessage.value).toBe('')
  })

  it('shows conflict message without overwriting local markdown', async () => {
    const error = new ApiRequestError('版本冲突', 409, {
      code: 'RULE_CONFIG_VERSION_CONFLICT',
      current_optimistic_lock_version: 9,
    })
    const api = createDetailApi({ saveDraft: vi.fn().mockRejectedValue(error) })
    const state = createConfigLookupRuleDetailState(12, api)
    await state.load()
    state.contentMd.value = '本地未保存内容'

    const result = await state.saveDraft()

    expect(result.ok).toBe(false)
    expect(state.conflictMessage.value).toBe('规则已被他人更新，请刷新后手动合并。')
    expect(state.contentMd.value).toBe('本地未保存内容')
  })

  it('rolls back to a version and refreshes version history', async () => {
    const api = createDetailApi()
    const state = createConfigLookupRuleDetailState(12, api)
    await state.load()

    const result = await state.rollback(1)

    expect(result.ok).toBe(true)
    expect(api.rollback).toHaveBeenCalledWith(12, 1, {
      baseVersion: 6,
      description: '回滚到 v1',
    })
    expect(api.listVersions).toHaveBeenCalledTimes(2)
    expect(state.baseVersion.value).toBe(9)
  })

  it('runs trial with current draft content without changing record state', async () => {
    const api = createDetailApi()
    const state = createConfigLookupRuleDetailState(12, api)
    await state.load()
    state.contentMd.value = '本地草稿内容'

    const result = await state.runTrial({
      queryType: '礼包',
      versionedConfigFolder: '/datas_qa88',
      lookupInput: '1001',
      useCurrentDraft: true,
    })

    expect(result.ok).toBe(true)
    expect(api.trial).toHaveBeenCalledWith(12, {
      queryType: '礼包',
      versionedConfigFolder: '/datas_qa88',
      lookupInput: '1001',
      useCurrentDraft: true,
      contentMd: '本地草稿内容',
    })
    expect(state.trialResult.value?.status).toBe('hit')
    expect(state.contentMd.value).toBe('本地草稿内容')
    expect(state.baseVersion.value).toBe(6)
  })

  it('stores trial candidates returned by AI matching', async () => {
    const api = createDetailApi({
      trial: vi.fn().mockResolvedValue(response({
        status: 'candidates',
        message: '找到多个可能匹配的候选，请选择后查看详情',
        results: [],
        candidates: [
          { key: 'AbsolutePack:0:1001', page: 'AbsolutePack', id_value: '1001', name_value: '月卡', score: 0.82 },
        ],
        ai: {
          used: true,
          thresholds: {
            auto_match_threshold: 0.9,
            candidate_threshold: 0.6,
            max_candidates: 10,
          },
        },
      })),
    })
    const state = createConfigLookupRuleDetailState(12, api)
    await state.load()

    const result = await state.runTrial({
      queryType: '礼包',
      versionedConfigFolder: '/datas_qa88',
      lookupInput: '月卡',
      useCurrentDraft: false,
    })

    expect(result.ok).toBe(true)
    expect(state.trialResult.value?.candidates[0].name_value).toBe('月卡')
    expect(state.trialResult.value?.ai.used).toBe(true)
  })

  it('shows trial business errors without changing editor state', async () => {
    const api = createDetailApi({
      trial: vi.fn().mockResolvedValue(response({
        status: 'not_found',
        message: '未找到版本配置目录：/datas_missing，请确认目录是否存在于数据根 game_datas 下',
        results: [],
        candidates: [],
        ai: { used: false },
      })),
    })
    const state = createConfigLookupRuleDetailState(12, api)
    await state.load()
    state.contentMd.value = '本地草稿内容'

    const result = await state.runTrial({
      queryType: '礼包',
      versionedConfigFolder: '/datas_missing',
      lookupInput: '1001',
      useCurrentDraft: false,
    })

    expect(result.ok).toBe(false)
    expect(state.trialResult.value?.status).toBe('not_found')
    expect(state.trialErrorMessage.value).toBe(
      '未找到版本配置目录：/datas_missing，请确认目录是否存在于数据根 game_datas 下',
    )
    expect(state.trialErrorLines.value).toEqual([])
    expect(state.contentMd.value).toBe('本地草稿内容')
  })

  it('keeps trial validation errors separate from editor validation state', async () => {
    const error = new ApiRequestError('规则结构校验失败', 400, {
      code: 'RULE_CONFIG_VALIDATION_FAILED',
      errors: ['缺少必填字段：数据根'],
      summary: {},
    })
    const api = createDetailApi({ trial: vi.fn().mockRejectedValue(error) })
    const state = createConfigLookupRuleDetailState(12, api)
    await state.load()
    state.contentMd.value = '本地草稿内容'

    const result = await state.runTrial({
      queryType: '礼包',
      versionedConfigFolder: '/datas_qa88',
      lookupInput: '1001',
      useCurrentDraft: true,
    })

    expect(result.ok).toBe(false)
    expect(state.trialErrorMessage.value).toBe('规则结构校验失败')
    expect(state.trialErrorLines.value).toEqual(['缺少必填字段：数据根'])
    expect(state.validationErrors.value).toEqual([])
    expect(state.contentMd.value).toBe('本地草稿内容')
  })
})
