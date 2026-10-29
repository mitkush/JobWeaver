"""Draft API coverage uses recorded AI, mocked DNS and a fake Gmail client."""

import base64
import copy
import io
import uuid
from datetime import UTC, datetime, timedelta
from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest
from pypdf import PdfReader
from sqlalchemy import select, update

from app.adapters.gmail import get_gmail_client
from app.api.deps import get_gateway
from app.core.config import get_settings
from app.core.errors import ExternalServiceError, GatewayError, ValidationFailedError
from app.core.security import encrypt
from app.gateway.recorded import RecordedAIGateway
from app.main import app
from app.models import (
    Application,
    Draft,
    DraftVersion,
    Fact,
    GmailHandoff,
    Job,
    OAuthCredential,
    Posting,
)
from app.models.fact import FactKind, FactOrigin
from app.schemas.drafts import EmailCheck
from app.services import drafting
from app.services.correspondence import merge_jobs, source_priorities
from app.services.google_oauth import get_google_client
from app.tailoring.content import DraftLine
from tests.api.test_feed import BACKEND_BLR, seed
from tests.conftest import onboard


@pytest.fixture
async def prepared(alice):
    user, client = alice
    gateway = RecordedAIGateway(Path(get_settings().gateway_recorded_dir))
    app.dependency_overrides[get_gateway] = lambda: gateway
    await onboard(client)
    result = await client.post(
        "/api/documents/text",
        json={
            "kind": "resume",
            "text": "Python PostgreSQL billing API used by 40 merchant teams",
        },
    )
    assert result.status_code == 200
    assert (await client.post("/api/fact-bank/review")).status_code == 204
    await client.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    job_id = (await client.get("/api/feed")).json()["items"][0]["job_id"]
    return user, client, job_id, gateway


async def generated(prepared):
    _, client, job_id, _ = prepared
    created = await client.post("/api/drafts", json={"job_id": job_id})
    assert created.status_code == 202
    draft_id = created.json()["id"]
    result = (await client.get(f"/api/drafts/{draft_id}")).json()
    assert result["state"] == "ready", result
    return result


@pytest.fixture
def recipient_check(monkeypatch):
    async def check(recipient):
        return EmailCheck(recipient=recipient, valid=True, warnings=[])

    monkeypatch.setattr(drafting, "check_recipient", check)


class GoodGoogle:
    async def refresh_access_token(self, token):
        assert token == "refresh-token"
        return "access-token"


class FakeGmail:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    async def create_draft(self, token, raw):
        self.calls.append((token, raw))
        if self.fail:
            raise ExternalServiceError("offline")
        return "gmail-draft-123"


async def connect(db, user):
    db.add(
        OAuthCredential(
            user_id=user.id,
            provider="gmail",
            refresh_token_encrypted=encrypt("refresh-token"),
            scopes="https://www.googleapis.com/auth/gmail.compose",
            granted_at=datetime.now(UTC),
        )
    )
    await db.commit()


async def test_generation_removes_fabrication_and_retains_trace(prepared):
    draft = await generated(prepared)
    version = draft["version"]
    assert draft["current_version"] == 1
    assert len(version["warnings"]) == 2
    assert all(line["fact_refs"] for line in version["content"]["resume"])
    text = " ".join(line["text"] for line in version["content"]["resume"])
    assert "Kubernetes" not in text and "million" not in text
    assert "ledger" in text
    assert draft["attachment_name"].endswith(".pdf")


@pytest.mark.parametrize("missing", ["notice", "review", "country"])
async def test_generation_requires_notice_country_and_review(prepared, db, missing):
    user, client, job_id, _ = prepared
    if missing == "notice":
        user.ai_notice_accepted_at = None
    elif missing == "review":
        user.fact_bank_reviewed_at = None
    else:
        user.country = None
    await db.commit()
    assert (await client.post("/api/drafts", json={"job_id": job_id})).status_code == 409


