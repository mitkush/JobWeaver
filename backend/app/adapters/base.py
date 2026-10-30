"""Source Adapter interface (ADR-0003)."""

import asyncio
import enum
import hashlib
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime
from typing import TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.adapters.errors import (
    SourceBadResponse,
    SourceNotConfigured,
    SourceQuotaExhausted,
    SourceRateLimited,
    SourceUnavailable,
)
from app.core.config import Settings
from app.schemas.account_balances import AccountBalance

T = TypeVar("T")


async def bounded_gather(calls: Iterable[Awaitable[T]], limit: int) -> list[T]:
    """Runs calls with at most `limit` in flight, so one board never floods a provider."""
    gate = asyncio.Semaphore(limit)

    async def one(call: Awaitable[T]) -> T:
        async with gate:
            return await call

    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(one(c)) for c in calls]
    except ExceptionGroup as failed:
        # The first failure cancels the rest; callers handle it like a single call's error.
        raise failed.exceptions[0] from None
    return [task.result() for task in tasks]


class FetchMode(enum.StrEnum):
    # Query + time window; only sees new Postings, cannot see jobs close.
    WINDOWED = "windowed"
    # Full list of open jobs on one ATS Board; compared with stored Postings.
    SNAPSHOT = "snapshot"


class WorkMode(enum.StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"


class Location(BaseModel):
    model_config = ConfigDict(frozen=True)

    city: str | None = None
    country: str | None = None  # ISO 3166-1 alpha-2
    remote: bool = False


# FetchRun.query_key and QueryWatermark.query_key are String(300).
KEY_LENGTH = 300


class SourceQuery(BaseModel):
    """One windowed search: a title plus a location, built from users' Preferences."""

    model_config = ConfigDict(frozen=True)

    keywords: str
    location: Location | None = None

    @property
    def key(self) -> str:
        """Stable id for watermarks and Fetch Runs, at most 300 characters. A long keyword
        list is shortened with a hash of the whole query, so two searches never share a
        key and the place is never cut off."""
        loc = self.location
        where = "any" if loc is None else f"{loc.city or ''}|{loc.country or ''}|{loc.remote}"
        full = f"{self.keywords.lower()}@{where}"
        if len(full) <= KEY_LENGTH:
            return full
        digest = hashlib.sha256(full.encode()).hexdigest()[:16]
        suffix = f"#{digest}@{where}"[-(KEY_LENGTH // 2) :]
        return self.keywords.lower()[: KEY_LENGTH - len(suffix)] + suffix


# A daily window is 24 hours plus the fetcher's overlap (2 hours by default) plus a little
# scheduling drift. Without slack, any drift tips a daily search into a "past week" filter
# that is billed per record (Bright Data) or returns far more than is new.
WINDOW_SLACK_HOURS = 3


class FetchWindow(BaseModel):
    model_config = ConfigDict(frozen=True)

    since: datetime
    until: datetime

    @property
    def hours(self) -> float:
        return (self.until - self.since).total_seconds() / 3600

    def within_days(self, days: float) -> bool:
        """True when a provider filter of the last `days` days covers this window."""
        return self.hours <= days * 24 + WINDOW_SLACK_HOURS


class NormalizedPosting(BaseModel):
    """What every adapter emits (FR-B9). Public job-advert data only, never user data."""

    source_job_id: str
    title: str
    company: str
    description: str = ""
    locations: list[Location] = Field(default_factory=list)
    work_mode: WorkMode | None = None
    apply_url: str | None = None
    contact_email: str | None = None
    posted_at: datetime | None = None


class PendingAdvert(BaseModel):
    """Free text that may advertise jobs, for Sources whose adverts have no structure
    (Hacker News). AI extraction turns it into Postings later (FR-B8)."""

    ref: str
    text: str
    url: str | None = None
    posted_at: datetime | None = None


class FetchResult(BaseModel):
    postings: list[NormalizedPosting]
    pending: list[PendingAdvert] = Field(default_factory=list)
    # Credits or requests this call used, for the Credit Budget (FR-B5).
    credits_used: int = 0
    # False when the provider capped its list: a snapshot closes no missing jobs, and a
    # windowed search reports that some jobs in its window may be missing.
    complete: bool = True


class SourceAdapter(ABC):
    # Each provider declares its own key fields and account-balance capabilities.
    credential_settings: tuple[str, str] | None = None
    primary_credential_pause_setting: str | None = None
    account_balance_required: bool = False
    # Minimum verified balance required before starting a paid search, in cents.
    minimum_usable_balance = 1
    # Select credentials from start-request limit errors, without a local quota precheck.
    credential_limits_from_errors: bool = False
    name: str
    label: str
    # Optional provider site used to group adapters in user-facing source filters.
    site: str | None = None
    priority: int
    mode: FetchMode
    # Local monthly tracking guard; provider-reported limits come from account_balance.
    # None means no local metered limit.
    monthly_allowance: int | None = None
    allowance_unit: str = "requests"
    renewal_day: int = 1
    # Some providers ask for a minimum gap between calls (e.g. Remotive: 4 a day).
    min_interval_hours: float = 0
    # A standby only runs while the Source it backs up is Degraded or disabled, and the
    # two share query watermarks so a search is never paid for twice.
    standby_for: str | None = None
    # Sources billed from one account share a single allowance (e.g. "apify").
    budget_pool: str | None = None
    # Sources that are not reliable enough to run unless an admin turns them on.
    default_enabled: bool = True
    # On-demand browser imports have no scheduled or manual fetch operation.
    push_only: bool = False
    disabled_reason: str | None = None

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self.http = http
        self.settings = settings
        # Set by the fetcher before each call on metered Sources, so providers that take a
        # spending cap (Apify) stop at the budget instead of overrunning it.
        self.allowance_left: int | None = None
        self.credential_fingerprint: str | None = None
        self.exhausted_credentials: set[str] = set()

    async def account_balance(self, now: datetime, *, force: bool = False) -> AccountBalance | None:
        return None

    def is_configured(self) -> bool:
        return True

    @classmethod
    def credit_allowance(cls, settings: Settings) -> int | None:
        return cls.monthly_allowance

    def ensure_configured(self) -> None:
        if not self.is_configured():
            raise SourceNotConfigured(f"{self.label} is not configured (API key missing)")

    @staticmethod
    def check_response(label: str, response: httpx.Response) -> None:
        """Maps provider HTTP errors to SourceErrors with messages an admin can act on."""
        if response.status_code < 400:
            return
        body = response.text[:300].lower()
        if response.status_code in (401, 403):
            raise SourceUnavailable(f"{label} rejected the API key (HTTP {response.status_code})")
        if response.status_code == 402 or any(w in body for w in ("quota", "balance", "credit")):
            raise SourceQuotaExhausted(f"{label} free allowance is used up")
        if response.status_code == 429:
            raise SourceRateLimited(f"{label} rate limit reached")
        if response.status_code >= 500:
            raise SourceUnavailable(f"{label} is unavailable (HTTP {response.status_code})")
        raise SourceBadResponse(f"{label} returned HTTP {response.status_code}")


class WindowedSourceAdapter(SourceAdapter):
    # Opt-in durable asynchronous collections. The fetcher owns persistence; adapters
    # checkpoint the returned provider id before polling, without database access.
    # Incompatible with retry_incomplete_window: retrying a capped snapshot would
    # download the same results forever. Such adapters need pagination-aware state.
    resumable_collections: bool = False
    collection_id: str | None = None
    checkpoint_collection: Callable[[str | None], Awaitable[None]] | None = None

    mode = FetchMode.WINDOWED
    # Opt-in fallbacks can preserve partial results without claiming the window is done.
    retry_incomplete_window: bool = False
    # Optional, injected lookup: adapters never query the database themselves.
    known_postings: Callable[[set[str]], Awaitable[set[str]]] | None = None
    # False for Sources fetched once per run regardless of Preferences (e.g. Remotive).
    per_query: bool = True

    def search_queries(self, preference_queries: list[SourceQuery]) -> list[SourceQuery]:
        """The searches this Source runs, given one per title and place from users'
        Preferences. A Source may search more broadly and leave matching to the Feed."""
        return preference_queries

    def searches_titles(self) -> bool:
        """Whether each Preference title adds searches to this Source's daily run."""
        return True

    def continues_from(
        self, query: SourceQuery, preference_queries: list[SourceQuery]
    ) -> list[str]:
        """Keys of earlier searches a new search covers, so its first run picks up where
        they stopped instead of a Backfill. Empty: a new search starts with a Backfill."""
        return []

    @abstractmethod
    async def fetch_window(self, query: SourceQuery | None, window: FetchWindow) -> FetchResult: ...


class SnapshotSourceAdapter(SourceAdapter):
    mode = FetchMode.SNAPSHOT
    ats: str

    @abstractmethod
    async def fetch_board(self, slug: str) -> FetchResult: ...
