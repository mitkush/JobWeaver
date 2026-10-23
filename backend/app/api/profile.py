"""Application profile and Saved Answers, edited in the web app (ADR-0017)."""

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.application_profile import (
    ProfileContent,
    ProfileOut,
    ProfileSave,
    SavedAnswerIn,
    SavedAnswerOut,
)
from app.services import application_profile, saved_answers

router = APIRouter(prefix="/api", tags=["profile"])


@router.get("/profile")
async def get_profile(db: DbSession, user: CurrentUser) -> ProfileOut:
    return await application_profile.get(db, user)


@router.get("/profile/suggestion")
async def profile_suggestion(db: DbSession, user: CurrentUser) -> ProfileContent:
    """Values from the Fact Bank and the Google account to review; nothing is saved."""
    return await application_profile.suggestion(db, user)


@router.put("/profile")
async def save_profile(db: DbSession, user: CurrentUser, body: ProfileSave) -> ProfileOut:
    result = await application_profile.save(db, user, body.content, body.expected_version)
    await db.commit()
    return result


@router.get("/saved-answers")
async def list_saved_answers(db: DbSession, user: CurrentUser) -> list[SavedAnswerOut]:
    rows = await saved_answers.list_answers(db, user)
    return [SavedAnswerOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/saved-answers", status_code=201)
async def create_saved_answer(
    db: DbSession, user: CurrentUser, body: SavedAnswerIn
) -> SavedAnswerOut:
    row = await saved_answers.create(db, user, body)
    await db.commit()
    await db.refresh(row)
    return SavedAnswerOut.model_validate(row, from_attributes=True)


@router.put("/saved-answers/{answer_id}")
async def update_saved_answer(
    db: DbSession, user: CurrentUser, answer_id: uuid.UUID, body: SavedAnswerIn
) -> SavedAnswerOut:
    row = await saved_answers.update(db, user, answer_id, body)
    await db.commit()
    await db.refresh(row)
    return SavedAnswerOut.model_validate(row, from_attributes=True)


@router.delete("/saved-answers/{answer_id}", status_code=204)
async def delete_saved_answer(db: DbSession, user: CurrentUser, answer_id: uuid.UUID) -> None:
    await saved_answers.delete(db, user, answer_id)
    await db.commit()
