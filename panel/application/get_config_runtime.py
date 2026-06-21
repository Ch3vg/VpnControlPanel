from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from panel.config import PanelSettings
from panel.domain.value_objects.protocol import VpnProtocolType
from panel.infrastructure.persistence.repositories.vpn_config import (
    ConfigVersionSnapshot,
    VpnConfigRepository,
)
from panel.infrastructure.vpn.service_runtime import ServiceRuntimeProbe, probe_config_runtime


@dataclass(frozen=True, slots=True)
class ConfigRuntimeStatus:
    config_id: uuid.UUID
    online: bool | None
    systemd_active: bool | None
    port_listening: bool | None
    detail: str | None


def _probe_snapshot(snapshot: ConfigVersionSnapshot, settings: PanelSettings) -> ConfigRuntimeStatus:
    probe = probe_config_runtime(
        config_id=snapshot.config_id,
        profile=snapshot.profile,
        port=snapshot.port,
        settings=settings,
    )
    return ConfigRuntimeStatus(
        config_id=snapshot.config_id,
        online=probe.online,
        systemd_active=probe.systemd_active,
        port_listening=probe.port_listening,
        detail=probe.detail,
    )


class GetConfigsRuntimeUseCase:
    def __init__(self, configs: VpnConfigRepository, settings: PanelSettings) -> None:
        self._configs = configs
        self._settings = settings

    async def execute(self, *, protocol: VpnProtocolType | None = None) -> list[ConfigRuntimeStatus]:
        snapshots = await self._configs.list_current_version_snapshots()
        if protocol is not None:
            snapshots = [item for item in snapshots if item.protocol is protocol]
        if not snapshots:
            return []

        probes = await asyncio.gather(
            *[
                asyncio.to_thread(_probe_snapshot, snapshot, self._settings)
                for snapshot in snapshots
            ],
        )
        return list(probes)


class GetConfigRuntimeUseCase:
    def __init__(self, configs: VpnConfigRepository, settings: PanelSettings) -> None:
        self._configs = configs
        self._settings = settings

    async def execute(self, config_id: uuid.UUID) -> ConfigRuntimeStatus | None:
        config = await self._configs.get_by_id(config_id)
        if config is None or config.current_version is None:
            return None
        snapshot = await self._configs.get_version_snapshot(config_id, config.current_version)
        if snapshot is None:
            return None
        return await asyncio.to_thread(_probe_snapshot, snapshot, self._settings)
