"""Per-task progress callbacks without importing services into the gateway."""

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_callback: ContextVar[Callable[[str], Awaitable[None]] | None] = ContextVar(
    "draft_provider_progress", default=None
)


@contextmanager
def draft_progress(callback: Callable[[str], Awaitable[None]]) -> Iterator[None]:
    token = _callback.set(callback)
    try:
        yield
    finally:
        _callback.reset(token)


async def trying(provider: str) -> None:
    callback = _callback.get()
    if callback is not None:
        await callback(provider)
