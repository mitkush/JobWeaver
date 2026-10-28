"""Background proposals with explicit acceptance and immutable accepted context."""

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker
from app.core.errors import ConflictError, NotFoundError, PreconditionError
from app.gateway.base import BaseAIGateway
from app.gateway.progress import draft_progress
from app.gateway.schemas import ExtractSkillsRequest, JobAdvert, ReviseDraftRequest
from app.models import Draft, DraftProposal, User, UserJob
from app.schemas.draft_workflow import ProposalIn, ProposalOut
from app.services import drafting
from app.services.accounts import ensure_ai_allowed
from app.tailoring.content import DraftContent, FactSnapshot

logger = logging.getLogger(__name__)


async def owned(
    session: AsyncSession, user: User, draft_id: uuid.UUID, proposal_id: uuid.UUID
) -> DraftProposal:
    proposal = await session.scalar(
        select(DraftProposal).where(
            DraftProposal.id == proposal_id,
            DraftProposal.user_id == user.id,
            DraftProposal.draft_id == draft_id,
        )
    )
    if proposal is None:
        raise NotFoundError("Proposal not found")
    return proposal


def out(row: DraftProposal) -> ProposalOut:
    return ProposalOut(
        id=row.id,
        base_version=row.base_version,
        part=row.part,
        section=row.section,
        state=row.state,
        progress=row.progress,
        error=row.error,
        content=DraftContent.model_validate(row.content) if row.content else None,
        warnings=row.warnings,
    )


async def queue(
    session: AsyncSession, user: User, draft_id: uuid.UUID, body: ProposalIn
) -> DraftProposal:
    draft = await drafting.owned_draft(session, user, draft_id, lock=True)
    drafting.ready(draft, body.expected_version)
    if not draft.active:
        raise ConflictError("This is an archived Draft. Open the current Draft for this Job.")
    ensure_ai_allowed(user)
    if user.fact_bank_reviewed_at is None:
        raise PreconditionError("Review your Fact Bank first")
    existing = await session.scalar(
        select(DraftProposal).where(
            DraftProposal.draft_id == draft.id,
            DraftProposal.user_id == user.id,
            DraftProposal.state.in_(["queued", "generating", "ready"]),
        )
    )
    if existing:
        raise ConflictError("Review or discard the existing proposal first")
    if body.section and body.part != "resume":
        raise PreconditionError("Sections apply to the resume only")
    proposal = DraftProposal(
        user_id=user.id,
        draft_id=draft.id,
        base_version=body.expected_version,
        part=body.part,
        section=body.section,
        instruction=body.instruction,
    )
    session.add(proposal)
    await session.flush()
    return proposal


