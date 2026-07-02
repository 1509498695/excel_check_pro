"""飞书 Sheets 富读取 adapter 测试。"""

from __future__ import annotations

import json
from typing import Callable

import httpx
import pytest

from backend.app.database import async_session_factory
from backend.app.integrations import feishu_bot, feishu_client
from backend.app.models import FeishuBotConfigRecord
from backend.app.security.crypto import encrypt_secret
from backend.app.test_cases.feishu_rich_reader import read_feishu_parsed_source


@pytest.fixture(autouse=True)
def _clear_feishu_state() -> None:
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
                app_id="rich_sheet_unit",
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


def _token_response(token: str = "t_rich_sheet") -> httpx.Response:
    return httpx.Response(
        200,
        json={"code": 0, "msg": "ok", "tenant_access_token": token, "expire": 7200},
    )


def _spreadsheet_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "success",
            "data": {"spreadsheet": {"token": "shtcnrich123", "title": "富表格"}},
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
                        "grid_properties": {"row_count": 2, "column_count": 2},
                    },
                    {
                        "sheet_id": "gid001",
                        "title": "需求",
                        "index": 1,
                        "hidden": False,
                        "grid_properties": {"row_count": 3, "column_count": 50},
                    },
                    {
                        "sheet_id": "gid002",
                        "title": "配置",
                        "index": 2,
                        "hidden": False,
                        "grid_properties": {"row_count": 2, "column_count": 3},
                    },
                ]
            },
        },
    )


def _values_response(sheet_id: str, range_name: str) -> httpx.Response:
    values = {
        "gid001": [
            ["标题", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "备注"],
            ["登录", {"file_token": "cell_img", "name": "ui.png", "mime_type": "image/png"}],
            ["", "", "稀疏内容"],
        ],
        "gid002": [["字段", "说明"], ["id", "标识"]],
    }[sheet_id]
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "success",
            "data": {
                "spreadsheetToken": "shtcnrich123",
                "valueRange": {"range": range_name, "values": values},
            },
        },
    )


def _float_images_response(items: list[dict[str, object]]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "success",
            "data": {"items": items},
        },
    )


@pytest.mark.anyio
async def test_sheets_rich_reader_excludes_hidden_sheets_and_keeps_sparse_cells(
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
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnrich123":
            return _spreadsheet_response()
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnrich123/sheets/query":
            return _sheets_response()
        if request.url.path == "/open-apis/sheets/v2/spreadsheets/shtcnrich123/values/gid001!A1:AX3":
            return _values_response("gid001", "gid001!A1:AX3")
        if request.url.path == "/open-apis/sheets/v2/spreadsheets/shtcnrich123/values/gid002!A1:C2":
            return _values_response("gid002", "gid002!A1:C2")
        if request.url.path.endswith("/gid001/float_images/query"):
            return _float_images_response(
                [
                    {
                        "float_image_token": "float_img",
                        "float_image_id": "flt1",
                        "anchor": "C3",
                        "mime_type": "image/png",
                        "name": "float.png",
                    }
                ]
            )
        if request.url.path.endswith("/gid002/float_images/query"):
            return _float_images_response([])
        return httpx.Response(404, json={"code": 404, "msg": "not found"})

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        parsed = await read_feishu_parsed_source(
            session,
            test_project_id,
            "https://demo.feishu.cn/sheets/shtcnrich123",
        )

    assert parsed.doc_type == "sheets"
    assert [unit.title for unit in parsed.source_units] == ["需求", "配置"]
    assert any("隐藏页" in warning.message and "已排除" in warning.message for warning in parsed.warnings)
    assert not any("hidden1" in path and "/values/" in path for path in requested_paths)

    requirement_unit = parsed.source_units[0]
    assert {cell.coord for cell in requirement_unit.cells} == {"A1", "AX1", "A2", "B2", "C3"}
    assert "AX1" in parsed.markdown
    requirement_section = parsed.markdown.split("## Sheet: 配置", 1)[0]
    assert "B1" not in requirement_section
    assert len(parsed.markdown) < 2000
    assert {resource.source_id: resource.position for resource in parsed.resources} == {
        "cell_img": "需求!B2",
        "float_img": "需求!C3",
    }
    manifest_text = json.dumps(parsed.raw_manifest, ensure_ascii=False)
    assert "hidden1" in manifest_text
    assert "gid001" in manifest_text
