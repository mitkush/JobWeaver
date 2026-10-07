"""Error reports never carry what users wrote (FR-G3, FR-G5)."""

from app.core.config import Settings
from app.core.monitoring import init_error_tracking, scrub


def test_reporting_is_off_without_a_dsn():
    assert init_error_tracking(Settings(sentry_dsn="")) is False


def test_scrub_strips_bodies_cookies_headers_and_local_variables():
    event = {
        "request": {
            "url": "https://jobweaver.app/api/drafts/1/chat",
            "data": {"message": "my private draft text"},
            "cookies": {"jw_session": "secret"},
            "query_string": "recipient=a@b.co",
            "headers": {
                "Cookie": "jw_session=secret",
                "Authorization": "Bearer x",
                "User-Agent": "Mozilla",
            },  # fmt: skip
        },
        "user": {"email": "asha@example.com"},
        "breadcrumbs": {"values": [{"message": "GET /api", "data": {"body": "resume text"}}]},
        "exception": {
            "values": [{"stacktrace": {"frames": [{"function": "f", "vars": {"text": "resume"}}]}}]
        },  # fmt: skip
    }
    cleaned = scrub(event)
    assert "secret" not in str(cleaned) and "private" not in str(cleaned)
    assert "resume" not in str(cleaned) and "asha" not in str(cleaned)
    assert cleaned["request"]["url"].endswith("/chat")
    assert cleaned["request"]["headers"] == {"User-Agent": "Mozilla"}


async def test_logged_database_errors_never_carry_query_values():
    """Database errors quote the values they were given, which can be resumes or Drafts;
    logs keep the error type, SQL and stack only (FR-G3)."""
    import logging
    import sys

    import pytest
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from app.core.db import get_sessionmaker
    from app.core.monitoring import RedactingFormatter

    # Built at run time: the traceback shows source lines, which are code, not user data.
    private = " ".join(["my", "private", "resume"])
    async with get_sessionmaker()() as session:
        with pytest.raises(DBAPIError) as caught:
            await session.execute(text("SELECT CAST(:v AS integer)"), {"v": private})
    # SQLAlchemy's own parameter listing is off at the engine.
    assert "[parameters:" not in str(caught.value)
    try:
        raise caught.value
    except DBAPIError:
        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "Save failed", None,
                                   sys.exc_info())  # fmt: skip
    logged = RedactingFormatter("%(message)s").format(record)
    assert private not in logged
    assert "DBAPIError [SQL: SELECT CAST($1 AS integer)]" in logged and "Traceback" in logged


def test_scrub_drops_exception_and_log_text():
    event = {
        "exception": {
            "values": [
                {
                    "type": "IntegrityError",
                    "module": "sqlalchemy.exc",
                    "value": "duplicate key (body)=(my private draft)",
                }
            ]
        },  # fmt: skip
        "logentry": {
            "message": "Saving %s failed",
            "params": ["my private draft"],
            "formatted": "Saving my private draft failed",
        },  # fmt: skip
        "message": "Saving my private draft failed",
        "breadcrumbs": {
            "values": [{"category": "query", "message": "INSERT ... my private draft"}]
        },
        "extra": {"sys.argv": ["uvicorn"], "draft": "my private draft"},
    }
    cleaned = scrub(event)
    assert "private" not in str(cleaned)
    # Enough is left to group and debug: the exception type and the log template.
    assert cleaned["exception"]["values"][0]["type"] == "IntegrityError"
    assert cleaned["logentry"]["message"] == "Saving %s failed"
