from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from panel.api.main import create_app
from panel.config import PanelSettings
from panel.infrastructure.persistence.database import create_session_factory
from panel.infrastructure.persistence.models import Base
from panel.infrastructure.persistence.repositories.user import UserRepository
from panel.infrastructure.security import hash_password
from panel.infrastructure.vpn.default_profiles import default_vpn_profiles, templates_path_from_repo

pytest_plugins = ["tests.conftest_configs"]


@pytest.fixture
def panel_config_dict(tmp_path: Path) -> dict:
    return {
        "app": {"name": "test-panel", "max_secure": True, "environment": "development"},
        "server": {"host": "127.0.0.1", "port": 8000},
        "database": {"url": "sqlite+aiosqlite:///:memory:"},
        "security": {
            "secret_key": "a" * 32,
            "encryption_key": "b" * 32,
            "jwt_algorithm": "HS256",
            "jwt_expire_minutes": 60,
        },
        "broker": {
            "url": "http://127.0.0.1:8001",
            "api_key": "c" * 32,
        },
        "worker": {
            "worker_id": "test-worker",
            "task_types": ["config.initialize"],
        },
        "paths": {
            "configs": str(tmp_path / "vpn-configs"),
            "templates": str(templates_path_from_repo()),
        },
        "rate_limit": {
            "login": {"max_attempts": 5, "window_seconds": 900},
            "share": {"max_requests": 30, "window_seconds": 60},
        },
        "audit": {"enabled": True, "log_failed_login": True},
        "vpn": {
            "public_host": "127.0.0.1",
            "profiles": default_vpn_profiles(cert_dir=str(tmp_path / "certs")),
        },
    }


@pytest.fixture
def panel_settings(panel_config_dict: dict) -> PanelSettings:
    return PanelSettings.model_validate(panel_config_dict)


@pytest.fixture
def panel_config_file(tmp_path: Path, panel_config_dict: dict) -> Path:
    path = tmp_path / "panel.yaml"
    path.write_text(yaml.safe_dump(panel_config_dict), encoding="utf-8")
    return path


@pytest.fixture
def broker_config_file(tmp_path: Path) -> Path:
    path = tmp_path / "broker.yaml"
    data = {
        "server": {"host": "127.0.0.1", "port": 8001},
        "database": {"dsn": "sqlite+aiosqlite:///./data/test-broker.db"},
        "queue": {"default_lock_ttl_seconds": 180},
        "security": {"api_key": "d" * 32},
        "logging": {"level": "INFO"},
    }
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


@pytest.fixture
async def db_engine(panel_settings: PanelSettings) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(panel_settings.database.url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = create_session_factory(db_engine)
    async with factory() as session:
        yield session


@pytest.fixture
async def api_client(panel_settings: PanelSettings, db_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    app = create_app(panel_settings, with_db=False)
    app.state.settings = panel_settings
    app.state.engine = db_engine
    app.state.session_factory = create_session_factory(db_engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> tuple[str, str, uuid.UUID]:
    username = "admin"
    password = "super-secret-password"
    user = await UserRepository(db_session).create(username, hash_password(password))
    await db_session.commit()
    return username, password, user.id
