import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.user import Role
from app.services.gmail import GmailState


class OnboardingStatus(BaseModel):
    ai_notice_accepted: bool
    country_set: bool
    ai_region_blocked: bool
    documents_uploaded: bool
    fact_bank_reviewed: bool
    preferences_set: bool
    gmail_connected: bool
    # First unfinished step; "done" when the User can use the Feed.
    next_step: str


class GmailStatus(BaseModel):
    state: GmailState
    expires_at: datetime | None


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    picture_url: str | None
    role: Role
    country: str | None
    onboarding: OnboardingStatus
    gmail: GmailStatus
    # Days an Application may stay Applied before a Follow-up Reminder (FR-F2).
    follow_up_days: int


class CountryIn(BaseModel):
    country: str = Field(pattern=r"^[A-Za-z]{2}$")