async def test_generation_blocks_region_before_provider(prepared, db):
    user, client, job_id, _ = prepared
    user.country = "GB"
    await db.commit()
    assert (await client.post("/api/drafts", json={"job_id": job_id})).status_code == 409


async def test_unknown_and_other_users_jobs_cannot_create_drafts(prepared, bob):
    _, client, job_id, _ = prepared
    _, other = bob
    await onboard(other)
    await other.post(
        "/api/documents/text",
        json={
            "kind": "resume",
            "text": "Python billing API experience from my resume",
        },
    )
    await other.post("/api/fact-bank/review")
    assert (await other.post("/api/drafts", json={"job_id": job_id})).status_code == 404
    assert (await client.post("/api/drafts", json={"job_id": str(uuid.uuid4())})).status_code == 404


async def test_closed_job_is_refused(prepared, db):
    _, client, job_id, _ = prepared
    job = await db.get(Job, uuid.UUID(job_id))
    job.expired_at = datetime.now(UTC)
    await db.commit()
    assert (await client.post("/api/drafts", json={"job_id": job_id})).status_code == 409


async def test_manual_save_and_conflict(prepared):
    draft = await generated(prepared)
    _, client, _, _ = prepared
    content = copy.deepcopy(draft["version"]["content"])
    content["resume"][1]["text"] = "Developed the billing API used by 40 merchant teams"
    saved = await client.put(
        f"/api/drafts/{draft['id']}",
        json={
            "expected_version": 1,
            "content": content,
        },
    )
    assert saved.status_code == 200
    assert saved.json()["version"]["content"]["resume"][1]["manual"] is True
    assert saved.json()["current_version"] == 2
    assert (
        await client.put(
            f"/api/drafts/{draft['id']}",
            json={
                "expected_version": 1,
                "content": content,
            },
        )
    ).status_code == 409


async def test_manual_edits_naming_missing_skills_are_kept_and_flagged(prepared):
    # FR-E6: the User's own words are never refused or deleted; ADR-0005: they are flagged.
    draft = await generated(prepared)
    _, client, _, _ = prepared
    content = copy.deepcopy(draft["version"]["content"])
    content["resume"][0]["text"] = "Python and Kubernetes"
    result = await client.put(
        f"/api/drafts/{draft['id']}",
        json={
            "expected_version": 1,
            "content": content,
        },
    )
    assert result.status_code == 200
    version = result.json()["version"]
    assert version["number"] == 2
    assert version["content"]["resume"][0]["text"] == "Python and Kubernetes"
    assert version["content"]["resume"][0]["manual"] is True
    assert any(
        w.startswith("Your edit in the resume") and "Kubernetes" in w for w in version["warnings"]
    )


async def test_recheck_uses_current_fact_bank_without_replacing_manual_edits(prepared, db):
    draft = await generated(prepared)
    user, client, _, _ = prepared
    content = copy.deepcopy(draft["version"]["content"])
    content["resume"][0]["text"] = "Python and Kubernetes"
    saved = (
        await client.put(
            f"/api/drafts/{draft['id']}",
            json={"expected_version": 1, "content": content},
        )
    ).json()
    assert any("Kubernetes" in warning for warning in saved["version"]["warnings"])
    db.add(
        Fact(
            user_id=user.id,
            kind=FactKind.SKILL,
            group="",
            text="Kubernetes",
            origin=FactOrigin.USER,
            in_base_resume=False,
        )
    )
    await db.commit()

    response = await client.post(f"/api/drafts/{draft['id']}/recheck", json={"expected_version": 2})
    assert response.status_code == 200
    result = response.json()["version"]
    assert result["number"] == 3 and result["source"] == "recheck"
    assert result["warnings"] == []
    assert result["content"]["resume"][0]["text"] == "Python and Kubernetes"
    assert result["content"]["resume"][0]["manual"] is True
    assert any(fact["text"] == "Kubernetes" for fact in result["facts"])
    assert (
        await client.post(f"/api/drafts/{draft['id']}/recheck", json={"expected_version": 2})
    ).status_code == 409


