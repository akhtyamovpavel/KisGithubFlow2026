from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MARKETPLACE_",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Mini Marketplace"
    upload_directory: Path = Path(__file__).resolve().parents[1] / "uploads"
    database_url: str = (
        f"sqlite:///{Path(__file__).resolve().parents[1] / 'marketplace.db'}"
    )
    auth_secret_key: SecretStr | None = None
    auth_access_token_ttl_minutes: int = Field(default=30, gt=0, le=1440)
    moderator_email: str | None = None
    moderator_display_name: str | None = None
    moderator_password: SecretStr | None = None
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
