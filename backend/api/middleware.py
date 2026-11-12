"""Cookie-session CSRF protection.

Bearer-token requests are not vulnerable to classic CSRF and are exempt. When a
request is authenticated by the HttpOnly session cookie, every unsafe method
must also present the double-submit CSRF value in ``X-CSRF-Token``.
"""

from __future__ import annotations

import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.api.deps import ACCESS_COOKIE_NAME
from backend.config import get_settings

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_EXEMPT_PATHS = {"/auth/login", "/auth/register"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        path = request.url.path
        if (
            request.method in _SAFE_METHODS
            or path in _EXEMPT_PATHS
            or request.headers.get("authorization")
            or ACCESS_COOKIE_NAME not in request.cookies
        ):
            return await call_next(request)

        cookie_token = request.cookies.get(settings.csrf_cookie_name, "")
        header_token = request.headers.get(settings.csrf_header_name, "")
        if (
            not cookie_token
            or not header_token
            or not secrets.compare_digest(cookie_token, header_token)
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing or invalid"},
            )
        return await call_next(request)
