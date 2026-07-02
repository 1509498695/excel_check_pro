"""飞书电子表格 OpenAPI 客户端单元测试。"""

from __future__ import annotations

import json
from typing import Callable

import httpx
import pytest

from backend.app.database import async_session_factory
from backend.app.integrations import feishu_bot, feishu_client
from backend.app.integrations.feishu_client import (
    FEISHU_API_ERROR,
    FEISHU_APP_PERMISSION_MISSING,
    FEISHU_DOCUMENT_NOT_FOUND,
    FEISHU_DOCUMENT_PERMISSION_DENIED,
    FEISHU_INVALID_URL,
    FEISHU_METADATA_UNAVAILABLE,
    FEISHU_READ_RANGE_TOO_LARGE,
    FeishuClientError,
    add_source_document_collaborator,
    feishu_json_request,
    get_drive_metadata,
    get_feishu_tenant_access_token,
    get_spreadsheet_metadata,
    list_spreadsheet_sheets,
    read_sheet_columns,
    read_sheet_values,
    resolve_feishu_wiki_node,
    resolve_source_evidence_wiki_node,
    resolve_wiki_sheet_locator,
)
from backend.app.loaders.feishu_reader import parse_feishu_sheet_url
from backend.app.models import FeishuBotConfigRecord
from backend.app.security.crypto import encrypt_secret


@pytest.fixture(autouse=True)
def _clear_feishu_state() -> None:
    """每个用例清空现有 token 缓存，避免跨用例污染。"""
    feishu_bot._TOKEN_CACHE.clear()
    feishu_bot._TOKEN_LOCKS.clear()
    yield
    feishu_bot._TOKEN_CACHE.clear()
    feishu_bot._TOKEN_LOCKS.clear()


async def _seed_feishu_config(project_id: int) -> None:
    async with async_session_factory() as session:
        session.add(
            FeishuBotConfigRecord(
                project_id=project_id,
                app_id="cli_unit",
                app_secret_cipher=encrypt_secret("secret_unit"),
                default_chat_id="",
            )
        )
        await session.commit()


def _install_mock_transport(
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


def _token_response(token: str = "t_sheet") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "ok",
            "tenant_access_token": token,
            "expire": 7200,
        },
    )


def _spreadsheet_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "success",
            "data": {
                "spreadsheet": {
                    "token": "shtcnabc123",
                    "title": "需求明细",
                    "url": "https://demo.feishu.cn/sheets/shtcnabc123",
                    "owner_id": "ou_owner",
                }
            },
        },
    )


def _sheets_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "success",
            "data": {
                "sheets": [
                    {
                        "sheet_id": "hidden1",
                        "title": "隐藏页",
                        "index": 0,
                        "hidden": True,
                        "resource_type": "sheet",
                        "grid_properties": {"row_count": 5, "column_count": 2},
                    },
                    {
                        "sheet_id": "gid001",
                        "title": "Sheet1",
                        "index": 1,
                        "hidden": False,
                        "resource_type": "sheet",
                        "grid_properties": {"row_count": 3, "column_count": 28},
                    },
                    {
                        "sheet_id": "gid002",
                        "title": "Sheet2",
                        "index": 2,
                        "hidden": False,
                        "resource_type": "sheet",
                        "grid_properties": {"row_count": 2, "column_count": 3},
                    },
                ]
            },
        },
    )


def _values_response(range_name: str = "gid001!A1:AB3") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "success",
            "data": {
                "spreadsheetToken": "shtcnabc123",
                "valueRange": {
                    "range": range_name,
                    "values": [
                        ["姓名", "", "姓名"],
                        ["张三", 18, "研发"],
                        ["李四"],
                    ],
                },
            },
        },
    )


def _header_values_response(range_name: str = "gid001!A1:AB1") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "success",
            "data": {
                "spreadsheetToken": "shtcnabc123",
                "valueRange": {
                    "range": range_name,
                    "values": [["test1", "test2", "", None]],
                },
            },
        },
    )


