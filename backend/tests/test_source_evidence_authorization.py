"""Source Evidence 飞书授权闭环测试。"""

from __future__ import annotations

import datetime
import json
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.database import async_session_factory
from backend.app.integrations.feishu_bot import FeishuApiError
from backend.app.integrations.feishu_client import (
    FEISHU_API_ERROR,
    FEISHU_METADATA_UNAVAILABLE,
    FeishuClientError,
    FeishuDriveMetadata,
    FeishuOAuthUserInfo,
    FeishuWikiNode,
)
from backend.app.models import (
    FeishuBotConfigRecord,
    SourceEvidenceAuthorizationRecord,
    SourceEvidenceResourceRecord,
    SourceEvidenceRunRecord,
)
from backend.app.security.crypto import encrypt_secret
from backend.app.test_cases import source_evidence_authorization as authz
from backend.run import app


SOURCE_URL = "https://demo.feishu.cn/docx/doccnSource123"
SOURCE_TOKEN = "doccnSource123"


async def _seed_bot(
    project_id: int,
    *,
    app_id: str = "cli_source_evidence",
    default_chat_id: str = "oc_default",
) -> None:
    async with async_session_factory() as session:
        session.add(
            FeishuBotConfigRecord(
                project_id=project_id,
                app_id=app_id,
                app_secret_cipher=encrypt_secret("secret_unit"),
                default_chat_id=default_chat_id,
            )
        )
        await session.commit()


async def _seed_run(
    project_id: int,
    *,
    status: str = "pending_permission",
    source_url: str = SOURCE_URL,
    source_token: str = "",
    source_title: str = "源文档",
    expires_delta: datetime.timedelta = datetime.timedelta(days=1),
    resource_download_status: str | None = None,
) -> int:
    async with async_session_factory() as session:
        run = SourceEvidenceRunRecord(
            project_id=project_id,
            source_type="feishu",
            source_url=source_url,
            source_token=source_token,
            source_identifier=source_token or SOURCE_TOKEN,
            source_title=source_title,
            status=status,
            expires_at=datetime.datetime.now(datetime.UTC) + expires_delta,
        )
        session.add(run)
        await session.flush()
        if resource_download_status is not None:
            session.add(
                SourceEvidenceResourceRecord(
                    run_id=run.id,
                    project_id=project_id,
                    ref="img_001",
                    resource_type="image",
                    position="docx:block:image",
                    filename="ui.png",
                    file_token="fileTokenSecret123",
                    status="unobserved",
                    download_status=resource_download_status,
                )
            )
        await session.commit()
        return run.id


async def _seed_authorization_record(
    project_id: int,
    run_id: int,
    *,
    state: str = "state-source-evidence",
    status: str = authz.STATUS_AUTHORIZATION_SENT,
    source_token: str = SOURCE_TOKEN,
    doc_type: str = "docx",
    state_expires_delta: datetime.timedelta = datetime.timedelta(minutes=10),
    expires_delta: datetime.timedelta = datetime.timedelta(days=90),
    invalidated_at: datetime.datetime | None = None,
) -> int:
    now = datetime.datetime.now(datetime.UTC)
    async with async_session_factory() as session:
        record = SourceEvidenceAuthorizationRecord(
            project_id=project_id,
            app_id="cli_source_evidence",
            doc_type=doc_type,
            permission="edit",
            source_token_hash=authz.hash_source_token(source_token),
            source_token_alias_hashes_json="[]",
            status=status,
            state_hash=authz.hash_authorization_state(state),
            state_expires_at=now + state_expires_delta,
            originating_run_id=run_id,
            target_mode=authz.TARGET_DEFAULT_CHAT,
            sent_targets_count=1,
            failed_targets_count=0,
            expires_at=now + expires_delta,
            invalidated_at=invalidated_at,
        )
        session.add(record)
        await session.commit()
        return record.id


