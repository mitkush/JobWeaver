"""Background replacement proposals (APPLICATION_UX_PLAN stage 2): AI work never replaces the
accepted document until the User accepts it, against the version it was based on."""

import uuid

import pytest
from sqlalchemy import select, update

from app.core.errors import GatewayError
from app.gateway.schemas import DraftResult, GatewayResponse, ReviseDraftRequest
from app.models import DraftProposal, DraftVersion, Fact
from tests.api.test_drafts import generated, prepared  # noqa: F401


def facts_as_text(gateway, *, part: str = "resume") -> list[ReviseDraftRequest]:
    """A stand-in model: rewrites each line of the requested part to its first cited Fact,
    so the output is new text that still passes the Fact checks."""
    seen: list[ReviseDraftRequest] = []

    async def propose(request: ReviseDraftRequest) -> GatewayResponse[DraftResult]:
        seen.append(request)
        by_ref = {f.ref: f for f in request.facts}
        content = request.content.model_copy(deep=True)
        for line in getattr(content, part):
            if line.fact_refs and line.fact_refs[0] in by_ref and not line.heading:
                line.text = by_ref[line.fact_refs[0]].text
        return GatewayResponse[DraftResult](
            result=DraftResult(content=content, message=""), provider="fake", model="fake"
        )

    gateway.propose_draft = propose
    return seen


async def propose(client, draft_id: str, **body):
    return await client.post(
        f"/api/drafts/{draft_id}/proposals", json={"expected_version": 1, "part": "resume"} | body
    )


async def only_proposal(client, draft_id: str) -> dict:
    [row] = (await client.get(f"/api/drafts/{draft_id}/proposals")).json()
    return row


async def test_a_resume_replacement_waits_for_acceptance_and_leaves_the_cover_letter(prepared):  # noqa: F811
    _, client, _, gateway = prepared
    draft = await generated(prepared)
    facts_as_text(gateway)
    assert (await propose(client, draft["id"])).status_code == 202
    proposal = await only_proposal(client, draft["id"])
    assert proposal["state"] == "ready"
    # Nothing changed yet: the accepted document is still version 1.
    assert (await client.get(f"/api/drafts/{draft['id']}")).json()["current_version"] == 1

    accepted = await client.post(
        f"/api/drafts/{draft['id']}/proposals/{proposal['id']}/accept",
        json={"expected_version": 1},
    )
    assert accepted.status_code == 200, accepted.text
    after = accepted.json()
    assert after["current_version"] == 2
    assert (
        after["version"]["content"]["cover_letter"] == draft["version"]["content"]["cover_letter"]
    )
    assert (await client.get(f"/api/drafts/{draft['id']}/proposals")).json() == []

    # Undo is a restore of the preceding accepted version, itself a new version.
    undone = await client.post(
        f"/api/drafts/{draft['id']}/restore", json={"number": 1, "expected_version": 2}
    )
    assert undone.status_code == 200, undone.text
    assert undone.json()["version"]["content"] == draft["version"]["content"]


async def test_a_section_replacement_changes_only_that_section(prepared):  # noqa: F811
    _, client, _, gateway = prepared
    draft = await generated(prepared)
    seen = facts_as_text(gateway)
    resume = draft["version"]["content"]["resume"]
    section = next(line["section"] for line in resume if not line["heading"] and line["fact_refs"])
    assert (await propose(client, draft["id"], section=section)).status_code == 202
    proposal = await only_proposal(client, draft["id"])
    assert proposal["state"] == "ready", proposal
    assert section in seen[0].message
    proposed = proposal["content"]["resume"]
    others = [line for line in proposed if line["section"] != section]
    assert others == [line for line in resume if line["section"] != section]


async def test_stale_or_resolved_proposals_cannot_be_accepted(prepared):  # noqa: F811
    _, client, _, gateway = prepared
    draft = await generated(prepared)
    facts_as_text(gateway)
    await propose(client, draft["id"])
    proposal = await only_proposal(client, draft["id"])
    # A second proposal while one is waiting is refused.
    assert (await propose(client, draft["id"])).status_code == 409
    # The User edits the Draft meanwhile: the proposal's base is now stale.
    content = draft["version"]["content"]
    content["resume"][0]["text"] += " Edited."
    assert (
        await client.put(
            f"/api/drafts/{draft['id']}", json={"expected_version": 1, "content": content}
        )
    ).status_code == 200
    stale = await client.post(
        f"/api/drafts/{draft['id']}/proposals/{proposal['id']}/accept",
        json={"expected_version": 2},
    )
    assert stale.status_code == 409
    assert (await client.get(f"/api/drafts/{draft['id']}")).json()["current_version"] == 2
    kept = await client.delete(f"/api/drafts/{draft['id']}/proposals/{proposal['id']}")
    assert kept.status_code == 204
    again = await client.delete(f"/api/drafts/{draft['id']}/proposals/{proposal['id']}")
    assert again.status_code == 409


