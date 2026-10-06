"""Shared shape of the free remote-job boards (COSTS.md 8): fetched once per run, not per
query, and filtered to the window by posting date. Every job on them is remote."""

from typing import Any

from app.adapters.base import (
    FetchResult,
    FetchWindow,
    NormalizedPosting,
    SourceQuery,
    WindowedSourceAdapter,
)


class RemoteBoardAdapter(WindowedSourceAdapter):
    per_query = False
    priority = 8
    min_interval_hours = 6

    async def fetch_window(self, query: SourceQuery | None, window: FetchWindow) -> FetchResult:
        postings = [
            p
            for record in await self.records(window)
            if (p := self.to_posting(record)) is not None
            and (p.posted_at is None or p.posted_at >= window.since)
        ]
        return FetchResult(postings=postings, credits_used=1)

    async def records(self, window: FetchWindow) -> list[Any]:
        raise NotImplementedError

    def to_posting(self, record: Any) -> NormalizedPosting | None:
        raise NotImplementedError
