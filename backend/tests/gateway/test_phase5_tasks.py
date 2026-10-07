from pathlib import Path

import pytest

from app.core.config import get_settings
from app.core.errors import GatewayError
from app.gateway import prompts
from app.gateway.recorded import RecordedAIGateway
from app.gateway.routing import ROUTING_TABLE
from app.gateway.schemas import AdvertText, ExtractAdvertsRequest

FIXTURES = Path(get_settings().gateway_recorded_dir)
REQUEST = ExtractAdvertsRequest(adverts=[AdvertText(ref="1", text="Acme | Berlin | hiring")])


def test_adverts_run_on_flash_lite_first_with_text_fallbacks():
    # COSTS.md: HN extraction is high-volume work, Flash-Lite first.
    routes = [(r.provider, r.model) for r in ROUTING_TABLE["extract_adverts"]]
    assert routes[0] == ("gemini", "gemini-flash-lite-latest")
    assert [p for p, _ in routes] == ["gemini", "groq", "openrouter"]


def test_adverts_prompt_bounds_each_comment():
    text = prompts.extract_adverts_user(
        ExtractAdvertsRequest(adverts=[AdvertText(ref="9", text="x" * 20000)])
    )
    assert 'ref="9"' in text and len(text) < prompts.COMMENT_CHARS + 100


@pytest.mark.parametrize("variant", ["malformed", "refusal"])
async def test_recorded_advert_failures_are_gateway_errors(variant):
    with pytest.raises(GatewayError):
        await RecordedAIGateway(FIXTURES, variant).extract_adverts(REQUEST)  # type: ignore[arg-type]


async def test_recorded_adverts():
    result = (await RecordedAIGateway(FIXTURES).extract_adverts(REQUEST)).result
    assert [len(a.jobs) for a in result.adverts] == [2, 1, 0]
    assert result.adverts[2].is_job_advert is False


def test_gemini_flash_is_reserved_for_drafts_and_draft_chat():
    """FR-G4 AC1 and COSTS.md: Flash's small daily quota goes to Draft generation and
    Draft Chat only; every other task starts on Flash-Lite."""
    from app.gateway.routing import GEMINI_FLASH

    for task, routes in ROUTING_TABLE.items():
        uses_flash = any(r.model == GEMINI_FLASH for r in routes)
        assert uses_flash == (task in {"tailor_draft", "revise_draft"}), task
