"""Greenhouse public job board API, snapshot mode (ADR-0003, ADR-0013)."""

from typing import Any

from app.adapters.base import FetchResult, NormalizedPosting, SnapshotSourceAdapter
from app.adapters.errors import BoardNotFound, SourceBadResponse
from app.adapters.normalize import (
    extract_contact_email,
    html_to_text,
    parse_datetime,
    parse_location,
    work_mode_from,
)
from app.adapters.registry import register_adapter

API = "https://boards-api.greenhouse.io/v1/boards"


@register_adapter
class GreenhouseAdapter(SnapshotSourceAdapter):
    name = "greenhouse"
    label = "Greenhouse"
    priority = 3
    ats = "greenhouse"

    async def fetch_board(self, slug: str) -> FetchResult:
        board = await self.http.get(f"{API}/{slug}")
        if board.status_code == 404:
            raise BoardNotFound(f"Greenhouse has no board named {slug!r}")
        self.check_response(self.label, board)
        company = board.json().get("name") or slug
        response = await self.http.get(f"{API}/{slug}/jobs", params={"content": "true"})
        self.check_response(self.label, response)
        jobs = response.json().get("jobs")
        if not isinstance(jobs, list):
            raise SourceBadResponse("Greenhouse returned an unexpected response")
        return FetchResult(
            postings=[self._to_posting(job, company) for job in jobs if job.get("id")]
        )

    @staticmethod
    def _to_posting(job: dict[str, Any], company: str) -> NormalizedPosting:
        location_text = (job.get("location") or {}).get("name") or ""
        description = html_to_text(job.get("content") or "")
        return NormalizedPosting(
            source_job_id=str(job["id"]),
            title=job.get("title") or "Untitled",
            company=company,
            description=description,
            locations=[parse_location(location_text)] if location_text else [],
            work_mode=work_mode_from(location_text) or work_mode_from(description[:400]),
            apply_url=job.get("absolute_url"),
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(job.get("first_published") or job.get("updated_at")),
        )
