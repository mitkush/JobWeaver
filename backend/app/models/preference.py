import uuid

from sqlalchemy import Index
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
    # City null means the whole country; an empty list means global job locations.
    locations: Mapped[list[dict[str, str | None]]] = mapped_column(JSONB, default=list)
    work_modes: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
