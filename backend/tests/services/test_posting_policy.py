"""Publisher exclusions must apply before storage without erasing user history."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.adapters.jsearch import JSearchAdapter
from app.adapters.posting_policy import blocked_company
from app.adapters.serpapi import SerpApiAdapter
from app.models.posting import Company, Posting
from app.models.source import Source
from app.services.fetching import save_postings
from tests.services.test_correspondence import NOW, posting


@pytest.mark.parametrize("name", ["vmysmartpros", " VMySmartPros Pvt Ltd ", "RemotePromsp"])
async def test_excluded_publishers_never_create_companies_or_postings(db, name):
    new, seen = await save_postings(db, "adzuna", [posting("blocked", company=name)], NOW)
    assert new == 0
    assert seen == {"blocked"}
    assert await db.scalar(select(func.count()).select_from(Company)) == 0
    assert await db.scalar(select(func.count()).select_from(Posting)) == 0


async def test_policy_matches_identity_not_description_or_substrings(db):
    assert not blocked_company("Not vmysmartpros")
    new, _ = await save_postings(
        db, "adzuna", [posting("good", description="Moved from remotepromsp to Acme")], NOW
    )
    assert new == 1
    assert await db.scalar(select(func.count()).select_from(Posting)) == 1


async def test_migration_disables_only_selected_sources(db):
    names = ["jsearch", "serpapi", "adzuna", "foundit", "linkedin", "hackernews"]
    db.add_all(Source(name=name, enabled=True) for name in names)
    await db.flush()
    spec = spec_from_file_location(
        "disable_google_jobs",
        Path(__file__).parents[2] / "alembic/versions/0010_disable_google_jobs.py",
    )
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    def upgrade(connection):
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    await (await db.connection()).run_sync(upgrade)
    states = dict((await db.execute(select(Source.name, Source.enabled))).all())
    assert states == {name: name not in {"jsearch", "serpapi"} for name in names}
    assert JSearchAdapter.default_enabled is False
    assert SerpApiAdapter.default_enabled is False
