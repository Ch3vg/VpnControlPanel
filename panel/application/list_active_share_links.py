from __future__ import annotations

import uuid
from dataclasses import dataclass

from panel.infrastructure.persistence.repositories.share_token import ActiveShareLinkRow, ShareTokenRepository


@dataclass(frozen=True, slots=True)
class ListActiveShareLinksResult:
    items: list[ActiveShareLinkRow]


class ListActiveShareLinksUseCase:
    def __init__(self, shares: ShareTokenRepository) -> None:
        self._shares = shares

    async def execute(self, *, config_id: uuid.UUID | None = None) -> ListActiveShareLinksResult:
        items = await self._shares.list_active(config_id=config_id)
        return ListActiveShareLinksResult(items=items)
