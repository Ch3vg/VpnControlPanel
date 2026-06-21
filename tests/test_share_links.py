from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from panel.domain.value_objects.config_profile import ConfigProfile
from panel.domain.value_objects.config_status import ConfigStatus
from panel.domain.value_objects.protocol import VpnProtocolType
from panel.infrastructure.crypto import FieldEncryptor
from panel.infrastructure.crypto.config_data import encrypt_config_data_fields
from panel.infrastructure.persistence.database import create_session_factory
from panel.infrastructure.persistence.models import AuditLogModel, ShareTokenModel, VpnConfigModel, VpnConfigVersionModel
from panel.infrastructure.persistence.repositories.share_token import ShareTokenRepository
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository
from panel.infrastructure.security.share_token import generate_share_token, hash_share_token
from panel.infrastructure.vpn.config_builder import ProfileConfigBuilder


@pytest.fixture
async def xray_share_config(
    db_session: AsyncSession,
    admin_user: tuple[str, str, uuid.UUID],
    panel_settings,
) -> tuple[uuid.UUID, dict]:
    _, _, user_id = admin_user
    encryptor = FieldEncryptor(panel_settings.security.encryption_key)
    builder = ProfileConfigBuilder(panel_settings)
    result = builder.build(ConfigProfile.XRAY_REALITY, name="Office")
    result.config_data["inbounds"][0]["port"] = 10443
    result.port = 10443
    config_stored = encrypt_config_data_fields(
        result.config_data,
        builder.sensitive_fields(ConfigProfile.XRAY_REALITY),
        encryptor,
    )

    repo = VpnConfigRepository(db_session)
    version = VpnConfigVersionModel(
        version=1,
        port=10443,
        private_key=encryptor.encrypt(result.private_key),
        public_key=result.public_key,
        cert_fingerprint="fp:test",
        config_data=config_stored,
    )
    config = await repo.create_with_version(
        name="Office",
        protocol=VpnProtocolType.XRAY,
        status=ConfigStatus.ACTIVE,
        created_by=user_id,
        version=version,
    )
    await db_session.commit()
    return config.id, result.config_data


