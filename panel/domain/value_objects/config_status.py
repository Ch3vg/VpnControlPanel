from __future__ import annotations

from enum import StrEnum


class ConfigStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    ACTIVE = "active"
    FAILED = "failed"
