"""Stage 2 of the Application Extension (ADR-0017): the reviewed application profile, Saved
Answers within their scope, and choosing the exact Draft version from the extension."""

import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.models import Job
from app.services.extension_drafts import apply_link_matches
from app.services.saved_answers import question_key
from tests.api.test_drafts import generated, prepared  # noqa: F401
from tests.api.test_extension import EXT, OTHER_EXT, ext_client
from tests.api.test_extension import connect as ext_connect


@pytest.fixture(autouse=True)
def _allowed_extension(monkeypatch) -> None:
    monkeypatch.setenv("EXTENSION_IDS", f"{EXT},{OTHER_EXT}")
    get_settings.cache_clear()


async def add_fact(client, kind: str, group: str, text: str) -> str:
    response = await client.post("/api/facts", json={"kind": kind, "group": group, "text": text})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


async def save_profile(client, content: dict, expected: int = 0):
    return await client.put("/api/profile", json={"content": content, "expected_version": expected})


# Profile


async def test_suggestion_copies_contact_and_roles_from_facts_without_saving(alice):
    user, client = alice
    phone = await add_fact(client, "link", "Contact", "+91 98765 43210")
    linkedin = await add_fact(client, "link", "Contact", "linkedin.com/in/asha-dev")
    role = await add_fact(
        client, "experience", "Acme Corp", "Senior Software Developer, March 2023 to Present"
    )
    school = await add_fact(
        client, "education", "IIT Bombay", "B.Tech Computer Science, 2015 - 2019"
    )

    suggestion = (await client.get("/api/profile/suggestion")).json()
    assert suggestion["email"] == user.email
    assert suggestion["phone"] == "+91 98765 43210"
    assert suggestion["phone_fact_id"] == phone
    assert suggestion["links"] == [
        {"label": "linkedin", "url": "https://linkedin.com/in/asha-dev", "fact_id": linkedin}
    ]
    assert suggestion["employment"] == [
        {
            "employer": "Acme Corp",
            "title": "Senior Software Developer",
            "location": "",
            "start": "2023-03",
            "end": None,
            "current": True,
            "fact_ids": [role],
        }
    ]
    assert suggestion["education"][0] | {"fact_ids": None} == {
        "school": "IIT Bombay",
        "degree": "B.Tech Computer Science",
        "field": "",
        "start": "2015",
        "end": "2019",
        "fact_ids": None,
    }
    assert suggestion["education"][0]["fact_ids"] == [school]

    await add_fact(client, "education", "State University", "B.Tech in Computer Science, 2020")
    later = (await client.get("/api/profile/suggestion")).json()["education"][1]
    assert (later["degree"], later["start"], later["end"]) == (
        "B.Tech in Computer Science",
        None,
        "2020",
    )
    assert (await client.get("/api/profile")).json()["content"] is None


async def test_saving_is_the_review_and_needs_the_current_version(alice):
    _, client = alice
    content = {"first_name": "Asha", "email": "asha@example.com", "city": "Bengaluru"}
    first = await save_profile(client, content)
    assert first.status_code == 200
    assert first.json()["version"] == 1
    stale_tab = await save_profile(client, content | {"city": "Pune"}, expected=0)
    assert stale_tab.status_code == 409
    second = await save_profile(client, content | {"city": "Pune"}, expected=1)
    assert second.json()["version"] == 2
    assert (await client.get("/api/profile")).json()["content"]["city"] == "Pune"


async def test_a_profile_cannot_cite_another_users_facts(alice, bob):
    _, a = alice
    _, b = bob
    bobs_fact = await add_fact(b, "experience", "Bob Inc", "Engineer, 2020 - 2022")
    entry = {"employer": "Bob Inc", "fact_ids": [bobs_fact]}
    response = await save_profile(a, {"employment": [entry]})
    assert response.status_code == 422


