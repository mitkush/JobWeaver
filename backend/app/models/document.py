import enum
import uuid

from sqlalchemy import Enum, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, user_fk


class DocumentKind(enum.StrEnum):
    RESUME = "resume"
    PORTFOLIO = "portfolio"
    SUMMARY = "summary"


class Document(Base):
    """An uploaded source of Facts. One current document per kind per user."""

    __tablename__ = "documents"
    __table_args__ = (Index("idx_documents_user_kind", "user_id", "kind", unique=True),)

    user_id: Mapped[uuid.UUID] = user_fk()
    kind: Mapped[DocumentKind] = mapped_column(
        Enum(DocumentKind, name="document_kind", values_callable=lambda e: [m.value for m in e])
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    extracted_text: Mapped[str] = mapped_column(Text)
