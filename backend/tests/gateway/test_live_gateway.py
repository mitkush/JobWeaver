import json
import uuid

import pytest
from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.core.errors import GatewayError
from app.gateway.live import LiveAIGateway
from app.gateway.providers import Completion
from app.gateway.quota import UsageLedger
from app.gateway.routing import DAILY_QUOTAS, GEMINI_FLASH, GROQ_LARGE, ROUTING_TABLE, Route
from app.gateway.schemas import DocumentInput, ParseDocumentsRequest
from app.models import AIUsage
from app.models.document import DocumentKind

GOOD = json.dumps(
    {"facts": [{"kind": "skill", "text": "Go", "source_kind": "resume", "in_base_resume": True}]}
)


def test_provider_timeouts_are_short_only_for_interactive_draft_tasks():
    from app.services.drafting import DRAFT_GENERATION_TIMEOUT_SECONDS

    assert {route.timeout_seconds for route in ROUTING_TABLE["tailor_draft"]} == {20}
    assert {route.timeout_seconds for route in ROUTING_TABLE["revise_draft"]} == {20}
    assert sum(route.timeout_seconds for route in ROUTING_TABLE["tailor_draft"]) <= (
        DRAFT_GENERATION_TIMEOUT_SECONDS
    )
    assert sum(route.timeout_seconds for route in ROUTING_TABLE["revise_draft"]) <= (
        DRAFT_GENERATION_TIMEOUT_SECONDS
    )
    for task in ("parse_documents", "extract_skills", "extract_adverts"):
        assert {route.timeout_seconds for route in ROUTING_TABLE[task]} == {90}


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
    gemini = FakeClient("gemini", [GatewayError("gemini rate limit")])
    groq = FakeClient("groq", ["not json"])
    openrouter = FakeClient("openrouter", [GOOD])
    gateway = LiveAIGateway(
        {"gemini": gemini, "groq": groq, "openrouter": openrouter},
        UsageLedger(get_sessionmaker()),
    )

    response = await gateway.parse_documents(REQUEST.model_copy(update={"user_id": None}))
    assert response.provider == "openrouter"
    assert response.result.facts[0].text == "Go"
    outcomes = [(u.provider, u.outcome) for u in (await db.execute(select(AIUsage))).scalars()]
    assert sorted(outcomes) == [("gemini", "error"), ("groq", "error"), ("openrouter", "ok")]


async def test_skips_routes_over_their_daily_quota(db):
    ledger = UsageLedger(get_sessionmaker())
    for _ in range(DAILY_QUOTAS[("gemini", GEMINI_FLASH)]):
        await ledger.record(
            user_id=None, task="t", provider="gemini", model=GEMINI_FLASH, outcome="ok"
        )
    gemini = FakeClient("gemini", [GOOD])
    gateway = LiveAIGateway({"gemini": gemini}, ledger)
    await gateway.parse_documents(REQUEST.model_copy(update={"user_id": None}))
    assert GEMINI_FLASH not in gemini.calls


async def test_raises_one_clear_error_when_every_route_fails(db):
    gateway = LiveAIGateway({}, UsageLedger(get_sessionmaker()))
    with pytest.raises(GatewayError, match="not configured"):
        await gateway.parse_documents(REQUEST)


