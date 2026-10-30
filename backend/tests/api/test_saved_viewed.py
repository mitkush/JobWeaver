"""Saved and Viewed: personal marks on a User's link to a Job (ADR-0001, ADR-0002)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import update

from app.models import Job
from tests.api.test_feed import BACKEND_BLR, DATA_PUNE, medium_pair, seed


async def first_job(client) -> str:
    return (await client.get("/api/feed")).json()["items"][0]["job_id"]


async def saved(client, **params) -> dict:
    return (await client.get("/api/feed", params={"view": "saved", **params})).json()


async def test_saving_is_personal_and_lists_every_bookmark(alice, bob):
    _, a = alice
    _, b = bob
    await a.put("/api/preferences", json=BACKEND_BLR)
    await b.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    email_job = await first_job(a)
    link_job = (await a.get("/api/feed", params={"section": "link"})).json()["items"][0]["job_id"]
    assert (await a.post(f"/api/feed/{email_job}/save")).status_code == 204
    assert (await a.post(f"/api/feed/{link_job}/save")).status_code == 204

    # Both sections in one shortlist; the count is every bookmark.
    shortlist = await saved(a)
    assert {card["job_id"] for card in shortlist["items"]} == {email_job, link_job}
    assert shortlist["total"] == 2 and shortlist["counts"]["saved"] == 2
    assert all(card["saved"] for card in shortlist["items"])
    feed = (await a.get("/api/feed")).json()
    assert feed["counts"]["saved"] == 2 and feed["items"][0]["saved"] is True

    # Another User shares the Job but not the bookmark, and cannot touch it.
    assert (await saved(b))["total"] == 0
    assert (await b.get("/api/feed")).json()["items"][0]["saved"] is False
    assert (await b.post(f"/api/feed/{uuid.uuid4()}/save")).status_code == 404

    assert (await a.delete(f"/api/feed/{email_job}/save")).status_code == 204
    assert [card["job_id"] for card in (await saved(a))["items"]] == [link_job]


async def test_filters_narrow_the_shortlist_but_not_its_count(alice):
    _, client = alice
    await client.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    job_id = await first_job(client)
    await client.post(f"/api/feed/{job_id}/save")
    narrowed = await saved(client, q="no such company")
    assert narrowed["total"] == 0 and narrowed["counts"]["saved"] == 1


async def test_a_saved_job_survives_a_preferences_change(alice):
    _, client = alice
    await client.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    job_id = await first_job(client)
    await client.post(f"/api/feed/{job_id}/save")
    await client.put("/api/preferences", json=DATA_PUNE)
    # Kept like a Drafted Job: still listed, marked as no longer matching.
    still = {c["job_id"]: c["match"] for c in (await client.get("/api/feed")).json()["items"]}
    assert still.get(job_id, "absent") is None
    [card] = (await saved(client))["items"]
    assert card["job_id"] == job_id and card["match"] is None
    assert (await client.get(f"/api/jobs/{job_id}")).json()["saved"] is True


async def test_saving_does_not_unhide_and_hidden_bookmarks_stay_saved(alice):
    _, client = alice
    await client.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    job_id = await first_job(client)
    await client.post(f"/api/feed/{job_id}/hide")
    await client.post(f"/api/feed/{job_id}/save")
    assert (await client.get("/api/feed")).json()["total"] == 0
    [card] = (await saved(client))["items"]
    assert card["hidden"] is True and card["saved"] is True
    assert (await client.get("/api/feed", params={"view": "hidden"})).json()["total"] == 1


async def test_an_expired_bookmark_stays_in_saved_with_its_label(alice, db):
    _, client = alice
    await client.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    job_id = await first_job(client)
    await client.post(f"/api/feed/{job_id}/save")
    await db.execute(
        update(Job).where(Job.id == uuid.UUID(job_id)).values(expired_at=datetime.now(UTC))
    )
    await db.commit()
    assert (await client.get("/api/feed")).json()["total"] == 0
    [card] = (await saved(client))["items"]
    assert card["expired"] is True


async def test_viewed_is_recorded_once_and_filters_the_feed(alice, bob):
    _, a = alice
    _, b = bob
    await a.put("/api/preferences", json=BACKEND_BLR)
    await b.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    job_id = await first_job(a)
    # Opening the Job page's data alone does not count as viewing it.
    await a.get(f"/api/jobs/{job_id}")
    assert (await a.get("/api/feed", params={"viewed": "unviewed"})).json()["total"] == 1
    assert (await a.post(f"/api/jobs/{job_id}/viewed")).status_code == 204
    assert (await a.post(f"/api/jobs/{job_id}/viewed")).status_code == 204
    assert (await a.get("/api/feed", params={"viewed": "unviewed"})).json()["total"] == 0
    viewed = (await a.get("/api/feed", params={"viewed": "viewed"})).json()
    assert viewed["items"][0]["viewed"] is True
    assert (await a.get(f"/api/jobs/{job_id}")).json()["viewed"] is True
    # Personal: Bob has not viewed it.
    assert (await b.get("/api/feed", params={"viewed": "unviewed"})).json()["total"] == 1
    assert (await b.post(f"/api/jobs/{uuid.uuid4()}/viewed")).status_code == 404


async def test_merging_jobs_keeps_saved_and_viewed_from_either_side(alice):
    _, client = alice
    job_id, duplicate = await medium_pair(client)
    feed = (await client.get("/api/feed", params={"section": "link"})).json()
    other = next(c["job_id"] for c in feed["items"] if c["job_id"] != job_id)
    await client.post(f"/api/feed/{job_id}/save")
    await client.post(f"/api/jobs/{other}/viewed")
    merged = (await client.post(f"/api/possible-duplicates/{duplicate['pair_id']}/confirm")).json()[
        "job_id"
    ]
    detail = (await client.get(f"/api/jobs/{merged}")).json()
    assert detail["saved"] is True and detail["viewed"] is True
    assert [c["job_id"] for c in (await saved(client))["items"]] == [merged]


async def test_viewed_history_survives_preferences_without_keeping_nonmatching_cards(alice):
    _, client = alice
    await client.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    job_id = await first_job(client)
    await client.post(f"/api/jobs/{job_id}/viewed")
    first_viewed = (await client.get(f"/api/jobs/{job_id}")).json()["viewed"]
    assert first_viewed is True

    await client.put("/api/preferences", json=DATA_PUNE)
    for status in ("any", "viewed", "unviewed"):
        cards = (await client.get("/api/feed", params={"viewed": status})).json()["items"]
        assert job_id not in {card["job_id"] for card in cards}
    assert (await saved(client))["total"] == 0

    await client.put("/api/preferences", json=BACKEND_BLR)
    cards = (await client.get("/api/feed", params={"viewed": "viewed"})).json()["items"]
    assert next(card for card in cards if card["job_id"] == job_id)["viewed"] is True
    unviewed = (await client.get("/api/feed", params={"viewed": "unviewed"})).json()["items"]
    assert job_id not in {card["job_id"] for card in unviewed}
