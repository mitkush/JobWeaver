"""SmartRecruiters public Posting API, snapshot mode (ADR-0003, ADR-0013).

The list has no descriptions, so each posting needs one detail call; they run a few at a
time. Only companies that publish a public feed are reachable."""

from typing import Any

from app.adapters.base import (
    FetchResult,
    Location,
    NormalizedPosting,
    SnapshotSourceAdapter,
    WorkMode,
    bounded_gather,
)
from app.adapters.errors import BoardNotFound, SourceBadResponse
from app.adapters.normalize import (
    company_from_slug,
    country_code,
    extract_contact_email,
    html_to_text,
    normalize_city,
    parse_datetime,
)
from app.adapters.registry import register_adapter

API = "https://api.smartrecruiters.com/v1/companies"
PAGE = 100
# Safety stop for a runaway paginator; far above any single company's open jobs.
MAX_PAGES = 50
_SECTIONS = ("jobDescription", "qualifications", "additionalInformation")


@register_adapter
class SmartRecruitersAdapter(SnapshotSourceAdapter):
    name = "smartrecruiters"
    label = "SmartRecruiters"
    priority = 3
    ats = "smartrecruiters"
    detail_concurrency = 5

    async def fetch_board(self, slug: str) -> FetchResult:
        summaries: list[dict[str, Any]] = []
        for page in range(MAX_PAGES):
            response = await self.http.get(
                f"{API}/{slug}/postings", params={"limit": PAGE, "offset": page * PAGE}
            )
            if response.status_code == 404:
                raise BoardNotFound(f"SmartRecruiters has no company named {slug!r}")
            self.check_response(self.label, response)
            body = response.json()
            content = body.get("content") if isinstance(body, dict) else None
            if not isinstance(content, list):
                raise SourceBadResponse("SmartRecruiters returned an unexpected response")
            summaries.extend(c for c in content if isinstance(c, dict) and c.get("id"))
            if len(content) < PAGE or len(summaries) >= int(body.get("totalFound") or 0):
                break
        else:
            # A partial list would close jobs that are still open, so it is not used.
            raise SourceBadResponse(f"SmartRecruiters kept paginating for {slug!r}")
        details = await bounded_gather(
            (self._detail(slug, s["id"]) for s in summaries), self.detail_concurrency
        )
        return FetchResult(
            postings=[self._to_posting(s, d, slug) for s, d in zip(summaries, details, strict=True)]
        )

    async def _detail(self, slug: str, posting_id: str) -> dict[str, Any]:
        response = await self.http.get(f"{API}/{slug}/postings/{posting_id}")
        if response.status_code == 404:
            # Closed between the list and this call; the summary is still enough.
            return {}
        self.check_response(self.label, response)
        body = response.json()
        return body if isinstance(body, dict) else {}

    @staticmethod
    def _to_posting(
        summary: dict[str, Any], detail: dict[str, Any], slug: str
    ) -> NormalizedPosting:
        place = summary.get("location") or detail.get("location") or {}
        remote = bool(place.get("remote"))
        location = Location(
            city=normalize_city(place.get("city")),
            country=country_code(place.get("country")),
            remote=remote,
        )
        sections = ((detail.get("jobAd") or {}).get("sections")) or {}
        description = "\n".join(
            html_to_text((sections.get(key) or {}).get("text")) for key in _SECTIONS
        ).strip()
        company = (summary.get("company") or {}).get("name") or company_from_slug(slug)
        work_mode = WorkMode.REMOTE if remote else WorkMode.HYBRID if place.get("hybrid") else None
        return NormalizedPosting(
            source_job_id=str(summary["id"]),
            title=summary.get("name") or summary.get("title") or "Untitled",
            company=company,
            description=description,
            locations=[location] if (location.city or location.country or remote) else [],
            work_mode=work_mode,
            apply_url=detail.get("postingUrl")
            or detail.get("applyUrl")
            or f"https://jobs.smartrecruiters.com/{slug}/{summary['id']}",
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(summary.get("releasedDate")),
        )
