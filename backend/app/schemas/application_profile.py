import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

YEAR_MONTH = r"^\d{4}(-(0[1-9]|1[0-2]))?$"
Short = Field(default="", max_length=255)


class ProfileLink(BaseModel):
    label: Literal["linkedin", "github", "portfolio", "website", "other"]
    url: str = Field(min_length=1, max_length=2048)
    fact_id: uuid.UUID | None = None


class EmploymentEntry(BaseModel):
    employer: str = Field(min_length=1, max_length=255)
    title: str = Short
    location: str = Short
    start: str | None = Field(default=None, pattern=YEAR_MONTH)
    end: str | None = Field(default=None, pattern=YEAR_MONTH)
    current: bool = False
    fact_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class EducationEntry(BaseModel):
    school: str = Field(min_length=1, max_length=255)
    degree: str = Short
    field: str = Short
    start: str | None = Field(default=None, pattern=YEAR_MONTH)
    end: str | None = Field(default=None, pattern=YEAR_MONTH)
    fact_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class ProfileContent(BaseModel):
    """What the extension may fill. Free of AI: the User reviews every value (ADR-0017)."""

    first_name: str = Short
    last_name: str = Short
    email: str = Field(default="", max_length=320)
    phone: str = Field(default="", max_length=40)
    phone_fact_id: uuid.UUID | None = None
    city: str = Short
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    links: list[ProfileLink] = Field(default_factory=list, max_length=10)
    employment: list[EmploymentEntry] = Field(default_factory=list, max_length=20)
    education: list[EducationEntry] = Field(default_factory=list, max_length=10)


class ProfileOut(BaseModel):
    content: ProfileContent | None
    version: int
    reviewed_at: datetime | None
    # Paths such as "employment.0" or "phone" whose Facts changed after the review.
    stale: list[str]


class ProfileSave(BaseModel):
    content: ProfileContent
    expected_version: int = Field(ge=0)


Scope = Literal["general", "country", "company"]
Period = Literal["year", "month", "hour"]


class SavedAnswerIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=10000)
    scope: Scope = "general"
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    period: Period | None = None
    company_id: uuid.UUID | None = None
    sensitive: bool = False

    @field_validator("question", "answer")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class SavedAnswerOut(BaseModel):
    id: uuid.UUID
    question: str
    answer: str
    scope: Scope
    country: str | None
    currency: str | None
    period: Period | None
    company_id: uuid.UUID | None
    company_name: str
    sensitive: bool
    origin: Literal["user", "suggestion"]
    job_id: uuid.UUID | None
    updated_at: datetime
