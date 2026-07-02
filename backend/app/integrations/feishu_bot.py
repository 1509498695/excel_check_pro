"""飞书自建应用 OpenAPI 客户端（仅供项目校验侧后续步骤使用）。

设计要点：
- 仅暴露纯函数 ``get_tenant_access_token`` / ``send_text_to_chat`` /
  ``send_card_to_chat`` 与异常类型 ``FeishuApiError``，不持有 FastAPI 依赖。
- 按 ``project_id`` 维度做内存 token 缓存，TTL 上限 100 分钟，提前 2 分钟视为失效；
  通过 ``asyncio.Lock`` 串行化 token 刷新，避免雷群效应。
- 网络层使用 ``httpx.AsyncClient``，超时 10 秒；测试可通过 monkeypatch
  ``_create_async_client`` 注入 ``MockTransport``，无需引入 ``respx``。
- 任何 4xx/5xx、网络异常、飞书业务错误（``code != 0``）以及配置缺失/解密失败，统一抛出
  ``FeishuApiError``，错误消息可直接展示给最终用户。
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import FeishuBotConfigRecord
from backend.app.security.crypto import decrypt_secret


__all__ = [
    "FeishuApiError",
    "get_tenant_access_token",
    "upload_file",
    "send_file_to_chat",
    "send_text_to_chat",
    "send_card_to_chat",
    "send_text_to_open_id",
    "send_card_to_open_id",
    "invalidate_token_cache",
]


DEFAULT_TIMEOUT_SECONDS: float = 10.0
DEFAULT_TOKEN_TTL_SECONDS: int = 100 * 60
TOKEN_REFRESH_BUFFER_SECONDS: int = 2 * 60
FEISHU_OPEN_BASE_URL: str = "https://open.feishu.cn"
TENANT_ACCESS_TOKEN_PATH: str = "/open-apis/auth/v3/tenant_access_token/internal"
SEND_MESSAGE_PATH: str = "/open-apis/im/v1/messages"
UPLOAD_FILE_PATH: str = "/open-apis/im/v1/files"


_TOKEN_CACHE: dict[int, tuple[str, float]] = {}
_TOKEN_LOCKS: dict[int, asyncio.Lock] = {}
_TOKEN_LOCKS_GUARD = asyncio.Lock()


class FeishuApiError(RuntimeError):
    """飞书 OpenAPI 业务错误；message 可直接展示给用户。"""


def _create_async_client(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> httpx.AsyncClient:
    """构造 httpx.AsyncClient；测试可 monkeypatch 该符号注入 MockTransport。"""
    return httpx.AsyncClient(base_url=FEISHU_OPEN_BASE_URL, timeout=timeout)


def invalidate_token_cache(project_id: int) -> None:
    """清除指定项目的 token 缓存；配置变更后调用，避免旧 token 残留。"""
    _TOKEN_CACHE.pop(project_id, None)


async def _get_token_lock(project_id: int) -> asyncio.Lock:
    """按 project_id 取或创建 asyncio.Lock，避免并发重复刷新 token。"""
    async with _TOKEN_LOCKS_GUARD:
        lock = _TOKEN_LOCKS.get(project_id)
        if lock is None:
            lock = asyncio.Lock()
            _TOKEN_LOCKS[project_id] = lock
        return lock


async def _load_config_or_raise(
    db: AsyncSession,
    project_id: int,
) -> tuple[FeishuBotConfigRecord, str]:
    """读取项目级飞书机器人配置并返回 (record, plain_app_secret)。"""
    result = await db.execute(
        select(FeishuBotConfigRecord).where(
            FeishuBotConfigRecord.project_id == project_id
        )
    )
    record = result.scalar_one_or_none()
    if record is None or not record.app_id or not record.app_secret_cipher:
        raise FeishuApiError("项目未配置飞书机器人或密钥不可用")
    try:
        app_secret = decrypt_secret(record.app_secret_cipher)
    except ValueError as exc:
        raise FeishuApiError("项目未配置飞书机器人或密钥不可用") from exc
    if not app_secret:
        raise FeishuApiError("项目未配置飞书机器人或密钥不可用")
    return record, app_secret


def _summarize_response_body(response: httpx.Response, limit: int = 200) -> str:
    """截断响应体作为错误描述，避免日志过长。"""
    text = (response.text or "").strip()
    if len(text) <= limit:
        return _sanitize_error_message(text)
    return _sanitize_error_message(text[:limit] + "…")


def _sanitize_error_message(message: str) -> str:
    """移除飞书错误中的敏感凭证、OAuth code 和 Authorization 头。"""
    sanitized = re.sub(
        r"(?i)([\"']?\b(?:app_secret|tenant_access_token|user_access_token)[\"']?\s*[:=]\s*[\"']?)[^,\"'}\s]+",
        r"\1[REDACTED]",
        message,
    )
    sanitized = re.sub(
        r"(?i)(\b(?:oauth[\s_-]*code|authorization[\s_-]*code|auth[\s_-]*code)\s*[:=]\s*[\"']?)[^,\"'}\s]+",
        r"\1[REDACTED]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)\bAuthorization\s*[:=]\s*Bearer\s+[^,\s]+",
        "Authorization=[REDACTED]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)\bAuthorization\s*[:=]\s*[^,\s]+",
        "Authorization=[REDACTED]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)\bBearer\s+[^,\s]+",
        "Bearer [REDACTED]",
        sanitized,
    )
    for marker in (
        "app_secret",
        "tenant_access_token",
        "user_access_token",
        "authorization",
        "Authorization",
        "bearer",
        "Bearer",
        "oauth_code",
        "authorization_code",
        "auth_code",
        "oauth code",
        "OAuth code",
    ):
        sanitized = sanitized.replace(marker, "[REDACTED]")
    return sanitized


def _raise_for_http_status(response: httpx.Response) -> None:
    """HTTP 4xx/5xx 统一抛 FeishuApiError，message 含状态码与响应摘要。"""
    if response.is_success:
        return
    detail = _sanitize_error_message(_summarize_response_body(response))
    raise FeishuApiError(
        f"飞书 API 调用失败：HTTP {response.status_code} {detail}".strip()
    )


def _parse_business_payload(response: httpx.Response) -> dict[str, Any]:
    """解析飞书业务响应：code != 0 视为业务错误。"""
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise FeishuApiError("飞书 API 返回内容不是合法 JSON") from exc

    if not isinstance(payload, dict):
        raise FeishuApiError("飞书 API 返回结构异常")

    code = payload.get("code", -1)
    if code != 0:
        msg = _sanitize_error_message(str(payload.get("msg") or "未知错误"))
        raise FeishuApiError(f"飞书 API 错误（code={code}）：{msg}")
    return payload


async def _request_tenant_access_token(
    app_id: str,
    app_secret: str,
) -> tuple[str, int]:
    """实际调用飞书 token 接口，返回 (token, expire_seconds)。"""
    payload = {"app_id": app_id, "app_secret": app_secret}
    try:
        async with _create_async_client() as client:
            response = await client.post(TENANT_ACCESS_TOKEN_PATH, json=payload)
    except httpx.TimeoutException as exc:
        raise FeishuApiError("飞书 API 网络异常：请求超时") from exc
    except httpx.HTTPError as exc:
        raise FeishuApiError(
            _sanitize_error_message(f"飞书 API 网络异常：{exc}")
        ) from exc

    _raise_for_http_status(response)
    body = _parse_business_payload(response)

    token = body.get("tenant_access_token")
    expire = body.get("expire")
    if not isinstance(token, str) or not token:
        raise FeishuApiError("飞书 API 返回缺少 tenant_access_token")
    if not isinstance(expire, int) or expire <= 0:
        expire = DEFAULT_TOKEN_TTL_SECONDS
    return token, expire


async def get_tenant_access_token(db: AsyncSession, project_id: int) -> str:
    """读取并缓存 tenant_access_token；缓存内有效期 < 2 分钟时强制刷新。"""
    now = time.monotonic()
    cached = _TOKEN_CACHE.get(project_id)
    if cached is not None:
        token, expires_at = cached
        if expires_at - now > TOKEN_REFRESH_BUFFER_SECONDS:
            return token

    lock = await _get_token_lock(project_id)
    async with lock:
        cached = _TOKEN_CACHE.get(project_id)
        now = time.monotonic()
        if cached is not None:
            token, expires_at = cached
            if expires_at - now > TOKEN_REFRESH_BUFFER_SECONDS:
                return token

        record, app_secret = await _load_config_or_raise(db, project_id)
        token, expire = await _request_tenant_access_token(
            record.app_id, app_secret
        )
        ttl = min(expire, DEFAULT_TOKEN_TTL_SECONDS)
        _TOKEN_CACHE[project_id] = (token, time.monotonic() + ttl)
        return token


async def _send_message(
    db: AsyncSession,
    project_id: int,
    receive_id: str,
    msg_type: str,
    content: dict[str, Any],
    *,
    receive_id_type: str = "chat_id",
) -> dict[str, Any]:
    """统一发送入口：按 receive_id_type 组装消息体并提取 message_id。"""
    normalized_receive_id_type = (receive_id_type or "").strip().lower()
    if normalized_receive_id_type not in {"chat_id", "open_id"}:
        raise FeishuApiError("receive_id_type 仅支持 chat_id 或 open_id")
    if not receive_id or not receive_id.strip():
        raise FeishuApiError(f"{normalized_receive_id_type} 不能为空")

    token = await get_tenant_access_token(db, project_id)
    payload = {
        "receive_id": receive_id.strip(),
        "msg_type": msg_type,
        "content": json.dumps(content, ensure_ascii=False),
    }
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with _create_async_client() as client:
            response = await client.post(
                SEND_MESSAGE_PATH,
                params={"receive_id_type": normalized_receive_id_type},
                json=payload,
                headers=headers,
            )
    except httpx.TimeoutException as exc:
        raise FeishuApiError("飞书 API 网络异常：请求超时") from exc
    except httpx.HTTPError as exc:
        raise FeishuApiError(
            _sanitize_error_message(f"飞书 API 网络异常：{exc}")
        ) from exc

    _raise_for_http_status(response)
    body = _parse_business_payload(response)

    data = body.get("data")
    message_id = ""
    if isinstance(data, dict):
        raw_id = data.get("message_id")
        if isinstance(raw_id, str):
            message_id = raw_id
    return {"message_id": message_id, "raw": body}


def _get_im_file_type(file_path: Path) -> str:
    """按飞书 IM 文件类型映射本地文件后缀。"""
    suffix = file_path.suffix.lower()
    if suffix in {".xls", ".xlsx"}:
        return "xls"
    return "stream"


async def upload_file(
    db: AsyncSession,
    project_id: int,
    file_path: Path,
    *,
    file_name: str | None = None,
) -> dict[str, Any]:
    """上传本地文件到飞书 IM 资源，返回 {"file_key": str, "raw": dict}。"""
    resolved_path = Path(file_path).expanduser()
    if not resolved_path.is_file():
        raise FeishuApiError(f"待上传文件不存在或不是文件：{resolved_path}")

    token = await get_tenant_access_token(db, project_id)
    headers = {"Authorization": f"Bearer {token}"}
    display_name = file_name or resolved_path.name
    data = {
        "file_type": _get_im_file_type(resolved_path),
        "file_name": display_name,
    }

    try:
        with resolved_path.open("rb") as file_handle:
            async with _create_async_client() as client:
                response = await client.post(
                    UPLOAD_FILE_PATH,
                    data=data,
                    files={"file": (display_name, file_handle)},
                    headers=headers,
                )
    except httpx.TimeoutException as exc:
        raise FeishuApiError("飞书 API 网络异常：请求超时") from exc
    except httpx.HTTPError as exc:
        raise FeishuApiError(
            _sanitize_error_message(f"飞书 API 网络异常：{exc}")
        ) from exc
    except OSError as exc:
        raise FeishuApiError(f"读取待上传文件失败：{exc}") from exc

    _raise_for_http_status(response)
    body = _parse_business_payload(response)
    data_payload = body.get("data")
    file_key = ""
    if isinstance(data_payload, dict):
        raw_file_key = data_payload.get("file_key")
        if isinstance(raw_file_key, str):
            file_key = raw_file_key
    if not file_key:
        raise FeishuApiError("飞书 API 返回缺少 file_key")
    return {"file_key": file_key, "raw": body}


async def send_file_to_chat(
    db: AsyncSession,
    project_id: int,
    chat_id: str,
    file_path: Path,
    *,
    file_name: str | None = None,
) -> dict[str, Any]:
    """上传本地文件并向指定群发送文件消息。"""
    upload_result = await upload_file(
        db,
        project_id,
        file_path,
        file_name=file_name,
    )
    file_key = upload_result["file_key"]
    message_result = await _send_message(
        db=db,
        project_id=project_id,
        receive_id=chat_id,
        msg_type="file",
        content={"file_key": file_key},
        receive_id_type="chat_id",
    )
    return {
        "message_id": message_result.get("message_id", ""),
        "file_key": file_key,
        "upload": upload_result.get("raw", {}),
        "raw": message_result.get("raw", {}),
    }


async def send_text_to_chat(
    db: AsyncSession,
    project_id: int,
    chat_id: str,
    text: str,
) -> dict[str, Any]:
    """向指定群发送纯文本消息，返回 {"message_id": str, "raw": dict}。"""
    if text is None or not str(text).strip():
        raise FeishuApiError("发送内容不能为空")
    return await _send_message(
        db=db,
        project_id=project_id,
        receive_id=chat_id,
        msg_type="text",
        content={"text": str(text)},
        receive_id_type="chat_id",
    )


async def send_card_to_chat(
    db: AsyncSession,
    project_id: int,
    chat_id: str,
    card: dict[str, Any],
) -> dict[str, Any]:
    """向指定群发送富文本卡片消息（msg_type=interactive）。"""
    if not isinstance(card, dict) or not card:
        raise FeishuApiError("卡片内容必须为非空字典")
    return await _send_message(
        db=db,
        project_id=project_id,
        receive_id=chat_id,
        msg_type="interactive",
        content=card,
        receive_id_type="chat_id",
    )


async def send_text_to_open_id(
    db: AsyncSession,
    project_id: int,
    open_id: str,
    text: str,
) -> dict[str, Any]:
    """向指定用户 open_id 发送纯文本消息，返回 {"message_id": str, "raw": dict}。"""
    if text is None or not str(text).strip():
        raise FeishuApiError("发送内容不能为空")
    return await _send_message(
        db=db,
        project_id=project_id,
        receive_id=open_id,
        msg_type="text",
        content={"text": str(text)},
        receive_id_type="open_id",
    )


async def send_card_to_open_id(
    db: AsyncSession,
    project_id: int,
    open_id: str,
    card: dict[str, Any],
) -> dict[str, Any]:
    """向指定用户 open_id 发送富文本卡片消息（msg_type=interactive）。"""
    if not isinstance(card, dict) or not card:
        raise FeishuApiError("卡片内容必须为非空字典")
    return await _send_message(
        db=db,
        project_id=project_id,
        receive_id=open_id,
        msg_type="interactive",
        content=card,
        receive_id_type="open_id",
    )
