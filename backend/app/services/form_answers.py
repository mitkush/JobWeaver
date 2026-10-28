"""Answers to an application form's own questions (ADR-0017).

Order of preference for each question: a Saved Answer within its scope, then (unless the
form forbids AI-written answers) a Suggestion written only from the User's Facts, else the
relevant Facts as notes. Two rules are code, not prompt: sensitive questions are answered
only from Saved Answers, and a form that refuses AI answers gets notes, never prose."""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import GatewayError, NotFoundError, PreconditionError
from app.gateway.base import BaseAIGateway
from app.gateway.schemas import AnswerQuestionsRequest, FormQuestion
from app.models.application_profile import SavedAnswer
from app.models.draft import Draft, DraftVersion
from app.models.job import Job, UserJob
from app.models.posting import Posting
from app.models.user import User
from app.schemas.form_answers import AnswerOut, QuestionIn
from app.services import drafting, saved_answers, writing_style
from app.services.accounts import ensure_ai_allowed
from app.tailoring.checks import answer_problem
from app.tailoring.content import DraftLine, FactSnapshot
from app.tailoring.experience import experience_years

SENSITIVE = re.compile(
    r"\b(citizen(ship)?|nationality|authori[sz](ed|ation)|sponsor(ship)?|visa|salary|"
    r"compensation|pay|ctc|notice|gender|race|ethnic(ity)?|veteran|disab(led|ility)|"
    r"pronouns?|date of birth|birth|age|criminal|conviction|consent|declar(e|ation)|"
    r"relocat(e|ion)|right to work)\b",
    re.IGNORECASE,
)
STOCK = re.compile(
    r"\b(i am (so )?excited to|passionate about|leverag(e|ing)|synerg(y|ies)|"
    r"in today'?s fast[- ]paced|thrive in|dynamic team|go-getter)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[a-z][a-z+#.]{2,}")
MAX_NOTES = 5
NO_AI_NOTE = "This form asks for answers not written by AI. Write it from your Facts."


def is_sensitive(question: str) -> bool:
    return bool(SENSITIVE.search(question))


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.casefold()))


def fact_notes(question: str, context: str, facts: list[FactSnapshot]) -> list[str]:
    """The User's own Facts most related to the question, as notes to write from."""
    wanted = _words(question) | _words(context)
    scored = sorted(
        facts,
        key=lambda f: (len(_words(f"{f.group} {f.text}") & wanted), f.kind != "skill"),
        reverse=True,
    )
    notes = [f"{f.group}: {f.text}" if f.group else f.text for f in scored if f.kind != "skill"]
    return notes[:MAX_NOTES]


def fit(text: str, max_chars: int | None) -> str | None:
    """Within the field's limit, cut at a sentence end; None when no sentence fits."""
    text = " ".join(text.split()) if "\n" not in text else text.strip()
    if not max_chars or len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if cut.endswith((".", "!", "?")):
        return cut
    return cut[: end + 1] if end > 0 else None


async def _job(session: AsyncSession, user: User, job_id: uuid.UUID) -> Job:
    job = await session.scalar(
        select(Job)
        .join(UserJob, UserJob.job_id == Job.id)
        .where(Job.id == job_id, UserJob.user_id == user.id)
    )
    if job is None:
        raise NotFoundError("Job not found")
    return job


async def _description(session: AsyncSession, user: User, job: Job) -> str:
    """The description the User's active Draft was made with, else the User's own page
    text, else the Job's primary advert."""
    version = await session.scalar(
        select(DraftVersion)
        .join(Draft, Draft.id == DraftVersion.draft_id)
        .where(
            Draft.user_id == user.id,
            Draft.job_id == job.id,
            Draft.active.is_(True),
            DraftVersion.number == Draft.current_version,
        )
    )
    if version and version.job_context.get("description"):
        return str(version.job_context["description"])
    link = await session.scalar(
        select(UserJob).where(UserJob.user_id == user.id, UserJob.job_id == job.id)
    )
    if link and link.page_description:
        return str(link.page_description.get("description") or "")
    primary = await session.get(Posting, job.primary_posting_id) if job.primary_posting_id else None
    return primary.description if primary else ""


def _saved_for(question: str, answers: list[SavedAnswer]) -> SavedAnswer | None:
    key = saved_answers.question_key(question)
    rank = {"company": 0, "country": 1, "general": 2}
    matches = sorted((a for a in answers if a.question_key == key), key=lambda a: rank[a.scope])
    return matches[0] if matches else None


