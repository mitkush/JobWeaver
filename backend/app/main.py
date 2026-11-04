from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app import adapters  # noqa: F401  (registers Source Adapters)
from app.api import (
    applications,
    auth,
    drafts,
    extension,
    fact_bank,
    feed,
    health,
    me,
    preferences,
    profile,
    sources,
)
from app.api.csrf import CSRFMiddleware
from app.core.config import get_settings
from app.core.db import dispose_engine, get_sessionmaker
from app.core.errors import JobWeaverError, NotFoundError
from app.core.monitoring import configure_logging, init_error_tracking
from app.core.timing import ServerTimingMiddleware
from app.gateway.factory import build_gateway
from app.scheduler import start_scheduler, stop_scheduler
from app.services.drafting import recover_queued, stop_tasks
from app.services.fetching import recover_running_fetches

configure_logging()
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await recover_running_fetches(get_sessionmaker())
    await recover_queued(build_gateway())
    from app.services.draft_workflow import recover

    await recover(build_gateway())
    if get_settings().scheduler_enabled:
        start_scheduler()
    yield
    stop_scheduler()
    await stop_tasks()
    await dispose_engine()


def create_app(frontend_dist: Path | None = FRONTEND_DIST) -> FastAPI:
    init_error_tracking(get_settings())
    app = FastAPI(title="JobWeaver", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CSRFMiddleware)
    # Outermost, so the total includes the CSRF check.
    app.add_middleware(ServerTimingMiddleware)

    @app.exception_handler(JobWeaverError)
    async def _handle(_: Request, exc: JobWeaverError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status_code
        )

    modules = (
        health,
        auth,
        me,
        fact_bank,
        preferences,
        sources,
        feed,
        drafts,
        applications,
        extension,
        profile,
    )
    for module in modules:
        app.include_router(module.router)

    if frontend_dist is not None and frontend_dist.is_dir():
        mount_frontend(app, frontend_dist)
    return app


class HashedAssets(StaticFiles):
    """Vite names every built asset after its content, so a file never changes in place:
    browsers may keep it for a year without asking again. A deploy ships new names."""

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


# The page that names the current assets: always revalidated, so a deploy shows at once.
REVALIDATE = {"Cache-Control": "no-cache"}


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """One service serves the API and the built SPA: one URL, no CORS (ADR-0008)."""
    app.mount("/assets", HashedAssets(directory=dist / "assets"), name="assets")
    root = dist.resolve()
    index = root / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:  # sync: file checks run in the threadpool
        if path == "api" or path.startswith("api/"):
            raise NotFoundError("Not found")
        if path == "manifest.webmanifest":
            manifest = root / path
            if not manifest.is_file():
                raise NotFoundError("Not found")
            return FileResponse(
                manifest,
                media_type="application/manifest+json",
                headers={"Cache-Control": "no-cache"},
            )
        candidate = (root / path).resolve()
        if path and candidate.is_file() and root in candidate.parents and candidate != index:
            return FileResponse(candidate)
        # /index.html too: whichever way the page is reached, it names the current assets.
        return FileResponse(index, headers=REVALIDATE)


app = create_app()
