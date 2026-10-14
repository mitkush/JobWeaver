"""Explicit publisher exclusions shared by ingestion and the Feed.

These are product exclusions, not a claim that every listing is fraudulent.
Match company identity, never arbitrary words in a job description.
"""

from app.adapters.normalize import normalize_company

BLOCKED_COMPANIES = frozenset({"vmysmartpros", "remotepromsp"})


def blocked_company(name: str) -> bool:
    return normalize_company(name) in BLOCKED_COMPANIES
