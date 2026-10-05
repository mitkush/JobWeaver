"""Settings from the environment (12-factor). Nothing else reads os.environ."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+asyncpg://jobweaver:jobweaver@localhost:5432/jobweaver"
    # Base URL of the app as the browser sees it; used for OAuth redirects.
    public_url: str = "http://localhost:5173"
    session_secret: str = Field(default="dev-only-change-me", min_length=16)
    session_days: int = 30
    credentials_encryption_key: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""
    # Testing-mode refresh tokens expire 7 days after consent (ADR-0006); 0 = no expiry.
    gmail_token_lifetime_days: int = 7
    # Comma-separated in the environment.
    admin_emails: Annotated[list[str], NoDecode] = []
    dev_login_enabled: bool = False

    gateway_mode: Literal["live", "recorded"] = "live"
    gateway_recorded_dir: str = "tests/fixtures/gateway"
    gemini_api_key: str = ""
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    # While on Gemini's free tier, users in the EEA, CH and UK cannot be served (ADR-0012).
    gemini_free_tier: bool = True

    scheduler_enabled: bool = True
    max_upload_bytes: int = 5 * 1024 * 1024

    @field_validator("admin_emails", mode="before")
    @classmethod
    def _split_emails(cls, value: object) -> object:
        if isinstance(value, str):
            return [e.strip().lower() for e in value.split(",") if e.strip()]
        return value

    @property
    def secure_cookies(self) -> bool:
        return self.public_url.startswith("https://")

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.public_url}/api/auth/google/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
