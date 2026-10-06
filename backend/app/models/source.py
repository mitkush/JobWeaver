import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SourceState(enum.StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DISABLED = "disabled"


class Source(Base):
    """One job Source and its health (FR-B6). Shared, not user-owned (ADR-0002)."""

    __tablename__ = "sources"

    name: Mapped[str] = mapped_column(String(64), unique=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    state: Mapped[SourceState] = mapped_column(
        Enum(SourceState, name="source_state", values_callable=lambda e: [m.value for m in e]),
        default=SourceState.HEALTHY,
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    degraded_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manual_runs_today: Mapped[int] = mapped_column(Integer, default=0)
    manual_runs_date: Mapped[str | None] = mapped_column(String(10))
