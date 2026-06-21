from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from panel.infrastructure.system.resources import (
    ResourceSnapshot,
    SystemResourcesSnapshot,
    collect_system_resources,
)


def test_collect_system_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "panel.infrastructure.system.resources.psutil.cpu_percent",
        lambda interval=0: 42.5,
    )
    monkeypatch.setattr(
        "panel.infrastructure.system.resources.psutil.virtual_memory",
        lambda: SimpleNamespace(percent=55.0, used=8_000_000_000, total=16_000_000_000),
    )
    monkeypatch.setattr(
        "panel.infrastructure.system.resources.psutil.swap_memory",
        lambda: SimpleNamespace(percent=10.0, used=512_000_000, total=4_000_000_000),
    )
    monkeypatch.setattr(
        "panel.infrastructure.system.resources.psutil.disk_usage",
        lambda path: SimpleNamespace(percent=70.0, used=70_000_000_000, total=100_000_000_000),
    )

    snapshot = collect_system_resources("/opt/vpn/configs")

    assert snapshot.cpu_percent == 42.5
    assert snapshot.memory.percent == 55.0
    assert snapshot.memory.used_bytes == 8_000_000_000
    assert snapshot.swap.percent == 10.0
    assert snapshot.disk.percent == 70.0
    assert snapshot.disk_path == "/opt/vpn/configs"


@pytest.mark.asyncio
async def test_system_resources_requires_auth(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/system/resources")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_system_resources_endpoint(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    snapshot = SystemResourcesSnapshot(
        cpu_percent=12.3,
        memory=ResourceSnapshot(45.0, 4_000_000_000, 8_000_000_000),
        swap=ResourceSnapshot(0.0, 0, 0),
        disk=ResourceSnapshot(60.0, 60_000_000_000, 100_000_000_000),
        disk_path="/opt/vpn/configs",
    )

    with patch(
        "panel.api.routers.system.get_system_resources",
        new=AsyncMock(return_value=snapshot),
    ):
        response = await api_client.get("/api/v1/system/resources", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["cpu"]["percent"] == 12.3
    assert body["memory"]["percent"] == 45.0
    assert body["memory"]["used_bytes"] == 4_000_000_000
    assert body["swap"]["percent"] == 0.0
    assert body["disk"]["percent"] == 60.0
    assert body["disk_path"] == "/opt/vpn/configs"
