from fastapi import APIRouter, Response
from fastapi.responses import RedirectResponse

from app.api.auth import gmail_connect_url
from app.api.deps import SESSION_COOKIE, CurrentUser, DbSession, Google
from app.schemas.me import CountryIn, MeOut
from app.services import accounts
from app.services.gmail import disconnect_gmail

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me")
async def get_me(db: DbSession, user: CurrentUser) -> MeOut:
    return await accounts.build_me(db, user)


@router.post("/me/ai-notice")
async def accept_ai_notice(db: DbSession, user: CurrentUser) -> MeOut:
    await accounts.accept_ai_notice(db, user)
    await db.commit()
    return await accounts.build_me(db, user)


@router.put("/me/country")
async def set_country(db: DbSession, user: CurrentUser, body: CountryIn) -> MeOut:
    await accounts.set_country(db, user, body.country)
    await db.commit()
    return await accounts.build_me(db, user)


@router.delete("/me", status_code=204)
async def delete_me(db: DbSession, user: CurrentUser, google: Google, response: Response) -> None:
    await accounts.delete_account(db, user, google)
    await db.commit()
    response.delete_cookie(SESSION_COOKIE)


@router.get("/gmail/connect")
async def connect_gmail(
    user: CurrentUser, google: Google, next: str = "/settings"
) -> RedirectResponse:
    return RedirectResponse(gmail_connect_url(google, str(user.id), user.email, next))


@router.delete("/gmail")
async def disconnect(db: DbSession, user: CurrentUser, google: Google) -> MeOut:
    await disconnect_gmail(db, user, google)
    await db.commit()
    return await accounts.build_me(db, user)
