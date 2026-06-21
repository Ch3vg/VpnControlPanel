from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panel.domain.ports.broker import PublishedTask
from panel.domain.value_objects.config_status import ConfigStatus
from panel.domain.value_objects.protocol import VpnProtocolType
from panel.infrastructure.persistence.models import AuditLogModel, VpnConfigModel, VpnConfigVersionModel
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository


@pytest.fixture
def mock_broker() -> AsyncMock:
    broker = AsyncMock()
    task_counter = {"value": 0}

    async def publish_task(task_type: str, payload: dict) -> PublishedTask:
        task_counter["value"] += 1
        return PublishedTask(task_id=f"task-{task_counter['value']}")

    broker.publish_task.side_effect = publish_task
    broker.close = AsyncMock()
    return broker


@pytest.mark.asyncio
@patch("panel.api.routers.configs.HttpBrokerClient")
async def test_regenerate_all_configs(
    mock_broker_cls: AsyncMock,
    mock_broker: AsyncMock,
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_config: uuid.UUID,
    second_config: uuid.UUID,
    db_session: AsyncSession,
) -> None:
    mock_broker_cls.return_value = mock_broker

    response = await api_client.post("/api/v1/configs/regenerate-all", headers=auth_headers)
    assert response.status_code == 202
    body = response.json()
    assert len(body["queued"]) == 1
    assert body["queued"][0]["config_id"] == str(sample_config)
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["config_id"] == str(second_config)

    result = await db_session.execute(select(VpnConfigModel).where(VpnConfigModel.id == sample_config))
    assert result.scalar_one().status == ConfigStatus.PENDING.value


@pytest.mark.asyncio
@patch("panel.api.routers.configs.HttpBrokerClient")
async def test_regenerate_all_configs_audit(
    mock_broker_cls: AsyncMock,
    mock_broker: AsyncMock,
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_config: uuid.UUID,
    db_session: AsyncSession,
) -> None:
    mock_broker_cls.return_value = mock_broker

    await api_client.post("/api/v1/configs/regenerate-all", headers=auth_headers)
    result = await db_session.execute(
        select(AuditLogModel).where(AuditLogModel.event_type == "config.regenerate_all.requested"),
    )
    row = result.scalar_one()
    assert row.payload["queued_count"] == 1


@pytest.mark.asyncio
async def test_regenerate_all_configs_requires_auth(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/v1/configs/regenerate-all")
    assert response.status_code == 401


@pytest.mark.asyncio
@patch("panel.api.routers.configs.HttpBrokerClient")
async def test_regenerate_all_skips_busy_config(
    mock_broker_cls: AsyncMock,
    mock_broker: AsyncMock,
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    admin_user: tuple[str, str, uuid.UUID],
) -> None:
    mock_broker_cls.return_value = mock_broker

    _, _, user_id = admin_user
    repo = VpnConfigRepository(db_session)
    version = VpnConfigVersionModel(
        version=1,
        port=443,
        private_key="encrypted-private",
        public_key="public-key-value",
        cert_fingerprint="fp:abc",
        config_data={"inbound": "test"},
    )
    config = await repo.create_with_version(
        name="Busy",
        protocol=VpnProtocolType.XRAY,
        status=ConfigStatus.PROCESSING,
        created_by=user_id,
        version=version,
    )
    await db_session.commit()

    response = await api_client.post("/api/v1/configs/regenerate-all", headers=auth_headers)
    body = response.json()
    skipped_ids = {item["config_id"] for item in body["skipped"]}
    assert str(config.id) in skipped_ids
