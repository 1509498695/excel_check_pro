import { describe, expect, it, vi } from 'vitest'

import {
  CONFIG_LOOKUP_SAMPLE_MARKDOWN,
  buildCredentialRows,
  buildRuleConfigOverview,
  canOpenRuleDetail,
  createConfigLookupRuleState,
  ruleCatalog,
} from '../../src/features/rule-configs/useConfigLookupRule'
import type {
  RuleConfigCredentialsStatus,
  RuleConfigRecord,
  RuleConfigVersion,
} from '../../src/types/ruleConfigs'
import { ApiRequestError } from '../../src/utils/apiFetch'

const record: RuleConfigRecord = {
  project_id: 1,
  rule_family: 'config_lookup',
  content_md: '查询类型: 礼包',
  parsed_config_json: {
    queries: [{ query_type: '礼包', query_root: 'game_datas', pages: [{ name: 'AbsolutePack' }] }],
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

const versions: RuleConfigVersion[] = [
  {
    project_id: 1,
    rule_family: 'config_lookup',
    version: 2,
    content_md: '查询类型: 礼包',
    parsed_config_json: record.parsed_config_json,
    status: 'published',
    action: 'publish',
    operator: 2,
    description: '发布规则',
    created_at: '2024-05-27T02:32:18',
  },
  {
    project_id: 1,
    rule_family: 'config_lookup',
    version: 1,
    content_md: '查询类型: 礼包',
    parsed_config_json: record.parsed_config_json,
    status: 'draft',
    action: 'save_draft',
    operator: 1,
    description: '保存草稿',
    created_at: '2024-05-26T18:15:42',
  },
]

const credentials: RuleConfigCredentialsStatus = {
  svn: {
    configured: true,
    account_masked: 's******n',
    updated_at: '2024-05-27T01:20:11',
  },
  ai: {
    configured: true,
    provider: 'openai',
    model: 'gpt-compatible',
    masked_api_key: 'sk-********',
    credential_masked: 'sk-legacy',
    last_test_status: 'success',
    last_test_at: '2024-05-27T01:21:11',
    updated_at: '2024-05-27T01:20:11',
  },
}

function response<T>(data: T) {
  return { code: 200, msg: 'ok', data }
}

function createApi(overrides: Partial<ReturnType<typeof createBaseApi>> = {}) {
  return { ...createBaseApi(), ...overrides }
}

function createBaseApi() {
  return {
    getCurrent: vi.fn().mockResolvedValue(response(record)),
    listVersions: vi.fn().mockResolvedValue(response({ items: versions, total: versions.length })),
    getCredentialsStatus: vi.fn().mockResolvedValue(response(credentials)),
    validate: vi.fn().mockResolvedValue(response({
      ok: true,
      parsed_config_json: record.parsed_config_json,
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
    saveDraft: vi.fn().mockResolvedValue(response({ ...record, status: 'draft', optimistic_lock_version: 7 })),
    publish: vi.fn().mockResolvedValue(response({
      ...record,
      status: 'published',
      optimistic_lock_version: 8,
      validation: {
        ok: true,
        parsed_config_json: record.parsed_config_json,
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
    rollback: vi.fn().mockResolvedValue(response({ ...record, status: 'draft', optimistic_lock_version: 9 })),
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
            { field: 'INT_PackageId', label: 'INT_PackageId', value: '1001' },
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
  it('loads current config, versions, credentials, markdown and baseVersion', async () => {
    const api = createApi()
    const state = createConfigLookupRuleState(api, { allowDevFallback: false })

    await state.load()

    expect(api.getCurrent).toHaveBeenCalled()
    expect(api.listVersions).toHaveBeenCalled()
    expect(api.getCredentialsStatus).toHaveBeenCalled()
    expect(state.record.value.optimistic_lock_version).toBe(6)
    expect(state.baseVersion.value).toBe(6)
    expect(state.contentMd.value).toBe('查询类型: 礼包')
    expect(state.versions.value).toHaveLength(2)
    expect(state.credentials.value?.svn.account_masked).toBe('s******n')
  })

  it('uses sample markdown for empty records', async () => {
    const api = createApi({
      getCurrent: vi.fn().mockResolvedValue(response({
        ...record,
        content_md: '',
        status: 'empty',
        optimistic_lock_version: 0,
      })),
    })
    const state = createConfigLookupRuleState(api, { allowDevFallback: false })

    await state.load()

    expect(state.contentMd.value).toContain(CONFIG_LOOKUP_SAMPLE_MARKDOWN.split('\n')[0])
  })

  it('builds rule overview from current config and version history', () => {
    const overview = buildRuleConfigOverview(record, versions)

    expect(overview.map((item) => item.value)).toEqual([
      '3',
      '1',
      '0',
      '0',
      '2024/05/27 02:32:18',
    ])
  })

  it('saves draft with current baseVersion and updates state', async () => {
    const api = createApi()
    const state = createConfigLookupRuleState(api, { allowDevFallback: false })
    await state.load()

    const result = await state.saveDraft()

    expect(result.ok).toBe(true)
    expect(api.saveDraft).toHaveBeenCalledWith({
      contentMd: '查询类型: 礼包',
      baseVersion: 6,
      description: '保存草稿',
    })
    expect(state.baseVersion.value).toBe(7)
  })

  it('publishes successfully and returns immediate-effect message', async () => {
    const api = createApi()
    const state = createConfigLookupRuleState(api, { allowDevFallback: false })
    await state.load()

    const result = await state.publish()

    expect(result).toEqual({
      ok: true,
      message: '发布后已立即生效，无需重启机器人。',
    })
    expect(api.publish).toHaveBeenCalledWith({
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
    const api = createApi({ publish: vi.fn().mockRejectedValue(error) })
    const state = createConfigLookupRuleState(api, { allowDevFallback: false })
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
    const api = createApi({ saveDraft: vi.fn().mockRejectedValue(error) })
    const state = createConfigLookupRuleState(api, { allowDevFallback: false })
    await state.load()
    state.contentMd.value = '本地未保存内容'

    const result = await state.saveDraft()

    expect(result.ok).toBe(false)
    expect(state.conflictMessage.value).toContain('规则已被他人更新')
    expect(state.contentMd.value).toBe('本地未保存内容')
  })

  it('rolls back to a version and refreshes version history', async () => {
    const api = createApi()
    const state = createConfigLookupRuleState(api, { allowDevFallback: false })
    await state.load()

    const result = await state.rollback(1)

    expect(result.ok).toBe(true)
    expect(api.rollback).toHaveBeenCalledWith(1, {
      baseVersion: 6,
      description: '回滚到 v1',
    })
    expect(api.listVersions).toHaveBeenCalledTimes(2)
    expect(state.baseVersion.value).toBe(9)
  })

  it('runs trial with current draft content without changing record state', async () => {
    const api = createApi()
    const state = createConfigLookupRuleState(api, { allowDevFallback: false })
    await state.load()
    state.contentMd.value = '本地草稿内容'

    const result = await state.runTrial({
      queryType: '礼包',
      versionedConfigFolder: '/datas_qa88',
      lookupInput: '1001',
      useCurrentDraft: true,
    })

    expect(result.ok).toBe(true)
    expect(api.trial).toHaveBeenCalledWith({
      queryType: '礼包',
      versionedConfigFolder: '/datas_qa88',
      lookupInput: '1001',
      useCurrentDraft: true,
      contentMd: '本地草稿内容',
    })
    expect(state.trialResult.value?.status).toBe('hit')
    expect(state.trialErrorMessage.value).toBe('')
    expect(state.contentMd.value).toBe('本地草稿内容')
    expect(state.baseVersion.value).toBe(6)
  })

  it('stores trial candidates returned by AI matching', async () => {
    const api = createApi({
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
    const state = createConfigLookupRuleState(api, { allowDevFallback: false })
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
    const api = createApi({
      trial: vi.fn().mockResolvedValue(response({
        status: 'not_found',
        message: '未找到版本配置目录：/datas_missing，请确认目录是否存在于数据根 game_datas 下',
        results: [],
        candidates: [],
        ai: { used: false },
      })),
    })
    const state = createConfigLookupRuleState(api, { allowDevFallback: false })
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
    expect(state.baseVersion.value).toBe(6)
  })

  it('keeps trial validation errors separate from editor validation state', async () => {
    const error = new ApiRequestError('规则结构校验失败', 400, {
      code: 'RULE_CONFIG_VALIDATION_FAILED',
      errors: ['缺少必填字段：数据根'],
      summary: {},
    })
    const api = createApi({ trial: vi.fn().mockRejectedValue(error) })
    const state = createConfigLookupRuleState(api, { allowDevFallback: false })
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

  it('shows only masked credential status for non-admins', () => {
    const rows = buildCredentialRows(credentials, false)

    expect(rows).toEqual([
      expect.objectContaining({
        label: 'SVN 凭据',
        accountLabel: '账号：s******n',
        secretLabel: '密码：已脱敏',
        canManage: false,
      }),
      expect.objectContaining({
        label: 'AI 凭据',
        accountLabel: '供应商：openai / 模型：gpt-compatible',
        secretLabel: '密钥：sk-******** / 测试：成功',
        canManage: false,
      }),
    ])
  })

  it('keeps future rule families from entering edit mode', () => {
    const projectCheck = ruleCatalog.find((rule) => rule.id === 'project_check')

    expect(projectCheck).toBeTruthy()
    expect(canOpenRuleDetail(projectCheck!)).toBe(false)
  })
})
