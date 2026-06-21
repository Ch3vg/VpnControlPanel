from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from panel.config import PanelSettings
from panel.infrastructure.crypto.field_encryptor import FieldEncryptor


@dataclass(slots=True)
class WorkerContext:
    settings: PanelSettings
    session_factory: async_sessionmaker[AsyncSession]
    encryptor: FieldEncryptor


def cert_fingerprint_for_keys(private_key: str, public_key: str, explicit: str = "") -> str:
    if explicit:
        return explicit
    return hashlib.sha256(public_key.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(UTC)
