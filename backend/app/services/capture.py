"""Save a reviewed browser advert without fetching the page or calling AI."""

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import NormalizedPosting
from app.adapters.captured import CapturedAdapter
from app.adapters.normalize import normalize_company
from app.adapters.posting_policy import blocked_company
from app.core.errors import ValidationFailedError
from app.models.job import Job, UserJob
from app.models.posting import Company, Posting
from app.models.user import User
from app.schemas.capture import CapturedJobOut, CaptureIn
from app.services.correspondence import lock_grouping, refresh_jobs, source_priorities
from app.services.extension_drafts import apply_link_matches
from app.services.fetching import save_postings


async def save(session: AsyncSession, user: User, body: CaptureIn) -> CapturedJobOut:
    if blocked_company(body.company):
        raise ValidationFailedError("This publisher is excluded from JobWeaver")
    # Same transaction lock as grouping: repeated captures cannot create duplicate Jobs,
    # and dedup cannot remove the chosen Job before its personal link is saved.
    await lock_grouping(session)
    candidates = (
        await session.execute(
            select(Job, Posting.apply_url)
            .join(Company, Company.id == Job.company_id)
            .outerjoin(Posting, Posting.job_id == Job.id)
            .where(Company.normalized_name == normalize_company(body.company))
        )
    ).all()
    # Only reuse an unambiguous exact URL AND matching identity. A shared careers index
    # or conflicting advert must not silently attach the wrong Job.
    matches = {
        j.id: j
        for j, posting_url in candidates
        if normalize_company(j.company_name) == normalize_company(body.company)
        and " ".join(j.title.casefold().split()) == " ".join(body.title.casefold().split())
        and any(
            apply_link_matches(body.url, url) or apply_link_matches(url or "", body.url)
            for url in (j.apply_url, posting_url)
        )
    }
    job = next(iter(matches.values())) if len(matches) == 1 else None
    matched = job is not None
    now = datetime.now(UTC)
    if job is None:
        # Immutable, content-addressed Postings: one User's later capture cannot rewrite
        # another User's advert. The personal Page Description is the drafting input.
        ref = hashlib.sha256(
            json.dumps([body.url, body.company, body.title, body.description]).encode()
        ).hexdigest()
        await save_postings(
            session,
            CapturedAdapter.name,
            [
                NormalizedPosting(
                    source_job_id=ref,
                    title=body.title,
                    company=body.company,
                    # Reviewed/pasted browser text is User-owned, not shared Source data.
                    # Keep the shared Posting as public identity metadata only.
                    description="",
                    apply_url=body.url,
                )
            ],
            now,
        )
        posting = await session.scalar(
            select(Posting).where(
                Posting.source == CapturedAdapter.name, Posting.source_job_id == ref
            )
        )
        assert posting is not None
        if posting.job_id:
            job = await session.get(Job, posting.job_id)
        else:
            job = Job(id=uuid.uuid4(), company_id=posting.company_id)
            session.add(job)
            await session.flush()
            posting.job_id = job.id
            await session.flush()
            await refresh_jobs(session, [job.id], source_priorities())
    assert job is not None
    link = await session.scalar(
        select(UserJob).where(UserJob.user_id == user.id, UserJob.job_id == job.id)
    )
    if link is None:
        link = UserJob(user_id=user.id, job_id=job.id, match_kind=None)
        session.add(link)
    link.captured_at = now
    link.hidden_at = None
    link.page_description = {
        "description": body.description,
        "url": body.url,
        "read_at": now.isoformat(),
        "title": body.title,
        "company": body.company,
    }
    link.page_required_skills = None
    await session.flush()
    return CapturedJobOut(
        job_id=job.id, title=body.title, company=body.company, matched_existing=matched
    )