@pytest.mark.anyio
async def test_get_feishu_tenant_access_token_reuses_bot_config_and_cache(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_config(test_project_id)
    token_calls = {"value": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        token_calls["value"] += 1
        assert request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH
        body = json.loads(request.content.decode("utf-8"))
        assert body == {"app_id": "cli_unit", "app_secret": "secret_unit"}
        return _token_response("t_cached")

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        first = await get_feishu_tenant_access_token(session, test_project_id)
        second = await get_feishu_tenant_access_token(session, test_project_id)

    assert first == "t_cached"
    assert second == "t_cached"
    assert token_calls["value"] == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("doc_type", "expected_drive_type"),
    [
        ("docx", "doc"),
        ("docs", "doc"),
        ("sheets", "sheet"),
        ("base", "bitable"),
        ("bitable", "bitable"),
    ],
)
async def test_add_source_document_collaborator_supports_edit_permission(
    monkeypatch: pytest.MonkeyPatch,
    doc_type: str,
    expected_drive_type: str,
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/open-apis/drive/permission/member/create"
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={"code": 0, "msg": "success", "data": {"is_all_success": True}},
        )

    _install_mock_transport(monkeypatch, handler)

    result = await add_source_document_collaborator(
        user_access_token="u_source",
        source_token="src_token",
        bot_open_id="ou_bot",
        doc_type=doc_type,
        perm="edit",
    )

    assert result["is_all_success"] is True
    assert captured["headers"].get("authorization") == "Bearer u_source"
    assert captured["body"] == {
        "token": "src_token",
        "type": expected_drive_type,
        "members": [
            {"member_type": "openid", "member_id": "ou_bot", "perm": "edit"}
        ],
        "notify_lark": False,
    }


@pytest.mark.anyio
async def test_add_sheet_viewer_collaborator_keeps_view_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/open-apis/drive/v1/permissions/shtcnabc123/members"
        captured["query"] = dict(request.url.params)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"code": 0, "msg": "success"})

    _install_mock_transport(monkeypatch, handler)

    await feishu_client.add_sheet_viewer_collaborator(
        user_access_token="u_sheet",
        spreadsheet_token="shtcnabc123",
        bot_open_id="ou_bot",
    )

    assert captured["query"] == {"type": "sheet"}
    assert captured["headers"].get("authorization") == "Bearer u_sheet"
    assert captured["body"] == {
        "member_type": "openid",
        "member_id": "ou_bot",
        "perm": "view",
    }


