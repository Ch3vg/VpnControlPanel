from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panel.domain.entities.user import User
from panel.infrastructure.persistence.models import UserModel


def _to_entity(model: UserModel) -> User:
    return User(
        id=model.id,
        username=model.username,
        password_hash=model.password_hash,
        created_at=model.created_at,
    )


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_username(self, username: str) -> User | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.username == username),
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.id == user_id),
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def create(self, username: str, password_hash: str) -> User:
        model = UserModel(username=username, password_hash=password_hash)
        self._session.add(model)
        await self._session.flush()
        return _to_entity(model)
