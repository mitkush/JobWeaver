import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.draft import ApplicationStatus

STATUS_PATTERN = "^(" + "|".join(ApplicationStatus.ALL) + ")$"


class EventOut(BaseModel):
    status: str
    at: datetime


class ApplicationOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    draft_id: uuid.UUID | None
    title: str
    company: str
    company_id: uuid.UUID
    job_expired: bool
    status: str
    applied_at: datetime | None
    status_changed_at: datetime
    follow_up_due: bool
    history: list[EventOut]


class StatusIn(BaseModel):
    status: str = Field(pattern=STATUS_PATTERN)


class CompanyHistoryOut(BaseModel):
    id: uuid.UUID
    name: str
    applications: list[ApplicationOut]


class ReminderOut(BaseModel):
    application_id: uuid.UUID
    job_id: uuid.UUID
    title: str
    company: str
    applied_at: datetime
    days_waiting: int


class FollowUpOut(BaseModel):
    """A starting point the User edits; written from a template, never by AI."""

    recipient: str | None
    subject: str
    body: str


class FollowUpIn(BaseModel):
    recipient: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    confirm: bool = False
    confirm_email_warning: bool = False


class FollowUpResult(BaseModel):
    mode: str  # "gmail" | "fallback" | "reconnect"
    url: str
    message: str


class FollowUpDaysIn(BaseModel):
    days: int = Field(ge=1, le=60)
