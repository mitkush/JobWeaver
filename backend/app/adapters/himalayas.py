"""Himalayas remote jobs API: newest first, 20 per page, paged by cursor until the window
start is reached."""

from typing import Any

from app.adapters.base import FetchWindow, NormalizedPosting, WorkMode
from app.adapters.errors import SourceBadResponse
from app.adapters.normalize import (
    extract_contact_email,
    html_to_text,
    parse_datetime,
    remote_locations,
)
from app.adapters.registry import register_adapter
from app.adapters.remote_boards import RemoteBoardAdapter

API = "https://himalayas.app/jobs/api"
MAX_PAGES = 50


@register_adapter
class HimalayasAdapter(RemoteBoardAdapter):
    name = "himalayas"
    label = "Himalayas"

    async def records(self, window: FetchWindow) -> list[Any]:
        jobs: list[dict[str, Any]] = []
        params: dict[str, Any] = {"limit": 20}
        for _ in range(MAX_PAGES):
            response = await self.http.get(API, params=params)
            self.check_response(self.label, response)
            body = response.json()
            page = body.get("jobs") if isinstance(body, dict) else None
            if not isinstance(page, list):
                raise SourceBadResponse("Himalayas returned an unexpected response")
            jobs += [j for j in page if isinstance(j, dict)]
            dates = [parse_datetime(j.get("pubDate")) for j in page if isinstance(j, dict)]
            older = [d for d in dates if d is not None and d < window.since]
            cursor = body.get("nextCursor")
            if not page or not cursor or older:
                break
            params["cursor"] = cursor
        return jobs

    def to_posting(self, job: dict[str, Any]) -> NormalizedPosting | None:
        job_id = job.get("guid") or job.get("applicationLink")
        if not (job_id and job.get("title") and job.get("companyName")):
            return None
        description = html_to_text(job.get("description") or job.get("excerpt"))
        return NormalizedPosting(
            source_job_id=str(job_id)[:255],
            title=job["title"],
            company=job["companyName"],
            description=description,
            locations=remote_locations(job.get("locationRestrictions") or []),
            work_mode=WorkMode.REMOTE,
            apply_url=job.get("applicationLink") or job.get("guid"),
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(job.get("pubDate")),
        )
