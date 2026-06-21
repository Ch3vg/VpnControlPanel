from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from panel.domain.ports.broker import PublishedTask, TaskStatus
from panel.domain.value_objects.config_status import ConfigStatus
from panel.infrastructure.persistence.database import create_session_factory
from panel.infrastructure.persistence.models import AuditLogModel, VpnConfigModel


@pytest.mark.asyncio
@patch("panel.api.routers.configs.HttpBrokerClient")
async def test_create_config_returns_task_id(
    mock_broker_cls: AsyncMock,
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    db_engine: AsyncEngine,
) -> None:
    mock_broker = AsyncMock()
    mock_broker.publish_task.return_value = PublishedTask(task_id="task-abc-123")
    mock_broker.close = AsyncMock()
    mock_broker_cls.return_value = mock_broker

    response = await api_client.post(
        "/api/v1/configs",
        headers=auth_headers,
        json={"name": "Office", "protocol": "xray"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["task_id"] == "task-abc-123"
    assert body["config_id"]

    async with create_session_factory(db_engine)() as verify_session:
        result = await verify_session.execute(select(VpnConfigModel))
        model = result.scalar_one()
        assert model.name == "Office"
        assert model.status == ConfigStatus.PENDING.value
        assert model.last_task_id == "task-abc-123"
        assert model.current_version is None

        audit = await verify_session.execute(
            select(AuditLogModel).where(AuditLogModel.event_type == "config.created"),
        )
        assert audit.scalar_one_or_none() is not None

    mock_broker.publish_task.assert_awaited_once()
    call_kwargs = mock_broker.publish_task.await_args
    assert call_kwargs.args[0] == "config.initialize"
    payload = call_kwargs.args[1]
    assert payload["name"] == "Office"
    assert payload["protocol"] == "xray"
    assert payload["profile"] == "xray-reality"
    assert payload["target_version"] == 1
    assert payload["config_id"] == body["config_id"]
    assert payload["requested_by"]
    assert "private_key" not in payload
    assert "password" not in payload


@pytest.mark.asyncio
async def test_create_config_requires_auth(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/configs",
        json={"name": "Office", "protocol": "xray"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
@patch("panel.api.routers.configs.HttpBrokerClient")
async def test_get_config_status(
    mock_broker_cls: AsyncMock,
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    admin_user: tuple[str, str, uuid.UUID],
) -> None:
    _, _, user_id = admin_user
    config_id = uuid.uuid4()
    db_session.add(
        VpnConfigModel(
            id=config_id,
            name="Office",
            protocol="xray",
            status=ConfigStatus.PENDING.value,
            last_task_id="broker-task-1",
            is_active=True,
            created_by=user_id,
            updated_by=user_id,
        ),
    )
    await db_session.commit()

    mock_broker = AsyncMock()
    mock_broker.get_status.return_value = TaskStatus(
        task_id="broker-task-1",
        status="PENDING",
        retries=0,
        max_retries=3,
    )
    mock_broker.close = AsyncMock()
    mock_broker_cls.return_value = mock_broker

    response = await api_client.get(
        f"/api/v1/configs/{config_id}/status",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == "broker-task-1"
    assert body["task_status"] == "PENDING"
    assert body["status"] == "pending"