async def test_manual_rewording_is_saved_without_warnings(prepared):
    draft = await generated(prepared)
    _, client, _, _ = prepared
    content = copy.deepcopy(draft["version"]["content"])
    line = next(entry for entry in content["resume"] if "merchant" in entry["text"])
    line["text"] = "Designed a billing API serving 40 merchant teams"
    result = await client.put(
        f"/api/drafts/{draft['id']}", json={"expected_version": 1, "content": content}
    )
    assert result.status_code == 200
    assert result.json()["version"]["warnings"] == []


async def test_chat_keeps_manual_line_at_original_position_and_can_restore(prepared):
    draft = await generated(prepared)
    _, client, _, _ = prepared
    content = copy.deepcopy(draft["version"]["content"])
    content["resume"][1]["text"] = "Developed the billing API used by 40 merchant teams"
    await client.put(f"/api/drafts/{draft['id']}", json={"expected_version": 1, "content": content})
    revised = await client.post(
        f"/api/drafts/{draft['id']}/chat",
        json={
            "expected_version": 2,
            "message": "Lead with my portfolio project",
        },
    )
    assert revised.status_code == 200
    resume = revised.json()["version"]["content"]["resume"]
    assert resume[1]["text"] == content["resume"][1]["text"]
    assert resume[1]["manual"] is True
    restored = await client.post(
        f"/api/drafts/{draft['id']}/restore",
        json={
            "expected_version": 3,
            "number": 1,
        },
    )
    assert restored.json()["current_version"] == 4
    assert restored.json()["version"]["content"] == draft["version"]["content"]
    versions = (await client.get(f"/api/drafts/{draft['id']}/versions")).json()
    assert [version["number"] for version in versions] == [4, 3, 2, 1]


async def test_chat_refuses_missing_skill_and_offers_fact_bank(prepared):
    draft = await generated(prepared)
    _, client, _, _ = prepared
    result = await client.post(
        f"/api/drafts/{draft['id']}/chat",
        json={
            "expected_version": 1,
            "message": "Add Kubernetes to my skills",
        },
    )
    assert result.status_code == 422
    assert "Fact Bank" in result.json()["error"]["message"]


async def test_chat_can_explicitly_replace_manual_line(prepared):
    draft = await generated(prepared)
    _, client, _, _ = prepared
    content = copy.deepcopy(draft["version"]["content"])
    content["resume"][1]["text"] = "Developed the billing API used by 40 merchant teams"
    await client.put(f"/api/drafts/{draft['id']}", json={"expected_version": 1, "content": content})
    result = await client.post(
        f"/api/drafts/{draft['id']}/chat",
        json={
            "expected_version": 2,
            "message": "Reorder the resume",
            "overwrite_manual": True,
        },
    )
    assert result.status_code == 200
    assert all(not line["manual"] for line in result.json()["version"]["content"]["resume"])


async def test_trace_survives_fact_deletion_and_pdf_has_selectable_text(prepared, db):
    draft = await generated(prepared)
    user, client, _, _ = prepared
    facts = list((await db.scalars(select(Fact).where(Fact.user_id == user.id))).all())
    for fact in facts:
        await db.delete(fact)
    await db.commit()
    result = await client.get(f"/api/drafts/{draft['id']}/pdf")
    assert result.status_code == 200
    reader = PdfReader(io.BytesIO(result.content))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Python" in text and "40 merchant teams" in text
    assert len(reader.pages) <= 2
    trace = (await client.get(f"/api/drafts/{draft['id']}")).json()["version"]["facts"]
    assert len(trace) == 7
    assert (await client.get(f"/api/drafts/{draft['id']}/pdf?kind=cover_letter")).status_code == 200


async def test_diff_has_portfolio_additions(prepared):
    draft = await generated(prepared)
    _, client, _, _ = prepared
    diff = (await client.get(f"/api/drafts/{draft['id']}/diff")).json()
    assert "added_from_portfolio" in {line["kind"] for line in diff}
    assert "removed" in {line["kind"] for line in diff}


