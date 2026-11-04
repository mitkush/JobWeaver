import json
import math
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.errors import GatewayError
from app.gateway import prompts
from app.gateway.live import LiveAIGateway
from app.gateway.providers import GeminiClient
from app.gateway.quota import UsageLedger
from app.gateway.recorded import RecordedAIGateway
from app.gateway.routing import DAILY_QUOTAS, EMBEDDING_DIMENSIONS, GEMINI_EMBEDDING, ROUTING_TABLE
from app.gateway.schemas import EmbedRequest, ExtractSkillsRequest, JobAdvert
from app.models import AIUsage
from app.models.posting import EMBEDDING_DIM

FIXTURES = Path(get_settings().gateway_recorded_dir)
SKILLS = ExtractSkillsRequest(jobs=[JobAdvert(ref="1", title="Backend", description="Python")])


def test_embedding_size_matches_the_column():
    assert EMBEDDING_DIMENSIONS == EMBEDDING_DIM


def test_skills_run_on_flash_lite_first_with_text_fallbacks():
    # COSTS.md: high-volume extraction is Flash-Lite first, Groq as bulk fallback.
    routes = [(r.provider, r.model) for r in ROUTING_TABLE["extract_skills"]]
    assert routes[0] == ("gemini", "gemini-flash-lite-latest")
    assert [p for p, _ in routes] == ["gemini", "groq", "openrouter", "mistral"]


def test_skills_prompt_carries_only_advert_text():
    text = prompts.extract_skills_user(
        ExtractSkillsRequest(jobs=[JobAdvert(ref="7", title="T", description="x" * 9000)])
    )
    assert 'ref="7"' in text
    assert len(text) < prompts.ADVERT_CHARS + 200


@pytest.mark.parametrize("variant", ["malformed", "refusal"])
async def test_recorded_skill_failures_are_gateway_errors(variant):
    with pytest.raises(GatewayError):
        await RecordedAIGateway(FIXTURES, variant).extract_skills(SKILLS)  # type: ignore[arg-type]


async def test_recorded_skills_and_embeddings():
    gateway = RecordedAIGateway(FIXTURES)
    skills = await gateway.extract_skills(SKILLS)
    assert skills.result.jobs[0].skills[0] == "Python"
    vectors = (await gateway.embed_texts(EmbedRequest(texts=["a b", "a b", "c"]))).result.vectors
    assert vectors[0] == vectors[1] != vectors[2]
    assert math.isclose(sum(v * v for v in vectors[0]), 1.0)
    with pytest.raises(GatewayError):
        await RecordedAIGateway(FIXTURES, "refusal").embed_texts(EmbedRequest(texts=["a"]))


def gemini(handler) -> GeminiClient:
    return GeminiClient("k", httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_gemini_batch_embedding_request_and_reply():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [{"values": [3.0, 4.0]}] * 2})

    vectors = await gemini(handler).embed("m", ["one", "two"], 2)
    assert seen["url"].endswith("/models/m:batchEmbedContents")
    first = seen["body"]["requests"][0]
    assert first["outputDimensionality"] == 2
    assert first["taskType"] == "SEMANTIC_SIMILARITY"
    assert vectors == [[3.0, 4.0], [3.0, 4.0]]


@pytest.mark.parametrize(
    "reply",
    [
        httpx.Response(200, json={"embeddings": [{"values": [1.0]}]}),
        httpx.Response(200, json={"nothing": True}),
        httpx.Response(429, json={}),
    ],
)
async def test_gemini_embedding_problems_are_gateway_errors(reply):
    with pytest.raises(GatewayError):
        await gemini(lambda request: reply).embed("m", ["one", "two"], 2)


class FakeEmbedder(GeminiClient):
    def __init__(self, error: GatewayError | None = None) -> None:
        self.error = error

    async def embed(self, model, texts, dimensions):
        if self.error:
            raise self.error
        return [[3.0, 4.0] + [0.0] * (dimensions - 2) for _ in texts]


async def test_live_embeddings_are_unit_length_and_counted(db):
    gateway = LiveAIGateway({"gemini": FakeEmbedder()}, UsageLedger(get_sessionmaker()))
    response = await gateway.embed_texts(EmbedRequest(texts=["a"]))
    assert response.model == GEMINI_EMBEDDING
    assert response.result.vectors[0][:2] == [0.6, 0.8]
    usage = (await db.execute(select(AIUsage))).scalar_one()
    assert (usage.task, usage.outcome, usage.user_id) == ("embed_texts", "ok", None)


async def test_live_embeddings_never_fall_back_to_another_provider(db):
    ledger = UsageLedger(get_sessionmaker())
    with pytest.raises(GatewayError, match="Gemini key"):
        await LiveAIGateway({}, ledger).embed_texts(EmbedRequest(texts=["a"]))
    failing = LiveAIGateway({"gemini": FakeEmbedder(GatewayError("gemini timed out"))}, ledger)
    with pytest.raises(GatewayError):
        await failing.embed_texts(EmbedRequest(texts=["a"]))
    for _ in range(DAILY_QUOTAS[("gemini", GEMINI_EMBEDDING)]):
        await ledger.record(
            user_id=None,
            task="embed_texts",
            provider="gemini",
            model=GEMINI_EMBEDDING,
            outcome="ok",
        )
    with pytest.raises(GatewayError, match="quota"):
        await LiveAIGateway({"gemini": FakeEmbedder()}, ledger).embed_texts(
            EmbedRequest(texts=["a"])
        )


def test_skill_prompt_keeps_late_requirements_within_existing_budget():
    description = "About our company. " + "x" * 9000 + "Requirements: Ruby and Rails."
    text = prompts.extract_skills_user(
        ExtractSkillsRequest(jobs=[JobAdvert(ref="1", title="Engineer", description=description)])
    )
    assert "About our company." in text
    assert "Requirements: Ruby and Rails." in text
    assert len(text) < prompts.ADVERT_CHARS + 200
