import json
import uuid

import pytest

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.gateway import prompts
from app.gateway.draft_prompt import DRAFT_OUTPUT_RESERVE, draft_prompt
from app.gateway.live import CHARS_PER_TOKEN, TOKEN_MARGIN, LiveAIGateway
from app.gateway.quota import UsageLedger
from app.gateway.schemas import ReviseDraftRequest
from app.tailoring.content import DraftContent, DraftLine, FactSnapshot
from tests.gateway.test_draft_tasks import request
from tests.gateway.test_live_gateway import FakeClient


def fact(ref, kind, group, text):
    return FactSnapshot(
        ref=ref, id=uuid.uuid4(), kind=kind, group=group, text=text, in_base_resume=False
    )


def package(facts):
    body = request(uuid.uuid4())
    return body.model_copy(update={"description": "Python API performance", "facts": facts})


def refs(rendered):
    return {f["ref"] for f in json.loads(rendered)["facts"]}


def test_selects_relevant_whole_project_without_changing_the_fact_bank():
    body = package(
        [
            fact("F1", "project", "Other", "Built a gardening application. " * 15),
            fact("F7", "project", "API", "API project | Python | https://example.com/api"),
            fact("F9", "achievement", "API", "Improved Python API performance 60 times."),
        ]
    )
    original = body.model_dump()
    only_relevant = body.model_copy(update={"facts": body.facts[1:]})
    limit = len(prompts.draft_user(only_relevant))

    rendered = draft_prompt(body, limit)

    assert rendered is not None
    assert refs(rendered) == {"F7", "F9"}
    assert body.model_dump() == original
    assert [f["text"] for f in json.loads(rendered)["facts"]] == [f.text for f in body.facts[1:]]


def test_employment_dates_employers_and_contact_survive_an_unrelated_job():
    body = package(
        [
            fact("F1", "experience", "Old Employer", "Developer | Old Employer | 2018 to 2020"),
            fact("F2", "achievement", "Old Employer", "Maintained payroll software."),
            fact("F3", "experience", "New Employer", "Engineer | New Employer | 2020 to Present"),
            fact("F4", "other", "Contact", "Phone: +91 9999999999"),
            fact("F5", "project", "Side Project", "Python " * 1000),
        ]
    )
    limit = len(prompts.draft_user(body.model_copy(update={"facts": body.facts[:4]})))
    rendered = draft_prompt(body, limit)
    assert rendered is not None
    assert refs(rendered) == {"F1", "F2", "F3", "F4"}
    # Never squeeze protected employment history into a partial Fact.
    assert draft_prompt(body, limit - 1) is None


def test_a_project_cannot_fit_as_an_orphan_bullet():
    body = package(
        [
            fact("F1", "skill", "", "Python"),
            fact("F2", "project", "API", "Project title and employer " * 60),
            fact("F3", "achievement", "API", "Python API performance"),
        ]
    )
    limit = len(prompts.draft_user(body.model_copy(update={"facts": body.facts[:1]}))) + 200
    rendered = draft_prompt(body, limit)
    assert rendered is not None
    assert refs(rendered) == {"F1"}


def test_chat_keeps_every_cited_fact_and_manual_line_unchanged():
    body = package(
        [
            fact("F1", "skill", "", "Python"),
            fact("F2", "project", "Older Project", "Built a payroll product."),
            fact("F3", "achievement", "Older Project", "Reduced errors by 25%."),
            fact("F4", "project", "Uncited", "Python API " * 500),
        ]
    )
    manual = DraftLine(text="My exact saved wording", fact_refs=["F3"], manual=True)
    letter = DraftLine(text="I use Python", fact_refs=["F1"])
    content = DraftContent(resume=[manual], cover_letter=[letter])
    revision = ReviseDraftRequest(**body.model_dump(), content=content, message="Shorten")
    limit = len(prompts.draft_user(revision.model_copy(update={"facts": body.facts[:3]})))
    rendered = draft_prompt(revision, limit)
    assert rendered is not None
    assert refs(rendered) == {"F1", "F2", "F3"}
    assert json.loads(rendered)["content"] == content.model_dump(mode="json")
    assert revision.content.resume[0] == manual
    assert draft_prompt(revision, limit - 1) is None