@pytest.mark.asyncio
async def test_create_share_link(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    xray_share_config: tuple[uuid.UUID, dict],
    db_engine: AsyncEngine,
) -> None:
    config_id, _ = xray_share_config
    response = await api_client.post(
        f"/api/v1/configs/{config_id}/share",
        headers=auth_headers,
        json={"is_permanent": True},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["token"]
    assert body["url"].endswith(f"/share/{body['token']}")

    async with create_session_factory(db_engine)() as session:
        result = await session.execute(select(ShareTokenModel))
        row = result.scalar_one()
        assert row.token_hash == hash_share_token(body["token"])
        assert row.token_hash != body["token"]
        assert row.config_id == config_id
        assert row.config_version == 1
        assert row.is_permanent is True

        audit = await session.execute(
            select(AuditLogModel).where(AuditLogModel.event_type == "share.created"),
        )
        assert audit.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_create_share_requires_auth(
    api_client: AsyncClient,
    xray_share_config: tuple[uuid.UUID, dict],
) -> None:
    config_id, _ = xray_share_config
    response = await api_client.post(
        f"/api/v1/configs/{config_id}/share",
        json={"is_permanent": True},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_share_conflict_when_not_active(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    second_config: uuid.UUID,
) -> None:
    response = await api_client.post(
        f"/api/v1/configs/{second_config}/share",
        headers=auth_headers,
        json={"is_permanent": True},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_resolve_share_returns_uris(
    api_client: AsyncClient,
    xray_share_config: tuple[uuid.UUID, dict],
    db_engine: AsyncEngine,
) -> None:
    config_id, _ = xray_share_config
    raw_token = generate_share_token()
    async with create_session_factory(db_engine)() as session:
        _, _, user_id = await _get_admin(session)
        await ShareTokenRepository(session).create(
            token_hash=hash_share_token(raw_token),
            config_id=config_id,
            config_version=1,
            is_permanent=True,
            expires_at=None,
            created_by=user_id,
        )
        await session.commit()

    response = await api_client.get(f"/share/{raw_token}")
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    uris = response.json()
    assert len(uris) == 1
    assert uris[0].startswith("vless://")
    assert "10443" in uris[0]

    async with create_session_factory(db_engine)() as session:
        result = await session.execute(select(ShareTokenModel))
        row = result.scalar_one()
        assert row.access_count == 1
        assert row.last_accessed_at is not None


@pytest.mark.asyncio
async def test_resolve_share_not_found(api_client: AsyncClient) -> None:
    response = await api_client.get("/share/unknown-token-value")
    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"


@pytest.mark.asyncio
async def test_resolve_share_expired(
    api_client: AsyncClient,
    xray_share_config: tuple[uuid.UUID, dict],
    db_engine: AsyncEngine,
) -> None:
    config_id, _ = xray_share_config
    raw_token = generate_share_token()
    async with create_session_factory(db_engine)() as session:
        _, _, user_id = await _get_admin(session)
        model = ShareTokenModel(
            token_hash=hash_share_token(raw_token),
            config_id=config_id,
            config_version=1,
            is_permanent=False,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
            created_by=user_id,
        )
        session.add(model)
        await session.commit()

    response = await api_client.get(f"/share/{raw_token}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_revoke_share(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    xray_share_config: tuple[uuid.UUID, dict],
    db_engine: AsyncEngine,
) -> None:
    config_id, _ = xray_share_config
    raw_token = generate_share_token()
    async with create_session_factory(db_engine)() as session:
        _, _, user_id = await _get_admin(session)
        await ShareTokenRepository(session).create(
            token_hash=hash_share_token(raw_token),
            config_id=config_id,
            config_version=1,
            is_permanent=True,
            expires_at=None,
            created_by=user_id,
        )
        await session.commit()

    response = await api_client.delete(f"/api/v1/share/{raw_token}", headers=auth_headers)
    assert response.status_code == 204

    get_response = await api_client.get(f"/share/{raw_token}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_share_pins_config_version(
    api_client: AsyncClient,
    xray_share_config: tuple[uuid.UUID, dict],
    db_engine: AsyncEngine,
    panel_settings,
    admin_user: tuple[str, str, uuid.UUID],
) -> None:
    config_id, _ = xray_share_config
    _, _, user_id = admin_user
    raw_token = generate_share_token()
    encryptor = FieldEncryptor(panel_settings.security.encryption_key)
    builder = ProfileConfigBuilder(panel_settings)
    config_v2_result = builder.build(ConfigProfile.XRAY_REALITY, name="Office")
    config_v2_result.config_data["inbounds"][0]["port"] = 20443
    config_v2_result.port = 20443

    async with create_session_factory(db_engine)() as session:
        await ShareTokenRepository(session).create(
            token_hash=hash_share_token(raw_token),
            config_id=config_id,
            config_version=1,
            is_permanent=True,
            expires_at=None,
            created_by=user_id,
        )
        repo = VpnConfigRepository(session)
        await repo.insert_version(
            config_id=config_id,
            version=2,
            port=20443,
            private_key_encrypted=encryptor.encrypt(config_v2_result.private_key),
            public_key=config_v2_result.public_key,
            cert_fingerprint="fp:v2",
            config_data=encrypt_config_data_fields(
                config_v2_result.config_data,
                builder.sensitive_fields(ConfigProfile.XRAY_REALITY),
                encryptor,
            ),
        )
        model = await session.get(VpnConfigModel, config_id)
        assert model is not None
        model.current_version = 2
        await session.commit()

    response = await api_client.get(f"/share/{raw_token}")
    uris = response.json()
    assert "10443" in uris[0]
    assert "20443" not in uris[0]


async def _get_admin(session: AsyncSession) -> tuple[str, str, uuid.UUID]:
    from panel.infrastructure.persistence.models import UserModel

    result = await session.execute(select(UserModel))
    user = result.scalar_one()
    return user.username, "", user.id
