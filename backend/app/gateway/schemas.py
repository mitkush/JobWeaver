import uuid
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentKind
from app.models.fact import FactKind

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
