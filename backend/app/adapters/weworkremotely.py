"""We Work Remotely RSS feed. Titles read "Company: Job Title"."""

import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from app.adapters.base import FetchWindow, NormalizedPosting, WorkMode
from app.adapters.errors import SourceBadResponse
from app.adapters.normalize import extract_contact_email, html_to_text, remote_locations
from app.adapters.registry import register_adapter
from app.adapters.remote_boards import RemoteBoardAdapter

FEED = "https://weworkremotely.com/remote-jobs.rss"


@register_adapter
class WeWorkRemotelyAdapter(RemoteBoardAdapter):
    name = "weworkremotely"
    label = "We Work Remotely"

    async def records(self, window: FetchWindow) -> list[ET.Element]:
        response = await self.http.get(FEED)
        self.check_response(self.label, response)
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise SourceBadResponse(
                "We Work Remotely returned a feed JobWeaver could not read"
            ) from exc
        return root.findall("./channel/item")

    def to_posting(self, item: ET.Element) -> NormalizedPosting | None:
        def text(tag: str) -> str:
            return (item.findtext(tag) or "").strip()

        heading, link = text("title"), text("link")
        # Split on the first ": " only: job titles can contain colons too.
        company, _, title = heading.partition(": ")
        if not (title and company and (text("guid") or link)):
            return None
        try:
            posted = parsedate_to_datetime(text("pubDate")) if text("pubDate") else None
        except (TypeError, ValueError):
            posted = None
        description = html_to_text(text("description"))
        # <country> is more reliable than <region>, which is mostly "Anywhere in the World".
        return NormalizedPosting(
            source_job_id=text("guid") or link,
            title=title,
            company=company,
            description=description,
            locations=remote_locations(text("country") or text("region")),
            work_mode=WorkMode.REMOTE,
            apply_url=link or None,
            contact_email=extract_contact_email(description),
            posted_at=posted,
        )
