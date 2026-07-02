"""飞书 DOCX 富读取 adapter 测试。"""

from __future__ import annotations

import json
from typing import Callable

import httpx
import pytest

from backend.app.database import async_session_factory
from backend.app.integrations import feishu_bot, feishu_client
from backend.app.integrations.feishu_client import FeishuClientError
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
                app_id="rich_docx_unit",
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


def _token_response(token: str = "t_rich_docx") -> httpx.Response:
    return httpx.Response(
        200,
        json={"code": 0, "msg": "ok", "tenant_access_token": token, "expire": 7200},
    )


def _raw_content_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "success",
            "data": {
                "title": "需求文档",
                "content": "raw content mentions image.png but that is not evidence",
            },
        },
    )


def _blocks_page_one() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "success",
            "data": {
                "has_more": True,
                "page_token": "page-2",
                "items": [
                    {"block_id": "root", "children": ["img_block", "file_block", "text_block"]},
                    {
                        "block_id": "img_block",
                        "parent_id": "root",
                        "image": {"token": "tok_img", "mime_type": "image/png"},
                    },
                    {
                        "block_id": "file_block",
                        "parent_id": "root",
                        "file": {
                            "file_token": "tok_file",
                            "mime_type": "application/pdf",
                            "name": "spec.pdf",
                        },
                    },
                    {
                        "block_id": "text_block",
                        "parent_id": "root",
                        "text": {
                            "elements": [
                                {"text_run": {"content": "正文 image.png "}},
                                {"inline_block": {"block_id": "inline_file"}},
                            ]
                        },
                    },
                    {
                        "block_id": "inline_file",
                        "file": {
                            "file_token": "tok_inline",
                            "mime_type": "application/zip",
                            "name": "inline.zip",
                        },
                    },
                ],
            },
        },
    )


def _blocks_page_two() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "success",
            "data": {
                "has_more": False,
                "items": [
                    {"block_id": "table", "children": ["cell"]},
                    {
                        "block_id": "cell",
                        "parent_id": "table",
                        "block_type": "table_cell",
                        "children": ["cell_img"],
                    },
                    {
                        "block_id": "cell_img",
                        "parent_id": "cell",
                        "image": {"token": "tok_cell", "mime_type": "image/png"},
                    },
                    {
                        "block_id": "unsupported",
                        "whiteboard": {"token": "tok_whiteboard"},
                    },
                ],
            },
        },
    )


@pytest.mark.anyio
async def test_wiki_docx_resolves_and_reads_raw_content_and_blocks(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_config(test_project_id)
    requested_paths: list[str] = []
    block_page_tokens: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        if request.url.path == "/open-apis/wiki/v2/spaces/get_node":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "success",
                    "data": {
                        "node": {
                            "obj_type": "docx",
                            "obj_token": "doccnabc123",
                            "title": "Wiki 需求文档",
                        }
                    },
                },
            )
        if request.url.path == "/open-apis/docx/v1/documents/doccnabc123/raw_content":
            return _raw_content_response()
        if request.url.path == "/open-apis/docx/v1/documents/doccnabc123/blocks":
            block_page_tokens.append(request.url.params.get("page_token"))
            if request.url.params.get("page_token") == "page-2":
                return _blocks_page_two()
            return _blocks_page_one()
        return httpx.Response(404, json={"code": 404, "msg": "not found"})

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        parsed = await read_feishu_parsed_source(
            session,
            test_project_id,
            "https://demo.feishu.cn/wiki/wikcnabc123",
        )

    assert parsed.doc_type == "docx"
    assert parsed.token == "doccnabc123"
    assert "/open-apis/wiki/v2/spaces/get_node" in requested_paths
    assert "/open-apis/docx/v1/documents/doccnabc123/raw_content" in requested_paths
    assert block_page_tokens == [None, "page-2"]
    assert {resource.source_id: resource.ref for resource in parsed.resources} == {
        "tok_img": "docx_img_001",
        "tok_file": "docx_att_001",
        "tok_inline": "docx_att_002",
        "tok_cell": "docx_img_002",
    }
    assert '<image ref="docx_img_001" position="docx:block:img_block" />' in parsed.markdown
    assert '<attachment ref="docx_att_001" position="docx:block:file_block" />' in parsed.markdown
    assert '<attachment ref="docx_att_002" position="docx:block:text_block:element:2" />' in parsed.markdown
    assert '<image ref="docx_img_002" position="docx:block:cell_img" />' in parsed.markdown
    assert "tok_whiteboard" in json.dumps(parsed.raw_manifest, ensure_ascii=False)
    assert "tok_whiteboard" not in parsed.markdown
    assert "image.png" not in {resource.filename for resource in parsed.resources}


@pytest.mark.anyio
async def test_docx_raw_content_missing_content_fails(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_config(test_project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        if request.url.path == "/open-apis/docx/v1/documents/doccnabc123/raw_content":
            return httpx.Response(200, json={"code": 0, "msg": "success", "data": {"title": "bad"}})
        return httpx.Response(404, json={"code": 404, "msg": "not found"})

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        with pytest.raises(FeishuClientError) as exc_info:
            await read_feishu_parsed_source(
                session,
                test_project_id,
                "https://demo.feishu.cn/docx/doccnabc123",
            )

    assert "docx response missing content" in str(exc_info.value)