@pytest.mark.anyio
async def test_get_spreadsheet_metadata_success(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_config(test_project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        assert request.headers["authorization"] == "Bearer t_sheet"
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnabc123":
            return _spreadsheet_response()
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        metadata = await get_spreadsheet_metadata(
            session,
            test_project_id,
            parse_feishu_sheet_url("https://demo.feishu.cn/sheets/shtcnabc123"),
        )

    assert metadata.token == "shtcnabc123"
    assert metadata.title == "需求明细"
    assert metadata.owner_id == "ou_owner"


@pytest.mark.anyio
async def test_get_drive_metadata_normalizes_owner_and_creator(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_config(test_project_id)
    captured_body: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_body
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response("t_drive")
        assert request.headers["authorization"] == "Bearer t_drive"
        if request.url.path == "/open-apis/drive/v1/metas/batch_query":
            captured_body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "success",
                    "data": {
                        "metas": [
                            {
                                "doc_token": "doccnabc123",
                                "doc_type": "doc",
                                "title": "源需求文档",
                                "owner_id": "ou_owner",
                                "creator": {"open_id": "ou_creator"},
                            }
                        ]
                    },
                },
            )
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        metadata = await get_drive_metadata(
            session,
            test_project_id,
            "doccnabc123",
            "docx",
        )

    assert captured_body == {
        "request_docs": [{"doc_token": "doccnabc123", "doc_type": "doc"}],
        "with_url": True,
    }
    assert metadata.token == "doccnabc123"
    assert metadata.doc_type == "docx"
    assert metadata.drive_type == "doc"
    assert metadata.title == "源需求文档"
    assert metadata.owner_ids == ["ou_owner"]
    assert metadata.creator_ids == ["ou_creator"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "metadata_response",
    [
        httpx.Response(403, json={"code": 99991663, "msg": "missing scope"}),
        httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "success",
                "data": {
                    "failed_list": [
                        {
                            "doc_token": "doccnabc123",
                            "reason": "metadata permission denied",
                        }
                    ],
                    "metas": [],
                },
            },
        ),
        httpx.Response(200, json={"code": 0, "msg": "success", "data": {"metas": []}}),
    ],
)
async def test_get_drive_metadata_failure_is_degradable(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
    metadata_response: httpx.Response,
) -> None:
    await _seed_feishu_config(test_project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response("t_drive")
        if request.url.path == "/open-apis/drive/v1/metas/batch_query":
            return metadata_response
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        with pytest.raises(FeishuClientError) as exc_info:
            await get_drive_metadata(
                session,
                test_project_id,
                "doccnabc123",
                "docx",
            )

    assert exc_info.value.code == FEISHU_METADATA_UNAVAILABLE
    assert "metadata 不可用" in str(exc_info.value)


@pytest.mark.anyio
async def test_wiki_sheet_link_resolves_to_spreadsheet_token_before_metadata(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_config(test_project_id)
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
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
            return _spreadsheet_response()
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        metadata = await get_spreadsheet_metadata(
            session,
            test_project_id,
            "https://demo.feishu.cn/wiki/wikcnabc123",
        )

    assert metadata.token == "shtcnabc123"
    assert requested_paths == [
        feishu_bot.TENANT_ACCESS_TOKEN_PATH,
        "/open-apis/wiki/v2/spaces/get_node",
        "/open-apis/sheets/v3/spreadsheets/shtcnabc123",
    ]


@pytest.mark.anyio
async def test_wiki_node_that_is_not_sheet_maps_to_invalid_url(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_config(test_project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        if request.url.path == "/open-apis/wiki/v2/spaces/get_node":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "success",
                    "data": {"node": {"obj_token": "doccn123", "obj_type": "docx"}},
                },
            )
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        with pytest.raises(FeishuClientError) as exc_info:
            await resolve_wiki_sheet_locator(
                session,
                test_project_id,
                "https://demo.feishu.cn/wiki/wikcnabc123",
            )

    assert exc_info.value.code == FEISHU_INVALID_URL
    assert "不是飞书电子表格" in str(exc_info.value)


@pytest.mark.anyio
async def test_resolve_source_evidence_wiki_node_returns_real_token_and_alias(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_config(test_project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        if request.url.path == "/open-apis/wiki/v2/spaces/get_node":
            assert request.url.params["token"] == "wikcnabc123"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "success",
                    "data": {
                        "node": {
                            "obj_token": "doccnreal123",
                            "obj_type": "docx",
                            "title": "源需求文档",
                        }
                    },
                },
            )
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        node = await resolve_source_evidence_wiki_node(
            session,
            test_project_id,
            "wikcnabc123",
        )

    assert node.wiki_token == "wikcnabc123"
    assert node.obj_token == "doccnreal123"
    assert node.doc_type == "docx"
    assert node.title == "源需求文档"


@pytest.mark.anyio
async def test_list_spreadsheet_sheets_success(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_config(test_project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnabc123/sheets/query":
            return _sheets_response()
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        sheets = await list_spreadsheet_sheets(
            session,
            test_project_id,
            "https://demo.feishu.cn/sheets/shtcnabc123",
        )

    assert [sheet.sheet_id for sheet in sheets] == ["hidden1", "gid001", "gid002"]
    assert sheets[1].row_count == 3
    assert sheets[1].column_count == 28
    assert sheets[1].hidden is False


@pytest.mark.anyio
async def test_read_sheet_values_uses_sheet_from_locator_and_builds_rows(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_config(test_project_id)
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnabc123/sheets/query":
            return _sheets_response()
        if request.url.path == "/open-apis/sheets/v2/spreadsheets/shtcnabc123/values/gid002!A1:C2":
            return _values_response("gid002!A1:C2")
        return httpx.Response(404, json={"code": 404, "msg": "not found"})

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        table = await read_sheet_values(
            session,
            test_project_id,
            "https://demo.feishu.cn/sheets/shtcnabc123?sheet=gid002",
        )

    assert "/open-apis/sheets/v2/spreadsheets/shtcnabc123/values/gid002!A1:C2" in requested_paths
    assert table.sheet_id == "gid002"
    assert table.columns == ["姓名", "Unnamed: 2", "姓名.1"]
    assert table.rows == [
        {"姓名": "张三", "Unnamed: 2": 18, "姓名.1": "研发"},
        {"姓名": "李四", "Unnamed: 2": None, "姓名.1": None},
    ]
    assert table.raw_values[0] == ["姓名", "", "姓名"]


@pytest.mark.anyio
async def test_read_sheet_values_defaults_to_first_visible_sheet(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_config(test_project_id)
    captured_values_path = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_values_path
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnabc123/sheets/query":
            return _sheets_response()
        if request.url.path.startswith("/open-apis/sheets/v2/"):
            captured_values_path = request.url.path
            return _values_response()
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        table = await read_sheet_values(
            session,
            test_project_id,
            "https://demo.feishu.cn/sheets/shtcnabc123",
        )

    assert table.sheet_id == "gid001"
    assert captured_values_path.endswith("/values/gid001!A1:AB3")


@pytest.mark.anyio
async def test_read_sheet_columns_returns_first_row_columns(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_config(test_project_id)
    captured_values_path = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_values_path
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnabc123/sheets/query":
            return _sheets_response()
        if request.url.path.startswith("/open-apis/sheets/v2/"):
            captured_values_path = request.url.path
            return _header_values_response()
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        columns = await read_sheet_columns(
            session,
            test_project_id,
            "https://demo.feishu.cn/sheets/shtcnabc123",
    )

    assert captured_values_path.endswith("/values/gid001!A1:AB1")
    assert columns == ["test1", "test2"]


@pytest.mark.anyio
async def test_invalid_url_maps_to_internal_error(
    test_db,
    test_project_id: int,
) -> None:
    async with async_session_factory() as session:
        with pytest.raises(FeishuClientError) as exc_info:
            await get_spreadsheet_metadata(session, test_project_id, "not-a-url")

    assert exc_info.value.code == FEISHU_INVALID_URL
    assert str(exc_info.value) == "请输入合法的飞书电子表格链接"


@pytest.mark.anyio
async def test_token_error_maps_to_app_permission_missing(
    test_db,
    test_project_id: int,
) -> None:
    async with async_session_factory() as session:
        with pytest.raises(FeishuClientError) as exc_info:
            await get_feishu_tenant_access_token(session, test_project_id)

    assert exc_info.value.code == FEISHU_APP_PERMISSION_MISSING
    assert "飞书应用凭证不可用" in str(exc_info.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        (
            httpx.Response(403, json={"code": 1254030, "msg": "permission denied"}),
            FEISHU_DOCUMENT_PERMISSION_DENIED,
        ),
        (
            httpx.Response(404, json={"code": 1254040, "msg": "not found"}),
            FEISHU_DOCUMENT_NOT_FOUND,
        ),
        (
            httpx.Response(200, json={"code": 90227, "msg": "range too large 10MB"}),
            FEISHU_READ_RANGE_TOO_LARGE,
        ),
        (
            httpx.Response(200, json={"code": 99999, "msg": "unknown error"}),
            FEISHU_API_ERROR,
        ),
    ],
)
async def test_api_errors_map_to_internal_codes(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
    response: httpx.Response,
    expected_code: str,
) -> None:
    await _seed_feishu_config(test_project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnabc123":
            return response
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        with pytest.raises(FeishuClientError) as exc_info:
            await get_spreadsheet_metadata(
                session,
                test_project_id,
                "https://demo.feishu.cn/sheets/shtcnabc123",
            )

    assert exc_info.value.code == expected_code


@pytest.mark.anyio
async def test_error_message_redacts_sensitive_markers(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_config(test_project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        return httpx.Response(
            500,
            text=(
                "app_secret=secret_unit tenant_access_token=t_sheet "
                "user_access_token=u_x OAuth code=abc "
                "Authorization: Bearer t_header Bearer u_header"
            ),
        )

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        with pytest.raises(FeishuClientError) as exc_info:
            await get_spreadsheet_metadata(
                session,
                test_project_id,
                "https://demo.feishu.cn/sheets/shtcnabc123",
            )

    message = str(exc_info.value)
    assert "app_secret" not in message
    assert "tenant_access_token" not in message
    assert "user_access_token" not in message
    assert "OAuth code" not in message
    assert "Authorization" not in message
    assert "Bearer" not in message
    assert "secret_unit" not in message
    assert "t_sheet" not in message
    assert "u_x" not in message
    assert "t_header" not in message
    assert "u_header" not in message


@pytest.mark.anyio
async def test_feishu_json_request_supports_post_json_payload(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_config(test_project_id)
    captured_body: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_body
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response("t_post")
        assert request.headers["authorization"] == "Bearer t_post"
        if request.url.path == "/open-apis/bitable/v1/apps/app123/tables/tbl123/records/search":
            captured_body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={"code": 0, "msg": "success", "data": {"items": [{"record_id": "rec1"}]}},
            )
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        payload = await feishu_json_request(
            session,
            test_project_id,
            "POST",
            "/bitable/v1/apps/app123/tables/tbl123/records/search",
            json_payload={"view_id": "vew1"},
        )

    assert captured_body == {"view_id": "vew1"}
    assert payload["data"]["items"][0]["record_id"] == "rec1"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("obj_type", "expected_doc_type"),
    [
        ("docx", "docx"),
        ("sheet", "sheets"),
        ("bitable", "bitable"),
        ("base", "bitable"),
    ],
)
async def test_resolve_feishu_wiki_node_returns_supported_object_types(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
    obj_type: str,
    expected_doc_type: str,
) -> None:
    await _seed_feishu_config(test_project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        if request.url.path == "/open-apis/wiki/v2/spaces/get_node":
            assert request.url.params["token"] == "wikcnabc123"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "success",
                    "data": {
                        "node": {
                            "obj_type": obj_type,
                            "obj_token": f"{obj_type}_token",
                            "title": "Wiki 节点",
                        }
                    },
                },
            )
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        node = await resolve_feishu_wiki_node(session, test_project_id, "wikcnabc123")

    assert node.doc_type == expected_doc_type
    assert node.obj_token == f"{obj_type}_token"
    assert node.title == "Wiki 节点"


@pytest.mark.anyio
async def test_feishu_json_request_redacts_sensitive_markers(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_config(test_project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        return httpx.Response(
            500,
            text=(
                "app_secret=secret_unit tenant_access_token=t_sheet "
                "user_access_token=u_x OAuth code=abc "
                "Authorization: Bearer t_header Bearer u_header"
            ),
        )

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        with pytest.raises(FeishuClientError) as exc_info:
            await feishu_json_request(
                session,
                test_project_id,
                "GET",
                "/docx/v1/documents/doccnabc123/raw_content",
            )

    message = str(exc_info.value)
    assert "app_secret" not in message
    assert "tenant_access_token" not in message
    assert "user_access_token" not in message
    assert "OAuth code" not in message
    assert "Authorization" not in message
    assert "Bearer" not in message
    assert "secret_unit" not in message
    assert "t_sheet" not in message
    assert "u_x" not in message
    assert "t_header" not in message
    assert "u_header" not in message
