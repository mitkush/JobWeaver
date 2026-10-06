import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RunStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class FetchRun(Base):
    """One execution of one Source for one query or board (FR-B3, FR-B5)."""

    __tablename__ = "fetch_runs"
    __table_args__ = (Index("idx_fetch_runs_source_created", "source", "created_at"),)

    source: Mapped[str] = mapped_column(String(64))
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="run_status", values_callable=lambda e: [m.value for m in e])
    )
    trigger: Mapped[str] = mapped_column(String(16), default="schedule")
    query_key: Mapped[str | None] = mapped_column(String(300))
    board_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ats_boards.id", ondelete="SET NULL")
    )
    window_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    postings_found: Mapped[int] = mapped_column(Integer, default=0)
    postings_new: Mapped[int] = mapped_column(Integer, default=0)
    postings_closed: Mapped[int] = mapped_column(Integer, default=0)
    credits_used: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class QueryWatermark(Base):
    """Where the last successful window of a windowed query ended (FR-B3 AC1)."""

    __tablename__ = "query_watermarks"
    __table_args__ = (Index("idx_watermarks_source_query", "source", "query_key", unique=True),)

    source: Mapped[str] = mapped_column(String(64))
    query_key: Mapped[str] = mapped_column(String(300))
    last_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
