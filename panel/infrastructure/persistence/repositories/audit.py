from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from panel.infrastructure.persistence.models import AuditLogModel


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        user_id: uuid.UUID | None = None,
    ) -> None:
        self._session.add(
            AuditLogModel(
                user_id=user_id,
                event_type=event_type,
                payload=payload,
            ),
        )
