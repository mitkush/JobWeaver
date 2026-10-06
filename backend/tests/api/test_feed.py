"""Feed and Correspondence endpoints, including cross-user isolation (FR-D1 AC1, ADR-0001)."""

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, update

from app.adapters.base import Location
from app.api.deps import get_gateway
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.gateway.recorded import RecordedAIGateway
from app.main import app
from app.models import FetchRun, Job, MatchPair, PairStatus, Posting, RejectedPair, RunStatus
from app.services.correspondence import Correspondence
from tests.services.test_correspondence import ADVERT, NOW, OTHER_ROLE, add, posting

BACKEND_BLR = {
    "titles": ["Backend Engineer"],
    "locations": [{"city": "Bengaluru", "country": "IN"}],
    "work_modes": ["hybrid", "onsite"],
}
DATA_PUNE = {
    "titles": ["Data Engineer"],
    "locations": [{"city": "Pune", "country": "IN"}],
    "work_modes": ["onsite"],
}


def gateway() -> RecordedAIGateway:
    return RecordedAIGateway(Path(get_settings().gateway_recorded_dir))


async def process(**overrides) -> None:
    settings = get_settings().model_copy(update=overrides)

    async def no_sleep(_: float) -> None:
        return None

    await Correspondence(
        get_sessionmaker(), gateway(), settings, clock=lambda: NOW, sleep=no_sleep
    ).process()


@pytest.fixture(autouse=True)
def _recorded_gateway():
    app.dependency_overrides[get_gateway] = gateway


async def seed() -> None:
    await add(
        "linkedin",
        posting(
            "l1",
            contact_email="hiring@acme.com",
            apply_url="https://boards.greenhouse.io/acme/jobs/1?gh_src=linkedin",
        ),
        posting(
            "l2", title="Senior Backend Engineer", company="Globex", description="Globex " + ADVERT
        ),
        posting(
            "l3",
            title="Data Engineer",
            description=OTHER_ROLE,
            locations=[Location(city="Pune", country="IN")],
        ),
    )
    await add(
        "greenhouse",
        posting(
            "g1",
            apply_url="https://boards.greenhouse.io/acme/jobs/1",
            description="Acme backend role, Greenhouse version of the advert, short.",
            locations=[Location(city="Bengaluru", country="IN")],
        ),
    )
    await process()


async def test_feed_needs_sign_in(anon):
    assert (await anon.get("/api/feed")).status_code == 401


async def test_saving_preferences_fills_the_feed_at_once(alice, db):
    _, client = alice
    await seed()
    assert (await client.get("/api/feed")).json()["total"] == 0
    assert (await client.put("/api/preferences", json=BACKEND_BLR)).status_code == 200
    body = (await client.get("/api/feed")).json()
    assert body["counts"] == {"with_email": 1, "apply_link_only": 1}
    [card] = body["items"]
    assert card["title"] == "Backend Engineer"
    assert card["contact_email"] == "hiring@acme.com"
    assert [s["name"] for s in card["sources"]] == ["linkedin", "greenhouse"]
    # The background extraction ran after the response (recorded gateway).
    assert card["skill_gaps"] is None or isinstance(card["skill_gaps"], list)
    db.expire_all()
    assert (
        await db.scalar(select(Job.required_skills).where(Job.id == card["job_id"]))
    ) is not None


async def test_sections_filters_and_search(alice):
    _, client = alice
    await client.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    link_only = (await client.get("/api/feed", params={"section": "link"})).json()
    assert [c["company"] for c in link_only["items"]] == ["Globex"]

    async def total(**params):
        return (await client.get("/api/feed", params={"section": "link", **params})).json()["total"]

    assert await total(q="globex") == 1
    assert await total(q="nothing like this") == 0
    assert await total(source="linkedin") == 1
    assert await total(source="greenhouse") == 0
    assert await total(location="bengaluru") == 1
    assert await total(location="IN") == 1
    assert await total(location="Pune") == 0
    assert await total(posted_within_days=3) == 1
    assert await total(work_mode="remote") == 0


