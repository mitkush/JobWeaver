"""Naukri via an Apify actor (COSTS.md 2). India only; shares the Apify allowance.

The actor's input and output field names come from other projects' code, not from a live
run: alternatives are accepted, and a record without id, title and company is skipped."""

from typing import Any

from app.adapters.apify import ApifyAdapter
from app.adapters.base import FetchWindow, NormalizedPosting, SourceQuery
from app.adapters.normalize import (
    extract_contact_email,
    first,
    html_to_text,
    parse_datetime,
    parse_location,
    work_mode_from,
)
from app.adapters.registry import register_adapter


def freshness_for(window: FetchWindow) -> str:
    """Smallest Naukri "freshness" (days) that reaches back to the window start."""
    for days in (1, 3, 7, 15, 30):
        if window.hours <= days * 24 + 2:
            return str(days)
    return "all"


@register_adapter
class NaukriApifyAdapter(ApifyAdapter):
    name = "naukri"
    label = "Naukri (Apify)"
    priority = 2

    def actor(self) -> str:
        return self.settings.apify_naukri_actor

    def actor_input(self, query: SourceQuery, window: FetchWindow) -> dict[str, Any] | None:
        loc = query.location
        if loc and loc.country and loc.country != "IN":
            return None  # Naukri lists Indian jobs; other countries would only cost money
        payload: dict[str, Any] = {
            "keyword": query.keywords,
            "maxJobs": self.settings.apify_naukri_max_jobs,
            "freshness": freshness_for(window),
            "sortBy": "date",
            "fetchDetails": self.settings.apify_naukri_fetch_details,
        }
        if loc and loc.remote:
            payload["workMode"] = ["remote"]
        elif loc and loc.city:
            ids = {
                name.lower(): value for name, value in self.settings.apify_naukri_city_ids.items()
            }
            city_id = ids.get(loc.city.lower())
            if city_id:
                payload["cities"] = [city_id]
            else:
                payload["keyword"] = f"{query.keywords} {loc.city}"
        return payload

    def to_posting(self, record: dict[str, Any]) -> NormalizedPosting | None:
        job_id = first(record, "jobId", "job_id", "id")
        title = first(record, "title", "jobTitle")
        company = first(record, "companyName", "company")
        if not (job_id and title and company):
            return None
        location_text = first(record, "location", "jobLocation")
        for item in record.get("placeholders") or []:
            if isinstance(item, dict) and item.get("type") == "location" and not location_text:
                location_text = item.get("label")
        locations = [
            parse_location(part, default_country="IN")
            for part in str(location_text or "").split(",")
            if part.strip()
        ]
        description = html_to_text(first(record, "jobDescription", "description") or "")
        url = first(record, "jdURL", "jobUrl", "url")
        if url and str(url).startswith("/"):
            url = f"https://www.naukri.com{url}"
        return NormalizedPosting(
            source_job_id=str(job_id),
            title=str(title),
            company=str(company),
            description=description,
            locations=locations,
            work_mode=work_mode_from(
                f"{first(record, 'workMode', 'wfhType') or ''} {location_text}"
            ),
            apply_url=url,
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(
                first(record, "createdDate", "postedDate", "footerPlaceholderLabel")
            ),
        )
