from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from panel.application.configs import ConfigNotFound
from panel.config import PanelSettings
from panel.domain.entities.vpn_config import VpnConfig
from panel.domain.ports.broker import BrokerPort
from panel.domain.value_objects.config_status import ConfigStatus
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository
from panel.infrastructure.vpn.service_runtime import probe_config_availability


@dataclass(frozen=True, slots=True)
class ConfigTaskStatus:
    config_id: uuid.UUID
    status: ConfigStatus
    task_id: str | None
    task_status: str | None
    retries: int | None
    max_retries: int | None
    error_message: str | None
    runtime_online: bool | None = None
    runtime_systemd_active: bool | None = None
    runtime_port_listening: bool | None = None
    runtime_detail: str | None = None


class GetConfigStatusUseCase:
    def __init__(
        self,
        configs: VpnConfigRepository,
        broker: BrokerPort,
        settings: PanelSettings | None = None,
    ) -> None:
        self._configs = configs
        self._broker = broker
        self._settings = settings

    async def execute(self, config_id: uuid.UUID) -> ConfigTaskStatus:
        config = await self._configs.get_by_id(config_id)
        if config is None:
            raise ConfigNotFound

        runtime = await self._runtime_fields(config)

        if not config.last_task_id:
            return ConfigTaskStatus(
                config_id=config.id,
                status=config.status,
                task_id=None,
                task_status=None,
                retries=None,
                max_retries=None,
                error_message=config.error_message,
                **runtime,
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
            **runtime,
        )

    async def _runtime_fields(self, config: VpnConfig) -> dict[str, bool | str | None]:
        if self._settings is None or config.status is not ConfigStatus.ACTIVE:
            return {}
        if config.current_version is None:
            return {}
        snapshot = await self._configs.get_version_snapshot(config.id, config.current_version)
        if snapshot is None:
            return {}

        probe = await asyncio.to_thread(
            probe_config_availability,
            config_id=snapshot.config_id,
            profile=snapshot.profile,
            port=snapshot.port,
            settings=self._settings,
            snapshot=snapshot,
        )
        return {
            "runtime_online": probe.online,
            "runtime_systemd_active": probe.systemd_active,
            "runtime_port_listening": probe.port_listening,
            "runtime_detail": probe.detail,
        }