@pytest.mark.parametrize(
    "path", ["", "/versions", "/diff", "/pdf", "/email-check?recipient=x@y.com"]
)
async def test_cross_user_reads_are_hidden(prepared, bob, path):
    draft = await generated(prepared)
    _, other = bob
    assert (await other.get(f"/api/drafts/{draft['id']}{path}")).status_code == 404


async def test_cross_user_writes_are_hidden_before_ai_notice(prepared, bob):
    draft = await generated(prepared)
    _, other = bob
    paths = [
        ("PUT", "", {"expected_version": 1, "content": draft["version"]["content"]}),
        ("POST", "/chat", {"expected_version": 1, "message": "Shorten it"}),
        ("POST", "/restore", {"expected_version": 1, "number": 1}),
        (
            "POST",
            "/handoff",
            {"expected_version": 1, "recipient": "jobs@acme.com", "confirm": True},
        ),
        ("POST", "/applied", {"expected_version": 1}),
        ("POST", "/retry", None),
    ]
    for method, path, body in paths:
        assert (
            await other.request(method, f"/api/drafts/{draft['id']}{path}", json=body)
        ).status_code == 404


async def test_handoff_creates_only_a_gmail_draft_with_pdf_and_reuses_it(
    prepared, db, recipient_check
):
    draft = await generated(prepared)
    user, client, _, _ = prepared
    await connect(db, user)
    gmail = FakeGmail()
    app.dependency_overrides[get_google_client] = lambda: GoodGoogle()
    app.dependency_overrides[get_gmail_client] = lambda: gmail
    body = {"expected_version": 1, "recipient": "jobs@acme.com", "confirm": True}
    result = await client.post(f"/api/drafts/{draft['id']}/handoff", json=body)
    assert result.status_code == 200
    assert result.json()["mode"] == "gmail"
    mime = BytesParser(policy=policy.default).parsebytes(
        base64.urlsafe_b64decode(gmail.calls[0][1])
    )
    assert mime["To"] == "jobs@acme.com"
    attachment = list(mime.iter_attachments())[0]
    assert attachment.get_filename() == draft["attachment_name"]
    assert attachment.get_payload(decode=True).startswith(b"%PDF")
    assert mime["Subject"] == f"{draft['job']['title']} - {draft['job']['name']}"
    plain = mime.get_body(preferencelist=("plain",)).get_content()
    assert plain.startswith("Dear Hiring Team,")
    assert "resume attached" in plain
    assert f"Kind regards,\n{draft['job']['name']}" in plain
    page = mime.get_body(preferencelist=("html",)).get_content()
    assert 'class="gmail_signature"' in page
    assert (
        await client.post(f"/api/drafts/{draft['id']}/handoff", json=body)
    ).json() == result.json()
    assert len(gmail.calls) == 1


async def test_handoff_requires_explicit_confirmation(prepared, recipient_check):
    draft = await generated(prepared)
    _, client, _, _ = prepared
    assert (
        await client.post(
            f"/api/drafts/{draft['id']}/handoff",
            json={
                "expected_version": 1,
                "recipient": "jobs@acme.com",
            },
        )
    ).status_code == 409


async def test_expired_gmail_returns_reconnect_path_and_resumes_after_connect(
    prepared, db, recipient_check
):
    draft = await generated(prepared)
    user, client, _, _ = prepared
    await connect(db, user)
    credential = await db.scalar(select(OAuthCredential).where(OAuthCredential.user_id == user.id))
    credential.granted_at = datetime.now(UTC) - timedelta(days=8)
    await db.commit()
    body = {"expected_version": 1, "recipient": "jobs@acme.com", "confirm": True}
    result = await client.post(f"/api/drafts/{draft['id']}/handoff", json=body)
    assert result.json()["mode"] == "reconnect"
    assert "resume_handoff" in result.json()["url"]
    credential.granted_at = datetime.now(UTC)
    await db.commit()
    app.dependency_overrides[get_google_client] = lambda: GoodGoogle()
    app.dependency_overrides[get_gmail_client] = lambda: FakeGmail()
    assert (await client.post(f"/api/drafts/{draft['id']}/handoff", json=body)).json()[
        "mode"
    ] == "gmail"


