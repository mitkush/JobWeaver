"""Lever public postings API, snapshot mode (ADR-0003, ADR-0013)."""

from typing import Any

from app.adapters.base import FetchResult, NormalizedPosting, SnapshotSourceAdapter, WorkMode
from app.adapters.errors import BoardNotFound, SourceBadResponse
from app.adapters.normalize import (
    company_from_slug,
    extract_contact_email,
    html_to_text,
    parse_datetime,
    parse_location,
    work_mode_from,
)
from app.adapters.registry import register_adapter

API = "https://api.lever.co/v0/postings"
_WORKPLACE = {"remote": WorkMode.REMOTE, "hybrid": WorkMode.HYBRID, "onsite": WorkMode.ONSITE}


@register_adapter
class LeverAdapter(SnapshotSourceAdapter):
    name = "lever"
    label = "Lever"
    priority = 3
    ats = "lever"

    async def fetch_board(self, slug: str) -> FetchResult:
        response = await self.http.get(f"{API}/{slug}", params={"mode": "json"})
        if response.status_code == 404:
            raise BoardNotFound(f"Lever has no board named {slug!r}")
        self.check_response(self.label, response)
        jobs = response.json()
        if not isinstance(jobs, list):
            raise SourceBadResponse("Lever returned an unexpected response")
        company = company_from_slug(slug)
        return FetchResult(
            postings=[self._to_posting(job, company) for job in jobs if job.get("id")]
        )

    @staticmethod
    def _to_posting(job: dict[str, Any], company: str) -> NormalizedPosting:
        categories = job.get("categories") or {}
        texts = categories.get("allLocations") or [categories.get("location") or ""]
        lists = "\n".join(
            f"{item.get('text', '')}\n{html_to_text(item.get('content', ''))}"
            for item in job.get("lists") or []
        )
        description = "\n".join(
            part
            for part in (
                job.get("descriptionPlain") or html_to_text(job.get("description")),
                lists,
                job.get("additionalPlain") or "",
            )
            if part
        ).strip()
        workplace = _WORKPLACE.get(str(job.get("workplaceType", "")).lower())
        return NormalizedPosting(
            source_job_id=str(job["id"]),
            title=job.get("text") or "Untitled",
            company=company,
            description=description,
            locations=[parse_location(t) for t in texts if t],
            work_mode=workplace or work_mode_from(" ".join(texts)),
            apply_url=job.get("hostedUrl") or job.get("applyUrl"),
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(job.get("createdAt")),
        )
