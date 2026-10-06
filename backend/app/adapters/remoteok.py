"""Remote OK public API. Its terms ask that each job credits Remote OK and links to the
job's Remote OK page, so that page is the apply link."""

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
class RemoteOkAdapter(RemoteBoardAdapter):
    name = "remoteok"
    label = "Remote OK"

    async def records(self, window: FetchWindow) -> list[Any]:
        response = await self.http.get("https://remoteok.com/api")
        self.check_response(self.label, response)
        data = response.json()
        if not isinstance(data, list):
            raise SourceBadResponse("Remote OK returned an unexpected response")
        # The first element is Remote OK's legal notice, not a job.
        return [r for r in data if isinstance(r, dict) and r.get("id") and r.get("position")]

    def to_posting(self, job: dict[str, Any]) -> NormalizedPosting | None:
        if not job.get("company"):
            return None
        description = html_to_text(job.get("description"))
        return NormalizedPosting(
            source_job_id=str(job["id"]),
            title=job["position"],
            company=job["company"],
            description=description,
            locations=remote_locations(job.get("location")),
            work_mode=WorkMode.REMOTE,
            apply_url=job.get("url") or job.get("apply_url"),
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(job.get("date") or job.get("epoch")),
        )
