"""Error reporting to a free error-tracking tier (FR-G5), off unless SENTRY_DSN is set.

Reports carry the stack trace and route, never what users wrote: request bodies, cookies,
headers, query strings and local variables are stripped before anything leaves the
server (FR-G3: no document text, Draft content or email bodies outside the database)."""

from typing import Any

from app.core.config import Settings

_KEEP_HEADERS = {"user-agent", "content-type", "accept"}


def scrub(event: dict[str, Any], _hint: dict[str, Any] | None = None) -> dict[str, Any]:
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "cookies", "query_string", "env"):
            request.pop(key, None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {k: v for k, v in headers.items() if k.lower() in _KEEP_HEADERS}
    event.pop("user", None)
    for breadcrumb in (event.get("breadcrumbs") or {}).get("values", []):
        if isinstance(breadcrumb, dict):
            breadcrumb.pop("data", None)
    for exception in (event.get("exception") or {}).get("values", []):
        for frame in ((exception or {}).get("stacktrace") or {}).get("frames", []):
            if isinstance(frame, dict):
                frame.pop("vars", None)
    return event


def init_error_tracking(settings: Settings) -> bool:
    """Returns whether error tracking was turned on."""
    if not settings.sentry_dsn:
        return False
    import sentry_sdk  # imported only when configured

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        # Errors only: performance tracing would spend the free tier's quota.
        traces_sample_rate=0.0,
        before_send=scrub,  # type: ignore[arg-type]
    )
    return True
