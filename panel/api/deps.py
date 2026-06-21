from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from panel.application.audit_service import AuditService
from panel.config import PanelSettings
from panel.domain.entities.user import User
from panel.infrastructure.persistence.repositories.audit import AuditRepository
from panel.infrastructure.persistence.repositories.user import UserRepository
from panel.infrastructure.security import JwtError, JwtService

_bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> PanelSettings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise RuntimeError("Application settings are not initialized")
    return settings


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise RuntimeError("Database session factory is not initialized")
    return factory


SettingsDep = Annotated[PanelSettings, Depends(get_settings)]


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = get_session_factory(request)
    async with factory() as session:
        yield session


DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(
    settings: SettingsDep,
    session: DbSessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = JwtService(settings.security).decode_access_token(credentials.credentials)
    except JwtError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is None:
        return "unknown"
    return request.client.host


def make_audit_service(settings: PanelSettings, session: AsyncSession) -> AuditService:
    return AuditService(settings, AuditRepository(session))
