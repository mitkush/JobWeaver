"""Typed errors. Services raise these; the API layer maps them to HTTP responses."""


class JobWeaverError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(JobWeaverError):
    status_code = 404
    code = "not_found"


class AuthError(JobWeaverError):
    status_code = 401
    code = "unauthenticated"


class GoogleFlowError(AuthError):
    """A Google sign-in or Gmail step failed; `reason` is shown to the user in the app."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class ForbiddenError(JobWeaverError):
    status_code = 403
    code = "forbidden"


class ValidationFailedError(JobWeaverError):
    status_code = 422
    code = "validation_failed"


class PreconditionError(JobWeaverError):
    """The user must finish an earlier step first (e.g. accept the AI notice)."""

    status_code = 409
    code = "precondition_failed"


class ConflictError(JobWeaverError):
    """The action no longer applies (e.g. a Possible Duplicate someone already decided)."""

    status_code = 409
    code = "conflict"


class GatewayError(JobWeaverError):
    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message

    status_code = 503
    code = "ai_unavailable"


class ProviderBusy(GatewayError):
    """The provider is briefly overloaded (HTTP 503); worth one retry before falling through."""


class ExternalServiceError(JobWeaverError):
    status_code = 502
    code = "external_service_error"