def _metadata(
    *,
    owner_ids: list[str] | None = None,
    creator_ids: list[str] | None = None,
    token: str = SOURCE_TOKEN,
    doc_type: str = "docx",
) -> FeishuDriveMetadata:
    return FeishuDriveMetadata(
        token=token,
        doc_type=doc_type,
        drive_type="doc",
        title="源文档",
        owner_ids=owner_ids or [],
        creator_ids=creator_ids or [],
        raw={},
    )


def _oauth_url_from_card(card: dict[str, object]) -> str:
    return str(card["elements"][1]["actions"][0]["url"])  # type: ignore[index]


@pytest.mark.anyio
async def test_authorization_request_owner_partial_success_does_not_fallback_to_chat(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_bot(test_project_id)
    run_id = await _seed_run(test_project_id)
    direct_calls: list[str] = []
    chat_calls: list[str] = []

    async def fake_metadata(*_args, **_kwargs):
        return _metadata(owner_ids=["ou_fail", "ou_ok"])

    async def fake_send_open_id(_db, _project_id, open_id, _card):
        direct_calls.append(open_id)
        if open_id == "ou_fail":
            raise FeishuApiError("open_id failed")
        return {"message_id": f"mid-{open_id}"}

    async def fake_send_chat(_db, _project_id, chat_id, _card):
        chat_calls.append(chat_id)
        return {"message_id": "mid-chat"}

    monkeypatch.setattr(authz, "get_drive_metadata", fake_metadata)
    monkeypatch.setattr(authz, "send_card_to_open_id", fake_send_open_id)
    monkeypatch.setattr(authz, "send_card_to_chat", fake_send_chat)

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/authorization-request",
        json={},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "authorization_sent"
    assert data["target_mode"] == "owner_direct"
    assert data["sent_targets_count"] == 1
    assert data["failed_targets_count"] == 1
    assert direct_calls == ["ou_fail", "ou_ok"]
    assert chat_calls == []


@pytest.mark.anyio
async def test_authorization_request_direct_failures_fallback_to_default_chat(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_bot(test_project_id)
    run_id = await _seed_run(test_project_id)
    chat_calls: list[str] = []

    async def fake_metadata(*_args, **_kwargs):
        return _metadata(owner_ids=["ou_owner"], creator_ids=["ou_creator"])

    async def fake_send_open_id(_db, _project_id, _open_id, _card):
        raise FeishuApiError("direct failed")

    async def fake_send_chat(_db, _project_id, chat_id, _card):
        chat_calls.append(chat_id)
        return {"message_id": "mid-chat"}

    monkeypatch.setattr(authz, "get_drive_metadata", fake_metadata)
    monkeypatch.setattr(authz, "send_card_to_open_id", fake_send_open_id)
    monkeypatch.setattr(authz, "send_card_to_chat", fake_send_chat)

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/authorization-request",
        json={},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "authorization_sent"
    assert data["target_mode"] == "default_chat"
    assert data["fallback_to_default_chat"] is True
    assert data["sent_targets_count"] == 1
    assert data["failed_targets_count"] == 2
    assert chat_calls == ["oc_default"]


@pytest.mark.anyio
async def test_authorization_request_metadata_unavailable_fallbacks_to_default_chat(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_bot(test_project_id)
    run_id = await _seed_run(test_project_id)
    chat_calls: list[str] = []

    async def fake_metadata(*_args, **_kwargs):
        raise FeishuClientError(FEISHU_METADATA_UNAVAILABLE, "metadata unavailable")

    async def fake_send_chat(_db, _project_id, chat_id, _card):
        chat_calls.append(chat_id)
        return {"message_id": "mid-chat"}

    monkeypatch.setattr(authz, "get_drive_metadata", fake_metadata)
    monkeypatch.setattr(authz, "send_card_to_chat", fake_send_chat)

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/authorization-request",
        json={},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "authorization_sent"
    assert data["target_mode"] == "default_chat"
    assert data["fallback_to_default_chat"] is True
    assert chat_calls == ["oc_default"]


@pytest.mark.anyio
async def test_authorization_request_state_url_does_not_contain_tokens_and_wiki_alias_hash(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wiki_token = "wikcnSecret123"
    real_token = "doccnRealSecret456"
    await _seed_bot(test_project_id)
    run_id = await _seed_run(
        test_project_id,
        source_url=f"https://demo.feishu.cn/wiki/{wiki_token}",
        source_token="",
        source_title="Wiki 来源",
    )
    captured_cards: list[dict[str, object]] = []

    async def fake_resolve(_db, _project_id, _wiki_token):
        assert _wiki_token == wiki_token
        return FeishuWikiNode(
            wiki_token=wiki_token,
            obj_token=real_token,
            obj_type="docx",
            doc_type="docx",
            title="Wiki 来源",
        )

    async def fake_metadata(*_args, **_kwargs):
        return _metadata(owner_ids=[], creator_ids=[], token=real_token)

    async def fake_send_chat(_db, _project_id, _chat_id, card):
        captured_cards.append(card)
        return {"message_id": "mid-chat"}

    monkeypatch.setattr(authz, "resolve_source_evidence_wiki_node", fake_resolve)
    monkeypatch.setattr(authz, "get_drive_metadata", fake_metadata)
    monkeypatch.setattr(authz, "send_card_to_chat", fake_send_chat)

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/authorization-request",
        json={},
    )

    assert response.status_code == 200
    oauth_url = _oauth_url_from_card(captured_cards[0])
    assert wiki_token not in oauth_url
    assert real_token not in oauth_url
    assert "fileTokenSecret123" not in oauth_url

    async with async_session_factory() as session:
        record = (
            await session.execute(select(SourceEvidenceAuthorizationRecord))
        ).scalar_one()
    assert record.source_token_hash == authz.hash_source_token(real_token)
    assert wiki_token not in record.source_token_alias_hashes_json
    assert real_token not in record.source_token_alias_hashes_json
    aliases = json.loads(record.source_token_alias_hashes_json)
    assert aliases[0]["hash"] == authz.hash_source_token(wiki_token)


@pytest.mark.anyio
async def test_existing_unexpired_authorization_sent_does_not_resend(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_bot(test_project_id)
    run_id = await _seed_run(test_project_id)
    await _seed_authorization_record(test_project_id, run_id)

    async def fail_if_send(*_args, **_kwargs):
        raise AssertionError("should not send duplicate card")

    monkeypatch.setattr(authz, "get_drive_metadata", fail_if_send)
    monkeypatch.setattr(authz, "send_card_to_open_id", fail_if_send)
    monkeypatch.setattr(authz, "send_card_to_chat", fail_if_send)

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/authorization-request",
        json={},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "already_sent"


@pytest.mark.anyio
async def test_ready_run_without_permission_failures_returns_already_readable(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_bot(test_project_id)
    run_id = await _seed_run(
        test_project_id,
        status="ready",
        resource_download_status="downloaded",
    )

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("should not send authorization card")

    monkeypatch.setattr(authz, "send_card_to_open_id", fail_if_called)
    monkeypatch.setattr(authz, "send_card_to_chat", fail_if_called)

    response = await auth_client.post(
        f"/api/v1/test-cases/source-evidence-runs/{run_id}/authorization-request",
        json={},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "already_readable"


@pytest.mark.anyio
async def test_reusable_authorization_lookup_returns_existing_authorized_record(
    test_db,
    test_project_id: int,
) -> None:
    await _seed_bot(test_project_id)
    run_id = await _seed_run(test_project_id)
    record_id = await _seed_authorization_record(
        test_project_id,
        run_id,
        status=authz.STATUS_AUTHORIZED,
    )

    async with async_session_factory() as session:
        run = await session.get(SourceEvidenceRunRecord, run_id)
        assert run is not None
        record = await authz.find_reusable_source_evidence_authorization_for_run(
            session,
            project_id=test_project_id,
            run=run,
        )

    assert record is not None
    assert record.id == record_id


@pytest.mark.anyio
async def test_reusable_authorization_lookup_resolves_wiki_to_real_object_token(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wiki_token = "wikcnReuse123"
    real_token = "doccnReuseReal456"
    await _seed_bot(test_project_id)
    run_id = await _seed_run(
        test_project_id,
        source_url=f"https://demo.feishu.cn/wiki/{wiki_token}",
    )
    record_id = await _seed_authorization_record(
        test_project_id,
        run_id,
        status=authz.STATUS_AUTHORIZED,
        source_token=real_token,
    )

    async def fake_resolve(_db, _project_id, _wiki_token):
        assert _wiki_token == wiki_token
        return FeishuWikiNode(
            wiki_token=wiki_token,
            obj_token=real_token,
            obj_type="docx",
            doc_type="docx",
            title="Wiki 来源",
        )

    monkeypatch.setattr(authz, "resolve_source_evidence_wiki_node", fake_resolve)

    async with async_session_factory() as session:
        run = await session.get(SourceEvidenceRunRecord, run_id)
        assert run is not None
        record = await authz.find_reusable_source_evidence_authorization_for_run(
            session,
            project_id=test_project_id,
            run=run,
        )

    assert record is not None
    assert record.id == record_id
    assert record.source_token_hash == authz.hash_source_token(real_token)
    assert record.source_token_hash != authz.hash_source_token(wiki_token)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status,expires_delta,invalidated",
    [
        (authz.STATUS_AUTHORIZATION_SENT, datetime.timedelta(days=90), False),
        (authz.STATUS_AUTHORIZATION_FAILED, datetime.timedelta(days=90), False),
        (authz.STATUS_PENDING_VERIFICATION, datetime.timedelta(days=90), False),
        (authz.STATUS_AUTHORIZED, -datetime.timedelta(minutes=1), False),
        (authz.STATUS_AUTHORIZED, datetime.timedelta(days=90), True),
    ],
)
async def test_reusable_authorization_lookup_ignores_non_reusable_records(
    test_db,
    test_project_id: int,
    status: str,
    expires_delta: datetime.timedelta,
    invalidated: bool,
) -> None:
    await _seed_bot(test_project_id)
    run_id = await _seed_run(test_project_id)
    await _seed_authorization_record(
        test_project_id,
        run_id,
        status=status,
        expires_delta=expires_delta,
        invalidated_at=datetime.datetime.now(datetime.UTC) if invalidated else None,
    )

    async with async_session_factory() as session:
        run = await session.get(SourceEvidenceRunRecord, run_id)
        assert run is not None
        record = await authz.find_reusable_source_evidence_authorization_for_run(
            session,
            project_id=test_project_id,
            run=run,
        )

    assert record is None


@pytest.mark.anyio
async def test_oauth_callback_without_login_authorizes_after_light_verification(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_bot(test_project_id)
    run_id = await _seed_run(test_project_id, source_token=SOURCE_TOKEN)
    state = "state-callback-success"
    record_id = await _seed_authorization_record(test_project_id, run_id, state=state)
    collaborator_calls: list[dict[str, str]] = []
    verify_calls: list[str] = []

    async def fake_exchange(_db, _project_id, code, _callback_url):
        assert code == "oauth-code-once"
        return "user_access_token_once"

    async def fake_user_info(user_access_token):
        assert user_access_token == "user_access_token_once"
        return FeishuOAuthUserInfo(open_id="ou_clicker")

    async def fake_bot_open_id(_db, _project_id):
        return "ou_bot"

    async def fake_add_collaborator(user_access_token, token, bot_open_id, doc_type, *, perm, notify_lark=False):
        collaborator_calls.append(
            {
                "user_access_token": user_access_token,
                "token": token,
                "bot_open_id": bot_open_id,
                "doc_type": doc_type,
                "perm": perm,
            }
        )
        assert notify_lark is False
        return {"is_all_success": True}

    async def fake_json_request(_db, _project_id, _method, path, **_kwargs):
        verify_calls.append(path)
        return {"code": 0, "data": {"items": []}}

    monkeypatch.setattr(authz, "exchange_oauth_code_for_user_token", fake_exchange)
    monkeypatch.setattr(authz, "get_oauth_user_info", fake_user_info)
    monkeypatch.setattr(authz, "get_current_bot_open_id", fake_bot_open_id)
    monkeypatch.setattr(authz, "add_source_document_collaborator", fake_add_collaborator)
    monkeypatch.setattr(authz, "feishu_json_request", fake_json_request)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/test-cases/source-evidence-authorizations/oauth/callback",
            params={"code": "oauth-code-once", "state": state},
        )

    assert response.status_code == 200
    assert "授权已完成" in response.text
    assert collaborator_calls == [
        {
            "user_access_token": "user_access_token_once",
            "token": SOURCE_TOKEN,
            "bot_open_id": "ou_bot",
            "doc_type": "docx",
            "perm": "edit",
        }
    ]
    assert verify_calls == [f"/open-apis/docx/v1/documents/{SOURCE_TOKEN}/blocks"]
    async with async_session_factory() as session:
        record = await session.get(SourceEvidenceAuthorizationRecord, record_id)
    assert record is not None
    assert record.status == "authorized"
    assert record.authorized_by_open_id == "ou_clicker"
    assert record.state_hash is None


@pytest.mark.anyio
async def test_oauth_callback_expired_run_fails_without_adding_collaborator(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_bot(test_project_id)
    run_id = await _seed_run(
        test_project_id,
        source_token=SOURCE_TOKEN,
        expires_delta=-datetime.timedelta(minutes=1),
    )
    state = "state-expired-run"
    record_id = await _seed_authorization_record(test_project_id, run_id, state=state)

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("callback should not add collaborator for expired run")

    monkeypatch.setattr(authz, "add_source_document_collaborator", fail_if_called)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/test-cases/source-evidence-authorizations/oauth/callback",
            params={"code": "oauth-code", "state": state},
        )

    assert response.status_code == 200
    assert "证据已过期" in response.text
    async with async_session_factory() as session:
        record = await session.get(SourceEvidenceAuthorizationRecord, record_id)
    assert record is not None
    assert record.status == "expired"


@pytest.mark.anyio
async def test_callback_error_summary_redacts_sensitive_values(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_bot(test_project_id)
    run_id = await _seed_run(test_project_id, source_token=SOURCE_TOKEN)
    state = "state-redaction"
    record_id = await _seed_authorization_record(test_project_id, run_id, state=state)
    sensitive_message = (
        "app_secret=secret_unit tenant_access_token=tenant_secret "
        "user_access_token=user_secret OAuth code=oauth-code-secret "
        "Authorization: Bearer auth_secret Bearer bearer_secret"
    )

    async def fake_exchange(*_args, **_kwargs):
        return "user_secret"

    async def fake_user_info(*_args, **_kwargs):
        return FeishuOAuthUserInfo(open_id="ou_clicker")

    async def fake_bot_open_id(*_args, **_kwargs):
        return "ou_bot"

    async def fake_add_collaborator(*_args, **_kwargs):
        raise FeishuClientError(FEISHU_API_ERROR, sensitive_message)

    monkeypatch.setattr(authz, "exchange_oauth_code_for_user_token", fake_exchange)
    monkeypatch.setattr(authz, "get_oauth_user_info", fake_user_info)
    monkeypatch.setattr(authz, "get_current_bot_open_id", fake_bot_open_id)
    monkeypatch.setattr(authz, "add_source_document_collaborator", fake_add_collaborator)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/test-cases/source-evidence-authorizations/oauth/callback",
            params={"code": "oauth-code-secret", "state": state},
        )

    assert response.status_code == 200
    async with async_session_factory() as session:
        record = await session.get(SourceEvidenceAuthorizationRecord, record_id)
    assert record is not None
    combined = f"{response.text} {record.last_error_summary}"
    for forbidden in (
        "secret_unit",
        "tenant_secret",
        "user_secret",
        "oauth-code-secret",
        "auth_secret",
        "bearer_secret",
        "app_secret",
        "tenant_access_token",
        "user_access_token",
        "OAuth code",
        "Authorization",
        "Bearer",
    ):
        assert forbidden not in combined
