import json
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel

from app.core.errors import GatewayError
from app.gateway.base import BaseAIGateway
from app.gateway.parsing import parse_output
from app.gateway.schemas import GatewayResponse, ParseDocumentsRequest, ParseDocumentsResult

T = TypeVar("T", bound=BaseModel)
Variant = Literal["success", "malformed", "refusal"]


class RecordedAIGateway(BaseAIGateway):
    """Serves committed fixtures, so tests and CI make zero live AI calls.

    Fixtures live at <fixture_dir>/<task>/<variant>.json as {"output": "<raw model text>"}.
    They go through the same output validation as live responses.
    """

    def __init__(self, fixture_dir: Path, variant: Variant = "success") -> None:
        self.fixture_dir = fixture_dir
        self.variant = variant

    async def parse_documents(
        self, request: ParseDocumentsRequest
    ) -> GatewayResponse[ParseDocumentsResult]:
        return self._serve("parse_documents", ParseDocumentsResult)

    def _serve(self, task: str, result_type: type[T]) -> GatewayResponse[T]:
        path = self.fixture_dir / task / f"{self.variant}.json"
        if not path.exists():
            raise GatewayError(f"No recorded fixture at {path}")
        raw = json.loads(path.read_text())["output"]
        result = parse_output(raw, result_type)
        return GatewayResponse[result_type](  # type: ignore[valid-type]
            result=result, provider="recorded", model=f"{task}/{self.variant}"
        )
