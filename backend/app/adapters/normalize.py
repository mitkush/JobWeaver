"""Normalisation shared by every Source Adapter (FR-B9)."""

import html
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app.adapters.base import Location, WorkMode

_COMPANY_SUFFIXES = re.compile(
    r"[,.\s]+(inc|llc|l\.l\.c|ltd|limited|pvt|private|plc|gmbh|ag|sa|bv|corp|corporation|co|company)\.?$",
    re.IGNORECASE,
)

_CITY_ALIASES = {
    "bangalore": "Bengaluru",
    "bangalore urban": "Bengaluru",
    "bengaluru urban": "Bengaluru",
    "bombay": "Mumbai",
    "navi mumbai": "Navi Mumbai",
    "gurgaon": "Gurugram",
    "new delhi": "New Delhi",
    "delhi ncr": "Delhi",
    "madras": "Chennai",
    "calcutta": "Kolkata",
    "poona": "Pune",
    "nyc": "New York",
    "new york city": "New York",
    "sf": "San Francisco",
}

_COUNTRIES = {
    "india": "IN", "united states": "US", "united states of america": "US", "usa": "US",
    "us": "US", "united kingdom": "GB", "uk": "GB", "england": "GB", "germany": "DE",
    "canada": "CA", "australia": "AU", "singapore": "SG", "netherlands": "NL",
    "france": "FR", "spain": "ES", "ireland": "IE", "united arab emirates": "AE",
    "uae": "AE", "japan": "JP", "poland": "PL", "portugal": "PT", "sweden": "SE",
    "switzerland": "CH", "israel": "IL", "brazil": "BR", "mexico": "MX",
}  # fmt: skip

_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
    "VA", "WA", "WV", "WI", "WY", "DC",
}  # fmt: skip

# Indian state and union territory codes, and the cities job adverts most often pair with
# them, so "Pune, MH" or "Pune, IN" is India rather than a US state (IN is Indiana).
_INDIAN_STATES = {  # fmt: skip
    "AP",
    "AR",
    "AS",
    "BR",
    "CG",
    "CT",
    "DL",
    "GA",
    "GJ",
    "HP",
    "HR",
    "JH",
    "JK",
    "KA",
    "KL",
    "MH",
    "ML",
    "MN",
    "MP",
    "MZ",
    "NL",
    "OD",
    "OR",
    "PB",
    "PY",
    "RJ",
    "SK",
    "TG",
    "TN",
    "TR",
    "TS",
    "UK",
    "UP",
    "UT",
    "WB",
    "IN",
}
_INDIAN_CITIES = {  # fmt: skip
    "bengaluru",
    "mumbai",
    "navi mumbai",
    "pune",
    "hyderabad",
    "chennai",
    "delhi",
    "new delhi",
    "gurugram",
    "noida",
    "kolkata",
    "ahmedabad",
    "jaipur",
    "kochi",
    "coimbatore",
    "indore",
    "chandigarh",
    "thiruvananthapuram",
    "nagpur",
    "lucknow",
    "bhubaneswar",
    "mysuru",
    "vadodara",
    "visakhapatnam",
    "surat",
    "goa",
    "mohali",
    "faridabad",
    "ghaziabad",
    "thane",
}

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_NO_REPLY = re.compile(r"no-?reply|donotreply|do-not-reply", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")
_BLOCK_TAGS = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr)[^>]*>", re.IGNORECASE)
_RELATIVE = re.compile(r"(\d+)\s*\+?\s*(minute|hour|day|week|month)s?\s+ago", re.IGNORECASE)


def first(record: dict[str, Any], *keys: str) -> Any:
    """For payloads whose field names are not under our control (actors, site fetches):
    the first non-empty value among alternative keys."""
    for key in keys:
        value = record.get(key)
        if value not in (None, "", []):
            return value
    return None


def clean_space(text: str) -> str:
    return " ".join(text.split())


# Generic words after the brand ("Google India", "Razorpay Software") that do not change
# which employer it is. Only stripped while at least _MIN_BRAND characters remain, so
# "Air India" stays itself.
_COMPANY_DESCRIPTORS = re.compile(
    r"\s+(india|technologies|technology|software|solutions|services|systems)$", re.IGNORECASE
)
_MIN_BRAND = 4


def normalize_company(name: str) -> str:
    """Key used to treat "Google India Pvt Ltd" and "Google" as one Company (CONTEXT.md)."""
    value = clean_space(html.unescape(name)).strip(" .,")
    while True:
        stripped = _COMPANY_SUFFIXES.sub("", value).strip(" .,")
        if stripped == value or not stripped:
            break
        value = stripped
    while True:
        stripped = _COMPANY_DESCRIPTORS.sub("", value).strip(" .,")
        if stripped == value or len(stripped) < _MIN_BRAND:
            break
        value = stripped
        while True:
            again = _COMPANY_SUFFIXES.sub("", value).strip(" .,")
            if again == value or not again:
                break
            value = again
    return value.lower()


_COUNTRY_NAMES = {
    "IN": "India", "US": "United States", "GB": "United Kingdom", "DE": "Germany",
    "CA": "Canada", "AU": "Australia", "SG": "Singapore", "NL": "Netherlands", "FR": "France",
    "ES": "Spain", "IE": "Ireland", "AE": "United Arab Emirates", "JP": "Japan", "PL": "Poland",
    "PT": "Portugal", "SE": "Sweden", "CH": "Switzerland", "IL": "Israel", "BR": "Brazil",
    "MX": "Mexico", "NZ": "New Zealand", "MY": "Malaysia", "PH": "Philippines",
    "ID": "Indonesia", "VN": "Vietnam", "SA": "Saudi Arabia", "QA": "Qatar",
}  # fmt: skip


