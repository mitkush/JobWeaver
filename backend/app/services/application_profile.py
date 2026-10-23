"""The application profile the extension fills forms with (ADR-0017).

JobWeaver suggests values from the Fact Bank and the Google account; nothing reaches the
extension until the User saves the profile, which is their review. An entry that cites a
Fact changed or removed after that review needs review again, and the extension leaves it
out until then. No AI is involved."""

import hashlib
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ValidationFailedError
from app.models.application_profile import ApplicationProfile
from app.models.fact import Fact, FactKind
from app.models.user import User
from app.schemas.application_profile import (
    EducationEntry,
    EmploymentEntry,
    ProfileContent,
    ProfileLink,
    ProfileOut,
)
from app.schemas.extension import ExtProfileOut
from app.tailoring.contact import first_phone, profile_links
from app.tailoring.experience import role_dates

_PROFILE_HOSTS = {"linkedin.com": "linkedin", "github.com": "github"}
_END_YEAR = re.compile(r"[,(\s]\s*((?:19|20)\d\d)\)?\s*$")


async def _profile(session: AsyncSession, user: User) -> ApplicationProfile | None:
    return await session.scalar(
        select(ApplicationProfile).where(ApplicationProfile.user_id == user.id)
    )


async def _facts(session: AsyncSession, user: User) -> list[Fact]:
    return list(
        (
            await session.scalars(
                select(Fact)
                .where(Fact.user_id == user.id)
                .order_by(Fact.position, Fact.created_at, Fact.id)
            )
        ).all()
    )


def fact_hash(fact: Fact) -> str:
    """Changes when what a Fact says changes; not when it is reordered or toggled."""
    raw = "\x1f".join((str(fact.kind), fact.group, fact.text))
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def cited(content: ProfileContent) -> set[uuid.UUID]:
    return {
        *(i for i in [content.phone_fact_id] if i),
        *(link.fact_id for link in content.links if link.fact_id),
        *(i for entry in content.employment for i in entry.fact_ids),
        *(i for entry in content.education for i in entry.fact_ids),
    }


def stale_paths(content: ProfileContent, reviewed: dict[str, str], facts: list[Fact]) -> list[str]:
    """Entries citing a Fact that was removed, or says something else since the review."""
    now = {str(f.id): fact_hash(f) for f in facts}

    def stale(ids: list[uuid.UUID]) -> bool:
        return any(now.get(str(i)) is None or now[str(i)] != reviewed.get(str(i)) for i in ids)

    paths = []
    if content.phone_fact_id and stale([content.phone_fact_id]):
        paths.append("phone")
    paths += [
        f"links.{i}"
        for i, link in enumerate(content.links)
        if link.fact_id and stale([link.fact_id])
    ]
    paths += [f"employment.{i}" for i, e in enumerate(content.employment) if stale(e.fact_ids)]
    paths += [f"education.{i}" for i, e in enumerate(content.education) if stale(e.fact_ids)]
    return paths


async def get(session: AsyncSession, user: User) -> ProfileOut:
    profile = await _profile(session, user)
    if profile is None:
        return ProfileOut(content=None, version=0, reviewed_at=None, stale=[])
    content = ProfileContent.model_validate(profile.content)
    facts = await _facts(session, user)
    return ProfileOut(
        content=content,
        version=profile.version,
        reviewed_at=profile.reviewed_at,
        stale=stale_paths(content, profile.fact_hashes, facts),
    )


def _detach(content: ProfileContent, gone: set[uuid.UUID]) -> ProfileContent:
    """Drops citations of Facts that no longer exist: the User re-reviewed the values, so
    they stand on their own now, and the entry is no longer stale."""
    return content.model_copy(
        update={
            "phone_fact_id": None if content.phone_fact_id in gone else content.phone_fact_id,
            "links": [
                link.model_copy(update={"fact_id": None}) if link.fact_id in gone else link
                for link in content.links
            ],
            "employment": [
                e.model_copy(update={"fact_ids": [i for i in e.fact_ids if i not in gone]})
                for e in content.employment
            ],
            "education": [
                e.model_copy(update={"fact_ids": [i for i in e.fact_ids if i not in gone]})
                for e in content.education
            ],
        }
    )


