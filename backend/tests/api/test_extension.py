"""Application Extension connection (ADR-0017): approval, exchange and bearer access."""

import secrets
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.main import app
from app.models import ExtensionCredential, ExtensionGrant
from app.services.extension import s256

EXT = "abcdefghijklmnopabcdefghijklmnop"
OTHER_EXT = "ponmlkjihgfedcbaponmlkjihgfedcba"
ORIGIN = f"chrome-extension://{EXT}"


@pytest.fixture(autouse=True)
def _allowed_extension(monkeypatch) -> None:
    monkeypatch.setenv("EXTENSION_IDS", f"{EXT},{OTHER_EXT}")
    get_settings.cache_clear()


def ext_client(origin: str | None = ORIGIN, token: str | None = None) -> httpx.AsyncClient:
    """The extension's service worker: no cookies, its own origin, a bearer credential."""
    headers = {}
    if origin:
        headers["Origin"] = origin
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=headers
    )


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    return verifier, s256(verifier)


async def approve(client: httpx.AsyncClient, challenge: str, extension_id: str = EXT) -> str:
    response = await client.post(
        "/api/extension/approve", json={"extension_id": extension_id, "challenge": challenge}
    )
    assert response.status_code == 200, response.text
    return response.json()["code"]


async def connect(client: httpx.AsyncClient) -> str:
    verifier, challenge = pkce()
    code = await approve(client, challenge)
    async with ext_client() as ext:
        response = await ext.post("/api/ext/token", json={"code": code, "verifier": verifier})
    assert response.status_code == 200, response.text
    return response.json()["token"]


async def test_the_approved_extension_connects_and_reads_its_user(alice):
    user, client = alice
    verifier, challenge = pkce()
    code = await approve(client, challenge)
    async with ext_client() as ext:
        response = await ext.post("/api/ext/token", json={"code": code, "verifier": verifier})
        assert response.status_code == 200
        body = response.json()
        assert body["user"] == {"name": user.name, "email": user.email}
        async with ext_client(token=body["token"]) as authed:
            me = await authed.get("/api/ext/me")
    assert me.status_code == 200
    assert me.json()["email"] == user.email
    listed = (await client.get("/api/extension/connections")).json()
    assert [c["extension_id"] for c in listed] == [EXT]


async def test_a_code_works_once_and_a_replay_revokes_the_connection(alice, db):
    _, client = alice
    verifier, challenge = pkce()
    code = await approve(client, challenge)
    async with ext_client() as ext:
        first = await ext.post("/api/ext/token", json={"code": code, "verifier": verifier})
        replay = await ext.post("/api/ext/token", json={"code": code, "verifier": verifier})
        assert first.status_code == 200
        assert replay.status_code == 401
        async with ext_client(token=first.json()["token"]) as authed:
            assert (await authed.get("/api/ext/me")).status_code == 401


async def test_a_wrong_verifier_spends_the_code(alice):
    _, client = alice
    verifier, challenge = pkce()
    code = await approve(client, challenge)
    async with ext_client() as ext:
        wrong = await ext.post("/api/ext/token", json={"code": code, "verifier": pkce()[0]})
        right = await ext.post("/api/ext/token", json={"code": code, "verifier": verifier})
    assert wrong.status_code == 401
    assert right.status_code == 401


