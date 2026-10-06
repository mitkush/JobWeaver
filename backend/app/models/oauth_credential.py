import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, user_fk


class OAuthCredential(Base):
    """Encrypted Gmail credentials (ADR-0006). One row per user and provider."""

    __tablename__ = "oauth_credentials"
    __table_args__ = (Index("idx_oauth_user_provider", "user_id", "provider", unique=True),)

    user_id: Mapped[uuid.UUID] = user_fk()
    provider: Mapped[str] = mapped_column(String(32), default="gmail")
    refresh_token_encrypted: Mapped[str] = mapped_column(Text)
    scopes: Mapped[str] = mapped_column(Text, default="")
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
