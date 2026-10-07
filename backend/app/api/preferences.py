from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query

from app.api.deps import CurrentUser, DbSession, Gateway
from app.core.errors import NotFoundError
from app.schemas.preferences import PreferencesIn, PreferencesOut, TitleSuggestionsOut
from app.services import feed
from app.services import preferences as service
from app.services.pipeline import extract_skills_now

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


@router.get("")
async def get_preferences(db: DbSession, user: CurrentUser) -> PreferencesOut:
    preference = await service.get_preferences(db, user)
    if preference is None:
        raise NotFoundError("No preferences saved yet")
    return PreferencesOut.model_validate(preference, from_attributes=True)


@router.put("")
async def save_preferences(
    db: DbSession,
    user: CurrentUser,
    body: PreferencesIn,
    gateway: Gateway,
    background: BackgroundTasks,
) -> PreferencesOut:
    preference = await service.save_preferences(db, user, body)
    # The Feed follows the new Preferences at once, from Jobs already stored (FR-D1).
    await feed.sync_user_feed(db, user.id)
    await db.commit()
    background.add_task(extract_skills_now, gateway)
    return PreferencesOut.model_validate(preference, from_attributes=True)


@router.get("/title-suggestions")
async def title_suggestions(
    db: DbSession,
    user: CurrentUser,
    titles: Annotated[list[str], Query(max_length=20)],
) -> TitleSuggestionsOut:
    """Related titles to offer; only the ones the User adds are ever searched (FR-A3)."""
    preference = await service.get_preferences(db, user)
    return TitleSuggestionsOut(
        titles=service.suggested_titles([t[:100] for t in titles]),
        searches_per_title=await service.searches_per_title(db, preference),
    )
