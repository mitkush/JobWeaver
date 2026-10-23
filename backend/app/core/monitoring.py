"""Error reporting (FR-G5) and log formatting that never carry what users wrote (FR-G3:
no document text, Draft content or email bodies outside the database).

Error messages are treated as unsafe: a database error, for one, quotes the values it was
given, which can be a resume or a Draft. Reports keep the exception type, the stack and
the route; logs keep the type, the SQL statement and the stack."""

import logging
import re
import traceback
from types import TracebackType
from typing import Any

from sqlalchemy.exc import StatementError

from app.core.config import Settings

REMOVED = "[removed: may contain user content]"


class QueryCredentialFilter(logging.Filter):
    """HTTPX logs complete URLs; some providers require credentials in query strings."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = re.sub(
            r"([?&](?:api_key|app_key|token)=)[^&\s\"']+",
            r"\1[redacted]",
            message,
            flags=re.IGNORECASE,
        )
        if message != redacted:
            record.msg, record.args = redacted, ()
        return True


class RedactedDatabaseError(Exception):
    """Stands in for a database error in logs: its type and SQL, never its values."""


class RedactingFormatter(logging.Formatter):
    def formatException(  # noqa: N802 - logging's own method name
        self,
        ei: tuple[type[BaseException], BaseException, TracebackType | None]
        | tuple[None, None, None],
    ) -> str:
        _, value, tb = ei
        if isinstance(value, StatementError):
            safe = RedactedDatabaseError(f"{type(value).__name__} [SQL: {value.statement}]")
            # The driver's own error (the chained cause) quotes the values too: dropped.
            return "".join(traceback.format_exception(type(safe), safe, tb, chain=False)).rstrip()
        return super().formatException(ei)


def configure_logging() -> None:
    logging.getLogger("httpx").addFilter(QueryCredentialFilter())
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


_KEEP_HEADERS = {"user-agent", "content-type", "accept"}


def scrub(event: dict[str, Any], _hint: dict[str, Any] | None = None) -> dict[str, Any]:
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "cookies", "query_string", "env"):
            request.pop(key, None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {k: v for k, v in headers.items() if k.lower() in _KEEP_HEADERS}
    for key in ("user", "breadcrumbs", "extra", "message"):
        event.pop(key, None)
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        # The template ("Saving %s failed") groups errors; its values may be user content.
        event["logentry"] = {"message": logentry.get("message", "")}
    for exception in (event.get("exception") or {}).get("values", []):
        if not isinstance(exception, dict):
            continue
        if exception.get("value"):
            exception["value"] = REMOVED
        for frame in (exception.get("stacktrace") or {}).get("frames", []):
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
