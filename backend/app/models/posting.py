import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.vector import Vector

# Gemini embeddings reduced to 768 dimensions (ADR-0014, COSTS.md storage estimate).
EMBEDDING_DIM = 768


class Company(Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True)


class AtsBoard(Base):
    """A company's public board on an ATS, fetched in snapshot mode (ADR-0013)."""

    __tablename__ = "ats_boards"
    __table_args__ = (Index("idx_ats_boards_ats_slug", "ats", "slug", unique=True),)

    ats: Mapped[str] = mapped_column(String(32))
    slug: Mapped[str] = mapped_column(String(200))
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL")
    )
    discovered_from: Mapped[str] = mapped_column(String(16))  # "apply_url" | "manual"
    added_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    enabled: Mapped[bool] = mapped_column(default=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_nonempty_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Posting(Base):
    """One job advert as seen on one Source (CONTEXT.md). Public data only."""

    __tablename__ = "postings"
    __table_args__ = (
        Index("idx_postings_source_job", "source", "source_job_id", unique=True),
        Index("idx_postings_company_open", "company_id", "closed_at"),
        Index("idx_postings_board_open", "ats_board_id", "closed_at"),
        Index("idx_postings_job", "job_id"),
        Index("idx_postings_match_state", "match_state"),
    )

    source: Mapped[str] = mapped_column(String(64))
    source_job_id: Mapped[str] = mapped_column(String(255))
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    ats_board_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ats_boards.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    # Parsed when the description is already in memory; Jobs copy this on derivation.
    experience_requirement: Mapped[str | None] = mapped_column(String(100))
    # [{"city": .., "country": .., "remote": bool}]
    locations: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    work_mode: Mapped[str | None] = mapped_column(String(16))
    apply_url: Mapped[str | None] = mapped_column(String(2048))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_reason: Mapped[str | None] = mapped_column(String(32))
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    # pending -> done, or awaiting_embedding while Gemini is unavailable (ADR-0014).
    match_state: Mapped[str] = mapped_column(String(24), default="pending")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), deferred=True)
    # Vectors from different models are never compared (ADR-0014).
    embedding_model: Mapped[str | None] = mapped_column(String(64))
