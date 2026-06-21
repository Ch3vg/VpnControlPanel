from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from panel.api.main import create_app
from panel.config import PanelSettings


@pytest.mark.asyncio
async def test_admin_ui_index(panel_settings: PanelSettings) -> None:
    app = create_app(panel_settings, with_db=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/admin")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "VPN Control Panel" in response.text


@pytest.mark.asyncio
async def test_admin_ui_static_assets(panel_settings: PanelSettings) -> None:
    app = create_app(panel_settings, with_db=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        css = await client.get("/admin/static/css/app.css")
        api_js = await client.get("/admin/static/js/api.js")
    assert css.status_code == 200
    assert "background" in css.text
    assert api_js.status_code == 200
    assert "ApiClient" in api_js.text


@pytest.mark.asyncio
async def test_admin_ui_spa_fallback(panel_settings: PanelSettings) -> None:
    app = create_app(panel_settings, with_db=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/admin/configs/abc")
    assert response.status_code == 200
    assert "VPN Control Panel" in response.text


@pytest.mark.asyncio
async def test_admin_ui_disabled(panel_settings: PanelSettings) -> None:
    settings = panel_settings.model_copy(
        update={"web": panel_settings.web.model_copy(update={"enabled": False})},
    )
    app = create_app(settings, with_db=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/admin")
    assert response.status_code == 404