async def test_a_proposal_citing_a_changed_fact_is_refused(prepared, db):  # noqa: F811
    user, client, _, gateway = prepared
    draft = await generated(prepared)
    facts_as_text(gateway)
    await propose(client, draft["id"])
    proposal = await only_proposal(client, draft["id"])
    cited = {ref for line in proposal["content"]["resume"] for ref in line["fact_refs"]}
    fact_id = next(
        uuid.UUID(f["id"])
        for f in (
            await db.scalar(
                select(DraftProposal.facts).where(DraftProposal.id == uuid.UUID(proposal["id"]))
            )
        )
        if f["ref"] in cited
    )
    await db.execute(
        update(Fact)
        .where(Fact.id == fact_id, Fact.user_id == user.id)
        .values(text="Reworded later")
    )
    await db.commit()
    refused = await client.post(
        f"/api/drafts/{draft['id']}/proposals/{proposal['id']}/accept",
        json={"expected_version": 1},
    )
    assert refused.status_code == 409
    assert "Facts changed" in refused.json()["error"]["message"]


async def test_a_failed_proposal_leaves_the_draft_usable(prepared):  # noqa: F811
    _, client, _, gateway = prepared
    draft = await generated(prepared)

    async def unavailable(_request):
        raise GatewayError("All providers busy")

    gateway.propose_draft = unavailable
    assert (await propose(client, draft["id"])).status_code == 202
    proposal = await only_proposal(client, draft["id"])
    assert proposal["state"] == "failed"
    assert "current document is unchanged" in proposal["error"]
    current = (await client.get(f"/api/drafts/{draft['id']}")).json()
    assert current["current_version"] == 1 and current["state"] == "ready"


async def test_proposals_are_private_and_archived_drafts_refuse_them(prepared, bob):  # noqa: F811
    _, client, _, gateway = prepared
    draft = await generated(prepared)
    facts_as_text(gateway)
    await propose(client, draft["id"])
    proposal = await only_proposal(client, draft["id"])
    _, other = bob
    assert (await other.get(f"/api/drafts/{draft['id']}/proposals")).status_code == 404
    stolen = await other.post(
        f"/api/drafts/{draft['id']}/proposals/{proposal['id']}/accept",
        json={"expected_version": 1},
    )
    assert stolen.status_code == 404
    assert (
        await other.delete(f"/api/drafts/{draft['id']}/proposals/{proposal['id']}")
    ).status_code == 404

    await client.delete(f"/api/drafts/{draft['id']}/proposals/{proposal['id']}")
    assert (await client.delete(f"/api/drafts/{draft['id']}?expected_version=1")).status_code == 204
    assert (await propose(client, draft["id"])).status_code == 409


@pytest.mark.parametrize("missing", ["notice", "facts"])
async def test_proposals_need_the_ai_notice_and_a_reviewed_fact_bank(prepared, db, missing):  # noqa: F811
    user, client, _, gateway = prepared
    draft = await generated(prepared)
    from app.models import User

    values = (
        {"ai_notice_accepted_at": None} if missing == "notice" else {"fact_bank_reviewed_at": None}
    )
    await db.execute(update(User).where(User.id == user.id).values(**values))
    await db.commit()
    refused = await propose(client, draft["id"])
    assert refused.status_code == 409
    assert await db.scalar(select(DraftProposal.id)) is None


async def test_every_version_keeps_the_job_context_it_was_made_with(prepared, db):  # noqa: F811
    _, client, _, gateway = prepared
    draft = await generated(prepared)
    content = draft["version"]["content"]
    content["resume"][0]["text"] += " Edited."
    await client.put(f"/api/drafts/{draft['id']}", json={"expected_version": 1, "content": content})
    rows = list(
        await db.scalars(
            select(DraftVersion)
            .where(DraftVersion.draft_id == uuid.UUID(draft["id"]))
            .order_by(DraftVersion.number)
        )
    )
    assert [r.number for r in rows] == [1, 2]
    assert rows[0].job_context and rows[0].job_context == rows[1].job_context
    assert rows[0].job_context["title"] == draft["job"]["title"]
