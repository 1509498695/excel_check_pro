"""飞书 OpenAPI 客户端单元测试：使用 httpx.MockTransport 注入假后端。"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

import httpx
import pytest

from backend.app.database import async_session_factory
from backend.app.integrations import feishu_bot
from backend.app.integrations.feishu_bot import (
    FeishuApiError,
    get_tenant_access_token,
    invalidate_token_cache,
    send_card_to_chat,
    send_file_to_chat,
    send_text_to_chat,
)
from backend.app.models import FeishuBotConfigRecord
from backend.app.security.crypto import encrypt_secret


@pytest.fixture(autouse=True)
def _clear_feishu_state() -> None:
    """每个用例都从干净的内存缓存开始，避免上一个用例污染。"""
    feishu_bot._TOKEN_CACHE.clear()
    feishu_bot._TOKEN_LOCKS.clear()
    yield
    feishu_bot._TOKEN_CACHE.clear()
    feishu_bot._TOKEN_LOCKS.clear()


async def _seed_feishu_config(project_id: int) -> None:
    """直接在数据库中写入一条飞书机器人配置，便于客户端读取。"""
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
    """把 _create_async_client 替换成走 MockTransport 的版本。"""
    transport = httpx.MockTransport(handler)

    def _factory(timeout: float = 10.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=transport,
            base_url=feishu_bot.FEISHU_OPEN_BASE_URL,
            timeout=timeout,
        )

    monkeypatch.setattr(feishu_bot, "_create_async_client", _factory)


@pytest.mark.anyio
async def test_get_tenant_access_token_first_fetch_caches_value(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首次取值应当命中 token 接口，并把结果写入内存缓存。"""
    await _seed_feishu_config(test_project_id)
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "ok",
                    "tenant_access_token": "t_first",
                    "expire": 7200,
                },
            )
        return httpx.Response(404, json={"code": -1, "msg": "not found"})

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        token = await get_tenant_access_token(session, test_project_id)

    assert token == "t_first"
    assert test_project_id in feishu_bot._TOKEN_CACHE
    assert feishu_bot._TOKEN_CACHE[test_project_id][0] == "t_first"
    assert len(captured) == 1
    body = json.loads(captured[0].content.decode("utf-8"))
    assert body == {"app_id": "cli_unit", "app_secret": "secret_unit"}


@pytest.mark.anyio
async def test_get_tenant_access_token_cache_hit_skips_network(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """连续两次调用应当只命中一次 token 接口。"""
    await _seed_feishu_config(test_project_id)
    call_count = {"value": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["value"] += 1
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "ok",
                "tenant_access_token": "t_cache",
                "expire": 7200,
            },
        )

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        first = await get_tenant_access_token(session, test_project_id)
        second = await get_tenant_access_token(session, test_project_id)

    assert first == "t_cache"
    assert second == "t_cache"
    assert call_count["value"] == 1


