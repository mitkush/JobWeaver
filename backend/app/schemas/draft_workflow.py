import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.tailoring.content import DraftContent, Section


class ProposalIn(BaseModel):
    expected_version: int = Field(ge=1)
    part: Literal["resume", "cover_letter"]
    section: Section | None = None
    instruction: str = Field(default="", max_length=2000)


class ProposalOut(BaseModel):
    id: uuid.UUID
    base_version: int
    part: str
    section: str | None
    state: str
    progress: str
    error: str | None
    content: DraftContent | None
    warnings: list[str]


class ProposalAccept(BaseModel):
    expected_version: int = Field(ge=1)
