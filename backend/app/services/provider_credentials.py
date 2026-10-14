"""Ordered primary and backup accounts. Only fingerprints are persisted."""

import hashlib
from dataclasses import dataclass
from datetime import datetime

from app.adapters.base import SourceAdapter
from app.core.config import Settings


@dataclass(frozen=True)
class Credential:
    label: str
    settings: Settings
    fingerprint: str
    primary: bool


def active_primary_pause(
    adapter: type[SourceAdapter], settings: Settings, now: datetime
) -> datetime | None:
    setting = adapter.primary_credential_pause_setting
    paused_until = getattr(settings, setting) if setting else None
    return paused_until if paused_until is not None and now < paused_until else None


def credentials(adapter: type[SourceAdapter], settings: Settings) -> list[Credential]:
    if adapter.credential_settings is None:
        return []
    key, extra_keys = adapter.credential_settings
    backups = [token.strip() for token in getattr(settings, extra_keys).split(",") if token.strip()]
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
