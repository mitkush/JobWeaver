"""Application tracker, Follow-up Reminders and Company history (Epic F)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.adapters.gmail import GmailClient, get_gmail_client
from app.api.deps import CurrentUser, DbSession, Google
from app.schemas.applications import (
    ApplicationOut,
    CompanyHistoryOut,
    FollowUpIn,
    FollowUpOut,
    FollowUpResult,
    ReminderOut,
    StatusIn,
)
from app.services import applications

router = APIRouter(prefix="/api", tags=["applications"])
Gmail = Annotated[GmailClient, Depends(get_gmail_client)]


@router.get("/applications")
async def list_applications(db: DbSession, user: CurrentUser) -> list[ApplicationOut]:
    return await applications.tracker(db, user)


@router.patch("/applications/{application_id}")
async def set_status(
    db: DbSession, user: CurrentUser, application_id: uuid.UUID, body: StatusIn
) -> ApplicationOut:
    result = await applications.set_status(db, user, application_id, body.status)
    await db.commit()
    return result


@router.get("/reminders")
async def list_reminders(db: DbSession, user: CurrentUser) -> list[ReminderOut]:
    return await applications.reminders(db, user)


@router.post("/applications/{application_id}/follow-up/dismiss", status_code=204)
async def dismiss(db: DbSession, user: CurrentUser, application_id: uuid.UUID) -> None:
    await applications.dismiss_reminder(db, user, application_id)
    await db.commit()


@router.get("/applications/{application_id}/follow-up")
async def follow_up(db: DbSession, user: CurrentUser, application_id: uuid.UUID) -> FollowUpOut:
    return await applications.follow_up(db, user, application_id)


@router.post("/applications/{application_id}/follow-up")
async def follow_up_to_gmail(
    db: DbSession,
    user: CurrentUser,
    application_id: uuid.UUID,
    body: FollowUpIn,
    google: Google,
    gmail: Gmail,
) -> FollowUpResult:
    result = await applications.send_follow_up_to_gmail(
        db, user, application_id, body, google, gmail
    )
    await db.commit()
    return result


@router.get("/companies/{company_id}/applications")
async def company_history(
    db: DbSession, user: CurrentUser, company_id: uuid.UUID
) -> CompanyHistoryOut:
    return await applications.company_history(db, user, company_id)
