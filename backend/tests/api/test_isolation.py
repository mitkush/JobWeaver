"""FR-G1 AC1: every user-owned endpoint acts on the caller's own data only. These cover the
endpoints not already covered by their feature's tests."""

import uuid

from sqlalchemy import func, select

from app.models import Fact, OAuthCredential, UserJob
from tests.api.test_drafts import connect, prepared  # noqa: F401
from tests.api.test_fact_bank import upload_resume, use_variant
from tests.conftest import onboard


async def facts_of(db, user) -> int:
    return int(
        await db.scalar(select(func.count()).select_from(Fact).where(Fact.user_id == user.id))
    )


async def test_fact_bank_writes_never_touch_another_users_fact_bank(alice, bob, db):
    use_variant("success")
    alice_user, a = alice
    bob_user, b = bob
    await onboard(a)
    await onboard(b)
    assert (await upload_resume(a)).status_code == 200
    alice_facts = await facts_of(db, alice_user)
    assert alice_facts > 0

    # Bob's own uploads, rebuild and review only change Bob's Fact Bank.
    assert (await upload_resume(b)).status_code == 200
    text = {"kind": "summary", "text": "Backend engineer with ten years of Python and Go."}
    assert (await b.post("/api/documents/text", json=text)).status_code == 200
    assert (await b.post("/api/fact-bank/rebuild")).status_code == 200
    assert (await b.post("/api/fact-bank/review")).status_code == 204
    assert await facts_of(db, alice_user) == alice_facts
    assert (await a.get("/api/me")).json()["onboarding"]["fact_bank_reviewed"] is False

    # Bob's export holds Bob's documents and Facts only.
    export = (await b.get("/api/fact-bank/export")).json()
    alice_ids = {
        str(i) for i in (await db.scalars(select(Fact.id).where(Fact.user_id == alice_user.id)))
    }
    assert alice_ids.isdisjoint({str(f["id"]) for f in export["facts"]})

    # Bob deleting his Fact Bank leaves Alice's untouched.
    assert (await b.delete("/api/fact-bank")).status_code == 204
    assert await facts_of(db, bob_user) == 0
    assert await facts_of(db, alice_user) == alice_facts


async def test_disconnecting_gmail_only_disconnects_the_caller(alice, bob, db):
    alice_user, _ = alice
    bob_user, b = bob
    await connect(db, alice_user)
    await connect(db, bob_user)
    assert (await b.delete("/api/gmail")).status_code == 200
    owners = set((await db.scalars(select(OAuthCredential.user_id))).all())
    assert owners == {alice_user.id}


async def test_unhide_and_split_refuse_another_users_jobs(prepared, bob, db):  # noqa: F811
    alice_user, a, job_id, _ = prepared
    _, b = bob
    assert (await a.post(f"/api/feed/{job_id}/hide")).status_code == 204
    # The Job is not in Bob's Feed: he can neither unhide it for Alice nor split it.
    assert (await b.delete(f"/api/feed/{job_id}/hide")).status_code == 404
    link = await db.scalar(
        select(UserJob).where(UserJob.user_id == alice_user.id, UserJob.job_id == uuid.UUID(job_id))
    )
    assert link.hidden_at is not None
    split = await b.post(f"/api/jobs/{job_id}/postings/{uuid.uuid4()}/split")
    assert split.status_code == 404
