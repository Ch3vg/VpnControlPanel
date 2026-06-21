from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from panel.config import PanelSettings
from panel.domain.value_objects.config_profile import ConfigProfile
from panel.domain.value_objects.config_status import ConfigStatus
from panel.domain.value_objects.protocol import VpnProtocolType
from panel.infrastructure.crypto import FieldEncryptor
from panel.infrastructure.persistence.database import create_session_factory
from panel.infrastructure.persistence.models import VpnConfigModel, VpnConfigVersionModel
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository
from panel.worker.context import WorkerContext
from panel.worker.services.config_task import run_config_initialize


@pytest.mark.asyncio
async def test_config_initialize_handler(
    panel_settings: PanelSettings,
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    admin_user: tuple[str, str, uuid.UUID],
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    panel_settings.paths.configs = tmp_path
    if not panel_settings.paths.templates.is_absolute():
        from panel.infrastructure.vpn.default_profiles import templates_path_from_repo

        panel_settings.paths.templates = templates_path_from_repo()
    monkeypatch.setattr("panel.infrastructure.vpn.config_builder.reload_service", lambda _service: None)

    _, _, user_id = admin_user
    repo = VpnConfigRepository(db_session)
    config = await repo.create_pending(
        name="Office",
        protocol=VpnProtocolType.XRAY,
        profile=ConfigProfile.XRAY_REALITY,
        created_by=user_id,
    )
    await db_session.commit()

    ctx = WorkerContext(
        settings=panel_settings,
        session_factory=create_session_factory(db_engine),
        encryptor=FieldEncryptor(panel_settings.security.encryption_key),
    )
    payload = {
        "config_id": str(config.id),
        "protocol": "xray",
        "profile": "xray-reality",
        "name": "Office",
        "requested_by": str(user_id),
        "target_version": 1,
    }
    await run_config_initialize(payload, ctx)

    async with create_session_factory(db_engine)() as session:
        result = await session.execute(select(VpnConfigModel).where(VpnConfigModel.id == config.id))
        model = result.scalar_one()
        assert model.status == ConfigStatus.ACTIVE.value
        assert model.current_version == 1

        versions = await session.execute(
            select(VpnConfigVersionModel).where(VpnConfigVersionModel.config_id == config.id),
        )
        version = versions.scalar_one()
        assert version.port > 0
        encryptor = FieldEncryptor(panel_settings.security.encryption_key)
        decrypted = encryptor.decrypt(version.private_key)
        assert decrypted
        assert version.public_key
        assert version.config_data

    config_file = tmp_path / str(config.id) / "config.json"
    assert config_file.is_file()
    written = json.loads(config_file.read_text(encoding="utf-8"))
    assert written["inbounds"]
