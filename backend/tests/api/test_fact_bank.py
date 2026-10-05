from pathlib import Path

import pytest

from app.api.deps import get_gateway
from app.core.config import get_settings
from app.gateway.recorded import RecordedAIGateway
from tests.conftest import onboard
from tests.pdf import make_pdf

RESUME = make_pdf("Asha Rao. Backend engineer at Acme Corp. Python, PostgreSQL.")


def use_variant(variant: str) -> None:
    from app.main import app

    fixtures = Path(get_settings().gateway_recorded_dir)
    app.dependency_overrides[get_gateway] = lambda: RecordedAIGateway(fixtures, variant)


async def upload_resume(client):
    return await client.post(
        "/api/documents",
        data={"kind": "resume"},
        files={"file": ("resume.pdf", RESUME, "application/pdf")},
    )


@pytest.fixture
async def ready(alice):
    _, client = alice
    await onboard(client)
    return client


async def test_upload_builds_the_fact_bank(ready):
    response = await upload_resume(ready)
    assert response.status_code == 200
    body = response.json()
    assert body["document"]["kind"] == "resume"
    texts = {f["text"] for f in body["facts"]}
    assert "Python" in texts and "Kafka" in texts
    assert len(body["changes"]["added"]) == 7
    kafka = next(f for f in body["facts"] if f["text"] == "Kafka")
    assert kafka["in_base_resume"] is False  # portfolio-only facts are marked (FR-A2 AC1)
    assert kafka["origin"] == "ai"


async def test_rejects_unreadable_and_oversized_files(ready, monkeypatch):
    bad = await ready.post(
        "/api/documents",
        data={"kind": "resume"},
        files={"file": ("resume.pdf", b"not a pdf at all", "application/pdf")},
    )
    assert bad.status_code == 422
    image = await ready.post(
        "/api/documents",
        data={"kind": "resume"},
        files={"file": ("me.png", b"\x89PNG....", "image/png")},
    )
    assert image.status_code == 422
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "10")
    get_settings.cache_clear()
    assert (await upload_resume(ready)).status_code == 422


async def test_reupload_keeps_user_edits_and_reports_changes(ready):
    facts = (await upload_resume(ready)).json()["facts"]
    python = next(f for f in facts if f["text"] == "Python")
    edited = await ready.patch(f"/api/facts/{python['id']}", json={"text": "Python 3.12"})
    assert edited.json()["edited"] is True
    added = await ready.post("/api/facts", json={"kind": "skill", "text": "Rust"})
    assert added.status_code == 201

    second = (await upload_resume(ready)).json()
    texts = [f["text"] for f in second["facts"]]
    assert "Python 3.12" in texts and "Rust" in texts
    assert texts.count("PostgreSQL") == 1
    assert second["changes"]["kept_edits"] == 2
    # "Python" comes back from the AI as a new fact because the user renamed theirs.
    assert second["changes"]["added"] == ["Python"]


async def test_ai_failure_keeps_the_document_and_allows_retry(ready):
    use_variant("malformed")
    response = await upload_resume(ready)
    assert response.status_code == 503
    assert "Your document is saved" in response.json()["error"]["message"]
    assert len((await ready.get("/api/documents")).json()) == 1
    assert (await ready.get("/api/facts")).json() == []

    use_variant("success")
    retry = await ready.post("/api/fact-bank/rebuild")
    assert retry.status_code == 200
    assert len((await ready.get("/api/facts")).json()) == 7


async def test_ai_refusal_is_reported_not_stored(ready):
    use_variant("refusal")
    response = await upload_resume(ready)
    assert response.status_code == 503
    assert (await ready.get("/api/facts")).json() == []


async def test_merge_review_export_and_delete(ready):
    facts = (await upload_resume(ready)).json()["facts"]
    skills = [f["id"] for f in facts if f["kind"] == "skill"][:2]
    merged = await ready.post("/api/facts/merge", json={"fact_ids": skills, "text": "Python, SQL"})
    assert merged.status_code == 200
    assert merged.json()["origin"] == "user"
    assert len((await ready.get("/api/facts")).json()) == 6

    assert (await ready.post("/api/fact-bank/review")).status_code == 204
    me = (await ready.get("/api/me")).json()
    assert me["onboarding"]["fact_bank_reviewed"] is True
    assert me["onboarding"]["next_step"] == "preferences"

    export = (await ready.get("/api/fact-bank/export")).json()
    assert len(export["documents"]) == 1 and len(export["facts"]) == 6

    assert (await ready.delete("/api/fact-bank")).status_code == 204
    assert (await ready.get("/api/facts")).json() == []
    assert (await ready.get("/api/me")).json()["onboarding"]["fact_bank_reviewed"] is False


async def test_review_needs_facts(ready):
    assert (await ready.post("/api/fact-bank/review")).status_code == 409


async def test_typed_summary_is_a_document(ready):
    response = await ready.post(
        "/api/documents/text",
        json={"kind": "summary", "text": "Backend engineer who likes data pipelines."},
    )
    assert response.status_code == 200
    assert response.json()["document"]["filename"] == "summary.txt"


async def test_facts_are_isolated_between_users(ready, bob):
    facts = (await upload_resume(ready)).json()["facts"]
    fact_id = facts[0]["id"]
    _, bob_client = bob
    assert (await bob_client.get("/api/facts")).json() == []
    assert (await bob_client.patch(f"/api/facts/{fact_id}", json={"text": "x"})).status_code == 404
    assert (await bob_client.delete(f"/api/facts/{fact_id}")).status_code == 404
    other = await bob_client.post("/api/facts", json={"kind": "skill", "text": "Go"})
    merge = await bob_client.post(
        "/api/facts/merge", json={"fact_ids": [fact_id, other.json()["id"]], "text": "x"}
    )
    assert merge.status_code == 404
    assert (await bob_client.get("/api/documents")).json() == []
    assert len((await ready.get("/api/facts")).json()) == 7


async def test_failed_ai_calls_still_count_toward_the_daily_quota(ready, db):
    """The request rolls back on failure; usage records must survive it."""
    from sqlalchemy import func, select

    from app.core.db import get_sessionmaker
    from app.core.errors import GatewayError
    from app.gateway.live import LiveAIGateway
    from app.gateway.quota import UsageLedger
    from app.main import app
    from app.models import AIUsage

    class Down:
        name = "gemini"

        async def complete_json(self, *args):
            raise GatewayError("gemini timed out")

    app.dependency_overrides[get_gateway] = lambda: LiveAIGateway(
        {"gemini": Down()}, UsageLedger(get_sessionmaker())
    )
    response = await upload_resume(ready)
    assert response.status_code == 503
    assert await db.scalar(select(func.count()).select_from(AIUsage)) == 2  # Flash, Flash-Lite
