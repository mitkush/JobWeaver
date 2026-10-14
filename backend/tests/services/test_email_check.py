from types import SimpleNamespace
from unittest.mock import AsyncMock

import dns.exception
import dns.resolver
import pytest

from app.services.email_check import check_recipient


@pytest.mark.parametrize(
    ("answer", "valid", "warning"),
    [
        ([SimpleNamespace(exchange="mx.example.com.")], True, ""),
        ([SimpleNamespace(exchange=".")], False, "null MX"),
        (dns.resolver.NoAnswer(), False, "no MX"),
        (dns.resolver.NXDOMAIN(), False, "no MX"),
        (dns.exception.Timeout(), False, "Could not verify"),
    ],
)
async def test_dns_outcomes_are_explicit(monkeypatch, answer, valid, warning):
    resolver = AsyncMock()
    if isinstance(answer, Exception):
        resolver.side_effect = answer
    else:
        resolver.return_value = answer
    monkeypatch.setattr("dns.asyncresolver.resolve", resolver)
    result = await check_recipient("jobs@example.com")
    assert result.valid is valid
    if warning:
        assert warning in result.warnings[0]


async def test_invalid_address_does_not_trigger_dns(monkeypatch):
    resolver = AsyncMock()
    monkeypatch.setattr("dns.asyncresolver.resolve", resolver)
    result = await check_recipient("not an email")
    assert result.valid is False
    resolver.assert_not_called()


async def test_no_reply_is_warned_even_with_mx(monkeypatch):
    monkeypatch.setattr(
        "dns.asyncresolver.resolve",
        AsyncMock(return_value=[SimpleNamespace(exchange="mx.example.com.")]),
    )
    result = await check_recipient("no-reply@example.com")
    assert not result.valid and "no-reply" in result.warnings[0]


@pytest.mark.parametrize(
    ("recipient", "warned"),
    [
        ("accommodations@scribd.com", "accommodation address"),
        ("privacy@acme.com", "privacy address"),
        ("careers@acme.com", ""),
        ("sapna.hr@acme.com", ""),
    ],
)
async def test_addresses_meant_for_something_else_are_flagged(monkeypatch, recipient, warned):
    """An advert's accommodations or privacy address is not where applications go."""
    resolver = AsyncMock(return_value=[SimpleNamespace(exchange="mx.example.com.")])
    monkeypatch.setattr("dns.asyncresolver.resolve", resolver)
    result = await check_recipient(recipient)
    assert result.valid is not bool(warned)
    if warned:
        assert warned in result.warnings[0]
