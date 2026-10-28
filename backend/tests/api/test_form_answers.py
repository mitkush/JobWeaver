"""Answers to application-form questions and the Writing Style (ADR-0017, stage 7)."""

import json

import pytest
from sqlalchemy import update

from app.core.config import get_settings
from app.core.errors import GatewayError
from app.models import Document, User
from app.models.document import DocumentKind
from app.services.form_answers import fit
from app.services.writing_style import redact
from tests.api.test_drafts import prepared  # noqa: F401
from tests.api.test_extension import EXT, connect, ext_client

QUESTIONS = [
    {"ref": "q1", "question": "Why do you want to join us?"},
    {"ref": "q2", "question": "Describe your infrastructure experience"},
    {"ref": "q3", "question": "What will you bring to this role?"},
]


@pytest.fixture(autouse=True)
def allow_extension(monkeypatch):
    monkeypatch.setenv("EXTENSION_IDS", EXT)
    get_settings.cache_clear()


async def ask(client, job_id, questions=QUESTIONS, no_ai=False):
    token = await connect(client)
    async with ext_client(token=token) as ext:
        return await ext.post(
            "/api/ext/answers", json={"job_id": job_id, "questions": questions, "no_ai": no_ai}
        )


async def test_suggestions_must_pass_the_fact_checks(prepared):  # noqa: F811
    _, client, job_id, _ = prepared
    response = await ask(client, job_id)
    assert response.status_code == 200, response.text
    by_ref = {a["ref"]: a for a in response.json()}
    # Backed by the cited Fact: kept as a full Suggestion.
    assert by_ref["q1"]["kind"] == "suggestion"
    assert "40 merchant teams" in by_ref["q1"]["text"] and by_ref["q1"]["fact_refs"] == ["F4"]
    # Names a tool that is not in the Fact Bank: never offered as prose.
    assert by_ref["q2"]["kind"] == "fact_notes"
    assert "Kubernetes" not in json.dumps(by_ref["q2"])
    assert by_ref["q2"]["notes"]
    # Stock phrasing is flagged for the User to rework.
    assert by_ref["q3"]["kind"] == "suggestion"
    assert "stock phrasing" in by_ref["q3"]["warning"]


async def test_forms_that_refuse_ai_get_fact_notes_and_no_provider_call(prepared):  # noqa: F811
    _, client, job_id, gateway = prepared

    async def must_not_run(_request):
        raise AssertionError("no AI call for a form that refuses AI answers")

    gateway.answer_questions = must_not_run
    response = await ask(client, job_id, no_ai=True)
    assert response.status_code == 200
    assert {a["kind"] for a in response.json()} == {"fact_notes"}
    assert all("not written by AI" in a["warning"] for a in response.json())


async def test_sensitive_questions_only_use_saved_answers(prepared):  # noqa: F811
    _, client, job_id, gateway = prepared
    questions = [
        {"ref": "s1", "question": "What is your notice period?"},
        {"ref": "s2", "question": "Will you require visa sponsorship?"},
    ]
    saved = await client.post(
        "/api/saved-answers",
        json={"question": "What is your notice period?", "answer": "30 days", "sensitive": True},
    )
    assert saved.status_code == 201

    async def must_not_run(_request):
        raise AssertionError("sensitive questions never reach the AI")

    gateway.answer_questions = must_not_run
    by_ref = {a["ref"]: a for a in (await ask(client, job_id, questions)).json()}
    assert (by_ref["s1"]["kind"], by_ref["s1"]["text"]) == ("saved", "30 days")
    assert by_ref["s2"]["kind"] == "none" and by_ref["s2"]["text"] == ""


async def test_a_company_answer_is_used_only_for_that_company(prepared, db):  # noqa: F811
    from app.models import Company, Job

    _, client, job_id, gateway = prepared
    job = await db.get(Job, job_id)
    other = Company(name="Globex", normalized_name="globex-test")
    db.add(other)
    await db.commit()
    question = "Why do you want to join us?"
    await client.post(
        "/api/saved-answers",
        json={
            "question": question,
            "answer": "For Globex only",
            "scope": "company",
            "company_id": str(other.id),
        },
    )
    await client.post(
        "/api/saved-answers",
        json={
            "question": question,
            "answer": "Mine for this company",
            "scope": "company",
            "company_id": str(job.company_id),
        },
    )
    [answer] = (await ask(client, job_id, [{"ref": "q1", "question": question}])).json()
    assert (answer["kind"], answer["text"]) == ("saved", "Mine for this company")


