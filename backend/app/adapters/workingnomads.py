"""Working Nomads public jobs feed. It has no job id, so the job URL is the id."""

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
class WorkingNomadsAdapter(RemoteBoardAdapter):
    name = "workingnomads"
    label = "Working Nomads"

    async def records(self, window: FetchWindow) -> list[Any]:
        response = await self.http.get("https://www.workingnomads.com/api/exposed_jobs/")
        self.check_response(self.label, response)
        data = response.json()
        if not isinstance(data, list):
            raise SourceBadResponse("Working Nomads returned an unexpected response")
        return [j for j in data if isinstance(j, dict)]

    def to_posting(self, job: dict[str, Any]) -> NormalizedPosting | None:
        if not (job.get("url") and job.get("title") and job.get("company_name")):
            return None
        description = html_to_text(job.get("description"))
        return NormalizedPosting(
            source_job_id=str(job["url"])[:255],
            title=job["title"],
            company=job["company_name"],
            description=description,
            locations=remote_locations(job.get("location")),
            work_mode=WorkMode.REMOTE,
            apply_url=job["url"],
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(job.get("pub_date")),
        )
