"""飞书数据源权限检测接口测试。"""

from __future__ import annotations

import json
import datetime
from typing import Callable
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, inspect, select

from backend.app.auth.service import create_access_token, hash_password
from backend.app.database import async_session_factory, engine
from backend.app.integrations import feishu_bot, feishu_client
from backend.app.models import (
    FeishuBotConfigRecord,
    FeishuSheetAuthorizationRecord,
    User,
    UserProjectRole,
)
from backend.app.security.crypto import encrypt_secret
from backend.app.services.feishu_sheet_authorization_service import (
    AUTHORIZATION_STATUS_AUTHORIZATION_FAILED,
    AUTHORIZATION_STATUS_AUTHORIZED,
    AUTHORIZATION_STATUS_FAILED,
    AUTHORIZATION_STATUS_PENDING,
    AUTHORIZATION_STATUS_SENT,
    get_authorization_by_state,
    get_authorization_by_source,
    get_success_authorization_by_token,
    hash_authorization_state,
    mark_authorization_failed,
    mark_authorization_success,
    upsert_authorization_record,
)
from backend.config import settings
from backend.run import app


@pytest.fixture(autouse=True)
def _clear_feishu_state() -> None:
    oauth_callback_url = settings.feishu_oauth_callback_url
    oauth_authorize_url = settings.feishu_oauth_authorize_url
    sheet_oauth_scope = settings.feishu_sheet_oauth_scope
    feishu_bot._TOKEN_CACHE.clear()
    feishu_bot._TOKEN_LOCKS.clear()
    yield
    feishu_bot._TOKEN_CACHE.clear()
    feishu_bot._TOKEN_LOCKS.clear()
    object.__setattr__(settings, "feishu_oauth_callback_url", oauth_callback_url)
    object.__setattr__(settings, "feishu_oauth_authorize_url", oauth_authorize_url)
    object.__setattr__(settings, "feishu_sheet_oauth_scope", sheet_oauth_scope)


async def _seed_feishu_bot_config(
    project_id: int,
    *,
    app_id: str = "perm_app",
    app_secret: str = "perm_secret",
    default_chat_id: str = "",
) -> None:
    async with async_session_factory() as session:
        session.add(
            FeishuBotConfigRecord(
                project_id=project_id,
                app_id=app_id,
                app_secret_cipher=encrypt_secret(app_secret) if app_secret else "",
                default_chat_id=default_chat_id,
            )
        )
        await session.commit()


async def _create_project_member_headers(project_id: int) -> dict[str, str]:
    async with async_session_factory() as session:
        user = User(
            username="member",
            hashed_password=hash_password("member-pass"),
            is_super_admin=False,
            primary_project_id=project_id,
        )
        session.add(user)
        await session.flush()
        session.add(
            UserProjectRole(
                user_id=user.id,
                project_id=project_id,
                role="user",
            )
        )
        await session.commit()
        token = create_access_token(user.id, project_id=project_id)
    return {"Authorization": f"Bearer {token}"}


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


def _token_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "ok",
            "tenant_access_token": "t_perm",
            "expire": 7200,
        },
    )


def _spreadsheet_response(title: str = "权限检测表") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "success",
            "data": {
                "spreadsheet": {
                    "token": "shtcnperm123",
                    "title": title,
                    "url": "https://demo.feishu.cn/sheets/shtcnperm123",
                    "owner_id": "ou_owner",
                }
            },
        },
    )


async def _seed_authorization_sent(
    project_id: int,
    *,
    state: str = "state-ok",
    source_id: str = "feishu_items",
    expires_delta_seconds: int = 600,
    status: str = AUTHORIZATION_STATUS_SENT,
) -> None:
    expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        seconds=expires_delta_seconds
    )
    async with async_session_factory() as session:
        await upsert_authorization_record(
            session,
            project_id=project_id,
            source_id=source_id,
            spreadsheet_token="shtcnperm123",
            sheet_url="https://demo.feishu.cn/sheets/shtcnperm123",
            sheet_title="配置校验表",
            status=status,
            chat_id="oc_default",
            message_id="om_auth_card",
            state_hash=hash_authorization_state(state),
            state_expires_at=expires_at,
        )
        await session.commit()


