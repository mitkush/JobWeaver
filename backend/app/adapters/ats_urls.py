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
_WORKDAY_HOST = re.compile(r"^([\w-]+)\.(wd\d+)\.myworkdayjobs\.com$")
_LOCALE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")


def _workday(host: str, path: str) -> tuple[str, str] | None:
    """("workday", "nvidia/wd5/NVIDIAExternalCareerSite") for
    https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/... (with the
    site in its original case)."""
    match = _WORKDAY_HOST.match(host)
    if not match:
        return None
    parts = [p for p in path.split("/") if p]
    if parts and _LOCALE.match(parts[0]):
        parts = parts[1:]
    if parts and parts[0] == "wday":  # .../wday/cxs/<tenant>/<site>/...
        parts = parts[3:]
    if not parts or parts[0].lower() in ("job", "details", "login"):
        return None
    # The site name is case-sensitive in Workday's endpoints, so it keeps its case.
    return "workday", f"{match.group(1).lower()}/{match.group(2).lower()}/{parts[0]}"


def parse_ats_url(url: str | None) -> tuple[str, str] | None:
    """("greenhouse", "stripe") for https://boards.greenhouse.io/stripe/jobs/123."""
    if not url:
        return None
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.hostname or "").lower().removeprefix("www.")
    target = f"{host}{parsed.path}"
    if host.endswith("greenhouse.io") and "for=" in (parsed.query or ""):
        target = f"{host}/{parsed.query.split('for=')[1].split('&')[0]}"
    if workday := _workday(host, parsed.path):
        return workday
    for ats, pattern in _PATTERNS:
        match = pattern.match(target)
        if match:
            slug = match.group(1).lower()
            return None if slug in _NOT_SLUGS else (ats, slug)
    return None
