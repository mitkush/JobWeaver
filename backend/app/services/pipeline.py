"""The daily pipeline (PRD section 10): fetch, then group into Jobs, link Feeds and
extract skills. One place builds it, so every trigger runs the same steps."""

import logging

from app.core.db import get_sessionmaker
from app.gateway.base import BaseAIGateway
from app.gateway.factory import build_gateway
from app.services.correspondence import Correspondence, Report
from app.services.description_mentions import backfill as backfill_description_mentions
from app.services.fetching import Fetcher, fetch_lock

logger = logging.getLogger(__name__)


def build_correspondence(gateway: BaseAIGateway | None = None) -> Correspondence:
    return Correspondence(get_sessionmaker(), gateway or build_gateway())


def build_fetcher(gateway: BaseAIGateway | None = None) -> Fetcher:
    return Fetcher(get_sessionmaker(), after_fetch=build_correspondence(gateway).process)


async def process_queues(gateway: BaseAIGateway | None = None) -> Report | None:
    """Between fetches: embeddings queued while Gemini was down, skills not extracted yet
    (ADR-0014), and description mention caches not built yet. Skipped while a fetch runs,
    which processes the queues itself."""
    async with fetch_lock(get_sessionmaker()) as got:
        if not got:
            logger.info("Queue run skipped: a fetch is in progress")
            return None
        report = await build_correspondence(gateway).process()
        try:
            await backfill_description_mentions(get_sessionmaker())
        except Exception:
            # A cache is an optimisation: Feeds fall back to reading descriptions.
            logger.exception("Description mention backfill failed; it resumes next run")
        return report


async def extract_skills_now(gateway: BaseAIGateway | None = None) -> None:
    """Right after a User changes Preferences, so new Feed cards get Skill Gaps soon."""
    async with fetch_lock(get_sessionmaker()) as got:
        if got:
            await build_correspondence(gateway).extract_skills()
