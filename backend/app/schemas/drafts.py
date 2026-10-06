import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.tailoring.content import DraftContent, FactSnapshot
from app.tailoring.diff import DiffLine


class DraftCreate(BaseModel):
    job_id: uuid.UUID


class DraftSave(BaseModel):
    expected_version: int = Field(ge=1)
    content: DraftContent


class DraftChat(BaseModel):
    expected_version: int = Field(ge=1)
    message: str = Field(min_length=1, max_length=2000)
    overwrite_manual: bool = False


class RestoreVersion(BaseModel):
    expected_version: int = Field(ge=1)
    number: int = Field(ge=1)


class VersionOut(BaseModel):
    number: int
    source: str
    content: DraftContent
    facts: list[FactSnapshot]
    warnings: list[str]
    message: str
    created_at: datetime


class DraftOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    state: str
    progress: str
    error: str | None
    current_version: int
    job: dict[str, object]
    base_resume: str
    version: VersionOut | None
    application_status: str | None
    attachment_name: str


class EmailCheck(BaseModel):
    recipient: str
    valid: bool
    warnings: list[str]


class HandoffIn(BaseModel):
    expected_version: int = Field(ge=1)
    template: Literal["standard", "compact"] = "standard"
    recipient: str = Field(min_length=1, max_length=320)
    confirm: bool = False
    confirm_email_warning: bool = False


class HandoffOut(BaseModel):
    mode: Literal["gmail", "fallback", "reconnect"]
    url: str
    attachment_name: str
    message: str
    application_id: uuid.UUID | None = None


class AppliedIn(BaseModel):
    expected_version: int = Field(ge=1)


__all__ = ["DiffLine"]
