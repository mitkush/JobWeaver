import os

from cryptography.fernet import Fernet

# Test settings must be in place before the app is imported.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://jobweaver:jobweaver@localhost:5432/jobweaver_test"
)
os.environ.update(
    ENVIRONMENT="test",
    GATEWAY_MODE="recorded",
    GATEWAY_RECORDED_DIR=os.path.join(os.path.dirname(__file__), "fixtures", "gateway"),
    CREDENTIALS_ENCRYPTION_KEY=Fernet.generate_key().decode(),
    SESSION_SECRET="test-secret-at-least-16-chars",
    SCHEDULER_ENABLED="false",
    PUBLIC_URL="http://testserver",
    GOOGLE_CLIENT_ID="test-client-id",
    GOOGLE_CLIENT_SECRET="test-client-secret",
    ADMIN_EMAILS="admin@example.com",
    DEV_LOGIN_ENABLED="false",
)

from collections.abc import AsyncIterator  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_engine, get_sessionmaker  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, User  # noqa: E402
from app.services.auth import create_session, upsert_google_user  # noqa: E402
from app.services.google_oauth import GoogleProfile  # noqa: E402

CSRF = "test-csrf-token"


@pytest.fixture(scope="session", autouse=True)
async def _schema() -> AsyncIterator[None]:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture(autouse=True)
async def _clean() -> AsyncIterator[None]:
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


def make_client(session_token: str | None = None) -> httpx.AsyncClient:
    cookies = {"jw_csrf": CSRF}
    if session_token:
        cookies["jw_session"] = session_token
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        cookies=cookies,
        headers={"X-CSRF-Token": CSRF},
    )


async def signed_in(db: AsyncSession, email: str) -> tuple[User, httpx.AsyncClient]:
    user = await upsert_google_user(db, GoogleProfile(f"sub-{email}", email, "Test User", None))
    token = await create_session(db, user)
    await db.commit()
    return user, make_client(token)


@pytest.fixture
async def anon() -> AsyncIterator[httpx.AsyncClient]:
    async with make_client() as client:
        yield client


@pytest.fixture
async def alice(db: AsyncSession) -> AsyncIterator[tuple[User, httpx.AsyncClient]]:
    user, client = await signed_in(db, "alice@example.com")
    async with client:
        yield user, client


@pytest.fixture
async def bob(db: AsyncSession) -> AsyncIterator[tuple[User, httpx.AsyncClient]]:
    user, client = await signed_in(db, "bob@example.com")
    async with client:
        yield user, client


async def onboard(client: httpx.AsyncClient, country: str = "IN") -> None:
    """Accept the AI notice and set a country so uploads are allowed."""
    assert (await client.post("/api/me/ai-notice")).status_code == 200
    assert (await client.put("/api/me/country", json={"country": country})).status_code == 200
