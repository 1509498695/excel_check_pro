import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  apiGetFeishuBotConfig,
  apiTestProjectSvnCredential,
  apiUpsertFeishuBotConfig,
} from '../../src/api/admin'
import { apiFetch } from '../../src/utils/apiFetch'

vi.mock('../../src/utils/apiFetch', () => ({
  apiFetch: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)

describe('admin feishu bot api', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    apiFetchMock.mockResolvedValue({ code: 200, msg: 'ok', data: {} })
  })

  it('loads feishu bot config by project id', async () => {
    await apiGetFeishuBotConfig(12)

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/admin/projects/12/feishu-bot')
  })

  it('tests project SVN credential through dedicated endpoint', async () => {
    await apiTestProjectSvnCredential(12)

    expect(apiFetchMock).toHaveBeenCalledWith(
      '/api/v1/admin/projects/12/svn-credential/test',
      { method: 'POST' },
    )
  })

  it('saves legacy base config fields', async () => {
    await apiUpsertFeishuBotConfig(12, {
      app_id: 'cli_demo',
      app_secret: 'secret',
      default_chat_id: 'oc_default',
      allowed_open_ids: '',
      local_download_roots: 'D:/downloads',
      svn_download_roots: 'D:/svn',
      allowed_download_suffixes: '.xls,.xlsx',
    })

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/admin/projects/12/feishu-bot', {
      method: 'PUT',
      body: JSON.stringify({
        app_id: 'cli_demo',
        app_secret: 'secret',
        default_chat_id: 'oc_default',
        allowed_open_ids: '',
        local_download_roots: 'D:/downloads',
        svn_download_roots: 'D:/svn',
        allowed_download_suffixes: '.xls,.xlsx',
      }),
    })
  })

  it('saves extended config fields through the same endpoint', async () => {
    await apiUpsertFeishuBotConfig(12, {
      app_id: 'cli_demo',
      app_secret: null,
      bound_chat_ids: ['oc_default', 'oc_backup'],
      query_roots: [
        {
          alias: 'game_datas',
          display_name: '游戏配置主目录',
          svn_url: 'https://svn.example.com/game',
          enabled: true,
        },
      ],
      svn_credential: {
        username: 'svn_admin',
        password: 'svn_password',
      },
      ai_credential: {
        provider_preset: 'openai',
        base_url: 'https://api.openai.com/v1',
        model: 'gpt-5.4-mini',
        api_key: 'sk-project-secret',
        extra_headers: { 'X-Project': 'ExcelCheck' },
      },
      ai_match_params: {
        auto_match_threshold: 0.91,
        candidate_threshold: 0.61,
        max_candidates: 8,
      },
    })

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/admin/projects/12/feishu-bot', {
      method: 'PUT',
      body: JSON.stringify({
        app_id: 'cli_demo',
        bound_chat_ids: ['oc_default', 'oc_backup'],
        query_roots: [
          {
            alias: 'game_datas',
            display_name: '游戏配置主目录',
            svn_url: 'https://svn.example.com/game',
            enabled: true,
          },
        ],
        svn_credential: {
          username: 'svn_admin',
          password: 'svn_password',
        },
        ai_credential: {
          provider_preset: 'openai',
          base_url: 'https://api.openai.com/v1',
          model: 'gpt-5.4-mini',
          api_key: 'sk-project-secret',
          extra_headers: { 'X-Project': 'ExcelCheck' },
        },
        ai_match_params: {
          auto_match_threshold: 0.91,
          candidate_threshold: 0.61,
          max_candidates: 8,
        },
      }),
    })
  })

  it('does not send blank app secret as a clear operation', async () => {
    await apiUpsertFeishuBotConfig(12, {
      app_id: 'cli_demo',
      app_secret: null,
    })

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/admin/projects/12/feishu-bot', {
      method: 'PUT',
      body: JSON.stringify({ app_id: 'cli_demo' }),
    })
  })
})
