from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.errors import NotFoundError
from app.schemas.preferences import PreferencesIn, PreferencesOut
from app.services import preferences as service

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


@router.get("")
async def get_preferences(db: DbSession, user: CurrentUser) -> PreferencesOut:
    preference = await service.get_preferences(db, user)
    if preference is None:
        raise NotFoundError("No preferences saved yet")
    return PreferencesOut.model_validate(preference, from_attributes=True)


@router.put("")
async def save_preferences(db: DbSession, user: CurrentUser, body: PreferencesIn) -> PreferencesOut:
    preference = await service.save_preferences(db, user, body)
    await db.commit()
    return PreferencesOut.model_validate(preference, from_attributes=True)
