from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panel.infrastructure.persistence.models import AuditLogModel, VpnConfigModel


@pytest.mark.asyncio
async def test_list_configs_requires_auth(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/configs")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_configs(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_config: uuid.UUID,
    second_config: uuid.UUID,
) -> None:
    response = await api_client.get("/api/v1/configs", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    ids = {item["id"] for item in body["items"]}
    assert str(sample_config) in ids
    assert str(second_config) in ids


@pytest.mark.asyncio
async def test_list_configs_filter_protocol(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_config: uuid.UUID,
    second_config: uuid.UUID,
) -> None:
    response = await api_client.get(
        "/api/v1/configs",
        headers=auth_headers,
        params={"protocol": "xray"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(sample_config)
    assert body["items"][0]["protocol"] == "xray"


@pytest.mark.asyncio
async def test_get_config(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_config: uuid.UUID,
) -> None:
    response = await api_client.get(f"/api/v1/configs/{sample_config}", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Office"
    assert body["status"] == "active"
    assert body["current_version"] == 1
    assert body["current_version_detail"]["port"] == 443
    assert body["current_version_detail"]["public_key"] == "public-key-value"
    assert "private_key" not in body
    assert "private_key" not in body["current_version_detail"]


@pytest.mark.asyncio
async def test_get_config_not_found(api_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await api_client.get(f"/api/v1/configs/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_config_soft_delete(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_config: uuid.UUID,
    second_config: uuid.UUID,
    db_session: AsyncSession,
) -> None:
    response = await api_client.delete(f"/api/v1/configs/{sample_config}", headers=auth_headers)
    assert response.status_code == 204

    result = await db_session.execute(select(VpnConfigModel).where(VpnConfigModel.id == sample_config))
    model = result.scalar_one()
    assert model.is_active is False

    get_response = await api_client.get(f"/api/v1/configs/{sample_config}", headers=auth_headers)
    assert get_response.status_code == 404

    list_response = await api_client.get("/api/v1/configs", headers=auth_headers)
    assert list_response.json()["total"] == 1


@pytest.mark.asyncio
async def test_delete_config_audit(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_config: uuid.UUID,
    db_session: AsyncSession,
) -> None:
    await api_client.delete(f"/api/v1/configs/{sample_config}", headers=auth_headers)
    result = await db_session.execute(
        select(AuditLogModel).where(AuditLogModel.event_type == "config.deleted"),
    )
    row = result.scalar_one()
    assert row.payload["config_id"] == str(sample_config)
    assert row.user_id is not None


@pytest.mark.asyncio
async def test_delete_config_not_found(api_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await api_client.delete(f"/api/v1/configs/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404
