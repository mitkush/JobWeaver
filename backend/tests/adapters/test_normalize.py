from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.base import WorkMode
from app.adapters.normalize import (
    extract_contact_email,
    html_to_text,
    normalize_city,
    normalize_company,
    parse_datetime,
    parse_location,
    work_mode_from,
)

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ("Google LLC", "google"),
        ("Google", "google"),
        ("Google India Pvt. Ltd.", "google"),
        ("Shriffle Technologies Private Limited", "shriffle"),
        ("Razorpay Software Pvt Ltd", "razorpay"),
        ("Razorpay", "razorpay"),
        ("Air India Limited", "air india"),
        ("Tata Consultancy Services", "tata consultancy"),
        ("ACME, Inc.", "acme"),
        ("AT&amp;T", "at&t"),
    ],
)
def test_company_keys(raw, key):
    assert normalize_company(raw) == key


@pytest.mark.parametrize(
    ("raw", "city"),
    [("Bangalore", "Bengaluru"), ("Bangalore Urban", "Bengaluru"), ("gurgaon", "Gurugram"),
     ("pune", "Pune"), ("", None),
     # LinkedIn's administrative names for a city.
     ("Pune Division", "Pune"), ("Pune City", "Pune"), ("Nashik Division", "Nashik"),
     ("Greater Chennai Area", "Chennai"), ("Mumbai Metropolitan Region", "Mumbai"),
     ("Gurgaon District", "Gurugram"),
     # Real cities whose name ends in City or Area stay as they are.
     ("Mexico City", "Mexico City"), ("Kuwait City", "Kuwait City"),
     ("San Francisco Bay Area", "San Francisco Bay Area"), ("New York City", "New York")],
)  # fmt: skip
def test_city_aliases(raw, city):
    assert normalize_city(raw) == city


@pytest.mark.parametrize(
    ("raw", "city", "country", "remote"),
    [
        ("Bangalore, Karnataka, India", "Bengaluru", "IN", False),
        ("Bengaluru Urban, Karnataka, India", "Bengaluru", "IN", False),
        ("Pune Division, Maharashtra, India", "Pune", "IN", False),
        ("San Francisco, CA", "San Francisco", "US", False),
        ("Remote - India", None, "IN", True),
        ("Bengaluru (WFH), India", "Bengaluru", "IN", True),
        ("WFH - India", None, "IN", True),
        ("Mumbai, India (No WFH)", "Mumbai", "IN", False),
        ("Mumbai, India (WFH not available)", "Mumbai", "IN", False),
        ("London, United Kingdom (Hybrid)", "London", "GB", False),
        ("India", None, "IN", False),
        ("Anywhere", None, None, True),
    ],
)
def test_parse_location(raw, city, country, remote):
    location = parse_location(raw)
    assert (location.city, location.country, location.remote) == (city, country, remote)


def test_work_mode():
    assert work_mode_from("Hybrid - 3 days in office") == WorkMode.HYBRID
    assert work_mode_from("Fully remote") == WorkMode.REMOTE
    assert work_mode_from("WFH - India") == WorkMode.REMOTE
    assert work_mode_from("Hybrid with WFH days") == WorkMode.HYBRID
    assert work_mode_from("Work from office only. No WFH.") == WorkMode.ONSITE
    assert work_mode_from("WFH not available") is None
    assert work_mode_from("No remote work") is None
    assert work_mode_from("Remote work is not available") is None
    assert work_mode_from("No WFH, but remote roles are available") == WorkMode.REMOTE
    assert work_mode_from("On-site") == WorkMode.ONSITE
    assert work_mode_from(None, remote_flag=True) == WorkMode.REMOTE
    assert work_mode_from("Full-time") is None
    assert work_mode_from("AWFH") is None


def test_html_to_text_keeps_structure():
    raw = (
        "&lt;p&gt;We build &amp;amp; ship.&lt;/p&gt;"
        "&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;/ul&gt;"
    )
    assert html_to_text(raw) == "We build & ship.\nPython"


def test_contact_email_skips_no_reply_addresses():
    text = "Questions: noreply@acme.com. Send your CV to Jobs@Acme.com."
    assert extract_contact_email(text) == "jobs@acme.com"
    assert extract_contact_email("Apply on our site.") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-10-04T08:00:00Z", datetime(2026, 10, 4, 8, tzinfo=UTC)),
        ("2026-10-04T08:00:00", datetime(2026, 10, 4, 8, tzinfo=UTC)),
        (1791100800000, datetime.fromtimestamp(1791100800, UTC)),
        ("3 days ago", NOW - timedelta(days=3)),
        ("30+ days ago", NOW - timedelta(days=30)),
        ("Just now", NOW),
        ("not a date", None),
        (None, None),
    ],
)
def test_parse_datetime(raw, expected):
    assert parse_datetime(raw, now=NOW) == expected


def test_indian_state_codes_are_india_not_us_states():
    assert parse_location("Pune, IN").country == "IN"  # not Indiana
    assert parse_location("Chennai, TN").country == "IN"  # not Tennessee
    assert parse_location("Mumbai, MH").country == "IN"
    assert parse_location("Indianapolis, IN").country == "US"
    assert parse_location("Austin, TX").country == "US"
