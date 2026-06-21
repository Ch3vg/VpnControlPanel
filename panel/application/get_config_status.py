from __future__ import annotations

import uuid
from dataclasses import dataclass

from panel.application.configs import ConfigNotFound
from panel.domain.entities.vpn_config import VpnConfig
from panel.domain.ports.broker import BrokerPort
from panel.domain.value_objects.config_status import ConfigStatus
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository


@dataclass(frozen=True, slots=True)
class ConfigTaskStatus:
    config_id: uuid.UUID
    status: ConfigStatus
    task_id: str | None
    task_status: str | None
    retries: int | None
    max_retries: int | None
    error_message: str | None


class GetConfigStatusUseCase:
    def __init__(self, configs: VpnConfigRepository, broker: BrokerPort) -> None:
        self._configs = configs
        self._broker = broker

    async def execute(self, config_id: uuid.UUID) -> ConfigTaskStatus:
        config = await self._configs.get_by_id(config_id)
        if config is None:
            raise ConfigNotFound

        if not config.last_task_id:
            return ConfigTaskStatus(
                config_id=config.id,
                status=config.status,
                task_id=None,
                task_status=None,
                retries=None,
                max_retries=None,
                error_message=config.error_message,
            )

        task = await self._broker.get_status(config.last_task_id)
        return ConfigTaskStatus(
            config_id=config.id,
            status=config.status,
            task_id=config.last_task_id,
            task_status=task.status,
            retries=task.retries,
            max_retries=task.max_retries,
            error_message=config.error_message,
        )
