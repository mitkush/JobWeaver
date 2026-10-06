import hmac
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Cookie, Query, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr

from app.api.deps import CSRF_COOKIE, SESSION_COOKIE, DbSession, Google
from app.core.config import get_settings
from app.core.errors import AuthError, GoogleFlowError, NotFoundError
from app.core.security import new_token, sign_payload, verify_payload
from app.services import auth as auth_service
from app.services.gmail import store_gmail_credential
from app.services.google_oauth import (
    GMAIL_COMPOSE_SCOPE,
    SIGN_IN_SCOPES,
    GoogleOAuthClient,
    GoogleProfile,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
STATE_MAX_AGE = 600
# Ties the OAuth state to the browser that started the flow (login CSRF protection).
OAUTH_NONCE_COOKIE = "jw_oauth"


def _safe_next(next_path: str | None) -> str:
    # Only same-site relative paths, so the redirect cannot be abused.
    if next_path and next_path.startswith("/") and not next_path.startswith("//"):
        return next_path
    return "/"


def app_url(path: str, **params: str) -> str:
    """Absolute app URL for `path`, merging `params` into any query it already has."""
    parts = urlsplit(_safe_next(path))
    query = urlencode(dict(parse_qsl(parts.query)) | params)
    return get_settings().public_url + urlunsplit(("", "", parts.path, query, parts.fragment))


def set_session_cookies(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
    )
    set_csrf_cookie(response)


def set_csrf_cookie(response: Response, token: str | None = None) -> str:
    token = token or new_token()
    response.set_cookie(CSRF_COOKIE, token, secure=get_settings().secure_cookies, samesite="lax")
    return token


def start_oauth(
    google: GoogleOAuthClient,
    payload: dict[str, object],
    scopes: list[str],
    *,
    offline: bool,
    login_hint: str | None = None,
) -> RedirectResponse:
    nonce = new_token()
    state = sign_payload(payload | {"nonce": nonce}, STATE_MAX_AGE)
    response = RedirectResponse(
        google.authorization_url(scopes, state, offline=offline, login_hint=login_hint)
    )
    # Lax cookies are sent on Google's top-level redirect back to the callback.
    response.set_cookie(
        OAUTH_NONCE_COOKIE,
        nonce,
        max_age=STATE_MAX_AGE,
        httponly=True,
        secure=get_settings().secure_cookies,
        samesite="lax",
        path="/api/",
    )
    return response


class CsrfOut(BaseModel):
    csrf_token: str


@router.get("/csrf")
async def csrf(response: Response) -> CsrfOut:
    return CsrfOut(csrf_token=set_csrf_cookie(response))


@router.get("/google/login")
async def google_login(google: Google, next: str | None = None) -> RedirectResponse:
    payload = {"purpose": "sign_in", "next": _safe_next(next)}
    return start_oauth(google, payload, SIGN_IN_SCOPES, offline=False)


@router.get("/google/callback")
async def google_callback(
    db: DbSession,
    google: Google,
    state: str,
    code: str | None = None,
    error: Annotated[str | None, Query()] = None,
    jw_oauth: Annotated[str | None, Cookie()] = None,
) -> RedirectResponse:
    """One redirect URI for both sign-in and Gmail connection; the state says which.
    Every failure returns to the app with a readable reason, never a raw error page."""
    try:
        payload = verify_payload(state)
    except AuthError:
        return _finish(RedirectResponse(app_url("/sign-in", google_error="state")))
    nonce = str(payload.get("nonce", ""))
    if not jw_oauth or not hmac.compare_digest(nonce, jw_oauth):
        # The callback was opened in a browser that did not start this sign-in.
        return _finish(RedirectResponse(app_url("/sign-in", google_error="state")))

    gmail = payload.get("purpose") == "gmail"
    next_path = _safe_next(str(payload.get("next", "/")))
    failure_path = next_path if gmail else "/sign-in"
    if error or not code:
        reason = "cancelled" if error in (None, "access_denied") else "google_failed"
        return _finish(RedirectResponse(app_url(failure_path, google_error=reason)))

    try:
        tokens = await google.exchange_code(code)
        profile = await google.fetch_profile(tokens.access_token)
        if gmail:
            user = await auth_service.get_user_by_google_sub(db, profile.sub)
            if user is None or str(user.id) != payload.get("user_id"):
                raise GoogleFlowError(
                    "gmail_account", "Connect Gmail with the Google account you signed in with"
                )
            await store_gmail_credential(db, user, tokens)
            await db.commit()
            return _finish(RedirectResponse(app_url(next_path, gmail="connected")))

        user = await auth_service.upsert_google_user(db, profile)
        token = await auth_service.create_session(db, user)
        await db.commit()
    except GoogleFlowError as exc:
        await db.rollback()
        return _finish(RedirectResponse(app_url(failure_path, google_error=exc.reason)))

    response = _finish(RedirectResponse(app_url(next_path)))
    set_session_cookies(response, token)
    return response


def _finish(response: RedirectResponse) -> RedirectResponse:
    response.delete_cookie(OAUTH_NONCE_COOKIE, path="/api/")
    return response


@router.post("/logout", status_code=204)
async def logout(
    db: DbSession, response: Response, jw_session: Annotated[str | None, Cookie()] = None
) -> None:
    if jw_session:
        await auth_service.end_session(db, jw_session)
        await db.commit()
    response.delete_cookie(SESSION_COOKIE)


class DevLoginIn(BaseModel):
    email: EmailStr
    name: str = "Dev User"


@router.post("/dev-login", status_code=204)
async def dev_login(db: DbSession, body: DevLoginIn, response: Response) -> None:
    """Local development only: sign in without Google. Disabled unless explicitly enabled."""
    settings = get_settings()
    if not settings.dev_login_enabled or settings.environment == "production":
        raise NotFoundError("Not found")
    profile = GoogleProfile(f"dev:{body.email.lower()}", body.email.lower(), body.name, None)
    user = await auth_service.upsert_google_user(db, profile)
    token = await auth_service.create_session(db, user)
    await db.commit()
    set_session_cookies(response, token)


def gmail_connect(
    google: GoogleOAuthClient, user_id: str, email: str, next_path: str
) -> RedirectResponse:
    payload = {"purpose": "gmail", "user_id": user_id, "next": _safe_next(next_path)}
    return start_oauth(
        google, payload, [*SIGN_IN_SCOPES, GMAIL_COMPOSE_SCOPE], offline=True, login_hint=email
    )
