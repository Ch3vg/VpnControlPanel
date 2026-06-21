from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from panel.application.audit_service import AuditService
from panel.application.regenerate_config import (
    ConfigNotRegeneratable,
    RegenerateConfigResult,
    RegenerateConfigUseCase,
)
from panel.config import PanelSettings
from panel.domain.entities.user import User
from panel.domain.ports.broker import BrokerPort
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository


@dataclass(frozen=True, slots=True)
class SkippedRegenerate:
    config_id: uuid.UUID
    reason: str


@dataclass(frozen=True, slots=True)
class RegenerateAllConfigsResult:
    queued: list[RegenerateConfigResult]
    skipped: list[SkippedRegenerate]


class RegenerateAllConfigsUseCase:
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

    async def execute(self, user: User) -> RegenerateAllConfigsResult:
        regenerate = RegenerateConfigUseCase(
            self._settings,
            self._session,
            self._configs,
            self._broker,
            self._audit,
        )
        queued: list[RegenerateConfigResult] = []
        skipped: list[SkippedRegenerate] = []
        offset = 0
        limit = 100

        while True:
            batch = await self._configs.list_active(limit=limit, offset=offset)
            for config in batch.items:
                try:
                    result = await regenerate.execute(config.id, user)
                except ConfigNotRegeneratable as exc:
                    skipped.append(SkippedRegenerate(config_id=config.id, reason=str(exc)))
                else:
                    queued.append(result)

            if offset + len(batch.items) >= batch.total:
                break
            offset += len(batch.items)

        await self._audit.log(
            "config.regenerate_all.requested",
            {
                "queued_count": len(queued),
                "skipped_count": len(skipped),
            },
            user_id=user.id,
        )
        await self._session.commit()
        return RegenerateAllConfigsResult(queued=queued, skipped=skipped)
