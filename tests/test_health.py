from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from panel.api.main import create_app
from panel.config import PanelSettings


@pytest.mark.asyncio
async def test_health_endpoint(panel_settings: PanelSettings) -> None:
    app = create_app(panel_settings, with_db=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_swagger_hidden_when_max_secure(panel_settings: PanelSettings) -> None:
    app = create_app(panel_settings, with_db=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/docs")
    assert response.status_code == 404