async def test_timeouts_and_non_json_replies_fall_through_to_the_next_provider(db):
    import httpx

    from app.gateway.providers import GeminiClient, OpenAICompatibleClient

    def gemini(request):
        raise httpx.ReadTimeout("slow")

    def groq(request):
        return httpx.Response(200, text="<html>bad gateway</html>")

    def openrouter(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": GOOD}}]})

    clients = {
        "gemini": GeminiClient("k", httpx.AsyncClient(transport=httpx.MockTransport(gemini))),
        "groq": OpenAICompatibleClient(
            "groq", "https://g", "k", httpx.AsyncClient(transport=httpx.MockTransport(groq))
        ),
        "openrouter": OpenAICompatibleClient(
            "openrouter",
            "https://o",
            "k",
            httpx.AsyncClient(transport=httpx.MockTransport(openrouter)),
        ),
    }
    response = await LiveAIGateway(clients, UsageLedger(get_sessionmaker())).parse_documents(
        REQUEST.model_copy(update={"user_id": None})
    )
    assert response.provider == "openrouter"
    errors = (await db.execute(select(AIUsage).where(AIUsage.outcome == "error"))).scalars()
    assert {u.provider for u in errors} == {"gemini", "groq"}


async def test_a_provider_deadline_is_recorded_and_falls_through_to_the_next_route(db, monkeypatch):
    import asyncio

    monkeypatch.setitem(
        ROUTING_TABLE,
        "parse_documents",
        [
            Route("gemini", GEMINI_FLASH, timeout_seconds=0.01),
            Route("groq", GROQ_LARGE, timeout_seconds=0.01),
        ],
    )

    class SlowClient:
        async def complete_json(self, model, system, user, max_output_tokens):
            await asyncio.sleep(1)

    ledger = UsageLedger(get_sessionmaker())
    gateway = LiveAIGateway({"gemini": SlowClient(), "groq": FakeClient("groq", [GOOD])}, ledger)

    response = await gateway.parse_documents(REQUEST.model_copy(update={"user_id": None}))

    assert response.provider == "groq"
    outcomes = [
        (usage.provider, usage.outcome) for usage in (await db.execute(select(AIUsage))).scalars()
    ]
    assert sorted(outcomes) == [("gemini", "error"), ("groq", "ok")]


async def no_sleep(_: float) -> None:
    return None


async def test_a_busy_provider_is_retried_once_before_falling_through(db):
    from app.core.errors import ProviderBusy

    gemini = FakeClient("gemini", [ProviderBusy("gemini is overloaded (HTTP 503)"), GOOD])
    gateway = LiveAIGateway({"gemini": gemini}, UsageLedger(get_sessionmaker()), sleep=no_sleep)
    response = await gateway.parse_documents(REQUEST.model_copy(update={"user_id": None}))
    assert response.provider == "gemini"
    assert len(gemini.calls) == 2

    busy = ProviderBusy("gemini is overloaded (HTTP 503)")
    gemini = FakeClient("gemini", [busy, busy])
    groq = FakeClient("groq", [GOOD])
    gateway = LiveAIGateway(
        {"gemini": gemini, "groq": groq}, UsageLedger(get_sessionmaker()), sleep=no_sleep
    )
    response = await gateway.parse_documents(REQUEST.model_copy(update={"user_id": None}))
    assert response.provider == "groq"
    assert len(gemini.calls) == 2


async def test_failures_log_each_providers_own_reason(db, caplog):
    import httpx

    from app.gateway.providers import OpenAICompatibleClient

    def gone(request):
        message = "This model is unavailable for free. The paid version is available now"
        return httpx.Response(404, json={"error": {"message": message, "code": 404}})

    client = OpenAICompatibleClient(
        "openrouter", "https://or.test", "k", httpx.AsyncClient(transport=httpx.MockTransport(gone))
    )
    gateway = LiveAIGateway({"openrouter": client}, UsageLedger(get_sessionmaker()))
    with pytest.raises(GatewayError, match="unavailable for free"):
        await gateway.parse_documents(REQUEST.model_copy(update={"user_id": None}))
    assert "openrouter returned HTTP 404: This model is unavailable for free" in caplog.text


async def test_a_slow_busy_answer_falls_through_without_a_retry(db):
    from app.core.errors import ProviderBusy

    now = [0.0]

    class SlowBusy(FakeClient):
        async def complete_json(self, model, system, user, max_output_tokens):
            now[0] += 35  # the 503 took 35 s: a retry would eat the next provider's time
            return await super().complete_json(model, system, user, max_output_tokens)

    gemini = SlowBusy("gemini", [ProviderBusy("gemini is overloaded (HTTP 503)"), GOOD])
    groq = FakeClient("groq", [GOOD])
    gateway = LiveAIGateway(
        {"gemini": gemini, "groq": groq},
        UsageLedger(get_sessionmaker()),
        sleep=no_sleep,
        clock=lambda: now[0],
    )
    response = await gateway.parse_documents(REQUEST.model_copy(update={"user_id": None}))
    assert response.provider == "groq"
    assert len(gemini.calls) == 1
