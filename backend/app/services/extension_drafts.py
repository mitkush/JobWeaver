"""Drafts as the Application Extension sees them (ADR-0017): metadata to choose one, the
exact version to use, and that version's PDFs. Only the User's own, ready Drafts."""

import re
import uuid
from typing import Literal
from urllib.parse import parse_qsl, urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.documents.pdf import filename
from app.models.draft import Application, Draft, DraftVersion
from app.models.job import Job
from app.models.user import User
from app.schemas.extension import ExtDraftSummary, ExtDraftVersion
from app.services import drafting

# Hosts that serve the same boards under different names.
_HOST_ALIASES = {"job-boards.greenhouse.io": "boards.greenhouse.io"}
_ID_LIKE = re.compile(r"^(?:\d{4,}|[0-9a-f]{8}-[0-9a-f-]{27,})$", re.IGNORECASE)
MAX_DRAFTS = 50


def _parts(url: str) -> tuple[str, str, set[str]] | None:
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower().removeprefix("www.")
    ids = {v for _, v in parse_qsl(parts.query) if _ID_LIKE.match(v)}
    return _HOST_ALIASES.get(host, host), parts.path.rstrip("/"), ids


def apply_link_matches(page_url: str, apply_url: str | None) -> bool:
    """The page is the Job's apply link, a page under it (".../apply"), or the same link
    with tracking parameters. Ids in the stored link's query (gh_jid=123) must be there."""
    page, stored = _parts(page_url), _parts(apply_url or "")
    if page is None or stored is None:
        return False
    host, path, ids = page
    s_host, s_path, s_ids = stored
    if host != s_host or not s_ids <= ids:
        return False
    return path == s_path or (bool(s_path) and path.startswith(s_path + "/"))


def _host(url: str | None) -> str | None:
    parts = _parts(url or "")
    return parts[0] if parts else None


async def _ready(
    session: AsyncSession, user: User
) -> list[tuple[Draft, DraftVersion, str | None, str | None]]:
    rows = (
        await session.execute(
            select(Draft, DraftVersion, Application.status, Job.apply_url)
            .join(
                DraftVersion,
                (DraftVersion.draft_id == Draft.id)
                & (DraftVersion.number == Draft.current_version),
            )
            .join(Job, Job.id == Draft.job_id)
            .outerjoin(
                Application,
                (Application.user_id == Draft.user_id) & (Application.job_id == Draft.job_id),
            )
            .where(Draft.user_id == user.id, Draft.state == "ready", Draft.current_version > 0)
            .order_by(DraftVersion.created_at.desc())
            .limit(MAX_DRAFTS)
        )
    ).all()
    return [(d, v, str(s) if s else None, a) for d, v, s, a in rows]


def _summary(draft: Draft, row: DraftVersion, status: str | None) -> ExtDraftSummary:
    job = draft.job_snapshot
    return ExtDraftSummary(
        draft_id=draft.id,
        job_id=draft.job_id,
        title=str(job.get("title") or ""),
        company=str(job.get("company") or ""),
        apply_host=_host(str(job.get("apply_url") or "")),
        current_version=draft.current_version,
        saved_at=row.created_at,
        application_status=status,
    )


async def recent(session: AsyncSession, user: User) -> list[ExtDraftSummary]:
    return [_summary(d, v, s) for d, v, s, _ in await _ready(session, user)]


async def match(session: AsyncSession, user: User, page_url: str) -> list[ExtDraftSummary]:
    """Drafts for this page. Several matches are all returned: the User chooses."""
    return [
        _summary(d, v, s)
        for d, v, s, job_apply_url in await _ready(session, user)
        if apply_link_matches(page_url, str(d.job_snapshot.get("apply_url") or ""))
        or apply_link_matches(page_url, job_apply_url)
    ]


async def version_detail(
    session: AsyncSession, user: User, draft_id: uuid.UUID, number: int | None
) -> ExtDraftVersion:
    draft = await drafting.owned_draft(session, user, draft_id)
    if draft.state != "ready" or not draft.current_version:
        raise NotFoundError("This Draft is not ready yet")
    row = await drafting.version(session, draft, number)
    status = await session.scalar(
        select(Application.status).where(
            Application.user_id == user.id, Application.job_id == draft.job_id
        )
    )
    job = draft.job_snapshot
    names = [str(job["name"]), str(job["company"]), str(job["title"])]
    return ExtDraftVersion(
        draft_id=draft.id,
        job_id=draft.job_id,
        title=str(job["title"]),
        company=str(job["company"]),
        apply_url=str(job.get("apply_url") or "") or None,
        number=row.number,
        current_version=draft.current_version,
        saved_at=row.created_at,
        warnings=len(row.warnings),
        template=await drafting.fitting_template(draft, row),
        resume_file=filename(*names),
        cover_letter_file=filename(*names, "cover_letter"),
        application_status=str(status) if status else None,
    )


async def pdf(
    session: AsyncSession,
    user: User,
    draft_id: uuid.UUID,
    kind: Literal["resume", "cover_letter"],
    number: int,
    template: Literal["standard", "compact"] | None,
) -> tuple[bytes, str]:
    """Always a named version, so a newer Draft can never replace the chosen PDF."""
    chosen = template or (await version_detail(session, user, draft_id, number)).template
    return await drafting.pdf(session, user, draft_id, kind, chosen, number)
