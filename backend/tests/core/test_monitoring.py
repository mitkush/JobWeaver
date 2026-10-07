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