async def test_gmail_failure_returns_compose_fallback_and_records_drafted(
    prepared, db, recipient_check
):
    draft = await generated(prepared)
    user, client, _, _ = prepared
    await connect(db, user)
    app.dependency_overrides[get_google_client] = lambda: GoodGoogle()
    app.dependency_overrides[get_gmail_client] = lambda: FakeGmail(fail=True)
    response = await client.post(
        f"/api/drafts/{draft['id']}/handoff",
        json={
            "expected_version": 1,
            "recipient": "jobs@acme.com",
            "confirm": True,
        },
    )
    assert response.json()["mode"] == "fallback"
    assert "view=cm" in response.json()["url"]
    assert (await client.get(f"/api/drafts/{draft['id']}")).json()[
        "application_status"
    ] == "drafted"


async def test_after_a_gmail_failure_the_next_hand_off_tries_gmail_again(
    prepared, db, recipient_check
):
    draft = await generated(prepared)
    user, client, _, _ = prepared
    await connect(db, user)
    app.dependency_overrides[get_google_client] = lambda: GoodGoogle()
    body = {"expected_version": 1, "recipient": "jobs@acme.com", "confirm": True}
    app.dependency_overrides[get_gmail_client] = lambda: FakeGmail(fail=True)
    first = await client.post(f"/api/drafts/{draft['id']}/handoff", json=body)
    assert first.json()["mode"] == "fallback"
    gmail = FakeGmail()
    app.dependency_overrides[get_gmail_client] = lambda: gmail
    second = await client.post(f"/api/drafts/{draft['id']}/handoff", json=body)
    assert second.json()["mode"] == "gmail"
    assert len(gmail.calls) == 1
    rows = (await db.execute(select(GmailHandoff).where(GmailHandoff.user_id == user.id))).scalars()
    assert [row.gmail_draft_id for row in rows] == ["gmail-draft-123"]  # one row, updated
    assert len((await db.scalars(select(Application))).all()) == 1


class _Raises:
    def __init__(self, error):
        self.error = error

    async def tailor_draft(self, request):
        raise self.error


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (RuntimeError("bug"), "Something went wrong while writing"),
        (GatewayError("all providers down"), "AI services are busy"),
    ],
)
async def test_generation_failures_never_leave_a_draft_spinning(prepared, error, message):
    _, client, job_id, gateway = prepared
    app.dependency_overrides[get_gateway] = lambda: _Raises(error)
    created = await client.post("/api/drafts", json={"job_id": job_id})
    draft = (await client.get(f"/api/drafts/{created.json()['id']}")).json()
    assert draft["state"] == "failed"
    assert message in draft["error"]


async def test_nothing_traceable_says_so(prepared, monkeypatch):
    _, client, job_id, _ = prepared

    def nothing_kept(draft, content, facts):
        result = drafting.check(content, [])
        return result

    monkeypatch.setattr(drafting, "_check", nothing_kept)
    created = await client.post("/api/drafts", json={"job_id": job_id})
    draft = (await client.get(f"/api/drafts/{created.json()['id']}")).json()
    assert draft["state"] == "failed"
    assert draft["error"] == drafting.NOTHING_VERIFIED


async def test_email_warnings_need_separate_confirmation(prepared, monkeypatch):
    draft = await generated(prepared)
    _, client, _, _ = prepared

    async def check(recipient):
        return EmailCheck(recipient=recipient, valid=False, warnings=["No MX record"])

    monkeypatch.setattr(drafting, "check_recipient", check)
    body = {"expected_version": 1, "recipient": "jobs@acme.com", "confirm": True}
    assert (await client.post(f"/api/drafts/{draft['id']}/handoff", json=body)).status_code == 409
    body["confirm_email_warning"] = True
    assert (await client.post(f"/api/drafts/{draft['id']}/handoff", json=body)).json()[
        "mode"
    ] == "reconnect"


