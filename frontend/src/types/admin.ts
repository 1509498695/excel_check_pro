/**
 * 管理后台相关的精简类型，主要服务于项目级飞书机器人长连接配置面板。
 *
 * 与后端 `_serialize_feishu_bot_config` 的字段一一对应，移除事件回调期遗留的
 * `verification_token` / `encrypt_key` / `event_callback_url` 等字段。
 */

export type FeishuBotConnectionState =
  | 'inactive'
  | 'active'
  | 'error'
  | 'reconnecting'

export interface FeishuBotConfig {
  configured: boolean
  app_id: string
  has_app_secret: boolean
  default_chat_id: string
  allowed_open_ids: string[]
  local_download_roots: string[]
  svn_download_roots: string[]
  allowed_download_suffixes: string[]
  connection_state: FeishuBotConnectionState
  updated_at: string | null
}

export interface FeishuBotConfigPayload {
  app_id: string
  app_secret?: string | null
  default_chat_id?: string | null
  allowed_open_ids?: string | null
  local_download_roots?: string | null
  svn_download_roots?: string | null
  allowed_download_suffixes?: string | null
}

export interface FeishuBotTestSendPayload {
  chat_id: string
  text: string
  use_card?: boolean
}

export interface FeishuBotTestSendResult {
  message_id: string
}
