from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from panel.application.configs import ConfigNotFound
from panel.config import PanelSettings
from panel.domain.entities.user import User
from panel.domain.ports.broker import BrokerPort
from panel.domain.value_objects.config_status import ConfigStatus
from panel.application.audit_service import AuditService
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository


class ConfigNotRegeneratable(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RegenerateConfigResult:
    config_id: uuid.UUID
    task_id: str


class RegenerateConfigUseCase:
    def __init__(
        self,
        settings: PanelSettings,
        session: AsyncSession,
        configs: VpnConfigRepository,
        broker: BrokerPort,
        audit: AuditService,
    ) -> None:
        self._settings = settings
        self._session = session
        self._configs = configs
        self._broker = broker
        self._audit = audit

    async def execute(self, config_id: uuid.UUID, user: User) -> RegenerateConfigResult:
        config = await self._configs.get_by_id(config_id)
        if config is None:
            raise ConfigNotFound
        if config.current_version is None:
            raise ConfigNotRegeneratable("Config has no version to regenerate")
        if config.status in (ConfigStatus.PENDING, ConfigStatus.PROCESSING):
            raise ConfigNotRegeneratable("Config is busy")

        try:
            await self._configs.prepare_regenerate(config_id, user.id)
        except ValueError as exc:
            raise ConfigNotRegeneratable(str(exc)) from exc

        protocol, profile, name, target_version = await self._configs.get_regenerate_context(config_id)
        await self._session.commit()

        payload = {
            "config_id": str(config_id),
            "protocol": protocol.value,
            "profile": profile.value,
            "name": name,
            "requested_by": str(user.id),
            "target_version": target_version,
        }
        task = await self._broker.publish_task("config.regenerate", payload)
        await self._configs.set_last_task_id(config_id, task.task_id)

        await self._audit.log(
            "config.regenerate.requested",
            {
                "config_id": str(config_id),
                "target_version": target_version,
                "task_id": task.task_id,
            },
            user_id=user.id,
        )

        await self._session.commit()
        return RegenerateConfigResult(config_id=config_id, task_id=task.task_id)