async def answer(
    session: AsyncSession,
    user: User,
    job_id: uuid.UUID,
    questions: list[QuestionIn],
    no_ai: bool,
    gateway: BaseAIGateway,
) -> list[AnswerOut]:
    job = await _job(session, user, job_id)
    applicable = await saved_answers.applicable(session, user, job.id)
    results: dict[str, AnswerOut] = {}
    pending: list[QuestionIn] = []
    for q in questions:
        saved = _saved_for(q.question, applicable)
        if saved is not None:
            results[q.ref] = AnswerOut(
                ref=q.ref, kind="saved", text=saved.answer, saved_answer_id=saved.id
            )
        elif is_sensitive(q.question):
            results[q.ref] = AnswerOut(
                ref=q.ref,
                kind="none",
                warning="Answer this yourself, or save an answer in Settings to reuse it.",
            )
        else:
            pending.append(q)
    if pending:
        if user.fact_bank_reviewed_at is None:
            raise PreconditionError("Review your Fact Bank first")
        facts = await drafting._facts(session, user)
        context = await _description(session, user, job)
        if no_ai:
            for q in pending:
                results[q.ref] = AnswerOut(
                    ref=q.ref,
                    kind="fact_notes",
                    notes=fact_notes(q.question, job.title, facts),
                    warning=NO_AI_NOTE,
                )
        else:
            ensure_ai_allowed(user)
            results.update(await _suggest(session, user, job, context, facts, pending, gateway))
    return [results[q.ref] for q in questions if q.ref in results]


async def _suggest(
    session: AsyncSession,
    user: User,
    job: Job,
    context: str,
    facts: list[FactSnapshot],
    questions: list[QuestionIn],
    gateway: BaseAIGateway,
) -> dict[str, AnswerOut]:
    by_ref = {q.ref: q for q in questions}
    request = AnswerQuestionsRequest(
        user_id=user.id,
        job_title=job.title,
        company=job.company_name,
        description=context,
        facts=facts,
        writing_style=writing_style.prompt_text(user),
        questions=[
            FormQuestion(ref=q.ref, question=q.question, max_chars=q.max_chars) for q in questions
        ],
    )
    try:
        response = await gateway.answer_questions(request)
        drafted = {a.ref: a for a in response.result.answers if a.ref in by_ref}
    except GatewayError:
        drafted = {}
    known = {f.ref for f in facts}
    years = experience_years(facts)
    out: dict[str, AnswerOut] = {}
    for q in questions:
        notes = fact_notes(q.question, job.title, facts)
        got = drafted.get(q.ref)
        text = fit(got.text, q.max_chars) if got and got.text.strip() else None
        refs = [r for r in (got.fact_refs if got else []) if r in known]
        problem = None
        if text:
            # The same code checks as a Draft line: tools, numbers and claims must be in
            # the cited Facts (ADR-0005). A failing suggestion becomes notes.
            problem = answer_problem(
                DraftLine(id=q.ref, text=text, fact_refs=refs),
                facts,
                job_title=job.title,
                company=job.company_name,
                job_text=context,
                user_name=user.name,
                experience_years=years,
            )
        if not text or not refs or problem:
            out[q.ref] = AnswerOut(
                ref=q.ref,
                kind="fact_notes",
                notes=notes,
                warning="No suggestion your Facts fully support. Write it from these notes."
                if got
                else "Suggestions are unavailable right now. Write it from these notes.",
            )
            continue
        out[q.ref] = AnswerOut(
            ref=q.ref,
            kind="suggestion",
            text=text,
            fact_refs=refs,
            notes=notes,
            warning="Contains stock phrasing. Rework it in your own words."
            if STOCK.search(text)
            else None,
        )
    return out


async def save_from_extension(
    session: AsyncSession,
    user: User,
    job_id: uuid.UUID,
    question: str,
    answer_text: str,
    scope: str,
    origin: str,
) -> SavedAnswer:
    """An answer the User reviewed on a form, kept for reuse within its scope."""
    from app.schemas.application_profile import SavedAnswerIn
    from app.services.saved_answers import job_countries

    job = await _job(session, user, job_id)
    body: dict = {
        "question": question,
        "answer": answer_text,
        "scope": scope,
        "sensitive": is_sensitive(question),
    }
    if scope == "company":
        body["company_id"] = job.company_id
    elif scope == "country":
        countries = sorted(job_countries(job))
        if len(countries) != 1:
            raise PreconditionError("This Job is in several countries. Save it as General.")
        body["country"] = countries[0]
    row = await saved_answers.create(session, user, SavedAnswerIn.model_validate(body))
    row.origin, row.job_id = origin, job.id
    await session.flush()
    return row
