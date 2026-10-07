"""Application tracker (FR-F1), Follow-up Reminders (FR-F2) and Company history (FR-F3).

One Application per User and Job. Every status change is stored as a timestamped event.
Follow-up emails are written from a fixed template that uses only the Job, the Company
and the date applied, so nothing in them can be invented (ADR-0005); the User edits it
in Gmail and nothing is ever sent (ADR-0006)."""

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlencode

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.gmail import GmailClient, compose_url, raw_message
from app.core.errors import (
    GoogleFlowError,
    JobWeaverError,
    NotFoundError,
    PreconditionError,
    ValidationFailedError,
)
from app.models.draft import Application, ApplicationEvent, ApplicationStatus, GmailHandoff
from app.models.job import Job
from app.models.posting import Company
from app.models.user import User
from app.schemas.applications import (
    ApplicationOut,
    CompanyHistoryOut,
    EventOut,
    FollowUpIn,
    FollowUpOut,
    FollowUpResult,
    ReminderOut,
)
from app.services.email_check import check_recipient
from app.services.gmail import access_token
from app.services.google_oauth import GoogleOAuthClient

S = ApplicationStatus
# How far along an Application is. Offer and Rejected are both final outcomes, so between
# those two the more recent change wins.
PROGRESS = {S.DRAFTED: 0, S.APPLIED: 1, S.REPLIED: 2, S.INTERVIEW: 3, S.OFFER: 4, S.REJECTED: 4}


def utcnow() -> datetime:
    return datetime.now(UTC)


async def for_job(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID
) -> Application | None:
    return await session.scalar(
        select(Application).where(Application.user_id == user_id, Application.job_id == job_id)
    )


async def owned(session: AsyncSession, user: User, application_id: uuid.UUID) -> Application:
    application = await session.scalar(
        select(Application).where(Application.id == application_id, Application.user_id == user.id)
    )
    if application is None:
        raise NotFoundError("Application not found")
    return application


async def ensure(
    session: AsyncSession,
    user: User,
    job_id: uuid.UUID,
    draft_id: uuid.UUID | None,
    now: datetime | None = None,
) -> Application:
    """The Job's Application, created as Drafted on its first hand-off or Mark as applied."""
    now = now or utcnow()
    application = await for_job(session, user.id, job_id)
    if application is None:
        application = Application(
            user_id=user.id,
            job_id=job_id,
            draft_id=draft_id,
            status=S.DRAFTED,
            status_changed_at=now,
        )
        session.add(application)
        await session.flush()
        session.add(_event(user, application, S.DRAFTED))
    elif draft_id is not None:
        application.draft_id = draft_id
    await session.flush()
    return application


def _event(user: User, application: Application, status: str) -> ApplicationEvent:
    # Stamped from the clock, not the database: several changes in one transaction would
    # otherwise share now() and lose their order.
    return ApplicationEvent(
        user_id=user.id, application_id=application.id, status=status, created_at=utcnow()
    )


def change_status(
    session: AsyncSession, user: User, application: Application, status: str, now: datetime
) -> None:
    if status not in S.ALL:
        raise ValidationFailedError("Unknown application status")
    if status == application.status:
        return
    application.status = status
    application.status_changed_at = now
    if status == S.DRAFTED:
        # Moved back by hand: the User has not applied after all (FR-D5 stops warning).
        application.applied_at = None
    elif application.applied_at is None:
        # Replied, Interview, Offer and Rejected all mean the User applied.
        application.applied_at = now
    application.follow_up_after = (
        now + timedelta(days=user.follow_up_days) if status == S.APPLIED else None
    )
    session.add(_event(user, application, status))


async def mark_applied(
    session: AsyncSession, user: User, job_id: uuid.UUID, draft_id: uuid.UUID
) -> Application:
    now = utcnow()
    application = await ensure(session, user, job_id, draft_id, now)
    # A later status (Interview, Offer...) is never moved back by Mark as applied.
    if application.status == S.DRAFTED:
        change_status(session, user, application, S.APPLIED, now)
    await session.flush()
    return application


