"""ORM 模型定义：用户、项目、角色关联、业务数据记录。"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class Project(Base):
    """项目表。"""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    members: Mapped[list[UserProjectRole]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class User(Base):
    """用户表。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    is_super_admin: Mapped[bool] = mapped_column(default=False)
    primary_project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    roles: Mapped[list[UserProjectRole]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserProjectRole(Base):
    """用户-项目-角色关联表。"""

    __tablename__ = "user_project_roles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(32), default="user")
    joined_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="roles")
    project: Mapped[Project] = relationship(back_populates="members")


class FixedRulesConfigRecord(Base):
    """固定规则配置持久化记录（按 project_id 隔离）。"""

    __tablename__ = "fixed_rules_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RuleConfigRecord(Base):
    """通用规则配置当前文档（按 project_id + rule_family 隔离）。"""

    __tablename__ = "rule_configs"
    __table_args__ = (
        Index(
            "uq_rule_configs_project_family",
            "project_id",
            "rule_family",
            unique=True,
        ),
        Index("ix_rule_configs_project_id", "project_id"),
        Index("ix_rule_configs_rule_family", "rule_family"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_family: Mapped[str] = mapped_column(String(64), nullable=False)
    content_md: Mapped[str] = mapped_column(Text, default="")
    parsed_config_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    draft_version: Mapped[int] = mapped_column(default=0)
    published_version: Mapped[int | None] = mapped_column(nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    published_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    published_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    optimistic_lock_version: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RuleConfigVersionRecord(Base):
    """通用规则配置版本历史。"""

    __tablename__ = "rule_config_versions"
    __table_args__ = (
        Index(
            "uq_rule_config_versions_project_family_version",
            "project_id",
            "rule_family",
            "version",
            unique=True,
        ),
        Index(
            "ix_rule_config_versions_project_family",
            "project_id",
            "rule_family",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_family: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    content_md: Mapped[str] = mapped_column(Text, default="")
    parsed_config_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    operator: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ProjectQueryRootRecord(Base):
    """项目级配置表查询数据根（query_roots）。"""

    __tablename__ = "project_query_roots"
    __table_args__ = (
        Index(
            "uq_project_query_roots_project_alias",
            "project_id",
            "alias",
            unique=True,
        ),
        Index(
            "ix_project_query_roots_project_status",
            "project_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    svn_root_url: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="enabled", index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProjectSvnCredentialRecord(Base):
    """项目级 SVN 凭据配置（按 project_id 隔离）。"""

    __tablename__ = "project_svn_credentials"
    __table_args__ = (
        Index(
            "ix_project_svn_credentials_project_id",
            "project_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    username: Mapped[str] = mapped_column(String(128), default="")
    password_cipher: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProjectAiCredentialRecord(Base):
    """项目级 AI 模型凭据配置（按 project_id 隔离）。"""

    __tablename__ = "project_ai_credentials"
    __table_args__ = (
        Index(
            "ix_project_ai_credentials_project_id",
            "project_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_preset: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    encrypted_api_key: Mapped[str] = mapped_column(Text, default="")
    extra_headers_json: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_match_threshold: Mapped[float] = mapped_column(Float, default=0.9)
    candidate_threshold: Mapped[float] = mapped_column(Float, default=0.6)
    max_candidates: Mapped[int] = mapped_column(default=10)
    last_test_status: Mapped[str] = mapped_column(String(32), default="")
    last_test_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_test_error_summary: Mapped[str] = mapped_column(Text, default="")
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkbenchConfigRecord(Base):
    """工作台配置持久化记录（按 project_id + user_id 隔离）。"""

    __tablename__ = "workbench_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExecutionRunRecord(Base):
    """执行任务与执行结果主记录。"""

    __tablename__ = "execution_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    execution_mode: Mapped[str] = mapped_column(String(16), default="sync", index=True)
    status: Mapped[str] = mapped_column(String(16), default="success", index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    total_results: Mapped[int] = mapped_column(default=0)
    execution_time_ms: Mapped[int] = mapped_column(default=0)
    total_rows_scanned: Mapped[int] = mapped_column(default=0)
    failed_sources_json: Mapped[str] = mapped_column(Text, default="[]")
    error_message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    items: Mapped[list["ExecutionResultItemRecord"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ExecutionResultItemRecord(Base):
    """单条异常结果记录。"""

    __tablename__ = "execution_result_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("execution_runs.id", ondelete="CASCADE"), index=True
    )
    sort_index: Mapped[int] = mapped_column(index=True)
    level: Mapped[str] = mapped_column(String(32), default="info")
    rule_name: Mapped[str] = mapped_column(String(255), default="")
    location: Mapped[str] = mapped_column(Text, default="")
    row_index: Mapped[int] = mapped_column(default=0)
    raw_value_json: Mapped[str] = mapped_column(Text, default="null")
    display_value_json: Mapped[str] = mapped_column(Text, default="null")
    extra_json: Mapped[str] = mapped_column(Text, default="{}")
    message: Mapped[str] = mapped_column(Text, default="")

    run: Mapped[ExecutionRunRecord] = relationship(back_populates="items")


class FeishuBotConfigRecord(Base):
    """项目级飞书自建应用机器人配置（按 project_id 隔离，一项目一记录）。

    长连接版本字段精简：只保留 app_id / app_secret_cipher / default_chat_id /
    allowed_open_ids；事件回调期使用的 verification_token / encrypt_key 不再需要。
    """

    __tablename__ = "feishu_bot_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    app_id: Mapped[str] = mapped_column(String(64), default="")
    app_secret_cipher: Mapped[str] = mapped_column(Text, default="")
    default_chat_id: Mapped[str] = mapped_column(String(128), default="")
    # 触发权限白名单：飞书 open_id 列表，逗号分隔字符串落库；空串视为放开。
    allowed_open_ids: Mapped[str] = mapped_column(Text, default="")
    # 机器人下载根目录与后缀白名单：JSON 数组字符串，运行时解析后使用。
    local_download_roots: Mapped[str] = mapped_column(Text, default="[]")
    svn_download_roots: Mapped[str] = mapped_column(Text, default="[]")
    allowed_download_suffixes: Mapped[str] = mapped_column(
        Text,
        default='[".xls",".xlsx",".csv",".json",".xml",".txt"]',
    )
    auto_match_threshold: Mapped[float] = mapped_column(Float, default=0.9)
    candidate_threshold: Mapped[float] = mapped_column(Float, default=0.6)
    max_candidates: Mapped[int] = mapped_column(default=10)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FeishuBotBoundChatRecord(Base):
    """项目级飞书机器人绑定群，一个 chat_id 只能绑定一个项目。"""

    __tablename__ = "feishu_bot_bound_chats"
    __table_args__ = (
        Index("ix_feishu_bot_bound_chats_project_id", "project_id"),
        Index("uq_feishu_bot_bound_chats_chat_id", "chat_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    chat_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FeishuSheetAuthorizationRecord(Base):
    """飞书电子表格授权记录。

    同一项目内同一个 spreadsheet_token 允许被多个 source_id 复用，因此不对
    project_id + spreadsheet_token 建唯一索引。
    """

    __tablename__ = "feishu_sheet_authorizations"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "source_id",
            name="uq_feishu_sheet_auth_project_source",
        ),
        Index(
            "ix_feishu_sheet_auth_project_token",
            "project_id",
            "spreadsheet_token",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    spreadsheet_token: Mapped[str] = mapped_column(
        String(128),
        index=True,
        nullable=False,
    )
    sheet_url: Mapped[str] = mapped_column(Text, default="")
    sheet_title: Mapped[str] = mapped_column(String(255), default="")
    authorized_by_open_id: Mapped[str] = mapped_column(String(128), default="")
    bot_open_id: Mapped[str] = mapped_column(String(128), default="")
    chat_id: Mapped[str] = mapped_column(String(128), default="")
    message_id: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="authorized", index=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    state_hash: Mapped[str] = mapped_column(String(128), default="")
    state_expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    authorized_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
