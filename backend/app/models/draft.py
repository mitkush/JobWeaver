"""Versioned, user-owned application packages (ADR-0001, ADR-0005)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, user_fk


class Draft(Base):
    __tablename__ = "drafts"
    __table_args__ = (Index("idx_drafts_user_job", "user_id", "job_id"),)

    user_id: Mapped[uuid.UUID] = user_fk()
    # Merges explicitly move packages; missed paths must not silently delete them.
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"))
    state: Mapped[str] = mapped_column(String(24), default="queued")
    progress: Mapped[str] = mapped_column(String(255), default="Reading the job")
    error: Mapped[str | None] = mapped_column(Text)
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
    # Snapshots keep the original trace readable after Fact edits or deletion.
    facts: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    message: Mapped[str] = mapped_column(Text, default="")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (Index("idx_applications_user_job", "user_id", "job_id"),)

    user_id: Mapped[uuid.UUID] = user_fk()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"))
    draft_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("drafts.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(24), default="drafted")
    gmail_draft_id: Mapped[str | None] = mapped_column(String(255))
    # A hand-off is bound to a version and recipient; retrying it reuses the result.
    version: Mapped[int] = mapped_column(Integer)
    recipient: Mapped[str | None] = mapped_column(String(320))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
