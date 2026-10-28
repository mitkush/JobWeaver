from datetime import UTC, datetime

from app.core.config import get_settings
from tests.conftest import onboard


async def test_onboarding_starts_with_the_ai_notice(alice):
    _, client = alice
    me = (await client.get("/api/me")).json()
    assert me["onboarding"]["next_step"] == "ai_notice"
    assert me["gmail"]["state"] == "not_connected"


async def test_onboarding_steps_advance_in_order(alice):
    _, client = alice
    await client.post("/api/me/ai-notice")
    assert (await client.get("/api/me")).json()["onboarding"]["next_step"] == "country"
    await client.put("/api/me/country", json={"country": "in"})
    me = (await client.get("/api/me")).json()
    assert me["country"] == "IN"
    assert me["onboarding"]["next_step"] == "documents"


async def test_users_in_eea_ch_uk_are_blocked_on_the_free_ai_tier(alice):
    _, client = alice
    await onboard(client, country="DE")
    me = (await client.get("/api/me")).json()
    assert me["onboarding"]["ai_region_blocked"] is True
    assert me["onboarding"]["next_step"] == "region_blocked"
    upload = await client.post(
        "/api/documents/text", json={"kind": "summary", "text": "Backend engineer, ten years."}
    )
    assert upload.status_code == 409


async def test_no_document_reaches_ai_before_the_notice_is_accepted(alice):
    _, client = alice
    await client.put("/api/me/country", json={"country": "IN"})
    response = await client.post(
        "/api/documents/text", json={"kind": "summary", "text": "Backend engineer, ten years."}
    )
    assert response.status_code == 409
    assert "AI data notice" in response.json()["error"]["message"]


async def test_old_ai_notice_acceptance_must_be_renewed(alice, db):
    user, client = alice
    user.ai_notice_accepted_at = datetime.now(UTC)
    user.ai_notice_version = "1"
    await db.commit()
    me = (await client.get("/api/me")).json()
    assert me["onboarding"]["ai_notice_accepted"] is False
    assert me["onboarding"]["next_step"] == "ai_notice"

    blocked = await client.post(
        "/api/documents/text",
        json={"kind": "summary", "text": "Backend engineer, ten years."},
    )
    assert blocked.status_code == 409

    accepted = await client.post("/api/me/ai-notice")
    assert accepted.status_code == 200
    me = (await client.get("/api/me")).json()
    assert me["onboarding"]["ai_notice_accepted"] is True
    assert me["onboarding"]["next_step"] == "country"


async def test_country_must_be_a_two_letter_code(alice):
    _, client = alice
    assert (await client.put("/api/me/country", json={"country": "India"})).status_code == 422


async def test_delete_account_removes_user_data_and_signs_out(alice, bob):
    _, client = alice
    _, bob_client = bob
    await onboard(client)
    await client.post(
        "/api/documents/text", json={"kind": "summary", "text": "Backend engineer, ten years."}
    )
    assert (await client.delete("/api/me")).status_code == 204
    assert (await client.get("/api/me")).status_code == 401
    assert (await bob_client.get("/api/me")).status_code == 200


async def test_me_points_to_the_extension_store_listing_once_set(alice, monkeypatch):
    _, client = alice
    assert (await client.get("/api/me")).json()["extension_store_url"] is None
    monkeypatch.setenv(
        "EXTENSION_STORE_URL", "https://chromewebstore.google.com/detail/jobweaver/abc"
    )
    get_settings.cache_clear()
    me = (await client.get("/api/me")).json()
    assert me["extension_store_url"] == "https://chromewebstore.google.com/detail/jobweaver/abc"
