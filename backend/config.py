"""应用配置定义。"""

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


def _is_env_configured(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def _parse_app_env(raw_value: str | None) -> str:
    if raw_value is None or not raw_value.strip():
        return "development"

    normalized_value = raw_value.strip().lower()
    if normalized_value in {"development", "production"}:
        return normalized_value
    raise ValueError(
        f"APP_ENV 仅支持 development 或 production，当前值为：{raw_value}"
    )


def _parse_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return int(raw_value.strip())
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数，当前值为：{raw_value}") from exc


def _parse_non_negative_int_env(name: str, default: int) -> int:
    value = _parse_int_env(name, default)
    if value < 0:
        raise ValueError(f"{name} 不能为负数，当前值为：{value}")
    return value


def _parse_origins(raw_value: str | None) -> tuple[str, ...]:
    if raw_value is None or not raw_value.strip():
        return ("*",)
    return tuple(origin.strip() for origin in raw_value.split(",") if origin.strip()) or (
        "*",
    )


def _parse_bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default

    normalized_value = raw_value.strip().lower()
    if normalized_value in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} 必须是布尔值，当前值为：{raw_value}")


def _parse_path_allowlist(raw_value: str | None) -> tuple[Path, ...]:
    if raw_value is None or not raw_value.strip():
        return ()

    normalized_value = raw_value.replace(";", ",")
    paths: list[Path] = []
    for item in normalized_value.split(","):
        item = item.strip()
        if not item:
            continue
        paths.append(Path(item).expanduser())
    return tuple(paths)


def _parse_path_env(name: str, default: Path) -> Path:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    return Path(raw_value.strip()).expanduser()


def _parse_svn_url_allowlist(raw_value: str | None) -> tuple[str, ...]:
    if raw_value is None or not raw_value.strip():
        return ("samosvn",)
    return tuple(host.strip() for host in raw_value.split(",") if host.strip())


