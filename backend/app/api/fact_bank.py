import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession, Gateway
from app.core.errors import GatewayError, NotFoundError
from app.models.document import DocumentKind
from app.schemas.facts import (
    DocumentOut,
    FactBankChanges,
    FactBankExport,
    FactCreate,
    FactMerge,
    FactOut,
    FactUpdate,
    UploadResult,
)
from app.services import fact_bank

router = APIRouter(prefix="/api", tags=["fact-bank"])


async def _rebuild(db: DbSession, user: CurrentUser, gateway: Gateway) -> FactBankChanges:
    try:
        changes = await fact_bank.rebuild_fact_bank(db, user, gateway)
    except GatewayError as exc:
        await db.rollback()
        raise GatewayError(
            f"Your document is saved, but building your Fact Bank failed. {exc.message} "
            "Try again in a few minutes."
        ) from exc
    await db.commit()
    return changes


async def _upload_result(
    db: DbSession, user: CurrentUser, document_id: uuid.UUID, changes: FactBankChanges
) -> UploadResult:
    documents = await fact_bank.list_documents(db, user)
    document = next(d for d in documents if d.id == document_id)
    facts = await fact_bank.list_facts(db, user)
    return UploadResult(
        document=DocumentOut.model_validate(document),
        changes=changes,
        facts=[FactOut.model_validate(f) for f in facts],
    )


@router.get("/documents")
async def list_documents(db: DbSession, user: CurrentUser) -> list[DocumentOut]:
    return [DocumentOut.model_validate(d) for d in await fact_bank.list_documents(db, user)]


@router.post("/documents")
async def upload_document(
    db: DbSession,
    user: CurrentUser,
    gateway: Gateway,
    kind: Annotated[DocumentKind, Form()],
    file: Annotated[UploadFile, File()],
) -> UploadResult:
    data = await file.read()
    document = await fact_bank.save_document(
        db,
        user,
        kind=kind,
        filename=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        data=data,
    )
    await db.commit()
    changes = await _rebuild(db, user, gateway)
    return await _upload_result(db, user, document.id, changes)


class TextDocumentIn(BaseModel):
    kind: DocumentKind
    text: str = Field(min_length=20, max_length=50_000)


@router.post("/documents/text")
async def save_text_document(
    db: DbSession, user: CurrentUser, gateway: Gateway, body: TextDocumentIn
) -> UploadResult:
    """For a short summary typed in the browser instead of a file."""
    document = await fact_bank.save_document(
        db,
        user,
        kind=body.kind,
        filename=f"{body.kind.value}.txt",
        content_type="text/plain",
        data=body.text.encode(),
    )
    await db.commit()
    changes = await _rebuild(db, user, gateway)
    return await _upload_result(db, user, document.id, changes)


@router.post("/fact-bank/rebuild")
async def rebuild(db: DbSession, user: CurrentUser, gateway: Gateway) -> FactBankChanges:
    return await _rebuild(db, user, gateway)


@router.post("/fact-bank/review", status_code=204)
async def review(db: DbSession, user: CurrentUser) -> None:
    await fact_bank.mark_reviewed(db, user)
    await db.commit()


@router.get("/fact-bank/export")
async def export(db: DbSession, user: CurrentUser) -> FactBankExport:
    return FactBankExport(
        documents=[DocumentOut.model_validate(d) for d in await fact_bank.list_documents(db, user)],
        facts=[FactOut.model_validate(f) for f in await fact_bank.list_facts(db, user)],
    )


@router.delete("/fact-bank", status_code=204)
async def delete_all(db: DbSession, user: CurrentUser) -> None:
    await fact_bank.delete_fact_bank(db, user)
    await db.commit()


@router.get("/facts")
async def list_facts(db: DbSession, user: CurrentUser) -> list[FactOut]:
    return [FactOut.model_validate(f) for f in await fact_bank.list_facts(db, user)]


@router.post("/facts", status_code=201)
async def create_fact(db: DbSession, user: CurrentUser, body: FactCreate) -> FactOut:
    fact = await fact_bank.create_fact(db, user, body)
    await db.commit()
    return FactOut.model_validate(fact)


@router.patch("/facts/{fact_id}")
async def update_fact(
    db: DbSession, user: CurrentUser, fact_id: uuid.UUID, body: FactUpdate
) -> FactOut:
    fact = await fact_bank.update_fact(db, user, fact_id, body)
    await db.commit()
    return FactOut.model_validate(fact)


@router.delete("/facts/{fact_id}", status_code=204)
async def delete_fact(db: DbSession, user: CurrentUser, fact_id: uuid.UUID) -> None:
    await fact_bank.delete_fact(db, user, fact_id)
    await db.commit()


@router.post("/facts/merge")
async def merge_facts(db: DbSession, user: CurrentUser, body: FactMerge) -> FactOut:
    fact = await fact_bank.merge_facts(db, user, body)
    await db.commit()
    return FactOut.model_validate(fact)


__all__ = ["router", "NotFoundError"]
