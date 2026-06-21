from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from panel.domain.ports.broker import PublishedTask
from panel.domain.value_objects.config_status import ConfigStatus
from panel.infrastructure.persistence.database import create_session_factory
from panel.infrastructure.persistence.models import AuditLogModel, VpnConfigModel, VpnConfigVersionModel
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository


@pytest.fixture
async def active_config(
    db_session: AsyncSession,
    admin_user: tuple[str, str, uuid.UUID],
    panel_settings,
) -> uuid.UUID:
    _, _, user_id = admin_user
    from panel.domain.value_objects.config_profile import ConfigProfile
    from panel.domain.value_objects.protocol import VpnProtocolType
    from panel.infrastructure.crypto import FieldEncryptor
    from panel.infrastructure.crypto.config_data import encrypt_config_data_fields
    from panel.infrastructure.persistence.models import VpnConfigVersionModel
    from panel.infrastructure.vpn.config_builder import ProfileConfigBuilder

    builder = ProfileConfigBuilder(panel_settings)
    result = builder.build(ConfigProfile.XRAY_REALITY, name="Office")
    encryptor = FieldEncryptor(panel_settings.security.encryption_key)
    repo = VpnConfigRepository(db_session)
    version = VpnConfigVersionModel(
        version=1,
        port=result.port,
        private_key=encryptor.encrypt(result.private_key),
        public_key=result.public_key,
        cert_fingerprint="fp",
        config_data=encrypt_config_data_fields(
            result.config_data,
            builder.sensitive_fields(ConfigProfile.XRAY_REALITY),
            encryptor,
        ),
    )
    config = await repo.create_with_version(
        name="Office",
        protocol=VpnProtocolType.XRAY,
        status=ConfigStatus.ACTIVE,
        created_by=user_id,
        version=version,
    )
    model = await db_session.get(VpnConfigModel, config.id)
    assert model is not None
    model.profile = ConfigProfile.XRAY_REALITY.value
    await db_session.commit()
    return config.id


@pytest.mark.asyncio
@patch("panel.api.routers.configs.HttpBrokerClient")
async def test_regenerate_config_returns_task_id(
    mock_broker_cls: AsyncMock,
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    active_config: uuid.UUID,
    db_engine: AsyncEngine,
) -> None:
    mock_broker = AsyncMock()
    mock_broker.publish_task.return_value = PublishedTask(task_id="task-regen-1")
    mock_broker.close = AsyncMock()
    mock_broker_cls.return_value = mock_broker

    response = await api_client.post(
        f"/api/v1/configs/{active_config}/regenerate",
        headers=auth_headers,
    )
    assert response.status_code == 202
    body = response.json()
    assert body["task_id"] == "task-regen-1"
    assert body["config_id"] == str(active_config)

    async with create_session_factory(db_engine)() as session:
        result = await session.execute(select(VpnConfigModel).where(VpnConfigModel.id == active_config))
        model = result.scalar_one()
        assert model.status == ConfigStatus.PENDING.value
        assert model.last_task_id == "task-regen-1"
        assert model.current_version == 1

        versions = await session.execute(
            select(func.count()).select_from(VpnConfigVersionModel).where(
                VpnConfigVersionModel.config_id == active_config,
            ),
        )
        assert int(versions.scalar_one()) == 1

    payload = mock_broker.publish_task.await_args.args[1]
    assert payload["target_version"] == 2
    assert payload["config_id"] == str(active_config)
    assert payload["protocol"] == "xray"


@pytest.mark.asyncio
@patch("panel.api.routers.configs.HttpBrokerClient")
async def test_regenerate_config_audit(
    mock_broker_cls: AsyncMock,
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    active_config: uuid.UUID,
    db_engine: AsyncEngine,
) -> None:
    mock_broker = AsyncMock()
    mock_broker.publish_task.return_value = PublishedTask(task_id="task-regen-2")
    mock_broker.close = AsyncMock()
    mock_broker_cls.return_value = mock_broker

    await api_client.post(f"/api/v1/configs/{active_config}/regenerate", headers=auth_headers)

    async with create_session_factory(db_engine)() as session:
        result = await session.execute(
            select(AuditLogModel).where(AuditLogModel.event_type == "config.regenerate.requested"),
        )
        row = result.scalar_one()
        assert row.payload["target_version"] == 2


@pytest.mark.asyncio
async def test_regenerate_config_conflict_when_pending(
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
            current_version=1,
            is_active=True,
            created_by=user_id,
            updated_by=user_id,
        ),
    )
    await db_session.commit()

    response = await api_client.post(
        f"/api/v1/configs/{config_id}/regenerate",
        headers=auth_headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_regenerate_worker_creates_version_two(
    panel_settings,
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    active_config: uuid.UUID,
    admin_user: tuple[str, str, uuid.UUID],
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from panel.infrastructure.crypto import FieldEncryptor
    from panel.worker.context import WorkerContext
    from panel.worker.services.config_task import run_config_regenerate

    panel_settings.paths.configs = tmp_path
    monkeypatch.setattr("panel.infrastructure.vpn.config_builder.reload_service", lambda _service: None)

    _, _, user_id = admin_user
    ctx = WorkerContext(
        settings=panel_settings,
        session_factory=create_session_factory(db_engine),
        encryptor=FieldEncryptor(panel_settings.security.encryption_key),
    )
    payload = {
        "config_id": str(active_config),
        "protocol": "xray",
        "profile": "xray-reality",
        "name": "Office",
        "requested_by": str(user_id),
        "target_version": 2,
    }
    await run_config_regenerate(payload, ctx)

    async with create_session_factory(db_engine)() as session:
        result = await session.execute(select(VpnConfigModel).where(VpnConfigModel.id == active_config))
        model = result.scalar_one()
        assert model.status == ConfigStatus.ACTIVE.value
        assert model.current_version == 2

        versions = await session.execute(
            select(VpnConfigVersionModel)
            .where(VpnConfigVersionModel.config_id == active_config)
            .order_by(VpnConfigVersionModel.version),
        )
        rows = versions.scalars().all()
        assert len(rows) == 2
        assert rows[0].version == 1
        assert rows[1].version == 2
