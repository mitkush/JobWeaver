import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentKind
from app.models.fact import FactKind, FactOrigin


class FactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: FactKind
    group: str
    text: str
    source_kind: DocumentKind | None
    in_base_resume: bool
    origin: FactOrigin
    edited: bool


class FactCreate(BaseModel):
    kind: FactKind
    group: str = Field(default="", max_length=255)
    text: str = Field(min_length=1, max_length=2000)
    in_base_resume: bool = False


class FactUpdate(BaseModel):
    kind: FactKind | None = None
    group: str | None = Field(default=None, max_length=255)
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    in_base_resume: bool | None = None


class FactMerge(BaseModel):
    fact_ids: list[uuid.UUID] = Field(min_length=2, max_length=20)
    text: str = Field(min_length=1, max_length=2000)


class FactBankChanges(BaseModel):
    """What a re-parse changed (FR-A2 AC3). Edited and user-added Facts are always kept."""

    added: list[str]
    removed: list[str]
    kept_edits: int


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: DocumentKind
    filename: str
    size_bytes: int


class UploadResult(BaseModel):
    document: DocumentOut
    changes: FactBankChanges
    facts: list[FactOut]


class FactBankExport(BaseModel):
    documents: list[DocumentOut]
    facts: list[FactOut]
