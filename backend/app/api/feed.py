import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import CurrentUser, DbSession
from app.schemas.feed import FeedOut, FeedQuery, JobDetailOut, JobRef
from app.services import correspondence, feed

router = APIRouter(prefix="/api", tags=["feed"])


@router.get("/feed")
async def get_feed(
    db: DbSession, user: CurrentUser, query: Annotated[FeedQuery, Query()]
) -> FeedOut:
    return await feed.list_feed(db, user, query)


@router.post("/feed/{job_id}/hide", status_code=204)
async def hide_job(db: DbSession, user: CurrentUser, job_id: uuid.UUID) -> Response:
    await feed.set_hidden(db, user, job_id, True)
    await db.commit()
    return Response(status_code=204)


@router.delete("/feed/{job_id}/hide", status_code=204)
async def unhide_job(db: DbSession, user: CurrentUser, job_id: uuid.UUID) -> Response:
    await feed.set_hidden(db, user, job_id, False)
    await db.commit()
    return Response(status_code=204)


@router.get("/jobs/{job_id}")
async def get_job(db: DbSession, user: CurrentUser, job_id: uuid.UUID) -> JobDetailOut:
    return await feed.job_detail(db, user, job_id)


@router.post("/possible-duplicates/{pair_id}/confirm")
async def confirm_duplicate(db: DbSession, user: CurrentUser, pair_id: uuid.UUID) -> JobRef:
    job_id = await correspondence.confirm_pair(db, user, pair_id)
    await db.commit()
    return JobRef(job_id=job_id)


@router.post("/possible-duplicates/{pair_id}/reject", status_code=204)
async def reject_duplicate(db: DbSession, user: CurrentUser, pair_id: uuid.UUID) -> Response:
    await correspondence.reject_pair(db, user, pair_id)
    await db.commit()
    return Response(status_code=204)


@router.post("/jobs/{job_id}/postings/{posting_id}/split")
async def split_posting(
    db: DbSession, user: CurrentUser, job_id: uuid.UUID, posting_id: uuid.UUID
) -> JobRef:
    new_job = await correspondence.split_posting(db, user, job_id, posting_id)
    await db.commit()
    return JobRef(job_id=new_job)
