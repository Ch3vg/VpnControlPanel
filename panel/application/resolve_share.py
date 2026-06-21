from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from panel.config import PanelSettings, RateLimitRule
from panel.infrastructure.crypto import FieldEncryptor
from panel.infrastructure.crypto.config_data import decrypt_config_data_fields
from panel.infrastructure.persistence.repositories.rate_limit import PostgresRateLimiter, RateLimitExceeded
from panel.infrastructure.persistence.repositories.share_token import ShareTokenRepository
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository
from panel.infrastructure.security.share_token import hash_share_token
from panel.infrastructure.vpn.config_builder import ProfileConfigBuilder


class ShareNotFound(Exception):
    pass


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ResolveShareUseCase:
    def __init__(
        self,
        settings: PanelSettings,
        session: AsyncSession,
        shares: ShareTokenRepository,
        configs: VpnConfigRepository,
        rate_limiter: PostgresRateLimiter,
        encryptor: FieldEncryptor,
    ) -> None:
        self._settings = settings
        self._session = session
        self._shares = shares
        self._configs = configs
        self._rate_limiter = rate_limiter
        self._encryptor = encryptor
        self._share_rule: RateLimitRule = settings.rate_limit.share

    async def execute(self, raw_token: str, client_ip: str) -> list[str]:
        try:
            await self._rate_limiter.check_and_increment(
                "share",
                f"ip:{client_ip}",
                limit=self._share_rule.max_requests or 30,
                window_seconds=self._share_rule.window_seconds,
            )
        except RateLimitExceeded:
            raise

        token_hash = hash_share_token(raw_token)
        share = await self._shares.get_by_token_hash(token_hash)
        if share is None or share.revoked_at is not None:
            raise ShareNotFound
        if not share.is_permanent and share.expires_at is not None and _as_utc(share.expires_at) <= datetime.now(UTC):
            raise ShareNotFound

        snapshot = await self._configs.get_version_snapshot(share.config_id, share.config_version)
        if snapshot is None:
            raise ShareNotFound

        builder = ProfileConfigBuilder(self._settings)
        config_plain = decrypt_config_data_fields(
            snapshot.config_data,
            builder.sensitive_fields(snapshot.profile),
            self._encryptor,
        )
        uris = builder.build_client_uris(
            snapshot.profile,
            config_plain,
            public_key=snapshot.public_key,
            label=snapshot.name,
        )

        await self._shares.record_access(share.id)
        return uris