async def test_posted_within_uses_the_earliest_posting_date(alice, db):
    _, client = alice
    await client.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    await db.execute(update(Job).values(posted_at=NOW - timedelta(days=10)))
    await db.commit()
    assert (await client.get("/api/feed", params={"posted_within_days": 7})).json()["total"] == 0


async def test_freshness_shows_the_last_successful_fetch(alice, db):
    _, client = alice
    db.add(
        FetchRun(source="linkedin", status=RunStatus.SUCCEEDED, trigger="schedule", finished_at=NOW)
    )
    await db.commit()
    body = (await client.get("/api/feed")).json()
    assert body["last_updated_at"].startswith("2026-10-06T02:00")


async def test_hiding_is_personal(alice, bob):
    _, a = alice
    _, b = bob
    await a.put("/api/preferences", json=BACKEND_BLR)
    await b.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    job_id = (await a.get("/api/feed")).json()["items"][0]["job_id"]
    assert (await a.post(f"/api/feed/{job_id}/hide")).status_code == 204
    assert (await a.get("/api/feed")).json()["total"] == 0
    hidden = (await a.get("/api/feed", params={"hidden": True})).json()
    assert hidden["items"][0]["hidden"] is True
    assert (await b.get("/api/feed")).json()["total"] == 1
    assert (await a.delete(f"/api/feed/{job_id}/hide")).status_code == 204
    assert (await a.get("/api/feed")).json()["total"] == 1


async def test_hidden_job_stays_hidden_after_preferences_change(alice):
    _, client = alice
    await client.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    job_id = (await client.get("/api/feed")).json()["items"][0]["job_id"]
    await client.post(f"/api/feed/{job_id}/hide")
    await client.put("/api/preferences", json=DATA_PUNE)
    await client.put("/api/preferences", json=BACKEND_BLR)
    assert (await client.get("/api/feed")).json()["total"] == 0


async def test_one_users_preferences_never_reach_another_feed(alice, bob):
    # FR-D1 AC1
    _, a = alice
    _, b = bob
    await a.put("/api/preferences", json=BACKEND_BLR)
    await b.put("/api/preferences", json=DATA_PUNE)
    await seed()
    alice_jobs = {
        c["job_id"]
        for s in ("email", "link")
        for c in (await a.get("/api/feed", params={"section": s})).json()["items"]
    }
    bob_jobs = {
        c["job_id"]
        for s in ("email", "link")
        for c in (await b.get("/api/feed", params={"section": s})).json()["items"]
    }
    assert alice_jobs and bob_jobs and not alice_jobs & bob_jobs
    other = next(iter(alice_jobs))
    assert (await b.get(f"/api/jobs/{other}")).status_code == 404
    assert (await b.post(f"/api/feed/{other}/hide")).status_code == 404


async def test_correspondence_lists_every_posting_primary_first(alice):
    # FR-C6
    _, client = alice
    await client.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    job_id = (await client.get("/api/feed")).json()["items"][0]["job_id"]
    detail = (await client.get(f"/api/jobs/{job_id}")).json()
    assert [p["source"]["name"] for p in detail["postings"]] == ["linkedin", "greenhouse"]
    assert detail["postings"][0]["primary"] is True
    assert detail["description"].startswith("We are hiring")
    assert detail["possible_duplicates"] == []


async def medium_pair(client) -> tuple[str, dict]:
    await client.put("/api/preferences", json=BACKEND_BLR)
    await add("linkedin", posting("l1"))
    await add(
        "jsearch", posting("j1", title="Backend Engineer II", description=ADVERT + " Payments.")
    )
    await process(dedup_high_title=99)
    feed = (await client.get("/api/feed", params={"section": "link"})).json()
    assert all(card["possible_duplicate"] for card in feed["items"])
    detail = (await client.get(f"/api/jobs/{feed['items'][0]['job_id']}")).json()
    [duplicate] = detail["possible_duplicates"]
    return feed["items"][0]["job_id"], duplicate


