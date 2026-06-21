from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_configs_runtime(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_config: uuid.UUID,
) -> None:
    with patch(
        "panel.application.get_config_runtime.probe_config_runtime",
        return_value=__import__(
            "panel.infrastructure.vpn.service_runtime",
            fromlist=["ServiceRuntimeProbe"],
        ).ServiceRuntimeProbe(
            online=True,
            systemd_active=True,
            port_listening=True,
            detail=None,
        ),
    ):
        response = await api_client.get("/api/v1/configs/runtime", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["config_id"] == str(sample_config)
    assert body["items"][0]["online"] is True


@pytest.mark.asyncio
async def test_get_config_status_includes_runtime(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_config: uuid.UUID,
) -> None:
    with patch(
        "panel.application.get_config_status.probe_config_runtime",
        return_value=__import__(
            "panel.infrastructure.vpn.service_runtime",
            fromlist=["ServiceRuntimeProbe"],
        ).ServiceRuntimeProbe(
            online=False,
            systemd_active=True,
            port_listening=False,
            detail="port 8443 not listening",
        ),
    ):
        response = await api_client.get(
            f"/api/v1/configs/{sample_config}/status",
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["runtime_online"] is False
    assert body["runtime_detail"] == "port 8443 not listening"