async def test_entries_whose_facts_change_need_review_and_are_withheld(alice, db):
    _, client = alice
    phone = await add_fact(client, "link", "Contact", "+91 98765 43210")
    role = await add_fact(client, "experience", "Acme Corp", "Developer, 2021 - 2023")
    other = await add_fact(client, "experience", "Beta Ltd", "Engineer, 2019 - 2021")
    content = {
        "first_name": "Asha",
        "phone": "+91 98765 43210",
        "phone_fact_id": phone,
        "employment": [
            {"employer": "Acme Corp", "fact_ids": [role]},
            {"employer": "Beta Ltd", "fact_ids": [other]},
        ],
    }
    assert (await save_profile(client, content)).status_code == 200
    token = await ext_connect(client)
    async with ext_client(token=token) as ext:
        fresh = (await ext.get("/api/ext/profile")).json()
    assert fresh["needs_review"] is False
    assert len(fresh["content"]["employment"]) == 2

    # Reordering or toggling a Fact is not a change; rewording it is.
    toggled = await client.patch(f"/api/facts/{other}", json={"in_base_resume": True})
    assert toggled.status_code == 200, toggled.text
    edited = await client.patch(f"/api/facts/{role}", json={"text": "Lead Developer, 2021 - 2023"})
    assert edited.status_code == 200, edited.text
    assert (await client.delete(f"/api/facts/{phone}")).status_code in (200, 204)

    assert (await client.get("/api/profile")).json()["stale"] == ["phone", "employment.0"]
    async with ext_client(token=token) as ext:
        withheld = (await ext.get("/api/ext/profile")).json()
    assert withheld["needs_review"] is True
    assert withheld["content"]["phone"] == ""
    assert [e["employer"] for e in withheld["content"]["employment"]] == ["Beta Ltd"]


async def test_the_extension_sees_no_profile_before_the_first_review(alice):
    _, client = alice
    token = await ext_connect(client)
    async with ext_client(token=token) as ext:
        body = (await ext.get("/api/ext/profile")).json()
    assert body == {"reviewed": False, "version": 0, "needs_review": True, "content": None}


async def test_profiles_are_per_user(alice, bob):
    _, a = alice
    _, b = bob
    await save_profile(a, {"first_name": "Asha"})
    assert (await b.get("/api/profile")).json()["content"] is None
    token = await ext_connect(b)
    async with ext_client(token=token) as ext:
        assert (await ext.get("/api/ext/profile")).json()["reviewed"] is False


# Saved Answers


def test_question_keys_ignore_case_punctuation_and_required_marks():
    assert question_key("What is your notice period? *") == question_key(
        "what is your NOTICE period (required)"
    )


async def test_scope_rules_and_duplicates(alice, db):
    _, client = alice
    general = {"question": "Notice period?", "answer": "30 days", "sensitive": True}
    assert (await client.post("/api/saved-answers", json=general)).status_code == 201
    duplicate = await client.post("/api/saved-answers", json=general | {"answer": "60 days"})
    assert duplicate.status_code == 409

    no_country = {"question": "Expected salary?", "answer": "30 LPA", "scope": "country"}
    assert (await client.post("/api/saved-answers", json=no_country)).status_code == 422
    half_salary = no_country | {"country": "IN", "currency": "INR"}
    assert (await client.post("/api/saved-answers", json=half_salary)).status_code == 422
    salary = half_salary | {"period": "year"}
    assert (await client.post("/api/saved-answers", json=salary)).status_code == 201
    # The same question for another country is a separate answer.
    abroad = salary | {"country": "DE", "currency": "EUR", "answer": "70,000"}
    assert (await client.post("/api/saved-answers", json=abroad)).status_code == 201

    no_company = {"question": "Why this company?", "answer": "...", "scope": "company"}
    assert (await client.post("/api/saved-answers", json=no_company)).status_code == 422


async def test_only_answers_in_scope_reach_the_extension_for_a_job(prepared, db):  # noqa: F811
    _, client, job_id, _ = prepared
    job = await db.get(Job, job_id)
    other_company = (
        await db.scalars(select(Job.company_id).where(Job.company_id != job.company_id))
    ).first()
    await client.post(
        "/api/saved-answers", json={"question": "Notice period?", "answer": "30 days"}
    )
    for country, answer in (("IN", "30 LPA"), ("DE", "70,000 EUR")):
        await client.post(
            "/api/saved-answers",
            json={
                "question": "Expected salary?",
                "answer": answer,
                "scope": "country",
                "country": country,
            },
        )
    mine = {"question": "Why us?", "answer": "Billing at scale", "scope": "company"}
    assert (
        await client.post("/api/saved-answers", json=mine | {"company_id": str(job.company_id)})
    ).status_code == 201
    if other_company:
        theirs = mine | {"company_id": str(other_company), "answer": "Something else"}
        assert (await client.post("/api/saved-answers", json=theirs)).status_code == 201

    token = await ext_connect(client)
    async with ext_client(token=token) as ext:
        answers = (await ext.get("/api/ext/saved-answers", params={"job_id": job_id})).json()
    assert sorted(a["answer"] for a in answers) == ["30 LPA", "30 days", "Billing at scale"]


