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
from app.models import (
    Draft,
    FetchRun,
    Job,
    MatchPair,
    PairStatus,
    Posting,
    RejectedPair,
    RunStatus,
)
from app.services import feed as feed_service
from app.services.correspondence import Correspondence, merge_jobs, source_priorities
from app.services.feed import sync_all_feeds
from app.tailoring.job_experience import experience_requirement
from tests.services.test_correspondence import ADVERT, NOW, OTHER_ROLE, FailingSkills, add, posting


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Requires 5+ years of relevant experience.", "5+ years"),
        ("3-5 years of professional experience required.", "3–5 years"),
        ("At least 2 years experience preferred.", "2+ years"),
        ("Experience with Python is required.", None),
    ],
)
def test_extract_experience_requirement(description, expected):
    assert experience_requirement(description) == expected


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


@pytest.fixture(autouse=True)
def _feed_clock(monkeypatch):
    # Seeded postings use NOW; relative date filters must use that same clock.
    list_feed = feed_service.list_feed

    async def at_fixture_time(session, user, query, now=None):
        return await list_feed(session, user, query, now=NOW if now is None else now)

    monkeypatch.setattr(feed_service, "list_feed", at_fixture_time)


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


async def test_global_wfh_feed_keeps_location_and_work_mode_separate(alice):
    _, client = alice
    await add(
        "linkedin",
        posting("in-remote", company="IndiaCo", work_mode="remote"),
        posting(
            "de-remote",
            company="GermanyCo",
            work_mode="remote",
            locations=[Location(city="Berlin", country="DE")],
        ),
        posting(
            "de-office",
            company="OfficeCo",
            work_mode="onsite",
            locations=[Location(city="Berlin", country="DE")],
        ),
    )
    await process()
    preferences = {"titles": ["Backend Engineer"], "locations": [], "work_modes": ["remote"]}
    assert (await client.put("/api/preferences", json=preferences)).status_code == 200
    cards = (await client.get("/api/feed", params={"section": "link"})).json()["items"]
    assert {card["company"] for card in cards} == {"IndiaCo", "GermanyCo"}
    preferences["locations"] = [{"country": "IN", "city": None}]
    assert (await client.put("/api/preferences", json=preferences)).status_code == 200
    cards = (await client.get("/api/feed", params={"section": "link"})).json()["items"]
    assert [card["company"] for card in cards] == ["IndiaCo"]
    assert cards[0]["work_mode"] == "remote"
    assert cards[0]["locations"][0]["country"] == "IN"


async def test_saving_preferences_fills_the_feed_at_once(alice, db):
    _, client = alice
    await seed()
    assert (await client.get("/api/feed")).json()["total"] == 0
    assert (await client.put("/api/preferences", json=BACKEND_BLR)).status_code == 200
    body = (await client.get("/api/feed")).json()
    assert body["counts"] == {
        "with_email": 1,
        "apply_link_only": 1,
        "title_matches": 2,
        "keyword_matches": 0,
        "review_matches": 0,
        "saved": 0,
    }
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


async def test_feed_card_uses_the_cached_experience_hint(alice):
    _, client = alice
    await add(
        "linkedin",
        posting("experience-hint", description=ADVERT + " Requires 3-5 years of experience."),
    )
    await process()
    await client.put("/api/preferences", json=BACKEND_BLR)

    cards = (await client.get("/api/feed", params={"section": "link"})).json()["items"]
    assert cards[0]["experience_requirement"] == "3–5 years"


async def test_sections_filters_and_search(alice, db):
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
    assert await total(source="site:LinkedIn") == 1
    assert await total(source="greenhouse") == 0
    for linkedin_source in ("linkedin-apify", "linkedin-piloterr"):
        await db.execute(
            update(Job).where(Job.company_name == "Globex").values(sources=[linkedin_source])
        )
        await db.commit()
        assert await total(source="site:LinkedIn") == 1
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


