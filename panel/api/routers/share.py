from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from panel.api.deps import CurrentUserDep, SettingsDep, get_client_ip, get_db_session, make_audit_service
from panel.application.resolve_share import ResolveShareUseCase, ShareNotFound
from panel.application.revoke_share_link import RevokeShareLinkUseCase
from panel.infrastructure.crypto import FieldEncryptor
from panel.infrastructure.persistence.repositories.rate_limit import PostgresRateLimiter, RateLimitExceeded
from panel.infrastructure.persistence.repositories.share_token import ShareTokenRepository
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository

public_router = APIRouter(prefix="/share", tags=["share"])
admin_router = APIRouter(prefix="/api/v1/share", tags=["share"])

_SHARE_NOT_FOUND = "Not found"


@public_router.get("/{token:path}", response_model=list[str])
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
    return Response(
        content=json.dumps(uris),
        media_type="application/json",
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
