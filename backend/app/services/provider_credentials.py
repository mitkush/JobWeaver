"""Ordered primary and backup accounts. Only fingerprints are persisted."""

import hashlib
from dataclasses import dataclass

from app.adapters.base import SourceAdapter
from app.core.config import Settings


@dataclass(frozen=True)
class Credential:
    label: str
    settings: Settings
    fingerprint: str
    primary: bool


def credentials(adapter: type[SourceAdapter], settings: Settings) -> list[Credential]:
    if adapter.budget_pool == "apify":
        key, backups = (
            "apify_token",
            [key.strip() for key in settings.apify_tokens.split(",") if key.strip()],
        )
    elif adapter.name == "linkedin":
        key, backups = (
            "brightdata_api_key",
            [key.strip() for key in settings.brightdata_api_keys.split(",") if key.strip()],
        )
    else:
        return []
    options = [("Primary account", getattr(settings, key), True)]
    options += [(f"Backup account {i}", token, False) for i, token in enumerate(backups, 1)]
    result = []
    seen = set()
    for label, token, primary in options:
        token = token.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        result.append(
            Credential(
                label,
                settings.model_copy(update={key: token}),
                hashlib.sha256(token.encode()).hexdigest(),
                primary,
            )
        )
    return result