async def test_an_expired_code_is_refused(alice, db):
    _, client = alice
    verifier, challenge = pkce()
    code = await approve(client, challenge)
    await db.execute(
        update(ExtensionGrant).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db.commit()
    async with ext_client() as ext:
        response = await ext.post("/api/ext/token", json={"code": code, "verifier": verifier})
    assert response.status_code == 401
    assert "expired" in response.json()["error"]["message"]


@pytest.mark.parametrize(
    "origin", [None, "http://testserver", "https://evil.example", f"chrome-extension://{OTHER_EXT}"]
)
async def test_only_the_bound_extension_origin_can_exchange_a_code(alice, origin):
    _, client = alice
    verifier, challenge = pkce()
    code = await approve(client, challenge)
    async with ext_client(origin=origin) as other:
        response = await other.post("/api/ext/token", json={"code": code, "verifier": verifier})
    assert response.status_code == 403
    # Not spent by the wrong caller: the real extension can still finish.
    async with ext_client() as ext:
        ok = await ext.post("/api/ext/token", json={"code": code, "verifier": verifier})
    assert ok.status_code == 200


async def test_a_credential_is_refused_from_another_origin(alice):
    _, client = alice
    token = await connect(client)
    async with ext_client(origin="https://evil.example", token=token) as page:
        assert (await page.get("/api/ext/me")).status_code == 403


async def test_expired_credentials_and_unapproved_extensions_are_refused(alice, db, monkeypatch):
    _, client = alice
    token = await connect(client)
    await db.execute(
        update(ExtensionCredential).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db.commit()
    async with ext_client(token=token) as ext:
        assert (await ext.get("/api/ext/me")).status_code == 401

    fresh = await connect(client)
    monkeypatch.setenv("EXTENSION_IDS", OTHER_EXT)
    get_settings.cache_clear()
    async with ext_client(token=fresh) as ext:
        assert (await ext.get("/api/ext/me")).status_code == 401


async def test_unapproved_or_malformed_extension_ids_cannot_be_approved(alice, monkeypatch):
    _, client = alice
    _, challenge = pkce()
    bad = await client.post(
        "/api/extension/approve", json={"extension_id": "not-an-id", "challenge": challenge}
    )
    assert bad.status_code == 422
    monkeypatch.setenv("EXTENSION_IDS", "")
    get_settings.cache_clear()
    off = await client.post(
        "/api/extension/approve", json={"extension_id": EXT, "challenge": challenge}
    )
    assert off.status_code == 403


async def test_approving_needs_a_signed_in_user_and_the_csrf_check(alice, anon):
    _, challenge = pkce()
    body = {"extension_id": EXT, "challenge": challenge}
    assert (await anon.post("/api/extension/approve", json=body)).status_code == 401
    _, client = alice
    no_csrf = await client.post("/api/extension/approve", json=body, headers={"X-CSRF-Token": ""})
    assert no_csrf.status_code == 403


async def test_the_session_cookie_never_authorises_the_extension_surface(alice):
    _, client = alice
    assert (await client.get("/api/ext/me")).status_code == 401


async def test_revoking_in_settings_and_disconnecting_end_access_at_once(alice):
    _, client = alice
    revoked = await connect(client)
    [connection] = (await client.get("/api/extension/connections")).json()
    revoke = await client.delete(f"/api/extension/connections/{connection['id']}")
    assert revoke.status_code == 204
    async with ext_client(token=revoked) as ext:
        assert (await ext.get("/api/ext/me")).status_code == 401
    assert (await client.get("/api/extension/connections")).json() == []

    disconnected = await connect(client)
    async with ext_client(token=disconnected) as ext:
        assert (await ext.delete("/api/ext/token")).status_code == 204
        assert (await ext.get("/api/ext/me")).status_code == 401


async def test_users_only_see_and_revoke_their_own_connections(alice, bob, db):
    alice_user, a = alice
    _, b = bob
    alice_token = await connect(a)
    bob_token = await connect(b)
    [alice_connection] = (await a.get("/api/extension/connections")).json()
    bobs = (await b.get("/api/extension/connections")).json()
    assert len(bobs) == 1
    assert alice_connection["id"] != bobs[0]["id"]

    stolen = await b.delete(f"/api/extension/connections/{alice_connection['id']}")
    assert stolen.status_code == 404
    async with ext_client(token=alice_token) as ext:
        assert (await ext.get("/api/ext/me")).json()["email"] == alice_user.email
    async with ext_client(token=bob_token) as ext:
        assert (await ext.get("/api/ext/me")).json()["email"] == "bob@example.com"


async def test_a_code_approved_by_one_user_never_signs_in_another(alice, bob):
    alice_user, a = alice
    verifier, challenge = pkce()
    code = await approve(a, challenge)
    async with ext_client() as ext:
        token = (await ext.post("/api/ext/token", json={"code": code, "verifier": verifier})).json()
        assert token["user"]["email"] == alice_user.email


async def test_deleting_the_account_removes_its_connections(alice, db):
    _, client = alice
    token = await connect(client)
    assert (await client.delete("/api/me")).status_code == 204
    assert (await db.scalars(select(ExtensionCredential))).all() == []
    async with ext_client(token=token) as ext:
        assert (await ext.get("/api/ext/me")).status_code == 401
