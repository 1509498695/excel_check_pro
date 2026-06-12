import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  apiCreateRuleConfig,
  apiGetRuleConfig,
  apiGetRuleConfigCredentialsStatus,
  apiListRuleConfigs,
  apiListRuleConfigVersions,
  apiPublishRuleConfig,
  apiRollbackRuleConfigVersion,
  apiSaveRuleConfigDraft,
  apiTrialRuleConfig,
  apiValidateRuleConfig,
} from '../../src/api/ruleConfigs'
import { apiFetch } from '../../src/utils/apiFetch'

vi.mock('../../src/utils/apiFetch', () => ({
  apiFetch: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)

describe('rule config api', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    apiFetchMock.mockResolvedValue({ code: 200, msg: 'ok', data: {} })
  })

  it('loads config_lookup query rule list', async () => {
    await apiListRuleConfigs()

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/rule-configs/config_lookup')
  })

  it('creates a query rule draft from markdown', async () => {
    await apiCreateRuleConfig({
      contentMd: '查询类型: 礼包',
      description: '创建礼包规则',
    })

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/rule-configs/config_lookup', {
      method: 'POST',
      body: JSON.stringify({
        content_md: '查询类型: 礼包',
        description: '创建礼包规则',
      }),
    })
  })

  it('loads a single rule, version history and credentials status', async () => {
    await apiGetRuleConfig(12)
    await apiListRuleConfigVersions(12)
    await apiGetRuleConfigCredentialsStatus()

    expect(apiFetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/rule-configs/config_lookup/12',
    )
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/rule-configs/config_lookup/12/versions',
    )
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/v1/rule-configs/config_lookup/credentials/status',
    )
  })

  it('validates markdown for a single rule without persisting', async () => {
    await apiValidateRuleConfig(12, '查询类型: 礼包')

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/rule-configs/config_lookup/12/validate', {
      method: 'POST',
      body: JSON.stringify({ content_md: '查询类型: 礼包' }),
    })
  })

  it('runs config lookup trial against rule_id with optional current draft content', async () => {
    await apiTrialRuleConfig(12, {
      queryType: '礼包',
      versionedConfigFolder: '/datas_qa88',
      lookupInput: '1001',
      useCurrentDraft: true,
      contentMd: '查询类型: 礼包',
    })

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/rule-configs/config_lookup/12/trial', {
      method: 'POST',
      body: JSON.stringify({
        query_type: '礼包',
        versioned_config_folder: '/datas_qa88',
        lookup_input: '1001',
        use_current_draft: true,
        content_md: '查询类型: 礼包',
      }),
    })
  })

  it('maps baseVersion to expected optimistic lock when saving and publishing', async () => {
    await apiSaveRuleConfigDraft(12, {
      contentMd: '草稿',
      baseVersion: 7,
      description: '保存草稿',
    })
    await apiPublishRuleConfig(12, {
      contentMd: '发布',
      baseVersion: 8,
      description: '发布规则',
    })

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, '/api/v1/rule-configs/config_lookup/12/draft', {
      method: 'PUT',
      body: JSON.stringify({
        content_md: '草稿',
        expected_optimistic_lock_version: 7,
        description: '保存草稿',
      }),
    })
    expect(apiFetchMock).toHaveBeenNthCalledWith(2, '/api/v1/rule-configs/config_lookup/12/publish', {
      method: 'POST',
      body: JSON.stringify({
        content_md: '发布',
        expected_optimistic_lock_version: 8,
        description: '发布规则',
      }),
    })
  })

  it('maps baseVersion to expected optimistic lock when rolling back', async () => {
    await apiRollbackRuleConfigVersion(12, 3, {
      baseVersion: 9,
      description: '回滚到 v3',
    })

    expect(apiFetchMock).toHaveBeenCalledWith(
      '/api/v1/rule-configs/config_lookup/12/versions/3/rollback',
      {
        method: 'POST',
        body: JSON.stringify({
          expected_optimistic_lock_version: 9,
          description: '回滚到 v3',
        }),
      },
    )
  })
})
