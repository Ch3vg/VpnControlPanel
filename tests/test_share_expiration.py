from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from panel.application.share_expiration import InvalidShareRequest, resolve_share_expiration


def test_resolve_permanent() -> None:
    result = resolve_share_expiration(is_permanent=True)
    assert result.is_permanent is True
    assert result.expires_at is None


def test_resolve_ttl_seconds() -> None:
    before = datetime.now(UTC)
    result = resolve_share_expiration(is_permanent=False, ttl_seconds=3600)
    after = datetime.now(UTC)
    assert result.is_permanent is False
    assert result.expires_at is not None
    assert before + timedelta(seconds=3600) <= result.expires_at <= after + timedelta(seconds=3600)


def test_resolve_expires_at() -> None:
    expires = datetime.now(UTC) + timedelta(hours=2)
    result = resolve_share_expiration(is_permanent=False, expires_at=expires)
    assert result.is_permanent is False
    assert result.expires_at == expires


def test_ttl_and_expires_at_conflict() -> None:
    expires = datetime.now(UTC) + timedelta(hours=1)
    with pytest.raises(InvalidShareRequest, match="either ttl_seconds or expires_at"):
        resolve_share_expiration(is_permanent=False, ttl_seconds=60, expires_at=expires)


def test_ttl_with_permanent_conflict() -> None:
    with pytest.raises(InvalidShareRequest, match="ttl_seconds cannot be used"):
        resolve_share_expiration(is_permanent=True, ttl_seconds=60)
