import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import NotFoundError, PreconditionError, ValidationFailedError
from app.documents.extract import extract_text
from app.gateway.base import BaseAIGateway
from app.gateway.schemas import DocumentInput, ParseDocumentsRequest
from app.models.document import Document, DocumentKind
from app.models.fact import DismissedFact, Fact, FactOrigin
from app.models.user import User
from app.schemas.facts import FactBankChanges, FactCreate, FactMerge, FactUpdate
from app.services.accounts import ensure_ai_allowed


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


async def _dismiss(session: AsyncSession, user: User, *texts: str) -> None:
    """Remembers text the User took out, so a re-parse does not add it back."""
    for key in {_norm(text) for text in texts if text.strip()}:
        await session.execute(
            insert(DismissedFact)
            .values(id=uuid.uuid4(), user_id=user.id, text_key=key)
            .on_conflict_do_nothing(index_elements=["user_id", "text_key"])
        )


async def _dismissed(session: AsyncSession, user: User) -> set[str]:
    return set(
        (
            await session.execute(
                select(DismissedFact.text_key).where(DismissedFact.user_id == user.id)
            )
        ).scalars()
    )


async def list_documents(session: AsyncSession, user: User) -> list[Document]:
    query = select(Document).where(Document.user_id == user.id).order_by(Document.kind)
    return list((await session.execute(query)).scalars())


async def list_facts(session: AsyncSession, user: User) -> list[Fact]:
    query = (
        select(Fact)
        .where(Fact.user_id == user.id)
        .order_by(Fact.kind, Fact.group, Fact.position, Fact.created_at)
    )
    return list((await session.execute(query)).scalars())


async def save_document(
    session: AsyncSession,
    user: User,
    *,
    kind: DocumentKind,
    filename: str,
    content_type: str,
    data: bytes,
) -> Document:
    """Stores the upload, replacing the user's previous document of the same kind."""
    ensure_ai_allowed(user)
    if len(data) > get_settings().max_upload_bytes:
        raise ValidationFailedError("Files must be 5 MB or smaller")
    text = extract_text(data, content_type, filename)
    await session.execute(
        delete(Document).where(Document.user_id == user.id, Document.kind == kind)
    )
    document = Document(
        user_id=user.id,
        kind=kind,
        filename=filename[:255],
        content_type=content_type[:100],
        size_bytes=len(data),
        content=data,
        extracted_text=text,
    )
    session.add(document)
    await session.flush()
    return document


async def rebuild_fact_bank(
    session: AsyncSession, user: User, gateway: BaseAIGateway
) -> FactBankChanges:
    """Re-parses all documents. AI Facts the user never touched are replaced; edited and
    user-added Facts are always kept (FR-A2 AC3)."""
    ensure_ai_allowed(user)
    documents = await list_documents(session, user)
    if not documents:
        raise PreconditionError("Upload your resume first")
    response = await gateway.parse_documents(
        ParseDocumentsRequest(
            user_id=user.id,
            documents=[DocumentInput(kind=d.kind, text=d.extracted_text) for d in documents],
        )
    )
    facts = await list_facts(session, user)
    replaceable = [f for f in facts if f.origin == FactOrigin.AI and not f.edited]
    kept = [f for f in facts if f not in replaceable]
    old_texts = {_norm(f.text): f.text for f in replaceable}
    # Kept Facts and anything the User deleted, merged or reworded never come back.
    kept_texts = {_norm(f.text) for f in kept} | await _dismissed(session, user)

    for fact in replaceable:
        await session.delete(fact)
    new_texts: dict[str, str] = {}
    for position, parsed in enumerate(response.result.facts):
        key = _norm(parsed.text)
        if key in kept_texts or key in new_texts:
            continue
        new_texts[key] = parsed.text
        session.add(
            Fact(
                user_id=user.id,
                kind=parsed.kind,
                group=parsed.group[:255],
                text=parsed.text,
                source_kind=parsed.source_kind,
                in_base_resume=parsed.in_base_resume,
                origin=FactOrigin.AI,
                edited=False,
                position=position,
            )
        )
    await session.flush()
    return FactBankChanges(
        added=[text for key, text in new_texts.items() if key not in old_texts],
        removed=[text for key, text in old_texts.items() if key not in new_texts],
        kept_edits=len(kept),
    )


async def _owned_fact(session: AsyncSession, user: User, fact_id: uuid.UUID) -> Fact:
    fact = await session.get(Fact, fact_id)
    if fact is None or fact.user_id != user.id:
        raise NotFoundError("Fact not found")
    return fact


async def create_fact(session: AsyncSession, user: User, data: FactCreate) -> Fact:
    fact = Fact(
        user_id=user.id,
        kind=data.kind,
        group=data.group,
        text=data.text.strip(),
        source_kind=None,
        in_base_resume=data.in_base_resume,
        origin=FactOrigin.USER,
        edited=False,
        position=10_000,
    )
    session.add(fact)
    await session.flush()
    return fact


async def update_fact(
    session: AsyncSession, user: User, fact_id: uuid.UUID, data: FactUpdate
) -> Fact:
    fact = await _owned_fact(session, user, fact_id)
    if data.text is not None and _norm(data.text) != _norm(fact.text):
        await _dismiss(session, user, fact.text)  # the AI's wording must not return beside it
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(fact, field, value.strip() if isinstance(value, str) else value)
    fact.edited = True
    await session.flush()
    return fact


async def delete_fact(session: AsyncSession, user: User, fact_id: uuid.UUID) -> None:
    fact = await _owned_fact(session, user, fact_id)
    await _dismiss(session, user, fact.text)
    await session.delete(fact)
    await session.flush()


async def merge_facts(session: AsyncSession, user: User, data: FactMerge) -> Fact:
    facts = [await _owned_fact(session, user, fact_id) for fact_id in set(data.fact_ids)]
    if len(facts) < 2:
        raise ValidationFailedError("Pick at least two different Facts to merge")
    first = min(facts, key=lambda f: f.position)
    merged = Fact(
        user_id=user.id,
        kind=first.kind,
        group=first.group,
        text=data.text.strip(),
        source_kind=first.source_kind,
        in_base_resume=any(f.in_base_resume for f in facts),
        origin=FactOrigin.USER,
        edited=True,
        position=first.position,
    )
    await _dismiss(
        session, user, *(fact.text for fact in facts if _norm(fact.text) != _norm(merged.text))
    )
    for fact in facts:
        await session.delete(fact)
    session.add(merged)
    await session.flush()
    return merged


async def mark_reviewed(session: AsyncSession, user: User) -> None:
    if not await list_facts(session, user):
        raise PreconditionError("There are no Facts to review yet")
    user.fact_bank_reviewed_at = datetime.now(UTC)
    await session.flush()


async def delete_fact_bank(session: AsyncSession, user: User) -> None:
    await session.execute(delete(Fact).where(Fact.user_id == user.id))
    await session.execute(delete(DismissedFact).where(DismissedFact.user_id == user.id))
    await session.execute(delete(Document).where(Document.user_id == user.id))
    user.fact_bank_reviewed_at = None
    await session.flush()
