"""Source Adapter interface (ADR-0003)."""

import asyncio
import enum
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Iterable
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


class SourceQuery(BaseModel):
    """One windowed search: a title plus a location, built from users' Preferences."""

    model_config = ConfigDict(frozen=True)

    keywords: str
    location: Location | None = None

    @property
    def key(self) -> str:
        loc = self.location
        where = "any" if loc is None else f"{loc.city or ''}|{loc.country or ''}|{loc.remote}"
        return f"{self.keywords.lower()}@{where}"[:300]


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
    # False when a snapshot provider capped its list: missing jobs are not closed.
    complete: bool = True


class SourceAdapter(ABC):
    name: str
    label: str
    priority: int
    mode: FetchMode
    # Monthly free allowance in credits or requests; None means no metered limit.
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
    disabled_reason: str | None = None

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self.http = http
        self.settings = settings
        # Set by the fetcher before each call on metered Sources, so providers that take a
        # spending cap (Apify) stop at the budget instead of overrunning it.
        self.allowance_left: int | None = None

    def is_configured(self) -> bool:
        return True

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
    mode = FetchMode.WINDOWED
    # False for Sources fetched once per run regardless of Preferences (e.g. Remotive).
    per_query: bool = True

    @abstractmethod
    async def fetch_window(self, query: SourceQuery | None, window: FetchWindow) -> FetchResult: ...


class SnapshotSourceAdapter(SourceAdapter):
    mode = FetchMode.SNAPSHOT
    ats: str

    @abstractmethod
    async def fetch_board(self, slug: str) -> FetchResult: ...