def company_from_slug(slug: str) -> str:
    """For ATS APIs without a company name: "acme-labs" reads as "Acme Labs"."""
    return " ".join(part.capitalize() for part in re.split(r"[-._]", slug) if part)


def country_display(code: str) -> str:
    """Country name for search queries; falls back to the code itself."""
    return _COUNTRY_NAMES.get(code.upper(), code.upper())


def normalize_city(city: str | None) -> str | None:
    if not city:
        return None
    value = clean_space(city).strip(" ,")
    return _CITY_ALIASES.get(value.lower(), value.title() if value.islower() else value) or None


def country_code(value: str | None) -> str | None:
    if not value:
        return None
    raw = clean_space(value).strip(" ,.")
    # Names and common aliases first: "UK" is GB, not a code of its own.
    if raw.lower() in _COUNTRIES:
        return _COUNTRIES[raw.lower()]
    if len(raw) == 2 and raw.isalpha():
        return raw.upper()
    return None


_NEGATED_REMOTE = re.compile(
    r"\b(?:no|not|without)\s+(?:remote(?:\s+work)?|wfh|work from home)\b"
    r"|\b(?:remote(?:\s+work)?|wfh|work from home)\s+"
    r"(?:is\s+)?(?:not available|unavailable|not allowed)\b",
    re.IGNORECASE,
)


def _without_negated_remote(text: str) -> str:
    """Do not treat a rejected remote option as an offered work mode."""
    return _NEGATED_REMOTE.sub("", text)


def parse_location(text: str | None, default_country: str | None = None) -> Location:
    """Parses free text such as "Bangalore, Karnataka, India" or "Remote - US"."""
    if not text:
        return Location(country=default_country)
    raw = re.sub(r"\(\s*\)", "", _without_negated_remote(clean_space(text)))
    remote = bool(re.search(r"\bremote\b|\bwfh\b|work from home|anywhere", raw, re.IGNORECASE))
    cleaned = re.sub(
        r"\(?\b(remote|wfh|hybrid|on-?site|work from home|anywhere)\b\)?",
        "",
        raw,
        flags=re.IGNORECASE,
    )
    parts = [p.strip(" -/") for p in re.split(r"[,;|/]| - ", cleaned) if p.strip(" -/")]
    country = None
    if parts:
        last = parts[-1]
        first = (normalize_city(parts[0]) or "").lower()
        if len(parts) > 1 and last.upper() in _INDIAN_STATES and first in _INDIAN_CITIES:
            country = "IN"
        # "San Francisco, CA" is California, not Canada.
        elif len(parts) > 1 and len(last) == 2 and last.upper() in _US_STATES:
            country = "US"
        else:
            country = country_code(last)
        if country is not None:
            parts = parts[:-1]
    city = normalize_city(parts[0]) if parts else None
    if city and country_code(city):
        country, city = country or country_code(city), None
    return Location(city=city, country=country or default_country, remote=remote)


_ANYWHERE = re.compile(r"^(anywhere|worldwide|global|remote|anywhere in the world)$", re.I)


def remote_locations(value: object) -> list[Location]:
    """Remote-board location text ("USA, Canada", ["India"], "Anywhere") as remote
    Locations: the countries a remote hire may live in, or one with no country."""
    parts = value if isinstance(value, list) else re.split(r"[,;/|]| or ", str(value or ""))
    found: list[Location] = []
    for part in parts:
        text = clean_space(str(part)).strip(" .()")
        if not text or _ANYWHERE.match(text):
            continue
        code = country_code(text) or parse_location(text).country
        if code and all(loc.country != code for loc in found):
            found.append(Location(country=code, remote=True))
    return found or [Location(remote=True)]


def work_mode_from(text: str | None, *, remote_flag: bool | None = None) -> WorkMode | None:
    if remote_flag:
        return WorkMode.REMOTE
    if not text:
        return None
    lowered = _without_negated_remote(text).lower()
    if "hybrid" in lowered:
        return WorkMode.HYBRID
    if "remote" in lowered or "work from home" in lowered or re.search(r"\bwfh\b", lowered):
        return WorkMode.REMOTE
    if re.search(r"on-?site|in-office|in office|work from office", lowered):
        return WorkMode.ONSITE
    return None


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(value)
    if "<" in text:
        text = _BLOCK_TAGS.sub("\n", text)
        text = _TAGS.sub("", text)
        text = html.unescape(text)
    lines = [clean_space(line) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def extract_contact_email(text: str) -> str | None:
    """First hiring-looking address in a description; never a no-reply address."""
    for match in _EMAIL.finditer(text):
        email = match.group(0).rstrip(".").lower()
        if not _NO_REPLY.search(email) and not email.endswith((".png", ".jpg", ".gif")):
            return email
    return None


def parse_datetime(value: object, *, now: datetime | None = None) -> datetime | None:
    """ISO strings, epoch seconds or milliseconds, and "3 days ago" style text."""
    now = now or datetime.now(UTC)
    if value is None or value == "":
        return None
    if isinstance(value, int | float):
        seconds = value / 1000 if value > 1e11 else value
        return datetime.fromtimestamp(seconds, UTC)
    text = str(value).strip()
    if text.isdigit():
        return parse_datetime(int(text), now=now)
    relative = _RELATIVE.search(text)
    if relative:
        amount, unit = int(relative.group(1)), relative.group(2).lower()
        days = {"minute": 1 / 1440, "hour": 1 / 24, "day": 1, "week": 7, "month": 30}[unit]
        return now - timedelta(days=amount * days)
    if re.search(r"\b(just now|today)\b", text, re.IGNORECASE):
        return now
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
