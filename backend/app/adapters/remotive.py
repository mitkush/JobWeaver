"""Remotive remote jobs API. Fetched once per run, not per query: Remotive asks for
at most 4 requests a day and credit back to each job's Remotive URL (COSTS.md)."""

from typing import Any

from app.adapters.base import (
    FetchResult,
    FetchWindow,
    Location,
    NormalizedPosting,
    SourceQuery,
    WindowedSourceAdapter,
    WorkMode,
)
from app.adapters.errors import SourceBadResponse
from app.adapters.normalize import (
    extract_contact_email,
    html_to_text,
    parse_datetime,
    parse_location,
)
from app.adapters.registry import register_adapter

API = "https://remotive.com/api/remote-jobs"


@register_adapter
class RemotiveAdapter(WindowedSourceAdapter):
    name = "remotive"
    label = "Remotive"
    priority = 8
    per_query = False
    min_interval_hours = 6

    async def fetch_window(self, query: SourceQuery | None, window: FetchWindow) -> FetchResult:
        response = await self.http.get(API)
        self.check_response(self.label, response)
        jobs = response.json().get("jobs")
        if not isinstance(jobs, list):
            raise SourceBadResponse("Remotive returned an unexpected response")
        postings = []
        for job in jobs:
            posting = self._to_posting(job)
            if posting and (posting.posted_at is None or posting.posted_at >= window.since):
                postings.append(posting)
        return FetchResult(postings=postings, credits_used=1)

    @staticmethod
    def _to_posting(job: dict[str, Any]) -> NormalizedPosting | None:
        if not (job.get("id") and job.get("title") and job.get("company_name")):
            return None
        region = job.get("candidate_required_location") or ""
        parsed = parse_location(region)
        location = Location(city=None, country=parsed.country, remote=True)
        description = html_to_text(job.get("description") or "")
        return NormalizedPosting(
            source_job_id=str(job["id"]),
            title=job["title"],
            company=job["company_name"],
            description=description,
            locations=[location],
            work_mode=WorkMode.REMOTE,
            apply_url=job.get("url"),
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(job.get("publication_date")),
        )