async def test_split_clears_possible_duplicates_between_former_group_mates(alice, db):
    _, client = alice
    job_id, duplicate = await medium_pair(client)
    # The pair's Postings end up in one Job some other way (e.g. a High match via a third
    # Posting), leaving the Medium pair open.
    pair = await db.get(MatchPair, duplicate["pair_id"])
    pair_id, split_posting_id = pair.id, pair.posting_b_id
    jobs_of = select(Posting.job_id).where(Posting.id.in_([pair.posting_a_id, pair.posting_b_id]))
    first, second = (await db.execute(jobs_of)).scalars().all()
    await merge_jobs(db, first, second, source_priorities())
    await db.commit()
    merged = (await client.get("/api/feed", params={"section": "link"})).json()["items"][0][
        "job_id"
    ]

    response = await client.post(f"/api/jobs/{merged}/postings/{split_posting_id}/split")
    assert response.status_code == 200
    db.expire_all()
    assert (await db.get(MatchPair, pair_id)).status == PairStatus.REJECTED
    feed = (await client.get("/api/feed", params={"section": "link"})).json()
    assert feed["total"] == 2
    assert not any(card["possible_duplicate"] for card in feed["items"])
    again = await client.post(f"/api/possible-duplicates/{pair_id}/reject")
    assert again.status_code == 409


async def test_not_the_same_job_tolerates_an_existing_rejected_pair(alice, db):
    _, client = alice
    _, duplicate = await medium_pair(client)
    pair = await db.get(MatchPair, duplicate["pair_id"])
    db.add(
        RejectedPair(posting_a_id=pair.posting_a_id, posting_b_id=pair.posting_b_id, reason="split")
    )
    await db.commit()
    response = await client.post(f"/api/possible-duplicates/{pair.id}/reject")
    assert response.status_code == 204


async def test_search_text_is_literal_not_a_wildcard(alice):
    _, client = alice
    await seed()
    await client.put("/api/preferences", json=BACKEND_BLR)
    everything = (await client.get("/api/feed")).json()["counts"]
    assert sum(everything.values()) > 0
    percent = (await client.get("/api/feed", params={"q": "%"})).json()["counts"]
    underscore = (await client.get("/api/feed", params={"q": "_"})).json()["counts"]
    assert sum(percent.values()) == 0 and sum(underscore.values()) == 0


RAILS_ADVERT = (
    "We are hiring an engineer for our payments platform. The stack is Ruby on Rails with "
    "PostgreSQL and Redis, deployed on AWS. Strong guardrails for code review. Pune office."
)
RAILS_BLR = BACKEND_BLR | {
    "titles": ["Backend Developer"],
    "keywords": ["Rails", "Ruby on Rails", "PostgreSQL", "Git"],
    "core_keywords": ["Rails"],
    "keyword_min_matches": 2,
}


async def confirmed_context(skills=None) -> None:
    """Explicit cached analysis for lexical/cache/isolation tests, without a model call."""
    async with get_sessionmaker()() as session:
        await session.execute(
            update(Job).values(
                required_skills=skills
                if skills is not None
                else ["Ruby on Rails", "PostgreSQL", "Sidekiq"],
                skills_extracted_at=NOW,
            )
        )
        await session.commit()


async def seed_keywords() -> None:
    await add(
        "linkedin",
        posting("k1", title="Software Engineer - Payments", description=RAILS_ADVERT),
        posting(
            "k2",
            title="Java Engineer",
            company="Initech",
            description="Java services with PostgreSQL and Git. Spring Boot. Bengaluru office.",
        ),
    )
    await process()
    await confirmed_context()


async def test_differently_titled_jobs_matching_core_keywords_get_their_own_section(alice):
    _, client = alice
    await seed_keywords()
    assert (await client.put("/api/preferences", json=RAILS_BLR)).status_code == 200
    title = (await client.get("/api/feed", params={"section": "link"})).json()
    assert title["items"] == []
    assert title["counts"]["keyword_matches"] == 1
    body = (await client.get("/api/feed", params={"section": "link", "match": "keywords"})).json()
    [card] = body["items"]
    assert card["title"] == "Software Engineer - Payments"
    assert card["match"] == "keywords"
    # "Rails" and "Ruby on Rails" are one skill; guardrails is not Rails. Skill extraction
    # ran after the sync and listed PostgreSQL, so that match now reads as a requirement.
    assert card["matched_keywords"] == [
        {"keyword": "Rails", "where": "requirements", "core": True},
        {"keyword": "PostgreSQL", "where": "requirements", "core": False},
    ]
    detail = (await client.get(f"/api/jobs/{card['job_id']}")).json()
    assert detail["match"] == "keywords"


async def test_no_core_keyword_means_no_keyword_section(alice):
    _, client = alice
    await seed_keywords()
    prefs = RAILS_BLR | {"core_keywords": []}
    assert (await client.put("/api/preferences", json=prefs)).status_code == 200
    body = (await client.get("/api/feed", params={"section": "link", "match": "keywords"})).json()
    assert body["items"] == [] and body["counts"]["keyword_matches"] == 0


