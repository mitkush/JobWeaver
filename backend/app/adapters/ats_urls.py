"""Finds company ATS Boards in apply URLs (ADR-0013). Pure URL parsing, no AI."""

import re
from urllib.parse import urlparse

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "greenhouse",
        re.compile(r"^(?:job-)?boards(?:\.eu)?\.greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)"),
    ),
    ("lever", re.compile(r"^jobs(?:\.eu)?\.lever\.co/([\w.-]+)")),
    ("ashby", re.compile(r"^jobs\.ashbyhq\.com/([\w.-]+)")),
    ("smartrecruiters", re.compile(r"^(?:jobs|careers)\.smartrecruiters\.com/([\w-]+)")),
    ("workable", re.compile(r"^apply\.workable\.com/([\w-]+)")),
    ("recruitee", re.compile(r"^([\w-]+)\.recruitee\.com")),
]
_NOT_SLUGS = {"jobs", "job", "embed", "careers", "api", "j", "o"}


def parse_ats_url(url: str | None) -> tuple[str, str] | None:
    """("greenhouse", "stripe") for https://boards.greenhouse.io/stripe/jobs/123."""
    if not url:
        return None
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.hostname or "").lower().removeprefix("www.")
    target = f"{host}{parsed.path}"
    if host.endswith("greenhouse.io") and "for=" in (parsed.query or ""):
        target = f"{host}/{parsed.query.split('for=')[1].split('&')[0]}"
    for ats, pattern in _PATTERNS:
        match = pattern.match(target)
        if match:
            slug = match.group(1).lower()
            return None if slug in _NOT_SLUGS else (ats, slug)
    return None
