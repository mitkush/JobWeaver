"""Recruitee public careers-site API, snapshot mode (ADR-0003, ADR-0013)."""

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
)
from app.adapters.registry import register_adapter


@register_adapter
class RecruiteeAdapter(SnapshotSourceAdapter):
    name = "recruitee"
    label = "Recruitee"
    priority = 3
    ats = "recruitee"

    async def fetch_board(self, slug: str) -> FetchResult:
        response = await self.http.get(f"https://{slug}.recruitee.com/api/offers/")
        if response.status_code == 404:
            raise BoardNotFound(f"Recruitee has no careers site named {slug!r}")
        self.check_response(self.label, response)
        body = response.json()
        offers = body.get("offers") if isinstance(body, dict) else None
        if not isinstance(offers, list):
            raise SourceBadResponse("Recruitee returned an unexpected response")
        return FetchResult(
            postings=[
                self._to_posting(offer, slug)
                for offer in offers
                if offer.get("id") and offer.get("status", "published") == "published"
            ]
        )

    @staticmethod
    def _to_posting(offer: dict[str, Any], slug: str) -> NormalizedPosting:
        remote = bool(offer.get("remote"))
        places = offer.get("locations") or [offer]
        locations = [
            Location(
                city=normalize_city(place.get("city")),
                country=country_code(place.get("country_code") or place.get("country")),
                remote=remote,
            )
            for place in places
            if isinstance(place, dict) and (place.get("city") or place.get("country_code"))
        ]
        if remote and not locations:
            locations = [Location(remote=True)]
        work_mode = (
            WorkMode.REMOTE
            if remote
            else WorkMode.HYBRID
            if offer.get("hybrid")
            else WorkMode.ONSITE
            if offer.get("on_site")
            else None
        )
        description = "\n".join(
            part
            for part in (
                html_to_text(offer.get("description")),
                html_to_text(offer.get("requirements")),
            )
            if part
        )
        return NormalizedPosting(
            source_job_id=str(offer["id"]),
            title=offer.get("title") or "Untitled",
            company=offer.get("company_name") or company_from_slug(slug),
            description=description,
            locations=locations,
            work_mode=work_mode,
            apply_url=offer.get("careers_url") or offer.get("careers_apply_url"),
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(
                str(offer.get("published_at") or offer.get("created_at") or "").replace(
                    " UTC", "+00:00"
                )
            ),
        )
