"""User-reviewed public adverts pushed by the extension (ADR-0017), never fetched."""

from app.adapters.base import FetchResult, FetchWindow, SourceQuery, WindowedSourceAdapter
from app.adapters.registry import register_adapter


@register_adapter
class CapturedAdapter(WindowedSourceAdapter):
    name = "captured"
    label = "Careers page (captured)"
    priority = 99
    default_enabled = False
    push_only = True
    disabled_reason = "Added on demand from a careers page through the browser extension."
    per_query = False

    async def fetch_window(self, query: SourceQuery | None, window: FetchWindow) -> FetchResult:
        return FetchResult(postings=[])
