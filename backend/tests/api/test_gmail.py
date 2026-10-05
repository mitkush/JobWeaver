from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.core.security import decrypt
from app.models import OAuthCredential
from app.services.google_oauth import GMAIL_COMPOSE_SCOPE, GoogleProfile, get_google_client
from tests.api.test_auth import FakeGoogle


@pytest.fixture
def google(alice):
    from app.main import app

    user, _ = alice
    fake = FakeGoogle(
        GoogleProfile(user.google_sub, user.email, user.name, None),
        scope=f"openid email profile {GMAIL_COMPOSE_SCOPE}",
    )
    app.dependency_overrides[get_google_client] = lambda: fake
    return fake


async def connect(client) -> None:
    start = await client.get("/api/gmail/connect", params={"next": "/settings"})
    assert GMAIL_COMPOSE_SCOPE in start.headers["location"]
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    done = await client.get("/api/auth/google/callback", params={"code": "c", "state": state})
    assert done.headers["location"] == "http://testserver/settings?gmail=connected"


async def test_connect_stores_an_encrypted_refresh_token(alice, google, db):
    user, client = alice
    await connect(client)
    credential = (await db.execute(select(OAuthCredential))).scalar_one()
    assert credential.user_id == user.id
    assert credential.refresh_token_encrypted != "refresh-token"
    assert decrypt(credential.refresh_token_encrypted) == "refresh-token"
    me = (await client.get("/api/me")).json()
    assert me["gmail"]["state"] == "connected"
    assert me["onboarding"]["gmail_connected"] is True


async def test_status_warns_before_and_after_the_seven_day_expiry(alice, google, db):
    _, client = alice
    await connect(client)
    credential = (await db.execute(select(OAuthCredential))).scalar_one()
    credential.granted_at = datetime.now(UTC) - timedelta(days=6, hours=12)
    await db.commit()
    assert (await client.get("/api/me")).json()["gmail"]["state"] == "expires_soon"
    credential.granted_at = datetime.now(UTC) - timedelta(days=8)
    await db.commit()
    assert (await client.get("/api/me")).json()["gmail"]["state"] == "expired"


async def finish(client, next_path="/settings"):
    start = await client.get("/api/gmail/connect", params={"next": next_path})
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    return await client.get("/api/auth/google/callback", params={"code": "c", "state": state})


async def test_missing_gmail_scope_returns_to_the_app_with_a_reason(alice, google):
    _, client = alice
    google.scope = "openid email profile"
    response = await finish(client)
    assert response.headers["location"] == "http://testserver/settings?google_error=gmail_scope"


async def test_gmail_must_match_the_signed_in_account(alice, google):
    _, client = alice
    google.profile = GoogleProfile("someone-else", "other@example.com", "Other", None)
    response = await finish(client)
    assert response.headers["location"] == "http://testserver/settings?google_error=gmail_account"


async def test_redirect_keeps_the_existing_query(alice, google):
    _, client = alice
    response = await finish(client, "/onboarding/gmail?from=banner")
    assert response.headers["location"] == (
        "http://testserver/onboarding/gmail?from=banner&gmail=connected"
    )


async def test_cancelled_gmail_consent_is_encoded(alice, google):
    _, client = alice
    start = await client.get("/api/gmail/connect", params={"next": "/settings?x=1"})
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    response = await client.get(
        "/api/auth/google/callback", params={"error": "server error&x=2", "state": state}
    )
    assert response.headers["location"] == (
        "http://testserver/settings?x=1&google_error=google_failed"
    )


async def test_disconnect_revokes_and_deletes(alice, google, db):
    _, client = alice
    await connect(client)
    response = await client.delete("/api/gmail")
    assert response.json()["gmail"]["state"] == "not_connected"
    assert google.revoked == ["refresh-token"]
    assert (await db.execute(select(OAuthCredential))).first() is None


async def test_account_deletion_revokes_gmail(alice, google):
    _, client = alice
    await connect(client)
    assert (await client.delete("/api/me")).status_code == 204
    assert google.revoked == ["refresh-token"]


async def test_account_deletion_survives_an_unreadable_token(alice, google, db):
    _, client = alice
    await connect(client)
    credential = (await db.execute(select(OAuthCredential))).scalar_one()
    credential.refresh_token_encrypted = "not-a-fernet-token"
    await db.commit()
    assert (await client.delete("/api/me")).status_code == 204
    assert google.revoked == []
