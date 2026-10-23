"""Draft orchestration: progress, immutable versions, editing and outward hand-off."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import quote, urlencode

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.gmail import GmailClient, compose_url, raw_message
from app.adapters.links import LinkState, check_apply_link
from app.core.db import get_sessionmaker
from app.core.errors import (
    ConflictError,
    GatewayError,
    GoogleFlowError,
    JobWeaverError,
    NotFoundError,
    PreconditionError,
    ValidationFailedError,
)
from app.documents.pdf import filename, page_count, render_pdf
from app.gateway.base import BaseAIGateway
from app.gateway.schemas import (
    ExtractSkillsRequest,
    JobAdvert,
    ReviseDraftRequest,
    TailorDraftRequest,
)
from app.models import (
    Application,
    Document,
    DocumentKind,
    Draft,
    DraftVersion,
    Fact,
    GmailHandoff,
    Job,
    User,
    UserJob,
)
from app.models.posting import Posting
from app.schemas.drafts import DraftOut, HandoffIn, HandoffOut, VersionOut
from app.services import applications
from app.services.accounts import ensure_ai_allowed
from app.services.correspondence import clean_skills, refresh_jobs, source_priorities
from app.services.email_check import check_recipient
from app.services.gmail import access_token
from app.services.google_oauth import GoogleOAuthClient
from app.tailoring.checks import CheckResult, check
from app.tailoring.completeness import include_supported_skills
from app.tailoring.content import DraftContent, FactSnapshot
from app.tailoring.diff import moved
from app.tailoring.email import body_html, body_text, greeting_name, signature, subject
from app.tailoring.experience import experience_years
from app.tailoring.placeholders import fill_placeholders
from app.tailoring.skills import requested_missing_skills, user_skills

logger = logging.getLogger(__name__)
AI_BUSY = "The AI services are busy right now. Retry in a few minutes."
DRAFT_GENERATION_TIMEOUT_SECONDS = 90
NOTHING_VERIFIED = (
    "No generated line could be traced to your Fact Bank, so nothing was kept. "
    "Check that your Fact Bank covers your experience, then retry."
)

# Tasks remain referenced, and are recovered from their durable queue after a restart.
_TASKS: set[asyncio.Task[None]] = set()


async def owned_draft(
    session: AsyncSession,
    user: User,
    draft_id: uuid.UUID,
    *,
    lock: bool = False,
) -> Draft:
    query = select(Draft).where(Draft.id == draft_id, Draft.user_id == user.id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    draft = await session.scalar(query)
    if draft is None:
        raise NotFoundError("Draft not found")
    return draft


async def version(session: AsyncSession, draft: Draft, number: int | None = None) -> DraftVersion:
    row = await session.scalar(
        select(DraftVersion).where(
            DraftVersion.draft_id == draft.id,
            DraftVersion.user_id == draft.user_id,
            DraftVersion.number == (number or draft.current_version),
        )
    )
    if row is None:
        raise NotFoundError("Draft version not found")
    return row


def version_out(row: DraftVersion) -> VersionOut:
    return VersionOut(
        number=row.number,
        source=row.source,
        content=DraftContent.model_validate(row.content),
        facts=[FactSnapshot.model_validate(fact) for fact in row.facts],
        warnings=row.warnings,
        message=row.message,
        created_at=row.created_at,
    )


def ready(draft: Draft, expected: int) -> None:
    if draft.state != "ready" or draft.current_version != expected:
        raise ConflictError("The Draft changed. Reload it before saving your changes.")


async def _facts(session: AsyncSession, user: User) -> list[FactSnapshot]:
    facts = list(
        (
            await session.scalars(
                select(Fact)
                .where(Fact.user_id == user.id)
                .order_by(Fact.position, Fact.created_at, Fact.id)
            )
        ).all()
    )
    if not facts:
        raise PreconditionError("Add Facts to your Fact Bank first")
    if len(facts) > 200:
        raise PreconditionError(
            "A Draft supports up to 200 Facts. Consolidate your Fact Bank first."
        )
    return [
        FactSnapshot(
            ref=f"F{i}",
            id=fact.id,
            kind=fact.kind.value,
            group=fact.group,
            text=fact.text,
            in_base_resume=fact.in_base_resume,
        )
        for i, fact in enumerate(facts, 1)
    ]


async def _updated_facts(
    session: AsyncSession, user: User, previous: list[FactSnapshot]
) -> list[FactSnapshot]:
    """Refresh Fact text without changing the references already used by this Draft."""
    existing = {fact.id: fact.ref for fact in previous}
    next_ref = max((int(fact.ref[1:]) for fact in previous), default=0) + 1
    latest = await _facts(session, user)
    for fact in latest:
        if fact.id in existing:
            fact.ref = existing[fact.id]
        else:
            fact.ref = f"F{next_ref}"
            next_ref += 1
    return latest


def _request(draft: Draft, facts: list[FactSnapshot]) -> TailorDraftRequest:
    job = draft.job_snapshot
    return TailorDraftRequest(
        user_id=draft.user_id,
        job_title=str(job["title"]),
        company=str(job["company"]),
        description=str(job["description"]),
        facts=facts,
        has_email=bool(job.get("contact_email")),
        experience_years=experience_years(facts),
    )


def _check(draft: Draft, content: DraftContent, facts: list[FactSnapshot]) -> CheckResult:
    job = draft.job_snapshot
    content = fill_placeholders(
        content,
        name=str(job.get("name") or ""),
        email=str(job.get("email") or ""),
        company=str(job.get("company") or ""),
        title=str(job.get("title") or ""),
    )
    return check(
        content,
        facts,
        job_title=str(job.get("title") or ""),
        company=str(job.get("company") or ""),
        job_skills=[str(s) for s in job.get("required_skills") or []],
        job_text=str(job.get("description") or ""),
        user_name=str(job.get("name") or ""),
        experience_years=experience_years(facts),
    )


def _email_header(draft: Draft, content: DraftContent) -> None:
    """Subject and greeting for AI output: facts about the job and the User, set by code."""
    job = draft.job_snapshot
    content.email_subject = subject(content, str(job["title"]), str(job.get("name") or ""))
    content.email_greeting = greeting_name(
        content.email_greeting, str(job.get("description") or "")
    )


MAX_LINKS_CHECKED = 4
LINK_CLOSED = (
    "This job's apply link now says the page is not found, so the job looks closed. "
    "It has been marked closed; choose another job."
)


async def ensure_link_open(
    session: AsyncSession, user: User, job_id: uuid.UUID, http: httpx.AsyncClient
) -> None:
    """Checks the apply link for free before drafting (FR-B10 AC3). A closed link closes
    its Postings; if that closes the Job, the User is told before any AI work starts."""
    job = await session.scalar(
        select(Job)
        .join(UserJob, UserJob.job_id == Job.id)
        .where(Job.id == job_id, UserJob.user_id == user.id)
    )
    if job is None or job.expired_at is not None:
        return  # create() reports the missing or closed Job itself
    # Each open Posting's own link: copies of one advert often differ only by a tracking
    # parameter, and a Job is closed only when none of its links still works.
    links = (
        await session.execute(
            select(Posting.apply_url)
            .where(
                Posting.job_id == job.id,
                Posting.closed_at.is_(None),
                Posting.apply_url.is_not(None),
            )
            .distinct()
            .limit(MAX_LINKS_CHECKED)
        )
    ).scalars()
    dead = [url for url in links if await check_apply_link(http, url) == LinkState.CLOSED]
    if not dead:
        return
    await session.execute(
        update(Posting)
        .where(
            Posting.job_id == job.id,
            Posting.apply_url.in_(dead),
            Posting.closed_at.is_(None),
        )
        .values(closed_at=datetime.now(UTC), closed_reason="link")
    )
    await refresh_jobs(session, [job.id], source_priorities())
    await session.commit()
    await session.refresh(job)
    if job.expired_at is not None:
        raise PreconditionError(LINK_CLOSED)


async def create(session: AsyncSession, user: User, job_id: uuid.UUID) -> Draft:
    ensure_ai_allowed(user)
    if user.fact_bank_reviewed_at is None:
        raise PreconditionError("Review your Fact Bank before creating a Draft")
    job = await session.scalar(
        select(Job)
        .join(UserJob, UserJob.job_id == Job.id)
        .where(Job.id == job_id, UserJob.user_id == user.id)
        .with_for_update(of=UserJob)
    )
    if job is None:
        raise NotFoundError("Job not found in your Feed")
    if job.expired_at is not None:
        raise PreconditionError("This Job is closed. Choose an open Job.")
    await _facts(session, user)
    # Reuse a package already being generated, so a double click cannot duplicate it.
    existing = await session.scalar(
        select(Draft)
        .where(
            Draft.user_id == user.id,
            Draft.job_id == job_id,
            Draft.state.in_(["queued", "generating"]),
        )
        .order_by(Draft.created_at.desc())
    )
    if existing is not None:
        current_link = await session.scalar(
            select(UserJob).where(UserJob.user_id == user.id, UserJob.job_id == job.id)
        )
        if (
            current_link
            and current_link.page_description
            and str(current_link.page_description["description"])
            != existing.job_snapshot.get("description")
        ):
            raise ConflictError(
                "A Draft is already generating with another description. Wait for it to finish."
            )
        return existing
    from app.models import Posting

    primary = await session.get(Posting, job.primary_posting_id) if job.primary_posting_id else None
    link = await session.scalar(
        select(UserJob).where(UserJob.user_id == user.id, UserJob.job_id == job.id)
    )
    page = link.page_description if link and link.page_description else None
    document = await session.scalar(
        select(Document).where(
            Document.user_id == user.id,
            Document.kind == DocumentKind.RESUME,
        )
    )
    draft = Draft(
        user_id=user.id,
        job_id=job.id,
        state="queued",
        progress="Reading the job",
        current_version=0,
        job_snapshot={
            "title": job.title,
            "company": job.company_name,
            "description": str(page["description"])
            if page
            else primary.description
            if primary
            else "",
            "description_origin": dict(page)
            if page
            else {
                "posting_id": str(primary.id) if primary else None,
                "url": primary.apply_url if primary else None,
            },
            "contact_email": job.contact_email,
            "apply_url": job.apply_url,
            # The shared Job's AI skill list describes its Source text, not this User's
            # Page Description. Do not reuse it for a different description.
            "required_skills": [] if page else list(job.required_skills or []),
            "page_skills_pending": bool(page),
            "name": user.name or "Applicant",
            "email": user.email,
        },
        base_resume=document.extracted_text if document else "",
    )
    session.add(draft)
    await session.flush()
    return draft


async def _save_version(
    session: AsyncSession,
    draft: Draft,
    content: DraftContent,
    facts: list[FactSnapshot],
    source: str,
    warnings: list[str] | None = None,
    message: str = "",
) -> DraftVersion:
    draft.current_version += 1
    row = DraftVersion(
        user_id=draft.user_id,
        draft_id=draft.id,
        number=draft.current_version,
        source=source,
        content=content.model_dump(mode="json"),
        facts=[fact.model_dump(mode="json") for fact in facts],
        warnings=warnings or [],
        message=message,
    )
    session.add(row)
    await session.flush()
    return row


async def generate(draft_id: uuid.UUID, user_id: uuid.UUID, gateway: BaseAIGateway) -> None:
    async with get_sessionmaker()() as session:
        user = await session.get(User, user_id)
        if user is None:
            return
        try:
            draft = await owned_draft(session, user, draft_id, lock=True)
            if draft.state != "queued":
                return
            ensure_ai_allowed(user)
            facts = await _facts(session, user)
            draft.state, draft.progress = "generating", "Choosing your experience"
            await session.commit()
            if draft.job_snapshot.get("page_skills_pending"):
                draft.progress = "Reading requirements from your reviewed job description"
                await session.commit()
                async with asyncio.timeout(DRAFT_GENERATION_TIMEOUT_SECONDS):
                    extracted = await gateway.extract_skills(
                        ExtractSkillsRequest(
                            user_id=user.id,
                            jobs=[
                                JobAdvert(
                                    ref="1",
                                    title=str(draft.job_snapshot["title"]),
                                    description=str(draft.job_snapshot["description"]),
                                )
                            ],
                        )
                    )
                found = next((j.skills for j in extracted.result.jobs if j.ref == "1"), None)
                if found is None:
                    raise GatewayError("The AI did not return job requirements. Retry generation.")
                requirements = clean_skills(found)
                user = await session.get(User, user_id, populate_existing=True)
                if user is None:
                    return
                ensure_ai_allowed(user)
                draft = await owned_draft(session, user, draft_id, lock=True)
                draft.job_snapshot = {
                    **draft.job_snapshot,
                    "required_skills": requirements,
                    "page_skills_pending": False,
                }
                link = await session.scalar(
                    select(UserJob).where(
                        UserJob.user_id == user_id, UserJob.job_id == draft.job_id
                    )
                )
                if link and link.page_description == draft.job_snapshot.get("description_origin"):
                    link.page_required_skills = requirements
                await session.commit()
            draft.progress = "Writing the Tailored Resume, Cover Letter and Application Email"
            await session.commit()
            async with asyncio.timeout(DRAFT_GENERATION_TIMEOUT_SECONDS):
                result = await gateway.tailor_draft(_request(draft, facts))
            # Recheck ownership and notice before persisting provider output.
            user = await session.get(User, user_id, populate_existing=True)
            if user is None:
                return
            ensure_ai_allowed(user)
            draft = await owned_draft(session, user, draft_id, lock=True)
            draft.progress = "Checking Facts and Tailoring Trace"
            generated = result.result.content
            for part in ("resume", "cover_letter", "email_body"):
                for line in getattr(generated, part):
                    line.manual = False  # only the User's own edits are protected
            checked = _check(draft, generated, facts)
            content, warnings = checked.content, checked.warnings
            content = include_supported_skills(
                content, facts, [str(s) for s in draft.job_snapshot.get("required_skills") or []]
            )
            checked = _check(draft, content, facts)
            content, warnings = checked.content, [*warnings, *checked.warnings]
            if not content.resume or not content.cover_letter:
                raise _Unverified()
            _email_header(draft, content)
            if draft.job_snapshot.get("contact_email") and not content.email_body:
                raise _Unverified()
            try:
                await asyncio.to_thread(
                    render_pdf,
                    content,
                    str(draft.job_snapshot["name"]),
                    str(draft.job_snapshot["email"]),
                    "resume",
                    "compact",
                    facts,
                )
            except ValidationFailedError as exc:
                # The Draft is still saved: only the editor can fix it, and a failed Draft
                # has no editor. The warning says what to change before downloading.
                warnings = [*warnings, f"PDF: {exc.message}"]
            await _save_version(
                session, draft, content, facts, "generation", warnings, result.result.message
            )
            draft.state, draft.progress, draft.error = "ready", "Ready to review", None
            await session.commit()
        except _Unverified:
            await _fail(session, draft_id, user_id, NOTHING_VERIFIED)
        except (GatewayError, TimeoutError) as exc:
            # The User sees "busy"; the log keeps every provider's own reason.
            reason = exc.message if isinstance(exc, GatewayError) else "timed out after 60s"
            logger.warning("Draft %s generation failed: %s", draft_id, reason)
            await _fail(session, draft_id, user_id, AI_BUSY)
        except JobWeaverError as exc:
            # Notice, region or Fact Bank preconditions: their message says what to do.
            await _fail(session, draft_id, user_id, exc.message)
        except Exception:
            # Never leave a Draft spinning on "generating" after an unexpected error.
            logger.exception("Draft %s generation failed", draft_id)
            await _fail(
                session, draft_id, user_id, "Something went wrong while writing. Retry the draft."
            )


class _Unverified(Exception):
    """Every generated line failed the truthfulness checks."""


async def _fail(
    session: AsyncSession, draft_id: uuid.UUID, user_id: uuid.UUID, message: str
) -> None:
    await session.rollback()
    draft = await session.scalar(
        select(Draft).where(Draft.id == draft_id, Draft.user_id == user_id)
    )
    if draft is not None:
        draft.state, draft.progress, draft.error = "failed", "Generation stopped", message
        await session.commit()


async def recover_queued(gateway: BaseAIGateway) -> None:
    async with get_sessionmaker()() as session:
        drafts = list(
            (
                await session.scalars(
                    select(Draft).where(
                        Draft.state.in_(["queued", "generating"]),
                    )
                )
            ).all()
        )
        for draft in drafts:
            draft.state = "queued"
        await session.commit()
        for draft in drafts:
            task = asyncio.create_task(generate(draft.id, draft.user_id, gateway))
            _TASKS.add(task)
            task.add_done_callback(_TASKS.discard)


async def stop_tasks() -> None:
    for task in list(_TASKS):
        task.cancel()
    if _TASKS:
        await asyncio.gather(*_TASKS, return_exceptions=True)


# Which layout each version fits in, so the page opens on one that downloads. Versions are
# immutable, so the answer never changes; the cache only bounds repeated rendering.
_TEMPLATE_FITS: dict[tuple[uuid.UUID, int], Literal["standard", "compact"]] = {}


async def fitting_template(draft: Draft, row: DraftVersion) -> Literal["standard", "compact"]:
    """Standard when it fits one page, else Compact when that fits one page; past that,
    whichever fits two pages. A second page holding a few lines looks unfinished."""
    key = (draft.id, row.number)
    if key not in _TEMPLATE_FITS:
        content = DraftContent.model_validate(row.content)
        facts = [FactSnapshot.model_validate(fact) for fact in row.facts]
        name, email = str(draft.job_snapshot["name"]), str(draft.job_snapshot["email"])
        try:
            pages = {
                template: await asyncio.to_thread(page_count, content, name, email, template, facts)
                for template in ("standard", "compact")
            }
        except ValidationFailedError:
            pages = {"standard": 3, "compact": 3}
        fits: Literal["standard", "compact"] = "standard"
        if pages["standard"] > 1 and pages["compact"] < pages["standard"]:
            fits = "compact"
        if len(_TEMPLATE_FITS) > 2000:
            _TEMPLATE_FITS.clear()
        _TEMPLATE_FITS[key] = fits
    return _TEMPLATE_FITS[key]


async def detail(session: AsyncSession, user: User, draft_id: uuid.UUID) -> DraftOut:
    draft = await owned_draft(session, user, draft_id)
    current = await version(session, draft) if draft.current_version else None
    status = await session.scalar(
        select(Application.status).where(
            Application.user_id == user.id, Application.job_id == draft.job_id
        )
    )
    job = draft.job_snapshot
    return DraftOut(
        id=draft.id,
        job_id=draft.job_id,
        state=draft.state,
        progress=draft.progress,
        error=draft.error,
        current_version=draft.current_version,
        job=job,
        base_resume=draft.base_resume,
        version=version_out(current) if current else None,
        application_status=status,
        attachment_name=filename(str(job["name"]), str(job["company"]), str(job["title"])),
        template=await fitting_template(draft, current) if current else "standard",
    )


async def save(
    session: AsyncSession,
    user: User,
    draft_id: uuid.UUID,
    expected: int,
    content: DraftContent,
) -> None:
    draft = await owned_draft(session, user, draft_id, lock=True)
    ready(draft, expected)
    previous = await version(session, draft)
    facts = [FactSnapshot.model_validate(fact) for fact in previous.facts]
    old = {
        line.id: line
        for part in ("resume", "cover_letter", "email_body")
        for line in getattr(DraftContent.model_validate(previous.content), part)
    }
    edited = content.model_copy(deep=True)
    old_position = {
        line.id: i
        for part in ("resume", "cover_letter", "email_body")
        for i, line in enumerate(getattr(DraftContent.model_validate(previous.content), part))
    }
    for part in ("resume", "cover_letter", "email_body"):
        lines = getattr(edited, part)
        kept = [i for i, line in enumerate(lines) if line.id in old_position]
        # A line the User moved, or moved to another section, is their edit too (FR-E6):
        # Draft Chat keeps it where they put it.
        shifted = {kept[j] for j in moved([old_position[lines[i].id] for i in kept])}
        for i, line in enumerate(lines):
            if (
                line.id not in old
                or line.text != old[line.id].text
                or line.fact_refs != old[line.id].fact_refs
                or line.section != old[line.id].section
                or line.heading != old[line.id].heading
                or i in shifted
            ):
                line.manual = True
            else:
                line.manual = old[line.id].manual
    # The User's own words are flagged, never refused or deleted (FR-E6, ADR-0005).
    checked = _check(draft, edited, facts)
    await _save_version(session, draft, checked.content, facts, "manual", checked.warnings)


async def recheck(session: AsyncSession, user: User, draft_id: uuid.UUID, expected: int) -> None:
    draft = await owned_draft(session, user, draft_id, lock=True)
    ready(draft, expected)
    previous = await version(session, draft)
    facts = await _updated_facts(
        session, user, [FactSnapshot.model_validate(fact) for fact in previous.facts]
    )
    checked = _check(draft, DraftContent.model_validate(previous.content), facts)
    if not checked.content.resume or not checked.content.cover_letter:
        raise ValidationFailedError(
            "The current Fact Bank cannot support this Draft. Restore the missing Facts "
            "or edit the Draft before rechecking."
        )
    await _save_version(
        session,
        draft,
        checked.content,
        facts,
        "recheck",
        checked.warnings,
        "Rechecked against the current Fact Bank",
    )


async def chat(
    session: AsyncSession,
    user: User,
    draft_id: uuid.UUID,
    expected: int,
    message: str,
    overwrite_manual: bool,
    gateway: BaseAIGateway,
) -> None:
    # Ownership is checked before notice or any provider call.
    draft = await owned_draft(session, user, draft_id, lock=True)
    ready(draft, expected)
    ensure_ai_allowed(user)
    current = await version(session, draft)
    facts = await _updated_facts(
        session, user, [FactSnapshot.model_validate(fact) for fact in current.facts]
    )
    content = DraftContent.model_validate(current.content)
    skills = user_skills(
        [fact.text for fact in facts if fact.kind == "skill"],
        [f"{fact.group} {fact.text}" for fact in facts],
    )
    missing = requested_missing_skills(message, skills)
    if missing:
        raise ValidationFailedError(
            "Not in your Fact Bank: " + ", ".join(missing) + ". Add the Facts there first."
        )
    request = ReviseDraftRequest(
        **_request(draft, facts).model_dump(), content=content, message=message
    )
    try:
        async with asyncio.timeout(DRAFT_GENERATION_TIMEOUT_SECONDS):
            response = await gateway.revise_draft(request)
    except TimeoutError as exc:
        raise GatewayError("Draft Chat timed out. Please retry.") from exc
    for part in ("resume", "cover_letter", "email_body"):
        for line in getattr(response.result.content, part):
            line.manual = False  # whatever the model claims, these lines are AI text
    proposed = _check(draft, response.result.content, facts)
    proposal = proposed.content
    if not proposal.resume or not proposal.cover_letter:
        raise ValidationFailedError("This change needs Facts that are not in your Fact Bank.")
    if not overwrite_manual:
        for part in ("resume", "cover_letter", "email_body"):
            old_lines = getattr(content, part)
            new_lines = getattr(proposal, part)
            locked = {line.id for line in old_lines if line.manual}
            new_lines = [line for line in new_lines if line.id not in locked]
            for i, line in enumerate(old_lines):
                if line.manual:
                    new_lines.insert(min(i, len(new_lines)), line)
            setattr(proposal, part, new_lines)
    else:
        for part in ("resume", "cover_letter", "email_body"):
            for line in getattr(proposal, part):
                line.manual = False
    proposal.email_subject = content.email_subject
    proposal.email_greeting = content.email_greeting
    # Your kept lines are checked again (a Fact may have changed) and flagged, not removed.
    final = _check(draft, proposal, facts)
    await _save_version(
        session,
        draft,
        final.content,
        facts,
        "chat",
        proposed.removed + final.flagged,
        f"You: {message}\n\nDraft Chat: {response.result.message}",
    )


async def restore(
    session: AsyncSession,
    user: User,
    draft_id: uuid.UUID,
    expected: int,
    number: int,
) -> None:
    draft = await owned_draft(session, user, draft_id, lock=True)
    ready(draft, expected)
    old = await version(session, draft, number)
    await _save_version(
        session,
        draft,
        DraftContent.model_validate(old.content),
        [FactSnapshot.model_validate(fact) for fact in old.facts],
        "restore",
        old.warnings,
        f"Restored version {number}",
    )


async def pdf(
    session: AsyncSession,
    user: User,
    draft_id: uuid.UUID,
    kind: Literal["resume", "cover_letter"],
    template: Literal["standard", "compact"],
    number: int | None = None,
) -> tuple[bytes, str]:
    draft = await owned_draft(session, user, draft_id)
    row = await version(session, draft, number)
    job = draft.job_snapshot
    content = DraftContent.model_validate(row.content)
    data = await asyncio.to_thread(
        render_pdf,
        content,
        str(job["name"]),
        str(job["email"]),
        kind,
        template,
        [FactSnapshot.model_validate(fact) for fact in row.facts],
    )
    return data, filename(str(job["name"]), str(job["company"]), str(job["title"]), kind)


def reconnect(draft: Draft) -> HandoffOut:
    path = f"/drafts/{draft.id}?resume_handoff=1"
    return HandoffOut(
        mode="reconnect",
        url="/api/gmail/connect?" + urlencode({"next": path}),
        attachment_name=filename(
            str(draft.job_snapshot["name"]),
            str(draft.job_snapshot["company"]),
            str(draft.job_snapshot["title"]),
        ),
        message="Connect Gmail again, then confirm the hand-off to resume.",
    )


async def handoff(
    session: AsyncSession,
    user: User,
    draft_id: uuid.UUID,
    body: HandoffIn,
    google: GoogleOAuthClient,
    gmail: GmailClient,
) -> HandoffOut:
    draft = await owned_draft(session, user, draft_id, lock=True)
    ready(draft, body.expected_version)
    if not body.confirm:
        raise PreconditionError("Confirm the recipient and attachment before opening Gmail")
    check = await check_recipient(body.recipient)
    if check.warnings and not body.confirm_email_warning:
        raise PreconditionError(
            "Confirm the email warning before continuing: " + "; ".join(check.warnings)
        )
    if "\n" in body.recipient or "\r" in body.recipient:
        raise ValidationFailedError("Recipient must be a single email address")
    recipient = check.recipient
    row = await version(session, draft)
    content = DraftContent.model_validate(row.content)
    job = draft.job_snapshot
    email_subject = " ".join(content.email_subject.split())
    sign = signature(
        content,
        str(job["name"]),
        user.email,
        [FactSnapshot.model_validate(fact) for fact in row.facts],
    )
    message_body = body_text(content, content.email_greeting, sign)
    message_html = body_html(content, content.email_greeting, sign)
    attachment = filename(str(job["name"]), str(job["company"]), str(job["title"]))
    application = await applications.ensure(session, user, draft.job_id, draft.id)
    existing = await session.scalar(
        select(GmailHandoff)
        .where(
            GmailHandoff.user_id == user.id,
            GmailHandoff.application_id == application.id,
            GmailHandoff.kind == "application",
            GmailHandoff.draft_id == draft.id,
            GmailHandoff.version == draft.current_version,
            GmailHandoff.recipient == recipient,
        )
        .order_by(GmailHandoff.created_at.desc())
        .limit(1)
    )
    url = compose_url(user.email, recipient, email_subject, message_body)
    mode = "fallback"
    # Reuse only a hand-off that reached Gmail; after a Gmail failure, try Gmail again.
    if existing is None or not existing.gmail_draft_id:
        data, _ = await pdf(session, user, draft.id, "resume", body.template)
        try:
            token = await access_token(session, user, google)
            gmail_id = await gmail.create_draft(
                token,
                raw_message(
                    user.email,
                    recipient,
                    email_subject,
                    message_body,
                    data,
                    attachment,
                    html=message_html,
                ),
            )
        except GoogleFlowError:
            return reconnect(draft)
        except JobWeaverError:
            gmail_id = None
        if existing is None:
            existing = GmailHandoff(
                user_id=user.id,
                application_id=application.id,
                kind="application",
                draft_id=draft.id,
                version=draft.current_version,
                recipient=recipient,
            )
            session.add(existing)
        existing.gmail_draft_id = gmail_id
        await session.flush()
    if existing.gmail_draft_id:
        mode = "gmail"
        url = f"https://mail.google.com/mail/u/{quote(user.email, safe='')}/#drafts"
    return HandoffOut(
        mode=mode,
        url=url,
        attachment_name=attachment,
        application_id=application.id,
        message=(
            "Your Gmail draft includes the resume PDF. Review it in Gmail before sending."
            if mode == "gmail"
            else "Gmail is unavailable. Open compose and attach the downloaded PDF yourself."
        ),
    )


async def mark_applied(
    session: AsyncSession, user: User, draft_id: uuid.UUID, expected: int
) -> None:
    draft = await owned_draft(session, user, draft_id, lock=True)
    ready(draft, expected)
    await applications.mark_applied(session, user, draft.job_id, draft.id)
