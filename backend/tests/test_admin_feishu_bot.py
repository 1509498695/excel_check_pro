"""管理后台：项目级飞书机器人配置 4 路由（GET/PUT/DELETE/test-send）。

覆盖范围：
- GET：未配置返回脱敏空值；已配置返回 has_app_secret=True，密文不外露。
- PUT：首次必须传 app_secret；增量保留 app_secret；空串清空被拒绝。
- PUT：白名单 round-trip（多行 + 逗号混合 → 去重保序），default_chat_id 清空。
- 跨项目同 app_id + 同 app_secret 允许，不同 app_secret → 400。
- DELETE：幂等，重复调用仍返回 204；调用 invalidate_token_cache。
- POST test-send：monkeypatch 替换底层发送函数，不真实打飞书；FeishuApiError → 400。
- 403：非项目管理员访问任意路由都被拒绝。
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.auth.service import create_access_token, hash_password
from backend.app.database import async_session_factory
from backend.app.integrations import feishu_bot as feishu_bot_module
from backend.app.integrations.feishu_bot import FeishuApiError
from backend.app.models import (
    FeishuBotBoundChatRecord,
    FeishuBotConfigRecord,
    ProjectAiCredentialRecord,
    Project,
    ProjectQueryRootRecord,
    ProjectSvnCredentialRecord,
    User,
    UserProjectRole,
)
from backend.app.security.crypto import decrypt_secret, encrypt_secret
from backend.run import app


@pytest.fixture(autouse=True)
def _clear_feishu_token_cache() -> None:
    """避免上一个测试残留的 token 缓存影响 invalidate_token_cache 断言。"""
    feishu_bot_module._TOKEN_CACHE.clear()
    feishu_bot_module._TOKEN_LOCKS.clear()
    yield
    feishu_bot_module._TOKEN_CACHE.clear()
    feishu_bot_module._TOKEN_LOCKS.clear()


class _FakeSupervisor:
    """admin 路由测试用的飞书长连接 supervisor 桩，避免真实拉起 ws 客户端。

    只暴露 admin/router.py 直接调用到的 3 个方法（reload / stop_one /
    get_state），并把每次调用的 project_id 收集到列表，方便断言。
    """

    def __init__(self) -> None:
        self.reload_calls: list[int] = []
        self.stop_one_calls: list[int] = []
        self.state_map: dict[int, str] = {}

    async def reload(self, project_id: int, db) -> None:  # noqa: ANN001
        self.reload_calls.append(project_id)

    async def stop_one(self, project_id: int) -> None:
        self.stop_one_calls.append(project_id)

    def get_state(self, project_id: int) -> str:
        return self.state_map.get(project_id, "inactive")


@pytest.fixture
def fake_supervisor(monkeypatch: pytest.MonkeyPatch) -> _FakeSupervisor:
    """把 admin/router.py 里 import 进来的 long_conn_supervisor 替换成 FakeSupervisor。

    必须 patch `backend.app.admin.router.long_conn_supervisor`：admin/router.py 里
    通过 `from ... import long_conn_supervisor` 拿到了局部引用，patch 模块原始
    位置不会生效。
    """
    fake = _FakeSupervisor()
    monkeypatch.setattr(
        "backend.app.admin.router.long_conn_supervisor", fake
    )
    return fake


@pytest.fixture(autouse=True)
def _autouse_supervisor(fake_supervisor: _FakeSupervisor) -> None:
    """所有 admin 飞书路由测试默认走 FakeSupervisor，避免触发真实长连接。"""
    return None


async def _create_secondary_project(name: str | None = None) -> int:
    """新建一个额外项目，用于跨项目唯一性冲突等场景。"""
    project_name = name or f"secondary-{uuid4().hex[:8]}"
    async with async_session_factory() as session:
        project = Project(name=project_name, description="副项目")
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project.id


async def _create_normal_user_headers(project_id: int) -> dict[str, str]:
    """构造一个普通成员用户，用于验证 403。"""
    async with async_session_factory() as session:
        user = User(
            username=f"plain_{uuid4().hex[:8]}",
            hashed_password=hash_password("pwd"),
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


async def _read_feishu_record(project_id: int) -> FeishuBotConfigRecord | None:
    """便于断言落库内容（含密文解密回字符串校验）。"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(FeishuBotConfigRecord).where(
                FeishuBotConfigRecord.project_id == project_id
            )
        )
        return result.scalar_one_or_none()


