"""Source Adapter interface (ADR-0003). Concrete adapters arrive in Phase 2."""

import enum
from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


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
    """One windowed search: a title or keyword plus a location."""

    model_config = ConfigDict(frozen=True)

    keywords: str
    location: Location | None = None


class FetchWindow(BaseModel):
    model_config = ConfigDict(frozen=True)

    since: datetime
    until: datetime


class NormalizedPosting(BaseModel):
    """What every adapter emits (FR-B9). Public job-advert data only, never user data."""

    source_job_id: str
    title: str
    company: str
    description: str
    locations: list[Location] = Field(default_factory=list)
    work_mode: WorkMode | None = None
    apply_url: HttpUrl | None = None
    contact_email: str | None = None
    posted_at: datetime | None = None


class FetchResult(BaseModel):
    postings: list[NormalizedPosting]
    # Credits or requests this call used, for the Credit Budget (FR-B5).
    credits_used: int = 0
    requests_used: int = 0


class SourceAdapter(ABC):
    name: str
    priority: int
    mode: FetchMode


class WindowedSourceAdapter(SourceAdapter):
    mode = FetchMode.WINDOWED

    @abstractmethod
    async def fetch_window(self, query: SourceQuery, window: FetchWindow) -> FetchResult: ...


class SnapshotSourceAdapter(SourceAdapter):
    mode = FetchMode.SNAPSHOT

    @abstractmethod
    async def fetch_board(self, board_slug: str) -> FetchResult: ...
