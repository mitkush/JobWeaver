import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.application_profile import ProfileContent


class ExtensionApproveIn(BaseModel):
    extension_id: str = Field(max_length=32)
    challenge: str = Field(max_length=64)


class ExtensionGrantOut(BaseModel):
    code: str
    expires_at: datetime


class ExtensionTokenIn(BaseModel):
    code: str = Field(max_length=128)
    verifier: str = Field(max_length=128)


class ExtensionUserOut(BaseModel):
    name: str
    email: str


class ExtensionTokenOut(BaseModel):
    token: str
    expires_at: datetime
    user: ExtensionUserOut


class ExtensionConnectionOut(BaseModel):
    id: uuid.UUID
    extension_id: str
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime


class ExtProfileOut(BaseModel):
    """The reviewed profile, without entries whose Facts changed since the review."""

    reviewed: bool
    version: int
    needs_review: bool
    content: ProfileContent | None


class ExtDraftSummary(BaseModel):
    draft_id: uuid.UUID
    job_id: uuid.UUID
    title: str
    company: str
    apply_host: str | None
    current_version: int
    saved_at: datetime
    application_status: str | None


class ExtDraftMatch(BaseModel):
    """Drafts whose Job's apply link matches the page; more than one means the User picks."""

    drafts: list[ExtDraftSummary]


class ExtDraftVersion(BaseModel):
    draft_id: uuid.UUID
    job_id: uuid.UUID
    title: str
    company: str
    apply_url: str | None
    number: int
    current_version: int
    saved_at: datetime
    warnings: int
    template: Literal["standard", "compact"]
    resume_file: str
    cover_letter_file: str
    application_status: str | None