async def test_confirm_merges_for_everyone(alice, bob, db):
    _, client = alice
    _, b = bob
    await b.put("/api/preferences", json=BACKEND_BLR)
    job_id, duplicate = await medium_pair(client)
    assert duplicate["other_job_in_feed"] is True
    response = await client.post(f"/api/possible-duplicates/{duplicate['pair_id']}/confirm")
    assert response.status_code == 200
    merged = response.json()["job_id"]
    assert (await client.get("/api/feed", params={"section": "link"})).json()["total"] == 1
    # Jobs are shared, so Bob sees one Job too (FR-C3 AC3).
    assert (await b.get("/api/feed", params={"section": "link"})).json()["total"] == 1
    detail = (await client.get(f"/api/jobs/{merged}")).json()
    assert len(detail["postings"]) == 2
    again = await client.post(f"/api/possible-duplicates/{duplicate['pair_id']}/confirm")
    assert again.status_code == 409


async def test_not_the_same_job_is_stored_and_never_proposed_again(alice, db):
    _, client = alice
    _, duplicate = await medium_pair(client)
    response = await client.post(f"/api/possible-duplicates/{duplicate['pair_id']}/reject")
    assert response.status_code == 204
    assert await db.scalar(select(RejectedPair.reason)) == "not_same"
    await db.execute(update(Posting).values(match_state="pending"))
    await db.commit()
    await process(dedup_high_title=99)
    feed = (await client.get("/api/feed", params={"section": "link"})).json()
    assert feed["total"] == 2
    assert not any(card["possible_duplicate"] for card in feed["items"])


async def test_pairs_outside_your_feed_cannot_be_decided(alice, bob):
    _, client = alice
    _, b = bob
    await b.put("/api/preferences", json=DATA_PUNE)
    _, duplicate = await medium_pair(client)
    assert (
        await b.post(f"/api/possible-duplicates/{duplicate['pair_id']}/confirm")
    ).status_code == 404
    assert (
        await b.post(f"/api/possible-duplicates/{duplicate['pair_id']}/reject")
    ).status_code == 404


async def test_split_takes_a_posting_out_for_good(alice, db):
    # FR-C4
    _, client = alice
    await client.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    job_id = (await client.get("/api/feed")).json()["items"][0]["job_id"]
    detail = (await client.get(f"/api/jobs/{job_id}")).json()
    greenhouse = next(p for p in detail["postings"] if p["source"]["name"] == "greenhouse")
    response = await client.post(f"/api/jobs/{job_id}/postings/{greenhouse['id']}/split")
    assert response.status_code == 200
    new_job = response.json()["job_id"]
    assert new_job != job_id
    assert len((await client.get(f"/api/jobs/{job_id}")).json()["postings"]) == 1
    assert len((await client.get(f"/api/jobs/{new_job}")).json()["postings"]) == 1
    await db.execute(update(Posting).values(match_state="pending"))
    await db.commit()
    await process()
    assert len((await client.get(f"/api/jobs/{job_id}")).json()["postings"]) == 1
    # A Job with one Posting has nothing to split.
    response = await client.post(f"/api/jobs/{new_job}/postings/{greenhouse['id']}/split")
    assert response.status_code == 422


async def test_split_rejects_postings_of_other_jobs(alice):
    _, client = alice
    await client.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    cards = (await client.get("/api/feed")).json()["items"] + (
        await client.get("/api/feed", params={"section": "link"})
    ).json()["items"]
    first, second = cards[0]["job_id"], cards[1]["job_id"]
    other = (await client.get(f"/api/jobs/{second}")).json()["postings"][0]["id"]
    assert (await client.post(f"/api/jobs/{first}/postings/{other}/split")).status_code == 404


async def test_confirm_is_refused_when_a_split_stands_between_the_jobs(alice, db):
    _, client = alice
    job_id, duplicate = await medium_pair(client)
    pair = await db.get(MatchPair, duplicate["pair_id"])
    db.add(
        RejectedPair(posting_a_id=pair.posting_a_id, posting_b_id=pair.posting_b_id, reason="split")
    )
    await db.commit()
    response = await client.post(f"/api/possible-duplicates/{duplicate['pair_id']}/confirm")
    assert response.status_code == 409
    db.expire_all()
    assert (await db.get(MatchPair, duplicate["pair_id"])).status == PairStatus.OPEN
