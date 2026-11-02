"""Settings from the environment (12-factor). Nothing else reads os.environ."""

from datetime import datetime
from functools import lru_cache
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEV_SESSION_SECRET = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+asyncpg://jobweaver:jobweaver@localhost:5432/jobweaver"
    # Base URL of the app as the browser sees it; used for OAuth redirects.
    public_url: str = "http://localhost:5173"
    session_secret: str = Field(default=DEV_SESSION_SECRET, min_length=16)
    session_days: int = 30
    credentials_encryption_key: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""
    # Testing-mode refresh tokens expire 7 days after consent (ADR-0006); 0 = no expiry.
    gmail_token_lifetime_days: int = 7
    # Comma-separated in the environment.
    admin_emails: Annotated[list[str], NoDecode] = []
    dev_login_enabled: bool = False
    # Application Extension (ADR-0017): IDs of the extensions allowed to connect, comma-
    # separated. Empty turns the extension connection off.
    extension_ids: Annotated[list[str], NoDecode] = []
    # The extension keeps its credential in session storage and reconnects after expiry.
    extension_credential_hours: int = Field(default=12, ge=1, le=168)
    # The Chrome Web Store listing, once published. Empty: Settings explains the unpacked
    # install instead.
    extension_store_url: str = ""

    gateway_mode: Literal["live", "recorded"] = "live"
    gateway_recorded_dir: str = "tests/fixtures/gateway"
    gemini_api_key: str = ""
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    mistral_api_key: str = Field(default="", repr=False)
    # Personal Claude route: explicit owner-only consent, never subscription credentials.
    claude_code_enabled: bool = False
    claude_code_owner_id: UUID | None = None
    claude_code_worker_url: str = "http://jobweaver-claude:8080"
    claude_code_worker_key: str = Field(default="", repr=False)
    claude_code_consent_version: str = ""
    claude_code_consent_accepted_at: datetime | None = None
    # While on Gemini's free tier, users in the EEA, CH and UK cannot be served (ADR-0012).
    gemini_free_tier: bool = True

    # Error reporting (FR-G5): a free Sentry project's DSN. Empty turns reporting off.
    sentry_dsn: str = ""

    # Job Sources (Phase 2). A Source without its key is reported as not configured.
    brightdata_api_key: str = ""
    brightdata_api_keys: str = Field(default="", repr=False)
    # Bright Data does not expose free-tier credits. Pause an exhausted primary
    # until its next renewal while keeping it first in the credential list.
    brightdata_primary_paused_until: datetime | None = None
    brightdata_linkedin_dataset_id: str = "gd_lpfll7v5hcqtkxl6l"
    # Broad role keywords searched once per Preference country, joined with OR, instead of
    # one search per title and city. Empty keeps the per-title searches.
    brightdata_discovery_keywords: str = ""
    # Extra country-wide discovery searches, independent of Feed Preferences.
    brightdata_discovery_countries: str = ""
    # Records one Bright Data search may return (limit_per_input); 0 means no cap.
    brightdata_limit_per_search: int = 1000
    rapidapi_key: str = ""
    # Phase 5 Sources. Apify's free $5 a month is shared by Naukri and LinkedIn (Apify).
    # Actor inputs are written for these actors; another actor needs its own mapping.
    apify_token: str = ""
    apify_tokens: str = Field(default="", repr=False)
    apify_naukri_actor: str = "muhammetakkurtt~naukri-job-scraper"
    apify_naukri_max_jobs: int = 200
    # Full descriptions, needed for skills and contact emails (the actor's detail mode).
    apify_naukri_fetch_details: bool = True
    # The actor filters by Naukri's numeric city ids, which are not published. Map the
    # cities you search ({"Bengaluru": "<id>"}) after checking them on naukri.com; an
    # unmapped city is added to the keywords instead.
    apify_naukri_city_ids: dict[str, str] = {}
    apify_linkedin_actor: str = "curious_coder~linkedin-jobs-scraper"
    # Upper bound per search, not a budget cut: LinkedIn shows at most about 1,000.
    apify_linkedin_max_items: int = 1000
    # Piloterr LinkedIn search API: independent third-party job data provider.
    piloterr_api_key: str = Field(default="", repr=False)
    piloterr_linkedin_pages_per_query: int = 1
    scrapingdog_api_key: str = Field(default="", repr=False)
    # Local safety ceiling, not a promise of recurring provider credits.
    scrapingdog_monthly_credits: int = Field(default=100, ge=0)
    jobspy_timeout_seconds: int = Field(default=900, ge=1, le=1800)
    jobspy_max_results: int = Field(default=50, ge=1, le=1000)
    jobspy_proxies: list[str] = Field(default_factory=list, repr=False)
    # Piloterr needs LinkedIn geo IDs. Keys may be city names or ISO country codes.
    piloterr_linkedin_geo_ids: dict[str, str] = Field(default_factory=lambda: {"IN": "102713980"})
    serpapi_key: str = ""
    # Each page is one of the 250 monthly searches and holds up to 10 jobs.
    serpapi_pages_per_query: int = 1
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_pages_per_query: int = 2
    backfill_days: int = 14
    window_overlap_hours: int = 2
    # Windowed-only Postings older than this are treated as closed (FR-B10).
    posting_max_age_days: int = 30
    # Daily run time; 01:17 UTC is 06:47 in India. Off the hour to avoid busy minutes.
    fetch_hour_utc: int = 1
    fetch_minute_utc: int = 17
    # Shared secret for the external cron fallback (ADR-0008). Empty disables the endpoint.
    internal_cron_secret: str = ""

    # Duplicate bands (FR-C1 AC3): strict to start, tuned on real data.
    dedup_window_days: int = 30
    dedup_high_title: float = 90
    dedup_high_description: float = 0.92
    dedup_medium_title: float = 75
    dedup_medium_description: float = 0.85
    # Gemini embedding pacing; free-tier per-minute token limits are low (COSTS.md).
    embedding_batch_size: int = 20
    embedding_batch_pause_seconds: float = 20
    embedding_max_batches_per_run: int = 60
    # AI skill extraction: adverts per request and requests per run (ADR-0010).
    # Hacker News comments per extraction call, and calls per run (Flash-Lite quota).
    adverts_batch_size: int = 8
    adverts_max_batches_per_run: int = 30
    skills_batch_size: int = 5
    skills_max_batches_per_run: int = 40

    scheduler_enabled: bool = True
    max_upload_bytes: int = 5 * 1024 * 1024

    @field_validator("brightdata_discovery_countries")
    @classmethod
    def discovery_countries(cls, value: str) -> str:
        countries = list(dict.fromkeys(c.strip().upper() for c in value.split(",") if c.strip()))
        if any(len(c) != 2 or not c.isascii() or not c.isalpha() for c in countries):
            raise ValueError("Discovery countries must be comma-separated two-letter country codes")
        return ",".join(countries)

    @field_validator("brightdata_primary_paused_until")
    @classmethod
    def _pause_date_needs_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("BRIGHTDATA_PRIMARY_PAUSED_UNTIL needs a timezone, such as Z")
        return value

    @field_validator("extension_ids", mode="before")
    @classmethod
    def _split_extension_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [e.strip() for e in value.split(",") if e.strip()]
        return value

    @field_validator("admin_emails", mode="before")
    @classmethod
    def _split_emails(cls, value: object) -> object:
        if isinstance(value, str):
            return [e.strip().lower() for e in value.split(",") if e.strip()]
        return value

    @model_validator(mode="after")
    def _production_needs_real_secrets(self) -> "Settings":
        if self.environment != "production":
            return self
        missing = [
            name
            for name, ok in (
                ("SESSION_SECRET", self.session_secret != DEV_SESSION_SECRET),
                ("CREDENTIALS_ENCRYPTION_KEY", bool(self.credentials_encryption_key)),
                ("GOOGLE_CLIENT_ID", bool(self.google_client_id)),
                ("GOOGLE_CLIENT_SECRET", bool(self.google_client_secret)),
                # Without https the session cookie is sent without Secure.
                ("PUBLIC_URL (https)", self.public_url.startswith("https://")),
            )
            if not ok
        ]
        if missing:
            raise ValueError(f"Production needs these environment variables: {', '.join(missing)}")
        return self

    @property
    def secure_cookies(self) -> bool:
        return self.public_url.startswith("https://")

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.public_url}/api/auth/google/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