async def test_apply_link_flow_marks_applied_idempotently(prepared, db):
    draft = await generated(prepared)
    _, client, _, _ = prepared
    body = {"expected_version": 1}
    for _ in range(2):
        assert (
            await client.post(f"/api/drafts/{draft['id']}/applied", json=body)
        ).status_code == 204
    rows = list((await db.scalars(select(Application))).all())
    assert len(rows) == 1 and rows[0].applied_at is not None
    assert (await client.get(f"/api/drafts/{draft['id']}")).json()[
        "application_status"
    ] == "applied"


async def test_failed_generation_can_retry(prepared):
    _, client, job_id, _ = prepared
    bad = RecordedAIGateway(Path(get_settings().gateway_recorded_dir), "malformed")
    app.dependency_overrides[get_gateway] = lambda: bad
    created = await client.post("/api/drafts", json={"job_id": job_id})
    draft_id = created.json()["id"]
    assert (await client.get(f"/api/drafts/{draft_id}")).json()["state"] == "failed"
    app.dependency_overrides[get_gateway] = lambda: prepared[3]
    assert (await client.post(f"/api/drafts/{draft_id}/retry")).status_code == 202
    assert (await client.get(f"/api/drafts/{draft_id}")).json()["state"] == "ready"


async def test_job_merge_preserves_draft_versions_and_application(prepared, db):
    draft = await generated(prepared)
    _, client, job_id, _ = prepared
    await client.post(f"/api/drafts/{draft['id']}/applied", json={"expected_version": 1})
    other_id = (await client.get("/api/feed?section=link")).json()["items"][0]["job_id"]
    survivor = await merge_jobs(db, uuid.UUID(job_id), uuid.UUID(other_id), source_priorities())
    await db.commit()
    db.expire_all()
    row = await db.get(Draft, uuid.UUID(draft["id"]))
    application = await db.scalar(select(Application).where(Application.draft_id == row.id))
    versions = list(
        (await db.scalars(select(DraftVersion).where(DraftVersion.draft_id == row.id))).all()
    )
    assert row.job_id == survivor and application.job_id == survivor and len(versions) == 1


async def test_feed_application_state_and_company_warning(prepared, db, bob):
    from app.services.feed import package_states

    draft = await generated(prepared)
    user, client, job_id, _ = prepared
    await client.post(f"/api/drafts/{draft['id']}/applied", json={"expected_version": 1})
    job = await db.get(Job, uuid.UUID(job_id))
    sibling = Job(company_id=job.company_id, title="Platform Engineer", company_name="Acme")
    db.add(sibling)
    await db.commit()
    drafts, states, warned = await package_states(db, user, [job, sibling])
    assert drafts[job.id] == uuid.UUID(draft["id"])
    assert states[job.id] == "applied"
    # FR-D5: the warning is for *another* Job at the Company, not the one applied to.
    assert warned == {sibling.id}
    later = datetime.now(UTC) + timedelta(days=91)
    assert (await package_states(db, user, [job, sibling], later))[2] == set()
    other_user, _ = bob
    assert await package_states(db, other_user, [job]) == ({}, {}, set())
    card = next(
        item for item in (await client.get("/api/feed")).json()["items"] if item["job_id"] == job_id
    )
    assert card["draft_id"] == draft["id"]
    assert card["application_status"] == "applied" and not card["company_applied"]


async def test_ai_cannot_mark_its_own_lines_as_manual_edits(prepared, monkeypatch):
    # Codex review: generation used to keep a fabricated line the model labelled manual.
    _, client, job_id, gateway = prepared
    original = gateway.tailor_draft

    async def tailor(request):
        response = await original(request)
        response.result.content.resume.append(
            DraftLine(text="Ran Kubernetes at Google", fact_refs=["F1"], manual=True)
        )
        return response

    monkeypatch.setattr(gateway, "tailor_draft", tailor)
    created = await client.post("/api/drafts", json={"job_id": job_id})
    draft = (await client.get(f"/api/drafts/{created.json()['id']}")).json()
    texts = [line["text"] for line in draft["version"]["content"]["resume"]]
    assert "Ran Kubernetes at Google" not in texts
    assert not any(line["manual"] for line in draft["version"]["content"]["resume"])
    assert any(w.startswith("Removed a resume line") for w in draft["version"]["warnings"])


