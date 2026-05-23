"""飞书电子表格 OpenAPI 读取客户端。

本模块提供电子表格读取、OAuth 回调临时 token 交换与 Drive 协作者授权基础能力。
项目级 app_id/app_secret 与 tenant_access_token 缓存复用 feishu_bot 模块。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode, urlparse, urlunparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.integrations.feishu_bot import (
    DEFAULT_TIMEOUT_SECONDS,
    FEISHU_OPEN_BASE_URL,
    FeishuApiError,
    get_tenant_access_token,
)
from backend.app.loaders.feishu_reader import (
    FeishuSheetError,
    FeishuSheetLocator,
    parse_feishu_sheet_url,
)
from backend.app.models import FeishuBotConfigRecord
from backend.app.security.crypto import decrypt_secret


__all__ = [
    "FEISHU_API_ERROR",
    "FEISHU_APP_PERMISSION_MISSING",
    "FEISHU_DOCUMENT_NOT_FOUND",
    "FEISHU_DOCUMENT_PERMISSION_DENIED",
    "FEISHU_INVALID_URL",
    "FEISHU_READ_RANGE_TOO_LARGE",
    "FeishuClientError",
    "FeishuSheetMetadata",
    "FeishuSheetTable",
    "FeishuSpreadsheetMetadata",
    "FeishuOAuthUserInfo",
    "add_sheet_viewer_collaborator",
    "exchange_oauth_code_for_user_token",
    "get_current_bot_open_id",
    "get_feishu_tenant_access_token",
    "get_oauth_user_info",
    "get_spreadsheet_metadata",
    "list_spreadsheet_sheets",
    "read_sheet_columns",
    "read_sheet_values",
    "resolve_wiki_sheet_locator",
    "resolve_wiki_sheet_locator_with_user_token",
]


FEISHU_INVALID_URL = "FEISHU_INVALID_URL"
FEISHU_APP_PERMISSION_MISSING = "FEISHU_APP_PERMISSION_MISSING"
FEISHU_DOCUMENT_PERMISSION_DENIED = "FEISHU_DOCUMENT_PERMISSION_DENIED"
FEISHU_DOCUMENT_NOT_FOUND = "FEISHU_DOCUMENT_NOT_FOUND"
FEISHU_READ_RANGE_TOO_LARGE = "FEISHU_READ_RANGE_TOO_LARGE"
FEISHU_API_ERROR = "FEISHU_API_ERROR"

SPREADSHEET_GET_PATH = "/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}"
SHEETS_QUERY_PATH = "/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query"
SHEET_VALUES_PATH = "/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values/{range}"
OAUTH_TOKEN_PATH = "/open-apis/authen/v2/oauth/token"
OAUTH_USER_INFO_PATH = "/open-apis/authen/v1/user_info"
BOT_INFO_PATH = "/open-apis/bot/v3/info"
DRIVE_PERMISSION_MEMBER_PATH = "/open-apis/drive/v1/permissions/{token}/members"
WIKI_GET_NODE_PATH = "/open-apis/wiki/v2/spaces/get_node"

_APP_PERMISSION_CODES = {10003, 99991663, 99991664, 99991665, 99991668, 99991672}
_READ_RANGE_TOO_LARGE_CODES = {90227}


@dataclass(frozen=True)
class FeishuSpreadsheetMetadata:
    """飞书电子表格基础元信息。"""

    token: str
    title: str
    url: str
    owner_id: str


@dataclass(frozen=True)
class FeishuSheetMetadata:
    """飞书工作表元信息。"""

    sheet_id: str
    title: str
    index: int
    row_count: int
    column_count: int
    hidden: bool
    resource_type: str


@dataclass(frozen=True)
class FeishuSheetTable:
    """飞书工作表整表读取结果。"""

    spreadsheet_token: str
    sheet_id: str
    sheet_title: str
    range: str
    columns: list[str]
    rows: list[dict[str, Any]]
    raw_values: list[list[Any]]


@dataclass(frozen=True)
class FeishuOAuthUserInfo:
    """飞书 OAuth 授权用户信息。"""

    open_id: str


class FeishuClientError(RuntimeError):
    """飞书电子表格客户端错误；code 为系统内部错误码。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        feishu_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.feishu_code = feishu_code

    def __str__(self) -> str:
        return self.message


