import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings

BASE_ENV = {
    "environment": Environment.DEVELOPMENT,
    "database_url": "postgresql+psycopg2://user:pass@localhost:5432/db",
    "secret_key": "a-reasonably-long-development-secret-key",
    "smtp_host": "smtp.example.com",
    "smtp_username": "user@example.com",
    "smtp_password": "password",
    "smtp_from_email": "user@example.com",
    "smtp_from_name": "Test",
    "frontend_url": "http://localhost:3000",
}


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **{**BASE_ENV, **overrides})


def test_development_settings_are_permissive() -> None:
    settings = make_settings()

    assert settings.is_development is True
    assert settings.is_production is False
    assert settings.debug is True


def test_cors_origins_parsed_from_comma_separated_string() -> None:
    settings = make_settings(cors_origins="http://a.com, http://b.com")

    assert settings.cors_origins == ["http://a.com", "http://b.com"]


def test_trusted_proxy_ips_parsed_from_comma_separated_string() -> None:
    settings = make_settings(trusted_proxy_ips="10.0.0.1, 10.0.0.2")

    assert settings.trusted_proxy_ips == ["10.0.0.1", "10.0.0.2"]


def test_list_settings_parse_from_real_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression test: passing these as Settings(**kwargs) (like every other
    # test in this file does) exercises Pydantic's normal field validation
    # and never touches pydantic-settings' env-var decoding layer. Render,
    # docker-compose `environment:`, and CI `env:` all set real OS
    # environment variables, which go through a different code path
    # (EnvSettingsSource) that used to attempt a JSON-decode of these
    # comma-separated strings before our validator ever ran, and crashed on
    # any value that wasn't valid JSON — i.e. every realistic value.
    for key, value in BASE_ENV.items():
        if isinstance(value, str):
            monkeypatch.setenv(key.upper(), value)
    monkeypatch.setenv("ENVIRONMENT", Environment.DEVELOPMENT.value)
    monkeypatch.setenv("CORS_ORIGINS", "http://a.com,http://b.com")
    monkeypatch.setenv("TRUSTED_HOSTS", "api.example.com")
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "*")

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["http://a.com", "http://b.com"]
    assert settings.trusted_hosts == ["api.example.com"]
    assert settings.trusted_proxy_ips == ["*"]


def test_trusted_proxy_ips_defaults_empty() -> None:
    settings = make_settings()

    assert settings.trusted_proxy_ips == []


def test_secret_key_below_absolute_minimum_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(secret_key="too-short")


def test_production_requires_longer_secret_key() -> None:
    with pytest.raises(ValidationError):
        make_settings(
            environment=Environment.PRODUCTION,
            secret_key="a-short-but-valid-dev-key",
            frontend_url="https://example.com",
            trusted_hosts=["example.com"],
        )


def test_production_rejects_known_placeholder_secret_key() -> None:
    with pytest.raises(ValidationError):
        make_settings(
            environment=Environment.PRODUCTION,
            secret_key="replace-this-with-a-long-random-secret-key",
            frontend_url="https://example.com",
            trusted_hosts=["example.com"],
        )


def test_production_rejects_sqlite() -> None:
    with pytest.raises(ValidationError):
        make_settings(
            environment=Environment.PRODUCTION,
            secret_key="a" * 32,
            database_url="sqlite:///./prod.db",
            frontend_url="https://example.com",
            trusted_hosts=["example.com"],
        )


def test_production_rejects_plaintext_frontend_url() -> None:
    with pytest.raises(ValidationError):
        make_settings(
            environment=Environment.PRODUCTION,
            secret_key="a" * 32,
            frontend_url="http://example.com",
            trusted_hosts=["example.com"],
        )


def test_production_rejects_wildcard_trusted_hosts() -> None:
    with pytest.raises(ValidationError):
        make_settings(
            environment=Environment.PRODUCTION,
            secret_key="a" * 32,
            frontend_url="https://example.com",
            trusted_hosts=["*"],
        )


def test_valid_production_settings_pass() -> None:
    settings = make_settings(
        environment=Environment.PRODUCTION,
        secret_key="a" * 32,
        frontend_url="https://example.com",
        trusted_hosts=["example.com"],
    )

    assert settings.is_production is True
    assert settings.debug is False


def test_docs_disabled_in_production() -> None:
    settings = make_settings(
        environment=Environment.PRODUCTION,
        secret_key="a" * 32,
        frontend_url="https://example.com",
        trusted_hosts=["example.com"],
    )

    assert settings.docs_enabled is False


def test_docs_enabled_outside_production() -> None:
    settings = make_settings(environment=Environment.DEVELOPMENT)

    assert settings.docs_enabled is True


def test_bare_postgres_scheme_is_normalized_to_psycopg2() -> None:
    settings = make_settings(
        database_url="postgres://user:pass@host:5432/dbname"
    )

    assert settings.database_url == "postgresql+psycopg2://user:pass@host:5432/dbname"


def test_already_qualified_database_url_is_left_unchanged() -> None:
    settings = make_settings(
        database_url="postgresql+psycopg2://user:pass@host:5432/dbname"
    )

    assert settings.database_url == "postgresql+psycopg2://user:pass@host:5432/dbname"
