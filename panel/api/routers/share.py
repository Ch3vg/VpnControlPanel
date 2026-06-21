from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from panel.api.deps import CurrentUserDep, SettingsDep, get_client_ip, get_db_session, make_audit_service
from panel.api.schemas.share import (
    CreateAllShareLinkRequest,
    CreateShareLinkResponse,
    ShareLinkListItem,
    ShareLinkListResponse,
)
from panel.application.create_all_share_link import CreateAllShareLinksUseCase
from panel.application.create_share_link import ConfigNotShareable
from panel.application.list_active_share_links import ListActiveShareLinksUseCase
from panel.application.share_expiration import InvalidShareRequest
from panel.application.resolve_share import ResolveShareUseCase, ShareNotFound
from panel.application.revoke_share_link import RevokeShareLinkUseCase
from panel.infrastructure.crypto import FieldEncryptor
from panel.infrastructure.persistence.repositories.rate_limit import PostgresRateLimiter, RateLimitExceeded
from panel.infrastructure.persistence.repositories.share_token import ShareTokenRepository
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository

public_router = APIRouter(prefix="/share", tags=["share"])
admin_router = APIRouter(prefix="/api/v1/share", tags=["share"])

_SHARE_NOT_FOUND = "Not found"


def _to_list_item(row) -> ShareLinkListItem:
    return ShareLinkListItem(
        id=row.id,
        all_configs=row.config_id is None,
        config_id=row.config_id,
        config_name=row.config_name,
        secure=row.secure,
        is_permanent=row.is_permanent,
        created_by=row.created_by_username,
        created_at=row.created_at,
        expires_at=row.expires_at,
        access_count=row.access_count,
        last_accessed_at=row.last_accessed_at,
    )


@admin_router.get("/links", response_model=ShareLinkListResponse)
async def list_active_share_links(
    _user: CurrentUserDep,
    session: AsyncSession = Depends(get_db_session),
    config_id: uuid.UUID | None = Query(default=None),
) -> ShareLinkListResponse:
    use_case = ListActiveShareLinksUseCase(ShareTokenRepository(session))
    result = await use_case.execute(config_id=config_id)
    items = [_to_list_item(row) for row in result.items]
    return ShareLinkListResponse(items=items, total=len(items))


@admin_router.delete("/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share_link_by_id(
    link_id: uuid.UUID,
    user: CurrentUserDep,
    settings: SettingsDep,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    use_case = RevokeShareLinkUseCase(
        ShareTokenRepository(session),
        make_audit_service(settings, session),
    )
    try:
        await use_case.execute_by_id(link_id, user)
    except ShareNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found") from None
    await session.commit()


@admin_router.post("/all", status_code=status.HTTP_201_CREATED, response_model=CreateShareLinkResponse)
async def create_all_share_links(
    body: CreateAllShareLinkRequest,
    request: Request,
    user: CurrentUserDep,
    settings: SettingsDep,
    session: AsyncSession = Depends(get_db_session),
) -> CreateShareLinkResponse:
    use_case = CreateAllShareLinksUseCase(
        VpnConfigRepository(session),
        ShareTokenRepository(session),
        make_audit_service(settings, session),
    )
    try:
        result = await use_case.execute(
            user,
            secure=body.secure,
            is_permanent=body.is_permanent,
            expires_at=body.expires_at,
            ttl_seconds=body.ttl_seconds,
            public_base_url=str(request.base_url).rstrip("/"),
        )
    except ConfigNotShareable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except InvalidShareRequest as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    await session.commit()
    return CreateShareLinkResponse(
        token=result.token,
        url=result.url,
        secure=result.secure,
        all_configs=True,
        config_count=result.config_count,
        is_permanent=result.is_permanent,
        expires_at=result.expires_at,
    )


@public_router.get("/{token:path}")
async def resolve_share(
    token: str,
    request: Request,
    settings: SettingsDep,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    use_case = ResolveShareUseCase(
        settings,
        session,
        ShareTokenRepository(session),
        VpnConfigRepository(session),
        PostgresRateLimiter(session),
        FieldEncryptor(settings.security.encryption_key),
    )
    try:
        uris = await use_case.execute(token, get_client_ip(request))
    except RateLimitExceeded:
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
        ) from None
    except ShareNotFound:
        await session.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_SHARE_NOT_FOUND) from None

    await session.commit()
    body = "\n".join(uris)
    if body:
        body += "\n"
    return Response(
        content=body,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@admin_router.delete("/{token:path}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share(
    token: str,
    user: CurrentUserDep,
    settings: SettingsDep,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    use_case = RevokeShareLinkUseCase(
        ShareTokenRepository(session),
        make_audit_service(settings, session),
    )
    try:
        await use_case.execute(token, user)
    except ShareNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found") from None
    await session.commit()
