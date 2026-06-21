from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    from sqlalchemy.ext.asyncio import AsyncSession

    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
