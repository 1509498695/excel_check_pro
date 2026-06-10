import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  apiGetRuleConfig,
  apiGetRuleConfigCredentialsStatus,
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

  it('loads current config_lookup rule config', async () => {
    await apiGetRuleConfig()

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/rule-configs/config_lookup')
  })

  it('loads version history and credentials status', async () => {
    await apiListRuleConfigVersions()
    await apiGetRuleConfigCredentialsStatus()

    expect(apiFetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/rule-configs/config_lookup/versions',
    )
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/rule-configs/config_lookup/credentials/status',
    )
  })

  it('validates markdown without persisting', async () => {
    await apiValidateRuleConfig('查询类型: 礼包')

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/rule-configs/config_lookup/validate', {
      method: 'POST',
      body: JSON.stringify({ content_md: '查询类型: 礼包' }),
    })
  })

  it('runs config lookup trial with optional current draft content', async () => {
    await apiTrialRuleConfig({
      queryType: '礼包',
      versionedConfigFolder: '/datas_qa88',
      lookupInput: '1001',
      useCurrentDraft: true,
      contentMd: '查询类型: 礼包',
    })

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/rule-configs/config_lookup/trial', {
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
    await apiSaveRuleConfigDraft({
      contentMd: '草稿',
      baseVersion: 7,
      description: '保存草稿',
    })
    await apiPublishRuleConfig({
      contentMd: '发布',
      baseVersion: 8,
      description: '发布规则',
    })

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, '/api/v1/rule-configs/config_lookup/draft', {
      method: 'PUT',
      body: JSON.stringify({
        content_md: '草稿',
        expected_optimistic_lock_version: 7,
        description: '保存草稿',
      }),
    })
    expect(apiFetchMock).toHaveBeenNthCalledWith(2, '/api/v1/rule-configs/config_lookup/publish', {
      method: 'POST',
      body: JSON.stringify({
        content_md: '发布',
        expected_optimistic_lock_version: 8,
        description: '发布规则',
      }),
    })
  })

  it('maps baseVersion to expected optimistic lock when rolling back', async () => {
    await apiRollbackRuleConfigVersion(3, {
      baseVersion: 9,
      description: '回滚到 v3',
    })

    expect(apiFetchMock).toHaveBeenCalledWith(
      '/api/v1/rule-configs/config_lookup/versions/3/rollback',
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
