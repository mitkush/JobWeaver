"""Apply-link check: only public addresses, every redirect hop checked (FR-B10 AC3)."""

import httpx

from app.adapters.links import LinkState, check_apply_link


def http(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def public(_: str) -> list[str]:
    return ["93.184.216.34"]


async def test_not_found_and_gone_mean_closed_anything_else_does_not():
    for status, state in ((404, LinkState.CLOSED), (410, LinkState.CLOSED),
                          (200, LinkState.OPEN), (403, LinkState.UNKNOWN),
                          (500, LinkState.UNKNOWN), (999, LinkState.UNKNOWN)):  # fmt: skip
        async with http(lambda r, s=status: httpx.Response(s)) as client:
            assert await check_apply_link(client, "https://jobs.acme.dev/1", public) == state


async def test_private_and_metadata_addresses_are_never_fetched():
    called = []

    def handler(request):
        called.append(request)
        return httpx.Response(404)

    for address in ("169.254.169.254", "10.0.0.5", "127.0.0.1", "::1", "192.168.1.1"):

        async def resolve(_: str, a=address) -> list[str]:
            return [a]

        async with http(handler) as client:
            assert await check_apply_link(client, "https://evil.example/x", resolve) == (
                LinkState.UNKNOWN
            )
    assert called == []
    async with http(handler) as client:
        assert await check_apply_link(client, "file:///etc/passwd", public) == LinkState.UNKNOWN
    assert called == []


async def test_a_redirect_to_a_private_address_is_not_followed():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.host == "jobs.acme.dev":
            return httpx.Response(302, headers={"location": "http://internal.acme/admin"})
        return httpx.Response(404)

    async def resolve(host: str) -> list[str]:
        return ["10.1.2.3"] if host == "internal.acme" else ["93.184.216.34"]

    async with http(handler) as client:
        assert await check_apply_link(client, "https://jobs.acme.dev/1", resolve) == (
            LinkState.UNKNOWN
        )
    assert seen == ["https://jobs.acme.dev/1"]


async def test_redirects_to_a_closed_page_are_followed_and_network_errors_are_unknown():
    def handler(request):
        if request.url.path == "/1":
            return httpx.Response(301, headers={"location": "/closed"})
        return httpx.Response(410)

    async with http(handler) as client:
        assert await check_apply_link(client, "https://jobs.acme.dev/1", public) == (
            LinkState.CLOSED
        )

    def down(request):
        raise httpx.ConnectTimeout("slow", request=request)

    async with http(down) as client:
        assert await check_apply_link(client, "https://jobs.acme.dev/1", public) == (
            LinkState.UNKNOWN
        )
    assert await check_apply_link(httpx.AsyncClient(), None, public) == LinkState.UNKNOWN
