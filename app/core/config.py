from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FastAPI Authentication API"
    environment: str = "development"
    database_url: str = "sqlite:///./fastapi_auth.db"
    secret_key: str = "change-this-in-production"

    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "FastAPI Authentication API"
    frontend_url: str = "http://localhost:3000"

@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()