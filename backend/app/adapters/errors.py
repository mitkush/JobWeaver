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


class SourceUnavailable(SourceError):
    pass


class SourceBadResponse(SourceError):
    pass


class BoardNotFound(SourceError):
    """The company no longer has a board at this slug; the board is disabled."""
