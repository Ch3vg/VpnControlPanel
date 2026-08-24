from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_config_data(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_config: uuid.UUID,
) -> None:
    response = await api_client.get(
        f"/api/v1/configs/{sample_config}/config-data",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["config_id"] == str(sample_config)
    assert body["version"] == 1
    assert body["format"] == "json"
    assert isinstance(body["config_data"], dict)
    assert body["content"]
    assert '"inbound"' in body["content"] or "inbound" in body["content"]


@pytest.mark.asyncio
async def test_put_config_data_content(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_config: uuid.UUID,
) -> None:
    current = await api_client.get(
        f"/api/v1/configs/{sample_config}/config-data",
        headers=auth_headers,
    )
    assert current.status_code == 200
    data = {**current.json()["config_data"], "_edited": True}
    content = __import__("json").dumps(data, indent=2)

    with patch("panel.application.update_config_data.ProfileConfigBuilder.write_files") as write_mock:
        response = await api_client.put(
            f"/api/v1/configs/{sample_config}/config-data",
            headers=auth_headers,
            json={"content": content, "format": "json"},
        )
    assert response.status_code == 200
    assert response.json()["config_data"]["_edited"] is True
    assert response.json()["format"] == "json"
    write_mock.assert_called_once()
