from __future__ import annotations

import uuid

from panel.application.audit_service import AuditService
from panel.domain.entities.user import User
from panel.infrastructure.persistence.repositories.share_token import ShareTokenRepository
from panel.infrastructure.security.share_token import hash_share_token


class ShareNotFound(Exception):
    pass


class RevokeShareLinkUseCase:
    def __init__(
        self,
        shares: ShareTokenRepository,
        audit: AuditService,
    ) -> None:
        self._shares = shares
        self._audit = audit

    async def execute(self, raw_token: str, user: User) -> None:
        token_hash = hash_share_token(raw_token)
        revoked = await self._shares.revoke_by_token_hash(token_hash)
        if not revoked:
            raise ShareNotFound

        await self._audit.log(
            "share.revoked",
            {"token_hash": token_hash},
            user_id=user.id,
        )

    async def execute_by_id(self, link_id: uuid.UUID, user: User) -> None:
        revoked = await self._shares.revoke_by_id(link_id)
        if not revoked:
            raise ShareNotFound

        await self._audit.log(
            "share.revoked",
            {"link_id": str(link_id)},
            user_id=user.id,
        )
