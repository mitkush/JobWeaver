"""Server-Timing: how long an API request took, and its named phases, shown in the
browser's network panel. Durations only; never query text or data."""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_phases: ContextVar[list[tuple[str, float]] | None] = ContextVar("server_timing", default=None)


@contextmanager
def phase(name: str) -> Iterator[None]:
    """Times a block of the current request; outside a request it only runs the block."""
    started = time.perf_counter()
    try:
        yield
    finally:
        spans = _phases.get()
        if spans is not None:
            spans.append((name, (time.perf_counter() - started) * 1000))


class ServerTimingMiddleware:
    """Adds `Server-Timing: <phase>;dur=…, app;dur=…` to /api/ responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return
        spans: list[tuple[str, float]] = []
        token = _phases.set(spans)
        started = time.perf_counter()

        async def timed_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                total = (time.perf_counter() - started) * 1000
                entries = [f"{name};dur={ms:.1f}" for name, ms in spans]
                entries.append(f"app;dur={total:.1f}")
                MutableHeaders(scope=message).append("Server-Timing", ", ".join(entries))
            await send(message)

        try:
            await self.app(scope, receive, timed_send)
        finally:
            _phases.reset(token)
