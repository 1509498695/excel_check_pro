"""飞书长连接 supervisor 与事件分发的单元测试。

策略
----

- 用 ``FakeWsClient`` / ``FakeEventHandlerBuilder`` 把 lark-oapi 的 WebSocket
  入口完全替换掉，避免真打飞书；FakeWsClient 暴露 ``started`` / ``stopped``
  与 ``inject_event`` 三个测试钩子。
- 用 ``stub_send_text`` / ``stub_send_card`` 替换底层 OpenAPI 调用，记录
  调用次数与入参，verify dispatch_message_event 链路。
- ``stub_execute_fixed_rules_for_project`` 替换真实校验执行，避免触达
  数据源 / 文件 IO，并支持注入异常分支。
- 每个测试都通过 ``test_db`` 创建干净表结构；supervisor 用例通过
  ``async_session_factory`` 注入会话，与生产路径一致。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.app.database import async_session_factory
from backend.app.integrations import feishu_long_conn
from backend.app.integrations.feishu_bot import FeishuApiError
from backend.app.integrations.feishu_download import QueryListingGroup
from backend.app.integrations.feishu_long_conn import (
    FeishuLongConnSupervisor,
    _CARD_PREVIEW_LIMIT,
    _DOWNLOAD_STARTED_REPLY,
    _DOWNLOAD_USAGE_REPLY,
    _FORBIDDEN_REPLY,
    _QUERY_STARTED_REPLY,
    _STARTED_REPLY,
    build_project_check_card,
    dispatch_message_event,
    matches_project_check_command,
    parse_allowed_open_ids,
    translate_execution_error,
)
from backend.app.models import FeishuBotConfigRecord, Project
from backend.app.security.crypto import encrypt_secret


# --------------------------------------------------------------------------- #
# 假 SDK：Client + EventDispatcherHandler
# --------------------------------------------------------------------------- #


class FakeEventHandler:
    """记录已注册的事件回调；inject_event 通过它把事件转给 supervisor handler。"""

    def __init__(self) -> None:
        self._callbacks: dict[str, Callable[[Any], None]] = {}

    def _register(self, key: str, callback: Callable[[Any], None]) -> None:
        self._callbacks[key] = callback


class FakeEventHandlerBuilder:
    """模拟 ``EventDispatcherHandler.builder("","")`` 的链式 API。"""

    def __init__(self, *_: Any, **__: Any) -> None:
        self._handler = FakeEventHandler()

    def register_p2_im_message_receive_v1(
        self, callback: Callable[[Any], None]
    ) -> "FakeEventHandlerBuilder":
        self._handler._register("im.message.receive_v1", callback)
        return self

    def build(self) -> FakeEventHandler:
        return self._handler


class FakeWsClient:
    """``lark.ws.Client`` 的最小可观测替身。"""

    instances: list["FakeWsClient"] = []

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        event_handler: FakeEventHandler,
        log_level: Any = None,
        auto_reconnect: bool = True,
        **_: Any,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.event_handler = event_handler
        self.log_level = log_level
        self._auto_reconnect = auto_reconnect
        self.started = False
        self.stopped = False
        self.connect_calls = 0
        self.disconnect_calls = 0
        FakeWsClient.instances.append(self)

    async def _connect(self) -> None:
        self.connect_calls += 1
        self.started = True

    async def _ping_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return

    async def _disconnect(self) -> None:
        self.disconnect_calls += 1
        self.stopped = True

    def inject_event(self, event_obj: Any) -> None:
        callback = self.event_handler._callbacks.get("im.message.receive_v1")
        if callback is None:
            raise AssertionError("im.message.receive_v1 handler not registered")
        callback(event_obj)


@pytest.fixture
def fake_lark(monkeypatch: pytest.MonkeyPatch) -> type[FakeWsClient]:
    """安装 lark-oapi 的替身；每个测试独立计数。"""
    FakeWsClient.instances.clear()
    monkeypatch.setattr(
        feishu_long_conn.lark.ws,
        "Client",
        FakeWsClient,
    )
    monkeypatch.setattr(
        feishu_long_conn.lark.EventDispatcherHandler,
        "builder",
        lambda *args, **kwargs: FakeEventHandlerBuilder(),
    )
    return FakeWsClient


def make_event(
    *,
    text: str = "项目校验",
    chat_type: str = "group",
    msg_type: str = "text",
    open_id: str = "ou_a",
    chat_id: str = "oc_demo",
    content_override: str | None = None,
) -> SimpleNamespace:
    """构造与 lark P2ImMessageReceiveV1 结构对齐的最小事件对象。"""
    content = content_override if content_override is not None else json.dumps({"text": text})
    return SimpleNamespace(
        event=SimpleNamespace(
            sender=SimpleNamespace(
                sender_id=SimpleNamespace(open_id=open_id),
            ),
            message=SimpleNamespace(
                chat_id=chat_id,
                chat_type=chat_type,
                message_type=msg_type,
                content=content,
            ),
        )
    )


# --------------------------------------------------------------------------- #
# 1. 纯函数测试
# --------------------------------------------------------------------------- #


def test_matches_project_check_command_plain() -> None:
    assert matches_project_check_command("项目校验") is True
    assert matches_project_check_command("  项目校验 ") is True


def test_matches_project_check_command_with_at_mention() -> None:
    assert matches_project_check_command("@_user_1 项目校验") is True
    assert matches_project_check_command("@_user_42  项目校验") is True


def test_matches_project_check_command_negative() -> None:
    assert matches_project_check_command("") is False
    assert matches_project_check_command("hello") is False
    assert matches_project_check_command("项目检查") is False
    assert matches_project_check_command(None) is False  # type: ignore[arg-type]


def test_parse_allowed_open_ids_normalizes_input() -> None:
    raw = "ou_a, ou_b\nou_a\n  ou_c  ,,\nou_d"
    assert parse_allowed_open_ids(raw) == ["ou_a", "ou_b", "ou_c", "ou_d"]


def test_parse_allowed_open_ids_empty() -> None:
    assert parse_allowed_open_ids("") == []
    assert parse_allowed_open_ids("   \n  ,") == []


def test_translate_execution_error_value_error() -> None:
    msg = translate_execution_error(ValueError("当前项目尚未配置固定规则"))
    assert "当前项目尚未配置固定规则" in msg
    assert msg.startswith("项目校验失败")


def test_translate_execution_error_other() -> None:
    assert "依赖文件不存在" in translate_execution_error(
        FileNotFoundError("missing.xlsx")
    )
    assert "服务端依赖加载异常" in translate_execution_error(ImportError("svn"))
    assert "当前环境不支持" in translate_execution_error(NotImplementedError("svn"))
    runtime_msg = translate_execution_error(RuntimeError("boom"))
    assert "项目校验执行失败" in runtime_msg and "boom" in runtime_msg


def test_build_project_check_card_truncates_abnormal_results() -> None:
    summary = {
        "abnormal_results": [
            {"rule_name": f"R{i}", "location": f"loc{i}", "message": f"m{i}"}
            for i in range(_CARD_PREVIEW_LIMIT + 3)
        ],
        "failed_sources": [],
        "total_rows_scanned": 1000,
        "execution_time_ms": 234,
    }
    card = build_project_check_card(
        project_id=1,
        project_name="演示项目",
        summary=summary,
        platform_url="",
    )
    contents = json.dumps(card, ensure_ascii=False)
    assert "[演示项目] 项目校验完成" in contents
    assert f"更多 3 条" in contents
    # 每条预览仍应出现
    for i in range(_CARD_PREVIEW_LIMIT):
        assert f"R{i}" in contents


def test_build_project_check_card_truncates_failed_sources() -> None:
    summary = {
        "abnormal_results": [],
        "failed_sources": [f"src_{i}" for i in range(_CARD_PREVIEW_LIMIT + 2)],
        "total_rows_scanned": 0,
        "execution_time_ms": 1,
    }
    card = build_project_check_card(
        project_id=1,
        project_name="P",
        summary=summary,
        platform_url="",
    )
    contents = json.dumps(card, ensure_ascii=False)
    assert "**失败数据源**" in contents
    assert f"更多 2 条" in contents


def test_build_project_check_card_omits_action_when_no_url() -> None:
    summary = {
        "abnormal_results": [],
        "failed_sources": [],
        "total_rows_scanned": 0,
        "execution_time_ms": 0,
    }
    card = build_project_check_card(
        project_id=1,
        project_name="P",
        summary=summary,
        platform_url="",
    )
    elements = card["elements"]
    assert all(e.get("tag") != "action" for e in elements)


def test_build_project_check_card_renders_action_when_url_present() -> None:
    summary = {
        "abnormal_results": [],
        "failed_sources": [],
        "total_rows_scanned": 5,
        "execution_time_ms": 12,
    }
    card = build_project_check_card(
        project_id=1,
        project_name="P",
        summary=summary,
        platform_url="https://example.com/result/1",
    )
    actions = [e for e in card["elements"] if e.get("tag") == "action"]
    assert len(actions) == 1
    assert actions[0]["actions"][0]["url"] == "https://example.com/result/1"


# --------------------------------------------------------------------------- #
# 2. dispatch_message_event 路径测试
# --------------------------------------------------------------------------- #


@pytest.fixture
def stub_calls() -> dict[str, Any]:
    return {"text": [], "card": [], "execute": []}


@pytest.fixture
def stub_dispatch_dependencies(
    monkeypatch: pytest.MonkeyPatch, stub_calls: dict[str, Any]
) -> dict[str, Any]:
    """替换 dispatch 所依赖的 send_*_to_chat / execute_fixed_rules_for_project。"""

    async def _send_text(*, db, project_id, chat_id, text):  # noqa: ANN001
        stub_calls["text"].append(
            {"project_id": project_id, "chat_id": chat_id, "text": text}
        )
        return {"message_id": "om_text"}

    async def _send_card(*, db, project_id, chat_id, card):  # noqa: ANN001
        stub_calls["card"].append(
            {"project_id": project_id, "chat_id": chat_id, "card": card}
        )
        return {"message_id": "om_card"}

    async def _execute(db, project_id, **kwargs):  # noqa: ANN001
        stub_calls["execute"].append({"project_id": project_id, "kwargs": kwargs})
        return {
            "result_id": 1,
            "total_rows_scanned": 100,
            "failed_sources": [],
            "abnormal_results": [
                {"rule_name": "R1", "location": "loc", "message": "m"}
            ],
            "execution_time_ms": 12,
            "project_name": "示例项目",
        }

    monkeypatch.setattr(
        "backend.app.integrations.feishu_long_conn.send_text_to_chat", _send_text
    )
    monkeypatch.setattr(
        "backend.app.integrations.feishu_long_conn.send_card_to_chat", _send_card
    )
    monkeypatch.setattr(
        "backend.app.integrations.feishu_long_conn.execute_fixed_rules_for_project",
        _execute,
    )
    return stub_calls


@pytest.mark.anyio
async def test_dispatch_runs_full_flow_on_match(
    test_db,
    test_project_id: int,
    stub_dispatch_dependencies: dict[str, Any],
) -> None:
    event = make_event(text="项目校验")
    async with async_session_factory() as session:
        await dispatch_message_event(session, test_project_id, [], event)

    text_calls = stub_dispatch_dependencies["text"]
    card_calls = stub_dispatch_dependencies["card"]
    execute_calls = stub_dispatch_dependencies["execute"]
    assert len(text_calls) == 1
    assert text_calls[0]["text"] == _STARTED_REPLY
    assert text_calls[0]["chat_id"] == "oc_demo"
    assert len(card_calls) == 1
    assert card_calls[0]["chat_id"] == "oc_demo"
    assert "[示例项目] 项目校验完成" in json.dumps(
        card_calls[0]["card"], ensure_ascii=False
    )
    assert len(execute_calls) == 1
    assert execute_calls[0]["project_id"] == test_project_id


@pytest.mark.anyio
async def test_dispatch_blocks_when_open_id_not_in_whitelist(
    test_db,
    test_project_id: int,
    stub_dispatch_dependencies: dict[str, Any],
) -> None:
    event = make_event(text="项目校验", open_id="ou_intruder")
    async with async_session_factory() as session:
        await dispatch_message_event(
            session, test_project_id, ["ou_admin"], event
        )

    assert stub_dispatch_dependencies["text"] == [
        {
            "project_id": test_project_id,
            "chat_id": "oc_demo",
            "text": _FORBIDDEN_REPLY,
        }
    ]
    assert stub_dispatch_dependencies["card"] == []
    assert stub_dispatch_dependencies["execute"] == []


@pytest.mark.anyio
async def test_dispatch_ignores_non_command_or_non_text(
    test_db,
    test_project_id: int,
    stub_dispatch_dependencies: dict[str, Any],
) -> None:
    cases = [
        make_event(text="hello world"),
        make_event(text="项目校验", chat_type="p2p"),
        make_event(text="项目校验", msg_type="image"),
        make_event(text="项目校验", chat_id=""),
    ]
    async with async_session_factory() as session:
        for event in cases:
            await dispatch_message_event(session, test_project_id, [], event)

    assert stub_dispatch_dependencies["text"] == []
    assert stub_dispatch_dependencies["card"] == []
    assert stub_dispatch_dependencies["execute"] == []


@pytest.mark.anyio
async def test_dispatch_translates_execution_error(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
    stub_calls: dict[str, Any],
) -> None:
    async def _send_text(*, db, project_id, chat_id, text):  # noqa: ANN001
        stub_calls["text"].append(
            {"project_id": project_id, "chat_id": chat_id, "text": text}
        )

    async def _send_card(*, db, project_id, chat_id, card):  # noqa: ANN001
        stub_calls["card"].append(card)

    async def _explode(db, project_id, **kwargs):  # noqa: ANN001
        raise ValueError("当前项目尚未配置固定规则")

    monkeypatch.setattr(
        "backend.app.integrations.feishu_long_conn.send_text_to_chat", _send_text
    )
    monkeypatch.setattr(
        "backend.app.integrations.feishu_long_conn.send_card_to_chat", _send_card
    )
    monkeypatch.setattr(
        "backend.app.integrations.feishu_long_conn.execute_fixed_rules_for_project",
        _explode,
    )

    event = make_event(text="项目校验")
    async with async_session_factory() as session:
        await dispatch_message_event(session, test_project_id, [], event)

    texts = [c["text"] for c in stub_calls["text"]]
    assert texts[0] == _STARTED_REPLY
    assert texts[1].startswith("项目校验失败")
    assert "尚未配置固定规则" in texts[1]
    assert stub_calls["card"] == []


@pytest.mark.anyio
async def test_dispatch_download_sends_file_to_origin_group(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
    stub_dispatch_dependencies: dict[str, Any],
) -> None:
    async with async_session_factory() as session:
        session.add(
            FeishuBotConfigRecord(
                project_id=test_project_id,
                app_id="cli_download",
                app_secret_cipher=encrypt_secret("secret"),
                local_download_roots="[]",
                svn_download_roots="[]",
                allowed_download_suffixes='[".xlsx"]',
            )
        )
        await session.commit()

    file_calls: list[dict[str, Any]] = []

    def _resolve_download_file(requested_path, **kwargs):  # noqa: ANN001
        assert requested_path == "configs/a.xlsx"
        assert kwargs["allowed_suffixes"] == [".xlsx"]
        return SimpleNamespace(
            path=Path("D:/configs/a.xlsx"),
            display_name="a.xlsx",
        )

    async def _send_file(*, db, project_id, chat_id, file_path, file_name):  # noqa: ANN001
        file_calls.append(
            {
                "project_id": project_id,
                "chat_id": chat_id,
                "file_path": file_path,
                "file_name": file_name,
            }
        )
        return {"message_id": "om_file", "file_key": "file_x"}

    monkeypatch.setattr(
        "backend.app.integrations.feishu_long_conn.resolve_download_file",
        _resolve_download_file,
    )
    monkeypatch.setattr(
        "backend.app.integrations.feishu_long_conn.send_file_to_chat",
        _send_file,
    )

    event = make_event(text="@_user_1 下载 configs/a.xlsx")
    async with async_session_factory() as session:
        await dispatch_message_event(session, test_project_id, [], event)

    assert [item["text"] for item in stub_dispatch_dependencies["text"]] == [
        _DOWNLOAD_STARTED_REPLY
    ]
    assert file_calls == [
        {
            "project_id": test_project_id,
            "chat_id": "oc_demo",
            "file_path": Path("D:/configs/a.xlsx"),
            "file_name": "a.xlsx",
        }
    ]
    assert stub_dispatch_dependencies["execute"] == []
    assert stub_dispatch_dependencies["card"] == []


@pytest.mark.anyio
async def test_dispatch_download_missing_path_returns_usage(
    test_db,
    test_project_id: int,
    stub_dispatch_dependencies: dict[str, Any],
) -> None:
    event = make_event(text="@_user_1 下载")
    async with async_session_factory() as session:
        await dispatch_message_event(session, test_project_id, [], event)

    assert [item["text"] for item in stub_dispatch_dependencies["text"]] == [
        _DOWNLOAD_USAGE_REPLY
    ]
    assert stub_dispatch_dependencies["execute"] == []
    assert stub_dispatch_dependencies["card"] == []


@pytest.mark.anyio
async def test_dispatch_query_sends_listing_to_origin_group(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
    stub_dispatch_dependencies: dict[str, Any],
) -> None:
    async with async_session_factory() as session:
        session.add(
            FeishuBotConfigRecord(
                project_id=test_project_id,
                app_id="cli_query",
                app_secret_cipher=encrypt_secret("secret"),
                local_download_roots='["D:/local"]',
                svn_download_roots='["D:/svn"]',
                allowed_download_suffixes='[".xlsx"]',
            )
        )
        await session.commit()

    def _resolve_query_listing(request, **kwargs):  # noqa: ANN001
        assert request.directory == "configs"
        assert request.prefix == "ab"
        assert kwargs["local_roots"] == ["D:/local"]
        assert kwargs["svn_roots"] == ["D:/svn"]
        assert kwargs["allowed_suffixes"] == [".xlsx"]
        return [
            QueryListingGroup(
                title="SVN#1 svn",
                directory=Path("D:/svn/configs"),
                entries=["Abc/", "abc.xlsx"],
                source_kind="svn",
            ),
            QueryListingGroup(
                title="本地#1 local",
                directory=Path("D:/local/configs"),
                entries=[],
                source_kind="local",
            ),
        ]

    monkeypatch.setattr(
        "backend.app.integrations.feishu_long_conn.resolve_query_listing",
        _resolve_query_listing,
    )

    event = make_event(text="@_user_1 查询 configs ab")
    async with async_session_factory() as session:
        await dispatch_message_event(session, test_project_id, [], event)

    texts = [item["text"] for item in stub_dispatch_dependencies["text"]]
    assert texts[0] == _QUERY_STARTED_REPLY
    assert "配置目录查询结果：configs，前缀：ab" in texts[1]
    assert "[SVN#1 svn]" in texts[1]
    assert "- Abc/" in texts[1]
    assert "- abc.xlsx" in texts[1]
    assert "[本地#1 local]" in texts[1]
    assert "- 无匹配项" in texts[1]
    assert stub_dispatch_dependencies["execute"] == []
    assert stub_dispatch_dependencies["card"] == []


@pytest.mark.anyio
async def test_dispatch_query_reuses_open_id_whitelist(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
    stub_dispatch_dependencies: dict[str, Any],
) -> None:
    def fail_resolve(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("forbidden query must not resolve listings")

    monkeypatch.setattr(
        "backend.app.integrations.feishu_long_conn.resolve_query_listing",
        fail_resolve,
    )

    event = make_event(text="@_user_1 查询", open_id="ou_intruder")
    async with async_session_factory() as session:
        await dispatch_message_event(session, test_project_id, ["ou_admin"], event)

    assert stub_dispatch_dependencies["text"] == [
        {
            "project_id": test_project_id,
            "chat_id": "oc_demo",
            "text": _FORBIDDEN_REPLY,
        }
    ]
    assert stub_dispatch_dependencies["execute"] == []
    assert stub_dispatch_dependencies["card"] == []


@pytest.mark.anyio
async def test_dispatch_query_splits_long_result_messages(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
    stub_dispatch_dependencies: dict[str, Any],
) -> None:
    async with async_session_factory() as session:
        session.add(
            FeishuBotConfigRecord(
                project_id=test_project_id,
                app_id="cli_query_long",
                app_secret_cipher=encrypt_secret("secret"),
                local_download_roots='["D:/local"]',
                svn_download_roots="[]",
                allowed_download_suffixes='[".xlsx"]',
            )
        )
        await session.commit()

    def _resolve_query_listing(request, **kwargs):  # noqa: ANN001
        return [
            QueryListingGroup(
                title="本地#1 local",
                directory=Path("D:/local"),
                entries=[f"config_{index:02d}.xlsx" for index in range(12)],
                source_kind="local",
            )
        ]

    monkeypatch.setattr(feishu_long_conn, "_QUERY_MESSAGE_LIMIT", 90)
    monkeypatch.setattr(
        "backend.app.integrations.feishu_long_conn.resolve_query_listing",
        _resolve_query_listing,
    )

    event = make_event(text="@_user_1 查询")
    async with async_session_factory() as session:
        await dispatch_message_event(session, test_project_id, [], event)

    texts = [item["text"] for item in stub_dispatch_dependencies["text"]]
    assert texts[0] == _QUERY_STARTED_REPLY
    assert len(texts) > 2
    assert all(len(text) <= 90 for text in texts[1:])
    assert "config_00.xlsx" in "\n".join(texts[1:])
    assert "config_11.xlsx" in "\n".join(texts[1:])
    assert stub_dispatch_dependencies["execute"] == []
    assert stub_dispatch_dependencies["card"] == []


@pytest.mark.anyio
async def test_dispatch_swallows_send_errors(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """send_text 抛 FeishuApiError 时应只记日志，不打断后续 execute。"""
    execute_called = {"value": False}

    async def _explode_text(*, db, project_id, chat_id, text):  # noqa: ANN001
        raise FeishuApiError("HTTP 500 boom")

    async def _execute(db, project_id, **kwargs):  # noqa: ANN001
        execute_called["value"] = True
        return {
            "abnormal_results": [],
            "failed_sources": [],
            "total_rows_scanned": 0,
            "execution_time_ms": 1,
            "project_name": "P",
        }

    async def _send_card(*, db, project_id, chat_id, card):  # noqa: ANN001
        return {"message_id": "om"}

    monkeypatch.setattr(
        "backend.app.integrations.feishu_long_conn.send_text_to_chat", _explode_text
    )
    monkeypatch.setattr(
        "backend.app.integrations.feishu_long_conn.execute_fixed_rules_for_project",
        _execute,
    )
    monkeypatch.setattr(
        "backend.app.integrations.feishu_long_conn.send_card_to_chat", _send_card
    )

    event = make_event(text="项目校验")
    async with async_session_factory() as session:
        await dispatch_message_event(session, test_project_id, [], event)

    assert execute_called["value"] is True


# --------------------------------------------------------------------------- #
# 3. Supervisor 行为测试
# --------------------------------------------------------------------------- #


async def _create_extra_project(name: str) -> int:
    async with async_session_factory() as session:
        project = Project(name=name, description="副项目")
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project.id


async def _seed_feishu_record(
    project_id: int,
    *,
    app_id: str,
    secret_plain: str = "secret",
    allowed: str = "",
) -> None:
    async with async_session_factory() as session:
        session.add(
            FeishuBotConfigRecord(
                project_id=project_id,
                app_id=app_id,
                app_secret_cipher=encrypt_secret(secret_plain),
                allowed_open_ids=allowed,
            )
        )
        await session.commit()


@pytest.fixture
def supervisor() -> FeishuLongConnSupervisor:
    """每用例新构造一个 supervisor，避免相互污染（不复用模块级单例）。"""
    sup = FeishuLongConnSupervisor()
    sup.set_session_factory(async_session_factory)
    return sup


@pytest.mark.anyio
async def test_start_one_creates_client_and_marks_active(
    test_db,
    test_project_id: int,
    fake_lark: type[FakeWsClient],
    supervisor: FeishuLongConnSupervisor,
) -> None:
    await supervisor.start_one(
        test_project_id, "cli_a", "secret_a", ["ou_a"]
    )
    try:
        assert supervisor.get_state(test_project_id) == "active"
        assert len(FakeWsClient.instances) == 1
        client = FakeWsClient.instances[0]
        assert client.app_id == "cli_a"
        assert client.started is True
    finally:
        await supervisor.stop_all()


@pytest.mark.anyio
async def test_stop_one_disconnects_and_clears_state(
    test_db,
    test_project_id: int,
    fake_lark: type[FakeWsClient],
    supervisor: FeishuLongConnSupervisor,
) -> None:
    await supervisor.start_one(test_project_id, "cli_a", "secret_a", [])
    await supervisor.stop_one(test_project_id)

    assert supervisor.get_state(test_project_id) == "inactive"
    client = FakeWsClient.instances[0]
    assert client.stopped is True


@pytest.mark.anyio
async def test_stop_all_is_idempotent(
    test_db,
    test_project_id: int,
    fake_lark: type[FakeWsClient],
    supervisor: FeishuLongConnSupervisor,
) -> None:
    await supervisor.start_one(test_project_id, "cli_a", "secret_a", [])
    await supervisor.stop_all()
    await supervisor.stop_all()
    assert supervisor._clients == {}


@pytest.mark.anyio
async def test_app_id_conflict_keeps_first_owner(
    test_db,
    test_project_id: int,
    fake_lark: type[FakeWsClient],
    supervisor: FeishuLongConnSupervisor,
) -> None:
    other_project_id = await _create_extra_project(f"other-{uuid4().hex[:6]}")

    await supervisor.start_one(test_project_id, "cli_shared", "s1", [])
    await supervisor.start_one(other_project_id, "cli_shared", "s2", [])

    try:
        assert supervisor.get_state(test_project_id) == "active"
        assert supervisor.get_state(other_project_id) == "error"
        # 仅创建了一个 ws client，第二个项目因冲突跳过创建。
        assert len(FakeWsClient.instances) == 1
        # _app_id_owner 仍指向第一个项目。
        assert supervisor._app_id_owner == {"cli_shared": test_project_id}
    finally:
        await supervisor.stop_all()


@pytest.mark.anyio
async def test_reload_replaces_existing_client(
    test_db,
    test_project_id: int,
    fake_lark: type[FakeWsClient],
    supervisor: FeishuLongConnSupervisor,
) -> None:
    await _seed_feishu_record(
        test_project_id, app_id="cli_a", secret_plain="secret_v1"
    )
    await supervisor.start_one(test_project_id, "cli_a", "secret_v1", [])
    first_client = FakeWsClient.instances[0]

    # 模拟管理员改了 app_id（同时改了 secret），库里同步更新。
    async with async_session_factory() as session:
        result = await session.execute(
            select(FeishuBotConfigRecord).where(
                FeishuBotConfigRecord.project_id == test_project_id
            )
        )
        record = result.scalar_one()
        record.app_id = "cli_b"
        record.app_secret_cipher = encrypt_secret("secret_v2")
        record.allowed_open_ids = "ou_x"
        session.add(record)
        await session.commit()

    async with async_session_factory() as session:
        await supervisor.reload(test_project_id, session)

    try:
        assert first_client.stopped is True
        assert len(FakeWsClient.instances) == 2
        new_client = FakeWsClient.instances[1]
        assert new_client.started is True
        assert new_client.app_id == "cli_b"
        assert new_client.app_secret == "secret_v2"
        assert supervisor.get_state(test_project_id) == "active"
        assert supervisor._allowed_open_ids[test_project_id] == ["ou_x"]
    finally:
        await supervisor.stop_all()


@pytest.mark.anyio
async def test_reload_with_cleared_config_keeps_inactive(
    test_db,
    test_project_id: int,
    fake_lark: type[FakeWsClient],
    supervisor: FeishuLongConnSupervisor,
) -> None:
    """配置已被 DELETE 清空时，reload 应当只 stop 不 start。"""
    await supervisor.start_one(test_project_id, "cli_a", "secret_a", [])
    async with async_session_factory() as session:
        await supervisor.reload(test_project_id, session)

    assert supervisor.get_state(test_project_id) == "inactive"
    assert FakeWsClient.instances[0].stopped is True
    # 没有第二个 client 被创建。
    assert len(FakeWsClient.instances) == 1


@pytest.mark.anyio
async def test_event_callback_pushes_dispatch_to_main_loop(
    test_db,
    test_project_id: int,
    fake_lark: type[FakeWsClient],
    supervisor: FeishuLongConnSupervisor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FakeWsClient.inject_event 应当触发 supervisor 的 dispatch 调用。"""
    captured: list[int] = []

    async def _fake_dispatch(session, pid, allowed, event):  # noqa: ANN001
        captured.append(pid)

    monkeypatch.setattr(
        "backend.app.integrations.feishu_long_conn.dispatch_message_event",
        _fake_dispatch,
    )

    await supervisor.start_one(
        test_project_id, "cli_a", "secret_a", ["ou_a"]
    )
    try:
        client = FakeWsClient.instances[0]
        client.inject_event(make_event(text="项目校验"))
        # run_coroutine_threadsafe 调度后需要让事件循环跑一下。
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert captured == [test_project_id]
    finally:
        await supervisor.stop_all()


