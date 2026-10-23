"""Careers-page capture starts without a Feed entry or Draft and makes no AI call."""

import copy
import uuid

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import Draft, Job, Posting, UserJob
from app.schemas.capture import public_page_url
from app.services.correspondence import merge_jobs, source_priorities
from app.services.feed import sync_user_feed
from tests.api.test_drafts import generated, prepared  # noqa: F401
from tests.api.test_extension import EXT, connect, ext_client

ADVERT = {
    "title": "Senior Software Engineer",
    "company": "Example Health",
    "url": "https://careers.example.com/jobs/123?utm_source=mail&token=private#apply",
    "description": "Build Ruby on Rails services and maintain PostgreSQL databases. " * 4,
}


@pytest.fixture(autouse=True)
def allow_extension(monkeypatch):
    monkeypatch.setenv("EXTENSION_IDS", EXT)
    get_settings.cache_clear()


async def captured(client, body=None):
    token = await connect(client)
    async with ext_client(token=token) as ext:
        response = await ext.post("/api/ext/jobs/capture", json=body or ADVERT)
    assert response.status_code == 201, response.text
    return response.json(), token


async def test_unknown_job_saved_without_preferences_or_ai_consent_survives_rebuild(alice, db):
    user, client = alice
    result, token = await captured(client)
    job_id = uuid.UUID(result["job_id"])
    assert result["matched_existing"] is False
    posting = await db.scalar(select(Posting).where(Posting.job_id == job_id))
    assert posting.source == "captured"
    assert posting.apply_url == "https://careers.example.com/jobs/123"
    assert posting.description == ADVERT["description"].strip()
    await sync_user_feed(db, user.id)
    await db.commit()
    link = await db.scalar(
        select(UserJob).where(UserJob.user_id == user.id, UserJob.job_id == job_id)
    )
    assert link is not None and link.captured_at is not None
    assert link.page_description["description"] == ADVERT["description"].strip()
    async with ext_client(token=token) as ext:
        # Saving is local work, but creating a Draft must retain the AI gates.
        response = await ext.post(f"/api/ext/jobs/{job_id}/draft")
    assert response.status_code == 409
    assert "AI data notice" in response.text
    assert (await client.get(f"/api/jobs/{job_id}")).status_code == 200


async def test_repeat_and_second_user_capture_share_job_but_never_rewrite_description(
    alice, bob, db
):
    user, a = alice
    other, b = bob
    first, _ = await captured(a)
    again, _ = await captured(a)
    assert first["job_id"] == again["job_id"]
    replacement = ADVERT | {
        "description": "A shorter and current public company job description. " * 3
    }
    second, _ = await captured(b, replacement)
    assert second["job_id"] == first["job_id"] and second["matched_existing"]
    job_id = uuid.UUID(first["job_id"])
    posting = await db.scalar(select(Posting).where(Posting.job_id == job_id))
    assert posting.description == ADVERT["description"].strip()
    links = (await db.scalars(select(UserJob).where(UserJob.job_id == job_id))).all()
    texts = {link.user_id: link.page_description["description"] for link in links}
    assert texts[user.id] == ADVERT["description"].strip()
    assert texts[other.id] == replacement["description"].strip()


async def test_capture_creates_draft_from_own_facts_and_keeps_older_draft_context(prepared, db):  # noqa: F811
    user, client, job_id, _ = prepared
    old = await generated(prepared)
    old_draft = await db.get(Draft, uuid.UUID(old["id"]))
    original = copy.deepcopy(old_draft.job_snapshot)
    job = await db.get(Job, uuid.UUID(job_id))
    body = ADVERT | {"url": job.apply_url, "title": job.title, "company": job.company_name}
    result, token = await captured(client, body)
    assert result["job_id"] == job_id and result["matched_existing"]
    async with ext_client(token=token) as ext:
        response = await ext.post(f"/api/ext/jobs/{job_id}/draft")
    assert response.status_code == 202, response.text
    new_id = uuid.UUID(response.json()["draft_id"])
    assert new_id != old_draft.id
    await db.refresh(old_draft)
    assert old_draft.job_snapshot == original
    new = await db.get(Draft, new_id)
    assert new.user_id == user.id
    assert new.job_snapshot["description"] == body["description"].strip()
    assert new.job_snapshot["description_origin"]["url"] == public_page_url(job.apply_url)
    assert new.job_snapshot["required_skills"] == []
    assert new.state == "ready"


async def test_another_users_job_cannot_be_drafted(bob, alice):
    _, a = alice
    _, b = bob
    first, _ = await captured(a)
    token = await connect(b)
    async with ext_client(token=token) as ext:
        response = await ext.post(f"/api/ext/jobs/{first['job_id']}/draft")
    assert response.status_code == 404


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:pass@example.com/job",
        "http://127.0.0.1/job",
        "http://localhost/job",
    ],
)
async def test_capture_refuses_nonpublic_urls(alice, url):
    _, client = alice
    token = await connect(client)
    async with ext_client(token=token) as ext:
        response = await ext.post("/api/ext/jobs/capture", json=ADVERT | {"url": url})
    assert response.status_code == 422


async def test_capture_requires_reviewable_content_and_bearer(alice):
    _, client = alice
    assert (await client.post("/api/ext/jobs/capture", json=ADVERT)).status_code == 401
    token = await connect(client)
    async with ext_client(token=token) as ext:
        assert (
            await ext.post("/api/ext/jobs/capture", json=ADVERT | {"description": "too short"})
        ).status_code == 422
        assert (
            await ext.post("/api/ext/jobs/capture", json=ADVERT | {"company": " "})
        ).status_code == 422


async def test_merge_keeps_captured_link_and_its_own_description(alice, db):
    user, client = alice
    first, _ = await captured(client)
    second, _ = await captured(
        client, ADVERT | {"title": "Different role", "url": "https://other.example/jobs/456"}
    )
    survivor = await merge_jobs(
        db, uuid.UUID(first["job_id"]), uuid.UUID(second["job_id"]), source_priorities()
    )
    await db.commit()
    link = await db.scalar(
        select(UserJob).where(UserJob.user_id == user.id, UserJob.job_id == survivor)
    )
    assert (
        link is not None and link.captured_at and link.page_description["title"] == ADVERT["title"]
    )
