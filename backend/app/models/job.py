import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, user_fk


def _enum(cls: type[enum.StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class Job(Base):
    """The real opening one or more Postings describe (CONTEXT.md). Shared (ADR-0002).

    Every field except the skills is derived from the Job's Postings by
    services.correspondence.refresh_jobs, so nothing found on a lower-priority Posting
    is lost (ADR-0004)."""

    __tablename__ = "jobs"
    __table_args__ = (Index("idx_jobs_open_posted", "expired_at", "posted_at"),)

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    # Not a foreign key: postings.job_id already points here, and a cycle buys nothing.
    primary_posting_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    title: Mapped[str] = mapped_column(String(500), default="")
    company_name: Mapped[str] = mapped_column(String(255), default="")
    # Union of all Postings' locations: [{"city", "country", "remote"}]
    locations: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    work_mode: Mapped[str | None] = mapped_column(String(16))
    apply_url: Mapped[str | None] = mapped_column(String(2048))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    # Earliest known posting date across the stack, so a repost does not look new.
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Source names in the stack, highest priority first ("Available on" badges).
    sources: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)
    # Extracted once per Job by AI (ADR-0010); None until extracted.
    required_skills: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)), default=None)
    skills_extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Parsed from the primary Posting when correspondence derives this Job.
    experience_requirement: Mapped[str | None] = mapped_column(String(100))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Band(enum.StrEnum):
    EXACT = "exact"
    HIGH = "high"
    MEDIUM = "medium"


class PairStatus(enum.StrEnum):
    AUTO = "auto"  # Exact or High: grouped without asking
    OPEN = "open"  # Medium: a Possible Duplicate waiting for a decision
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class MatchPair(Base):
    """A claim that two Postings describe the same Job (ADR-0004). Low pairs are not stored.

    posting_a_id is always the smaller id, so each pair has one row."""

    __tablename__ = "match_pairs"
    __table_args__ = (
        Index("idx_match_pairs_pair", "posting_a_id", "posting_b_id", unique=True),
        Index("idx_match_pairs_b", "posting_b_id"),
        Index("idx_match_pairs_status", "status"),
    )

    posting_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("postings.id", ondelete="CASCADE"))
    posting_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("postings.id", ondelete="CASCADE"))
    band: Mapped[Band] = mapped_column(_enum(Band, "match_band"))
    status: Mapped[PairStatus] = mapped_column(_enum(PairStatus, "pair_status"))
    # {"reason": "same_url" | "same_text" | "similar", "title": 0-100, "description": 0-1}
    signals: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RejectedPair(Base):
    """Two Postings someone said are not the same Job. Permanent and global (FR-C3 AC3)."""

    __tablename__ = "rejected_pairs"
    __table_args__ = (
        Index("idx_rejected_pairs_pair", "posting_a_id", "posting_b_id", unique=True),
        Index("idx_rejected_pairs_b", "posting_b_id"),
    )

    posting_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("postings.id", ondelete="CASCADE"))
    posting_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("postings.id", ondelete="CASCADE"))
    reason: Mapped[str] = mapped_column(String(16))  # "not_same" | "split"
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class UserJob(Base):
    """A Job in one User's Feed, with that User's own state (ADR-0002)."""

    __tablename__ = "user_jobs"
    __table_args__ = (
        Index("idx_user_jobs_user_job", "user_id", "job_id", unique=True),
        Index("idx_user_jobs_user_hidden", "user_id", "hidden_at"),
        Index("idx_user_jobs_user_saved", "user_id", "saved_at"),
        Index("idx_user_jobs_job", "job_id"),
    )

    user_id: Mapped[uuid.UUID] = user_fk()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Saved for later: kept through Feed rebuilds, shown even after the Job expires.
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when the User opens the Job page.
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Explicitly saved Jobs survive Preferences and automatic Feed rebuilds.
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Reviewed page text belongs to this User, never overwrites a shared Posting.
    page_description: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    page_required_skills: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)))
    # Why the Job is in this Feed: "title" or "keywords". None when it no longer matches
    # the Preferences but stays because the User hid it, drafted for it or applied.
    match_kind: Mapped[str | None] = mapped_column(String(16), default="title")
    # For keyword matches: [{"keyword", "where": "requirements" | "description", "core"}]
    matched_keywords: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