@dataclass(frozen=True)
class Settings:
    """集中管理服务名、监听地址、数据库、JWT 和运行参数。"""

    app_name: str = "excel-check-backend"
    app_env: str = field(default_factory=lambda: _parse_app_env(os.getenv("APP_ENV")))
    debug: bool = False
    host: str = field(
        default_factory=lambda: os.getenv("APP_HOST", "127.0.0.1").strip()
        or "127.0.0.1"
    )
    port: int = field(default_factory=lambda: _parse_int_env("APP_PORT", 8000))
    api_v1_prefix: str = "/api/v1"
    default_thread_pool_size: int = 4
    backend_root: Path = field(default_factory=lambda: Path(__file__).resolve().parent)
    project_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent
    )
    runtime_dir: Path = field(
        default_factory=lambda: _parse_path_env(
            "RUNTIME_DIR",
            Path(__file__).resolve().parent / ".runtime",
        )
    )
    runtime_upload_dir: Path = field(
        default_factory=lambda: _parse_path_env(
            "RUNTIME_UPLOAD_DIR",
            Path(__file__).resolve().parent.parent
            / "backend"
            / ".runtime_uploads"
            / "local_excel",
        )
    )
    source_evidence_dir: Path = field(
        default_factory=lambda: _parse_path_env(
            "SOURCE_EVIDENCE_DIR",
            Path(__file__).resolve().parent / ".runtime" / "source-evidence",
        )
    )
    frontend_dist_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "FRONTEND_DIST_DIR",
                str(Path(__file__).resolve().parent.parent / "frontend" / "dist"),
            )
        )
    )
    cors_allow_origins: tuple[str, ...] = field(
        default_factory=lambda: _parse_origins(os.getenv("CORS_ALLOW_ORIGINS"))
    )
    cors_allow_origins_configured: bool = field(
        default_factory=lambda: _is_env_configured("CORS_ALLOW_ORIGINS")
    )
    local_file_root_allowlist: tuple[Path, ...] = field(
        default_factory=lambda: _parse_path_allowlist(
            os.getenv("LOCAL_FILE_ROOT_ALLOWLIST")
        )
    )
    enable_local_picker: bool = field(
        default_factory=lambda: _parse_bool_env("ENABLE_LOCAL_PICKER", False)
    )
    max_upload_mb: int = field(
        default_factory=lambda: _parse_int_env("MAX_UPLOAD_MB", 50)
    )
    feishu_bot_max_file_mb: int = field(
        default_factory=lambda: _parse_int_env("FEISHU_BOT_MAX_FILE_MB", 30)
    )
    feishu_oauth_callback_url: str = field(
        default_factory=lambda: (os.getenv("FEISHU_OAUTH_CALLBACK_URL") or "").strip()
    )
    feishu_oauth_authorize_url: str = field(
        default_factory=lambda: (
            os.getenv("FEISHU_OAUTH_AUTHORIZE_URL")
            or "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
        ).strip()
    )
    feishu_sheet_oauth_scope: str = field(
        default_factory=lambda: (
            os.getenv("FEISHU_SHEET_OAUTH_SCOPE")
            or "sheets:spreadsheet:readonly wiki:node:read docs:permission.member:create"
        ).strip()
    )
    feishu_source_evidence_oauth_callback_url: str = field(
        default_factory=lambda: (
            os.getenv("FEISHU_SOURCE_EVIDENCE_OAUTH_CALLBACK_URL") or ""
        ).strip()
    )
    feishu_source_evidence_oauth_scope: str = field(
        default_factory=lambda: (
            os.getenv("FEISHU_SOURCE_EVIDENCE_OAUTH_SCOPE") or ""
        ).strip()
    )
    source_evidence_authorization_ttl_days: int = field(
        default_factory=lambda: _parse_non_negative_int_env(
            "SOURCE_EVIDENCE_AUTHORIZATION_TTL_DAYS",
            90,
        )
    )
    fixed_rules_config_path: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent
        / ".runtime"
        / "fixed-rules"
        / "default.json"
    )
    svn_executable: str = field(
        default_factory=lambda: (os.getenv("SVN_EXECUTABLE") or "svn").strip()
        or "svn"
    )
    supported_source_types: tuple[str, ...] = field(
        default_factory=lambda: ("local_excel", "feishu", "svn")
    )
    svn_cache_dir: Path = field(
        default_factory=lambda: _parse_path_env(
            "SVN_CACHE_DIR",
            Path(__file__).resolve().parent / ".runtime" / "svn-cache",
        )
    )
    svn_credentials_path: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent
        / ".runtime"
        / "svn-credentials.json"
    )
    svn_credentials_key_path: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent
        / ".runtime"
        / ".svn-key"
    )
    svn_cache_ttl_seconds: int = 60
    package_items_ai_parse_cache_ttl_seconds: int = 600
    svn_url_allowlist: tuple[str, ...] = field(
        default_factory=lambda: _parse_svn_url_allowlist(
            os.getenv("SVN_URL_ALLOWLIST")
        )
    )
    svn_url_allowlist_configured: bool = field(
        default_factory=lambda: _is_env_configured("SVN_URL_ALLOWLIST")
    )
    svn_list_timeout_seconds: int = 30
    svn_subprocess_timeout_seconds: int = 600
    upload_retention_days: int = field(
        default_factory=lambda: _parse_non_negative_int_env(
            "UPLOAD_RETENTION_DAYS",
            30,
        )
    )
    svn_cache_retention_days: int = field(
        default_factory=lambda: _parse_non_negative_int_env(
            "SVN_CACHE_RETENTION_DAYS",
            30,
        )
    )
    execution_result_retention_days: int = field(
        default_factory=lambda: _parse_non_negative_int_env(
            "EXECUTION_RESULT_RETENTION_DAYS",
            90,
        )
    )
    source_evidence_ttl_days: int = field(
        default_factory=lambda: _parse_non_negative_int_env(
            "SOURCE_EVIDENCE_TTL_DAYS",
            7,
        )
    )
    source_evidence_soffice_executable: str = field(
        default_factory=lambda: (
            os.getenv("SOURCE_EVIDENCE_SOFFICE_EXECUTABLE") or ""
        ).strip()
    )
    source_evidence_xls_convert_timeout_seconds: int = field(
        default_factory=lambda: _parse_non_negative_int_env(
            "SOURCE_EVIDENCE_XLS_CONVERT_TIMEOUT_SECONDS",
            60,
        )
    )
    log_retention_days: int = field(
        default_factory=lambda: _parse_non_negative_int_env(
            "LOG_RETENTION_DAYS",
            14,
        )
    )

    # --- 数据库 ---
    db_url: str = field(
        default_factory=lambda: os.getenv("DB_URL") or "sqlite+aiosqlite:///"
        + str(
            Path(__file__).resolve().parent / ".runtime" / "excel_check.db"
        )
    )

    # --- JWT ---
    jwt_secret_key: str = field(
        default_factory=lambda: os.getenv("JWT_SECRET_KEY") or secrets.token_urlsafe(32)
    )
    jwt_secret_key_configured: bool = field(
        default_factory=lambda: bool((os.getenv("JWT_SECRET_KEY") or "").strip())
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 小时

    # --- 超级管理员 ---
    default_super_admin_username: str = "admin"
    default_super_admin_password: str = field(
        default_factory=lambda: os.getenv("DEFAULT_SUPER_ADMIN_PASSWORD") or "123456"
    )
    default_super_admin_password_configured: bool = field(
        default_factory=lambda: bool(
            (os.getenv("DEFAULT_SUPER_ADMIN_PASSWORD") or "").strip()
        )
    )

    def __post_init__(self) -> None:
        self.validate_production_safety()

    def validate_production_safety(self) -> None:
        """生产环境启动前强制校验关键安全配置。"""
        if self.app_env != "production":
            return

        errors: list[str] = []
        if not self.jwt_secret_key_configured:
            errors.append("JWT_SECRET_KEY 必须显式提供")
        if not self.default_super_admin_password_configured:
            errors.append("DEFAULT_SUPER_ADMIN_PASSWORD 必须显式提供")
        if not self.cors_allow_origins_configured:
            errors.append("CORS_ALLOW_ORIGINS 必须显式提供")
        if not self.svn_url_allowlist_configured:
            errors.append("SVN_URL_ALLOWLIST 必须显式提供")
        if self.default_super_admin_password.strip() == "123456":
            errors.append("DEFAULT_SUPER_ADMIN_PASSWORD 不能使用默认密码 123456")
        if "*" in self.cors_allow_origins:
            errors.append("CORS_ALLOW_ORIGINS 在 production 模式不能包含 *")
        if not self.svn_url_allowlist:
            errors.append("SVN_URL_ALLOWLIST 至少配置一个 SVN host")

        if errors:
            raise ValueError("生产环境配置不安全，启动已中止：" + "；".join(errors))

    @property
    def max_upload_bytes(self) -> int:
        """返回上传文件大小上限（字节）。"""
        return max(1, self.max_upload_mb) * 1024 * 1024

    @property
    def feishu_bot_max_file_bytes(self) -> int:
        """返回飞书机器人单文件推送大小上限（字节）。"""
        return max(1, self.feishu_bot_max_file_mb) * 1024 * 1024


settings = Settings()
