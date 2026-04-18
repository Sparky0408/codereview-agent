"""Application configuration via pydantic-settings.

All secrets and tunables are read from environment variables / .env file.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration — every env var the app needs lives here."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_name: str = "CodeReview Agent"
    debug: bool = False

    # --- GitHub App ---
    github_app_id: int = 0
    github_private_key_path: str = "secrets/codereview-agent.pem"
    github_webhook_secret: str = ""

    # --- Database (PostgreSQL) ---
    database_url: str = "postgresql+asyncpg://codereview:codereview@localhost:5432/codereview"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Gemini ---
    gemini_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
