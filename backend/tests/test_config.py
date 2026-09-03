"""Tests for environment-driven configuration."""

from app.core.config import Settings
from app.schemas.health import HealthResponse


def test_defaults_are_safe():
    settings = Settings()
    assert settings.service_name == "payscape-x"
    assert settings.app_env == "development"
    assert settings.app_version == "0.1.0"
    # Default database target is PostgreSQL (local development only).
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.cors_origin_list == ["http://localhost:3000"]
    assert settings.demo_mode is True


def test_environment_overrides(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://svc:secret@db.internal:5432/prod")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com, https://ops.example.com")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("DEMO_MODE", "false")

    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://svc:secret@db.internal:5432/prod"
    assert settings.cors_origin_list == ["https://app.example.com", "https://ops.example.com"]
    assert settings.log_level == "DEBUG"
    assert settings.app_env == "staging"
    assert settings.demo_mode is False


def test_cors_origins_are_stripped(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", " http://localhost:3000 , http://localhost:3001 ")
    settings = Settings()
    assert settings.cors_origin_list == ["http://localhost:3000", "http://localhost:3001"]


def test_api_schemas_never_expose_credentials():
    """The public API surface must not leak database credentials."""
    fields = set(HealthResponse.model_fields)
    assert fields == {"status", "service", "version", "database"}
    assert "database_url" not in fields
    assert "password" not in " ".join(fields)