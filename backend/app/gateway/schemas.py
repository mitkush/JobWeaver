import uuid
from typing import Generic, TypeVar

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
    """Public job-advert text only; never User data (ADR-0002, ADR-0010)."""

    jobs: list[JobAdvert] = Field(min_length=1, max_length=10)


class JobSkills(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ref: str
    skills: list[str] = Field(default_factory=list, max_length=40)


class ExtractSkillsResult(BaseModel):
    jobs: list[JobSkills]


class TailorDraftRequest(BaseModel):
    user_id: uuid.UUID
    job_title: str
    company: str
    description: str
    facts: list[FactSnapshot] = Field(min_length=1, max_length=200)
    has_email: bool


class ReviseDraftRequest(TailorDraftRequest):
    content: DraftContent
    message: str = Field(min_length=1, max_length=2000)


class DraftResult(BaseModel):
    content: DraftContent
    message: str = ""
