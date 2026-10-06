"""Hacker News "Ask HN: Who is hiring?" threads through the Algolia HN API.

Each top-level comment is one company's free-text advert. The adapter only collects the
comments posted in the window; AI extraction turns them into Postings later and queues
them while AI is unavailable (FR-B8)."""

import html
import re
from datetime import UTC, datetime
from typing import Any

from app.adapters.base import (
    FetchResult,
    FetchWindow,
    PendingAdvert,
    SourceQuery,
    WindowedSourceAdapter,
)
from app.adapters.errors import SourceBadResponse
from app.adapters.normalize import html_to_text
from app.adapters.registry import register_adapter

API = "https://hn.algolia.com/api/v1"
THREAD_TITLE = "ask hn: who is hiring?"
# A thread stays active for about a month; the previous one still gets comments early on.
THREADS = 2
# HN shortens long link text with "...", so the full URL is taken from the href.
_LINK = re.compile(r'<a\s[^>]*href="([^"]+)"[^>]*>.*?</a>', re.IGNORECASE | re.DOTALL)


def comment_text(raw: str) -> str:
    return html_to_text(_LINK.sub(lambda m: html.unescape(m.group(1)), raw))


@register_adapter
class HackerNewsAdapter(WindowedSourceAdapter):
    name = "hackernews"
    label = "Hacker News (Who is hiring)"
    priority = 9
    per_query = False
    min_interval_hours = 6

    async def fetch_window(self, query: SourceQuery | None, window: FetchWindow) -> FetchResult:
        response = await self.http.get(
            f"{API}/search_by_date",
            params={"tags": "story,author_whoishiring", "hitsPerPage": 10},
        )
        self.check_response(self.label, response)
        hits = response.json().get("hits")
        if not isinstance(hits, list):
            raise SourceBadResponse("Hacker News search returned an unexpected response")
        # The same account also posts "Who wants to be hired?" and "Freelancer?" threads.
        threads = [
            h
            for h in hits
            if isinstance(h, dict) and str(h.get("title", "")).lower().startswith(THREAD_TITLE)
        ][:THREADS]
        adverts: list[PendingAdvert] = []
        for thread in threads:
            adverts += await self._comments(str(thread["objectID"]), window)
        return FetchResult(postings=[], pending=adverts, credits_used=1 + len(threads))

    async def _comments(self, thread_id: str, window: FetchWindow) -> list[PendingAdvert]:
        response = await self.http.get(f"{API}/items/{thread_id}")
        self.check_response(self.label, response)
        children = response.json().get("children")
        if not isinstance(children, list):
            raise SourceBadResponse("Hacker News returned an unexpected thread")
        adverts = []
        for comment in children:
            posted = _posted(comment)
            # Deleted comments have no text; replies are nested, so only top level counts.
            if not comment.get("text") or posted is None or posted < window.since:
                continue
            adverts.append(
                PendingAdvert(
                    ref=str(comment["id"]),
                    text=comment_text(comment["text"]),
                    url=f"https://news.ycombinator.com/item?id={comment['id']}",
                    posted_at=posted,
                )
            )
        return adverts


def _posted(comment: dict[str, Any]) -> datetime | None:
    stamp = comment.get("created_at_i")
    if isinstance(stamp, int):
        return datetime.fromtimestamp(stamp, UTC)
    return None
