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
    assert isinstance(body["config_data"], dict)
    assert body["config_data"]


@pytest.mark.asyncio
async def test_put_config_data(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_config: uuid.UUID,
) -> None:
    current = await api_client.get(
        f"/api/v1/configs/{sample_config}/config-data",
        headers=auth_headers,
    )
    assert current.status_code == 200
    data = current.json()["config_data"]
    data = {**data, "_edited": True}

    with patch("panel.application.update_config_data.ProfileConfigBuilder.write_files") as write_mock:
        response = await api_client.put(
            f"/api/v1/configs/{sample_config}/config-data",
            headers=auth_headers,
            json={"config_data": data},
        )
    assert response.status_code == 200
    assert response.json()["config_data"]["_edited"] is True
    write_mock.assert_called_once()

    verify = await api_client.get(
        f"/api/v1/configs/{sample_config}/config-data",
        headers=auth_headers,
    )
    assert verify.json()["config_data"]["_edited"] is True