async def move_to_job(session: AsyncSession, gone_id: uuid.UUID, survivor_id: uuid.UUID) -> None:
    """Two Jobs became one (Correspondence): each User keeps one Application, with the
    history and hand-offs of both."""
    for gone in list(
        (await session.execute(select(Application).where(Application.job_id == gone_id))).scalars()
    ):
        kept = await for_job(session, gone.user_id, survivor_id)
        if kept is None:
            gone.job_id = survivor_id
            continue
        # The further-along Application wins; a newer but earlier status never does.
        gone_ahead = (PROGRESS[gone.status], gone.status_changed_at) > (
            PROGRESS[kept.status],
            kept.status_changed_at,
        )
        if gone_ahead:
            kept.status, kept.status_changed_at = gone.status, gone.status_changed_at
            kept.follow_up_after = gone.follow_up_after
            kept.draft_id = gone.draft_id or kept.draft_id
        applied = [a for a in (kept.applied_at, gone.applied_at) if a is not None]
        kept.applied_at = min(applied) if applied else None
        for model in (ApplicationEvent, GmailHandoff):
            await session.execute(
                update(model)
                .where(model.application_id == gone.id)
                .values(application_id=kept.id)
                .execution_options(synchronize_session=False)
            )
        await session.delete(gone)
    await session.flush()


# Read models ------------------------------------------------------------------------------


async def _out(
    session: AsyncSession, user: User, rows: list[tuple[Application, Job]], now: datetime
) -> list[ApplicationOut]:
    ids = [application.id for application, _ in rows]
    history: dict[uuid.UUID, list[EventOut]] = {i: [] for i in ids}
    if ids:
        events = await session.execute(
            select(ApplicationEvent)
            .where(ApplicationEvent.user_id == user.id, ApplicationEvent.application_id.in_(ids))
            .order_by(ApplicationEvent.created_at, ApplicationEvent.id)
        )
        for event in events.scalars():
            history[event.application_id].append(EventOut(status=event.status, at=event.created_at))
    return [
        ApplicationOut(
            id=application.id,
            job_id=job.id,
            draft_id=application.draft_id,
            title=job.title,
            company=job.company_name,
            company_id=job.company_id,
            job_expired=job.expired_at is not None,
            status=application.status,
            applied_at=application.applied_at,
            status_changed_at=application.status_changed_at,
            follow_up_due=_due(application, now),
            history=history[application.id],
        )
        for application, job in rows
    ]


def _due(application: Application, now: datetime) -> bool:
    return (
        application.status == S.APPLIED
        and application.follow_up_after is not None
        and application.follow_up_after <= now
    )


async def tracker(
    session: AsyncSession, user: User, now: datetime | None = None
) -> list[ApplicationOut]:
    now = now or utcnow()
    rows = await session.execute(
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(Application.user_id == user.id)
        .order_by(Application.status_changed_at.desc(), Application.id)
    )
    return await _out(session, user, [tuple(row) for row in rows], now)


async def set_status(
    session: AsyncSession, user: User, application_id: uuid.UUID, status: str
) -> ApplicationOut:
    application = await owned(session, user, application_id)
    now = utcnow()
    change_status(session, user, application, status, now)
    await session.flush()
    job = await session.get(Job, application.job_id)
    assert job is not None
    return (await _out(session, user, [(application, job)], now))[0]


async def company_history(
    session: AsyncSession, user: User, company_id: uuid.UUID, now: datetime | None = None
) -> CompanyHistoryOut:
    company = await session.get(Company, company_id)
    if company is None:
        raise NotFoundError("Company not found")
    rows = await session.execute(
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(Application.user_id == user.id, Job.company_id == company_id)
        .order_by(Application.status_changed_at.desc(), Application.id)
    )
    return CompanyHistoryOut(
        id=company.id,
        name=company.name,
        applications=await _out(session, user, [tuple(row) for row in rows], now or utcnow()),
    )


async def reminders(
    session: AsyncSession, user: User, now: datetime | None = None
) -> list[ReminderOut]:
    now = now or utcnow()
    rows = await session.execute(
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(
            Application.user_id == user.id,
            Application.status == S.APPLIED,
            Application.follow_up_after <= now,
        )
        .order_by(Application.applied_at, Application.id)
    )
    return [
        ReminderOut(
            application_id=application.id,
            job_id=job.id,
            title=job.title,
            company=job.company_name,
            applied_at=application.applied_at or application.status_changed_at,
            days_waiting=(now - application.status_changed_at).days,
        )
        for application, job in rows
    ]


