import { describe, expect, it } from 'vitest'

import {
  applyFeishuBotConfigToForm,
  buildFeishuBotConfigPayload,
  createFeishuBotConfigFormState,
  extractFeishuBotConfigError,
  mergeDefaultChatIdIntoBoundChats,
  validateFeishuBotConfigForm,
} from '../../src/features/admin/feishuBotConfigForm'
import { ApiRequestError } from '../../src/utils/apiFetch'
import type { FeishuBotConfig } from '../../src/types/admin'

const backendConfig: FeishuBotConfig = {
  configured: true,
  app_id: 'cli_demo',
  has_app_secret: true,
  default_chat_id: 'oc_default',
  bound_chat_ids: ['oc_default', 'oc_backup'],
  allowed_open_ids: ['ou_a', 'ou_b'],
  local_download_roots: ['D:/downloads'],
  svn_download_roots: ['D:/svn'],
  allowed_download_suffixes: ['.xls', '.xlsx'],
  query_roots: [
    {
      alias: 'game_datas',
      display_name: '游戏配置主目录',
      svn_url: 'https://svn.example.com/game',
      enabled: true,
    },
  ],
  svn_credential: {
    configured: true,
    username_masked: 'svn_admin',
    updated_at: '2024-05-27T01:20:11',
  },
  ai_credential: {
    configured: true,
    provider_preset: 'openai',
    base_url: 'https://api.openai.com/v1',
    model: 'gpt-5.4-mini',
    api_key_masked: 'sk-***cret',
    has_extra_headers: true,
    updated_at: '2024-05-27T01:20:11',
  },
  ai_match_params: {
    auto_match_threshold: 0.91,
    candidate_threshold: 0.61,
    max_candidates: 8,
  },
  connection_state: 'active',
  updated_at: '2024-05-27T02:32:18',
}

describe('feishu bot config form model', () => {
  it('hydrates editable form and masked credentials from backend config', () => {
    const form = applyFeishuBotConfigToForm(backendConfig)

    expect(form.appId).toBe('cli_demo')
    expect(form.appSecret).toBe('')
    expect(form.boundChatIdsText).toBe('oc_default\noc_backup')
    expect(form.queryRoots).toEqual([
      {
        alias: 'game_datas',
        displayName: '游戏配置主目录',
        svnUrl: 'https://svn.example.com/game',
        enabled: true,
      },
    ])
    expect(form.svnCredential.username).toBe('svn_admin')
    expect(form.svnCredential.password).toBe('')
    expect(form.aiCredential.providerPreset).toBe('openai')
    expect(form.aiCredential.apiKey).toBe('')
    expect(form.aiCredential.maskedApiKey).toBe('sk-***cret')
    expect(form.aiMatchParams.maxCandidates).toBe('8')
  })

  it('builds payload for bound chats query roots and SVN credentials', () => {
    const form = applyFeishuBotConfigToForm(backendConfig)
    form.svnCredential.isEditing = true
    form.svnCredential.password = 'svn_password'

    const payload = buildFeishuBotConfigPayload(form, { hasAppSecret: true })

    expect(payload).toEqual({
      app_id: 'cli_demo',
      app_secret: null,
      default_chat_id: 'oc_default',
      allowed_open_ids: 'ou_a\nou_b',
      local_download_roots: 'D:/downloads',
      svn_download_roots: 'D:/svn',
      allowed_download_suffixes: '.xls,.xlsx',
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
    })
  })

  it('merges default chat id into bound chat list while preserving order', () => {
    expect(mergeDefaultChatIdIntoBoundChats('oc_default', 'oc_other')).toBe(
      'oc_other\noc_default',
    )
    expect(mergeDefaultChatIdIntoBoundChats('oc_default', '')).toBe('oc_default')
    expect(mergeDefaultChatIdIntoBoundChats('oc_default', 'oc_default\noc_other')).toBe(
      'oc_default\noc_other',
    )
  })

  it('builds payload with default chat id in bound chats even when omitted by user', () => {
    const form = createFeishuBotConfigFormState()
    form.appId = 'cli_demo'
    form.appSecret = 'secret'
    form.defaultChatId = 'oc_default'
    form.boundChatIdsText = ''

    const payload = buildFeishuBotConfigPayload(form, { hasAppSecret: false })

    expect(payload.bound_chat_ids).toEqual(['oc_default'])
  })

  it('validates query root rows after auto-merging default chat membership', () => {
    const form = createFeishuBotConfigFormState()
    form.appId = 'cli_demo'
    form.appSecret = 'secret'
    form.defaultChatId = 'oc_default'
    form.boundChatIdsText = 'oc_other'
    form.queryRoots = [
      { alias: 'game_datas', displayName: '主目录', svnUrl: 'https://svn/a', enabled: true },
      { alias: 'game_datas', displayName: '重复', svnUrl: '', enabled: true },
    ]

    const result = validateFeishuBotConfigForm(form, { hasAppSecret: false })

    expect(result.ok).toBe(false)
    expect(result.errors).toEqual([
      'query_roots alias 重复：game_datas',
      'query_roots.svn_url 不能为空：game_datas',
    ])
  })

  it('extracts backend Chinese errors for inline display', () => {
    const error = new ApiRequestError(
      '该飞书群已绑定项目「项目 A」，不能重复绑定到「项目 B」',
      400,
      '该飞书群已绑定项目「项目 A」，不能重复绑定到「项目 B」',
    )

    expect(extractFeishuBotConfigError(error)).toBe(
      '该飞书群已绑定项目「项目 A」，不能重复绑定到「项目 B」',
    )
  })
})
