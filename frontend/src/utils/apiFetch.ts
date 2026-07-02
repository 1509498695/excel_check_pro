/**
 * 封装 fetch，自动附加 Bearer Token 和 Content-Type。
 * 所有业务 API 统一通过此函数发起请求。
 */

import type { ApiFileResponse } from '../types/api'

export type { ApiFileResponse } from '../types/api'

const TOKEN_KEY = 'ec_token'

export class ApiRequestError extends Error {
  status: number
  detail: unknown
  payload: unknown

  constructor(message: string, status: number, detail: unknown = null, payload: unknown = null) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
    this.detail = detail
    this.payload = payload
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

function isAuthLoginOrRegisterUrl(url: string): boolean {
  return url.includes('/auth/login') || url.includes('/auth/register')
}

function extractApiErrorMessage(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }

  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const payload = detail as { msg?: unknown; message?: unknown; detail?: unknown }
    if (typeof payload.msg === 'string' && payload.msg.trim()) {
      return payload.msg
    }
    if (typeof payload.message === 'string' && payload.message.trim()) {
      return payload.message
    }
    if (typeof payload.detail === 'string' && payload.detail.trim()) {
      return payload.detail
    }
  }

  if (!Array.isArray(detail)) {
    return null
  }

  const selectedRuleIdsMismatch = detail.find((item) => {
    if (!item || typeof item !== 'object') {
      return false
    }

    const issue = item as {
      type?: unknown
      loc?: unknown
    }

    return (
      issue.type === 'extra_forbidden' &&
      Array.isArray(issue.loc) &&
      issue.loc.join('.') === 'body.selected_rule_ids'
    )
  })

  if (selectedRuleIdsMismatch) {
    return '当前后端服务未升级到支持规则勾选执行的版本，请重启后端服务后重试。'
  }

  const firstMessage = detail.find((item) => {
    if (!item || typeof item !== 'object') {
      return false
    }
    return typeof (item as { msg?: unknown }).msg === 'string'
  }) as { msg?: string } | undefined

  return firstMessage?.msg?.trim() || null
}

export async function apiFetch<T = unknown>(url: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers = new Headers(options.headers)

  if (token && !isAuthLoginOrRegisterUrl(url)) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const isFormDataBody = typeof FormData !== 'undefined' && options.body instanceof FormData
  if (options.body && !isFormDataBody && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(url, { ...options, headers })

  if (!response.ok) {
    let message = '请求失败，请稍后重试。'
    let payload: { detail?: unknown; msg?: unknown; message?: unknown } | null = null
    try {
      payload = (await response.json()) as {
        detail?: unknown
        msg?: unknown
        message?: unknown
      }
      const extractedMessage =
        extractApiErrorMessage(payload.detail) ?? extractApiErrorMessage(payload)
      if (extractedMessage) {
        message = extractedMessage
      }
    } catch {
      message = `${response.status} ${response.statusText}`
    }

    if (response.status === 401) {
      clearToken()
      if (!isAuthLoginOrRegisterUrl(url)) {
        window.location.href = '/login'
      }
      throw new ApiRequestError(message, response.status, payload?.detail, payload)
    }

    throw new ApiRequestError(message, response.status, payload?.detail, payload)
  }

  if (response.status === 204) {
    return undefined as T
  }

  const rawText = await response.text()
  if (!rawText.trim()) {
    return undefined as T
  }

  return JSON.parse(rawText) as T
}

export async function apiDownloadFile(
  url: string,
  fallbackFilename: string,
  options: RequestInit = {},
): Promise<ApiFileResponse> {
  const token = getToken()
  const headers = new Headers(options.headers)

  if (token && !isAuthLoginOrRegisterUrl(url)) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(url, { ...options, headers })

  if (!response.ok) {
    let message = '下载失败，请稍后重试。'
    let payload: { detail?: unknown; msg?: unknown; message?: unknown } | null = null
    try {
      payload = (await response.json()) as {
        detail?: unknown
        msg?: unknown
        message?: unknown
      }
      const extractedMessage =
        extractApiErrorMessage(payload.detail) ?? extractApiErrorMessage(payload)
      if (extractedMessage) {
        message = extractedMessage
      }
    } catch {
      message = `${response.status} ${response.statusText}`
    }

    if (response.status === 401) {
      clearToken()
      if (!isAuthLoginOrRegisterUrl(url)) {
        window.location.href = '/login'
      }
    }

    throw new ApiRequestError(message, response.status, payload?.detail, payload)
  }

  return {
    blob: await response.blob(),
    filename: extractDownloadFilename(response.headers) ?? fallbackFilename,
  }
}

function extractDownloadFilename(headers: Headers): string | null {
  const disposition = headers.get('Content-Disposition')
  if (!disposition) {
    return null
  }

  const filenameStarMatch = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (filenameStarMatch?.[1]) {
    return decodeURIComponent(filenameStarMatch[1].trim())
  }

  const filenameMatch = disposition.match(/filename="?([^";]+)"?/i)
  return filenameMatch?.[1]?.trim() || null
}
