from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from panel.api.main import create_app
from panel.config import PanelSettings
from panel.infrastructure.persistence.database import create_session_factory
from panel.infrastructure.vpn.default_profiles import templates_path_from_repo


@pytest.fixture
def editable_templates(tmp_path: Path, panel_config_dict: dict) -> tuple[dict, Path]:
    dest = tmp_path / "templates"
    shutil.copytree(templates_path_from_repo(), dest)
    panel_config_dict["paths"]["templates"] = str(dest)
    return panel_config_dict, dest


@pytest.fixture
async def templates_client(
    editable_templates: tuple[dict, Path],
    db_engine: AsyncEngine,
    admin_user: tuple[str, str, uuid.UUID],
) -> AsyncIterator[tuple[AsyncClient, dict[str, str], Path]]:
    panel_config_dict, templates_dir = editable_templates
    settings = PanelSettings.model_validate(panel_config_dict)
    app = create_app(settings, with_db=False)
    app.state.settings = settings
    app.state.engine = db_engine
    app.state.session_factory = create_session_factory(db_engine)
    transport = ASGITransport(app=app)
    username, password, _ = admin_user
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post("/auth/login", json={"username": username, "password": password})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        yield client, headers, templates_dir


@pytest.mark.asyncio
async def test_list_templates(
    templates_client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    client, headers, templates_dir = templates_client
    response = await client.get("/api/v1/templates", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert items
    for item in items:
        assert item["exists"] is True
        assert item["format"] in {"json", "yaml"}
        assert Path(item["path"]).resolve().is_relative_to(templates_dir.resolve())


@pytest.mark.asyncio
async def test_get_and_update_template(
    templates_client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    client, headers, templates_dir = templates_client
    listed = await client.get("/api/v1/templates", headers=headers)
    profile = next(item["profile"] for item in listed.json()["items"] if item["format"] == "json")

    current = await client.get(f"/api/v1/templates/{profile}", headers=headers)
    assert current.status_code == 200
    body = current.json()
    assert body["profile"] == profile
    assert body["format"] == "json"
    assert body["content"]

    data = json.loads(body["content"])
    data["_panel_template_edit"] = True
    content = json.dumps(data, indent=2)

    updated = await client.put(
        f"/api/v1/templates/{profile}",
        headers=headers,
        json={"content": content},
    )
    assert updated.status_code == 200
    assert '"_panel_template_edit"' in updated.json()["content"]
    path = Path(updated.json()["path"])
    assert path.resolve().is_relative_to(templates_dir.resolve())
    assert "_panel_template_edit" in path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_update_template_rejects_invalid_json(
    templates_client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    client, headers, _ = templates_client
    listed = await client.get("/api/v1/templates", headers=headers)
    profile = next(item["profile"] for item in listed.json()["items"] if item["format"] == "json")

    response = await client.put(
        f"/api/v1/templates/{profile}",
        headers=headers,
        json={"content": "{not-json"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_unknown_profile(
    templates_client: tuple[AsyncClient, dict[str, str], Path],
) -> None:
    client, headers, _ = templates_client
    response = await client.get("/api/v1/templates/no-such-profile", headers=headers)
    assert response.status_code == 404