async def test_page_opens_on_the_template_the_resume_fits_in(prepared, monkeypatch):
    """Compact when only Compact fits on one page: a second page with a few lines on it
    looks unfinished."""

    def pages(content, name, email, template="standard", facts=None):
        return 2 if template == "standard" else 1

    monkeypatch.setattr(drafting, "page_count", pages)
    drafting._TEMPLATE_FITS.clear()
    draft = await generated(prepared)
    assert draft["template"] == "compact"


async def test_page_keeps_standard_when_compact_saves_no_page(prepared, monkeypatch):
    def pages(content, name, email, template="standard", facts=None):
        return 2

    monkeypatch.setattr(drafting, "page_count", pages)
    drafting._TEMPLATE_FITS.clear()
    draft = await generated(prepared)
    assert draft["template"] == "standard"


async def test_a_pdf_problem_never_fails_generation(prepared, monkeypatch):
    """A failed Draft has no editor, so it could never be fixed: it is saved with a warning
    saying what to change instead."""

    def unrenderable(*args, **kwargs):
        raise ValidationFailedError("This PDF font cannot render a character. Edit it first.")

    monkeypatch.setattr(drafting, "render_pdf", unrenderable)
    drafting._TEMPLATE_FITS.clear()
    draft = await generated(prepared)
    assert draft["state"] == "ready"
    assert any(w.startswith("PDF: This PDF font") for w in draft["version"]["warnings"])


async def test_a_closed_apply_link_closes_the_job_before_any_ai_work(prepared, db):
    """FR-B10 AC3: checked for free when the Draft is created."""
    import httpx

    from app.adapters.links import get_link_http

    _, client, _, _ = prepared
    link_job = (await client.get("/api/feed?section=link")).json()["items"][0]["job_id"]
    dead = "https://jobs.acme.dev/backend/1"
    await db.execute(
        update(Posting).where(Posting.job_id == uuid.UUID(link_job)).values(apply_url=dead)
    )
    await db.execute(update(Job).where(Job.id == uuid.UUID(link_job)).values(apply_url=dead))
    await db.commit()
    app.dependency_overrides[get_link_http] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(404))
    )
    refused = await client.post("/api/drafts", json={"job_id": link_job})
    assert refused.status_code == 409
    assert "looks closed" in refused.json()["error"]["message"]
    job = await db.get(Job, uuid.UUID(link_job))
    await db.refresh(job)
    assert job.expired_at is not None
    assert (await db.scalars(select(Draft))).all() == []
    posting = await db.scalar(select(Posting).where(Posting.job_id == uuid.UUID(link_job)))
    await db.refresh(posting)
    assert posting.closed_reason == "link"


async def test_an_open_or_unreachable_link_never_blocks_a_draft(prepared, db):
    """Only an explicit 404 or 410 closes a Job; a blocked or slow site is not evidence."""
    import httpx

    from app.adapters.links import get_link_http

    _, client, job_id, _ = prepared
    await db.execute(
        update(Job).where(Job.id == uuid.UUID(job_id)).values(apply_url="https://x.dev/1")
    )
    await db.execute(
        update(Posting)
        .where(Posting.job_id == uuid.UUID(job_id))
        .values(apply_url="https://x.dev/1")
    )
    await db.commit()
    app.dependency_overrides[get_link_http] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(403))
    )
    assert (await client.post("/api/drafts", json={"job_id": job_id})).status_code == 202


