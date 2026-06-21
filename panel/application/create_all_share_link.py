from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from panel.application.audit_service import AuditService
from panel.application.create_share_link import ConfigNotShareable
from panel.application.share_expiration import resolve_share_expiration
from panel.domain.entities.user import User
from panel.domain.value_objects.config_status import ConfigStatus
from panel.infrastructure.persistence.repositories.share_token import ShareTokenRepository
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository
from panel.infrastructure.security.share_token import generate_share_token, hash_share_token


@dataclass(frozen=True, slots=True)
class CreateAllShareLinksResult:
    token: str
    url: str
    secure: bool
    config_count: int
    is_permanent: bool
    expires_at: datetime | None


class CreateAllShareLinksUseCase:
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
        user: User,
        *,
        secure: bool,
        is_permanent: bool,
        expires_at: datetime | None,
        ttl_seconds: int | None,
        public_base_url: str,
    ) -> CreateAllShareLinksResult:
        expiration = resolve_share_expiration(
            is_permanent=is_permanent,
            expires_at=expires_at,
            ttl_seconds=ttl_seconds,
        )

        snapshots = await self._configs.list_current_version_snapshots()
        if not snapshots:
            raise ConfigNotShareable("No active configs available for sharing")

        raw_token = generate_share_token()
        token_hash = hash_share_token(raw_token)
        await self._shares.create(
            token_hash=token_hash,
            config_id=None,
            config_version=None,
            secure=secure,
            is_permanent=expiration.is_permanent,
            expires_at=expiration.expires_at,
            created_by=user.id,
        )

        await self._audit.log(
            "share.created",
            {
                "all_configs": True,
                "secure": secure,
                "config_count": len(snapshots),
                "is_permanent": expiration.is_permanent,
                "expires_at": expiration.expires_at.isoformat() if expiration.expires_at else None,
                "ttl_seconds": ttl_seconds,
            },
            user_id=user.id,
        )

        base = public_base_url.rstrip("/")
        return CreateAllShareLinksResult(
            token=raw_token,
            url=f"{base}/share/{raw_token}",
            secure=secure,
            config_count=len(snapshots),
            is_permanent=expiration.is_permanent,
            expires_at=expiration.expires_at,
        )
