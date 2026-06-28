"""
Logging + correlation ID middleware.
"""
from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger, set_correlation_id

logger = get_logger(__name__)

EXCLUDED_PATHS = {"/api/v1/health/live", "/api/v1/health/ready", "/favicon.ico"}


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    - Injects X-Correlation-ID header (uses existing or generates one)
    - Logs every request with method, path, status, duration
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip noisy probe endpoints
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        set_correlation_id(cid)
        start = time.perf_counter()

        response: Response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Correlation-ID"] = cid
        response.headers["X-Response-Time"]  = f"{duration_ms}ms"

        logger.info(
            "HTTP request",
            extra={
                "method":      request.method,
                "path":        request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_ip":   request.client.host if request.client else None,
                "user_agent":  request.headers.get("User-Agent", ""),
            },
        )
        return response