async def dismiss_reminder(session: AsyncSession, user: User, application_id: uuid.UUID) -> None:
    """Hides the reminder for another follow-up period."""
    application = await owned(session, user, application_id)
    if application.status != S.APPLIED:
        raise PreconditionError("Only Applied Applications have follow-up reminders")
    application.follow_up_after = utcnow() + timedelta(days=user.follow_up_days)
    await session.flush()


# Follow-up emails ---------------------------------------------------------------------------


async def follow_up(session: AsyncSession, user: User, application_id: uuid.UUID) -> FollowUpOut:
    application = await owned(session, user, application_id)
    if application.status != S.APPLIED:
        raise PreconditionError("Follow-ups are for Applications still waiting for a reply")
    job = await session.get(Job, application.job_id)
    assert job is not None
    recipient = await session.scalar(
        select(GmailHandoff.recipient)
        .where(
            GmailHandoff.user_id == user.id,
            GmailHandoff.application_id == application.id,
            GmailHandoff.kind == "application",
        )
        .order_by(GmailHandoff.created_at.desc())
        .limit(1)
    )
    applied = application.applied_at or application.status_changed_at
    body = (
        f"Dear hiring team,\n\n"
        f"I applied for the {job.title} role at {job.company_name} on "
        f"{applied:%d %B %Y} and wanted to follow up. I am still very interested in the role "
        f"and would welcome the chance to discuss it.\n\n"
        f"Thank you for your time.\n\n"
        f"Best regards,\n{user.name}"
    )
    return FollowUpOut(
        recipient=recipient or job.contact_email,
        subject=f"Following up: {job.title} application",
        body=body,
    )


async def send_follow_up_to_gmail(
    session: AsyncSession,
    user: User,
    application_id: uuid.UUID,
    body: FollowUpIn,
    google: GoogleOAuthClient,
    gmail: GmailClient,
) -> FollowUpResult:
    """Creates a Gmail draft (never sends). Falls back to a prefilled compose link."""
    application = await owned(session, user, application_id)
    if application.status != S.APPLIED:
        raise PreconditionError("Follow-ups are for Applications still waiting for a reply")
    if not body.confirm:
        raise PreconditionError("Confirm the recipient before opening Gmail")
    check = await check_recipient(body.recipient)
    if check.warnings and not body.confirm_email_warning:
        raise PreconditionError(
            "Confirm the email warning before continuing: " + "; ".join(check.warnings)
        )
    subject = " ".join(body.subject.split())
    url = compose_url(user.email, check.recipient, subject, body.body)
    mode = "fallback"
    gmail_id = None
    try:
        token = await access_token(session, user, google)
        gmail_id = await gmail.create_draft(
            token, raw_message(user.email, check.recipient, subject, body.body)
        )
        mode = "gmail"
        url = f"https://mail.google.com/mail/u/{quote(user.email, safe='')}/#drafts"
    except GoogleFlowError:
        # Gmail access ended: nothing is recorded and the reminder stays until it works.
        return FollowUpResult(
            mode="reconnect",
            url="/api/gmail/connect?" + urlencode({"next": "/applications"}),
            message="Connect Gmail again, then draft the follow-up again.",
        )
    except JobWeaverError:
        gmail_id = None
    session.add(
        GmailHandoff(
            user_id=user.id,
            application_id=application.id,
            kind="follow_up",
            recipient=check.recipient,
            gmail_draft_id=gmail_id,
        )
    )
    # The reminder comes back only if there is still no reply after another period.
    application.follow_up_after = utcnow() + timedelta(days=user.follow_up_days)
    await session.flush()
    return FollowUpResult(
        mode=mode,
        url=url,
        message=(
            "Your follow-up is in Gmail Drafts. Review it there before sending."
            if mode == "gmail"
            else "Gmail is unavailable. Open compose to send the follow-up yourself."
        ),
    )
