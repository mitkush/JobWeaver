"""Application tracker, Follow-up Reminders and Company history (FR-F1 to FR-F3)."""

import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.adapters.gmail import get_gmail_client
from app.main import app
from app.models import Application, GmailHandoff, Job
from app.services import applications as service
from app.services.email_check import EmailCheck
from app.services.google_oauth import get_google_client
from tests.api.test_drafts import FakeGmail, GoodGoogle, connect, generated, prepared  # noqa: F401


@pytest.fixture
def ok_recipient(monkeypatch):
    async def check(recipient):
        return EmailCheck(recipient=recipient, valid=True, warnings=[])

    monkeypatch.setattr(service, "check_recipient", check)


async def applied(prepared):  # noqa: F811
    draft = await generated(prepared)
    _, client, _, _ = prepared
    assert (
        await client.post(f"/api/drafts/{draft['id']}/applied", json={"expected_version": 1})
    ).status_code == 204
    return draft, (await client.get("/api/applications")).json()[0]


async def test_tracker_records_every_status_change(prepared):  # noqa: F811
    _, client, job_id, _ = prepared
    draft, item = await applied(prepared)
    assert item["job_id"] == job_id and item["draft_id"] == draft["id"]
    assert item["status"] == "applied" and item["applied_at"]
    assert [e["status"] for e in item["history"]] == ["drafted", "applied"]

    moved = await client.patch(f"/api/applications/{item['id']}", json={"status": "interview"})
    assert moved.status_code == 200
    assert [e["status"] for e in moved.json()["history"]] == ["drafted", "applied", "interview"]
    assert moved.json()["applied_at"] == item["applied_at"]
    # Mark as applied never moves a later status back.
    await client.post(f"/api/drafts/{draft['id']}/applied", json={"expected_version": 1})
    assert (await client.get("/api/applications")).json()[0]["status"] == "interview"

    bad = await client.patch(f"/api/applications/{item['id']}", json={"status": "ghosted"})
    assert bad.status_code == 422
    # Moved back to Drafted by hand: no longer counts as applied (FR-D5).
    back = await client.patch(f"/api/applications/{item['id']}", json={"status": "drafted"})
    assert back.json()["applied_at"] is None


async def test_applications_are_private(prepared, bob):  # noqa: F811
    _, item = await applied(prepared)
    _, other = bob
    assert (await other.get("/api/applications")).json() == []
    assert (await other.get("/api/reminders")).json() == []
    for request in (
        other.patch(f"/api/applications/{item['id']}", json={"status": "offer"}),
        other.get(f"/api/applications/{item['id']}/follow-up"),
        other.post(f"/api/applications/{item['id']}/follow-up/dismiss"),
        other.post(
            f"/api/applications/{item['id']}/follow-up",
            json={"recipient": "a@b.co", "subject": "s", "body": "b", "confirm": True},
        ),
    ):
        assert (await request).status_code == 404
    history = (await other.get(f"/api/companies/{item['company_id']}/applications")).json()
    assert history["applications"] == []


async def test_company_history_lists_every_application_there(prepared, db):  # noqa: F811
    user, client, _, _ = prepared
    _, item = await applied(prepared)
    history = await client.get(f"/api/companies/{item['company_id']}/applications")
    assert history.json()["name"] and [a["id"] for a in history.json()["applications"]] == [
        item["id"]
    ]
    assert (await client.get(f"/api/companies/{uuid.uuid4()}/applications")).status_code == 404


async def test_follow_up_reminder_drafts_a_template_email_without_attachment(
    prepared,  # noqa: F811
    db,
    ok_recipient,
):
    user, client, _, _ = prepared
    _, item = await applied(prepared)
    assert (await client.get("/api/reminders")).json() == []
    await db.execute(
        update(Application).values(follow_up_after=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db.commit()
    reminders = (await client.get("/api/reminders")).json()
    assert [r["application_id"] for r in reminders] == [item["id"]]
    assert (await client.get("/api/applications")).json()[0]["follow_up_due"] is True

    template = (await client.get(f"/api/applications/{item['id']}/follow-up")).json()
    job = await db.get(Job, uuid.UUID(item["job_id"]))
    assert job.title in template["body"] and job.company_name in template["body"]
    assert template["subject"] == f"Following up: {job.title} application"

    await connect(db, user)
    gmail = FakeGmail()
    app.dependency_overrides[get_google_client] = lambda: GoodGoogle()
    app.dependency_overrides[get_gmail_client] = lambda: gmail
    body = {"recipient": "jobs@acme.com", "subject": template["subject"], "body": "Edited"}
    refused = await client.post(f"/api/applications/{item['id']}/follow-up", json=body)
    assert refused.status_code == 409  # the recipient must be confirmed first
    sent = await client.post(
        f"/api/applications/{item['id']}/follow-up", json=body | {"confirm": True}
    )
    assert sent.json()["mode"] == "gmail"
    raw = base64.urlsafe_b64decode(gmail.calls[0][1]).decode()
    assert "Edited" in raw and "attachment" not in raw.lower()
    handoff = await db.scalar(select(GmailHandoff).where(GmailHandoff.kind == "follow_up"))
    assert handoff.gmail_draft_id == "gmail-draft-123"
    # The reminder waits another period; the status is unchanged.
    assert (await client.get("/api/reminders")).json() == []
    assert (await client.get("/api/applications")).json()[0]["status"] == "applied"


async def test_reminders_can_be_dismissed_and_follow_ups_need_applied(prepared, db):  # noqa: F811
    _, client, _, _ = prepared
    _, item = await applied(prepared)
    await db.execute(
        update(Application).values(follow_up_after=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db.commit()
    dismissed = await client.post(f"/api/applications/{item['id']}/follow-up/dismiss")
    assert dismissed.status_code == 204
    assert (await client.get("/api/reminders")).json() == []
    await client.patch(f"/api/applications/{item['id']}", json={"status": "replied"})
    assert (await client.get(f"/api/applications/{item['id']}/follow-up")).status_code == 409


async def test_follow_up_days_setting(prepared, db):  # noqa: F811
    user, client, _, _ = prepared
    assert (await client.get("/api/me")).json()["follow_up_days"] == 7
    assert (await client.put("/api/me/follow-up-days", json={"days": 0})).status_code == 422
    saved = await client.put("/api/me/follow-up-days", json={"days": 10})
    assert saved.json()["follow_up_days"] == 10
    _, item = await applied(prepared)
    db.expire_all()
    row = await db.get(Application, uuid.UUID(item["id"]))
    assert (row.follow_up_after - row.status_changed_at).days == 10
