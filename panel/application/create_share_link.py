from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from panel.application.audit_service import AuditService
from panel.application.configs import ConfigNotFound
from panel.domain.entities.user import User
from panel.domain.value_objects.config_status import ConfigStatus
from panel.infrastructure.persistence.repositories.share_token import ShareTokenRepository
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository
from panel.infrastructure.security.share_token import generate_share_token, hash_share_token


class ConfigNotShareable(Exception):
    pass


class InvalidShareRequest(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CreateShareLinkResult:
    token: str
    url: str
    config_id: uuid.UUID
    config_version: int


class CreateShareLinkUseCase:
    def __init__(
        self,
        configs: VpnConfigRepository,
        shares: ShareTokenRepository,
        audit: AuditService,
    ) -> None:
        self._configs = configs
        self._shares = shares
        self._audit = audit

    async def execute(
        self,
        config_id: uuid.UUID,
        user: User,
        *,
        is_permanent: bool,
        expires_at: datetime | None,
        public_base_url: str,
    ) -> CreateShareLinkResult:
        if not is_permanent and expires_at is None:
            raise InvalidShareRequest("expires_at is required when is_permanent is false")
        if expires_at is not None and expires_at <= datetime.now(UTC):
            raise InvalidShareRequest("expires_at must be in the future")

        config = await self._configs.get_by_id(config_id)
        if config is None:
            raise ConfigNotFound
        if config.current_version is None or config.status is not ConfigStatus.ACTIVE:
            raise ConfigNotShareable("Config is not ready for sharing")

        raw_token = generate_share_token()
        token_hash = hash_share_token(raw_token)
        await self._shares.create(
            token_hash=token_hash,
            config_id=config_id,
            config_version=config.current_version,
            is_permanent=is_permanent,
            expires_at=None if is_permanent else expires_at,
            created_by=user.id,
        )

        await self._audit.log(
            "share.created",
            {
                "config_id": str(config_id),
                "config_version": config.current_version,
                "is_permanent": is_permanent,
            },
            user_id=user.id,
        )

        base = public_base_url.rstrip("/")
        return CreateShareLinkResult(
            token=raw_token,
            url=f"{base}/share/{raw_token}",
            config_id=config_id,
            config_version=config.current_version,
        )
