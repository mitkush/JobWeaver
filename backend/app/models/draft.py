"""Versioned, user-owned application packages (ADR-0001, ADR-0005)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, user_fk


class Draft(Base):
    __tablename__ = "drafts"
    __table_args__ = (
        Index("idx_drafts_user_job", "user_id", "job_id"),
        # One active package per User and Job; archived packages keep application history.
        Index(
            "uq_drafts_active_user_job",
            "user_id",
            "job_id",
            unique=True,
            postgresql_where=text("active"),
        ),
    )

    user_id: Mapped[uuid.UUID] = user_fk()
    # Merges explicitly move packages; missed paths must not silently delete them.
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"))
    state: Mapped[str] = mapped_column(String(24), default="queued")
    progress: Mapped[str] = mapped_column(String(255), default="Reading the job")
    error: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    job_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    base_resume: Mapped[str] = mapped_column(Text, default="")


class DraftVersion(Base):
    __tablename__ = "draft_versions"
    __table_args__ = (
        Index("idx_draft_versions_number", "draft_id", "number", unique=True),
        Index("idx_draft_versions_user", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = user_fk()
    draft_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drafts.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(24))
    content: Mapped[dict[str, object]] = mapped_column(JSONB)
    job_context: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    # Snapshots keep the original trace readable after Fact edits or deletion.
    facts: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    message: Mapped[str] = mapped_column(Text, default="")


class ApplicationStatus:
    """FR-F1. Changed by hand, except Drafted (first hand-off) and Applied (Mark as applied)."""

    DRAFTED = "drafted"
    APPLIED = "applied"
    REPLIED = "replied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    ALL = (DRAFTED, APPLIED, REPLIED, INTERVIEW, OFFER, REJECTED)


class Application(Base):
    """One per User and Job: the tracker card (FR-F1)."""

    __tablename__ = "applications"
    __table_args__ = (Index("idx_applications_user_job", "user_id", "job_id", unique=True),)

    user_id: Mapped[uuid.UUID] = user_fk()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"))
    # The Draft last used for this Job.
    draft_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("drafts.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(24), default=ApplicationStatus.DRAFTED)
    # When the User first applied; stays set through later statuses (FR-D5).
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # A Follow-up Reminder is due from here while the status is Applied (FR-F2).
    follow_up_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApplicationEvent(Base):
    """Timestamped status history (FR-F1); created_at is when the status changed."""

    __tablename__ = "application_events"
    __table_args__ = (Index("idx_application_events_user_app", "user_id", "application_id"),)

    user_id: Mapped[uuid.UUID] = user_fk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(24))


class GmailHandoff(Base):
    """One Gmail draft created for an Application or a follow-up. Retrying the same
    version and recipient reuses it instead of creating a second Gmail draft."""

    __tablename__ = "gmail_handoffs"
    __table_args__ = (Index("idx_gmail_handoffs_user_app", "user_id", "application_id"),)

    user_id: Mapped[uuid.UUID] = user_fk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(16), default="application")  # | "follow_up"
    draft_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("drafts.id", ondelete="SET NULL"))
    version: Mapped[int | None] = mapped_column(Integer)
    recipient: Mapped[str] = mapped_column(String(320))
    gmail_draft_id: Mapped[str | None] = mapped_column(String(255))


class DraftProposal(Base):
    """Durable, scoped AI work; candidates never overwrite accepted versions."""

    __tablename__ = "draft_proposals"
    user_id: Mapped[uuid.UUID] = user_fk()
    draft_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("drafts.id", ondelete="CASCADE"), index=True
    )
    base_version: Mapped[int] = mapped_column(Integer)
    part: Mapped[str] = mapped_column(String(24))
    section: Mapped[str | None] = mapped_column(String(40))
    instruction: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(24), default="queued")
    progress: Mapped[str] = mapped_column(String(255), default="Queued")
    error: Mapped[str | None] = mapped_column(Text)
    content: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    facts: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    job_context: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
