"""Writing Style (ADR-0017): how the User writes, never what they did.

Built from text the User wrote themselves. Excerpts are redacted by code (names, numbers,
dates and technologies become placeholders) and dropped when little but placeholders is
left, so a style example can never carry a claim into an answer (ADR-0005)."""

import json
import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PreconditionError
from app.gateway.base import BaseAIGateway
from app.gateway.schemas import WritingStyleRequest
from app.models.application_profile import SavedAnswer
from app.models.document import Document, DocumentKind
from app.models.fact import Fact
from app.models.user import User
from app.schemas.writing_style import WritingStyleIn, WritingStyleOut
from app.services.accounts import ensure_ai_allowed
from app.tailoring.checks import technologies_in

_NUMBER = re.compile(r"\b\d[\d,.:%/-]*\b")
_MONTH = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{2,4}\b",
    re.IGNORECASE,
)
# Capitalised words not at a sentence start: proper names of people, products, places.
_PROPER = re.compile(r"(?<=[a-z,;:]\s)([A-Z][\w&.-]+(?:\s+[A-Z][\w&.-]+)*)")
_PLACEHOLDER = re.compile(r"\[(?:NAME|NUMBER|DATE|TECH)\]")
MAX_TRAITS = 8
MAX_EXCERPTS = 3


def redact(text: str, names: set[str]) -> str:
    """Placeholders for anything that could be a claim: names, numbers, dates, tools."""
    out = " ".join(text.split())[:300]
    for name in sorted(names, key=len, reverse=True):
        if len(name) > 1:
            out = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", "[NAME]", out, flags=re.IGNORECASE)
    out = _MONTH.sub("[DATE]", out)
    for written in sorted(technologies_in(out).values(), key=len, reverse=True):
        out = re.sub(rf"(?<!\w){re.escape(written)}(?!\w)", "[TECH]", out)
    out = _NUMBER.sub("[NUMBER]", out)
    return _PROPER.sub("[NAME]", out)


def _mostly_placeholders(text: str) -> bool:
    words = text.split()
    return not words or len(_PLACEHOLDER.findall(text)) / len(words) > 0.25


async def _names(session: AsyncSession, user: User) -> set[str]:
    groups = await session.scalars(select(Fact.group).where(Fact.user_id == user.id))
    names = {g.strip() for g in groups if g and g.strip() and g.strip().casefold() != "contact"}
    names.update(part for part in user.name.split() if len(part) > 1)
    return names


def _load(user: User) -> dict:
    try:
        data = json.loads(user.writing_style or "{}")
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def get(user: User) -> WritingStyleOut:
    data = _load(user)
    return WritingStyleOut(
        traits=list(data.get("traits", []))[:MAX_TRAITS],
        excerpts=list(data.get("excerpts", []))[:MAX_EXCERPTS],
        built_at=data.get("built_at"),
    )


def prompt_text(user: User) -> str:
    """What the answer task sees: traits and redacted excerpts, labelled as tone only."""
    style = get(user)
    if not style.traits and not style.excerpts:
        return ""
    lines = ["Traits: " + "; ".join(style.traits)] if style.traits else []
    if style.excerpts:
        lines.append("Tone examples (content redacted): " + " | ".join(style.excerpts))
    return "\n".join(lines)


async def _store(
    session: AsyncSession, user: User, traits: list[str], excerpts: list[str]
) -> WritingStyleOut:
    names = await _names(session, user)
    clean = [redact(e, names) for e in excerpts]
    data = {
        "traits": [" ".join(t.split())[:200] for t in traits if t.strip()][:MAX_TRAITS],
        "excerpts": [e for e in clean if not _mostly_placeholders(e)][:MAX_EXCERPTS],
        "built_at": datetime.now(UTC).isoformat(),
    }
    user.writing_style = json.dumps(data)
    await session.flush()
    return get(user)


async def samples(session: AsyncSession, user: User) -> list[str]:
    """Only text the User wrote: their summary and the answers they saved or reworked."""
    summary = await session.scalar(
        select(Document.extracted_text).where(
            Document.user_id == user.id, Document.kind == DocumentKind.SUMMARY
        )
    )
    answers = await session.scalars(
        select(SavedAnswer.answer)
        .where(SavedAnswer.user_id == user.id, SavedAnswer.sensitive.is_(False))
        .order_by(SavedAnswer.updated_at.desc())
        .limit(6)
    )
    texts = ([summary] if summary else []) + [a for a in answers if len(a.split()) >= 8]
    return [t for t in texts if t and t.strip()][:8]


async def rebuild(session: AsyncSession, user: User, gateway: BaseAIGateway) -> WritingStyleOut:
    ensure_ai_allowed(user)
    texts = await samples(session, user)
    if not texts:
        raise PreconditionError(
            "Add a short summary in your Fact Bank, or save a few answers in your own words, first"
        )
    response = await gateway.describe_writing_style(
        WritingStyleRequest(user_id=user.id, samples=texts)
    )
    return await _store(session, user, response.result.traits, response.result.excerpts)


async def save(session: AsyncSession, user: User, body: WritingStyleIn) -> WritingStyleOut:
    """The User's own edit; excerpts are redacted again, so an edit cannot add a claim."""
    return await _store(session, user, body.traits, body.excerpts)


async def clear(session: AsyncSession, user: User) -> None:
    user.writing_style = ""
    await session.flush()
