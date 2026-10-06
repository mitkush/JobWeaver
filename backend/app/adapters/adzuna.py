"""Adzuna search API (COSTS.md: 25/minute, 250/day, 2,500/month). Adzuna serves a fixed
list of countries, so global and other-country searches are skipped at no cost. Its
descriptions are snippets of about 500 characters; the full advert is behind the link."""

import math
from typing import Any

from app.adapters.base import (
    FetchResult,
    FetchWindow,
    Location,
    NormalizedPosting,
    SourceQuery,
    WindowedSourceAdapter,
)
from app.adapters.errors import SourceBadResponse, SourceError
from app.adapters.normalize import (
    country_code,
    extract_contact_email,
    html_to_text,
    normalize_city,
    parse_datetime,
    work_mode_from,
)
from app.adapters.registry import register_adapter

API = "https://api.adzuna.com/v1/api/jobs"
PAGE = 50
COUNTRIES = {"at", "au", "be", "br", "ca", "ch", "de", "es", "fr", "gb", "in", "it", "mx",
             "nl", "nz", "pl", "sg", "us", "za"}  # fmt: skip


@register_adapter
class AdzunaAdapter(WindowedSourceAdapter):
    name = "adzuna"
    label = "Adzuna"
    priority = 7
    monthly_allowance = 2500
    allowance_unit = "requests"

    def is_configured(self) -> bool:
        return bool(self.settings.adzuna_app_id and self.settings.adzuna_app_key)

    async def fetch_window(self, query: SourceQuery | None, window: FetchWindow) -> FetchResult:
        self.ensure_configured()
        assert query is not None
        loc = query.location
        country = (loc.country or "").lower() if loc else ""
        if country not in COUNTRIES:
            return FetchResult(postings=[])
        params: dict[str, Any] = {
            "app_id": self.settings.adzuna_app_id,
            "app_key": self.settings.adzuna_app_key,
            # Adzuna has no remote filter; the word has to appear in the advert.
            "what": f"{query.keywords} remote" if loc and loc.remote else query.keywords,
            "max_days_old": max(math.ceil(window.hours / 24), 1),
            "results_per_page": PAGE,
            "sort_by": "date",
            "content-type": "application/json",
        }
        if loc and loc.city and not loc.remote:
            params["where"] = loc.city
        postings: list[NormalizedPosting] = []
        spent = 0
        for page in range(1, max(self.settings.adzuna_pages_per_query, 1) + 1):
            if self.allowance_left is not None and spent >= self.allowance_left:
                break  # each page is a paid request; stop at the monthly allowance
            response = await self.http.get(f"{API}/{country}/search/{page}", params=params)
            try:
                self.check_response(self.label, response)
                body = response.json()
            except SourceError as exc:
                exc.credits_used = spent + (0 if response.status_code == 429 else 1)
                raise
            except ValueError as exc:
                raise SourceBadResponse(
                    "Adzuna returned data JobWeaver could not read", credits_used=spent + 1
                ) from exc
            spent += 1
            results = body.get("results") if isinstance(body, dict) else None
            if not isinstance(results, list):
                raise SourceBadResponse(
                    "Adzuna returned an unexpected response", credits_used=spent
                )
            postings += [p for r in results if (p := self._to_posting(r, country)) is not None]
            if len(results) < PAGE:
                break
        return FetchResult(postings=postings, credits_used=spent)

    @staticmethod
    def _to_posting(job: dict[str, Any], country: str) -> NormalizedPosting | None:
        company = (job.get("company") or {}).get("display_name")
        if not (job.get("id") and job.get("title") and company):
            return None
        area = (job.get("location") or {}).get("area") or []
        city = normalize_city(area[-1]) if len(area) >= 3 else None
        description = html_to_text(job.get("description"))
        title = html_to_text(job["title"])
        return NormalizedPosting(
            source_job_id=str(job["id"]),
            title=title,
            company=html_to_text(company),
            description=description,
            locations=[Location(city=city, country=country_code(country))],
            work_mode=work_mode_from(f"{title} {description[:300]}"),
            apply_url=job.get("redirect_url"),
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(job.get("created")),
        )
