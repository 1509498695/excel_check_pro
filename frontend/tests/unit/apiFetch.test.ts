// @vitest-environment happy-dom

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiRequestError, apiFetch, clearToken } from '../../src/utils/apiFetch'

describe('apiFetch', () => {
  beforeEach(() => {
    clearToken()
    vi.restoreAllMocks()
  })

  it('uses top-level msg from non-OK JSON responses', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 400,
          msg: '连接测试失败',
          data: { last_test_error_summary: '模型名或接口地址不存在。' },
        }),
        {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    )

    await expect(apiFetch('/api/v1/admin/projects/12/vision-ai-config/test')).rejects.toMatchObject(
      {
        name: 'ApiRequestError',
        message: '连接测试失败',
        status: 400,
      } satisfies Partial<ApiRequestError>,
    )
  })
})
