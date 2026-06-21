from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


class InvalidShareRequest(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ShareExpiration:
    is_permanent: bool
    expires_at: datetime | None


def resolve_share_expiration(
    *,
    is_permanent: bool = True,
    expires_at: datetime | None = None,
    ttl_seconds: int | None = None,
) -> ShareExpiration:
    if ttl_seconds is not None:
        if ttl_seconds <= 0:
            raise InvalidShareRequest("ttl_seconds must be positive")
        if expires_at is not None:
            raise InvalidShareRequest("Specify either ttl_seconds or expires_at, not both")
        if is_permanent:
            raise InvalidShareRequest("ttl_seconds cannot be used with is_permanent")
        return ShareExpiration(
            is_permanent=False,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )

    if is_permanent:
        if expires_at is not None:
            raise InvalidShareRequest("expires_at cannot be used with is_permanent")
        return ShareExpiration(is_permanent=True, expires_at=None)

    if expires_at is None:
        raise InvalidShareRequest("ttl_seconds or expires_at is required when is_permanent is false")
    if expires_at <= datetime.now(UTC):
        raise InvalidShareRequest("expires_at must be in the future")
    return ShareExpiration(is_permanent=False, expires_at=expires_at)