async def test_moving_a_line_protects_it_like_an_edit(prepared):
    """FR-E6: reordering or moving a line to another section is the User's edit."""
    draft = await generated(prepared)
    _, client, _, _ = prepared
    content = draft["version"]["content"]
    assert len(content["resume"]) >= 2
    content["resume"] = [content["resume"][-1], *content["resume"][:-1]]
    first = content["resume"][0]
    content["resume"][1]["section"] = (
        "Projects" if content["resume"][1]["section"] != "Projects" else "Summary"
    )
    saved = await client.put(
        f"/api/drafts/{draft['id']}", json={"expected_version": 1, "content": content}
    )
    assert saved.status_code in (200, 204), saved.text
    lines = (await client.get(f"/api/drafts/{draft['id']}")).json()["version"]["content"]["resume"]
    by_id = {line["id"]: line for line in lines}
    assert by_id[first["id"]]["manual"] is True
    assert by_id[content["resume"][1]["id"]]["manual"] is True
    assert all(not by_id[line["id"]]["manual"] for line in content["resume"][2:])


async def test_archiving_keeps_versions_and_the_application_link(prepared, db):
    user, client, job_id, _ = prepared
    draft = await generated(prepared)
    marked = await client.post(f"/api/drafts/{draft['id']}/applied", json={"expected_version": 1})
    assert marked.status_code == 204
    archived = await client.delete(f"/api/drafts/{draft['id']}?expected_version=1")
    assert archived.status_code == 204
    # The package used for the application stays readable, with its PDFs.
    assert (await client.get(f"/api/drafts/{draft['id']}")).json()["active"] is False
    pdf = await client.get(f"/api/drafts/{draft['id']}/pdf", params={"number": 1})
    assert pdf.status_code == 200
    assert (
        await db.scalar(
            select(DraftVersion.id).where(DraftVersion.draft_id == uuid.UUID(draft["id"]))
        )
        is not None
    )
    # The Job page lists it, so an archived package is never lost from view.
    job = (await client.get(f"/api/jobs/{job_id}")).json()
    assert job["draft_id"] is None
    assert [d["id"] for d in job["archived_drafts"]] == [draft["id"]]
    owner_id = user.id
    db.expire_all()
    application = await db.scalar(
        select(Application).where(Application.user_id == owner_id, Application.job_id == job_id)
    )
    assert application.status == "applied"
    assert str(application.draft_id) == draft["id"]


async def test_delete_checks_owner_version_and_in_progress(prepared, bob, db):
    _, client, _, _ = prepared
    draft = await generated(prepared)
    _, other = bob
    path = f"/api/drafts/{draft['id']}"
    assert (await other.delete(path + "?expected_version=1")).status_code == 404
    assert (await client.delete(path + "?expected_version=2")).status_code == 409
    await db.execute(
        update(Draft).where(Draft.id == uuid.UUID(draft["id"])).values(state="generating")
    )
    await db.commit()
    assert (await client.delete(path + "?expected_version=1")).status_code == 409


async def test_one_active_package_per_job_and_archiving_keeps_history(prepared, db):  # noqa: F811
    _, client, job_id, _ = prepared
    old = await generated(prepared)
    content = copy.deepcopy(old["version"]["content"])
    content["resume"][0]["text"] += " My saved wording."
    saved = await client.put(
        f"/api/drafts/{old['id']}", json={"expected_version": 1, "content": content}
    )
    assert saved.status_code == 200
    # Creating again opens the active package instead of a second one.
    again = await client.post("/api/drafts", json={"job_id": job_id})
    assert again.status_code == 202
    assert again.json()["id"] == old["id"]
    assert again.json()["version"]["content"]["resume"][0]["text"].endswith("My saved wording.")

    archived = await client.delete(f"/api/drafts/{old['id']}?expected_version=2")
    assert archived.status_code == 204
    kept = (await client.get(f"/api/drafts/{old['id']}")).json()
    assert kept["active"] is False and kept["current_version"] == 2
    # An archived package is read-only.
    refused = await client.put(
        f"/api/drafts/{old['id']}", json={"expected_version": 2, "content": content}
    )
    assert refused.status_code == 409
    fresh = await client.post("/api/drafts", json={"job_id": job_id})
    assert fresh.json()["id"] != old["id"]
