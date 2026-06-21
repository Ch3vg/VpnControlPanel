from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from panel.api.main import create_app
from panel.config import PanelSettings
from panel.infrastructure.persistence.database import create_session_factory
from panel.infrastructure.persistence.models import AuditLogModel
from panel.infrastructure.security import JwtService, hash_password, verify_password


def test_hash_and_verify_password() -> None:
    hashed = hash_password("secret-password")
    assert hashed != "secret-password"
    assert verify_password("secret-password", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_roundtrip(panel_settings: PanelSettings) -> None:
    service = JwtService(panel_settings.security)
    user_id = uuid.uuid4()
    token = service.create_access_token(user_id)
    assert service.decode_access_token(token) == user_id


@pytest.mark.asyncio
async def test_login_success(api_client: AsyncClient, admin_user: tuple[str, str, uuid.UUID]) -> None:
    username, password, _ = admin_user
    response = await api_client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


@pytest.mark.asyncio
async def test_login_invalid_credentials(api_client: AsyncClient, admin_user: tuple[str, str, uuid.UUID]) -> None:
    username, _, _ = admin_user
    response = await api_client.post("/auth/login", json={"username": username, "password": "wrong"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_login_unknown_user_same_error(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/auth/login",
        json={"username": "nobody", "password": "wrong"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_failed_login_audit(
    api_client: AsyncClient,
    admin_user: tuple[str, str, uuid.UUID],
    db_session: AsyncSession,
) -> None:
    username, _, _ = admin_user
    await api_client.post("/auth/login", json={"username": username, "password": "wrong"})
    result = await db_session.execute(
        select(AuditLogModel).where(AuditLogModel.event_type == "auth.login.failed"),
    )
    row = result.scalar_one()
    assert row.payload["username_attempt"] == username
    assert "ip" in row.payload


@pytest.mark.asyncio
async def test_login_rate_limit(panel_config_dict: dict, db_engine: AsyncEngine) -> None:
    panel_config_dict["rate_limit"]["login"]["max_attempts"] = 2
    settings = PanelSettings.model_validate(panel_config_dict)
    app = create_app(settings, with_db=False)
    app.state.settings = settings
    app.state.engine = db_engine
    app.state.session_factory = create_session_factory(db_engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(2):
            response = await client.post("/auth/login", json={"username": "x", "password": "y"})
            assert response.status_code == 401
        response = await client.post("/auth/login", json={"username": "x", "password": "y"})
        assert response.status_code == 429


@pytest.mark.asyncio
async def test_swagger_requires_valid_jwt(
    panel_config_dict: dict,
    db_engine: AsyncEngine,
    admin_user: tuple[str, str, uuid.UUID],
) -> None:
    panel_config_dict["app"]["max_secure"] = False
    settings = PanelSettings.model_validate(panel_config_dict)
    app = create_app(settings, with_db=False)
    app.state.settings = settings
    app.state.engine = db_engine
    app.state.session_factory = create_session_factory(db_engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/docs")
        assert response.status_code == 401

        _, password, _ = admin_user
        login = await client.post("/auth/login", json={"username": "admin", "password": password})
        token = login.json()["access_token"]
        response = await client.get("/docs", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_failed_login_no_audit_when_disabled(
    panel_config_dict: dict,
    db_engine: AsyncEngine,
    admin_user: tuple[str, str, uuid.UUID],
) -> None:
    panel_config_dict["audit"]["log_failed_login"] = False
    settings = PanelSettings.model_validate(panel_config_dict)
    app = create_app(settings, with_db=False)
    app.state.settings = settings
    app.state.engine = db_engine
    app.state.session_factory = create_session_factory(db_engine)
    transport = ASGITransport(app=app)
    username, _, _ = admin_user
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/auth/login", json={"username": username, "password": "wrong"})

    async with create_session_factory(db_engine)() as session:
        result = await session.execute(
            select(AuditLogModel).where(AuditLogModel.event_type == "auth.login.failed"),
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_failed_login_no_audit_when_audit_disabled(
    panel_config_dict: dict,
    db_engine: AsyncEngine,
    admin_user: tuple[str, str, uuid.UUID],
) -> None:
    panel_config_dict["audit"]["enabled"] = False
    settings = PanelSettings.model_validate(panel_config_dict)
    app = create_app(settings, with_db=False)
    app.state.settings = settings
    app.state.engine = db_engine
    app.state.session_factory = create_session_factory(db_engine)
    transport = ASGITransport(app=app)
    username, _, _ = admin_user
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/auth/login", json={"username": username, "password": "wrong"})

    async with create_session_factory(db_engine)() as session:
        result = await session.execute(
            select(AuditLogModel).where(AuditLogModel.event_type == "auth.login.failed"),
        )
        assert result.scalar_one_or_none() is None
