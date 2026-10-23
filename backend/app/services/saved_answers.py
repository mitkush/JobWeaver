"""Saved Answers (ADR-0017): reused only within their scope, never across Companies."""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models.application_profile import SavedAnswer
from app.models.job import Job, UserJob
from app.models.posting import Company
from app.models.user import User
from app.schemas.application_profile import SavedAnswerIn

_NOISE = re.compile(r"[^\w\s]")
_OPTIONAL = re.compile(r"\((?:optional|required)\)", re.IGNORECASE)


def question_key(question: str) -> str:
    """ "What is your notice period? *" and "what is your notice period" are one question."""
    text = _OPTIONAL.sub(" ", question.casefold())
    return " ".join(_NOISE.sub(" ", text).split())[:255]


async def _owned(session: AsyncSession, user: User, answer_id: uuid.UUID) -> SavedAnswer:
    row = await session.scalar(
        select(SavedAnswer).where(SavedAnswer.id == answer_id, SavedAnswer.user_id == user.id)
    )
    if row is None:
        raise NotFoundError("Saved answer not found")
    return row


async def list_answers(session: AsyncSession, user: User) -> list[SavedAnswer]:
    return list(
        (
            await session.scalars(
                select(SavedAnswer)
                .where(SavedAnswer.user_id == user.id)
                .order_by(SavedAnswer.question_key, SavedAnswer.scope, SavedAnswer.created_at)
            )
        ).all()
    )


async def _apply(
    session: AsyncSession, user: User, row: SavedAnswer, body: SavedAnswerIn
) -> SavedAnswer:
    country = currency = period = company_id = None
    company_name = ""
    if body.scope == "country":
        if not body.country:
            raise ValidationFailedError("Choose the country this answer applies to")
        if (body.currency is None) != (body.period is None):
            raise ValidationFailedError("A salary needs both a currency and a period")
        country, currency, period = body.country, body.currency, body.period
    elif body.scope == "company":
        company = await session.get(Company, body.company_id) if body.company_id else None
        if company is None:
            raise ValidationFailedError("Choose the Company this answer applies to")
        company_id, company_name = company.id, company.name
    key = question_key(body.question)
    if not key:
        raise ValidationFailedError("Write the question this answer is for")
    duplicate = await session.scalar(
        select(SavedAnswer.id).where(
            SavedAnswer.user_id == user.id,
            SavedAnswer.question_key == key,
            SavedAnswer.scope == body.scope,
            SavedAnswer.country.is_not_distinct_from(country),
            SavedAnswer.currency.is_not_distinct_from(currency),
            SavedAnswer.period.is_not_distinct_from(period),
            SavedAnswer.company_id.is_not_distinct_from(company_id),
            SavedAnswer.id != row.id if row.id else True,
        )
    )
    if duplicate is not None:
        raise ConflictError("You already saved an answer to this question for the same scope")
    row.question, row.question_key, row.answer = body.question, key, body.answer
    row.scope, row.country, row.currency, row.period = body.scope, country, currency, period
    row.company_id, row.company_name, row.sensitive = company_id, company_name, body.sensitive
    return row


async def create(session: AsyncSession, user: User, body: SavedAnswerIn) -> SavedAnswer:
    row = await _apply(session, user, SavedAnswer(user_id=user.id, origin="user"), body)
    session.add(row)
    await session.flush()
    return row


async def update(
    session: AsyncSession, user: User, answer_id: uuid.UUID, body: SavedAnswerIn
) -> SavedAnswer:
    row = await _apply(session, user, await _owned(session, user, answer_id), body)
    await session.flush()
    return row


async def delete(session: AsyncSession, user: User, answer_id: uuid.UUID) -> None:
    await session.delete(await _owned(session, user, answer_id))


def job_countries(job: Job) -> set[str]:
    return {str(loc["country"]).upper() for loc in job.locations or [] if loc.get("country")}


async def applicable(session: AsyncSession, user: User, job_id: uuid.UUID) -> list[SavedAnswer]:
    """Answers usable for one of the User's Jobs: general ones, ones for a country the Job
    is in, and ones for the Job's own Company. Salary currency and period are returned for
    the caller to match against the form's question."""
    job = await session.scalar(
        select(Job)
        .join(UserJob, UserJob.job_id == Job.id)
        .where(Job.id == job_id, UserJob.user_id == user.id)
    )
    if job is None:
        raise NotFoundError("Job not found")
    countries = job_countries(job)
    return [
        row
        for row in await list_answers(session, user)
        if row.scope == "general"
        or (row.scope == "country" and row.country in countries)
        or (row.scope == "company" and row.company_id == job.company_id)
    ]
