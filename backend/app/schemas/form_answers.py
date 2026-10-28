import uuid
from typing import Literal

from pydantic import BaseModel, Field


class QuestionIn(BaseModel):
    """Question text from the form, never page content or other answers (ADR-0017)."""

    ref: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=1000)
    max_chars: int | None = Field(default=None, ge=1, le=20000)


class AnswersIn(BaseModel):
    job_id: uuid.UUID
    questions: list[QuestionIn] = Field(min_length=1, max_length=12)
    # The form says not to use AI: notes from the User's Facts only, never prose.
    no_ai: bool = False


class AnswerOut(BaseModel):
    ref: str
    kind: Literal["saved", "suggestion", "fact_notes", "none"]
    text: str = ""
    notes: list[str] = Field(default_factory=list)
    fact_refs: list[str] = Field(default_factory=list)
    saved_answer_id: uuid.UUID | None = None
    warning: str | None = None


class ExtSavedAnswerIn(BaseModel):
    job_id: uuid.UUID
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=10000)
    scope: Literal["general", "country", "company"] = "company"
    origin: Literal["user", "suggestion"] = "user"
