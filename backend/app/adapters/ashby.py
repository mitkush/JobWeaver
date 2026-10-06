"""Ashby public job board API, snapshot mode (ADR-0003, ADR-0013)."""

from typing import Any

from app.adapters.base import (
    FetchResult,
    Location,
    NormalizedPosting,
    SnapshotSourceAdapter,
    WorkMode,
)
from app.adapters.errors import BoardNotFound, SourceBadResponse
from app.adapters.normalize import (
    company_from_slug,
    country_code,
    extract_contact_email,
    html_to_text,
    normalize_city,
    parse_datetime,
    parse_location,
    work_mode_from,
)
from app.adapters.registry import register_adapter

API = "https://api.ashbyhq.com/posting-api/job-board"
_WORKPLACE = {"remote": WorkMode.REMOTE, "hybrid": WorkMode.HYBRID, "onsite": WorkMode.ONSITE}


@register_adapter
class AshbyAdapter(SnapshotSourceAdapter):
    name = "ashby"
    label = "Ashby"
    priority = 3
    ats = "ashby"

    async def fetch_board(self, slug: str) -> FetchResult:
        response = await self.http.get(f"{API}/{slug}", params={"includeCompensation": "false"})
        if response.status_code == 404:
            raise BoardNotFound(f"Ashby has no board named {slug!r}")
        self.check_response(self.label, response)
        body = response.json()
        jobs = body.get("jobs") if isinstance(body, dict) else None
        if not isinstance(jobs, list):
            raise SourceBadResponse("Ashby returned an unexpected response")
        company = company_from_slug(slug)
        return FetchResult(
            postings=[
                self._to_posting(job, company)
                for job in jobs
                # Unlisted jobs are reachable by link only; they are not advertised.
                if job.get("id") and job.get("isListed", True)
            ]
        )

    @staticmethod
    def _to_posting(job: dict[str, Any], company: str) -> NormalizedPosting:
        remote = bool(job.get("isRemote"))
        workplace = _WORKPLACE.get(str(job.get("workplaceType") or "").lower().replace("-", ""))
        locations = []
        address = (job.get("address") or {}).get("postalAddress") or {}
        if address.get("addressCountry") or address.get("addressLocality"):
            locations.append(
                Location(
                    city=normalize_city(address.get("addressLocality")),
                    country=country_code(address.get("addressCountry")),
                    remote=remote,
                )
            )
        elif job.get("location"):
            locations.append(parse_location(job["location"]))
        for extra in job.get("secondaryLocations") or []:
            text = extra.get("location") if isinstance(extra, dict) else None
            if text:
                locations.append(parse_location(text))
        description = job.get("descriptionPlain") or html_to_text(job.get("descriptionHtml"))
        return NormalizedPosting(
            source_job_id=str(job["id"]),
            title=job.get("title") or "Untitled",
            company=company,
            description=description,
            locations=locations,
            work_mode=workplace or work_mode_from(job.get("location"), remote_flag=remote),
            apply_url=job.get("jobUrl") or job.get("applyUrl"),
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(job.get("publishedAt") or job.get("publishedDate")),
        )
