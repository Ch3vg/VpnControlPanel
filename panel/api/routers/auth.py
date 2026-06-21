from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from panel.api.deps import SettingsDep, get_client_ip, get_current_user, get_db_session, make_audit_service
from panel.api.schemas.auth import LoginRequest, LoginResponse
from panel.application.login import InvalidCredentials, LoginUseCase
from panel.infrastructure.persistence.repositories.rate_limit import PostgresRateLimiter, RateLimitExceeded
from panel.infrastructure.persistence.repositories.user import UserRepository
from panel.infrastructure.security import JwtService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    settings: SettingsDep,
    session: AsyncSession = Depends(get_db_session),
) -> LoginResponse:
    use_case = LoginUseCase(
        settings=settings,
        users=UserRepository(session),
        rate_limiter=PostgresRateLimiter(session),
        audit=make_audit_service(settings, session),
        jwt_service=JwtService(settings.security),
    )
    try:
        result = await use_case.execute(body.username, body.password, get_client_ip(request))
    except RateLimitExceeded:
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts",
        ) from None
    except InvalidCredentials:
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        ) from None

    await session.commit()
    return LoginResponse(access_token=result.access_token, token_type=result.token_type)
