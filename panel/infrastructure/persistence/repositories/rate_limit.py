from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from panel.infrastructure.persistence.models import RateLimitEntryModel


class RateLimitExceeded(Exception):
    pass


class PostgresRateLimiter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def check_and_increment(
        self,
        scope: str,
        identifier: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> None:
        now = datetime.now(UTC)
        window_start = datetime.fromtimestamp(
            (int(now.timestamp()) // window_seconds) * window_seconds,
            tz=UTC,
        )
        key = f"{scope}:{identifier}"

        dialect = self._session.bind.dialect.name if self._session.bind else "postgresql"
        insert_stmt = sqlite_insert if dialect == "sqlite" else pg_insert

        stmt = (
            insert_stmt(RateLimitEntryModel)
            .values(key=key, window_start=window_start, count=1)
            .on_conflict_do_update(
                index_elements=["key", "window_start"],
                set_={"count": RateLimitEntryModel.count + 1},
            )
            .returning(RateLimitEntryModel.count)
        )
        result = await self._session.execute(stmt)
        count = result.scalar_one()
        if count > limit:
            raise RateLimitExceeded

    async def current_count(
        self,
        scope: str,
        identifier: str,
        *,
        window_seconds: int,
    ) -> int:
        now = datetime.now(UTC)
        window_start = datetime.fromtimestamp(
            (int(now.timestamp()) // window_seconds) * window_seconds,
            tz=UTC,
        )
        key = f"{scope}:{identifier}"
        result = await self._session.execute(
            select(RateLimitEntryModel.count).where(
                RateLimitEntryModel.key == key,
                RateLimitEntryModel.window_start == window_start,
            ),
        )
        return result.scalar_one_or_none() or 0