async def test_core_keywords_must_be_keywords(alice):
    _, client = alice
    prefs = RAILS_BLR | {"core_keywords": ["Kotlin"]}
    assert (await client.put("/api/preferences", json=prefs)).status_code == 422
    prefs = RAILS_BLR | {"core_keywords": ["rails"]}
    saved = (await client.put("/api/preferences", json=prefs)).json()
    assert saved["core_keywords"] == ["Rails"]


async def test_drafted_job_stays_marked_no_longer_matching(alice, db):
    user, client = alice
    await seed_keywords()
    await client.put("/api/preferences", json=RAILS_BLR)
    params = {"section": "link", "match": "keywords"}
    job_id = (await client.get("/api/feed", params=params)).json()["items"][0]["job_id"]
    db.add(Draft(user_id=user.id, job_id=job_id))
    await db.commit()
    assert (await client.put("/api/preferences", json=BACKEND_BLR)).status_code == 200
    assert (await client.get("/api/feed", params=params)).json()["items"] == []
    kept = (await client.get("/api/feed", params={"section": "link"})).json()["items"]
    assert [(c["job_id"], c["match"], c["matched_keywords"]) for c in kept] == [(job_id, None, [])]
    # Matching again restores the reason.
    await client.put("/api/preferences", json=RAILS_BLR)
    [card] = (await client.get("/api/feed", params=params)).json()["items"]
    assert card["job_id"] == job_id and card["match"] == "keywords"


async def test_keywords_reach_only_their_owners_feed(alice, bob):
    _, a = alice
    _, b = bob
    await seed_keywords()
    await a.put("/api/preferences", json=RAILS_BLR)
    await b.put("/api/preferences", json=BACKEND_BLR)
    params = {"section": "link", "match": "keywords"}
    assert len((await a.get("/api/feed", params=params)).json()["items"]) == 1
    assert (await b.get("/api/feed", params=params)).json()["items"] == []
    assert (await b.get("/api/feed", params={"section": "link"})).json()["items"] == []


async def test_title_suggestions(alice):
    _, client = alice
    await client.put("/api/preferences", json=BACKEND_BLR)
    response = await client.get(
        "/api/preferences/title-suggestions", params={"titles": ["Backend Developer"]}
    )
    body = response.json()
    assert "Software Engineer" in body["titles"]
    assert body["searches_per_title"] >= 0


async def sync_all(_client) -> None:
    async with get_sessionmaker()() as session:
        await sync_all_feeds(session)
        await session.commit()


async def test_another_users_keywords_never_change_my_keyword_matches(alice, bob):
    _, a = alice
    _, b = bob
    await add(
        "linkedin",
        posting(
            "k3",
            title="Software Engineer - Billing",
            description=(
                "Rails developer wanted for our billing platform. postgresql experience "
                "required. Hybrid in our Bengaluru office."
            ),
        ),
    )
    await process()
    await confirmed_context()
    params = {"section": "link", "match": "keywords"}
    await a.put("/api/preferences", json=RAILS_BLR)
    before = (await a.get("/api/feed", params=params)).json()["items"]
    theirs = RAILS_BLR | {"keywords": ["Rails developer"], "core_keywords": ["Rails developer"]}
    await b.put("/api/preferences", json=theirs)
    await sync_all(a)
    after = (await a.get("/api/feed", params=params)).json()["items"]

    def matched(cards):
        return [(c["job_id"], {k["keyword"] for k in c["matched_keywords"]}) for c in cards]

    assert [c["title"] for c in before] == ["Software Engineer - Billing"]
    assert matched(after) == matched(before)
    assert matched(after)[0][1] == {"Rails", "PostgreSQL"}


