"""Free apply-link check before drafting (FR-B10 AC3, ADR-0003).

Apply links come from third-party adverts, so a link is only ever fetched when every
address its host resolves to is on the public internet, and every redirect hop is checked
the same way. Otherwise a crafted link could make the server read its own network (on a
cloud VM, the instance metadata service). Only an explicit "not found" or "gone" counts as
closed; anything else (blocked, slow, odd status) leaves the Job as it is.

Accepted limit: the host is resolved again when connecting, so a DNS server that answers
differently within seconds (DNS rebinding) is not stopped. Only the status of a GET is
learned, and nothing is returned to the User, so such a probe reveals very little."""

import asyncio
import enum
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urljoin, urlparse

import httpx

MAX_REDIRECTS = 5
CLOSED_STATUSES = {404, 410}

Resolve = Callable[[str], Awaitable[list[str]]]


class LinkState(enum.StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"


async def resolve_host(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


async def _public(url: str, resolve: Resolve) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        addresses = await resolve(parsed.hostname)
    except OSError:
        return False
    try:
        return bool(addresses) and all(ipaddress.ip_address(a).is_global for a in addresses)
    except ValueError:
        return False


async def check_apply_link(
    http: httpx.AsyncClient, url: str | None, resolve: Resolve | None = None
) -> LinkState:
    if not url:
        return LinkState.UNKNOWN
    resolve = resolve or resolve_host
    try:
        for _ in range(MAX_REDIRECTS + 1):
            if not await _public(url, resolve):
                return LinkState.UNKNOWN
            # Redirects are followed by hand so that each hop is checked first. The body
            # is never read: the status is all that matters.
            async with http.stream("GET", url, follow_redirects=False) as response:
                if response.is_redirect and response.headers.get("location"):
                    url = urljoin(url, response.headers["location"])
                    continue
                if response.status_code in CLOSED_STATUSES:
                    return LinkState.CLOSED
                return LinkState.OPEN if response.status_code < 400 else LinkState.UNKNOWN
        return LinkState.UNKNOWN
    except httpx.HTTPError:
        return LinkState.UNKNOWN


_http = httpx.AsyncClient(
    timeout=httpx.Timeout(8.0, connect=5.0),
    headers={"User-Agent": "JobWeaver/0.1 (checks whether a job advert is still open)"},
)


def get_link_http() -> httpx.AsyncClient:
    return _http
