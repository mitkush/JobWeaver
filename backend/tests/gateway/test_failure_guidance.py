import pytest

from app.gateway.live import TOO_LARGE, unavailable_message


@pytest.mark.parametrize(
    ("reasons", "expected"),
    [
        (["not configured"], "No AI provider is configured"),
        (["not configured", "timed out"], "did not finish in time"),
        (["daily quota reached", "rate-limited or quota exhausted"], "usage or rate limit"),
        ([TOO_LARGE, "not configured"], "request is too large"),
        (["timed out", "daily quota reached"], "Some may be busy, limited or unavailable"),
        (["secret from provider"], "Some may be busy, limited or unavailable"),
    ],
)
def test_actionable_guidance_without_exposing_diagnostics(reasons, expected):
    message = unavailable_message(reasons)
    assert expected in message
    assert "secret" not in message
