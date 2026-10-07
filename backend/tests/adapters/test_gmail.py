import httpx
import pytest

from app.adapters.gmail import DRAFTS_URL, GmailClient
from app.core.errors import ExternalServiceError, GoogleFlowError


async def test_gmail_only_creates_a_draft_with_raw_mime():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "draft-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        assert await GmailClient(http).create_draft("access-token", "mime") == "draft-1"
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == DRAFTS_URL
    assert request.method == "POST"
    assert request.headers["Authorization"] == "Bearer access-token"
    assert request.read() == b'{"message":{"raw":"mime"}}'


@pytest.mark.parametrize(
    "response,error",
    [
        (httpx.Response(401), GoogleFlowError),
        (httpx.Response(403), ExternalServiceError),
        (httpx.Response(200, text="invalid json"), ExternalServiceError),
        (httpx.Response(200, json={}), ExternalServiceError),
        (httpx.Response(200, json={"id": None}), ExternalServiceError),
    ],
)
async def test_gmail_failure_is_typed(response, error):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response)) as http:
        with pytest.raises(error):
            await GmailClient(http).create_draft("token", "mime")


async def test_gmail_network_failure_is_typed():
    def handler(request):
        raise httpx.ConnectError("offline")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ExternalServiceError):
            await GmailClient(http).create_draft("token", "mime")


def test_compose_link_encodes_the_sender_like_the_drafts_link():
    from app.adapters.gmail import compose_url

    url = compose_url("a+b/c@example.com", "jobs@acme.com", "Hi", "Body")
    assert url.startswith("https://mail.google.com/mail/u/a%2Bb%2Fc@example.com/?")
