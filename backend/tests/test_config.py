import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_refuses_to_start_without_real_secrets():
    with pytest.raises(ValidationError, match="SESSION_SECRET, CREDENTIALS_ENCRYPTION_KEY"):
        Settings(
            environment="production",
            session_secret="dev-only-change-me",
            credentials_encryption_key="",
            google_client_id="",
            google_client_secret="",
        )


def test_production_starts_with_secrets():
    settings = Settings(
        environment="production",
        session_secret="a-real-secret-value",
        credentials_encryption_key="key",
        google_client_id="id",
        google_client_secret="secret",
        public_url="https://jobweaver.example",
    )
    assert settings.secure_cookies


def test_admin_emails_are_comma_separated(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "A@x.com, b@y.com")
    assert Settings().admin_emails == ["a@x.com", "b@y.com"]


def test_production_requires_an_https_public_url():
    with pytest.raises(ValidationError, match=r"PUBLIC_URL \(https\)"):
        Settings(
            environment="production",
            session_secret="a-real-secret-value",
            credentials_encryption_key="key",
            google_client_id="id",
            google_client_secret="secret",
            public_url="http://jobweaver.example",
        )