async def _read_bound_chats(project_id: int) -> list[str]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(FeishuBotBoundChatRecord.chat_id)
            .where(FeishuBotBoundChatRecord.project_id == project_id)
            .order_by(FeishuBotBoundChatRecord.chat_id)
        )
        return list(result.scalars().all())


async def _read_query_roots(project_id: int) -> list[ProjectQueryRootRecord]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ProjectQueryRootRecord)
            .where(ProjectQueryRootRecord.project_id == project_id)
            .order_by(ProjectQueryRootRecord.alias)
        )
        return list(result.scalars().all())


async def _read_project_credentials(
    project_id: int,
) -> tuple[ProjectSvnCredentialRecord | None, ProjectAiCredentialRecord | None]:
    async with async_session_factory() as session:
        svn_result = await session.execute(
            select(ProjectSvnCredentialRecord).where(
                ProjectSvnCredentialRecord.project_id == project_id
            )
        )
        ai_result = await session.execute(
            select(ProjectAiCredentialRecord).where(
                ProjectAiCredentialRecord.project_id == project_id
            )
        )
        return svn_result.scalar_one_or_none(), ai_result.scalar_one_or_none()


async def _seed_project_svn_test_config(
    project_id: int,
    *,
    password: str = "svn_pwd",
    roots: list[tuple[str, str, str, str]] | None = None,
) -> None:
    """直接准备项目级 SVN 凭据和 query_roots，用于连接测试接口。"""
    rows = roots or [
        ("game_datas", "游戏配置主目录", "https://svn.example.com/game", "enabled"),
        ("activity_datas", "活动配置目录", "https://svn.example.com/activity", "enabled"),
    ]
    async with async_session_factory() as session:
        session.add(
            ProjectSvnCredentialRecord(
                project_id=project_id,
                username="svn_admin",
                password_cipher=encrypt_secret(password),
            )
        )
        for alias, display_name, svn_url, status in rows:
            session.add(
                ProjectQueryRootRecord(
                    project_id=project_id,
                    alias=alias,
                    display_name=display_name,
                    svn_root_url=svn_url,
                    status=status,
                )
            )
        await session.commit()