async def test_core_keywords_are_must_haves_confirmed_by_the_job_description(alice):
    _, client = alice
    await add(
        "linkedin",
        posting(
            "j1",
            title="Backend Developer (Java)",
            company="SAP",
            description="Java, Spring Boot and PostgreSQL services for our finance and "
            "procurement teams. Hybrid in the Bengaluru office.",
        ),
        posting(
            "j2",
            title="Backend Developer",
            company="Shopify",
            description="Our monolith runs on Ruby on Rails with PostgreSQL, and you will "
            "own the checkout services. Bengaluru.",
        ),
        posting(
            "j3",
            title="Ruby on Rails Developer",
            company="Freshworks",
            description="Build billing services. Bengaluru.",
        ),
        posting(
            "j4",
            title="Ruby on Rails Developer",
            company="Zoho",
            description="A strong Java role in our Bengaluru office, building payment "
            "services on Spring Boot for enterprise customers.",
        ),
    )
    await process()
    await confirmed_context()
    prefs = {
        "titles": ["Backend Developer", "Ruby on Rails Developer"],
        "keywords": ["Rails", "PostgreSQL"],
        "core_keywords": ["Rails"],
        "keyword_min_matches": 2,
        "locations": [{"city": "Bengaluru", "country": "IN"}],
        "work_modes": ["hybrid", "onsite"],
    }
    assert (await client.put("/api/preferences", json=prefs)).status_code == 200

    async def feed(match):
        params = {"section": "link", "match": match}
        return (await client.get("/api/feed", params=params)).json()

    main = await feed("title")
    # SAP names no Core keyword; Zoho's title says Rails but its description does not.
    assert {c["company"]: [k["keyword"] for k in c["matched_keywords"]] for c in main["items"]} == {
        "Shopify": ["Rails", "PostgreSQL"]
    }
    review = await feed("review")
    # Freshworks' advert is too short to confirm anything: shown apart, not as a match.
    assert [(c["company"], c["match"]) for c in review["items"]] == [("Freshworks", "review")]
    assert main["counts"]["review_matches"] == 1

    # Without a Core keyword, titles alone decide again.
    prefs["core_keywords"] = []
    await client.put("/api/preferences", json=prefs)
    companies = {c["company"] for c in (await feed("title"))["items"]}
    assert companies == {"SAP", "Shopify", "Freshworks", "Zoho"}


async def test_a_title_only_rails_job_stays_under_review_even_with_extracted_skills(alice, db):
    _, client = alice
    await add(
        "linkedin",
        posting("t1", title="Ruby on Rails Developer", company="Freshworks", description=""),
    )
    await process()
    await db.execute(update(Job).values(required_skills=["Ruby on Rails"]))
    await db.commit()
    prefs = {
        "titles": ["Ruby on Rails Developer"],
        "keywords": ["Rails"],
        "core_keywords": ["Rails"],
        "keyword_min_matches": 1,
        "locations": [{"city": "Bengaluru", "country": "IN"}],
        "work_modes": ["hybrid", "onsite"],
    }
    await client.put("/api/preferences", json=prefs)
    params = {"section": "link", "match": "review"}
    [card] = (await client.get("/api/feed", params=params)).json()["items"]
    assert (card["company"], card["match"]) == ("Freshworks", "review")
    assert card["matched_keywords"] == []
    title = (await client.get("/api/feed", params={"section": "link"})).json()
    assert title["items"] == []


RAILS_CORE = {
    "titles": ["Backend Developer", "Ruby on Rails Developer"],
    "keywords": ["Rails"],
    "core_keywords": ["Rails"],
    "keyword_min_matches": 1,
    "locations": [{"city": "Bengaluru", "country": "IN"}],
    "work_modes": ["hybrid", "onsite"],
}
JAVA_ADVERT = "Java and Spring Boot services for our payments platform in Bengaluru. " * 20


async def test_long_adverts_without_a_core_keyword_are_never_read(alice, monkeypatch):
    """The database filters descriptions first (Neon transfer, COSTS.md); Python's
    whole-word checks still decide, so other spellings and capitals keep matching."""
    _, client = alice
    await add(
        "linkedin",
        posting("n1", title="Backend Developer", company="SAP", description=JAVA_ADVERT),
        posting(
            "n2",
            title="Backend Developer",
            company="Shopify",
            description="Our checkout runs on RoR and PostgreSQL. " + JAVA_ADVERT,
        ),
        posting(
            "n3",
            title="Backend Developer",
            company="Zoho",
            description="WE USE RUBY ON RAILS FOR BILLING. " + JAVA_ADVERT,
        ),
    )
    await process()
    await confirmed_context()
    read: list[str] = []
    real = feed_service.mentioned

    def spy(text, terms):
        read.append(text)
        return real(text, terms)

    monkeypatch.setattr(feed_service, "mentioned", spy)
    await client.put("/api/preferences", json=RAILS_CORE)
    items = (await client.get("/api/feed", params={"section": "link"})).json()["items"]
    assert {c["company"] for c in items} == {"Shopify", "Zoho"}
    assert JAVA_ADVERT not in read


