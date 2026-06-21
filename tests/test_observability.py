from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from panel.api.main import create_app
from panel.config import PanelSettings
from panel.infrastructure.observability.metrics import normalize_path


def test_normalize_path_replaces_uuid_and_tokens() -> None:
    path = "/api/v1/configs/550e8400-e29b-41d4-a716-446655440000/share"
    assert normalize_path(path) == "/api/v1/configs/{id}/share"
    assert normalize_path("/share/abc-def_token") == "/share/{token}"
    assert normalize_path("/api/v1/share/abc-def_token") == "/api/v1/share/{token}"


@pytest.mark.asyncio
async def test_metrics_endpoint(panel_settings: PanelSettings) -> None:
    app = create_app(panel_settings, with_db=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/health")
        response = await client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "http_requests_total" in response.text


@pytest.mark.asyncio
async def test_metrics_disabled(panel_config_dict: dict) -> None:
    panel_config_dict["metrics"] = {"enabled": False}
    settings = PanelSettings.model_validate(panel_config_dict)
    app = create_app(settings, with_db=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_security_headers_on_response(panel_settings: PanelSettings) -> None:
    app = create_app(panel_settings, with_db=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "no-referrer"
