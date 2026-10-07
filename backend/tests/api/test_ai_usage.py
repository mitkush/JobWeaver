"""Admin view of AI usage against free quotas (FR-G4)."""

from app.gateway.routing import DAILY_QUOTAS, GEMINI_FLASH
from app.models import AIUsage


async def test_ai_usage_is_admin_only(alice):
    _, user_client = alice
    assert (await user_client.get("/api/admin/ai-usage")).status_code == 403


async def test_usage_summary_counts_calls_errors_and_tokens(db):
    from tests.conftest import signed_in

    admin_user, client = await signed_in(db, "admin@example.com")
    db.add_all(
        [
            AIUsage(task="tailor_draft", provider="gemini", model=GEMINI_FLASH, outcome="ok",
                    input_tokens=1000, output_tokens=400),
            AIUsage(task="tailor_draft", provider="gemini", model=GEMINI_FLASH, outcome="error"),
        ]
    )  # fmt: skip
    await db.commit()
    async with client:
        body = (await client.get("/api/admin/ai-usage")).json()
    flash = next(m for m in body["models"] if m["model"] == GEMINI_FLASH)
    assert (flash["calls_today"], flash["errors_today"]) == (2, 1)
    assert flash["daily_quota"] == DAILY_QUOTAS[("gemini", GEMINI_FLASH)]
    # Every quota-limited model is listed, used today or not.
    assert len(body["models"]) >= len(DAILY_QUOTAS)
    assert body["tasks_last_7_days"] == [
        {"task": "tailor_draft", "calls": 2, "errors": 1, "input_tokens": 1000,
         "output_tokens": 400}
    ]  # fmt: skip
