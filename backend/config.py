"""应用配置定义。"""

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


def _parse_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return int(raw_value.strip())
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数，当前值为：{raw_value}") from exc


def _parse_origins(raw_value: str | None) -> tuple[str, ...]:
    if raw_value is None or not raw_value.strip():
        return ("*",)
    return tuple(origin.strip() for origin in raw_value.split(",") if origin.strip()) or (
        "*",
    )


@dataclass(frozen=True)
class Settings:
    """集中管理服务名、监听地址、数据库、JWT 和运行参数。"""

    app_name: str = "excel-check-backend"
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
        default_factory=lambda: Path(__file__).resolve().parent / ".runtime"
    )
    runtime_upload_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent
        / "backend"
        / ".runtime_uploads"
        / "local_excel"
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
    max_upload_mb: int = field(
        default_factory=lambda: _parse_int_env("MAX_UPLOAD_MB", 50)
    )
    feishu_bot_max_file_mb: int = field(
        default_factory=lambda: _parse_int_env("FEISHU_BOT_MAX_FILE_MB", 30)
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
        default_factory=lambda: Path(__file__).resolve().parent
        / ".runtime"
        / "svn-cache"
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
    svn_url_allowlist: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            host.strip()
            for host in (os.getenv("SVN_URL_ALLOWLIST") or "samosvn").split(",")
            if host.strip()
        )
        or ("samosvn",)
    )
    svn_list_timeout_seconds: int = 30
    svn_subprocess_timeout_seconds: int = 600

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

    @property
    def max_upload_bytes(self) -> int:
        """返回上传文件大小上限（字节）。"""
        return max(1, self.max_upload_mb) * 1024 * 1024

    @property
    def feishu_bot_max_file_bytes(self) -> int:
        """返回飞书机器人单文件推送大小上限（字节）。"""
        return max(1, self.feishu_bot_max_file_mb) * 1024 * 1024


settings = Settings()
