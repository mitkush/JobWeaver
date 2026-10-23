"""Application Extension connections (ADR-0017): a one-time grant, then a credential."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, user_fk


class ExtensionGrant(Base):
    """A single-use code the User approved on a signed-in page, bound to one extension
    and to the extension's PKCE challenge. Exchanged once for an ExtensionCredential."""

    __tablename__ = "extension_grants"
    __table_args__ = (Index("idx_extension_grants_user", "user_id"),)

    user_id: Mapped[uuid.UUID] = user_fk()
    extension_id: Mapped[str] = mapped_column(String(32))
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # base64url(SHA-256(verifier)), sent by the extension when it opened the page.
    challenge: Mapped[str] = mapped_column(String(64))
    # The version of the access list (services.extension.SCOPES) the User saw and approved.
    scopes_version: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExtensionCredential(Base):
    """An opaque bearer credential for the /api/ext/ surface; only its hash is stored."""

    __tablename__ = "extension_credentials"
    __table_args__ = (Index("idx_extension_credentials_user", "user_id"),)

    user_id: Mapped[uuid.UUID] = user_fk()
    extension_id: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Below the current SCOPES_VERSION the credential is refused until approved again.
    scopes_version: Mapped[int] = mapped_column(Integer, default=1)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
