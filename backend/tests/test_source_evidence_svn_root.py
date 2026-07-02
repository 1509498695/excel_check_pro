"""Source Evidence SVN Root admin API tests."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient
import pytest

from backend.app.auth.service import create_access_token, hash_password
from backend.app.database import async_session_factory
from backend.app.models import ProjectQueryRootRecord, User, UserProjectRole
from backend.run import app


async def _create_normal_user_headers(project_id: int) -> dict[str, str]:
    async with async_session_factory() as session:
        user = User(
            username="source_evidence_svn_member",
            hashed_password=hash_password("pwd"),
            is_super_admin=False,
            primary_project_id=project_id,
        )
        session.add(user)
        await session.flush()
        session.add(UserProjectRole(user_id=user.id, project_id=project_id, role="user"))
        await session.commit()
        token = create_access_token(user.id, project_id=project_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_admin_can_save_and_read_source_evidence_svn_roots(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    response = await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/source-evidence-svn-roots",
        json={
            "items": [
                {
                    "alias": "design_docs",
                    "display_name": "策划案 SVN",
                    "svn_url": "https://samosvn/game/design",
                    "enabled": True,
                },
                {
                    "alias": "archive_docs",
                    "display_name": "历史策划",
                    "svn_url": "https://samosvn/game/archive/",
                    "enabled": False,
                },
            ]
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"] == [
        {
            "alias": "design_docs",
            "display_name": "策划案 SVN",
            "svn_url": "https://samosvn/game/design/",
            "enabled": True,
        },
        {
            "alias": "archive_docs",
            "display_name": "历史策划",
            "svn_url": "https://samosvn/game/archive/",
            "enabled": False,
        },
    ]

    read_response = await auth_client.get(
        f"/api/v1/admin/projects/{test_project_id}/source-evidence-svn-roots"
    )
    assert read_response.status_code == 200
    assert read_response.json()["data"] == response.json()["data"]


@pytest.mark.anyio
async def test_source_evidence_svn_roots_reject_non_admin(
    test_project_id: int,
) -> None:
    headers = await _create_normal_user_headers(test_project_id)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    ) as client:
        response = await client.put(
            f"/api/v1/admin/projects/{test_project_id}/source-evidence-svn-roots",
            json={"items": []},
        )

    assert response.status_code == 403


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("items", "message"),
    [
        (
            [
                {
                    "alias": "design",
                    "display_name": "A",
                    "svn_url": "https://samosvn/game/design/",
                    "enabled": True,
                },
                {
                    "alias": "design",
                    "display_name": "B",
                    "svn_url": "https://samosvn/game/other/",
                    "enabled": True,
                },
            ],
            "source_evidence_svn_roots alias 重复：design",
        ),
        (
            [
                {
                    "alias": "bad",
                    "display_name": "Bad",
                    "svn_url": " ",
                    "enabled": True,
                }
            ],
            "source_evidence_svn_roots.svn_url 不能为空：bad",
        ),
        (
            [
                {
                    "alias": "bad",
                    "display_name": "Bad",
                    "svn_url": "file:///tmp/design",
                    "enabled": True,
                }
            ],
            "必须以 http(s):// 开头",
        ),
        (
            [
                {
                    "alias": "bad",
                    "display_name": "Bad",
                    "svn_url": "https://evil.example.com/game/design/",
                    "enabled": True,
                }
            ],
            "不在允许列表",
        ),
    ],
)
async def test_source_evidence_svn_roots_validate_input(
    auth_client: AsyncClient,
    test_project_id: int,
    items: list[dict[str, object]],
    message: str,
) -> None:
    response = await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/source-evidence-svn-roots",
        json={"items": items},
    )

    assert response.status_code == 400
    assert message in response.json()["detail"]


@pytest.mark.anyio
async def test_source_evidence_roots_do_not_replace_remote_query_roots(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    async with async_session_factory() as session:
        session.add(
            ProjectQueryRootRecord(
                project_id=test_project_id,
                alias="game_datas",
                display_name="游戏配置",
                svn_root_url="https://samosvn/game/configs/",
                status="enabled",
            )
        )
        await session.commit()

    response = await auth_client.put(
        f"/api/v1/admin/projects/{test_project_id}/source-evidence-svn-roots",
        json={
            "items": [
                {
                    "alias": "design_docs",
                    "display_name": "策划案 SVN",
                    "svn_url": "https://samosvn/game/design/",
                    "enabled": True,
                }
            ]
        },
    )

    assert response.status_code == 200
    bot_config = await auth_client.get(f"/api/v1/admin/projects/{test_project_id}/feishu-bot")
    assert bot_config.status_code == 200
    assert bot_config.json()["data"]["query_roots"] == [
        {
            "alias": "game_datas",
            "display_name": "游戏配置",
            "svn_url": "https://samosvn/game/configs/",
            "enabled": True,
        }
    ]
