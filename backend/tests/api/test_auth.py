from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import sign_payload
from app.models import User, UserSession
from app.models.user import Role
from app.services.google_oauth import GoogleProfile, GoogleTokens, get_google_client
from tests.conftest import make_client


class FakeGoogle:
    """Stands in for Google's OAuth endpoints."""

    def __init__(self, profile: GoogleProfile, scope: str = "openid email profile") -> None:
        self.profile = profile
        self.scope = scope
        self.revoked: list[str] = []

    def authorization_url(self, scopes, state, *, offline, login_hint=None):
        return f"https://accounts.example/auth?scope={'+'.join(scopes)}&state={state}&offline={offline}"

    async def exchange_code(self, code):
        return GoogleTokens("access", "refresh-token", self.scope)

    async def fetch_profile(self, access_token):
        return self.profile

    async def revoke(self, token):
        self.revoked.append(token)


@pytest.fixture
def google():
    from app.main import app

    fake = FakeGoogle(GoogleProfile("sub-1", "new@example.com", "New User", None))
    app.dependency_overrides[get_google_client] = lambda: fake
    return fake


def _state(response) -> str:
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


async def test_login_redirects_to_google_with_signed_state(anon, google):
    response = await anon.get("/api/auth/google/login", params={"next": "/onboarding"})
    assert response.status_code == 307
    assert response.headers["location"].startswith("https://accounts.example/auth")
    assert _state(response)


async def test_callback_creates_user_and_session_and_redirects(anon, google, db):
    login = await anon.get("/api/auth/google/login", params={"next": "/onboarding"})
    response = await anon.get(
        "/api/auth/google/callback", params={"code": "abc", "state": _state(login)}
    )
    assert response.status_code == 307
    assert response.headers["location"] == "http://testserver/onboarding"
    assert "jw_session" in response.cookies
    user = (await db.execute(select(User))).scalar_one()
    assert user.email == "new@example.com"
    assert user.role == Role.USER
    assert await db.scalar(select(func.count()).select_from(UserSession)) == 1


async def test_sign_up_is_open_and_admin_comes_from_config(anon, google, db):
    google.profile = GoogleProfile("sub-2", "admin@example.com", "Admin", None)
    login = await anon.get("/api/auth/google/login")
    await anon.get("/api/auth/google/callback", params={"code": "x", "state": _state(login)})
    user = (await db.execute(select(User))).scalar_one()
    assert user.role == Role.ADMIN


async def test_callback_rejects_tampered_state(anon, google):
    response = await anon.get(
        "/api/auth/google/callback", params={"code": "abc", "state": "forged.signature"}
    )
    assert response.status_code == 401


async def test_redirect_target_cannot_leave_the_site(anon, google):
    login = await anon.get("/api/auth/google/login", params={"next": "//evil.example/x"})
    response = await anon.get(
        "/api/auth/google/callback", params={"code": "abc", "state": _state(login)}
    )
    assert response.headers["location"] == "http://testserver/"


async def test_cancelled_consent_returns_to_app_with_error(anon, google):
    state = sign_payload({"purpose": "sign_in", "next": "/"}, 600)
    response = await anon.get(
        "/api/auth/google/callback", params={"error": "access_denied", "state": state}
    )
    assert response.headers["location"] == "http://testserver/?google_error=access_denied"


async def test_me_requires_a_session(anon):
    response = await anon.get("/api/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_logout_ends_the_session(alice):
    _, client = alice
    assert (await client.get("/api/me")).status_code == 200
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.get("/api/me")).status_code == 401


async def test_state_changing_requests_need_the_csrf_header(alice):
    _, client = alice
    response = await client.post("/api/me/ai-notice", headers={"X-CSRF-Token": "wrong"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


async def test_dev_login_is_off_unless_enabled(anon, monkeypatch):
    body = {"email": "dev@example.com"}
    assert (await anon.post("/api/auth/dev-login", json=body)).status_code == 404
    monkeypatch.setenv("DEV_LOGIN_ENABLED", "true")
    get_settings.cache_clear()
    response = await anon.post("/api/auth/dev-login", json=body)
    assert response.status_code == 204
    async with make_client(response.cookies["jw_session"]) as client:
        assert (await client.get("/api/me")).json()["email"] == "dev@example.com"


async def test_dev_login_never_works_in_production(anon, monkeypatch):
    monkeypatch.setenv("DEV_LOGIN_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    response = await anon.post("/api/auth/dev-login", json={"email": "dev@example.com"})
    assert response.status_code == 404
