import uuid

from sqlalchemy import Boolean, Index, Integer
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import String

from app.models.base import Base, user_fk


class Preference(Base):
    __tablename__ = "preferences"
    __table_args__ = (Index("idx_preferences_user", "user_id", unique=True),)

    user_id: Mapped[uuid.UUID] = user_fk()
    titles: Mapped[list[str]] = mapped_column(ARRAY(String(200)), default=list)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String(100)), default=list)
    # Keywords a differently titled Job must mention at least one of to reach the Feed's
    # keyword section; none means that section is off. Always a subset of keywords.
    core_keywords: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), default=list, server_default="{}"
    )
    # Distinct keywords such a Job must mention in total, core ones included.
    keyword_min_matches: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    # Also search paid Sources by each core keyword, within their budgets.
    search_keywords: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # City null means the whole country; an empty list means global job locations.
    locations: Mapped[list[dict[str, str | None]]] = mapped_column(JSONB, default=list)
    work_modes: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
