"""Owner-only subscription route; consent is an explicit private operator record."""

import uuid
from datetime import UTC, datetime

from app.core.config import get_settings
from app.gateway.routing import Route

NOTICE_VERSION = "1"
CLAUDE_ROUTE = Route("claude-code", "sonnet", timeout_seconds=60)


def allowed(user_id: uuid.UUID | None) -> bool:
    settings = get_settings()
    accepted = settings.claude_code_consent_accepted_at
    return bool(
        settings.claude_code_enabled
        and user_id is not None
        and user_id == settings.claude_code_owner_id
        and len(settings.claude_code_worker_key) >= 32
        and settings.claude_code_consent_version == NOTICE_VERSION
        and accepted is not None
        and accepted.tzinfo is not None
        and accepted <= datetime.now(UTC)
    )