def test_selection_is_repeatable_and_empty_budget_never_sends_empty_facts():
    body = package([fact("F1", "skill", "Languages", "Python")])
    assert draft_prompt(body, 10) is None
    assert draft_prompt(body, 2000) == draft_prompt(body, 2000)


@pytest.mark.parametrize("chat", [False, True])
async def test_oversized_fact_bank_fits_groq_with_output_room(alice, chat):
    from pathlib import Path

    user, _ = alice
    body = package(
        [
            fact("F1", "skill", "Languages", "Python API performance"),
            *[
                fact(f"F{i}", "project", f"Garden {i}", "Gardening tools " * 80)
                for i in range(2, 42)
            ],
        ]
    ).model_copy(update={"user_id": user.id})
    if chat:
        line = DraftLine(text="Python API performance", fact_refs=["F1"], manual=True)
        body = ReviseDraftRequest(
            **body.model_dump(),
            content=DraftContent(resume=[line], cover_letter=[line]),
            message="Shorten without changing my wording",
        )
    raw = json.loads(
        (Path(get_settings().gateway_recorded_dir) / "tailor_draft" / "success.json").read_text()
    )["output"]
    groq = FakeClient("groq", [raw])
    gateway = LiveAIGateway({"groq": groq}, UsageLedger(get_sessionmaker()))
    method = gateway.revise_draft if chat else gateway.tailor_draft
    result = await method(body)
    assert result.provider == "groq"
    system = prompts.REVISE_DRAFT_SYSTEM if chat else prompts.TAILOR_DRAFT_SYSTEM
    prompt_tokens = -(-(len(system) + len(groq.user_prompts[0])) // CHARS_PER_TOKEN)
    assert prompt_tokens + groq.output_budgets[0] + TOKEN_MARGIN <= 8000
    assert groq.output_budgets[0] >= DRAFT_OUTPUT_RESERVE
    assert len(refs(groq.user_prompts[0])) < len(body.facts)
    assert "F1" in refs(groq.user_prompts[0])
    if chat:
        assert json.loads(groq.user_prompts[0])["content"] == body.content.model_dump(mode="json")


async def test_protected_context_too_large_for_groq_uses_larger_provider(alice):
    from pathlib import Path

    user, _ = alice
    body = package(
        [fact("F1", "experience", "Employer", "Engineer | Employer | 2020 to Present " * 800)]
    ).model_copy(update={"user_id": user.id})
    raw = json.loads(
        (Path(get_settings().gateway_recorded_dir) / "tailor_draft" / "success.json").read_text()
    )["output"]
    groq = FakeClient("groq", [raw])
    larger = FakeClient("openrouter", [raw])
    gateway = LiveAIGateway({"groq": groq, "openrouter": larger}, UsageLedger(get_sessionmaker()))
    response = await gateway.tailor_draft(body)
    assert response.provider == "openrouter"
    assert groq.calls == []
    assert larger.user_prompts == [prompts.draft_user(body)]


async def test_generation_accepts_a_slow_primary_and_falls_back_within_route_deadlines(
    alice, monkeypatch
):
    import asyncio
    from pathlib import Path

    from app.gateway.providers import Completion
    from app.gateway.routing import ROUTING_TABLE, Route

    user, _ = alice
    raw = json.loads(
        (Path(get_settings().gateway_recorded_dir) / "tailor_draft" / "success.json").read_text()
    )["output"]
    # Scale configured seconds to milliseconds: 30 ms would exceed the old 20 ms route.
    configured = ROUTING_TABLE["tailor_draft"]
    monkeypatch.setitem(
        ROUTING_TABLE,
        "tailor_draft",
        [
            Route(r.provider, r.model, r.max_output_tokens, r.timeout_seconds / 1000)
            for r in configured
        ],
    )

    class Slow:
        delay = 0.03
        cancelled = False

        async def complete_json(self, model, system, prompt, output):
            try:
                await asyncio.sleep(self.delay)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            return Completion(raw, 10, 5)

    primary = Slow()
    groq = FakeClient("groq", [raw])
    gateway = LiveAIGateway({"gemini": primary, "groq": groq}, UsageLedger(get_sessionmaker()))
    assert (await gateway.tailor_draft(request(user.id))).provider == "gemini"
    assert groq.calls == []
    primary.delay = 1
    assert (await gateway.tailor_draft(request(user.id))).provider == "groq"
    assert primary.cancelled
