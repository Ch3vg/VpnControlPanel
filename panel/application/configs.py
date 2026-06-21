from __future__ import annotations

import uuid
from dataclasses import dataclass

from panel.application.audit_service import AuditService
from panel.config import PanelSettings
from panel.domain.entities.user import User
from panel.domain.entities.vpn_config import VpnConfig
from panel.domain.value_objects.protocol import VpnProtocolType
from panel.infrastructure.persistence.repositories.vpn_config import ConfigListResult, VpnConfigRepository
from panel.infrastructure.vpn.systemd_unit import remove_config_unit


class ConfigNotFound(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ListConfigsQuery:
    protocol: VpnProtocolType | None = None
    limit: int = 50
    offset: int = 0


class ListConfigsUseCase:
    def __init__(self, configs: VpnConfigRepository) -> None:
        self._configs = configs

    async def execute(self, query: ListConfigsQuery) -> ConfigListResult:
        return await self._configs.list_active(
            protocol=query.protocol,
            limit=query.limit,
            offset=query.offset,
        )


class GetConfigUseCase:
    def __init__(self, configs: VpnConfigRepository) -> None:
        self._configs = configs

    async def execute(self, config_id: uuid.UUID) -> VpnConfig:
        config = await self._configs.get_by_id(config_id)
        if config is None:
            raise ConfigNotFound
        return config


class DeleteConfigUseCase:
    def __init__(
        self,
        configs: VpnConfigRepository,
        audit: AuditService,
        settings: PanelSettings,
    ) -> None:
        self._configs = configs
        self._audit = audit
        self._settings = settings

    async def execute(self, config_id: uuid.UUID, user: User) -> None:
        config = await self._configs.get_by_id(config_id)
        if config is None:
            raise ConfigNotFound

        if self._settings.systemd.per_config:
            profile_settings = self._settings.vpn.profiles[config.profile.value]
            remove_config_unit(
                config.profile,
                config_id,
                config_filename=profile_settings.config_filename,
                settings=self._settings.systemd,
            )

        deleted = await self._configs.soft_delete(config_id, user.id)
        if not deleted:
            raise ConfigNotFound
        await self._audit.log(
            "config.deleted",
            {"config_id": str(config_id)},
            user_id=user.id,
        )
