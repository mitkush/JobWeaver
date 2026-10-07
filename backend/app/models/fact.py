import enum
import uuid

from sqlalchemy import Boolean, Enum, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, user_fk
from app.models.document import DocumentKind


class FactKind(enum.StrEnum):
    SKILL = "skill"
    EXPERIENCE = "experience"
    PROJECT = "project"
    ACHIEVEMENT = "achievement"
    EDUCATION = "education"
    LINK = "link"
    OTHER = "other"


class FactOrigin(enum.StrEnum):
    AI = "ai"
    USER = "user"


def _enum(cls: type[enum.StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class Fact(Base):
    """One entry of the Fact Bank: the only allowed source for tailoring (ADR-0005)."""

    __tablename__ = "facts"
    __table_args__ = (Index("idx_facts_user_kind", "user_id", "kind"),)

    user_id: Mapped[uuid.UUID] = user_fk()
    kind: Mapped[FactKind] = mapped_column(_enum(FactKind, "fact_kind"))
    # Grouping label such as the employer or project name; empty for skills.
    group: Mapped[str] = mapped_column(String(255), default="")
    text: Mapped[str] = mapped_column(Text)
    source_kind: Mapped[DocumentKind | None] = mapped_column(
        _enum(DocumentKind, "document_kind"), nullable=True
    )
    in_base_resume: Mapped[bool] = mapped_column(Boolean, default=False)
    origin: Mapped[FactOrigin] = mapped_column(_enum(FactOrigin, "fact_origin"))
    # Set once the user changes an AI fact, so a re-parse never overwrites it (FR-A2 AC3).
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)


class DismissedFact(Base):
    """Text the User removed from their Fact Bank (deleted, merged away, or edited from the
    AI's wording). A re-parse never brings it back (FR-A2 AC3). Text only, never values
    from other Users; deleted with the Fact Bank."""

    __tablename__ = "dismissed_facts"
    __table_args__ = (Index("idx_dismissed_facts_user_text", "user_id", "text_key", unique=True),)

    user_id: Mapped[uuid.UUID] = user_fk()
    # Lower-cased, whitespace-collapsed Fact text.
    text_key: Mapped[str] = mapped_column(Text)