async def test_saved_answers_are_per_user_and_jobs_must_be_linked(prepared, bob, db):  # noqa: F811
    _, client, job_id, _ = prepared
    _, b = bob
    created = await client.post("/api/saved-answers", json={"question": "Q?", "answer": "A"})
    answer_id = created.json()["id"]
    assert (await b.get("/api/saved-answers")).json() == []
    assert (await b.delete(f"/api/saved-answers/{answer_id}")).status_code == 404
    edit = {"question": "Q?", "answer": "B"}
    assert (await b.put(f"/api/saved-answers/{answer_id}", json=edit)).status_code == 404

    token = await ext_connect(b)
    async with ext_client(token=token) as ext:
        # Bob has no link to Alice's Feed Job.
        refused = await ext.get("/api/ext/saved-answers", params={"job_id": job_id})
    assert refused.status_code == 404


# Draft selection


@pytest.mark.parametrize(
    ("page", "stored", "expected"),
    [
        ("https://jobs.lever.co/acme/123e4567", "https://jobs.lever.co/acme/123e4567", True),
        ("https://jobs.lever.co/acme/123e4567/apply", "https://jobs.lever.co/acme/123e4567", True),
        ("https://www.acme.com/jobs/42/?utm_source=x", "https://acme.com/jobs/42", True),
        (
            "https://job-boards.greenhouse.io/acme/jobs/4012345",
            "https://boards.greenhouse.io/acme/jobs/4012345",
            True,
        ),
        (
            "https://acme.com/careers?gh_jid=4012345",
            "https://acme.com/careers?gh_jid=4012345",
            True,
        ),
        (
            "https://acme.com/careers?gh_jid=999999",
            "https://acme.com/careers?gh_jid=4012345",
            False,
        ),
        ("https://acme.com/jobs/420", "https://acme.com/jobs/42", False),
        ("https://acme.com/", "https://acme.com/jobs/42", False),
        ("https://evil.com/jobs/42", "https://acme.com/jobs/42", False),
        ("javascript:alert(1)", "https://acme.com/jobs/42", False),
        ("https://acme.com/jobs/42", None, False),
    ],
)
def test_apply_link_matching(page, stored, expected):
    assert apply_link_matches(page, stored) is expected


async def test_the_extension_lists_matches_and_the_exact_version(prepared, db):  # noqa: F811
    user, client, job_id, _ = prepared
    draft = await generated(prepared)
    await db.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(apply_url="https://jobs.lever.co/acme/abc12345-0000-0000-0000-000000000000")
    )
    await db.commit()
    token = await ext_connect(client)
    async with ext_client(token=token) as ext:
        recent = (await ext.get("/api/ext/drafts")).json()
        assert [d["draft_id"] for d in recent] == [draft["id"]]
        page = "https://jobs.lever.co/acme/abc12345-0000-0000-0000-000000000000/apply"
        matched = (await ext.get("/api/ext/drafts/match", params={"url": page})).json()
        assert [d["draft_id"] for d in matched["drafts"]] == [draft["id"]]
        nothing = (
            await ext.get("/api/ext/drafts/match", params={"url": "https://other.example/x"})
        ).json()
        assert nothing["drafts"] == []

        detail = (await ext.get(f"/api/ext/drafts/{draft['id']}")).json()
        assert detail["number"] == detail["current_version"] == draft["current_version"]
        assert detail["resume_file"] == draft["attachment_name"]
        assert detail["background_answer"]
        assert all(
            line["text"] in detail["background_answer"]
            for line in draft["version"]["content"]["cover_letter"]
            if not line["text"].lower().startswith("dear")
        )
        assert detail["cover_letter_file"].endswith("_Cover_Letter.pdf")
        assert detail["warnings"] == len(draft["version"]["warnings"])

        pdf = await ext.get(
            f"/api/ext/drafts/{draft['id']}/pdf", params={"number": detail["number"]}
        )
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF")
        assert "Cache-Control" in pdf.headers
        missing = await ext.get(f"/api/ext/drafts/{draft['id']}/pdf")
        assert missing.status_code == 422  # a version number is always required
        unknown = await ext.get(f"/api/ext/drafts/{draft['id']}", params={"number": 99})
        assert unknown.status_code == 404


