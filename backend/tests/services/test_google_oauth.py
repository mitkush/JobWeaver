from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.core.errors import AuthError
from app.services.google_oauth import GMAIL_COMPOSE_SCOPE, GoogleOAuthClient


def google_with(handler) -> GoogleOAuthClient:
    return GoogleOAuthClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_gmail_url_asks_for_offline_access_and_fresh_consent():
    url = google_with(lambda r: httpx.Response(200)).authorization_url(
        [GMAIL_COMPOSE_SCOPE], "state-1", offline=True, login_hint="a@example.com"
    )
    query = parse_qs(urlparse(url).query)
    assert query["access_type"] == ["offline"] and query["prompt"] == ["consent"]
    assert query["redirect_uri"] == ["http://testserver/api/auth/google/callback"]
    assert query["login_hint"] == ["a@example.com"]


async def test_exchange_and_profile():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "at", "scope": "openid"})
        return httpx.Response(
            200, json={"sub": "1", "email": "A@Example.com", "email_verified": True}
        )

    google = google_with(handler)
    tokens = await google.exchange_code("code")
    assert tokens.refresh_token is None
    profile = await google.fetch_profile(tokens.access_token)
    assert profile.email == "a@example.com"


async def test_unverified_email_and_bad_code_are_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(200, json={"sub": "1", "email": "a@x.com", "email_verified": False})

    google = google_with(handler)
    with pytest.raises(AuthError):
        await google.exchange_code("bad")
    with pytest.raises(AuthError):
        await google.fetch_profile("at")


async def test_revoke_is_best_effort():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    await google_with(handler).revoke("token")


async def test_network_errors_become_readable_sign_in_errors():
    from app.core.errors import GoogleFlowError

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow")

    with pytest.raises(GoogleFlowError) as error:
        await google_with(handler).exchange_code("code")
    assert error.value.reason == "google_failed"

    with pytest.raises(GoogleFlowError):
        await google_with(lambda r: httpx.Response(200, text="<html>")).fetch_profile("at")
