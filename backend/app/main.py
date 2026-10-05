import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import adapters  # noqa: F401  (registers Source Adapters)
from app.api import auth, fact_bank, health, me, preferences
from app.api.csrf import CSRFMiddleware
from app.core.config import get_settings
from app.core.db import dispose_engine
from app.core.errors import JobWeaverError
from app.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if get_settings().scheduler_enabled:
        start_scheduler()
    yield
    stop_scheduler()
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(title="JobWeaver", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CSRFMiddleware)

    @app.exception_handler(JobWeaverError)
    async def _handle(_: Request, exc: JobWeaverError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status_code
        )

    for module in (health, auth, me, fact_bank, preferences):
        app.include_router(module.router)

    if FRONTEND_DIST.is_dir():
        _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """One service serves the API and the built SPA: one URL, no CORS (ADR-0008)."""
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
    index = FRONTEND_DIST / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        candidate = (FRONTEND_DIST / path).resolve()
        if path and candidate.is_file() and FRONTEND_DIST in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
