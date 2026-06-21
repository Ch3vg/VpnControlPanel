from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panel.domain.value_objects.config_status import ConfigStatus
from panel.domain.value_objects.protocol import VpnProtocolType
from panel.infrastructure.persistence.models import AuditLogModel, VpnConfigModel, VpnConfigVersionModel
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository


@pytest.fixture
async def auth_headers(api_client: AsyncClient, admin_user: tuple[str, str, uuid.UUID]) -> dict[str, str]:
    username, password, _ = admin_user
    response = await api_client.post("/auth/login", json={"username": username, "password": password})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def sample_config(
    db_session: AsyncSession,
    admin_user: tuple[str, str, uuid.UUID],
) -> uuid.UUID:
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
        name="Office",
        protocol=VpnProtocolType.XRAY,
        status=ConfigStatus.ACTIVE,
        created_by=user_id,
        version=version,
    )
    await db_session.commit()
    return config.id


@pytest.fixture
async def second_config(
    db_session: AsyncSession,
    admin_user: tuple[str, str, uuid.UUID],
) -> uuid.UUID:
    _, _, user_id = admin_user
    repo = VpnConfigRepository(db_session)
    version = VpnConfigVersionModel(
        version=1,
        port=8443,
        private_key="encrypted-private-2",
        public_key="public-key-2",
        cert_fingerprint="fp:def",
        config_data={},
    )
    config = await repo.create_with_version(
        name="Home",
        protocol=VpnProtocolType.HYSTERIA2,
        status=ConfigStatus.PENDING,
        created_by=user_id,
        version=version,
    )
    await db_session.commit()
    return config.id
