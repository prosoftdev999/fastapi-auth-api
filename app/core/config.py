from enum import Enum
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


_INSECURE_SECRET_KEYS = {
    "replace-this-with-a-long-random-secret-key",
    "your-generated-secret-key",
    "changeme",
    "secret",
    "secretkey",
}

_MIN_SECRET_KEY_LENGTH = 16
_MIN_PRODUCTION_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    app_name: str = "FastAPI Authentication API"
    app_version: str = "0.2.0"
    environment: Environment = Environment.DEVELOPMENT

    database_url: str

    secret_key: str
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    smtp_host: str
    smtp_port: int = 587
    smtp_username: str
    smtp_password: str
    smtp_from_email: str
    smtp_from_name: str

    frontend_url: str

    # NoDecode: without it, pydantic-settings tries to JSON-decode list-typed
    # env vars before our comma-split validator ever runs, and blows up on
    # any plain comma-separated string (i.e. every real deployment — Render,
    # docker-compose `environment:`, CI `env:` all set real OS env vars, not
    # a .env file pydantic-settings parses itself).
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    trusted_hosts: Annotated[list[str], NoDecode] = ["*"]

    # IPs/networks of trusted reverse proxies (e.g. the Nginx container).
    # When set, X-Forwarded-For/X-Forwarded-Proto from these sources are
    # trusted to determine the real client IP/scheme (uvicorn's
    # ProxyHeadersMiddleware) — otherwise every request behind Nginx would
    # appear to come from the proxy's IP, breaking per-IP rate limiting.
    trusted_proxy_ips: Annotated[list[str], NoDecode] = []

    log_level: str = "INFO"

    redis_url: str = "redis://localhost:6379/0"

    google_client_id: str | None = None
    google_client_secret: str | None = None

    github_client_id: str | None = None
    github_client_secret: str | None = None

    microsoft_client_id: str | None = None
    microsoft_client_secret: str | None = None
    microsoft_tenant: str = "common"

    # S3-compatible object storage for file uploads. endpoint_url is only
    # for non-AWS providers (MinIO, R2, Spaces, ...) — leave unset for AWS.
    s3_endpoint_url: str | None = None
    s3_bucket_name: str = "fastapi-auth-uploads"
    s3_region: str = "us-east-1"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator(
        "cors_origins", "trusted_hosts", "trusted_proxy_ips", mode="before"
    )
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> object:
        # Render/Heroku-style managed Postgres URLs use the bare "postgres://"
        # scheme, which SQLAlchemy 2.0 no longer accepts with the psycopg2 driver.
        if isinstance(value, str) and value.startswith("postgres://"):
            return "postgresql+psycopg2://" + value[len("postgres://") :]
        return value

    @field_validator("secret_key")
    @classmethod
    def _validate_secret_key_length(cls, value: str) -> str:
        if len(value) < _MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                f"SECRET_KEY must be at least {_MIN_SECRET_KEY_LENGTH} characters long"
            )
        return value

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

        if normalized not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")

        return normalized

    @model_validator(mode="after")
    def _validate_production_invariants(self) -> "Settings":
        if self.environment is not Environment.PRODUCTION:
            return self

        if len(self.secret_key) < _MIN_PRODUCTION_SECRET_KEY_LENGTH:
            raise ValueError(
                "SECRET_KEY must be at least "
                f"{_MIN_PRODUCTION_SECRET_KEY_LENGTH} characters long in production"
            )

        if self.secret_key.lower() in _INSECURE_SECRET_KEYS:
            raise ValueError("SECRET_KEY must be changed for production use")

        if self.database_url.startswith("sqlite"):
            raise ValueError(
                "SQLite is not permitted in production; set a PostgreSQL DATABASE_URL"
            )

        if not self.frontend_url.startswith("https://"):
            raise ValueError("FRONTEND_URL must use https:// in production")

        if "*" in self.trusted_hosts:
            raise ValueError(
                "TRUSTED_HOSTS must be explicit in production (wildcard not allowed)"
            )

        return self

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.environment is Environment.DEVELOPMENT

    @property
    def debug(self) -> bool:
        return self.environment in (Environment.DEVELOPMENT, Environment.TEST)

    @property
    def docs_enabled(self) -> bool:
        return not self.is_production


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
