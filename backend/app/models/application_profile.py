"""The reviewed data the Application Extension fills forms with (ADR-0017)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, user_fk


class ApplicationProfile(Base):
    """One per User. `content` is validated by schemas.application_profile.ProfileContent.
    Saving it is the User's review; entries citing a Fact changed since then need review
    again before the extension may use them."""

    __tablename__ = "application_profiles"
    __table_args__ = (Index("idx_application_profiles_user", "user_id", unique=True),)

    user_id: Mapped[uuid.UUID] = user_fk()
    content: Mapped[dict[str, object]] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=0)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Fingerprint of each cited Fact's kind, group and text when the User reviewed.
    fact_hashes: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)


class SavedAnswer(Base):
    """An answer the User gave to a form question, reused only within its scope:
    `general` anywhere, `country` for Jobs in that country (and currency and period for
    salary), `company` only for that Company."""

    __tablename__ = "saved_answers"
    __table_args__ = (Index("idx_saved_answers_user_key", "user_id", "question_key"),)

    user_id: Mapped[uuid.UUID] = user_fk()
    question: Mapped[str] = mapped_column(Text)
    question_key: Mapped[str] = mapped_column(String(255))
    answer: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String(16))
    country: Mapped[str | None] = mapped_column(String(2))
    currency: Mapped[str | None] = mapped_column(String(3))
    period: Mapped[str | None] = mapped_column(String(8))
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE")
    )
    company_name: Mapped[str] = mapped_column(String(255), default="")
    # Work authorisation, salary, notice period and the like: filled only from here.
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    # "user" (typed by the User) or "suggestion" (a Suggestion the User edited and kept).
    origin: Mapped[str] = mapped_column(String(16), default="user")
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