async def test_a_newer_version_does_not_change_the_chosen_one(prepared):  # noqa: F811
    _, client, _, _ = prepared
    draft = await generated(prepared)
    first = draft["current_version"]
    content = draft["version"]["content"]
    content["resume"][0]["text"] = content["resume"][0]["text"] + " "
    saved = await client.put(
        f"/api/drafts/{draft['id']}", json={"content": content, "expected_version": first}
    )
    assert saved.status_code == 200, saved.text
    token = await ext_connect(client)
    async with ext_client(token=token) as ext:
        chosen = (await ext.get(f"/api/ext/drafts/{draft['id']}", params={"number": first})).json()
        latest = (await ext.get(f"/api/ext/drafts/{draft['id']}")).json()
    assert chosen["number"] == first
    assert latest["number"] == latest["current_version"] == first + 1


async def test_other_users_drafts_are_invisible_to_the_extension(prepared, bob):  # noqa: F811
    _, client, _, _ = prepared
    draft = await generated(prepared)
    _, b = bob
    token = await ext_connect(b)
    async with ext_client(token=token) as ext:
        assert (await ext.get("/api/ext/drafts")).json() == []
        assert (await ext.get(f"/api/ext/drafts/{draft['id']}")).status_code == 404
        pdf = await ext.get(f"/api/ext/drafts/{draft['id']}/pdf", params={"number": 1})
        assert pdf.status_code == 404


async def test_extension_routes_need_the_credential(anon, alice):
    _, client = alice
    for path in ("/api/ext/profile", "/api/ext/drafts", "/api/ext/drafts/match?url=https://a.b/c"):
        assert (await client.get(path)).status_code == 401
        assert (await anon.get(path)).status_code == 401


async def test_saving_again_lets_go_of_a_deleted_fact_and_uses_the_entry(alice):
    _, client = alice
    phone = await add_fact(client, "link", "Contact", "+91 98765 43210")
    role = await add_fact(client, "experience", "Acme Corp", "Developer, 2021 - 2023")
    content = {
        "phone": "+91 98765 43210",
        "phone_fact_id": phone,
        "employment": [{"employer": "Acme Corp", "title": "Developer", "fact_ids": [role]}],
    }
    assert (await save_profile(client, content)).status_code == 200
    for fact in (phone, role):
        assert (await client.delete(f"/api/facts/{fact}")).status_code == 204
    assert (await client.get("/api/profile")).json()["stale"] == ["phone", "employment.0"]

    # The editor still holds the deleted IDs; saving is the User's review of the values.
    resaved = await save_profile(client, content | {"phone": "+91 90000 00000"}, expected=1)
    assert resaved.status_code == 200, resaved.text
    body = (await client.get("/api/profile")).json()
    assert body["stale"] == []
    assert body["content"]["phone_fact_id"] is None
    assert body["content"]["employment"][0]["fact_ids"] == []
    token = await ext_connect(client)
    async with ext_client(token=token) as ext:
        used = (await ext.get("/api/ext/profile")).json()
    assert used["needs_review"] is False
    assert used["content"]["phone"] == "+91 90000 00000"
    assert [e["employer"] for e in used["content"]["employment"]] == ["Acme Corp"]


async def test_simultaneous_saves_of_one_version_conflict(alice, monkeypatch):
    import asyncio

    from app.services import application_profile

    _, client = alice
    assert (await save_profile(client, {"city": "Pune"})).status_code == 200
    # Hold the first save after its version check, long enough for the second to read the
    # same version; without a lock both would succeed and one edit would be lost.
    facts = application_profile._facts
    calls = 0

    async def slow_first(session, user):
        nonlocal calls
        calls += 1
        if calls == 1:
            await asyncio.sleep(0.3)
        return await facts(session, user)

    monkeypatch.setattr(application_profile, "_facts", slow_first)
    first = asyncio.create_task(save_profile(client, {"city": "Mumbai"}, expected=1))
    await asyncio.sleep(0.05)
    second = await save_profile(client, {"city": "Chennai"}, expected=1)
    results = [await first, second]
    assert [r.status_code for r in results] == [200, 409]
    current = (await client.get("/api/profile")).json()
    assert current["version"] == 2
    assert current["content"]["city"] == "Mumbai"


async def test_simultaneous_first_saves_conflict(alice):
    import asyncio

    _, client = alice
    results = await asyncio.gather(
        save_profile(client, {"city": "Mumbai"}),
        save_profile(client, {"city": "Chennai"}),
    )
    assert sorted(r.status_code for r in results) == [200, 409]
    assert (await client.get("/api/profile")).json()["version"] == 1
