"""飞书电子表格数据源端到端能力与回归测试。"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

import httpx
import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.api.schemas import DataSource, TaskTree, ValidationRule, VariableTag
from backend.app.database import async_session_factory
from backend.app.execution_pipeline import run_execution_pipeline
from backend.app.integrations import feishu_bot, feishu_client
from backend.app.integrations.feishu_client import (
    FEISHU_API_ERROR,
    FeishuClientError,
    FeishuSheetMetadata,
    FeishuSheetTable,
)
from backend.app.loaders.feishu_reader import FeishuSheetError, parse_feishu_sheet_url
from backend.app.models import FeishuBotConfigRecord, FeishuSheetAuthorizationRecord
from backend.app.security.crypto import encrypt_secret
from backend.app.services.feishu_sheet_authorization_service import (
    AUTHORIZATION_STATUS_AUTHORIZATION_FAILED,
    AUTHORIZATION_STATUS_AUTHORIZED,
    AUTHORIZATION_STATUS_SENT,
    hash_authorization_state,
    upsert_authorization_record,
)
from backend.config import settings
from backend.run import app


@pytest.fixture(autouse=True)
def _reset_feishu_runtime_settings() -> None:
    callback_url = settings.feishu_oauth_callback_url
    feishu_bot._TOKEN_CACHE.clear()
    feishu_bot._TOKEN_LOCKS.clear()
    yield
    feishu_bot._TOKEN_CACHE.clear()
    feishu_bot._TOKEN_LOCKS.clear()
    object.__setattr__(settings, "feishu_oauth_callback_url", callback_url)


@pytest.mark.parametrize(
    ("url", "expected_token", "expected_sheet_id"),
    [
        ("https://demo.feishu.cn/sheets/shtcnabc123", "shtcnabc123", None),
        ("https://tenant.larksuite.com/sheets/shtcnxyz789", "shtcnxyz789", None),
        ("https://demo.feishu.cn/sheets/shtcnabc123?sheet=gid001", "shtcnabc123", "gid001"),
        ("https://demo.feishu.cn/wiki/wikcnabc123?sheet=gid001", "wikcnabc123", "gid001"),
    ],
)
def test_feishu_url_parse_accepts_supported_sheet_links(
    url: str,
    expected_token: str,
    expected_sheet_id: str | None,
) -> None:
    locator = parse_feishu_sheet_url(url)

    assert locator.spreadsheet_token == expected_token
    assert locator.sheet_id == expected_sheet_id
    assert locator.normalized_url.startswith("https://")
    assert "/sheets/" in locator.normalized_url or "/wiki/" in locator.normalized_url


@pytest.mark.parametrize(
    ("url", "expected_message"),
    [
        ("https://demo.feishu.cn/base/app123", "第一版仅支持飞书电子表格链接"),
        ("https://demo.feishu.cn/docx/doccn123", "第一版仅支持飞书电子表格链接"),
        ("https://demo.feishu.cn/docs/doccn123", "第一版仅支持飞书电子表格链接"),
        ("https://example.com/sheets/shtcnabc123", "请输入合法的飞书电子表格链接"),
    ],
)
def test_feishu_url_parse_rejects_unsupported_or_non_feishu_links(
    url: str,
    expected_message: str,
) -> None:
    with pytest.raises(FeishuSheetError) as exc_info:
        parse_feishu_sheet_url(url)

    assert expected_message in str(exc_info.value)


@pytest.mark.anyio
async def test_feishu_metadata_e2e_reads_authorized_sheets_and_columns(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id)
    _install_feishu_openapi_mock(monkeypatch, _build_sheet_openapi_handler())

    response = await auth_client.post(
        "/api/v1/sources/metadata",
        json=_feishu_source_payload(),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data == {
        "source_id": "src_feishu",
        "source_type": "feishu",
        "sheets": [
            {"name": "Items", "sheet_id": "gid_items", "columns": ["ID", "Name", "Group"]},
            {"name": "Lookup", "sheet_id": "gid_lookup", "columns": ["RefID", "Label"]},
        ],
        "authorization_status": "authorized",
    }


@pytest.mark.anyio
async def test_feishu_metadata_e2e_reads_wiki_hosted_sheet_by_resolving_node(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id)
    _install_feishu_openapi_mock(monkeypatch, _build_sheet_openapi_handler())

    response = await auth_client.post(
        "/api/v1/sources/metadata",
        json={
            "id": "src_feishu",
            "type": "feishu",
            "pathOrUrl": "https://demo.feishu.cn/wiki/wikcnabc123",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source_type"] == "feishu"
    assert data["sheets"][0] == {
        "name": "Items",
        "sheet_id": "gid_items",
        "columns": ["ID", "Name", "Group"],
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("api_response", "expected_status", "expected_code"),
    [
        (
            httpx.Response(403, json={"code": 1254030, "msg": "permission denied"}),
            403,
            "FEISHU_DOCUMENT_PERMISSION_DENIED",
        ),
        (
            httpx.Response(401, json={"code": 99991663, "msg": "invalid app"}),
            403,
            "FEISHU_APP_PERMISSION_MISSING",
        ),
        (
            httpx.Response(404, json={"code": 1254040, "msg": "not found"}),
            404,
            "FEISHU_DOCUMENT_NOT_FOUND",
        ),
    ],
)
async def test_feishu_metadata_e2e_maps_permission_app_and_not_found_errors(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
    api_response: httpx.Response,
    expected_status: int,
    expected_code: str,
) -> None:
    await _seed_feishu_bot_config(test_project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _tenant_token_response()
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnabc123/sheets/query":
            return api_response
        return httpx.Response(404)

    _install_feishu_openapi_mock(monkeypatch, handler)

    response = await auth_client.post(
        "/api/v1/sources/metadata",
        json=_feishu_source_payload(),
    )

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == expected_code


@pytest.mark.anyio
async def test_feishu_preview_e2e_column_preview_uses_sheet_headers_and_real_row_index(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id)
    _install_feishu_openapi_mock(monkeypatch, _build_sheet_openapi_handler())

    response = await auth_client.post(
        "/api/v1/sources/column-preview",
        json={
            "source": _feishu_source_payload(),
            "sheet": "Items",
            "column": "Name",
            "limit": 3,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source_type"] == "feishu"
    assert data["sheet"] == "Items"
    assert data["column"] == "Name"
    assert data["preview_rows"] == [
        {"row_index": 2, "value": "Alpha"},
        {"row_index": 3, "value": "Beta"},
        {"row_index": 4, "value": "Beta Duplicate"},
    ]
    assert data["total_rows"] == 4
    assert data["loaded_all_rows"] is False


@pytest.mark.anyio
async def test_feishu_preview_e2e_composite_skips_empty_key_and_reports_duplicates(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id)
    _install_feishu_openapi_mock(monkeypatch, _build_sheet_openapi_handler())

    duplicate_response = await auth_client.post(
        "/api/v1/sources/composite-preview",
        json={
            "source": _feishu_source_payload(),
            "sheet": "Items",
            "columns": ["ID", "Name", "Group"],
            "key_column": "ID",
            "append_index_to_key": False,
        },
    )
    append_response = await auth_client.post(
        "/api/v1/sources/composite-preview",
        json={
            "source": _feishu_source_payload(),
            "sheet": "Items",
            "columns": ["ID", "Name", "Group"],
            "key_column": "ID",
            "append_index_to_key": True,
        },
    )

    assert duplicate_response.status_code == 200
    duplicate_data = duplicate_response.json()["data"]
    assert duplicate_data["has_duplicate_keys"] is True
    assert duplicate_data["duplicate_keys_preview"] == ["2"]
    assert duplicate_data["mapping"] == {}
    assert duplicate_data["loaded_rows"] == 0

    assert append_response.status_code == 200
    append_data = append_response.json()["data"]
    assert append_data["has_duplicate_keys"] is True
    assert sorted(append_data["mapping"]) == ["1_0", "2_1", "2_2"]
    assert append_data["loaded_rows"] == 3
    assert append_data["total_rows"] == 4


@pytest.mark.anyio
async def test_feishu_preview_e2e_rejects_key_column_not_in_columns(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id)
    _install_feishu_openapi_mock(monkeypatch, _build_sheet_openapi_handler())

    response = await auth_client.post(
        "/api/v1/sources/composite-preview",
        json={
            "source": _feishu_source_payload(),
            "sheet": "Items",
            "columns": ["Name", "Group"],
            "key_column": "ID",
        },
    )

    assert response.status_code == 400
    assert "主键列必须包含在组合列中" in response.json()["detail"]


def test_feishu_execution_pipeline_e2e_loads_single_and_composite_dataframes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_feishu_runtime_stubs(monkeypatch)

    result = run_execution_pipeline(
        TaskTree(
            sources=[
                DataSource(
                    id="src_feishu",
                    type="feishu",
                    pathOrUrl="https://demo.feishu.cn/sheets/shtcnabc123",
                )
            ],
            variables=[
                VariableTag(
                    tag="[items-name]",
                    source_id="src_feishu",
                    sheet="Items",
                    column="Name",
                ),
                VariableTag(
                    tag="[items-json]",
                    source_id="src_feishu",
                    sheet="Items",
                    variable_kind="composite",
                    columns=["ID", "Name", "Group"],
                    key_column="ID",
                    append_index_to_key=True,
                ),
            ],
            rules=[
                ValidationRule(
                    rule_type="not_null",
                    params={"target_tags": ["[items-name]"]},
                )
            ],
        ),
        project_id=1,
    )

    single_frame = result["loaded_variables"]["[items-name]"]
    composite_frame = result["loaded_variables"]["[items-json]"]
    assert list(single_frame.columns) == ["Name", "_row_index"]
    assert list(composite_frame.columns) == ["__key__", "ID", "Name", "Group", "_row_index"]
    assert composite_frame["__key__"].tolist() == ["1_0", "2_1", "2_2"]
    assert result["failed_sources"] == []
    assert any(item["location"] == "[items-name] -> Name" for item in result["abnormal_results"])


def test_feishu_execution_pipeline_e2e_failed_source_enters_failed_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _explode(*_args, **_kwargs):
        raise FeishuClientError(FEISHU_API_ERROR, "飞书 API 临时不可用")

    monkeypatch.setattr(feishu_client, "list_spreadsheet_sheets", _explode)

    result = run_execution_pipeline(
        TaskTree(
            sources=[
                DataSource(
                    id="src_feishu",
                    type="feishu",
                    pathOrUrl="https://demo.feishu.cn/sheets/shtcnabc123",
                )
            ],
            variables=[
                VariableTag(
                    tag="[items-name]",
                    source_id="src_feishu",
                    sheet="Items",
                    column="Name",
                )
            ],
            rules=[
                ValidationRule(
                    rule_type="not_null",
                    params={"target_tags": ["[items-name]"]},
                )
            ],
        ),
        project_id=1,
    )

    assert result["loaded_variables"] == {}
    assert result["failed_sources"] == ["src_feishu"]
    assert result["abnormal_results"] == []


@pytest.mark.anyio
async def test_feishu_authorization_e2e_check_permission_authorized(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id)
    _install_feishu_openapi_mock(monkeypatch, _build_sheet_openapi_handler())

    response = await auth_client.post(
        "/api/v1/feishu/sources/check-permission",
        json={
            "source_id": "src_feishu",
            "sheet_url": "https://demo.feishu.cn/sheets/shtcnabc123?sheet=gid_items",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "authorized"
    assert data["spreadsheet_token"] == "shtcnabc123"
    assert data["title"] == "配置校验表"


@pytest.mark.anyio
async def test_feishu_authorization_e2e_check_permission_pending_authorization(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _tenant_token_response()
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnabc123":
            return httpx.Response(403, json={"code": 1254030, "msg": "permission denied"})
        return httpx.Response(404)

    _install_feishu_openapi_mock(monkeypatch, handler)

    response = await auth_client.post(
        "/api/v1/feishu/sources/check-permission",
        json={
            "source_id": "src_feishu",
            "sheet_url": "https://demo.feishu.cn/sheets/shtcnabc123",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "pending_authorization",
        "error_status": "document_permission_denied",
        "message": "文档权限不足，请发送授权请求到群。",
    }


@pytest.mark.anyio
async def test_feishu_authorization_e2e_wiki_missing_scope_is_pending_authorization(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _tenant_token_response()
        if request.url.path == "/open-apis/wiki/v2/spaces/get_node":
            assert request.url.params["token"] == "RdxWwporRihMQVk5Lxxcr6Pjnfd"
            return httpx.Response(
                400,
                json={
                    "code": 99991672,
                    "msg": (
                        "Access denied. One of the following scopes is required: "
                        "[wiki:wiki, wiki:wiki:readonly, wiki:node:read]."
                    ),
                },
            )
        return httpx.Response(404)

    _install_feishu_openapi_mock(monkeypatch, handler)

    response = await auth_client.post(
        "/api/v1/feishu/sources/check-permission",
        json={
            "source_id": "src_feishu",
            "sheet_url": "https://t6bdpf8yjg.feishu.cn/wiki/RdxWwporRihMQVk5Lxxcr6Pjnfd",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "pending_authorization",
        "error_status": "document_permission_denied",
        "message": "文档权限不足，请发送授权请求到群。",
    }


@pytest.mark.anyio
async def test_feishu_authorization_e2e_send_card_creates_state_and_callback_succeeds(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id, default_chat_id="oc_default")
    object.__setattr__(
        settings,
        "feishu_oauth_callback_url",
        "https://example.com/api/v1/feishu/sources/oauth/callback",
    )
    captured: dict[str, Any] = {"notices": []}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _tenant_token_response()
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnabc123":
            return httpx.Response(403, json={"code": 1254030, "msg": "permission denied"})
        if request.url.path == "/open-apis/authen/v2/oauth/token":
            return httpx.Response(200, json={"access_token": "u_e2e"})
        if request.url.path == "/open-apis/authen/v1/user_info":
            assert request.headers["authorization"] == "Bearer u_e2e"
            return httpx.Response(200, json={"code": 0, "data": {"open_id": "ou_user"}})
        if request.url.path == "/open-apis/bot/v3/info":
            assert request.headers["authorization"] == "Bearer t_e2e"
            return httpx.Response(200, json={"code": 0, "data": {"bot": {"open_id": "ou_bot"}}})
        if request.url.path == "/open-apis/drive/v1/permissions/shtcnabc123/members":
            assert request.url.params["type"] == "sheet"
            assert json.loads(request.content.decode("utf-8")) == {
                "member_type": "openid",
                "member_id": "ou_bot",
                "perm": "view",
            }
            return httpx.Response(200, json={"code": 0, "data": {}})
        return httpx.Response(404)

    async def _fake_send_card(*, db, project_id, chat_id, card):  # noqa: ANN001
        captured["chat_id"] = chat_id
        captured["card"] = card
        return {"message_id": "om_auth_card", "raw": {}}

    async def _fake_send_text(*, db, project_id, chat_id, text):  # noqa: ANN001
        captured["notices"].append({"chat_id": chat_id, "text": text})
        return {"message_id": "om_notice", "raw": {}}

    _install_feishu_openapi_mock(monkeypatch, handler)
    monkeypatch.setattr("backend.app.api.feishu_api.send_card_to_chat", _fake_send_card)
    monkeypatch.setattr("backend.app.api.feishu_api.send_text_to_chat", _fake_send_text)

    send_response = await auth_client.post(
        "/api/v1/feishu/sources/send-authorization-card",
        json={
            "source_id": "src_feishu",
            "sheet_url": "https://demo.feishu.cn/sheets/shtcnabc123",
        },
    )
    assert send_response.status_code == 200
    assert send_response.json()["data"]["status"] == AUTHORIZATION_STATUS_SENT

    button_url = captured["card"]["elements"][1]["actions"][0]["url"]
    state = parse_qs(urlparse(button_url).query)["state"][0]
    async with async_session_factory() as session:
        sent_record = (
            await session.execute(select(FeishuSheetAuthorizationRecord))
        ).scalar_one()
    assert sent_record.state_hash == hash_authorization_state(state)
    assert sent_record.state_hash != state

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        callback_response = await client.get(
            "/api/v1/feishu/sources/oauth/callback",
            params={"code": "oauth-code", "state": state},
        )
        reused_response = await client.get(
            "/api/v1/feishu/sources/oauth/callback",
            params={"code": "oauth-code", "state": state},
        )

    assert callback_response.status_code == 200
    assert "飞书表格授权成功" in callback_response.text
    assert "授权请求不存在或已被使用" in reused_response.text
    async with async_session_factory() as session:
        authorized_record = (
            await session.execute(select(FeishuSheetAuthorizationRecord))
        ).scalar_one()
    assert authorized_record.status == AUTHORIZATION_STATUS_AUTHORIZED
    assert authorized_record.authorized_by_open_id == "ou_user"
    assert authorized_record.bot_open_id == "ou_bot"
    assert authorized_record.state_hash == ""
    assert authorized_record.state_expires_at is None
    assert captured["notices"] == [
        {
            "chat_id": "oc_default",
            "text": "飞书表格授权成功，机器人现在可以读取该配置表。",
        }
    ]


@pytest.mark.anyio
async def test_feishu_authorization_e2e_wiki_sheet_card_callback_resolves_real_token(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id, default_chat_id="oc_default")
    object.__setattr__(
        settings,
        "feishu_oauth_callback_url",
        "https://example.com/api/v1/feishu/sources/oauth/callback",
    )
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _tenant_token_response()
        if request.url.path == "/open-apis/wiki/v2/spaces/get_node":
            if request.headers.get("authorization") == "Bearer t_e2e":
                return httpx.Response(403, json={"code": 1254030, "msg": "permission denied"})
            assert request.headers.get("authorization") == "Bearer u_e2e"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "success",
                    "data": {
                        "node": {
                            "node_token": "wikcnabc123",
                            "obj_token": "shtcnreal456",
                            "obj_type": "sheet",
                        }
                    },
                },
            )
        if request.url.path == "/open-apis/authen/v2/oauth/token":
            return httpx.Response(200, json={"access_token": "u_e2e"})
        if request.url.path == "/open-apis/authen/v1/user_info":
            return httpx.Response(200, json={"code": 0, "data": {"open_id": "ou_user"}})
        if request.url.path == "/open-apis/bot/v3/info":
            return httpx.Response(200, json={"code": 0, "data": {"open_id": "ou_bot"}})
        if request.url.path == "/open-apis/drive/v1/permissions/shtcnreal456/members":
            captured["drive_body"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"code": 0, "data": {}})
        return httpx.Response(404)

    async def _fake_send_card(*, db, project_id, chat_id, card):  # noqa: ANN001
        captured["card"] = card
        return {"message_id": "om_auth_card", "raw": {}}

    async def _fake_send_text(*, db, project_id, chat_id, text):  # noqa: ANN001
        captured["notice"] = text
        return {"message_id": "om_notice", "raw": {}}

    _install_feishu_openapi_mock(monkeypatch, handler)
    monkeypatch.setattr("backend.app.api.feishu_api.send_card_to_chat", _fake_send_card)
    monkeypatch.setattr("backend.app.api.feishu_api.send_text_to_chat", _fake_send_text)

    send_response = await auth_client.post(
        "/api/v1/feishu/sources/send-authorization-card",
        json={
            "source_id": "src_feishu",
            "sheet_url": "https://demo.feishu.cn/wiki/wikcnabc123",
        },
    )
    assert send_response.status_code == 200
    assert send_response.json()["data"]["status"] == AUTHORIZATION_STATUS_SENT
    state = parse_qs(urlparse(captured["card"]["elements"][1]["actions"][0]["url"]).query)["state"][0]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        callback_response = await client.get(
            "/api/v1/feishu/sources/oauth/callback",
            params={"code": "oauth-code", "state": state},
        )

    assert callback_response.status_code == 200
    assert "飞书表格授权成功" in callback_response.text
    assert captured["drive_body"] == {
        "member_type": "openid",
        "member_id": "ou_bot",
        "perm": "view",
    }
    async with async_session_factory() as session:
        record = (await session.execute(select(FeishuSheetAuthorizationRecord))).scalar_one()
    assert record.status == AUTHORIZATION_STATUS_AUTHORIZED
    assert record.spreadsheet_token == "shtcnreal456"
    assert record.sheet_url == "https://demo.feishu.cn/sheets/shtcnreal456"
    assert record.state_hash == ""


@pytest.mark.anyio
async def test_feishu_authorization_e2e_callback_expired_state_fails(
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id, default_chat_id="oc_default")
    await _seed_sent_authorization(test_project_id, state="expired-state", expires_delta_seconds=-1)
    notices: list[str] = []

    async def _fake_send_text(*, db, project_id, chat_id, text):  # noqa: ANN001
        notices.append(text)
        return {"message_id": "om_notice", "raw": {}}

    monkeypatch.setattr("backend.app.api.feishu_api.send_text_to_chat", _fake_send_text)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get(
            "/api/v1/feishu/sources/oauth/callback",
            params={"code": "oauth-code", "state": "expired-state"},
        )

    assert response.status_code == 200
    assert "授权请求已过期" in response.text
    async with async_session_factory() as session:
        record = (await session.execute(select(FeishuSheetAuthorizationRecord))).scalar_one()
    assert record.status == AUTHORIZATION_STATUS_AUTHORIZATION_FAILED
    assert record.state_hash == ""
    assert notices == ["授权失败：授权请求已过期，请重新发送授权请求。"]


@pytest.mark.anyio
async def test_feishu_authorization_e2e_callback_share_permission_failure(
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id, default_chat_id="oc_default")
    await _seed_sent_authorization(test_project_id, state="share-denied")
    object.__setattr__(
        settings,
        "feishu_oauth_callback_url",
        "https://example.com/api/v1/feishu/sources/oauth/callback",
    )
    notices: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/open-apis/authen/v2/oauth/token":
            return httpx.Response(200, json={"access_token": "u_e2e"})
        if request.url.path == "/open-apis/authen/v1/user_info":
            return httpx.Response(200, json={"code": 0, "data": {"open_id": "ou_user"}})
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _tenant_token_response()
        if request.url.path == "/open-apis/bot/v3/info":
            return httpx.Response(200, json={"code": 0, "data": {"open_id": "ou_bot"}})
        if request.url.path == "/open-apis/drive/v1/permissions/shtcnabc123/members":
            return httpx.Response(403, json={"code": 1254030, "msg": "permission denied"})
        return httpx.Response(404)

    async def _fake_send_text(*, db, project_id, chat_id, text):  # noqa: ANN001
        notices.append(text)
        return {"message_id": "om_notice", "raw": {}}

    _install_feishu_openapi_mock(monkeypatch, handler)
    monkeypatch.setattr("backend.app.api.feishu_api.send_text_to_chat", _fake_send_text)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get(
            "/api/v1/feishu/sources/oauth/callback",
            params={"code": "oauth-code", "state": "share-denied"},
        )

    message = (
        "授权失败：飞书拒绝添加机器人为表格协作者。请确认当前用户是文档所有者或可管理协作者，"
        "并确认飞书应用已开通“添加云文档协作者”或云文档权限管理相关权限且已发布生效。"
    )
    assert response.status_code == 200
    assert message in response.text
    async with async_session_factory() as session:
        record = (await session.execute(select(FeishuSheetAuthorizationRecord))).scalar_one()
    assert record.status == AUTHORIZATION_STATUS_AUTHORIZATION_FAILED
    assert record.error_message == message
    assert record.state_hash == ""
    assert notices == [message]


@pytest.mark.anyio
async def test_local_excel_metadata_preview_execution_regression(tmp_path: Path) -> None:
    workbook_path = _create_regression_workbook(tmp_path / "local_regression.xlsx")
    source = {"id": "src_local", "type": "local_excel", "path": str(workbook_path)}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        metadata_response = await client.post("/api/v1/sources/metadata", json=source)
        preview_response = await client.post(
            "/api/v1/sources/column-preview",
            json={"source": source, "sheet": "Items", "column": "Name", "limit": 2},
        )
        composite_response = await client.post(
            "/api/v1/sources/composite-preview",
            json={
                "source": source,
                "sheet": "Items",
                "columns": ["ID", "Name", "Group"],
                "key_column": "ID",
                "append_index_to_key": True,
            },
        )
        execute_response = await client.post(
            "/api/v1/engine/execute",
            json=_not_null_execute_payload(source),
        )

    assert metadata_response.status_code == 200
    assert metadata_response.json()["data"]["sheets"][0]["columns"] == ["ID", "Name", "Group"]
    assert preview_response.status_code == 200
    assert preview_response.json()["data"]["preview_rows"][0] == {"row_index": 2, "value": "Alpha"}
    assert composite_response.status_code == 200
    assert sorted(composite_response.json()["data"]["mapping"]) == ["1_0", "2_1", "2_2", "3_3"]
    assert execute_response.status_code == 200
    assert execute_response.json()["meta"]["failed_sources"] == []
    assert any(
        item["row_index"] == 5
        for item in execute_response.json()["data"]["abnormal_results"]
    )


@pytest.mark.anyio
async def test_svn_metadata_preview_execution_regression(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.loaders import svn_cache

    workbook_path = _create_regression_workbook(tmp_path / "svn_regression.xlsx")
    monkeypatch.setattr(svn_cache, "prepare_remote_svn_source", lambda *_args, **_kwargs: workbook_path)
    source = {
        "id": "src_svn",
        "type": "svn",
        "pathOrUrl": "https://samosvn/data/project/samo/GameDatas/datas_qa88/items.xlsx",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        metadata_response = await client.post("/api/v1/sources/metadata", json=source)
        preview_response = await client.post(
            "/api/v1/sources/column-preview",
            json={"source": source, "sheet": "Items", "column": "Name", "limit": 2},
        )
        composite_response = await client.post(
            "/api/v1/sources/composite-preview",
            json={
                "source": source,
                "sheet": "Items",
                "columns": ["ID", "Name", "Group"],
                "key_column": "ID",
                "append_index_to_key": True,
            },
        )
        execute_response = await client.post(
            "/api/v1/engine/execute",
            json=_not_null_execute_payload(source),
        )

    assert metadata_response.status_code == 200
    assert metadata_response.json()["data"]["source_type"] == "svn"
    assert preview_response.status_code == 200
    assert preview_response.json()["data"]["source_type"] == "svn"
    assert composite_response.status_code == 200
    assert composite_response.json()["data"]["source_type"] == "svn"
    assert execute_response.status_code == 200
    assert execute_response.json()["meta"]["failed_sources"] == []


async def _seed_feishu_bot_config(
    project_id: int,
    *,
    default_chat_id: str = "",
) -> None:
    async with async_session_factory() as session:
        session.add(
            FeishuBotConfigRecord(
                project_id=project_id,
                app_id="e2e_app",
                app_secret_cipher=encrypt_secret("e2e_secret"),
                default_chat_id=default_chat_id,
            )
        )
        await session.commit()


async def _seed_sent_authorization(
    project_id: int,
    *,
    state: str,
    expires_delta_seconds: int = 600,
) -> None:
    async with async_session_factory() as session:
        await upsert_authorization_record(
            session,
            project_id=project_id,
            source_id="src_feishu",
            spreadsheet_token="shtcnabc123",
            sheet_url="https://demo.feishu.cn/sheets/shtcnabc123",
            sheet_title="配置校验表",
            status=AUTHORIZATION_STATUS_SENT,
            chat_id="oc_default",
            message_id="om_auth_card",
            state_hash=hash_authorization_state(state),
            state_expires_at=datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(seconds=expires_delta_seconds),
        )
        await session.commit()


def _install_feishu_openapi_mock(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    transport = httpx.MockTransport(handler)

    def _factory(timeout: float = 10.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=transport,
            base_url=feishu_bot.FEISHU_OPEN_BASE_URL,
            timeout=timeout,
        )

    monkeypatch.setattr(feishu_bot, "_create_async_client", _factory)
    monkeypatch.setattr(feishu_client, "_create_async_client", _factory)


def _tenant_token_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "ok",
            "tenant_access_token": "t_e2e",
            "expire": 7200,
        },
    )


def _build_sheet_openapi_handler() -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            assert json.loads(request.content.decode("utf-8")) == {
                "app_id": "e2e_app",
                "app_secret": "e2e_secret",
            }
            return _tenant_token_response()
        assert request.headers.get("authorization") == "Bearer t_e2e"
        if request.url.path == "/open-apis/wiki/v2/spaces/get_node":
            assert request.url.params["token"] == "wikcnabc123"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "success",
                    "data": {
                        "node": {
                            "node_token": "wikcnabc123",
                            "obj_token": "shtcnabc123",
                            "obj_type": "sheet",
                        }
                    },
                },
            )
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnabc123":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "success",
                    "data": {
                        "spreadsheet": {
                            "token": "shtcnabc123",
                            "title": "配置校验表",
                            "url": "https://demo.feishu.cn/sheets/shtcnabc123",
                            "owner_id": "ou_owner",
                        }
                    },
                },
            )
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnabc123/sheets/query":
            return _sheets_response()
        if request.url.path == "/open-apis/sheets/v2/spreadsheets/shtcnabc123/values/gid_items!A1:C5":
            return _values_response(
                "gid_items!A1:C5",
                [
                    ["ID", "Name", "Group"],
                    [1, "Alpha", "A"],
                    [2, "Beta", "B"],
                    [2, "Beta Duplicate", "B"],
                    ["", "", "C"],
                ],
            )
        if request.url.path == "/open-apis/sheets/v2/spreadsheets/shtcnabc123/values/gid_lookup!A1:B3":
            return _values_response(
                "gid_lookup!A1:B3",
                [
                    ["RefID", "Label"],
                    [1, "One"],
                    [2, "Two"],
                ],
            )
        return httpx.Response(404, json={"code": 404, "msg": "not found"})

    return handler


def _sheets_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "success",
            "data": {
                "sheets": [
                    {
                        "sheet_id": "gid_items",
                        "title": "Items",
                        "index": 0,
                        "hidden": False,
                        "resource_type": "sheet",
                        "grid_properties": {"row_count": 5, "column_count": 3},
                    },
                    {
                        "sheet_id": "gid_lookup",
                        "title": "Lookup",
                        "index": 1,
                        "hidden": False,
                        "resource_type": "sheet",
                        "grid_properties": {"row_count": 3, "column_count": 2},
                    },
                ]
            },
        },
    )


def _values_response(range_name: str, values: list[list[Any]]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "success",
            "data": {
                "spreadsheetToken": "shtcnabc123",
                "valueRange": {
                    "range": range_name,
                    "values": values,
                },
            },
        },
    )


def _feishu_source_payload() -> dict[str, str]:
    return {
        "id": "src_feishu",
        "type": "feishu",
        "pathOrUrl": "https://demo.feishu.cn/sheets/shtcnabc123",
    }


def _install_feishu_runtime_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _list_sheets(*_args, **_kwargs):
        return [
            FeishuSheetMetadata(
                sheet_id="gid_items",
                title="Items",
                index=0,
                row_count=5,
                column_count=3,
                hidden=False,
                resource_type="sheet",
            )
        ]

    async def _read_values(*_args, **_kwargs):
        return FeishuSheetTable(
            spreadsheet_token="shtcnabc123",
            sheet_id="gid_items",
            sheet_title="Items",
            range="gid_items!A1:C5",
            columns=["ID", "Name", "Group"],
            rows=[],
            raw_values=[
                ["ID", "Name", "Group"],
                [1, "Alpha", "A"],
                [2, "", "B"],
                [2, "Beta Duplicate", "B"],
                ["", "", "C"],
            ],
        )

    monkeypatch.setattr(feishu_client, "list_spreadsheet_sheets", _list_sheets)
    monkeypatch.setattr(feishu_client, "read_sheet_values", _read_values)


def _create_regression_workbook(target_path: Path) -> Path:
    with pd.ExcelWriter(target_path, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "ID": [1, 2, 2, 3],
                "Name": ["Alpha", "Beta", "Beta Duplicate", ""],
                "Group": ["A", "B", "B", "C"],
            }
        ).to_excel(writer, sheet_name="Items", index=False)
    return target_path


def _not_null_execute_payload(source: dict[str, str]) -> dict[str, Any]:
    return {
        "sources": [source],
        "variables": [
            {
                "tag": "[items-name]",
                "source_id": source["id"],
                "sheet": "Items",
                "column": "Name",
            }
        ],
        "rules": [
            {
                "rule_type": "not_null",
                "params": {"target_tags": ["[items-name]"]},
            }
        ],
    }
