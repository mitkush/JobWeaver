"""Double-submit CSRF check for cookie-authenticated, state-changing API requests."""

import hmac

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.api.deps import CSRF_COOKIE, CSRF_HEADER

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        # /api/internal/ is called by cron with its own secret, never by a browser.
        if (
            request.method not in SAFE_METHODS
            and path.startswith("/api/")
            and not path.startswith("/api/internal/")
        ):
            cookie = request.cookies.get(CSRF_COOKIE, "")
            header = request.headers.get(CSRF_HEADER, "")
            if not cookie or not hmac.compare_digest(cookie, header):
                return JSONResponse(
                    {"error": {"code": "csrf_failed", "message": "Please reload the page"}},
                    status_code=403,
                )
        return await call_next(request)
