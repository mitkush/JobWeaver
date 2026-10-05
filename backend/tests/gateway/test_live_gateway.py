import json
import uuid

import pytest
from sqlalchemy import select

from app.core.errors import GatewayError
from app.gateway.live import LiveAIGateway
from app.gateway.providers import Completion
from app.gateway.quota import UsageLedger
from app.gateway.routing import DAILY_QUOTAS, GEMINI_FLASH
from app.gateway.schemas import DocumentInput, ParseDocumentsRequest
from app.models import AIUsage
from app.models.document import DocumentKind

GOOD = json.dumps(
    {"facts": [{"kind": "skill", "text": "Go", "source_kind": "resume", "in_base_resume": True}]}
)


class FakeClient:
    def __init__(self, name: str, outputs: list[str | Exception]) -> None:
        self.name = name
        self.outputs = outputs
        self.calls: list[str] = []

    async def complete_json(self, model, system, user, max_output_tokens):
        self.calls.append(model)
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return Completion(output, 10, 5)


REQUEST = ParseDocumentsRequest(
    user_id=uuid.uuid4(), documents=[DocumentInput(kind=DocumentKind.RESUME, text="Go dev")]
)


async def test_falls_back_on_errors_and_bad_output_then_records_usage(db):
    gemini = FakeClient("gemini", [GatewayError("gemini rate limit"), "not json"])
    groq = FakeClient("groq", [GOOD])
    gateway = LiveAIGateway({"gemini": gemini, "groq": groq}, UsageLedger(db))

    response = await gateway.parse_documents(REQUEST.model_copy(update={"user_id": None}))
    assert response.provider == "groq"
    assert response.result.facts[0].text == "Go"
    outcomes = [(u.provider, u.outcome) for u in (await db.execute(select(AIUsage))).scalars()]
    assert sorted(outcomes) == [("gemini", "error"), ("gemini", "error"), ("groq", "ok")]


async def test_skips_routes_over_their_daily_quota(db):
    ledger = UsageLedger(db)
    for _ in range(DAILY_QUOTAS[("gemini", GEMINI_FLASH)]):
        await ledger.record(
            user_id=None, task="t", provider="gemini", model=GEMINI_FLASH, outcome="ok"
        )
    gemini = FakeClient("gemini", [GOOD])
    gateway = LiveAIGateway({"gemini": gemini}, ledger)
    await gateway.parse_documents(REQUEST.model_copy(update={"user_id": None}))
    assert GEMINI_FLASH not in gemini.calls


async def test_raises_one_clear_error_when_every_route_fails(db):
    gateway = LiveAIGateway({}, UsageLedger(db))
    with pytest.raises(GatewayError, match="not configured"):
        await gateway.parse_documents(REQUEST)