# --------------------------------------------------------------------------- #
# 4. FastAPI lifespan 集成
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_lifespan_starts_and_stops_supervisor(
    test_db,
    monkeypatch: pytest.MonkeyPatch,
    fake_lark: type[FakeWsClient],
) -> None:
    """FastAPI lifespan 启动时调一次 start_all、关闭时调一次 stop_all。

    用 ``async with lifespan(app)`` 直接驱动生命周期，比 ``TestClient`` 更轻：
    无需引入 ``asgi_lifespan`` / ``requests`` 兼容层，且能直接复用现有 anyio 测试栈。
    ``fake_lark`` 顺带把 lark.ws.Client 替换成 FakeWsClient，万一 supervisor 内部
    被实际调用也不会真打飞书。
    """
    counters = {"start": 0, "stop": 0}

    async def _fake_start_all() -> None:
        counters["start"] += 1

    async def _fake_stop_all() -> None:
        counters["stop"] += 1

    monkeypatch.setattr(
        feishu_long_conn.long_conn_supervisor, "start_all", _fake_start_all
    )
    monkeypatch.setattr(
        feishu_long_conn.long_conn_supervisor, "stop_all", _fake_stop_all
    )

    from backend.run import create_app, lifespan

    app = create_app()
    async with lifespan(app):
        pass

    assert counters == {"start": 1, "stop": 1}