def _create_async_client(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> httpx.AsyncClient:
    """构造 httpx.AsyncClient；测试可 monkeypatch 注入 MockTransport。"""
    return httpx.AsyncClient(base_url=FEISHU_OPEN_BASE_URL, timeout=timeout)


async def get_feishu_tenant_access_token(db: AsyncSession, project_id: int) -> str:
    """获取 tenant_access_token，复用现有机器人配置与缓存。"""
    try:
        return await get_tenant_access_token(db, project_id)
    except FeishuApiError as exc:
        raise FeishuClientError(
            FEISHU_APP_PERMISSION_MISSING,
            _sanitize_error_message(f"飞书应用凭证不可用：{exc}"),
        ) from exc


async def exchange_oauth_code_for_user_token(
    db: AsyncSession,
    project_id: int,
    code: str,
    redirect_uri: str,
) -> str:
    """使用 OAuth code 换取临时 user_access_token；调用方不得持久化。"""
    normalized_code = (code or "").strip()
    if not normalized_code:
        raise FeishuClientError(FEISHU_API_ERROR, "飞书 OAuth 回调缺少授权码。")
    config, app_secret = await _load_feishu_bot_config_secret(db, project_id)
    payload = {
        "grant_type": "authorization_code",
        "client_id": config.app_id,
        "client_secret": app_secret,
        "code": normalized_code,
        "redirect_uri": redirect_uri,
    }
    response_payload = await _request_feishu_json_without_auth(
        "POST",
        OAUTH_TOKEN_PATH,
        json_payload=payload,
        context_message="飞书 OAuth token 换取失败",
    )
    token = _extract_user_access_token(response_payload)
    if not token:
        raise FeishuClientError(FEISHU_API_ERROR, "飞书 OAuth 返回缺少 user_access_token。")
    return token


async def get_oauth_user_info(user_access_token: str) -> FeishuOAuthUserInfo:
    """使用临时 user_access_token 获取授权用户 open_id。"""
    payload = await _request_feishu_json_with_bearer(
        "GET",
        OAUTH_USER_INFO_PATH,
        access_token=user_access_token,
        context_message="飞书 OAuth 用户信息读取失败",
    )
    data = payload.get("data")
    data_payload = data if isinstance(data, dict) else payload
    open_id = _as_str(data_payload.get("open_id") if isinstance(data_payload, dict) else "")
    if not open_id:
        raise FeishuClientError(FEISHU_API_ERROR, "飞书 OAuth 返回缺少用户 open_id。")
    return FeishuOAuthUserInfo(open_id=open_id)


async def get_current_bot_open_id(db: AsyncSession, project_id: int) -> str:
    """获取当前项目飞书应用机器人的 open_id。"""
    payload = await _request_feishu_json(db, project_id, "GET", BOT_INFO_PATH)
    data = _ensure_dict(payload.get("data"), "data")
    bot = data.get("bot")
    bot_payload = bot if isinstance(bot, dict) else data
    open_id = _as_str(bot_payload.get("open_id"))
    if not open_id:
        open_id = _as_str(bot_payload.get("id"))
    if not open_id:
        raise FeishuClientError(FEISHU_API_ERROR, "飞书 API 返回缺少机器人 open_id。")
    return open_id


async def add_sheet_viewer_collaborator(
    user_access_token: str,
    spreadsheet_token: str,
    bot_open_id: str,
) -> None:
    """以授权用户身份把机器人添加为飞书电子表格只读协作者。"""
    path = DRIVE_PERMISSION_MEMBER_PATH.format(
        token=quote(spreadsheet_token, safe="")
    )
    await _request_feishu_json_with_bearer(
        "POST",
        path,
        access_token=user_access_token,
        context_message="飞书表格协作者授权失败",
        params={"type": "sheet"},
        json_payload={
            "member_type": "openid",
            "member_id": bot_open_id,
            "perm": "view",
        },
    )


async def resolve_wiki_sheet_locator(
    db: AsyncSession,
    project_id: int,
    locator: FeishuSheetLocator | str,
) -> FeishuSheetLocator:
    """将知识库里的电子表格 Wiki 节点解析为真实 spreadsheet token。"""
    resolved_locator = _resolve_locator(locator)
    if resolved_locator.url_type != "wiki":
        return resolved_locator
    payload = await _request_feishu_json(
        db,
        project_id,
        "GET",
        WIKI_GET_NODE_PATH,
        params={"token": resolved_locator.spreadsheet_token},
    )
    return _build_sheet_locator_from_wiki_payload(payload, resolved_locator)


async def resolve_wiki_sheet_locator_with_user_token(
    user_access_token: str,
    locator: FeishuSheetLocator | str,
) -> FeishuSheetLocator:
    """用 OAuth 用户身份解析 Wiki 节点，供授权回调内一次性使用。"""
    resolved_locator = _resolve_locator(locator)
    if resolved_locator.url_type != "wiki":
        return resolved_locator
    payload = await _request_feishu_json_with_bearer(
        "GET",
        WIKI_GET_NODE_PATH,
        access_token=user_access_token,
        context_message="飞书 Wiki 节点解析失败",
        params={"token": resolved_locator.spreadsheet_token},
    )
    return _build_sheet_locator_from_wiki_payload(payload, resolved_locator)


async def get_spreadsheet_metadata(
    db: AsyncSession,
    project_id: int,
    locator: FeishuSheetLocator | str,
) -> FeishuSpreadsheetMetadata:
    """读取飞书电子表格元信息。"""
    resolved_locator = await resolve_wiki_sheet_locator(db, project_id, locator)
    path = SPREADSHEET_GET_PATH.format(
        spreadsheet_token=quote(resolved_locator.spreadsheet_token, safe="")
    )
    payload = await _request_feishu_json(db, project_id, "GET", path)
    spreadsheet = _ensure_dict(payload.get("data"), "data").get("spreadsheet")
    spreadsheet_payload = _ensure_dict(spreadsheet, "spreadsheet")

    return FeishuSpreadsheetMetadata(
        token=_as_str(
            spreadsheet_payload.get("token"),
            fallback=resolved_locator.spreadsheet_token,
        ),
        title=_as_str(spreadsheet_payload.get("title")),
        url=_as_str(spreadsheet_payload.get("url")),
        owner_id=_as_str(spreadsheet_payload.get("owner_id")),
    )


async def list_spreadsheet_sheets(
    db: AsyncSession,
    project_id: int,
    locator: FeishuSheetLocator | str,
) -> list[FeishuSheetMetadata]:
    """获取飞书电子表格下所有工作表及其属性。"""
    resolved_locator = await resolve_wiki_sheet_locator(db, project_id, locator)
    path = SHEETS_QUERY_PATH.format(
        spreadsheet_token=quote(resolved_locator.spreadsheet_token, safe="")
    )
    payload = await _request_feishu_json(db, project_id, "GET", path)
    sheets_payload = _ensure_dict(payload.get("data"), "data").get("sheets")
    if not isinstance(sheets_payload, list):
        raise FeishuClientError(
            FEISHU_API_ERROR,
            "飞书 API 返回缺少工作表列表。",
        )

    sheets: list[FeishuSheetMetadata] = []
    for item in sheets_payload:
        if not isinstance(item, dict):
            continue
        grid_properties = item.get("grid_properties")
        grid = grid_properties if isinstance(grid_properties, dict) else {}
        sheet_id = _as_str(item.get("sheet_id"))
        if not sheet_id:
            continue
        sheets.append(
            FeishuSheetMetadata(
                sheet_id=sheet_id,
                title=_as_str(item.get("title"), fallback=sheet_id),
                index=_as_int(item.get("index")),
                row_count=max(0, _as_int(grid.get("row_count"))),
                column_count=max(0, _as_int(grid.get("column_count"))),
                hidden=bool(item.get("hidden", False)),
                resource_type=_as_str(item.get("resource_type")),
            )
        )
    return sheets


async def read_sheet_values(
    db: AsyncSession,
    project_id: int,
    locator: FeishuSheetLocator | str,
    *,
    sheet_id: str | None = None,
) -> FeishuSheetTable:
    """读取指定工作表整表数据；第一行为表头，第二行开始为数据。"""
    resolved_locator = await resolve_wiki_sheet_locator(db, project_id, locator)
    sheets = await list_spreadsheet_sheets(db, project_id, resolved_locator)
    selected_sheet = _select_sheet(sheets, requested_sheet_id=sheet_id or resolved_locator.sheet_id)
    range_name = _build_sheet_range(selected_sheet)
    path = SHEET_VALUES_PATH.format(
        spreadsheet_token=quote(resolved_locator.spreadsheet_token, safe=""),
        range=quote(range_name, safe="!:"),
    )
    payload = await _request_feishu_json(db, project_id, "GET", path)
    data = _ensure_dict(payload.get("data"), "data")
    value_range = _ensure_dict(data.get("valueRange"), "valueRange")
    raw_values = _normalize_values(value_range.get("values"))
    columns = _normalize_columns(raw_values[0] if raw_values else [])
    rows = _build_rows(columns, raw_values[1:] if raw_values else [])

    return FeishuSheetTable(
        spreadsheet_token=_as_str(
            data.get("spreadsheetToken"),
            fallback=resolved_locator.spreadsheet_token,
        ),
        sheet_id=selected_sheet.sheet_id,
        sheet_title=selected_sheet.title,
        range=_as_str(value_range.get("range"), fallback=range_name),
        columns=columns,
        rows=rows,
        raw_values=raw_values,
    )


async def read_sheet_columns(
    db: AsyncSession,
    project_id: int,
    locator: FeishuSheetLocator | str,
    *,
    sheet_id: str | None = None,
) -> list[str]:
    """读取指定工作表首行列结构。"""
    table = await read_sheet_values(
        db,
        project_id,
        locator,
        sheet_id=sheet_id,
    )
    return table.columns


async def _request_feishu_json(
    db: AsyncSession,
    project_id: int,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token = await get_feishu_tenant_access_token(db, project_id)
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with _create_async_client() as client:
            response = await client.request(
                method,
                path,
                headers=headers,
                params=params,
            )
    except httpx.TimeoutException as exc:
        raise FeishuClientError(
            FEISHU_API_ERROR,
            "飞书 API 网络异常：请求超时。",
        ) from exc
    except httpx.HTTPError as exc:
        raise FeishuClientError(
            FEISHU_API_ERROR,
            _sanitize_error_message(f"飞书 API 网络异常：{exc}"),
        ) from exc

    if not response.is_success:
        raise _build_http_error(response)

    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise FeishuClientError(
            FEISHU_API_ERROR,
            "飞书 API 返回内容不是合法 JSON。",
        ) from exc
    if not isinstance(payload, dict):
        raise FeishuClientError(
            FEISHU_API_ERROR,
            "飞书 API 返回结构异常。",
        )

    code = payload.get("code", -1)
    if code != 0:
        feishu_code = _as_int(code, fallback=-1)
        msg = _sanitize_error_message(str(payload.get("msg") or "未知错误"))
        raise _build_business_error(feishu_code, msg)
    return payload


async def _request_feishu_json_without_auth(
    method: str,
    path: str,
    *,
    context_message: str,
    json_payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        async with _create_async_client() as client:
            response = await client.request(
                method,
                path,
                json=json_payload,
                params=params,
            )
    except httpx.TimeoutException as exc:
        raise FeishuClientError(FEISHU_API_ERROR, f"{context_message}：请求超时。") from exc
    except httpx.HTTPError as exc:
        raise FeishuClientError(
            FEISHU_API_ERROR,
            _sanitize_error_message(f"{context_message}：{exc}"),
        ) from exc

    return _parse_feishu_response_payload(response, context_message=context_message)


async def _request_feishu_json_with_bearer(
    method: str,
    path: str,
    *,
    access_token: str,
    context_message: str,
    json_payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with _create_async_client() as client:
            response = await client.request(
                method,
                path,
                json=json_payload,
                params=params,
                headers=headers,
            )
    except httpx.TimeoutException as exc:
        raise FeishuClientError(FEISHU_API_ERROR, f"{context_message}：请求超时。") from exc
    except httpx.HTTPError as exc:
        raise FeishuClientError(
            FEISHU_API_ERROR,
            _sanitize_error_message(f"{context_message}：{exc}"),
        ) from exc

    return _parse_feishu_response_payload(response, context_message=context_message)


def _parse_feishu_response_payload(
    response: httpx.Response,
    *,
    context_message: str,
) -> dict[str, Any]:
    if not response.is_success:
        raise _build_http_error(response)
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise FeishuClientError(
            FEISHU_API_ERROR,
            f"{context_message}：飞书 API 返回内容不是合法 JSON。",
        ) from exc
    if not isinstance(payload, dict):
        raise FeishuClientError(
            FEISHU_API_ERROR,
            f"{context_message}：飞书 API 返回结构异常。",
        )

    code = payload.get("code")
    if code not in (None, 0):
        feishu_code = _as_int(code, fallback=-1)
        msg = _sanitize_error_message(
            str(payload.get("msg") or payload.get("error_description") or "未知错误")
        )
        raise _build_business_error(feishu_code, msg)
    if payload.get("error"):
        msg = _sanitize_error_message(
            str(payload.get("error_description") or payload.get("error") or "未知错误")
        )
        raise FeishuClientError(FEISHU_API_ERROR, f"{context_message}：{msg}")
    return payload


def _resolve_locator(locator: FeishuSheetLocator | str) -> FeishuSheetLocator:
    if isinstance(locator, FeishuSheetLocator):
        return locator
    try:
        return parse_feishu_sheet_url(str(locator))
    except FeishuSheetError as exc:
        raise FeishuClientError(FEISHU_INVALID_URL, str(exc)) from exc


def _build_sheet_locator_from_wiki_payload(
    payload: dict[str, Any],
    wiki_locator: FeishuSheetLocator,
) -> FeishuSheetLocator:
    data = _ensure_dict(payload.get("data"), "data")
    node = _ensure_dict(data.get("node"), "node")
    obj_type = _as_str(node.get("obj_type")).lower()
    if obj_type != "sheet":
        raise FeishuClientError(
            FEISHU_INVALID_URL,
            "该 Wiki 节点不是飞书电子表格，第一版仅支持飞书电子表格链接。",
        )

    obj_token = _as_str(node.get("obj_token"))
    if not obj_token:
        raise FeishuClientError(
            FEISHU_API_ERROR,
            "飞书 Wiki 节点返回缺少电子表格 token。",
        )

    return FeishuSheetLocator(
        spreadsheet_token=obj_token,
        sheet_id=wiki_locator.sheet_id,
        normalized_url=_build_sheets_url_from_locator(wiki_locator, obj_token),
        url_type="sheet",
    )


def _build_sheets_url_from_locator(
    locator: FeishuSheetLocator,
    spreadsheet_token: str,
) -> str:
    parsed = urlparse(locator.normalized_url)
    host = parsed.netloc
    query = urlencode({"sheet": locator.sheet_id}) if locator.sheet_id else ""
    if not host:
        return f"https://feishu.cn/sheets/{spreadsheet_token}{f'?{query}' if query else ''}"
    return urlunparse(("https", host, f"/sheets/{spreadsheet_token}", "", query, ""))


async def _load_feishu_bot_config_secret(
    db: AsyncSession,
    project_id: int,
) -> tuple[FeishuBotConfigRecord, str]:
    result = await db.execute(
        select(FeishuBotConfigRecord).where(
            FeishuBotConfigRecord.project_id == project_id
        )
    )
    record = result.scalar_one_or_none()
    if record is None or not record.app_id or not record.app_secret_cipher:
        raise FeishuClientError(
            FEISHU_APP_PERMISSION_MISSING,
            "飞书应用凭证不可用：项目未配置飞书机器人或密钥不可用。",
        )
    try:
        app_secret = decrypt_secret(record.app_secret_cipher)
    except ValueError as exc:
        raise FeishuClientError(
            FEISHU_APP_PERMISSION_MISSING,
            "飞书应用凭证不可用：项目未配置飞书机器人或密钥不可用。",
        ) from exc
    if not app_secret:
        raise FeishuClientError(
            FEISHU_APP_PERMISSION_MISSING,
            "飞书应用凭证不可用：项目未配置飞书机器人或密钥不可用。",
        )
    return record, app_secret


def _extract_user_access_token(payload: dict[str, Any]) -> str:
    token = payload.get("access_token") or payload.get("user_access_token")
    if isinstance(token, str) and token:
        return token
    data = payload.get("data")
    if isinstance(data, dict):
        token = data.get("access_token") or data.get("user_access_token")
        if isinstance(token, str) and token:
            return token
    return ""


def _select_sheet(
    sheets: list[FeishuSheetMetadata],
    *,
    requested_sheet_id: str | None,
) -> FeishuSheetMetadata:
    if not sheets:
        raise FeishuClientError(
            FEISHU_DOCUMENT_NOT_FOUND,
            "飞书电子表格中未找到工作表。",
        )

    if requested_sheet_id:
        for sheet in sheets:
            if sheet.sheet_id == requested_sheet_id:
                return sheet
        raise FeishuClientError(
            FEISHU_DOCUMENT_NOT_FOUND,
            f"飞书电子表格中未找到工作表：{requested_sheet_id}。",
        )

    visible_sheets = [sheet for sheet in sheets if not sheet.hidden]
    candidates = visible_sheets or sheets
    return sorted(candidates, key=lambda item: item.index)[0]


def _build_sheet_range(sheet: FeishuSheetMetadata) -> str:
    row_count = max(1, sheet.row_count)
    column_count = max(1, sheet.column_count)
    end_column = _column_index_to_letters(column_count)
    return f"{sheet.sheet_id}!A1:{end_column}{row_count}"


def _column_index_to_letters(index: int) -> str:
    if index <= 0:
        raise ValueError("column index must be positive")

    letters: list[str] = []
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


def _normalize_columns(header_row: list[Any]) -> list[str]:
    columns: list[str] = []
    seen_counts: dict[str, int] = {}

    for index, value in enumerate(header_row, start=1):
        raw_name = "" if value is None else str(value).strip()
        base_name = raw_name or f"Unnamed: {index}"
        duplicate_count = seen_counts.get(base_name, 0)
        seen_counts[base_name] = duplicate_count + 1
        columns.append(base_name if duplicate_count == 0 else f"{base_name}.{duplicate_count}")
    return columns


def _build_rows(
    columns: list[str],
    data_rows: list[list[Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_row in data_rows:
        row: dict[str, Any] = {}
        for index, column in enumerate(columns):
            row[column] = raw_row[index] if index < len(raw_row) else None
        rows.append(row)
    return rows


def _normalize_values(values: Any) -> list[list[Any]]:
    if not isinstance(values, list):
        return []

    normalized: list[list[Any]] = []
    for row in values:
        if isinstance(row, list):
            normalized.append(row)
        else:
            normalized.append([row])
    return normalized


def _build_http_error(response: httpx.Response) -> FeishuClientError:
    detail = _sanitize_error_message(_summarize_response_body(response))
    business_error = _build_http_business_error(response)
    if business_error is not None:
        business_error.status_code = response.status_code
        return business_error
    if response.status_code == 401:
        return FeishuClientError(
            FEISHU_APP_PERMISSION_MISSING,
            f"飞书应用权限或访问凭证不可用：HTTP {response.status_code} {detail}".strip(),
            status_code=response.status_code,
        )
    if response.status_code == 403:
        return FeishuClientError(
            FEISHU_DOCUMENT_PERMISSION_DENIED,
            f"飞书应用无权访问该电子表格：HTTP {response.status_code} {detail}".strip(),
            status_code=response.status_code,
        )
    if response.status_code == 404:
        return FeishuClientError(
            FEISHU_DOCUMENT_NOT_FOUND,
            f"飞书电子表格或工作表不存在：HTTP {response.status_code} {detail}".strip(),
            status_code=response.status_code,
        )
    if response.status_code == 413 or _looks_like_range_too_large(detail):
        return FeishuClientError(
            FEISHU_READ_RANGE_TOO_LARGE,
            f"飞书电子表格读取范围过大：HTTP {response.status_code} {detail}".strip(),
            status_code=response.status_code,
        )
    return FeishuClientError(
        FEISHU_API_ERROR,
        f"飞书 API 调用失败：HTTP {response.status_code} {detail}".strip(),
        status_code=response.status_code,
    )


def _build_business_error(feishu_code: int, msg: str) -> FeishuClientError:
    lower_msg = msg.lower()
    if _looks_like_wiki_authorization_needed(lower_msg):
        return FeishuClientError(
            FEISHU_DOCUMENT_PERMISSION_DENIED,
            f"飞书应用无权访问该 Wiki 表格节点：{msg}",
            feishu_code=feishu_code,
        )
    if feishu_code in _APP_PERMISSION_CODES or _looks_like_app_permission_error(lower_msg):
        return FeishuClientError(
            FEISHU_APP_PERMISSION_MISSING,
            f"飞书应用权限不足：{msg}",
            feishu_code=feishu_code,
        )
    if _looks_like_range_too_large(lower_msg) or feishu_code in _READ_RANGE_TOO_LARGE_CODES:
        return FeishuClientError(
            FEISHU_READ_RANGE_TOO_LARGE,
            f"飞书电子表格读取范围过大：{msg}",
            feishu_code=feishu_code,
        )
    if _looks_like_not_found_error(lower_msg):
        return FeishuClientError(
            FEISHU_DOCUMENT_NOT_FOUND,
            f"飞书电子表格或工作表不存在：{msg}",
            feishu_code=feishu_code,
        )
    if _looks_like_document_permission_error(lower_msg):
        return FeishuClientError(
            FEISHU_DOCUMENT_PERMISSION_DENIED,
            f"飞书应用无权访问该电子表格：{msg}",
            feishu_code=feishu_code,
        )
    return FeishuClientError(
        FEISHU_API_ERROR,
        f"飞书 API 错误（code={feishu_code}）：{msg}",
        feishu_code=feishu_code,
    )


def _build_http_business_error(response: httpx.Response) -> FeishuClientError | None:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    code = payload.get("code")
    if code in (None, 0):
        return None
    feishu_code = _as_int(code, fallback=-1)
    msg = _sanitize_error_message(
        str(payload.get("msg") or payload.get("error_description") or "未知错误")
    )
    return _build_business_error(feishu_code, msg)


def _looks_like_app_permission_error(message: str) -> bool:
    return any(
        keyword in message
        for keyword in (
            "app permission",
            "missing scope",
            "scope",
            "invalid tenant_access_token",
            "invalid app",
            "应用权限",
            "权限范围",
            "访问凭证",
        )
    )


def _looks_like_wiki_authorization_needed(message: str) -> bool:
    return "access denied" in message and any(
        keyword in message
        for keyword in (
            "wiki:node:read",
            "wiki:wiki:readonly",
            "wiki:wiki",
            "wiki",
        )
    )


def _looks_like_document_permission_error(message: str) -> bool:
    return any(
        keyword in message
        for keyword in (
            "permission",
            "forbidden",
            "access denied",
            "no access",
            "无权限",
            "权限不足",
            "没有权限",
            "无权",
        )
    )


def _looks_like_not_found_error(message: str) -> bool:
    return any(
        keyword in message
        for keyword in (
            "not found",
            "not exist",
            "does not exist",
            "不存在",
            "找不到",
            "未找到",
        )
    )


def _looks_like_range_too_large(message: str) -> bool:
    return any(
        keyword in message
        for keyword in (
            "too large",
            "range too large",
            "exceed",
            "exceeded",
            "10m",
            "10mb",
            "范围过大",
            "超过",
            "超出",
        )
    )


def _summarize_response_body(response: httpx.Response, limit: int = 200) -> str:
    text = (response.text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _sanitize_error_message(message: str) -> str:
    sanitized = re.sub(
        r"(?i)\b(app_secret|tenant_access_token|user_access_token)\s*=\s*[^,\s]+",
        r"\1=[REDACTED]",
        message,
    )
    sanitized = re.sub(
        r"(?i)\boauth\s+code\s*=\s*[^,\s]+",
        "OAuth code=[REDACTED]",
        sanitized,
    )
    for marker in (
        "app_secret",
        "tenant_access_token",
        "user_access_token",
        "oauth code",
        "OAuth code",
    ):
        sanitized = sanitized.replace(marker, "[REDACTED]")
    return sanitized


def _ensure_dict(value: Any, label: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raise FeishuClientError(
        FEISHU_API_ERROR,
        f"飞书 API 返回缺少 {label}。",
    )


def _as_str(value: Any, *, fallback: str = "") -> str:
    if value is None:
        return fallback
    return str(value)


def _as_int(value: Any, *, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return fallback
    return fallback
