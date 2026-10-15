"""Failures a Source can report. Any of them marks only that Source Degraded (ADR-0003)."""


class SourceError(Exception):
    def __init__(self, message: str, *, credits_used: int = 0) -> None:
        super().__init__(message)
        self.message = message
        # What the failed call still cost, so the Credit Budget never reads low (FR-B5).
        self.credits_used = credits_used


class SourceNotConfigured(SourceError):
    pass


class SourceRateLimited(SourceError):
    pass


class SourceQuotaExhausted(SourceError):
    pass


class SourceQuotaRejected(SourceQuotaExhausted):
    """Provider rejected a start request for credits or rate limits; no search started.

    Only this error permits retrying a search with another account.
    """


class SourceUnavailable(SourceError):
    pass


class SourceBadResponse(SourceError):
    pass


class BoardNotFound(SourceError):
    """The company no longer has a board at this slug; the board is disabled."""


def quota_rejected(response) -> bool:
    """Explicit spending errors only, never general 429 rate limits or HTTP timeouts."""
    if response.status_code == 402:
        return True
    if response.status_code not in (400, 403, 429):
        return False
    body = response.text.lower()
    return any(
        term in body
        for term in (
            "insufficient credits",
            "not enough credits",
            "credit limit exceeded",
            "free credits exhausted",
            "monthly usage limit exceeded",
            "insufficient balance",
        )
    )
