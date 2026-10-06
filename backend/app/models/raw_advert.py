from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RawAdvert(Base):
    """Free-text job adverts (e.g. a Hacker News "Who is hiring" comment) waiting for AI
    extraction into Postings (FR-B8). Public advert text only; shared like Postings
    (ADR-0002), so there is no user_id."""

    __tablename__ = "raw_adverts"
    __table_args__ = (
        Index("idx_raw_adverts_source_ref", "source", "ref", unique=True),
        Index("idx_raw_adverts_pending", "extracted_at", "attempts"),
    )

    source: Mapped[str] = mapped_column(String(64))
    ref: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(2048))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set once extraction finished, whether it found jobs or not.
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    postings: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