async def test_a_short_advert_padded_with_whitespace_stays_under_review(alice, db):
    """PostgreSQL and Python trim different characters: the short advert is still read
    and still called too short to confirm a Core keyword."""
    _, client = alice
    await add(
        "linkedin",
        posting("p1", title="Ruby on Rails Developer", company="Freshworks", description="x"),
    )
    await process()
    padded = "Build billing services." + "\n" * 90 + " " * 10
    await db.execute(update(Posting).values(description=padded))
    await db.commit()
    await client.put("/api/preferences", json=RAILS_CORE)
    params = {"section": "link", "match": "review"}
    [card] = (await client.get("/api/feed", params=params)).json()["items"]
    assert (card["company"], card["match"]) == ("Freshworks", "review")


async def test_blocked_publisher_hidden_from_existing_feed_without_deleting_history(alice, db):
    from app.models.posting import Company

    _, client = alice
    await add("adzuna", posting("legacy", company="Previously allowed"))
    await process()
    await client.put("/api/preferences", json=BACKEND_BLR)
    before = (await client.get("/api/feed", params={"section": "link"})).json()
    [card] = before["items"]
    # Simulate an existing record imported before the publisher exclusion was deployed.
    await db.execute(
        update(Company)
        .where(Company.normalized_name == "previously allowed")
        .values(name="vmysmartpros", normalized_name="vmysmartpros")
    )
    await db.commit()
    after = (await client.get("/api/feed", params={"section": "link"})).json()
    assert after["items"] == []
    assert (await client.get(f"/api/jobs/{card['job_id']}")).status_code == 200
    assert await db.scalar(select(Posting.id).where(Posting.source_job_id == "legacy"))
    # Matching must not bring it back on the next preferences update either.
    await client.put("/api/preferences", json=BACKEND_BLR)
    assert (await client.get("/api/feed", params={"section": "link"})).json()["items"] == []