async def test_suggestions_fit_the_field_or_become_notes(prepared):  # noqa: F811
    assert fit("First sentence. Second one is longer.", 20) == "First sentence."
    assert fit("One very long sentence without a stop", 10) is None
    _, client, job_id, _ = prepared
    tight = [{"ref": "q1", "question": "Why do you want to join us?", "max_chars": 12}]
    [answer] = (await ask(client, job_id, tight)).json()
    assert answer["kind"] == "fact_notes"


async def test_ai_answers_need_the_notice_and_an_unavailable_ai_degrades_to_notes(prepared, db):  # noqa: F811
    user, client, job_id, gateway = prepared

    async def unavailable(_request):
        raise GatewayError("busy")

    gateway.answer_questions = unavailable
    answers = (await ask(client, job_id)).json()
    assert {a["kind"] for a in answers} == {"fact_notes"}
    assert "unavailable" in answers[0]["warning"]

    await db.execute(update(User).where(User.id == user.id).values(ai_notice_accepted_at=None))
    await db.commit()
    assert (await ask(client, job_id)).status_code == 409


async def test_answers_are_scoped_to_the_users_own_jobs(prepared, bob):  # noqa: F811
    _, _, job_id, _ = prepared
    _, other = bob
    assert (await ask(other, job_id)).status_code == 404
    _, client, _, _ = prepared
    cookie_only = await client.post(
        "/api/ext/answers", json={"job_id": job_id, "questions": QUESTIONS}
    )
    assert cookie_only.status_code == 401


async def test_saving_a_reviewed_answer_from_the_extension(prepared, db):  # noqa: F811
    from app.models import Job

    _, client, job_id, _ = prepared
    job = await db.get(Job, job_id)
    token = await connect(client)
    async with ext_client(token=token) as ext:
        saved = await ext.post(
            "/api/ext/saved-answers",
            json={
                "job_id": job_id,
                "question": "Why us?",
                "answer": "My reworked answer",
                "origin": "suggestion",
            },
        )
    assert saved.status_code == 201, saved.text
    body = saved.json()
    assert (body["scope"], body["company_id"], body["origin"]) == (
        "company",
        str(job.company_id),
        "suggestion",
    )
    async with ext_client(token=token) as ext:
        notice = await ext.post(
            "/api/ext/saved-answers",
            json={
                "job_id": job_id,
                "question": "What is your notice period?",
                "answer": "30 days",
                "scope": "general",
            },
        )
    assert notice.json()["sensitive"] is True


# Writing Style


def test_redaction_removes_names_numbers_dates_and_tools():
    text = redact(
        "At Acme Corp I cut report time from 10 minutes to 30 seconds using Kafka in March 2024.",
        {"Acme Corp"},
    )
    for gone in ("Acme", "10", "30", "Kafka", "2024"):
        assert gone not in text
    assert "[NAME]" in text and "[NUMBER]" in text and "[TECH]" in text


async def test_writing_style_is_built_from_own_text_and_carries_no_claims(prepared, db):  # noqa: F811
    user, client, _, _ = prepared
    assert (await client.post("/api/me/writing-style/rebuild")).status_code == 409  # no samples yet
    db.add(
        Document(
            user_id=user.id,
            kind=DocumentKind.SUMMARY,
            filename="summary.txt",
            content_type="text/plain",
            size_bytes=0,
            content=b"",
            extracted_text="I like owning a problem end to end and writing down what I learned.",
        )
    )
    await db.commit()
    built = await client.post("/api/me/writing-style/rebuild")
    assert built.status_code == 200, built.text
    style = built.json()
    assert "Short, direct sentences" in style["traits"]
    joined = " ".join(style["excerpts"])
    for claim in ("Acme", "10 minutes", "Kafka", "Ledger Sync"):
        assert claim not in joined
    assert any("[NUMBER]" in e for e in style["excerpts"])

    edited = await client.put(
        "/api/me/writing-style",
        json={
            "traits": ["Plain words"],
            "excerpts": [
                "I shipped releases for the team at Acme Corp.",
                "Kafka at Acme Corp, 2024.",
            ],
        },
    )
    # The User's own edit is redacted too, and an excerpt that was mostly claims is dropped.
    assert edited.json()["excerpts"] == ["I shipped releases for the team at [NAME]."]
    assert (await client.delete("/api/me/writing-style")).status_code == 204
    assert (await client.get("/api/me/writing-style")).json()["traits"] == []
