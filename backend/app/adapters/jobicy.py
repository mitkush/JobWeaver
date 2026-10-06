"""Jobicy remote jobs API. Its terms ask for at most one sync an hour and a link to the
canonical Jobicy page, which is the apply link."""

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


@register_adapter
class JobicyAdapter(RemoteBoardAdapter):
    name = "jobicy"
    label = "Jobicy"

    async def records(self, window: FetchWindow) -> list[Any]:
        response = await self.http.get(
            "https://jobicy.com/api/v2/remote-jobs", params={"count": 200}
        )
        self.check_response(self.label, response)
        body = response.json()
        jobs = body.get("jobs") if isinstance(body, dict) else None
        if not isinstance(jobs, list):
            raise SourceBadResponse("Jobicy returned an unexpected response")
        return [j for j in jobs if isinstance(j, dict)]

    def to_posting(self, job: dict[str, Any]) -> NormalizedPosting | None:
        if not (job.get("id") and job.get("jobTitle") and job.get("companyName")):
            return None
        description = html_to_text(job.get("jobDescription") or job.get("jobExcerpt"))
        return NormalizedPosting(
            source_job_id=str(job["id"]),
            title=html_to_text(job["jobTitle"]),
            company=html_to_text(job["companyName"]),
            description=description,
            locations=remote_locations(job.get("jobGeo")),
            work_mode=WorkMode.REMOTE,
            apply_url=job.get("url"),
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(job.get("pubDate")),
        )
