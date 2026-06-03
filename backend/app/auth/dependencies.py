"""FastAPI 依赖：从请求中提取当前用户和项目上下文。"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.service import (
    decode_access_token,
    get_user_with_roles,
    resolve_active_project_id,
)
from backend.app.database import get_db
from backend.app.models import User

_bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUserContext:
    """封装请求级别的用户身份与项目上下文。"""

    def __init__(
        self,
        user: User,
        project_id: int | None,
        requested_project_id: int | None = None,
    ):
        self.user = user
        self.project_id = project_id
        self.requested_project_id = requested_project_id

    @property
    def user_id(self) -> int:
        return self.user.id

    @property
    def is_super_admin(self) -> bool:
        return self.user.is_super_admin

    def role_in_project(self, project_id: int) -> str | None:
        """返回用户在指定项目中的角色，不存在则为 None。"""
        for r in self.user.roles:
            if r.project_id == project_id:
                return r.role
        return None

    def require_project(self) -> int:
        """要求当前请求携带有效 project_id，否则抛出 403。"""
        if self.project_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="请先选择一个项目",
            )
        return self.project_id

    def require_project_member(self) -> int:
        """要求用户属于当前项目。"""
        pid = self.require_project()
        if self.is_super_admin:
            return pid
        role = self.role_in_project(pid)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您不属于当前项目",
            )
        return pid

    def require_strict_project_member(self) -> int:
        """要求当前 Token 指定的项目也必须是用户所属项目。"""
        pid = self.require_project_member()
        if self.is_super_admin or self.requested_project_id is None:
            return pid
        if self.requested_project_id != pid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您不属于当前项目",
            )
        return pid

    def require_project_admin(self) -> int:
        """要求用户是项目管理员或超级管理员。"""
        pid = self.require_project()
        if self.is_super_admin:
            return pid
        role = self.role_in_project(pid)
        if role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要项目管理员权限",
            )
        return pid

    def require_super_admin(self) -> None:
        """要求超级管理员权限。"""
        if not self.is_super_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要超级管理员权限",
            )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUserContext:
    """从 Bearer Token 中解析当前用户。"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = int(payload["sub"])
    project_id = payload.get("pid")

    user = await get_user_with_roles(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )

    resolved_project_id = resolve_active_project_id(user, project_id)
    return CurrentUserContext(
        user=user,
        project_id=resolved_project_id,
        requested_project_id=project_id,
    )


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUserContext | None:
    """可选认证：未携带 Token 时返回 None，不拦截请求。"""
    if credentials is None:
        return None

    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError:
        return None

    user_id = int(payload["sub"])
    project_id = payload.get("pid")
    user = await get_user_with_roles(db, user_id)
    if user is None:
        return None

    resolved_project_id = resolve_active_project_id(user, project_id)
    return CurrentUserContext(
        user=user,
        project_id=resolved_project_id,
        requested_project_id=project_id,
    )
