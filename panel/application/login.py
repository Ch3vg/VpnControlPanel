from __future__ import annotations

from dataclasses import dataclass

from panel.config import PanelSettings, RateLimitRule
from panel.application.audit_service import AuditService
from panel.infrastructure.persistence.repositories.rate_limit import PostgresRateLimiter, RateLimitExceeded
from panel.infrastructure.persistence.repositories.user import UserRepository
from panel.infrastructure.security import JwtService, verify_password


class InvalidCredentials(Exception):
    pass


@dataclass(frozen=True, slots=True)
class LoginResult:
    access_token: str
    token_type: str = "bearer"


class LoginUseCase:
    def __init__(
        self,
        settings: PanelSettings,
        users: UserRepository,
        rate_limiter: PostgresRateLimiter,
        audit: AuditService,
        jwt_service: JwtService,
    ) -> None:
        self._settings = settings
        self._users = users
        self._rate_limiter = rate_limiter
        self._audit = audit
        self._jwt = jwt_service
        self._login_rule: RateLimitRule = settings.rate_limit.login

    async def execute(self, username: str, password: str, client_ip: str) -> LoginResult:
        try:
            await self._rate_limiter.check_and_increment(
                "login",
                f"ip:{client_ip}",
                limit=self._login_rule.max_attempts or 5,
                window_seconds=self._login_rule.window_seconds,
            )
        except RateLimitExceeded:
            raise

        user = await self._users.get_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            await self._log_failed_login(username, client_ip)
            raise InvalidCredentials

        token = self._jwt.create_access_token(user.id)
        return LoginResult(access_token=token)

    async def _log_failed_login(self, username: str, client_ip: str) -> None:
        await self._audit.log_failed_login(username, client_ip)
