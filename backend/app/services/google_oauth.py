"""Google OAuth: sign-in (profile scopes) and Gmail access (gmail.compose, ADR-0006)."""

import contextlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.errors import GoogleFlowError

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SIGN_IN_SCOPES = ["openid", "email", "profile"]
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"


@dataclass(frozen=True)
class GoogleTokens:
    access_token: str
    refresh_token: str | None
    scope: str


@dataclass(frozen=True)
class GoogleProfile:
    sub: str
    email: str
    name: str
    picture: str | None


class GoogleOAuthClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    def authorization_url(
        self, scopes: list[str], state: str, *, offline: bool, login_hint: str | None = None
    ) -> str:
        settings = get_settings()
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
            "include_granted_scopes": "true",
        }
        if offline:
            # Always re-consent so Google returns a fresh refresh token.
            params |= {"access_type": "offline", "prompt": "consent"}
        if login_hint:
            params["login_hint"] = login_hint
        return f"{AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> GoogleTokens:
        settings = get_settings()
        response = await self._call(
            "post",
            TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if response.status_code >= 400:
            raise GoogleFlowError("google_failed", "Google sign-in failed. Please try again.")
        body = _json(response)
        if "access_token" not in body:
            raise GoogleFlowError("google_failed", "Google sign-in failed. Please try again.")
        return GoogleTokens(body["access_token"], body.get("refresh_token"), body.get("scope", ""))

    async def fetch_profile(self, access_token: str) -> GoogleProfile:
        response = await self._call(
            "get", USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        if response.status_code >= 400:
            raise GoogleFlowError("google_failed", "Could not read your Google profile")
        body = _json(response)
        if not body.get("sub") or not body.get("email"):
            raise GoogleFlowError("google_failed", "Could not read your Google profile")
        if not body.get("email_verified", False):
            raise GoogleFlowError("email_unverified", "Your Google email address is not verified")
        return GoogleProfile(
            body["sub"], body["email"].lower(), body.get("name", ""), body.get("picture")
        )

    async def _call(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Network failures become a readable sign-in error instead of a server error."""
        try:
            return await self.http.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise GoogleFlowError("google_failed", "Google could not be reached") from exc

    async def revoke(self, token: str) -> None:
        # Best effort: the credential is deleted locally either way.
        with contextlib.suppress(httpx.HTTPError):
            await self.http.post(REVOKE_URL, data={"token": token})


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise GoogleFlowError("google_failed", "Google sent an unexpected response") from exc
    if not isinstance(body, dict):
        raise GoogleFlowError("google_failed", "Google sent an unexpected response")
    return body


_http = httpx.AsyncClient(timeout=httpx.Timeout(20.0))


def get_google_client() -> GoogleOAuthClient:
    return GoogleOAuthClient(_http)
