from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.errors import GoogleFlowError
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
    assert response.headers["location"] == "http://testserver/sign-in?google_error=state"
    assert "jw_session" not in response.cookies


async def test_callback_link_opened_in_another_browser_does_not_sign_in(anon, google, db):
    """Login CSRF: an attacker's callback link must not sign the victim into their account."""
    login = await anon.get("/api/auth/google/login")
    async with make_client() as victim:  # has no jw_oauth cookie from this sign-in
        response = await victim.get(
            "/api/auth/google/callback", params={"code": "abc", "state": _state(login)}
        )
    assert response.headers["location"] == "http://testserver/sign-in?google_error=state"
    assert "jw_session" not in response.cookies
    assert (await db.execute(select(User))).first() is None


async def test_google_failures_return_to_sign_in_with_a_reason(anon, google):
    async def fail(code):
        raise GoogleFlowError("google_failed", "Google sign-in failed")

    google.exchange_code = fail
    login = await anon.get("/api/auth/google/login")
    response = await anon.get(
        "/api/auth/google/callback", params={"code": "abc", "state": _state(login)}
    )
    assert response.headers["location"] == "http://testserver/sign-in?google_error=google_failed"


async def test_redirect_target_cannot_leave_the_site(anon, google):
    login = await anon.get("/api/auth/google/login", params={"next": "//evil.example/x"})
    response = await anon.get(
        "/api/auth/google/callback", params={"code": "abc", "state": _state(login)}
    )
    assert response.headers["location"] == "http://testserver/"


async def test_cancelled_consent_returns_to_sign_in(anon, google):
    login = await anon.get("/api/auth/google/login")
    response = await anon.get(
        "/api/auth/google/callback", params={"error": "access_denied", "state": _state(login)}
    )
    assert response.headers["location"] == "http://testserver/sign-in?google_error=cancelled"


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


async def test_email_used_by_another_google_account_is_not_merged(anon, google, db):
    db.add(User(google_sub="old-sub", email="new@example.com"))
    await db.commit()
    login = await anon.get("/api/auth/google/login")
    response = await anon.get(
        "/api/auth/google/callback", params={"code": "abc", "state": _state(login)}
    )
    assert response.headers["location"] == (
        "http://testserver/sign-in?google_error=account_conflict"
    )
    assert "jw_session" not in response.cookies