@pytest.mark.anyio
async def test_check_permission_requires_login() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/feishu/sources/check-permission",
            json={
                "source_id": "feishu_items",
                "sheet_url": "https://demo.feishu.cn/sheets/shtcnperm123",
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "未提供认证令牌"


@pytest.mark.anyio
async def test_check_permission_allows_project_member(
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id)
    headers = await _create_project_member_headers(test_project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            body = json.loads(request.content.decode("utf-8"))
            assert body == {"app_id": "perm_app", "app_secret": "perm_secret"}
            return _token_response()
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnperm123":
            assert request.headers["authorization"] == "Bearer t_perm"
            return _spreadsheet_response()
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    ) as client:
        response = await client.post(
            "/api/v1/feishu/sources/check-permission",
            json={
                "source_id": "feishu_items",
                "sheet_url": "https://demo.feishu.cn/sheets/shtcnperm123?sheet=gid001&unused=1",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"] == {
        "status": "authorized",
        "spreadsheet_token": "shtcnperm123",
        "sheet_url": "https://demo.feishu.cn/sheets/shtcnperm123?sheet=gid001",
        "title": "权限检测表",
    }

    async with async_session_factory() as session:
        result = await session.execute(select(FeishuSheetAuthorizationRecord))
        records = result.scalars().all()
    assert len(records) == 1
    assert records[0].source_id == "feishu_items"
    assert records[0].spreadsheet_token == "shtcnperm123"
    assert records[0].status == "authorized"
    assert records[0].sheet_title == "权限检测表"


@pytest.mark.anyio
async def test_check_permission_returns_bot_not_configured(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/feishu/sources/check-permission",
        json={
            "source_id": "feishu_items",
            "sheet_url": "https://demo.feishu.cn/sheets/shtcnperm123",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "bot_not_configured",
        "message": "当前项目尚未配置飞书机器人应用。",
    }


@pytest.mark.anyio
async def test_check_permission_returns_invalid_url(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    await _seed_feishu_bot_config(test_project_id)

    response = await auth_client.post(
        "/api/v1/feishu/sources/check-permission",
        json={
            "source_id": "feishu_items",
            "sheet_url": "not-a-url",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "invalid_url",
        "message": "请输入合法的飞书电子表格链接",
    }


@pytest.mark.anyio
async def test_check_permission_reuses_authorized_record_without_calling_feishu(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id)
    async with async_session_factory() as session:
        session.add(
            FeishuSheetAuthorizationRecord(
                project_id=test_project_id,
                source_id="old_source",
                spreadsheet_token="shtcnperm123",
                sheet_url="https://demo.feishu.cn/sheets/shtcnperm123",
                sheet_title="已有授权表",
                status="authorized",
            )
        )
        await session.commit()

    def _fail_factory(timeout: float = 10.0) -> httpx.AsyncClient:
        raise AssertionError("复用授权记录时不应调用飞书 OpenAPI")

    monkeypatch.setattr(feishu_bot, "_create_async_client", _fail_factory)
    monkeypatch.setattr(feishu_client, "_create_async_client", _fail_factory)

    response = await auth_client.post(
        "/api/v1/feishu/sources/check-permission",
        json={
            "source_id": "new_source",
            "sheet_url": "https://demo.feishu.cn/sheets/shtcnperm123?sheet=gid002",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "authorized",
        "spreadsheet_token": "shtcnperm123",
        "sheet_url": "https://demo.feishu.cn/sheets/shtcnperm123",
        "title": "已有授权表",
        "reused_authorization": True,
    }


@pytest.mark.anyio
async def test_authorization_table_allows_multiple_source_ids_for_same_token(
    test_project_id: int,
) -> None:
    async with async_session_factory() as session:
        session.add_all(
            [
                FeishuSheetAuthorizationRecord(
                    project_id=test_project_id,
                    source_id="source_a",
                    spreadsheet_token="shtcnperm123",
                    sheet_url="https://demo.feishu.cn/sheets/shtcnperm123",
                    sheet_title="共享表",
                    status="authorized",
                ),
                FeishuSheetAuthorizationRecord(
                    project_id=test_project_id,
                    source_id="source_b",
                    spreadsheet_token="shtcnperm123",
                    sheet_url="https://demo.feishu.cn/sheets/shtcnperm123",
                    sheet_title="共享表",
                    status="authorized",
                ),
            ]
        )
        await session.commit()
        count_result = await session.execute(
            select(func.count()).select_from(FeishuSheetAuthorizationRecord)
        )

    assert count_result.scalar_one() == 2


@pytest.mark.anyio
async def test_authorization_table_schema_matches_required_indexes() -> None:
    """授权记录表应包含指定字段与索引，且不限制 project_id + token 唯一。"""

    def _inspect_schema(sync_conn) -> dict[str, object]:
        inspector = inspect(sync_conn)
        columns = {column["name"] for column in inspector.get_columns("feishu_sheet_authorizations")}
        indexes = inspector.get_indexes("feishu_sheet_authorizations")
        unique_constraints = inspector.get_unique_constraints("feishu_sheet_authorizations")
        return {
            "columns": columns,
            "indexes": indexes,
            "unique_constraints": unique_constraints,
        }

    async with engine.begin() as conn:
        schema = await conn.run_sync(_inspect_schema)

    assert schema["columns"] == {
        "id",
        "project_id",
        "source_id",
        "spreadsheet_token",
        "sheet_url",
        "sheet_title",
        "authorized_by_open_id",
        "bot_open_id",
        "chat_id",
        "message_id",
        "status",
        "error_message",
        "state_hash",
        "state_expires_at",
        "authorized_at",
        "created_at",
        "updated_at",
    }
    index_columns = {tuple(index["column_names"]) for index in schema["indexes"]}
    assert ("project_id", "spreadsheet_token") in index_columns
    assert ("spreadsheet_token",) in index_columns
    assert ("status",) in index_columns
    unique_columns = {
        tuple(constraint["column_names"])
        for constraint in schema["unique_constraints"]
    }
    assert ("project_id", "source_id") in unique_columns
    assert ("project_id", "spreadsheet_token") not in unique_columns


@pytest.mark.anyio
async def test_authorization_service_upsert_and_query_helpers(
    test_project_id: int,
) -> None:
    async with async_session_factory() as session:
        record = await upsert_authorization_record(
            session,
            project_id=test_project_id,
            source_id="source_a",
            spreadsheet_token="token_a",
            sheet_url="https://demo.feishu.cn/sheets/token_a",
            sheet_title="初始标题",
            status=AUTHORIZATION_STATUS_PENDING,
            state_hash="state-1",
        )
        await session.commit()
        record_id = record.id

        updated = await upsert_authorization_record(
            session,
            project_id=test_project_id,
            source_id="source_a",
            spreadsheet_token="token_b",
            sheet_url="https://demo.feishu.cn/sheets/token_b",
            sheet_title="更新标题",
            status=AUTHORIZATION_STATUS_PENDING,
            state_hash="state-2",
        )
        await session.commit()

        assert updated.id == record_id
        assert updated.spreadsheet_token == "token_b"
        assert updated.sheet_title == "更新标题"
        assert updated.state_hash == "state-2"

        by_source = await get_authorization_by_source(
            session,
            test_project_id,
            "source_a",
        )
        assert by_source is not None
        assert by_source.id == record_id
        assert (
            await get_success_authorization_by_token(
                session,
                test_project_id,
                "token_b",
            )
        ) is None

        success = await mark_authorization_success(
            session,
            by_source,
            authorized_by_open_id="ou_user",
            bot_open_id="ou_bot",
            chat_id="oc_chat",
            message_id="om_msg",
            sheet_title="授权成功标题",
        )
        await session.commit()

        assert success.status == AUTHORIZATION_STATUS_AUTHORIZED
        assert success.error_message == ""
        assert success.authorized_at is not None
        assert success.authorized_by_open_id == "ou_user"
        assert success.bot_open_id == "ou_bot"
        assert success.chat_id == "oc_chat"
        assert success.message_id == "om_msg"
        assert success.sheet_title == "授权成功标题"

        by_token = await get_success_authorization_by_token(
            session,
            test_project_id,
            "token_b",
        )
        assert by_token is not None
        assert by_token.id == record_id

        failed = await mark_authorization_failed(
            session,
            record_id,
            error_message="机器人暂无权限",
        )
        await session.commit()

    assert failed.status == AUTHORIZATION_STATUS_FAILED
    assert failed.error_message == "机器人暂无权限"


@pytest.mark.anyio
async def test_send_authorization_card_returns_callback_not_configured(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id, default_chat_id="oc_default")
    object.__setattr__(settings, "feishu_oauth_callback_url", "")

    response = await auth_client.post(
        "/api/v1/feishu/sources/send-authorization-card",
        json={
            "source_id": "feishu_items",
            "sheet_url": "https://demo.feishu.cn/sheets/shtcnperm123",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "callback_not_configured",
        "message": "当前服务尚未配置飞书 OAuth callback 地址。",
    }


@pytest.mark.anyio
async def test_send_authorization_card_returns_bot_not_configured_without_chat(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id, default_chat_id="")
    object.__setattr__(
        settings,
        "feishu_oauth_callback_url",
        "https://example.com/api/v1/feishu/oauth/callback",
    )

    response = await auth_client.post(
        "/api/v1/feishu/sources/send-authorization-card",
        json={
            "source_id": "feishu_items",
            "sheet_url": "https://demo.feishu.cn/sheets/shtcnperm123",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "bot_not_configured",
        "message": "当前项目尚未完整配置飞书机器人应用、密钥或默认群。",
    }


@pytest.mark.anyio
async def test_send_authorization_card_returns_invalid_url(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id, default_chat_id="oc_default")
    object.__setattr__(
        settings,
        "feishu_oauth_callback_url",
        "https://example.com/api/v1/feishu/oauth/callback",
    )

    response = await auth_client.post(
        "/api/v1/feishu/sources/send-authorization-card",
        json={
            "source_id": "feishu_items",
            "sheet_url": "not-a-url",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "invalid_url",
        "message": "请输入合法的飞书电子表格链接",
    }


@pytest.mark.anyio
async def test_send_authorization_card_sends_card_and_persists_state_hash(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id, default_chat_id="oc_default")
    object.__setattr__(
        settings,
        "feishu_oauth_callback_url",
        "https://example.com/api/v1/feishu/oauth/callback",
    )
    object.__setattr__(
        settings,
        "feishu_oauth_authorize_url",
        "https://accounts.feishu.cn/open-apis/authen/v1/authorize",
    )
    object.__setattr__(
        settings,
        "feishu_sheet_oauth_scope",
        "sheets:spreadsheet:readonly wiki:node:read",
    )
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnperm123":
            return _spreadsheet_response("配置校验表")
        return httpx.Response(404)

    async def _fake_send_card(*, db, project_id, chat_id, card):  # noqa: ANN001
        captured["project_id"] = project_id
        captured["chat_id"] = chat_id
        captured["card"] = card
        return {"message_id": "om_auth_card", "raw": {}}

    _install_mock_transport(monkeypatch, handler)
    monkeypatch.setattr("backend.app.api.feishu_api.send_card_to_chat", _fake_send_card)

    response = await auth_client.post(
        "/api/v1/feishu/sources/send-authorization-card",
        json={
            "source_id": "feishu_items",
            "sheet_url": "https://demo.feishu.cn/sheets/shtcnperm123?sheet=gid001&unused=1",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == AUTHORIZATION_STATUS_SENT
    assert payload["chat_id"] == "oc_default"
    assert payload["message_id"] == "om_auth_card"
    assert payload["expires_at"].endswith("Z")

    assert captured["project_id"] == test_project_id
    assert captured["chat_id"] == "oc_default"
    card = captured["card"]
    assert card["header"]["title"]["content"] == "飞书表格读取授权请求"
    card_text = card["elements"][0]["text"]["content"]
    assert "**项目：** test-project" in card_text
    assert "**数据源：** feishu_items" in card_text
    assert "**表格：** 配置校验表" in card_text
    assert "仅申请 view 只读权限，不会修改表格内容" in card_text
    button_url = card["elements"][1]["actions"][0]["url"]
    parsed_url = urlparse(button_url)
    query = parse_qs(parsed_url.query)
    assert parsed_url.geturl().startswith(
        "https://accounts.feishu.cn/open-apis/authen/v1/authorize?"
    )
    assert query["client_id"] == ["perm_app"]
    assert query["redirect_uri"] == ["https://example.com/api/v1/feishu/oauth/callback"]
    assert query["scope"] == ["sheets:spreadsheet:readonly wiki:node:read"]
    state = query["state"][0]
    assert len(state) > 20

    async with async_session_factory() as session:
        record = await get_authorization_by_source(
            session,
            test_project_id,
            "feishu_items",
        )
    assert record is not None
    assert record.status == AUTHORIZATION_STATUS_SENT
    assert record.chat_id == "oc_default"
    assert record.message_id == "om_auth_card"
    assert record.state_expires_at is not None
    assert record.sheet_url == "https://demo.feishu.cn/sheets/shtcnperm123?sheet=gid001"
    assert record.sheet_title == "配置校验表"
    assert record.state_hash == hash_authorization_state(state)
    assert record.state_hash != state


@pytest.mark.anyio
async def test_check_permission_returns_authorization_sent_by_source_without_calling_feishu(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id)
    await _seed_authorization_sent(test_project_id, state="state-waiting")

    def _fail_factory(timeout: float = 10.0) -> httpx.AsyncClient:
        raise AssertionError("已有 source 授权中记录时不应调用飞书 OpenAPI")

    monkeypatch.setattr(feishu_bot, "_create_async_client", _fail_factory)
    monkeypatch.setattr(feishu_client, "_create_async_client", _fail_factory)

    response = await auth_client.post(
        "/api/v1/feishu/sources/check-permission",
        json={
            "source_id": "feishu_items",
            "sheet_url": "https://demo.feishu.cn/wiki/wikcnabc123",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == AUTHORIZATION_STATUS_SENT
    assert payload["message"] == "授权请求已发送到群，等待有权限的成员完成授权。"
    assert payload["message_id"] == "om_auth_card"


@pytest.mark.anyio
async def test_check_permission_returns_authorized_by_source_with_real_sheet_url(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id)
    async with async_session_factory() as session:
        session.add(
            FeishuSheetAuthorizationRecord(
                project_id=test_project_id,
                source_id="feishu_items",
                spreadsheet_token="shtcnreal456",
                sheet_url="https://demo.feishu.cn/sheets/shtcnreal456",
                sheet_title="真实表格",
                status=AUTHORIZATION_STATUS_AUTHORIZED,
            )
        )
        await session.commit()

    def _fail_factory(timeout: float = 10.0) -> httpx.AsyncClient:
        raise AssertionError("已有 source 授权成功记录时不应调用飞书 OpenAPI")

    monkeypatch.setattr(feishu_bot, "_create_async_client", _fail_factory)
    monkeypatch.setattr(feishu_client, "_create_async_client", _fail_factory)

    response = await auth_client.post(
        "/api/v1/feishu/sources/check-permission",
        json={
            "source_id": "feishu_items",
            "sheet_url": "https://demo.feishu.cn/wiki/wikcnabc123",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "authorized",
        "spreadsheet_token": "shtcnreal456",
        "sheet_url": "https://demo.feishu.cn/sheets/shtcnreal456",
        "title": "真实表格",
        "reused_authorization": True,
    }


@pytest.mark.anyio
async def test_send_authorization_card_continues_when_metadata_permission_denied(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id, default_chat_id="oc_default")
    object.__setattr__(
        settings,
        "feishu_oauth_callback_url",
        "https://example.com/api/v1/feishu/oauth/callback",
    )
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnperm123":
            return httpx.Response(403, json={"code": 1254030, "msg": "permission denied"})
        return httpx.Response(404)

    async def _fake_send_card(*, db, project_id, chat_id, card):  # noqa: ANN001
        captured["card"] = card
        return {"message_id": "om_auth_card", "raw": {}}

    _install_mock_transport(monkeypatch, handler)
    monkeypatch.setattr("backend.app.api.feishu_api.send_card_to_chat", _fake_send_card)

    response = await auth_client.post(
        "/api/v1/feishu/sources/send-authorization-card",
        json={
            "source_id": "feishu_items",
            "sheet_url": "https://demo.feishu.cn/sheets/shtcnperm123?sheet=gid001&unused=1",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == AUTHORIZATION_STATUS_SENT
    card_text = captured["card"]["elements"][0]["text"]["content"]
    assert "**表格：** https://demo.feishu.cn/sheets/shtcnperm123?sheet=gid001" in card_text


@pytest.mark.anyio
async def test_send_authorization_card_returns_send_failed_without_leaking_state(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id, default_chat_id="oc_default")
    object.__setattr__(
        settings,
        "feishu_oauth_callback_url",
        "https://example.com/api/v1/feishu/oauth/callback",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnperm123":
            return _spreadsheet_response("配置校验表")
        return httpx.Response(404)

    async def _explode_send_card(*, db, project_id, chat_id, card):  # noqa: ANN001
        raise feishu_bot.FeishuApiError("飞书 API 网络异常：请求超时")

    _install_mock_transport(monkeypatch, handler)
    monkeypatch.setattr("backend.app.api.feishu_api.send_card_to_chat", _explode_send_card)

    response = await auth_client.post(
        "/api/v1/feishu/sources/send-authorization-card",
        json={
            "source_id": "feishu_items",
            "sheet_url": "https://demo.feishu.cn/sheets/shtcnperm123",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload == {
        "status": "send_failed",
        "message": "飞书 API 网络异常：请求超时",
    }
    assert "state" not in json.dumps(payload, ensure_ascii=False).lower()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("query", "seed_kwargs", "expected_text"),
    [
        (
            {},
            None,
            "授权失败：授权请求缺少 state，请重新发送授权请求。",
        ),
        (
            {"state": "missing-state", "code": "oauth-code"},
            None,
            "授权失败：授权请求不存在或已被使用，请重新发送授权请求。",
        ),
        (
            {"state": "state-expired", "code": "oauth-code"},
            {"state": "state-expired", "expires_delta_seconds": -1},
            "授权失败：授权请求已过期，请重新发送授权请求。",
        ),
        (
            {"state": "state-pending", "code": "oauth-code"},
            {"state": "state-pending", "status": AUTHORIZATION_STATUS_PENDING},
            "授权失败：该授权请求已被使用或状态不可用，请重新发送授权请求。",
        ),
    ],
)
async def test_oauth_callback_rejects_invalid_state(
    test_project_id: int,
    query: dict[str, str],
    seed_kwargs: dict[str, object] | None,
    expected_text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id, default_chat_id="oc_default")
    if seed_kwargs is not None:
        await _seed_authorization_sent(test_project_id, **seed_kwargs)
    notices: list[str] = []

    async def _fake_send_text(*, db, project_id, chat_id, text):  # noqa: ANN001
        notices.append(text)
        return {"message_id": "om_notice", "raw": {}}

    monkeypatch.setattr("backend.app.api.feishu_api.send_text_to_chat", _fake_send_text)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/feishu/sources/oauth/callback",
            params=query,
        )

    assert response.status_code == 200
    assert expected_text in response.text
    if seed_kwargs is not None:
        async with async_session_factory() as session:
            record = await get_authorization_by_source(
                session,
                test_project_id,
                "feishu_items",
            )
        assert record is not None
        assert record.status == AUTHORIZATION_STATUS_AUTHORIZATION_FAILED
        assert record.state_hash == ""
        assert record.state_expires_at is None
        assert notices == [expected_text]


@pytest.mark.anyio
async def test_oauth_callback_adds_sheet_viewer_and_marks_authorized(
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id, default_chat_id="oc_default")
    await _seed_authorization_sent(test_project_id, state="state-ok")
    object.__setattr__(
        settings,
        "feishu_oauth_callback_url",
        "https://example.com/api/v1/feishu/sources/oauth/callback",
    )
    captured: dict[str, object] = {"paths": [], "notices": []}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["paths"].append(request.url.path)
        if request.url.path == "/open-apis/authen/v2/oauth/token":
            body = json.loads(request.content.decode("utf-8"))
            assert body == {
                "grant_type": "authorization_code",
                "client_id": "perm_app",
                "client_secret": "perm_secret",
                "code": "oauth-code",
                "redirect_uri": "https://example.com/api/v1/feishu/sources/oauth/callback",
            }
            return httpx.Response(200, json={"access_token": "u_perm"})
        if request.url.path == "/open-apis/authen/v1/user_info":
            assert request.headers["authorization"] == "Bearer u_perm"
            return httpx.Response(200, json={"code": 0, "data": {"open_id": "ou_user"}})
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        if request.url.path == "/open-apis/bot/v3/info":
            assert request.headers["authorization"] == "Bearer t_perm"
            return httpx.Response(
                200,
                json={"code": 0, "data": {"bot": {"open_id": "ou_bot"}}},
            )
        if request.url.path == "/open-apis/drive/v1/permissions/shtcnperm123/members":
            assert request.url.params["type"] == "sheet"
            assert request.headers["authorization"] == "Bearer u_perm"
            body = json.loads(request.content.decode("utf-8"))
            assert body == {
                "member_type": "openid",
                "member_id": "ou_bot",
                "perm": "view",
            }
            return httpx.Response(200, json={"code": 0, "data": {}})
        return httpx.Response(404)

    async def _fake_send_text(*, db, project_id, chat_id, text):  # noqa: ANN001
        captured["notices"].append(
            {"project_id": project_id, "chat_id": chat_id, "text": text}
        )
        return {"message_id": "om_notice", "raw": {}}

    _install_mock_transport(monkeypatch, handler)
    monkeypatch.setattr("backend.app.api.feishu_api.send_text_to_chat", _fake_send_text)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/feishu/sources/oauth/callback",
            params={"code": "oauth-code", "state": "state-ok"},
        )
        second_response = await client.get(
            "/api/v1/feishu/sources/oauth/callback",
            params={"code": "oauth-code", "state": "state-ok"},
        )

    assert response.status_code == 200
    assert "飞书表格授权成功，机器人现在可以读取该配置表。" in response.text
    assert second_response.status_code == 200
    assert "授权请求不存在或已被使用" in second_response.text
    assert "/open-apis/drive/v1/permissions/shtcnperm123/members" in captured["paths"]
    assert captured["notices"] == [
        {
            "project_id": test_project_id,
            "chat_id": "oc_default",
            "text": "飞书表格授权成功，机器人现在可以读取该配置表。",
        }
    ]

    async with async_session_factory() as session:
        record = await get_authorization_by_source(
            session,
            test_project_id,
            "feishu_items",
        )
        by_state = await get_authorization_by_state(session, "state-ok")
    assert record is not None
    assert record.status == AUTHORIZATION_STATUS_AUTHORIZED
    assert record.authorized_by_open_id == "ou_user"
    assert record.bot_open_id == "ou_bot"
    assert record.authorized_at is not None
    assert record.state_hash == ""
    assert record.state_expires_at is None
    assert by_state is None


@pytest.mark.anyio
async def test_oauth_callback_missing_code_marks_authorization_failed(
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id, default_chat_id="oc_default")
    await _seed_authorization_sent(test_project_id, state="state-missing-code")
    notices: list[str] = []

    async def _fake_send_text(*, db, project_id, chat_id, text):  # noqa: ANN001
        notices.append(text)
        return {"message_id": "om_notice", "raw": {}}

    monkeypatch.setattr("backend.app.api.feishu_api.send_text_to_chat", _fake_send_text)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/feishu/sources/oauth/callback",
            params={"state": "state-missing-code"},
        )

    message = "授权失败：飞书 OAuth 回调缺少授权码，请重新发送授权请求。"
    assert response.status_code == 200
    assert message in response.text
    assert notices == [message]
    async with async_session_factory() as session:
        record = await get_authorization_by_source(
            session,
            test_project_id,
            "feishu_items",
        )
    assert record is not None
    assert record.status == AUTHORIZATION_STATUS_AUTHORIZATION_FAILED
    assert record.error_message == message
    assert record.state_hash == ""
    assert record.state_expires_at is None


@pytest.mark.anyio
async def test_oauth_callback_drive_permission_denied_uses_fixed_chinese_error(
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id, default_chat_id="oc_default")
    await _seed_authorization_sent(test_project_id, state="state-denied")
    object.__setattr__(
        settings,
        "feishu_oauth_callback_url",
        "https://example.com/api/v1/feishu/sources/oauth/callback",
    )
    notices: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/open-apis/authen/v2/oauth/token":
            return httpx.Response(200, json={"access_token": "u_perm"})
        if request.url.path == "/open-apis/authen/v1/user_info":
            return httpx.Response(200, json={"code": 0, "data": {"open_id": "ou_user"}})
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        if request.url.path == "/open-apis/bot/v3/info":
            return httpx.Response(
                200,
                json={"code": 0, "data": {"open_id": "ou_bot"}},
            )
        if request.url.path == "/open-apis/drive/v1/permissions/shtcnperm123/members":
            return httpx.Response(403, json={"code": 1254030, "msg": "permission denied"})
        return httpx.Response(404)

    async def _fake_send_text(*, db, project_id, chat_id, text):  # noqa: ANN001
        notices.append(text)
        return {"message_id": "om_notice", "raw": {}}

    _install_mock_transport(monkeypatch, handler)
    monkeypatch.setattr("backend.app.api.feishu_api.send_text_to_chat", _fake_send_text)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/feishu/sources/oauth/callback",
            params={"code": "oauth-code", "state": "state-denied"},
        )

    message = "授权失败：当前用户没有该表格的分享权限，请文档所有者或可管理协作者操作。"
    assert response.status_code == 200
    assert message in response.text
    assert notices == [message]
    async with async_session_factory() as session:
        record = await get_authorization_by_source(
            session,
            test_project_id,
            "feishu_items",
        )
    assert record is not None
    assert record.status == AUTHORIZATION_STATUS_AUTHORIZATION_FAILED
    assert record.error_message == message
    assert record.state_hash == ""
    assert record.state_expires_at is None


@pytest.mark.anyio
async def test_oauth_callback_token_error_does_not_leak_code_or_state(
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_feishu_bot_config(test_project_id, default_chat_id="oc_default")
    await _seed_authorization_sent(test_project_id, state="state-token-fail")
    object.__setattr__(
        settings,
        "feishu_oauth_callback_url",
        "https://example.com/api/v1/feishu/sources/oauth/callback",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/open-apis/authen/v2/oauth/token":
            return httpx.Response(
                400,
                json={
                    "error": "invalid_grant",
                    "error_description": "oauth code expired",
                },
            )
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/feishu/sources/oauth/callback",
            params={"code": "sensitive-code", "state": "state-token-fail"},
        )

    assert response.status_code == 200
    assert "授权失败：" in response.text
    assert "sensitive-code" not in response.text
    assert "state-token-fail" not in response.text
    async with async_session_factory() as session:
        record = await get_authorization_by_source(
            session,
            test_project_id,
            "feishu_items",
        )
    assert record is not None
    assert record.status == AUTHORIZATION_STATUS_AUTHORIZATION_FAILED
    assert "sensitive-code" not in record.error_message
    assert "state-token-fail" not in record.error_message
    assert record.state_hash == ""


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("api_response", "expected_data"),
    [
        (
            httpx.Response(403, json={"code": 1254030, "msg": "permission denied"}),
            {
                "status": "pending_authorization",
                "error_status": "document_permission_denied",
                "message": "文档权限不足，请发送授权请求到群。",
            },
        ),
        (
            httpx.Response(404, json={"code": 1254040, "msg": "not found"}),
            {
                "status": "not_found",
                "message": "飞书电子表格或工作表不存在：not found",
            },
        ),
        (
            httpx.Response(401, json={"code": 99991663, "msg": "invalid app"}),
            {
                "status": "app_permission_missing",
                "message": "飞书应用权限不足：invalid app",
            },
        ),
    ],
)
async def test_check_permission_maps_feishu_errors_to_business_status(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
    api_response: httpx.Response,
    expected_data: dict[str, str],
) -> None:
    await _seed_feishu_bot_config(test_project_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == feishu_bot.TENANT_ACCESS_TOKEN_PATH:
            return _token_response()
        if request.url.path == "/open-apis/sheets/v3/spreadsheets/shtcnperm123":
            return api_response
        return httpx.Response(404)

    _install_mock_transport(monkeypatch, handler)

    response = await auth_client.post(
        "/api/v1/feishu/sources/check-permission",
        json={
            "source_id": "feishu_items",
            "sheet_url": "https://demo.feishu.cn/sheets/shtcnperm123",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == expected_data
