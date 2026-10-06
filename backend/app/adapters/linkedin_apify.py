"""LinkedIn via an Apify actor: standby for Bright Data (ADR-0016).

Runs only while LinkedIn (Bright Data) is Degraded or disabled, continuing from the same
query watermarks, and shares the Apify allowance with Naukri. Like Bright Data it fetches
every result of a search (ADR-0009); only the budget can stop a run early. The actor's
field names come from other projects' code, not a live run, so alternatives are accepted."""

import math
from typing import Any
from urllib.parse import urlencode

from app.adapters.apify import ApifyAdapter
from app.adapters.base import FetchWindow, NormalizedPosting, SourceQuery
from app.adapters.normalize import (
    country_display,
    extract_contact_email,
    first,
    html_to_text,
    parse_datetime,
    parse_location,
    work_mode_from,
)
from app.adapters.registry import register_adapter


def search_url(query: SourceQuery, window: FetchWindow) -> str:
    """A LinkedIn jobs search URL; f_TPR takes any number of seconds, so the window is
    exact rather than rounded up to a day or a week."""
    loc = query.location
    place = ""
    if loc and (loc.city or loc.country):
        place = ", ".join(
            x for x in (loc.city, country_display(loc.country) if loc.country else None) if x
        )
    params = {
        "keywords": query.keywords,
        "location": place or "Worldwide",
        "f_TPR": f"r{math.ceil(window.hours * 3600)}",
        "sortBy": "DD",
    }
    if loc and loc.remote:
        params["f_WT"] = "2"
    return f"https://www.linkedin.com/jobs/search/?{urlencode(params)}"


@register_adapter
class LinkedInApifyAdapter(ApifyAdapter):
    name = "linkedin-apify"
    label = "LinkedIn (Apify)"
    priority = 1
    standby_for = "linkedin"

    def actor(self) -> str:
        return self.settings.apify_linkedin_actor

    def actor_input(self, query: SourceQuery, window: FetchWindow) -> dict[str, Any]:
        return {
            "urls": [search_url(query, window)],
            "count": self.settings.apify_linkedin_max_items,
            "scrapeCompany": False,
        }

    def to_posting(self, record: dict[str, Any]) -> NormalizedPosting | None:
        job_id = first(record, "id", "jobId", "job_id")
        title = first(record, "title", "jobTitle")
        company = first(record, "companyName", "company")
        if not (job_id and title and company):
            return None
        description = html_to_text(
            first(record, "descriptionText", "descriptionHtml", "description") or ""
        )
        location_text = first(record, "location", "jobLocation")
        work_text = " ".join(
            str(v) for v in (first(record, "workplaceTypes", "workType"), location_text) if v
        )
        return NormalizedPosting(
            source_job_id=str(job_id),
            title=str(title),
            company=str(company),
            description=description,
            locations=[parse_location(location_text)] if location_text else [],
            work_mode=work_mode_from(work_text),
            apply_url=first(record, "applyUrl", "link", "jobUrl"),
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(first(record, "postedAt", "publishedAt", "postedTime")),
        )
