from __future__ import annotations

import re
import time
from typing import Callable

from prometheus_client import Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match
from starlette.types import ASGIApp

UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


def normalize_path(path: str) -> str:
    if path.startswith("/share/"):
        return "/share/{token}"
    if path.startswith("/api/v1/share/"):
        return "/api/v1/share/{token}"
    return UUID_PATTERN.sub("{id}", path)


def render_metrics() -> bytes:
    return generate_latest()


class PrometheusMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, enabled: bool = True) -> None:
        super().__init__(app)
        self._enabled = enabled

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self._enabled or request.url.path == "/metrics":
            return await call_next(request)

        route_path = _resolve_route_path(request)
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        HTTP_REQUESTS_TOTAL.labels(request.method, route_path, str(response.status_code)).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(request.method, route_path).observe(duration)
        return response


def _resolve_route_path(request: Request) -> str:
    for route in request.app.routes:
        match, _ = route.matches(request.scope)
        if match is Match.FULL:
            return normalize_path(getattr(route, "path", request.url.path))
    return normalize_path(request.url.path)
