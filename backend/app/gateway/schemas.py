import uuid
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentKind
from app.models.fact import FactKind
from app.tailoring.content import DraftContent, FactSnapshot

ResultT = TypeVar("ResultT", bound=BaseModel)


class GatewayResponse(BaseModel, Generic[ResultT]):
    result: ResultT
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class DocumentInput(BaseModel):
    kind: DocumentKind
    text: str


class ParseDocumentsRequest(BaseModel):
    user_id: uuid.UUID
    documents: list[DocumentInput] = Field(min_length=1)


class ParsedFact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: FactKind
    group: str = ""
    text: str = Field(min_length=1, max_length=2000)
    source_kind: DocumentKind
    in_base_resume: bool


class ParseDocumentsResult(BaseModel):
    facts: list[ParsedFact]


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=100)


class EmbedResult(BaseModel):
    vectors: list[list[float]]


class JobAdvert(BaseModel):
    ref: str
    title: str
    description: str


class ExtractSkillsRequest(BaseModel):
    """Advert text from ingestion or a reviewed Page Description (ADR-0010).

    user_id attributes usage internally; it is not included in the provider prompt.
    """

    jobs: list[JobAdvert] = Field(min_length=1, max_length=10)
    user_id: uuid.UUID | None = None


class JobSkills(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ref: str
    skills: list[str] = Field(default_factory=list, max_length=40)


class ExtractSkillsResult(BaseModel):
    jobs: list[JobSkills]


class AdvertText(BaseModel):
    ref: str
    text: str


class ExtractAdvertsRequest(BaseModel):
    """Public free-text adverts (e.g. Hacker News comments); never User data (ADR-0002)."""

    adverts: list[AdvertText] = Field(min_length=1, max_length=10)


class ExtractedJob(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=300)
    company: str = Field(min_length=1, max_length=200)
    locations: list[str] = Field(default_factory=list, max_length=20)
    work_mode: Literal["onsite", "hybrid", "remote"] | None = None
    apply_url: str | None = None
    contact_email: str | None = None


class AdvertJobs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ref: str
    # False for comments that are not job adverts (questions, replies, meta posts).
    is_job_advert: bool = True
    jobs: list[ExtractedJob] = Field(default_factory=list, max_length=15)


class ExtractAdvertsResult(BaseModel):
    adverts: list[AdvertJobs]


class TailorDraftRequest(BaseModel):
    user_id: uuid.UUID
    job_title: str
    company: str
    description: str
    facts: list[FactSnapshot] = Field(min_length=1, max_length=200)
    has_email: bool
    # Counted by code from the User's role dates; the AI may claim this many years, no more.
    experience_years: float | None = None


class DraftDevelopmentRequest(TailorDraftRequest):
    previous_content: DraftContent
    feedback: str = Field(min_length=1, max_length=2000)


class ReviseDraftRequest(TailorDraftRequest):
    content: DraftContent
    message: str = Field(min_length=1, max_length=2000)


class DraftResult(BaseModel):
    content: DraftContent
    message: str = ""


class FormQuestion(BaseModel):
    """A question from an application form: its text only, never the page (ADR-0017)."""

    ref: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=1000)
    max_chars: int | None = Field(default=None, ge=1, le=20000)


class AnswerQuestionsRequest(BaseModel):
    user_id: uuid.UUID
    job_title: str
    company: str
    description: str
    facts: list[FactSnapshot] = Field(min_length=1, max_length=200)
    # Observable traits and redacted excerpts only; never facts (ADR-0017).
    writing_style: str = ""
    questions: list[FormQuestion] = Field(min_length=1, max_length=12)


class QuestionAnswer(BaseModel):
    ref: str
    text: str = Field(max_length=20000)
    fact_refs: list[str] = Field(default_factory=list)


class AnswerQuestionsResult(BaseModel):
    answers: list[QuestionAnswer]


class WritingStyleRequest(BaseModel):
    """Text the User wrote themselves; the result describes how they write, not what."""

    user_id: uuid.UUID
    samples: list[str] = Field(min_length=1, max_length=8)


class WritingStyleResult(BaseModel):
    traits: list[str] = Field(default_factory=list, max_length=8)
    excerpts: list[str] = Field(default_factory=list, max_length=3)
