from __future__ import annotations

from fastapi import APIRouter, Response

from panel.infrastructure.observability.metrics import render_metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics() -> Response:
    return Response(content=render_metrics(), media_type="text/plain; version=0.0.4; charset=utf-8")
