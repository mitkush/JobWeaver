"""Workable public widget API, snapshot mode (ADR-0003, ADR-0013). One call per board
returns every published job with its description (details=true)."""

from typing import Any

from app.adapters.base import FetchResult, Location, NormalizedPosting, SnapshotSourceAdapter
from app.adapters.errors import BoardNotFound, SourceBadResponse
from app.adapters.normalize import (
    company_from_slug,
    country_code,
    extract_contact_email,
    html_to_text,
    normalize_city,
    parse_datetime,
    work_mode_from,
)
from app.adapters.registry import register_adapter

API = "https://apply.workable.com/api/v1/widget/accounts"


@register_adapter
class WorkableAdapter(SnapshotSourceAdapter):
    name = "workable"
    label = "Workable"
    priority = 3
    ats = "workable"

    async def fetch_board(self, slug: str) -> FetchResult:
        response = await self.http.get(f"{API}/{slug}", params={"details": "true"})
        if response.status_code == 404:
            raise BoardNotFound(f"Workable has no account named {slug!r}")
        self.check_response(self.label, response)
        body = response.json()
        jobs = body.get("jobs") if isinstance(body, dict) else None
        if not isinstance(jobs, list):
            raise SourceBadResponse("Workable returned an unexpected response")
        company = body.get("name") or company_from_slug(slug)
        return FetchResult(
            postings=[self._to_posting(job, company) for job in jobs if job.get("shortcode")]
        )

    @staticmethod
    def _to_posting(job: dict[str, Any], company: str) -> NormalizedPosting:
        remote = bool(job.get("telecommuting"))
        places = [p for p in job.get("locations") or [] if isinstance(p, dict)] or [job]
        locations = [
            Location(
                city=normalize_city(place.get("city")),
                country=country_code(place.get("countryCode") or place.get("country")),
                remote=remote,
            )
            for place in places
            if not place.get("hidden") and (place.get("city") or place.get("country"))
        ]
        if remote and not locations:
            locations = [Location(remote=True)]
        description = html_to_text(job.get("description"))
        return NormalizedPosting(
            source_job_id=str(job["shortcode"]),
            title=job.get("title") or "Untitled",
            company=company,
            description=description,
            locations=locations,
            work_mode=work_mode_from(
                str(job.get("workplace_type") or "").replace("_", "-"), remote_flag=remote
            ),
            apply_url=job.get("url") or job.get("shortlink") or job.get("application_url"),
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(job.get("published_on") or job.get("created_at")),
        )
