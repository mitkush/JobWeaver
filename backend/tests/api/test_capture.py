"""Careers-page capture starts without a Feed entry or Draft and makes no AI call."""

import copy
import uuid

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import GatewayError
from app.models import Draft, DraftVersion, Job, Posting, UserJob
from app.models.preference import Preference
from app.schemas.capture import public_page_url
from app.services.correspondence import merge_jobs, source_priorities
from app.services.feed import sync_user_feed
from tests.api.test_drafts import generated, prepared  # noqa: F401
from tests.api.test_extension import EXT, connect, ext_client
from tests.conftest import signed_in

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
    assert posting.description == ""
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
    assert posting.description == ""
    links = (await db.scalars(select(UserJob).where(UserJob.job_id == job_id))).all()
    texts = {link.user_id: link.page_description["description"] for link in links}
    assert texts[user.id] == ADVERT["description"].strip()
    assert texts[other.id] == replacement["description"].strip()
    assert (await a.get(f"/api/jobs/{job_id}")).json()["description"] == texts[user.id]
    assert (await b.get(f"/api/jobs/{job_id}")).json()["description"] == texts[other.id]


async def test_capture_reaches_an_existing_draft_only_through_a_reviewed_replacement(prepared, db):  # noqa: F811
    """One active package per Job: the captured page JD becomes a new version only when the
    User accepts a replacement, and earlier versions keep their own job context."""
    user, client, job_id, _ = prepared
    old = await generated(prepared)
    draft = await db.get(Draft, uuid.UUID(old["id"]))
    first_context = copy.deepcopy(
        (await db.scalar(select(DraftVersion).where(DraftVersion.draft_id == draft.id))).job_context
    )
    job = await db.get(Job, uuid.UUID(job_id))
    job.required_skills = ["Redis"]
    await db.commit()
    body = ADVERT | {"url": job.apply_url, "title": job.title, "company": job.company_name}
    result, token = await captured(client, body)
    assert result["job_id"] == job_id and result["matched_existing"]
    async with ext_client(token=token) as ext:
        response = await ext.post(f"/api/ext/jobs/{job_id}/draft")
    assert response.status_code == 202, response.text
    assert response.json() == {"draft_id": old["id"], "state": "ready", "existing": True}

    queued = await client.post(
        f"/api/drafts/{old['id']}/proposals",
        json={"expected_version": 1, "part": "resume"},
    )
    assert queued.status_code == 202, queued.text
    [proposal] = (await client.get(f"/api/drafts/{old['id']}/proposals")).json()
    assert proposal["state"] == "ready", proposal
    accepted = await client.post(
        f"/api/drafts/{old['id']}/proposals/{proposal['id']}/accept",
        json={"expected_version": 1},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["current_version"] == 2
    versions = list(
        await db.scalars(
            select(DraftVersion)
            .where(DraftVersion.draft_id == draft.id)
            .order_by(DraftVersion.number)
            .execution_options(populate_existing=True)
        )
    )
    assert versions[0].job_context == first_context
    assert versions[1].job_context["description"] == body["description"].strip()
    assert versions[1].job_context["description_origin"]["url"] == public_page_url(job.apply_url)
    assert versions[1].job_context["required_skills"] == [
        "Python",
        "PostgreSQL",
        "Kubernetes",
        "Go",
    ]
    await db.refresh(job)
    assert job.required_skills == ["Redis"]


async def test_capture_only_job_never_enters_another_users_matching_feed(alice, bob, db):
    owner, a = alice
    friend, b = bob
    private_text = "Private edited browser description: do not share this. " * 4
    first, _ = await captured(a, ADVERT | {"description": private_text})
    db.add(Preference(user_id=friend.id, titles=[ADVERT["title"]]))
    await db.commit()
    await sync_user_feed(db, friend.id)
    await sync_user_feed(db, owner.id)
    await db.commit()
    job_id = uuid.UUID(first["job_id"])
    assert (
        await db.scalar(
            select(UserJob.id).where(UserJob.user_id == friend.id, UserJob.job_id == job_id)
        )
        is None
    )
    assert (await b.get(f"/api/jobs/{job_id}")).status_code == 404
    assert private_text.strip() not in (await b.get("/api/feed?section=link")).text
    assert (await a.get(f"/api/jobs/{job_id}")).json()["description"] == private_text.strip()


async def test_page_skill_extraction_failure_stops_draft_instead_of_silently_losing_checks(
    prepared,  # noqa: F811
    monkeypatch,
    db,
):
    _, client, _, gateway = prepared
    result, token = await captured(client)

    async def unavailable(_request):
        raise GatewayError("Unavailable")

    monkeypatch.setattr(gateway, "extract_skills", unavailable)
    async with ext_client(token=token) as ext:
        response = await ext.post(f"/api/ext/jobs/{result['job_id']}/draft")
    assert response.status_code == 202
    draft = await db.get(Draft, uuid.UUID(response.json()["draft_id"]))
    assert draft.state == "failed"
    assert draft.job_snapshot["page_skills_pending"] is True


@pytest.mark.parametrize(
    "stored_url,page_url",
    [
        (
            "https://boards.greenhouse.io/acme/jobs/42?gh_src=linkedin",
            "https://job-boards.greenhouse.io/acme/jobs/42",
        ),
        ("https://jobs.lever.co/acme/42/apply?utm_source=mail", "https://jobs.lever.co/acme/42"),
        (
            "https://acme.example/careers?gh_jid=4012345&utm_source=mail",
            "https://acme.example/careers?gh_jid=4012345",
        ),
    ],
)
async def test_capture_reuses_existing_job_across_url_variations(alice, db, stored_url, page_url):
    _, client = alice
    first, _ = await captured(client)
    job = await db.get(Job, uuid.UUID(first["job_id"]))
    job.apply_url = stored_url
    await db.commit()
    second, _ = await captured(client, ADVERT | {"url": page_url})
    assert second["job_id"] == first["job_id"]
    assert second["matched_existing"] is True


async def test_push_only_source_has_no_admin_fetch_controls(db):
    _, client = await signed_in(db, "admin@example.com")
    async with client:
        response = await client.get("/api/admin/sources")
        assert response.status_code == 200
        assert "captured" not in [row["name"] for row in response.json()]
        assert (
            await client.patch("/api/admin/sources/captured", json={"enabled": True})
        ).status_code == 422
        run = await client.post("/api/admin/sources/captured/run")
        assert run.status_code == 200
        assert run.json()["status"] == "skipped"


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
