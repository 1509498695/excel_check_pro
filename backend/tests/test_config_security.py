"""生产环境安全配置校验测试。"""

from __future__ import annotations

import pytest

from backend.config import Settings


SECURITY_ENV_KEYS = (
    "APP_ENV",
    "JWT_SECRET_KEY",
    "DEFAULT_SUPER_ADMIN_PASSWORD",
    "CORS_ALLOW_ORIGINS",
    "SVN_URL_ALLOWLIST",
)


def _clear_security_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in SECURITY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _set_valid_production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "production-jwt-secret")
    monkeypatch.setenv("DEFAULT_SUPER_ADMIN_PASSWORD", "strong-admin-password")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://excel-check.example.com")
    monkeypatch.setenv("SVN_URL_ALLOWLIST", "samosvn")


def test_app_env_defaults_to_development(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_security_env(monkeypatch)

    settings = Settings()

    assert settings.app_env == "development"
    assert settings.default_super_admin_password == "123456"
    assert settings.cors_allow_origins == ("*",)
    assert settings.svn_url_allowlist == ("samosvn",)


def test_development_keeps_convenient_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_security_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")

    settings = Settings()

    assert settings.app_env == "development"
    assert settings.jwt_secret_key
    assert settings.default_super_admin_password == "123456"
    assert settings.cors_allow_origins == ("*",)


def test_production_requires_explicit_security_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_security_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(ValueError) as exc_info:
        Settings()

    message = str(exc_info.value)
    assert "JWT_SECRET_KEY" in message
    assert "DEFAULT_SUPER_ADMIN_PASSWORD" in message
    assert "CORS_ALLOW_ORIGINS" in message
    assert "SVN_URL_ALLOWLIST" in message


def test_production_rejects_default_admin_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_security_env(monkeypatch)
    _set_valid_production_env(monkeypatch)
    monkeypatch.setenv("DEFAULT_SUPER_ADMIN_PASSWORD", "123456")

    with pytest.raises(ValueError) as exc_info:
        Settings()

    assert "DEFAULT_SUPER_ADMIN_PASSWORD 不能使用默认密码 123456" in str(
        exc_info.value
    )


def test_production_rejects_wildcard_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_security_env(monkeypatch)
    _set_valid_production_env(monkeypatch)
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")

    with pytest.raises(ValueError) as exc_info:
        Settings()

    assert "CORS_ALLOW_ORIGINS 在 production 模式不能包含 *" in str(exc_info.value)


def test_production_accepts_explicit_safe_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_security_env(monkeypatch)
    _set_valid_production_env(monkeypatch)

    settings = Settings()

    assert settings.app_env == "production"
    assert settings.jwt_secret_key_configured is True
    assert settings.default_super_admin_password_configured is True
    assert settings.cors_allow_origins_configured is True
    assert settings.svn_url_allowlist_configured is True
    assert settings.cors_allow_origins == ("https://excel-check.example.com",)
    assert settings.svn_url_allowlist == ("samosvn",)


def test_app_env_rejects_unknown_value(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_security_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "prod")

    with pytest.raises(ValueError) as exc_info:
        Settings()

    assert "APP_ENV 仅支持 development 或 production" in str(exc_info.value)