@pytest.mark.anyio
async def test_get_tenant_access_token_refetches_after_invalidation(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缓存被外部失效或剩余时间不足 2 分钟时应重新拉取 token。"""
    await _seed_feishu_config(test_project_id)
    tokens = iter(["t_v1", "t_v2"])
    call_count = {"value": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["value"] += 1
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "ok",
                "tenant_access_token": next(tokens),
                "expire": 7200,
            },
        )

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        first = await get_tenant_access_token(session, test_project_id)
        # 模拟「剩余有效期不足 2 分钟」
        feishu_bot._TOKEN_CACHE[test_project_id] = (first, time.monotonic() + 30)
        second = await get_tenant_access_token(session, test_project_id)
        invalidate_token_cache(test_project_id)
        assert test_project_id not in feishu_bot._TOKEN_CACHE

    assert first == "t_v1"
    assert second == "t_v2"
    assert call_count["value"] == 2


@pytest.mark.anyio
async def test_get_tenant_access_token_raises_on_4xx(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """token 接口返回 4xx 时应抛 FeishuApiError 并附带状态码。"""
    await _seed_feishu_config(test_project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": 99991663, "msg": "auth failed"})

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        with pytest.raises(FeishuApiError) as exc_info:
            await get_tenant_access_token(session, test_project_id)

    assert "HTTP 401" in str(exc_info.value)
    assert test_project_id not in feishu_bot._TOKEN_CACHE


@pytest.mark.anyio
async def test_get_tenant_access_token_raises_on_business_error(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """飞书业务错误（code != 0）应翻译为可读 message。"""
    await _seed_feishu_config(test_project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 10003, "msg": "invalid app_secret"},
        )

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        with pytest.raises(FeishuApiError) as exc_info:
            await get_tenant_access_token(session, test_project_id)

    message = str(exc_info.value)
    assert "code=10003" in message
    assert "invalid app_secret" in message


@pytest.mark.anyio
async def test_send_text_to_chat_builds_expected_payload(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """文本消息应以 receive_id_type=chat_id + msg_type=text 提交，并带 Bearer Token。"""
    await _seed_feishu_config(test_project_id)
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "ok",
                    "tenant_access_token": "t_send",
                    "expire": 7200,
                },
            )
        if request.url.path == feishu_bot.SEND_MESSAGE_PATH:
            captured["url"] = str(request.url)
            captured["headers"] = dict(request.headers)
            captured["body"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "ok",
                    "data": {"message_id": "om_demo_text"},
                },
            )
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        result = await send_text_to_chat(
            db=session,
            project_id=test_project_id,
            chat_id="oc_unit_chat",
            text="你好，飞书",
        )

    assert result["message_id"] == "om_demo_text"
    assert "receive_id_type=chat_id" in captured["url"]
    assert captured["headers"].get("authorization") == "Bearer t_send"
    assert captured["body"]["receive_id"] == "oc_unit_chat"
    assert captured["body"]["msg_type"] == "text"
    content = json.loads(captured["body"]["content"])
    assert content == {"text": "你好，飞书"}


@pytest.mark.anyio
async def test_send_card_to_chat_serializes_card_dict(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """卡片消息应使用 msg_type=interactive，并将原始字典 JSON 编码到 content。"""
    await _seed_feishu_config(test_project_id)
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "ok",
                    "tenant_access_token": "t_card",
                    "expire": 7200,
                },
            )
        if request.url.path == feishu_bot.SEND_MESSAGE_PATH:
            captured["body"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "ok",
                    "data": {"message_id": "om_demo_card"},
                },
            )
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    card = {
        "header": {"title": {"tag": "plain_text", "content": "测试消息"}},
        "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": "hi"}}],
    }
    async with async_session_factory() as session:
        result = await send_card_to_chat(
            db=session,
            project_id=test_project_id,
            chat_id="oc_card_chat",
            card=card,
        )

    assert result["message_id"] == "om_demo_card"
    assert captured["body"]["msg_type"] == "interactive"
    content = json.loads(captured["body"]["content"])
    assert content == card


@pytest.mark.anyio
async def test_send_file_to_chat_uploads_file_then_sends_file_message(
    test_db,
    test_project_id: int,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """文件消息应先上传拿 file_key，再用 msg_type=file 发送到原群。"""
    await _seed_feishu_config(test_project_id)
    file_path = tmp_path / "config.xlsx"
    file_path.write_bytes(b"excel-bytes")
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "ok",
                    "tenant_access_token": "t_file",
                    "expire": 7200,
                },
            )
        if request.url.path == feishu_bot.UPLOAD_FILE_PATH:
            captured["upload_headers"] = dict(request.headers)
            captured["upload_body"] = request.content
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "ok",
                    "data": {"file_key": "file_key_unit"},
                },
            )
        if request.url.path == feishu_bot.SEND_MESSAGE_PATH:
            captured["send_url"] = str(request.url)
            captured["send_headers"] = dict(request.headers)
            captured["send_body"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "ok",
                    "data": {"message_id": "om_file"},
                },
            )
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        result = await send_file_to_chat(
            db=session,
            project_id=test_project_id,
            chat_id="oc_file_chat",
            file_path=file_path,
        )

    assert result["message_id"] == "om_file"
    assert result["file_key"] == "file_key_unit"
    assert captured["upload_headers"].get("authorization") == "Bearer t_file"
    assert b'name="file_type"' in captured["upload_body"]
    assert b"xls" in captured["upload_body"]
    assert b"config.xlsx" in captured["upload_body"]
    assert b"excel-bytes" in captured["upload_body"]
    assert "receive_id_type=chat_id" in captured["send_url"]
    assert captured["send_headers"].get("authorization") == "Bearer t_file"
    assert captured["send_body"]["receive_id"] == "oc_file_chat"
    assert captured["send_body"]["msg_type"] == "file"
    assert json.loads(captured["send_body"]["content"]) == {
        "file_key": "file_key_unit"
    }


@pytest.mark.anyio
async def test_send_text_to_chat_raises_when_project_unconfigured(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """项目未配置飞书机器人时应直接抛 FeishuApiError，不发出网络请求。"""
    network_calls = {"value": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        network_calls["value"] += 1
        return httpx.Response(200, json={"code": 0, "msg": "ok"})

    _install_mock_transport(monkeypatch, handler)

    async with async_session_factory() as session:
        with pytest.raises(FeishuApiError) as exc_info:
            await send_text_to_chat(
                db=session,
                project_id=test_project_id,
                chat_id="oc_xxx",
                text="hi",
            )

    assert "未配置" in str(exc_info.value)
    assert network_calls["value"] == 0
