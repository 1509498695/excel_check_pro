"""ORM 模型定义：用户、项目、角色关联、业务数据记录。"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from backend.app.database import Base


SOURCE_EVIDENCE_DEFAULT_TTL_DAYS = 7
SOURCE_EVIDENCE_AUTHORIZATION_DEFAULT_TTL_DAYS = 90
TEST_CASE_GENERATION_RUN_DEFAULT_TTL_DAYS = 7

TEST_CASE_GENERATION_RUN_STATUSES = (
    "queued",
    "reading",
    "chunking",
    "extracting_atoms",
    "merging_atoms",
    "blueprinting",
    "generating_cases",
    "auditing_coverage",
    "supplementing",
    "auditing_quality",
    "repairing_cases",
    "rendering_artifacts",
    "completed",
    "partial_completed",
    "failed",
    "cancelled",
    "expired",
)


def _default_source_evidence_expires_at() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        days=SOURCE_EVIDENCE_DEFAULT_TTL_DAYS,
    )


def _default_source_evidence_authorization_expires_at() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        days=SOURCE_EVIDENCE_AUTHORIZATION_DEFAULT_TTL_DAYS,
    )


def _default_test_case_generation_run_expires_at() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        days=TEST_CASE_GENERATION_RUN_DEFAULT_TTL_DAYS,
    )


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
    """通用规则配置当前文档（按 project_id + rule_family + query_type 隔离）。"""

    __tablename__ = "rule_configs"
    __table_args__ = (
        Index(
            "uq_rule_configs_project_family_query_type",
            "project_id",
            "rule_family",
            "query_type",
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
    query_type: Mapped[str] = mapped_column(String(100), nullable=False)
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
            "uq_rule_config_versions_rule_config_version",
            "rule_config_id",
            "version",
            unique=True,
        ),
        Index("ix_rule_config_versions_rule_config_id", "rule_config_id"),
        Index(
            "ix_rule_config_versions_project_family",
            "project_id",
            "rule_family",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rule_config_id: Mapped[int] = mapped_column(
        ForeignKey("rule_configs.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_family: Mapped[str] = mapped_column(String(64), nullable=False)
    query_type: Mapped[str] = mapped_column(String(100), nullable=False)
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


class ProjectSourceEvidenceSvnRootRecord(Base):
    """项目级 Source Evidence SVN 文件读取边界。"""

    __tablename__ = "project_source_evidence_svn_roots"
    __table_args__ = (
        Index(
            "uq_project_source_evidence_svn_roots_project_alias",
            "project_id",
            "alias",
            unique=True,
        ),
        Index(
            "ix_project_source_evidence_svn_roots_project_status",
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


class ProjectVisionAiCredentialRecord(Base):
    """项目级 Vision AI 模型凭据配置（按 project_id 隔离）。"""

    __tablename__ = "project_vision_ai_credentials"
    __table_args__ = (
        Index(
            "ix_project_vision_ai_credentials_project_id",
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


class TestCaseReferenceCategoryRecord(Base):
    """用例生成 V1 参考案例分类（按 project_id 隔离）。"""

    __tablename__ = "test_case_reference_categories"
    __table_args__ = (
        Index(
            "uq_test_case_reference_categories_project_name_key",
            "project_id",
            "name_key",
            unique=True,
        ),
        Index("ix_test_case_reference_categories_project_id", "project_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    name_key: Mapped[str] = mapped_column(String(80), nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @validates("name")
    def _sync_name_key(self, _key: str, value: str) -> str:
        self.name_key = value.strip()
        return value


class TestCaseReferenceFileRecord(Base):
    """用例生成 V1 参考案例文件记录。

    active 状态由 deleted_at 是否为空决定。删除成功后保留审计行，但清空
    storage_path、profile_json 和推荐主参考标记。
    """

    __tablename__ = "test_case_reference_files"
    __table_args__ = (
        Index("ix_test_case_reference_files_project_id", "project_id"),
        Index("ix_test_case_reference_files_category_id", "category_id"),
        Index(
            "ix_test_case_reference_files_project_category",
            "project_id",
            "category_id",
        ),
        Index(
            "ix_test_case_reference_files_project_filename",
            "project_id",
            "original_filename",
        ),
        Index(
            "ix_test_case_reference_files_project_recommended",
            "project_id",
            "category_id",
            "is_recommended_primary",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_case_reference_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), default="")
    suffix: Mapped[str] = mapped_column(String(16), default="")
    size_bytes: Mapped[int] = mapped_column(default=0)
    storage_path: Mapped[str] = mapped_column(Text, default="")
    profile_json: Mapped[str] = mapped_column(Text, default="")
    is_recommended_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SourceEvidenceAuthorizationRecord(Base):
    """Source Evidence 飞书源文档授权复用记录。

    本表只保存哈希、状态和最小审计信息，不保存完整 URL、源 token、
    wiki token、file token、OAuth code 或 user_access_token。
    """

    __tablename__ = "source_evidence_authorizations"
    __table_args__ = (
        Index(
            "uq_source_evidence_authorizations_project_app_source_perm",
            "project_id",
            "app_id",
            "source_token_hash",
            "permission",
            unique=True,
        ),
        Index(
            "uq_source_evidence_authorizations_state_hash",
            "state_hash",
            unique=True,
        ),
        Index(
            "ix_source_evidence_authorizations_project_status_expires",
            "project_id",
            "status",
            "expires_at",
        ),
        Index(
            "ix_source_evidence_authorizations_project_originating_run",
            "project_id",
            "originating_run_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(32), default="")
    permission: Mapped[str] = mapped_column(String(16), default="edit")
    source_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_token_alias_hashes_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="authorization_sent")
    state_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    state_expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    originating_run_id: Mapped[int | None] = mapped_column(nullable=True)
    target_mode: Mapped[str] = mapped_column(String(32), default="not_sent")
    sent_targets_count: Mapped[int] = mapped_column(default=0)
    failed_targets_count: Mapped[int] = mapped_column(default=0)
    owner_candidates_truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    authorized_by_open_id: Mapped[str] = mapped_column(String(128), default="")
    authorized_by_display_name_masked: Mapped[str] = mapped_column(String(128), default="")
    authorized_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=_default_source_evidence_authorization_expires_at,
        nullable=False,
    )
    invalidated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    invalidated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_error_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SourceEvidenceRunRecord(Base):
    """用例生成 Source Evidence 读取 run。

    本表只保存读取过程的生命周期、TTL 和最小审计字段，不保存蓝图、用例、
    prompt 或 provider response。
    """

    __tablename__ = "source_evidence_runs"
    __table_args__ = (
        Index("ix_source_evidence_runs_project_id", "project_id"),
        Index("ix_source_evidence_runs_status", "status"),
        Index("ix_source_evidence_runs_project_status", "project_id", "status"),
        Index("ix_source_evidence_runs_project_expires", "project_id", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(String(32), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    source_token: Mapped[str] = mapped_column(Text, default="")
    source_identifier: Mapped[str] = mapped_column(String(255), default="")
    source_title: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="reading")
    storage_path: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=_default_source_evidence_expires_at,
        nullable=False,
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    cleaned_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_summary: Mapped[str] = mapped_column(Text, default="")
    raw_manifest_json: Mapped[str] = mapped_column(Text, default="{}")
    minimal_audit_json: Mapped[str] = mapped_column(Text, default="{}")
    cleaned_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    resources: Mapped[list["SourceEvidenceResourceRecord"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
    visual_observations: Mapped[list["SourceEvidenceVisualObservationRecord"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class SourceEvidenceResourceRecord(Base):
    """Source Evidence run 关联的资源文件元数据。"""

    __tablename__ = "source_evidence_resources"
    __table_args__ = (
        Index("ix_source_evidence_resources_run_id", "run_id"),
        Index("ix_source_evidence_resources_project_id", "project_id"),
        Index("ix_source_evidence_resources_status", "status"),
        Index("ix_source_evidence_resources_project_status", "project_id", "status"),
        Index("ix_source_evidence_resources_run_ref", "run_id", "ref"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("source_evidence_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    ref: Mapped[str] = mapped_column(String(128), default="")
    resource_type: Mapped[str] = mapped_column(String(32), default="")
    position: Mapped[str] = mapped_column(Text, default="")
    filename: Mapped[str] = mapped_column(String(255), default="")
    file_token: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    download_status: Mapped[str] = mapped_column(String(32), default="pending")
    local_path: Mapped[str] = mapped_column(Text, default="")
    mime_type: Mapped[str] = mapped_column(String(128), default="")
    observation_json: Mapped[str] = mapped_column(Text, default="")
    visual_packet_path: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    cleaned_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    run: Mapped[SourceEvidenceRunRecord] = relationship(back_populates="resources")


class SourceEvidenceVisualObservationRecord(Base):
    """Source Evidence 视觉 observation / adopted evidence 轻量索引。"""

    __tablename__ = "source_evidence_visual_observations"
    __table_args__ = (
        Index("ix_source_evidence_visual_observations_run_id", "run_id"),
        Index("ix_source_evidence_visual_observations_project_id", "project_id"),
        Index("ix_source_evidence_visual_observations_status", "status"),
        Index(
            "ix_source_evidence_visual_observations_project_status",
            "project_id",
            "status",
        ),
        Index(
            "uq_source_evidence_visual_observations_run_ref",
            "run_id",
            "ref",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("source_evidence_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    resource_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_evidence_resources.id", ondelete="SET NULL"),
        nullable=True,
    )
    ref: Mapped[str] = mapped_column(String(128), default="")
    position: Mapped[str] = mapped_column(Text, default="")
    filename: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="observed")
    observation_path: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    adopted_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    adopted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cleaned_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    run: Mapped[SourceEvidenceRunRecord] = relationship(back_populates="visual_observations")


class TestCaseGenerationRunRecord(Base):
    """用例生成 V3 全量异步 Generation Run。

    只保存运行状态、输入选择和结构化结果摘要，不保存 raw prompt 或 provider response。
    """

    __tablename__ = "test_case_generation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'queued', 'reading', 'chunking', 'extracting_atoms', "
                "'merging_atoms', 'blueprinting', 'generating_cases', "
                "'auditing_coverage', 'supplementing', 'auditing_quality', "
                "'repairing_cases', 'rendering_artifacts', 'completed', "
            "'partial_completed', 'failed', 'cancelled', 'expired'"
            ")",
            name="ck_test_case_generation_runs_status",
        ),
        Index("ix_test_case_generation_runs_project_id", "project_id"),
        Index("ix_test_case_generation_runs_status", "status"),
        Index("ix_test_case_generation_runs_project_status", "project_id", "status"),
        Index("ix_test_case_generation_runs_project_expires", "project_id", "expires_at"),
        Index(
            "ix_test_case_generation_runs_source_evidence_run",
            "source_evidence_run_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_evidence_run_id: Mapped[int] = mapped_column(
        ForeignKey("source_evidence_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    cancelled_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    planning_sheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reference_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    primary_reference_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_case_reference_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    primary_reference_sheet_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    strict_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    total_chunks: Mapped[int] = mapped_column(default=0)
    completed_chunks: Mapped[int] = mapped_column(default=0)
    failed_chunks: Mapped[int] = mapped_column(default=0)
    atom_count: Mapped[int] = mapped_column(default=0)
    case_count: Mapped[int] = mapped_column(default=0)
    warning_count: Mapped[int] = mapped_column(default=0)
    error_summary: Mapped[str] = mapped_column(Text, default="")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    stage_payload_json: Mapped[str] = mapped_column(Text, default="{}")
    minimal_audit_json: Mapped[str] = mapped_column(Text, default="{}")
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=_default_test_case_generation_run_expires_at,
        nullable=False,
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancelled_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expired_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cleaned_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chunks: Mapped[list["TestCaseGenerationChunkRecord"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
    atoms: Mapped[list["TestCaseRequirementAtomRecord"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
    cases: Mapped[list["TestCaseGenerationCaseRecord"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
    coverage_audits: Mapped[list["TestCaseCoverageAuditRecord"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class TestCaseGenerationChunkRecord(Base):
    """Generation Run 中的策划案 chunk 处理状态。"""

    __tablename__ = "test_case_generation_chunks"
    __table_args__ = (
        Index(
            "uq_test_case_generation_chunks_run_chunk_index",
            "run_id",
            "chunk_index",
            unique=True,
        ),
        Index("ix_test_case_generation_chunks_run_id", "run_id"),
        Index("ix_test_case_generation_chunks_project_id", "project_id"),
        Index("ix_test_case_generation_chunks_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("test_case_generation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    source_row_start: Mapped[int | None] = mapped_column(nullable=True)
    source_row_end: Mapped[int | None] = mapped_column(nullable=True)
    source_column_start: Mapped[int | None] = mapped_column(nullable=True)
    source_column_end: Mapped[int | None] = mapped_column(nullable=True)
    title_hint: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    retry_count: Mapped[int] = mapped_column(default=0)
    error_summary: Mapped[str] = mapped_column(Text, default="")
    structure_hints_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    run: Mapped[TestCaseGenerationRunRecord] = relationship(back_populates="chunks")


class TestCaseRequirementAtomRecord(Base):
    """V3 从策划案 chunk 中提取并合并后的需求原子。"""

    __tablename__ = "test_case_requirement_atoms"
    __table_args__ = (
        Index(
            "uq_test_case_requirement_atoms_run_atom_id",
            "run_id",
            "atom_id",
            unique=True,
        ),
        Index("ix_test_case_requirement_atoms_run_id", "run_id"),
        Index("ix_test_case_requirement_atoms_project_id", "project_id"),
        Index("ix_test_case_requirement_atoms_project_type", "project_id", "atom_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("test_case_generation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_case_generation_chunks.id", ondelete="SET NULL"),
        nullable=True,
    )
    atom_id: Mapped[str] = mapped_column(String(64), nullable=False)
    atom_type: Mapped[str] = mapped_column(String(32), default="requirement")
    requirement_text: Mapped[str] = mapped_column(Text, default="")
    source_sheet_name: Mapped[str] = mapped_column(String(255), default="")
    source_row_start: Mapped[int | None] = mapped_column(nullable=True)
    source_row_end: Mapped[int | None] = mapped_column(nullable=True)
    source_columns_json: Mapped[str] = mapped_column(Text, default="[]")
    cell_excerpt: Mapped[str] = mapped_column(Text, default="")
    visual_evidence_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    coverage_status: Mapped[str] = mapped_column(String(32), default="unmapped")
    merge_group_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    run: Mapped[TestCaseGenerationRunRecord] = relationship(back_populates="atoms")


class TestCaseGenerationCaseRecord(Base):
    """V3 生成的结构化用例行。"""

    __tablename__ = "test_case_generation_cases"
    __table_args__ = (
        Index(
            "uq_test_case_generation_cases_run_case_id",
            "run_id",
            "case_id",
            unique=True,
        ),
        Index("ix_test_case_generation_cases_run_id", "run_id"),
        Index("ix_test_case_generation_cases_project_id", "project_id"),
        Index("ix_test_case_generation_cases_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("test_case_generation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(String(64), nullable=False)
    fields_json: Mapped[str] = mapped_column(Text, default="{}")
    atom_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="official")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    run: Mapped[TestCaseGenerationRunRecord] = relationship(back_populates="cases")


class TestCaseCoverageAuditRecord(Base):
    """V3 覆盖率审计摘要。"""

    __tablename__ = "test_case_coverage_audits"
    __table_args__ = (
        Index("uq_test_case_coverage_audits_run_id", "run_id", unique=True),
        Index("ix_test_case_coverage_audits_project_id", "project_id"),
        Index("ix_test_case_coverage_audits_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("test_case_generation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), default="pending")
    total_atoms: Mapped[int] = mapped_column(default=0)
    covered_atoms: Mapped[int] = mapped_column(default=0)
    uncovered_atoms: Mapped[int] = mapped_column(default=0)
    unfounded_case_count: Mapped[int] = mapped_column(default=0)
    failed_chunk_count: Mapped[int] = mapped_column(default=0)
    uncovered_atom_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    unfounded_candidates_json: Mapped[str] = mapped_column(Text, default="[]")
    supplement_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    export_limitations_json: Mapped[str] = mapped_column(Text, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    run: Mapped[TestCaseGenerationRunRecord] = relationship(back_populates="coverage_audits")
