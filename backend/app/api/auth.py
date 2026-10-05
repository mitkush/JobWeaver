from typing import Annotated

from fastapi import APIRouter, Cookie, Query, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr

from app.api.deps import CSRF_COOKIE, SESSION_COOKIE, DbSession, Google
from app.core.config import get_settings
from app.core.errors import AuthError, NotFoundError
from app.core.security import new_token, sign_payload, verify_payload
from app.services import auth as auth_service
from app.services.gmail import store_gmail_credential
from app.services.google_oauth import GMAIL_COMPOSE_SCOPE, SIGN_IN_SCOPES, GoogleProfile

router = APIRouter(prefix="/api/auth", tags=["auth"])
STATE_MAX_AGE = 600


def _safe_next(next_path: str | None) -> str:
    # Only same-site relative paths, so the redirect cannot be abused.
    if next_path and next_path.startswith("/") and not next_path.startswith("//"):
        return next_path
    return "/"


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


class CsrfOut(BaseModel):
    csrf_token: str


@router.get("/csrf")
async def csrf(response: Response) -> CsrfOut:
    return CsrfOut(csrf_token=set_csrf_cookie(response))


@router.get("/google/login")
async def google_login(google: Google, next: str | None = None) -> RedirectResponse:
    state = sign_payload({"purpose": "sign_in", "next": _safe_next(next)}, STATE_MAX_AGE)
    return RedirectResponse(google.authorization_url(SIGN_IN_SCOPES, state, offline=False))


@router.get("/google/callback")
async def google_callback(
    db: DbSession,
    google: Google,
    state: str,
    code: str | None = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """One redirect URI for both sign-in and Gmail connection; the state says which."""
    payload = verify_payload(state)
    next_path = _safe_next(str(payload.get("next", "/")))
    base = get_settings().public_url
    if error or not code:
        return RedirectResponse(f"{base}{next_path}?google_error={error or 'cancelled'}")
    tokens = await google.exchange_code(code)

    if payload.get("purpose") == "gmail":
        profile = await google.fetch_profile(tokens.access_token)
        user = await auth_service.get_user_by_google_sub(db, profile.sub)
        if user is None or str(user.id) != payload.get("user_id"):
            raise AuthError("Connect Gmail with the same Google account you signed in with")
        await store_gmail_credential(db, user, tokens)
        await db.commit()
        return RedirectResponse(f"{base}{next_path}?gmail=connected")

    profile = await google.fetch_profile(tokens.access_token)
    user = await auth_service.upsert_google_user(db, profile)
    token = await auth_service.create_session(db, user)
    await db.commit()
    response = RedirectResponse(f"{base}{next_path}")
    set_session_cookies(response, token)
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


def gmail_connect_url(google: Google, user_id: str, email: str, next_path: str) -> str:
    state = sign_payload(
        {"purpose": "gmail", "user_id": user_id, "next": _safe_next(next_path)}, STATE_MAX_AGE
    )
    return google.authorization_url(
        [*SIGN_IN_SCOPES, GMAIL_COMPOSE_SCOPE], state, offline=True, login_hint=email
    )
