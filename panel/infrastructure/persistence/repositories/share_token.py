from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from panel.infrastructure.persistence.models import ShareTokenModel, UserModel, VpnConfigModel


@dataclass(frozen=True, slots=True)
class ActiveShareLinkRow:
    id: uuid.UUID
    config_id: uuid.UUID | None
    config_name: str | None
    secure: bool
    is_permanent: bool
    expires_at: datetime | None
    created_by_username: str
    created_at: datetime
    last_accessed_at: datetime | None
    access_count: int


@dataclass(frozen=True, slots=True)
class ShareTokenRecord:
    id: uuid.UUID
    token_hash: str
    config_id: uuid.UUID | None
    config_version: int | None
    secure: bool
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
        secure=model.secure,
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
        config_id: uuid.UUID | None,
        config_version: int | None,
        secure: bool,
        is_permanent: bool,
        expires_at: datetime | None,
        created_by: uuid.UUID,
    ) -> ShareTokenRecord:
        model = ShareTokenModel(
            token_hash=token_hash,
            config_id=config_id,
            config_version=config_version,
            secure=secure,
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

    async def revoke_by_id(self, link_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(ShareTokenModel).where(ShareTokenModel.id == link_id),
        )
        model = result.scalar_one_or_none()
        if model is None or model.revoked_at is not None:
            return False
        model.revoked_at = datetime.now(UTC)
        return True

    async def list_active(self, *, config_id: uuid.UUID | None = None) -> list[ActiveShareLinkRow]:
        now = datetime.now(UTC)
        filters = [
            ShareTokenModel.revoked_at.is_(None),
            or_(
                ShareTokenModel.is_permanent.is_(True),
                ShareTokenModel.expires_at > now,
            ),
        ]
        if config_id is not None:
            filters.append(ShareTokenModel.config_id == config_id)

        result = await self._session.execute(
            select(ShareTokenModel, UserModel.username, VpnConfigModel.name)
            .join(UserModel, ShareTokenModel.created_by == UserModel.id)
            .outerjoin(VpnConfigModel, ShareTokenModel.config_id == VpnConfigModel.id)
            .where(*filters)
            .order_by(ShareTokenModel.created_at.desc()),
        )
        rows: list[ActiveShareLinkRow] = []
        for share, username, config_name in result.all():
            rows.append(
                ActiveShareLinkRow(
                    id=share.id,
                    config_id=share.config_id,
                    config_name=config_name,
                    secure=share.secure,
                    is_permanent=share.is_permanent,
                    expires_at=share.expires_at,
                    created_by_username=username,
                    created_at=share.created_at,
                    last_accessed_at=share.last_accessed_at,
                    access_count=share.access_count,
                ),
            )
        return rows

    async def record_access(self, token_id: uuid.UUID) -> None:
        result = await self._session.execute(
            select(ShareTokenModel).where(ShareTokenModel.id == token_id),
        )
        model = result.scalar_one_or_none()
        if model is None:
            return
        model.last_accessed_at = datetime.now(UTC)
        model.access_count += 1
