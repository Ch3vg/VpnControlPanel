from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panel.infrastructure.persistence.models import ShareTokenModel


@dataclass(frozen=True, slots=True)
class ShareTokenRecord:
    id: uuid.UUID
    token_hash: str
    config_id: uuid.UUID
    config_version: int
    is_permanent: bool
    expires_at: datetime | None
    revoked_at: datetime | None
    created_by: uuid.UUID
    created_at: datetime
    last_accessed_at: datetime | None
    access_count: int


def _to_record(model: ShareTokenModel) -> ShareTokenRecord:
    return ShareTokenRecord(
        id=model.id,
        token_hash=model.token_hash,
        config_id=model.config_id,
        config_version=model.config_version,
        is_permanent=model.is_permanent,
        expires_at=model.expires_at,
        revoked_at=model.revoked_at,
        created_by=model.created_by,
        created_at=model.created_at,
        last_accessed_at=model.last_accessed_at,
        access_count=model.access_count,
    )


class ShareTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        token_hash: str,
        config_id: uuid.UUID,
        config_version: int,
        is_permanent: bool,
        expires_at: datetime | None,
        created_by: uuid.UUID,
    ) -> ShareTokenRecord:
        model = ShareTokenModel(
            token_hash=token_hash,
            config_id=config_id,
            config_version=config_version,
            is_permanent=is_permanent,
            expires_at=expires_at,
            created_by=created_by,
        )
        self._session.add(model)
        await self._session.flush()
        return _to_record(model)

    async def get_by_token_hash(self, token_hash: str) -> ShareTokenRecord | None:
        result = await self._session.execute(
            select(ShareTokenModel).where(ShareTokenModel.token_hash == token_hash),
        )
        model = result.scalar_one_or_none()
        return _to_record(model) if model else None

    async def revoke_by_token_hash(self, token_hash: str) -> bool:
        result = await self._session.execute(
            select(ShareTokenModel).where(ShareTokenModel.token_hash == token_hash),
        )
        model = result.scalar_one_or_none()
        if model is None or model.revoked_at is not None:
            return False
        model.revoked_at = datetime.now(UTC)
        return True

    async def record_access(self, token_id: uuid.UUID) -> None:
        result = await self._session.execute(
            select(ShareTokenModel).where(ShareTokenModel.id == token_id),
        )
        model = result.scalar_one_or_none()
        if model is None:
            return
        model.last_accessed_at = datetime.now(UTC)
        model.access_count += 1
