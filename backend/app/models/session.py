import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, user_fk


class UserSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("idx_sessions_user_expires", "user_id", "expires_at"),)

    user_id: Mapped[uuid.UUID] = user_fk()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
