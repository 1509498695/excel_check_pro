/**
 * 管理后台相关的精简类型，主要服务于项目级飞书机器人长连接配置面板。
 *
 * 与后端 `_serialize_feishu_bot_config` 的字段一一对应，移除事件回调期遗留的
 * `verification_token` / `encrypt_key` / `event_callback_url` 等字段。
 */

import type { AiProviderPreset } from './aiProvider'

export type FeishuBotConnectionState =
  | 'inactive'
  | 'active'
  | 'error'
  | 'reconnecting'

export interface FeishuBotQueryRoot {
  alias: string
  display_name: string
  svn_url: string
  enabled: boolean
}

export interface FeishuBotSvnCredentialStatus {
  configured: boolean
  username_masked: string
  updated_at: string | null
}

export type ProjectSvnCredentialTestStatus = 'success' | 'failed'

export interface ProjectSvnCredentialTestItem {
  alias: string
  display_name: string
  svn_url: string
  status: ProjectSvnCredentialTestStatus
  message: string
  entry_count: number
}

export interface ProjectSvnCredentialTestResult {
  status: ProjectSvnCredentialTestStatus
  items: ProjectSvnCredentialTestItem[]
}

export interface FeishuBotAiCredentialStatus {
  configured: boolean
  provider_preset: AiProviderPreset | ''
  provider?: AiProviderPreset | ''
  base_url: string
  model: string
  api_key_masked: string
  masked_api_key?: string
  has_extra_headers: boolean
  enabled?: boolean
  last_test_status?: string
  last_test_at?: string | null
  last_test_error_summary?: string
  updated_at: string | null
}

export interface FeishuBotAiMatchParams {
  auto_match_threshold: number
  candidate_threshold: number
  max_candidates: number
}

export interface FeishuBotConfig {
  configured: boolean
  app_id: string
  has_app_secret: boolean
  default_chat_id: string
  bound_chat_ids: string[]
  allowed_open_ids: string[]
  local_download_roots: string[]
  svn_download_roots: string[]
  allowed_download_suffixes: string[]
  query_roots: FeishuBotQueryRoot[]
  svn_credential: FeishuBotSvnCredentialStatus
  ai_credential: FeishuBotAiCredentialStatus
  ai_match_params: FeishuBotAiMatchParams
  connection_state: FeishuBotConnectionState
  updated_at: string | null
}

export interface ProjectSvnCredentialPayload {
  username?: string | null
  password?: string | null
}

export interface ProjectAiCredentialPayload {
  provider_preset: AiProviderPreset
  base_url?: string | null
  model?: string | null
  api_key?: string | null
  extra_headers?: Record<string, string>
}

export interface FeishuBotConfigPayload {
  app_id: string
  app_secret?: string | null
  default_chat_id?: string | null
  allowed_open_ids?: string | null
  local_download_roots?: string | null
  svn_download_roots?: string | null
  allowed_download_suffixes?: string | null
  bound_chat_ids?: string[] | null
  query_roots?: FeishuBotQueryRoot[] | null
  svn_credential?: ProjectSvnCredentialPayload | null
  ai_credential?: ProjectAiCredentialPayload | null
  ai_match_params?: Partial<FeishuBotAiMatchParams> | null
}

export interface FeishuBotTestSendPayload {
  chat_id: string
  text: string
  use_card?: boolean
}

export interface FeishuBotTestSendResult {
  message_id: string
}
