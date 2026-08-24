from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from panel.application.configs import ConfigNotFound
from panel.config import PanelSettings
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository
from panel.infrastructure.vpn.service_logs import clamp_log_lines, fetch_unit_journal
from panel.infrastructure.vpn.service_runtime import service_name_for_config


@dataclass(frozen=True, slots=True)
class ConfigLogsResult:
    config_id: uuid.UUID
    service_name: str | None
    lines: int
    content: str
    available: bool


class GetConfigLogsUseCase:
    def __init__(self, configs: VpnConfigRepository, settings: PanelSettings) -> None:
        self._configs = configs
        self._settings = settings

    async def execute(self, config_id: uuid.UUID, *, lines: int | None = None) -> ConfigLogsResult:
        config = await self._configs.get_by_id(config_id)
        if config is None:
            raise ConfigNotFound

        line_count = clamp_log_lines(lines)
        service_name = service_name_for_config(config_id, config.profile, self._settings)
        if service_name is None:
            return ConfigLogsResult(
                config_id=config_id,
                service_name=None,
                lines=line_count,
                content="Service name is not configured for this profile",
                available=False,
            )

        content, ok = await asyncio.to_thread(
            fetch_unit_journal,
            service_name,
            lines=line_count,
            settings=self._settings.systemd,
        )
        return ConfigLogsResult(
            config_id=config_id,
            service_name=service_name,
            lines=line_count,
            content=content,
            available=ok,
        )
