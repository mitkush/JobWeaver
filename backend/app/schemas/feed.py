import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.base import WorkMode


class FeedQuery(BaseModel):
    """Sort is always newest first (FR-D6)."""

    section: Literal["email", "link"] = "email"
    q: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=120)
    work_mode: WorkMode | None = None
    source: str | None = Field(default=None, max_length=64)
    posted_within_days: int | None = Field(default=None, ge=1, le=90)
    hidden: bool = False
    limit: int = Field(default=30, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class LocationOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    city: str | None = None
    country: str | None = None
    remote: bool = False


class SourceBadge(BaseModel):
    name: str
    label: str


class FeedCard(BaseModel):
    job_id: uuid.UUID
    title: str
    company: str
    locations: list[LocationOut]
    work_mode: str | None
    posted_at: datetime | None
    # "Available on": every Source in the Job's stack, highest priority first (FR-C6).
    sources: list[SourceBadge]
    contact_email: str | None
    apply_url: str | None
    # None until the Job's required skills are extracted; [] means no gaps (FR-D3).
    skill_gaps: list[str] | None
    possible_duplicate: bool
    hidden: bool


class FeedCounts(BaseModel):
    with_email: int
    apply_link_only: int


class FeedOut(BaseModel):
    items: list[FeedCard]
    total: int
    counts: FeedCounts
    # When any Source last finished a successful Fetch Run (FR-D7).
    last_updated_at: datetime | None
    sources: list[SourceBadge]


class PostingOut(BaseModel):
    id: uuid.UUID
    source: SourceBadge
    title: str
    locations: list[LocationOut]
    work_mode: str | None
    posted_at: datetime | None
    first_seen_at: datetime
    apply_url: str | None
    contact_email: str | None
    closed: bool
    primary: bool


class PossibleDuplicateOut(BaseModel):
    pair_id: uuid.UUID
    # The Posting of this Job that the other Job may duplicate.
    posting_id: uuid.UUID
    other_job_id: uuid.UUID
    other_job_in_feed: bool
    other_title: str
    other_company: str
    other_postings: list[PostingOut]
    title_similarity: float | None
    description_similarity: float | None


class JobDetailOut(BaseModel):
    job_id: uuid.UUID
    title: str
    company: str
    description: str
    locations: list[LocationOut]
    work_mode: str | None
    posted_at: datetime | None
    contact_email: str | None
    apply_url: str | None
    sources: list[SourceBadge]
    required_skills: list[str] | None
    skill_gaps: list[str] | None
    hidden: bool
    expired: bool
    postings: list[PostingOut]
    possible_duplicates: list[PossibleDuplicateOut]


class JobRef(BaseModel):
    """Where the User's view continues after a merge or a split."""

    job_id: uuid.UUID
