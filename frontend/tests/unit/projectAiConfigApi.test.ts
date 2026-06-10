import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  apiDeleteProjectAiConfig,
  apiGetProjectAiConfig,
  apiSaveProjectAiConfig,
  apiTestProjectAiConfig,
} from '../../src/api/projectAiConfig'
import { apiFetch } from '../../src/utils/apiFetch'

vi.mock('../../src/utils/apiFetch', () => ({
  apiFetch: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)

describe('project AI config api', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    apiFetchMock.mockResolvedValue({ code: 200, msg: 'ok', data: {} })
  })

  it('loads project AI config by project id', async () => {
    await apiGetProjectAiConfig(12)

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/admin/projects/12/ai-config')
  })

  it('saves project AI config with thresholds and API key', async () => {
    await apiSaveProjectAiConfig(12, {
      provider: 'openai',
      model: 'gpt-4o-mini',
      base_url: 'https://api.openai.com/v1',
      api_key: 'sk-project-secret',
      enabled: true,
      auto_match_threshold: 0.9,
      candidate_threshold: 0.6,
      max_candidates: 10,
    })

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/admin/projects/12/ai-config', {
      method: 'PUT',
      body: JSON.stringify({
        provider: 'openai',
        model: 'gpt-4o-mini',
        base_url: 'https://api.openai.com/v1',
        api_key: 'sk-project-secret',
        enabled: true,
        auto_match_threshold: 0.9,
        candidate_threshold: 0.6,
        max_candidates: 10,
      }),
    })
  })

  it('does not submit blank API key as a clear operation', async () => {
    await apiSaveProjectAiConfig(12, {
      provider: 'openai',
      model: 'gpt-4o-mini',
      base_url: 'https://api.openai.com/v1',
      api_key: null,
      enabled: true,
      auto_match_threshold: 0.9,
      candidate_threshold: 0.6,
      max_candidates: 10,
    })

    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/admin/projects/12/ai-config', {
      method: 'PUT',
      body: JSON.stringify({
        provider: 'openai',
        model: 'gpt-4o-mini',
        base_url: 'https://api.openai.com/v1',
        enabled: true,
        auto_match_threshold: 0.9,
        candidate_threshold: 0.6,
        max_candidates: 10,
      }),
    })
  })

  it('calls project level test and delete endpoints without copy-from-me', async () => {
    await apiTestProjectAiConfig(12)
    await apiDeleteProjectAiConfig(12)

    expect(apiFetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/admin/projects/12/ai-config/test',
      { method: 'POST' },
    )
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/admin/projects/12/ai-config',
      { method: 'DELETE' },
    )
    expect(apiFetchMock.mock.calls.map(([path]) => path)).not.toContain(
      '/api/v1/admin/projects/12/ai-config/copy-from-me',
    )
  })
})
