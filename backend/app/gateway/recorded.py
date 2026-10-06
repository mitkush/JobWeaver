import hashlib
import json
import math
import re
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel

from app.core.errors import GatewayError
from app.gateway.base import BaseAIGateway
from app.gateway.parsing import parse_output
from app.gateway.routing import EMBEDDING_DIMENSIONS
from app.gateway.schemas import (
    DraftResult,
    EmbedRequest,
    EmbedResult,
    ExtractSkillsRequest,
    ExtractSkillsResult,
    GatewayResponse,
    ParseDocumentsRequest,
    ParseDocumentsResult,
    ReviseDraftRequest,
    TailorDraftRequest,
)

T = TypeVar("T", bound=BaseModel)
Variant = Literal["success", "malformed", "refusal"]


class RecordedAIGateway(BaseAIGateway):
    """Serves committed fixtures, so tests and CI make zero live AI calls.

    Fixtures live at <fixture_dir>/<task>/<variant>.json as {"output": "<raw model text>"}.
    They go through the same output validation as live responses.
    """

    embedding_model = "recorded-embedding"

    def __init__(self, fixture_dir: Path, variant: Variant = "success") -> None:
        self.fixture_dir = fixture_dir
        self.variant = variant

    async def tailor_draft(self, request: TailorDraftRequest) -> GatewayResponse[DraftResult]:
        return self._serve("tailor_draft", DraftResult)

    async def revise_draft(self, request: ReviseDraftRequest) -> GatewayResponse[DraftResult]:
        return self._serve("revise_draft", DraftResult)

    async def parse_documents(
        self, request: ParseDocumentsRequest
    ) -> GatewayResponse[ParseDocumentsResult]:
        return self._serve("parse_documents", ParseDocumentsResult)

    async def extract_skills(
        self, request: ExtractSkillsRequest
    ) -> GatewayResponse[ExtractSkillsResult]:
        return self._serve("extract_skills", ExtractSkillsResult)

    async def embed_texts(self, request: EmbedRequest) -> GatewayResponse[EmbedResult]:
        """Vectors cannot be captured meaningfully as fixtures, so recorded mode builds a
        deterministic bag-of-words vector: the same words give the same vector, and
        texts sharing most words are close. Any non-success variant acts as an outage."""
        if self.variant != "success":
            raise GatewayError("Gemini embeddings unavailable (recorded outage)")
        return GatewayResponse[EmbedResult](
            result=EmbedResult(vectors=[recorded_vector(text) for text in request.texts]),
            provider="recorded",
            model=self.embedding_model,
        )

    def _serve(self, task: str, result_type: type[T]) -> GatewayResponse[T]:
        path = self.fixture_dir / task / f"{self.variant}.json"
        if not path.exists():
            raise GatewayError(f"No recorded fixture at {path}")
        raw = json.loads(path.read_text())["output"]
        result = parse_output(raw, result_type)
        return GatewayResponse[result_type](  # type: ignore[valid-type]
            result=result, provider="recorded", model=f"{task}/{self.variant}"
        )


_WORD = re.compile(r"[a-z0-9+#.]+")


def recorded_vector(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for word in _WORD.findall(text.lower()):
        digest = hashlib.sha1(word.encode()).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        vector[index] += 1.0 if digest[4] % 2 else -1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]
