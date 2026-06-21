from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from panel.config import PanelSettings
from panel.domain.entities.user import User
from panel.domain.ports.broker import BrokerPort
from panel.domain.value_objects.config_profile import ConfigProfile
from panel.domain.value_objects.protocol import VpnProtocolType
from panel.application.audit_service import AuditService
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository


@dataclass(frozen=True, slots=True)
class CreateConfigResult:
    config_id: uuid.UUID
    task_id: str


class CreateConfigUseCase:
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

    async def execute(
        self,
        name: str,
        protocol: VpnProtocolType,
        profile: ConfigProfile,
        user: User,
    ) -> CreateConfigResult:
        if profile.value not in self._settings.vpn.profiles:
            raise ValueError(f"Unknown profile: {profile.value}")
        config = await self._configs.create_pending(
            name=name,
            protocol=protocol,
            profile=profile,
            created_by=user.id,
        )
        await self._session.commit()

        target_version = 1
        payload = {
            "config_id": str(config.id),
            "protocol": protocol.value,
            "profile": profile.value,
            "name": name,
            "requested_by": str(user.id),
            "target_version": target_version,
        }
        task = await self._broker.publish_task("config.initialize", payload)
        await self._configs.set_last_task_id(config.id, task.task_id)

        await self._audit.log(
            "config.created",
            {
                "config_id": str(config.id),
                "protocol": protocol.value,
                "profile": profile.value,
                "name": name,
                "task_id": task.task_id,
            },
            user_id=user.id,
        )

        await self._session.commit()
        return CreateConfigResult(config_id=config.id, task_id=task.task_id)