async def test_short_core_advert_matching_both_candidate_paths_stays_under_review(alice):
    _, client = alice
    await add(
        "linkedin",
        posting(
            "short-core",
            title="Ruby on Rails Developer",
            company="Acme",
            description="Ruby on Rails and PostgreSQL.",
        ),
    )
    await process()
    assert (await client.put("/api/preferences", json=RAILS_CORE)).status_code == 200
    response = await client.get("/api/feed", params={"section": "link", "match": "review"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["match"] == "review"
    assert body["counts"]["title_matches"] == 0


@pytest.mark.parametrize("cache_state", ["current", "missing", "stale"])
async def test_description_cache_and_legacy_fallback_give_identical_matches(alice, db, cache_state):
    _, client = alice
    await seed_keywords()
    if cache_state != "current":
        await db.execute(
            update(Posting).values(
                description_mentions_version=None if cache_state == "missing" else "old"
            )
        )
        await db.commit()
    await client.put("/api/preferences", json=RAILS_BLR)
    body = (await client.get("/api/feed", params={"section": "link", "match": "keywords"})).json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Software Engineer - Payments"
    assert {k["keyword"] for k in body["items"][0]["matched_keywords"]} == {"Rails", "PostgreSQL"}


async def test_known_keywords_rebuild_without_description_selects_or_ilike(alice):
    import re

    from sqlalchemy import event

    from app.core.db import get_engine

    user, client = alice
    await seed_keywords()
    assert (await client.put("/api/preferences", json=RAILS_BLR)).status_code == 200
    statements = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    engine = get_engine().sync_engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        async with get_sessionmaker()() as session:
            await feed_service.sync_user_feed(session, user.id)
            await session.rollback()
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert not any(re.search(r"\bpostings\.description\b", sql) for sql in statements)
    assert not any("ILIKE" in sql.upper() for sql in statements)


@pytest.mark.parametrize("unknown_core", [False, True])
async def test_cached_fallback_supports_unknown_core_and_non_core_keywords(alice, unknown_core):
    _, client = alice
    await add(
        "linkedin",
        posting(
            "unknown-keyword",
            title="Payments Engineer",
            description="Build our Rails application with Sidekiq workers and reliable payments. "
            * 4,
        ),
    )
    await process()
    await confirmed_context()
    prefs = RAILS_BLR | {
        "keywords": ["Rails", "Sidekiq"],
        "core_keywords": ["Sidekiq"] if unknown_core else ["Rails"],
        "keyword_min_matches": 2,
    }
    assert (await client.put("/api/preferences", json=prefs)).status_code == 200
    body = (await client.get("/api/feed", params={"section": "link", "match": "keywords"})).json()
    assert body["total"] == 1
    assert {k["keyword"] for k in body["items"][0]["matched_keywords"]} == {"Rails", "Sidekiq"}


@pytest.mark.parametrize("skills", [[], ["Python", "Django"]])
async def test_context_pending_is_reviewed_then_rejected_without_keyword_skill(alice, skills):
    _, client = alice
    app.dependency_overrides[get_gateway] = lambda: FailingSkills(
        Path(get_settings().gateway_recorded_dir)
    )
    await add(
        "linkedin",
        posting(
            "business-rails",
            work_mode="hybrid",
            title="Backend Developer",
            description=(
                "Build infrastructure with data, trust and rails to transact across borders. "
                "Our backend uses Python and Django. Own its APIs and deployment in Bengaluru."
            ),
        ),
    )
    await process()
    await client.put("/api/preferences", json=RAILS_CORE)

    async def items(match):
        return (await client.get("/api/feed", params={"section": "link", "match": match})).json()[
            "items"
        ]

    assert len(await items("review")) == 1
    assert await items("title") == []
    await confirmed_context(skills)
    await sync_all(client)
    assert len(await items("review")) == 1
    assert await items("title") == []


async def test_pending_different_title_is_visible_then_promoted_with_evidence(alice):
    _, client = alice
    app.dependency_overrides[get_gateway] = lambda: FailingSkills(
        Path(get_settings().gateway_recorded_dir)
    )
    await add(
        "linkedin",
        posting(
            "technical-rails",
            work_mode="hybrid",
            title="Payments Engineer",
            description=(
                "Build our rails API with PostgreSQL and Sidekiq workers. "
                "Own reliable deployments and production monitoring in Bengaluru."
            ),
        ),
    )
    await process()
    await client.put("/api/preferences", json=RAILS_BLR)
    params = {"section": "link", "match": "review"}
    assert len((await client.get("/api/feed", params=params)).json()["items"]) == 1
    await confirmed_context()
    await sync_all(client)
    [card] = (await client.get("/api/feed", params=params | {"match": "keywords"})).json()["items"]
    detail = (await client.get(f"/api/jobs/{card['job_id']}")).json()
    assert detail["keyword_evidence"]["Rails"] == (
        "Build our rails API with PostgreSQL and Sidekiq workers."
    )
    assert "keyword_evidence" not in card


@pytest.mark.parametrize("spelling", ["ruby", "Ruby", "RUBY", "Ruby on Rails", "ruby on rails"])
@pytest.mark.parametrize("cache", ["current", "stale", "missing"])
async def test_rails_preference_matches_ruby_without_ai(alice, db, spelling, cache):
    _, client = alice
    app.dependency_overrides[get_gateway] = lambda: FailingSkills(
        Path(get_settings().gateway_recorded_dir)
    )
    await add(
        "linkedin",
        posting(
            "ruby-only",
            title="Backend Developer",
            work_mode="hybrid",
            description=(
                f"Build APIs using {spelling} and PostgreSQL. "
                + "Own reliable production services in Bengaluru. " * 4
            ),
        ),
    )
    await process()
    if cache != "current":
        await db.execute(
            update(Posting).values(description_mentions_version="old" if cache == "stale" else None)
        )
        await db.commit()
    prefs = RAILS_CORE | {"keywords": ["Ruby on Rails"], "core_keywords": ["Ruby on Rails"]}
    await client.put("/api/preferences", json=prefs)
    body = (await client.get("/api/feed", params={"section": "link"})).json()
    assert body["total"] == 1
    assert body["items"][0]["matched_keywords"][0]["keyword"] == "Ruby on Rails"
    assert body["counts"]["review_matches"] == 0


async def test_capitalised_business_rails_stays_reviewed_not_confirmed(alice):
    _, client = alice
    await add(
        "linkedin",
        posting(
            "payment-rails",
            title="Backend Developer",
            work_mode="hybrid",
            description=(
                "Payment Rails connect our suppliers with customers across borders. "
                "Build the Python and Django backend in Bengaluru and operate its APIs."
            ),
        ),
    )
    await process()
    await confirmed_context(["Python", "Django"])
    await client.put("/api/preferences", json=RAILS_CORE)
    body = (await client.get("/api/feed", params={"section": "link"})).json()
    assert body["items"] == []
    assert body["counts"]["review_matches"] == 1