async def generate(proposal_id: uuid.UUID, user_id: uuid.UUID, gateway: BaseAIGateway) -> None:
    async with get_sessionmaker()() as db:
        row = await db.scalar(
            select(DraftProposal)
            .where(DraftProposal.id == proposal_id, DraftProposal.user_id == user_id)
            .with_for_update()
        )
        if row is None or row.state != "queued":
            return
        row.state, row.progress = "generating", "Reading Facts and job context"
        draft = await db.get(Draft, row.draft_id)
        user = await db.get(User, user_id)
        await db.commit()
        try:
            if draft is None or user is None:
                raise NotFoundError("Draft not found")
            ensure_ai_allowed(user)
            base = await drafting.version(db, draft, row.base_version)
            context = dict(base.job_context or draft.job_snapshot)
            if not row.section:
                link = await db.scalar(
                    select(UserJob).where(
                        UserJob.user_id == user.id, UserJob.job_id == draft.job_id
                    )
                )
                if link and link.page_description:
                    page = link.page_description
                    context.update(
                        description=str(page["description"]), description_origin=dict(page)
                    )
                    requirements = await gateway.extract_skills(
                        ExtractSkillsRequest(
                            user_id=user.id,
                            jobs=[
                                JobAdvert(
                                    ref="1",
                                    title=str(context["title"]),
                                    description=str(context["description"]),
                                )
                            ],
                        )
                    )
                    context["required_skills"] = (
                        requirements.result.jobs[0].skills if requirements.result.jobs else []
                    )
            # Preserve old document references while giving changed Facts fresh refs.
            prior = [FactSnapshot.model_validate(f) for f in base.facts]
            latest = await drafting._facts(db, user)
            combined = list(prior)
            for fact in latest:
                same = next(
                    (
                        f
                        for f in combined
                        if f.id == fact.id
                        and f.text == fact.text
                        and f.group == fact.group
                        and f.kind == fact.kind
                    ),
                    None,
                )
                if same:
                    fact.ref = same.ref
                else:
                    fact.ref = f"F{max((int(f.ref[1:]) for f in combined), default=0) + 1}"
                    combined.append(fact)
            original = DraftContent.model_validate(base.content)
            target = f"{row.part}, section {row.section}" if row.section else row.part
            instruction = (
                f"Propose a replacement for {target} only. Preserve other documents and sections. "
                "Use only the supplied current Facts. The User will review before accepting. "
                + row.instruction
            )
            request = ReviseDraftRequest(
                **drafting._request(draft, latest, context).model_dump(),
                content=original,
                message=instruction[:2000],
            )

            async def progress(provider: str) -> None:
                async with get_sessionmaker()() as progress_db:
                    owner = await progress_db.get(User, user_id)
                    if owner is None:
                        raise NotFoundError("User not found")
                    ensure_ai_allowed(owner)
                    current = await progress_db.get(DraftProposal, proposal_id)
                    if current and current.state == "generating":
                        current.progress = f"Trying {provider}"
                        await progress_db.commit()

            await db.commit()  # Do not hold a transaction or Draft lock during AI.
            async with asyncio.timeout(240):
                with draft_progress(progress):
                    response = await gateway.propose_draft(request)
            checked = drafting._check(draft, response.result.content, latest, context)
            proposed = original.model_copy(deep=True)
            lines = getattr(checked.content, row.part)
            if row.section:
                replacement = [line for line in lines if line.section == row.section]
                if not replacement:
                    raise PreconditionError(
                        "No supported replacement was produced for this section"
                    )
                old = proposed.resume
                insertion = next(
                    (i for i, line in enumerate(old) if line.section == row.section), len(old)
                )
                kept = [line for line in old if line.section != row.section]
                proposed.resume = kept[:insertion] + replacement + kept[insertion:]
            else:
                if not lines:
                    raise PreconditionError("No supported replacement was produced")
                setattr(proposed, row.part, lines)
            for line in getattr(proposed, row.part):
                if not row.section or line.section == row.section:
                    line.manual = False
            ensure_ai_allowed(await db.get(User, user_id, populate_existing=True))
            row = await db.scalar(
                select(DraftProposal)
                .where(DraftProposal.id == proposal_id, DraftProposal.user_id == user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if row is None or row.state != "generating":
                return
            row.content, row.facts, row.job_context = (
                proposed.model_dump(mode="json"),
                [f.model_dump(mode="json") for f in combined],
                context,
            )
            row.warnings = checked.warnings
            row.state, row.progress = "ready", "Review this replacement"
            await db.commit()
        except Exception:
            logger.exception("Draft proposal %s failed", proposal_id)
            await db.rollback()
            row = await db.get(DraftProposal, proposal_id, populate_existing=True)
            if row and row.state == "generating":
                row.state, row.progress = "failed", "Generation stopped"
                row.error = (
                    "The replacement could not be prepared. Your current document is unchanged. "
                    "Discard this attempt and retry."
                )
                await db.commit()


async def accept(
    session: AsyncSession, user: User, draft_id: uuid.UUID, proposal_id: uuid.UUID, expected: int
) -> None:
    draft = await drafting.owned_draft(session, user, draft_id, lock=True)
    drafting.ready(draft, expected)
    proposal = await owned(session, user, draft_id, proposal_id)
    if proposal.state != "ready" or proposal.base_version != expected:
        raise ConflictError(
            "The Draft changed. Keep your edits, discard this proposal and generate again."
        )
    facts = [FactSnapshot.model_validate(f) for f in proposal.facts]
    content = DraftContent.model_validate(proposal.content)
    changed = [
        line
        for line in getattr(content, proposal.part)
        if not proposal.section or line.section == proposal.section
    ]
    used = {ref for line in changed for ref in line.fact_refs}
    latest = {f.id: f for f in await drafting._facts(session, user)}
    for fact in facts:
        if fact.ref in used:
            now = latest.get(fact.id)
            if now is None or (now.text, now.group, now.kind) != (fact.text, fact.group, fact.kind):
                raise ConflictError("Supporting Facts changed. Generate a fresh proposal.")
    await drafting._save_version(
        session,
        draft,
        content,
        facts,
        "replacement",
        proposal.warnings,
        "Accepted replacement",
        job_context=proposal.job_context,
    )
    proposal.state = "accepted"


async def discard(
    session: AsyncSession, user: User, draft_id: uuid.UUID, proposal_id: uuid.UUID
) -> None:
    await drafting.owned_draft(session, user, draft_id, lock=True)
    proposal = await owned(session, user, draft_id, proposal_id)
    if proposal.state in ("accepted", "dismissed"):
        raise ConflictError("This proposal is already resolved")
    proposal.state, proposal.progress = "dismissed", "Kept current document"


async def recover(gateway: BaseAIGateway) -> None:
    async with get_sessionmaker()() as db:
        rows = list(
            await db.scalars(
                select(DraftProposal).where(DraftProposal.state.in_(["queued", "generating"]))
            )
        )
        for row in rows:
            row.state = "queued"
        await db.commit()
        for row in rows:
            task = asyncio.create_task(generate(row.id, row.user_id, gateway))
            drafting._TASKS.add(task)
            task.add_done_callback(drafting._TASKS.discard)
