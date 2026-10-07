"""Two Jobs merged by Correspondence keep one Application per User (FR-F1)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models import Application, ApplicationEvent, Company, GmailHandoff, Job
from app.services import applications
from tests.conftest import signed_in


async def test_merging_jobs_keeps_one_application_with_both_histories(db):
    user, client = await signed_in(db, "merge@example.com")
    await client.aclose()
    company = Company(name="Acme", normalized_name="acme-merge")
    db.add(company)
    await db.flush()
    survivor = Job(company_id=company.id, title="Backend Engineer", company_name="Acme")
    gone = Job(company_id=company.id, title="Backend Engineer", company_name="Acme")
    db.add_all([survivor, gone])
    await db.flush()
    early = datetime.now(UTC) - timedelta(days=5)
    kept = await applications.ensure(db, user, survivor.id, None, early)
    moved = await applications.ensure(db, user, gone.id, None, early)
    applications.change_status(db, user, moved, "interview", datetime.now(UTC))
    db.add(GmailHandoff(user_id=user.id, application_id=moved.id, recipient="hr@acme.io"))
    await db.flush()

    kept_id, survivor_id = kept.id, survivor.id
    await applications.move_to_job(db, gone.id, survivor.id)
    await db.commit()
    db.expire_all()
    rows = list((await db.scalars(select(Application))).all())
    assert len(rows) == 1 and rows[0].id == kept_id and rows[0].job_id == survivor_id
    # The further-along status wins, and it counts as applied.
    assert rows[0].status == "interview" and rows[0].applied_at is not None
    events = await db.scalar(
        select(func.count())
        .select_from(ApplicationEvent)
        .where(ApplicationEvent.application_id == kept_id)
    )
    assert events == 3  # drafted, drafted, interview
    handoff = await db.scalar(select(GmailHandoff))
    assert handoff.application_id == kept_id


async def test_a_job_only_one_side_applied_to_just_moves(db):
    user, client = await signed_in(db, "move@example.com")
    await client.aclose()
    company = Company(name="Beta", normalized_name="beta-merge")
    db.add(company)
    await db.flush()
    survivor = Job(company_id=company.id, title="SRE", company_name="Beta")
    gone = Job(company_id=company.id, title="SRE", company_name="Beta")
    db.add_all([survivor, gone])
    await db.flush()
    application = await applications.ensure(db, user, gone.id, None)
    await applications.move_to_job(db, gone.id, survivor.id)
    await db.commit()
    assert (await db.get(Application, application.id)).job_id == survivor.id


async def _two_jobs(db, email: str, key: str):
    user, client = await signed_in(db, email)
    await client.aclose()
    company = Company(name=key, normalized_name=f"{key}-merge")
    db.add(company)
    await db.flush()
    survivor = Job(company_id=company.id, title="SRE", company_name=key)
    gone = Job(company_id=company.id, title="SRE", company_name=key)
    db.add_all([survivor, gone])
    await db.flush()
    return user, survivor, gone


async def test_a_newer_earlier_status_never_wins_a_merge(db):
    user, survivor, gone = await _two_jobs(db, "order@example.com", "order")
    then = datetime.now(UTC) - timedelta(days=3)
    kept = await applications.ensure(db, user, survivor.id, None, then)
    applications.change_status(db, user, kept, "interview", then)
    moved = await applications.ensure(db, user, gone.id, None)
    applications.change_status(db, user, moved, "applied", datetime.now(UTC))
    kept_id = kept.id
    await applications.move_to_job(db, gone.id, survivor.id)
    await db.commit()
    db.expire_all()
    row = await db.get(Application, kept_id)
    # Interview is further along than a newer Applied, and no reminder comes back.
    assert row.status == "interview" and row.follow_up_after is None


async def test_between_final_outcomes_the_newer_wins(db):
    user, survivor, gone = await _two_jobs(db, "final@example.com", "final")
    then = datetime.now(UTC) - timedelta(days=3)
    kept = await applications.ensure(db, user, survivor.id, None, then)
    applications.change_status(db, user, kept, "offer", then)
    moved = await applications.ensure(db, user, gone.id, None)
    applications.change_status(db, user, moved, "rejected", datetime.now(UTC))
    kept_id = kept.id
    await applications.move_to_job(db, gone.id, survivor.id)
    await db.commit()
    db.expire_all()
    assert (await db.get(Application, kept_id)).status == "rejected"