async def save(
    session: AsyncSession, user: User, content: ProfileContent, expected: int
) -> ProfileOut:
    """Saving is the review. The row lock makes the version check atomic, and the unique
    index turns two simultaneous first saves into one save and one conflict."""
    conflict = ConflictError("Your profile changed in another tab. Reload it before saving.")
    profile = await session.scalar(
        select(ApplicationProfile)
        .where(ApplicationProfile.user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (profile.version if profile else 0) != expected:
        raise conflict
    facts = {f.id: f for f in await _facts(session, user)}
    citations = cited(content)
    unknown = citations - facts.keys()
    if unknown:
        # Another User's Fact is refused; a Fact that no longer exists is let go.
        owners = (await session.scalars(select(Fact.user_id).where(Fact.id.in_(unknown)))).all()
        if owners:
            raise ValidationFailedError("The profile cites Facts that are not in your Fact Bank")
        content = _detach(content, unknown)
        citations -= unknown
    now = datetime.now(UTC)
    if profile is None:
        profile = ApplicationProfile(user_id=user.id, content={}, version=0, reviewed_at=now)
        session.add(profile)
    profile.content = content.model_dump(mode="json")
    profile.fact_hashes = {str(i): fact_hash(facts[i]) for i in citations}
    profile.version += 1
    profile.reviewed_at = now
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise conflict from exc
    return ProfileOut(content=content, version=profile.version, reviewed_at=now, stale=[])


async def for_extension(session: AsyncSession, user: User) -> ExtProfileOut:
    current = await get(session, user)
    if current.content is None:
        return ExtProfileOut(reviewed=False, version=0, needs_review=True, content=None)
    stale = set(current.stale)
    content = current.content.model_copy(
        update={
            "phone": "" if "phone" in stale else current.content.phone,
            "links": [x for i, x in enumerate(current.content.links) if f"links.{i}" not in stale],
            "employment": [
                x
                for i, x in enumerate(current.content.employment)
                if f"employment.{i}" not in stale
            ],
            "education": [
                x for i, x in enumerate(current.content.education) if f"education.{i}" not in stale
            ],
        }
    )
    return ExtProfileOut(
        reviewed=True, version=current.version, needs_review=bool(stale), content=content
    )


def _link_label(url: str) -> str:
    host = url.split("//")[-1].split("/")[0].removeprefix("www.").lower()
    return _PROFILE_HOSTS.get(host, "portfolio")


def _title_before(text: str, start: int) -> str:
    return text[:start].strip(" \t,;|:-–—(").strip()


async def suggestion(session: AsyncSession, user: User) -> ProfileContent:
    """A starting point from the Google account and the Fact Bank, copied as written."""
    facts = await _facts(session, user)
    first, _, last = " ".join(user.name.split()).partition(" ")
    phone, phone_fact = "", None
    links: list[ProfileLink] = []
    seen_urls: set[str] = set()
    for fact in facts:
        text = " ".join(fact.text.split())
        contact = fact.group.strip().casefold() == "contact"
        if not (contact or fact.kind == FactKind.LINK):
            continue
        if not phone and (found := first_phone(text)):
            phone, phone_fact = found, fact.id
        urls = profile_links(text)
        urls += [w.rstrip("/.,") for w in text.split() if w.startswith(("http://", "https://"))]
        for url in urls:
            full = url if url.startswith("http") else f"https://{url}"
            if full.lower() not in seen_urls and len(links) < 10:
                seen_urls.add(full.lower())
                links.append(ProfileLink(label=_link_label(full), url=full, fact_id=fact.id))

    employment: list[EmploymentEntry] = []
    education: list[EducationEntry] = []
    groups: dict[tuple[FactKind, str], list[Fact]] = {}
    for fact in facts:
        if fact.kind in (FactKind.EXPERIENCE, FactKind.EDUCATION) and fact.group.strip():
            groups.setdefault((fact.kind, fact.group.strip()), []).append(fact)
    for (kind, group), members in groups.items():
        dated = next(((f, d) for f in members if (d := role_dates(f.text))), None)
        source = dated[0] if dated else members[0]
        start, end = (dated[1][0], dated[1][1]) if dated else (None, None)
        if kind == FactKind.EXPERIENCE and len(employment) < 20:
            title = _title_before(" ".join(source.text.split()), dated[1][2]) if dated else ""
            employment.append(
                EmploymentEntry(
                    employer=group[:255],
                    title=title.removeprefix(group).strip(" ,-|–—")[:255],
                    start=start,
                    end=end,
                    current=bool(dated and end is None),
                    fact_ids=[source.id],
                )
            )
        elif kind == FactKind.EDUCATION and len(education) < 10:
            text = " ".join(source.text.split())
            degree = _title_before(text, dated[1][2]) if dated else text
            if not dated and (year := _END_YEAR.search(text)):
                # "B.Tech in Computer Science, 2020": the year is when it ended.
                degree, end = _title_before(text, year.start()), year.group(1)
            education.append(
                EducationEntry(
                    school=group[:255],
                    degree=" ".join(degree.split())[:255],
                    start=start,
                    end=end,
                    fact_ids=[source.id],
                )
            )
    return ProfileContent(
        first_name=first[:255],
        last_name=last[:255],
        email=user.email,
        phone=phone,
        phone_fact_id=phone_fact,
        country=user.country,
        links=links,
        employment=employment,
        education=education,
    )