@pytest.mark.anyio
async def test_get_returns_empty_skeleton_when_unconfigured(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """未配置时 GET 返回脱敏空骨架。"""
    response = await auth_client.get(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot"
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data == {
        "configured": False,
        "app_id": "",
        "has_app_secret": False,
        "default_chat_id": "",
        "bound_chat_ids": [],
        "allowed_open_ids": [],
        "local_download_roots": [],
        "svn_download_roots": [],
        "allowed_download_suffixes": [
            ".xls",
            ".xlsx",
            ".csv",
            ".json",
            ".xml",
            ".txt",
        ],
        "query_roots": [],
        "svn_credential": {
            "configured": False,
            "username_masked": "",
            "updated_at": None,
        },
        "ai_credential": {
            "configured": False,
            "provider_preset": "",
            "provider": "",
            "base_url": "",
            "model": "",
            "api_key_masked": "",
            "masked_api_key": "",
            "has_extra_headers": False,
            "enabled": False,
            "last_test_status": "",
            "last_test_at": None,
            "last_test_error_summary": "",
            "updated_at": None,
        },
        "ai_match_params": {
            "auto_match_threshold": 0.9,
            "candidate_threshold": 0.6,
            "max_candidates": 10,
        },
        "connection_state": "inactive",
        "updated_at": None,
    }


@pytest.mark.anyio
async def test_put_first_time_requires_app_secret(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """首次创建时未传 app_secret 应被拒绝。"""
    response = await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot",
        json={"app_id": "cli_first"},
    )
    assert response.status_code == 400
    assert "app_secret" in response.json()["detail"]


@pytest.mark.anyio
async def test_put_blank_app_secret_rejected(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """显式传空串 app_secret 应被拒绝（应走 DELETE 整体清除）。"""
    response = await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot",
        json={"app_id": "cli_first", "app_secret": ""},
    )
    assert response.status_code == 400
    assert "app_secret" in response.json()["detail"]


@pytest.mark.anyio
async def test_put_creates_then_get_returns_masked_data(
    auth_client: AsyncClient,
    test_project_id: int,
    tmp_path,
) -> None:
    """首次 PUT 创建成功 → GET 返回 has_app_secret=True 且不暴露密文。"""
    local_root = tmp_path / "local configs"
    svn_root = tmp_path / "svn_configs"
    payload = {
        "app_id": "cli_round_trip",
        "app_secret": "S3CRET_v1",
        "default_chat_id": "oc_chat_one",
        "allowed_open_ids": "ou_a, ou_b\nou_a\n  ou_c  ",
        "local_download_roots": f"{local_root}\n{local_root}",
        "svn_download_roots": str(svn_root),
        "allowed_download_suffixes": "xlsx, .json\n.csv",
    }
    put_resp = await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot",
        json=payload,
    )
    assert put_resp.status_code == 200
    put_data = put_resp.json()["data"]
    assert put_data["configured"] is True
    assert put_data["app_id"] == "cli_round_trip"
    assert put_data["has_app_secret"] is True
    assert put_data["default_chat_id"] == "oc_chat_one"
    assert put_data["allowed_open_ids"] == ["ou_a", "ou_b", "ou_c"]
    assert put_data["local_download_roots"] == [
        str(local_root.resolve(strict=False))
    ]
    assert put_data["svn_download_roots"] == [str(svn_root.resolve(strict=False))]
    assert put_data["allowed_download_suffixes"] == [".xlsx", ".json", ".csv"]
    assert put_data["connection_state"] == "inactive"
    assert put_data["updated_at"] is not None

    record = await _read_feishu_record(test_project_id)
    assert record is not None
    assert record.app_id == "cli_round_trip"
    # 密文应能解出原始明文，但 GET 永远不返回原文。
    assert decrypt_secret(record.app_secret_cipher) == "S3CRET_v1"
    assert record.allowed_open_ids == "ou_a,ou_b,ou_c"
    assert json.loads(record.local_download_roots) == [
        str(local_root.resolve(strict=False))
    ]
    assert json.loads(record.svn_download_roots) == [str(svn_root.resolve(strict=False))]
    assert json.loads(record.allowed_download_suffixes) == [
        ".xlsx",
        ".json",
        ".csv",
    ]

    get_resp = await auth_client.get(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot"
    )
    assert get_resp.status_code == 200
    get_data = get_resp.json()["data"]
    assert get_data["has_app_secret"] is True
    assert "app_secret" not in get_data
    assert get_data["allowed_open_ids"] == ["ou_a", "ou_b", "ou_c"]
    assert get_data["local_download_roots"] == [
        str(local_root.resolve(strict=False))
    ]
    assert get_data["svn_download_roots"] == [str(svn_root.resolve(strict=False))]
    assert get_data["allowed_download_suffixes"] == [".xlsx", ".json", ".csv"]


@pytest.mark.anyio
async def test_put_saves_extended_project_feishu_settings(
    auth_client: AsyncClient,
    test_project_id: int,
    tmp_path,
) -> None:
    """PUT 应保存新增绑定群、query_roots、项目凭据和 AI 默认参数。"""
    payload = {
        "app_id": "cli_extended",
        "app_secret": "S3CRET_ext",
        "default_chat_id": "oc_default",
        "bound_chat_ids": ["oc_default", "oc_backup"],
        "allowed_open_ids": "",
        "local_download_roots": str((tmp_path / "local").resolve(strict=False)),
        "svn_download_roots": str((tmp_path / "svn").resolve(strict=False)),
        "allowed_download_suffixes": ".xls,.xlsx",
        "query_roots": [
            {
                "alias": "game_datas",
                "display_name": "游戏配置主目录",
                "svn_url": "https://svn.example.com/game",
                "enabled": True,
            },
            {
                "alias": "activity_datas",
                "display_name": "活动配置目录",
                "svn_url": "https://svn.example.com/activity",
                "enabled": False,
            },
        ],
        "svn_credential": {"username": "svn_admin", "password": "svn_pwd"},
        "ai_credential": {
            "provider_preset": "openai",
            "base_url": "",
            "model": "",
            "api_key": "sk-project-secret",
            "extra_headers": {"X-Project": "ExcelCheck"},
        },
        "ai_match_params": {
            "auto_match_threshold": 0.91,
            "candidate_threshold": 0.61,
            "max_candidates": 8,
        },
    }

    response = await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot",
        json=payload,
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["bound_chat_ids"] == ["oc_default", "oc_backup"]
    assert data["allowed_open_ids"] == []
    assert data["query_roots"] == [
        {
            "alias": "game_datas",
            "display_name": "游戏配置主目录",
            "svn_url": "https://svn.example.com/game",
            "enabled": True,
        },
        {
            "alias": "activity_datas",
            "display_name": "活动配置目录",
            "svn_url": "https://svn.example.com/activity",
            "enabled": False,
        },
    ]
    assert data["svn_credential"]["configured"] is True
    assert data["svn_credential"]["username_masked"] == "svn_admin"
    assert "password" not in str(data["svn_credential"]).lower()
    assert data["ai_credential"]["configured"] is True
    assert data["ai_credential"]["provider_preset"] == "openai"
    assert data["ai_credential"]["base_url"] == "https://api.openai.com/v1"
    assert data["ai_credential"]["model"] == "gpt-5.4-mini"
    assert data["ai_credential"]["api_key_masked"] == "sk-***cret"
    assert data["ai_credential"]["has_extra_headers"] is True
    assert data["ai_match_params"] == {
        "auto_match_threshold": 0.91,
        "candidate_threshold": 0.61,
        "max_candidates": 8,
    }

    record = await _read_feishu_record(test_project_id)
    assert record is not None
    assert record.auto_match_threshold == 0.91
    assert record.candidate_threshold == 0.61
    assert record.max_candidates == 8
    assert await _read_bound_chats(test_project_id) == ["oc_backup", "oc_default"]
    roots = await _read_query_roots(test_project_id)
    assert [(root.alias, root.svn_root_url, root.status) for root in roots] == [
        ("activity_datas", "https://svn.example.com/activity", "disabled"),
        ("game_datas", "https://svn.example.com/game", "enabled"),
    ]
    svn_credential, ai_credential = await _read_project_credentials(test_project_id)
    assert svn_credential is not None
    assert decrypt_secret(svn_credential.password_cipher) == "svn_pwd"
    assert ai_credential is not None
    assert decrypt_secret(ai_credential.encrypted_api_key) == "sk-project-secret"


@pytest.mark.anyio
async def test_project_svn_credential_test_checks_enabled_query_roots(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """项目级 SVN 连接测试应逐个测试启用的远端 query_roots。"""
    await _seed_project_svn_test_config(
        test_project_id,
        password="svn_password_should_not_leak",
        roots=[
            ("game_datas", "游戏配置主目录", "https://svn.example.com/game", "enabled"),
            ("activity_datas", "活动配置目录", "https://svn.example.com/activity", "enabled"),
            ("local_datas", "本地目录", "D:/configs/local", "enabled"),
            ("disabled_datas", "禁用目录", "https://svn.example.com/disabled", "disabled"),
        ],
    )
    calls: list[tuple[str, str]] = []

    def _list_svn_directory(url, *, credentials, timeout=None):  # noqa: ANN001
        calls.append((url, credentials.password))
        return {"dir_url": url, "entries": [{"name": "IAPConfig.xls"}]}

    monkeypatch.setattr(
        "backend.app.admin.router.list_svn_directory",
        _list_svn_directory,
    )

    response = await auth_client.post(
        f"/api/v1/admin/projects/{test_project_id}/svn-credential/test"
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "success"
    assert [item["alias"] for item in data["items"]] == ["game_datas", "activity_datas"]
    assert all(item["status"] == "success" for item in data["items"])
    assert calls == [
        ("https://svn.example.com/game", "svn_password_should_not_leak"),
        ("https://svn.example.com/activity", "svn_password_should_not_leak"),
    ]
    assert "svn_password_should_not_leak" not in response.text


@pytest.mark.anyio
async def test_project_svn_credential_test_rejects_non_admin(
    test_project_id: int,
) -> None:
    """普通项目成员不能触发项目级 SVN 连接测试。"""
    headers = await _create_normal_user_headers(test_project_id)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    ) as client:
        response = await client.post(
            f"/api/v1/admin/projects/{test_project_id}/svn-credential/test"
        )

    assert response.status_code == 403


@pytest.mark.anyio
async def test_project_svn_credential_test_requires_saved_credential(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """未保存项目级 SVN 凭据时返回明确中文错误。"""
    response = await auth_client.post(
        f"/api/v1/admin/projects/{test_project_id}/svn-credential/test"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "请先保存项目级 SVN 凭据后再测试连接"


@pytest.mark.anyio
async def test_project_svn_credential_test_requires_enabled_remote_query_root(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """无启用远端 query_roots 时返回明确中文错误。"""
    await _seed_project_svn_test_config(
        test_project_id,
        roots=[
            ("local_datas", "本地目录", "D:/configs/local", "enabled"),
            ("disabled_datas", "禁用目录", "https://svn.example.com/disabled", "disabled"),
        ],
    )

    response = await auth_client.post(
        f"/api/v1/admin/projects/{test_project_id}/svn-credential/test"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "请先配置并启用至少一个 SVN 数据根后再测试连接"


@pytest.mark.anyio
async def test_project_svn_credential_test_returns_failure_summary_without_password(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单个 query_root 失败时返回脱敏错误摘要，不泄露 SVN 密码。"""
    await _seed_project_svn_test_config(
        test_project_id,
        password="do_not_return_this_password",
        roots=[
            ("game_datas", "游戏配置主目录", "https://svn.example.com/game", "enabled"),
            ("activity_datas", "活动配置目录", "https://svn.example.com/activity", "enabled"),
        ],
    )

    def _list_svn_directory(url, *, credentials, timeout=None):  # noqa: ANN001
        if "activity" in url:
            raise RuntimeError(
                "当前账号无权访问测试目录，请检查 SVN 用户权限或重新输入凭据。"
            )
        return {"dir_url": url, "entries": [{"name": "IAPConfig.xls"}]}

    monkeypatch.setattr(
        "backend.app.admin.router.list_svn_directory",
        _list_svn_directory,
    )

    response = await auth_client.post(
        f"/api/v1/admin/projects/{test_project_id}/svn-credential/test"
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert [(item["alias"], item["status"]) for item in data["items"]] == [
        ("game_datas", "success"),
        ("activity_datas", "failed"),
    ]
    assert "当前账号无权访问测试目录" in data["items"][1]["message"]
    assert "do_not_return_this_password" not in response.text


@pytest.mark.anyio
async def test_put_omitting_app_secret_keeps_existing_secret(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """已有配置时 app_secret 字段缺省，密文应保持不变。"""
    base_payload = {
        "app_id": "cli_keep",
        "app_secret": "secret_v1",
        "default_chat_id": "oc_v1",
    }
    await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot",
        json=base_payload,
    )
    record_before = await _read_feishu_record(test_project_id)
    assert record_before is not None
    cipher_before = record_before.app_secret_cipher

    update_payload = {
        "app_id": "cli_keep",
        "default_chat_id": "",
    }
    update_resp = await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot",
        json=update_payload,
    )
    assert update_resp.status_code == 200
    record_after = await _read_feishu_record(test_project_id)
    assert record_after is not None
    assert record_after.app_secret_cipher == cipher_before
    assert record_after.default_chat_id == ""


@pytest.mark.anyio
async def test_put_rejects_default_chat_id_not_in_explicit_bound_chats(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """显式传 bound_chat_ids 时 default_chat_id 必须包含其中。"""
    response = await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot",
        json={
            "app_id": "cli_bound_check",
            "app_secret": "s",
            "default_chat_id": "oc_default",
            "bound_chat_ids": ["oc_other"],
        },
    )

    assert response.status_code == 400
    assert "default_chat_id 必须包含在绑定群列表中" in response.json()["detail"]


@pytest.mark.anyio
async def test_put_rejects_chat_id_already_bound_to_other_project(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """一个飞书群只能绑定一个项目。"""
    other_project_id = await _create_secondary_project("项目 A")

    first = await auth_client.put(
        f"/api/v1/admin/projects/{other_project_id}/feishu-bot",
        json={
            "app_id": "cli_chat_owner",
            "app_secret": "s1",
            "default_chat_id": "oc_shared",
            "bound_chat_ids": ["oc_shared"],
        },
    )
    assert first.status_code == 200, first.text

    second = await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot",
        json={
            "app_id": "cli_chat_target",
            "app_secret": "s2",
            "default_chat_id": "oc_shared",
            "bound_chat_ids": ["oc_shared"],
        },
    )

    assert second.status_code == 400
    assert second.json()["detail"] == "该飞书群已绑定项目「项目 A」，不能重复绑定到「test-project」"


@pytest.mark.anyio
async def test_put_allows_same_app_id_with_same_app_secret(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """同一个 app_id 可被多个项目复用，但 app_secret 必须一致。"""
    other_project_id = await _create_secondary_project()

    first = await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot",
        json={"app_id": "cli_shared", "app_secret": "same_secret"},
    )
    assert first.status_code == 200

    second = await auth_client.put(
        f"/api/v1/admin/projects/{other_project_id}/feishu-bot",
        json={"app_id": "cli_shared", "app_secret": "same_secret"},
    )
    assert second.status_code == 200, second.text


@pytest.mark.anyio
async def test_put_rejects_same_app_id_with_different_app_secret(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """同 app_id 跨项目配置不同 app_secret 时应返回指定中文错误。"""
    other_project_id = await _create_secondary_project()

    first = await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot",
        json={"app_id": "cli_shared_reject", "app_secret": "s1"},
    )
    assert first.status_code == 200

    second = await auth_client.put(
        f"/api/v1/admin/projects/{other_project_id}/feishu-bot",
        json={"app_id": "cli_shared_reject", "app_secret": "s2"},
    )
    assert second.status_code == 400
    assert second.json()["detail"] == "该 App ID 已在其他项目配置，请使用相同 App Secret 或联系管理员确认"


@pytest.mark.anyio
async def test_put_rejects_duplicate_query_root_alias(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """query_roots alias 在项目内必须唯一。"""
    response = await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot",
        json={
            "app_id": "cli_duplicate_alias",
            "app_secret": "s",
            "query_roots": [
                {"alias": "game_datas", "display_name": "主目录", "svn_url": "https://svn/a", "enabled": True},
                {"alias": "game_datas", "display_name": "重复", "svn_url": "https://svn/b", "enabled": True},
            ],
        },
    )

    assert response.status_code == 400
    assert "query_roots alias 重复：game_datas" in response.json()["detail"]


@pytest.mark.anyio
async def test_put_rejects_empty_query_root_svn_url(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """query_roots.svn_url 不能为空。"""
    response = await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot",
        json={
            "app_id": "cli_empty_svn_url",
            "app_secret": "s",
            "query_roots": [
                {"alias": "game_datas", "display_name": "主目录", "svn_url": " ", "enabled": True}
            ],
        },
    )

    assert response.status_code == 400
    assert "query_roots.svn_url 不能为空：game_datas" in response.json()["detail"]


@pytest.mark.anyio
async def test_delete_is_idempotent_and_clears_token_cache(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """DELETE 在已配置 / 未配置两种情况下都应返回 204，并清空 token 缓存。"""
    await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot",
        json={"app_id": "cli_del", "app_secret": "to_be_deleted"},
    )
    feishu_bot_module._TOKEN_CACHE[test_project_id] = ("stale_token", 9_999_999_999.0)

    first = await auth_client.delete(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot"
    )
    assert first.status_code == 204
    assert test_project_id not in feishu_bot_module._TOKEN_CACHE

    second = await auth_client.delete(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot"
    )
    assert second.status_code == 204

    record = await _read_feishu_record(test_project_id)
    assert record is None


@pytest.mark.anyio
async def test_test_send_text_uses_monkeypatched_sender(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """test-send 文本走纯文本通道，monkeypatch 不真实打飞书。"""
    captured: dict[str, Any] = {}

    async def _fake_send_text(*, db, project_id, chat_id, text):
        captured["channel"] = "text"
        captured["chat_id"] = chat_id
        captured["text"] = text
        captured["project_id"] = project_id
        return {"message_id": "om_test_text", "raw": {}}

    async def _fake_send_card(*, db, project_id, chat_id, card):
        captured["channel"] = "card"
        return {"message_id": "om_test_card", "raw": {}}

    monkeypatch.setattr(
        "backend.app.admin.router.send_text_to_chat", _fake_send_text
    )
    monkeypatch.setattr(
        "backend.app.admin.router.send_card_to_chat", _fake_send_card
    )

    response = await auth_client.post(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot/test-send",
        json={"chat_id": "oc_demo", "text": "hello"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["message_id"] == "om_test_text"
    assert captured == {
        "channel": "text",
        "chat_id": "oc_demo",
        "text": "hello",
        "project_id": test_project_id,
    }


@pytest.mark.anyio
async def test_test_send_card_path(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """use_card=True 时走卡片通道。"""
    captured: dict[str, Any] = {}

    async def _fake_send_card(*, db, project_id, chat_id, card):
        captured["chat_id"] = chat_id
        captured["card"] = card
        return {"message_id": "om_card", "raw": {}}

    async def _fake_send_text(*, db, project_id, chat_id, text):
        raise AssertionError("text path should not be used when use_card=True")

    monkeypatch.setattr(
        "backend.app.admin.router.send_card_to_chat", _fake_send_card
    )
    monkeypatch.setattr(
        "backend.app.admin.router.send_text_to_chat", _fake_send_text
    )

    response = await auth_client.post(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot/test-send",
        json={"chat_id": "oc_demo", "text": "卡片正文", "use_card": True},
    )
    assert response.status_code == 200
    assert response.json()["data"]["message_id"] == "om_card"
    assert captured["chat_id"] == "oc_demo"
    assert captured["card"]["header"]["title"]["content"] == "测试消息"
    assert captured["card"]["elements"][0]["text"]["content"] == "卡片正文"


@pytest.mark.anyio
async def test_test_send_translates_feishu_api_error_to_400(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """底层 FeishuApiError 应被翻译成 400 + 中文 detail。"""

    async def _explode(*, db, project_id, chat_id, text):
        raise FeishuApiError("飞书 API 错误（code=10003）：invalid app_secret")

    monkeypatch.setattr(
        "backend.app.admin.router.send_text_to_chat", _explode
    )

    response = await auth_client.post(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot/test-send",
        json={"chat_id": "oc_demo", "text": "hi"},
    )
    assert response.status_code == 400
    assert "code=10003" in response.json()["detail"]


@pytest.mark.anyio
async def test_non_project_admin_gets_403_on_all_routes(
    test_project_id: int,
    test_db,
) -> None:
    """普通成员不能访问飞书机器人 4 个管理路由。"""
    headers = await _create_normal_user_headers(test_project_id)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    ) as client:
        get_resp = await client.get(
            f"/api/v1/admin/projects/{test_project_id}/feishu-bot"
        )
        put_resp = await client.put(
            f"/api/v1/admin/projects/{test_project_id}/feishu-bot",
            json={"app_id": "cli", "app_secret": "s"},
        )
        del_resp = await client.delete(
            f"/api/v1/admin/projects/{test_project_id}/feishu-bot"
        )
        send_resp = await client.post(
            f"/api/v1/admin/projects/{test_project_id}/feishu-bot/test-send",
            json={"chat_id": "oc_demo", "text": "hi"},
        )
    assert get_resp.status_code == 403
    assert put_resp.status_code == 403
    assert del_resp.status_code == 403
    assert send_resp.status_code == 403


@pytest.mark.anyio
async def test_put_triggers_supervisor_reload(
    auth_client: AsyncClient,
    test_project_id: int,
    fake_supervisor: _FakeSupervisor,
) -> None:
    """成功 PUT 后 supervisor.reload 应被调用一次，stop_one 不被调用。"""
    response = await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot",
        json={"app_id": "cli_reload", "app_secret": "s"},
    )
    assert response.status_code == 200
    assert fake_supervisor.reload_calls == [test_project_id]
    assert fake_supervisor.stop_one_calls == []


@pytest.mark.anyio
async def test_delete_triggers_supervisor_stop_one(
    auth_client: AsyncClient,
    test_project_id: int,
    fake_supervisor: _FakeSupervisor,
) -> None:
    """DELETE 应触发一次 supervisor.stop_one(project_id)。"""
    await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot",
        json={"app_id": "cli_stop", "app_secret": "s"},
    )
    fake_supervisor.reload_calls.clear()

    response = await auth_client.delete(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot"
    )
    assert response.status_code == 204
    assert fake_supervisor.stop_one_calls == [test_project_id]
    assert fake_supervisor.reload_calls == []


@pytest.mark.parametrize("primed_state", ["inactive", "active", "error"])
@pytest.mark.anyio
async def test_get_returns_supervisor_state(
    auth_client: AsyncClient,
    test_project_id: int,
    fake_supervisor: _FakeSupervisor,
    primed_state: str,
) -> None:
    """GET 应使用 supervisor.get_state 覆盖序列化里的兜底 inactive。"""
    fake_supervisor.state_map[test_project_id] = primed_state
    response = await auth_client.get(
        f"/api/v1/admin/projects/{test_project_id}/feishu-bot"
    )
    assert response.status_code == 200
    assert response.json()["data"]["connection_state"] == primed_state
