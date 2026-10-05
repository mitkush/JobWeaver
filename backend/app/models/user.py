import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Role(enum.StrEnum):
    USER = "user"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    google_sub: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    picture_url: Mapped[str | None] = mapped_column(String(1024))
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role", values_callable=lambda e: [m.value for m in e]),
        default=Role.USER,
    )
    # ISO 3166-1 alpha-2, asked in onboarding (FR-A1 AC4).
    country: Mapped[str | None] = mapped_column(String(2))
    ai_notice_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fact_bank_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
