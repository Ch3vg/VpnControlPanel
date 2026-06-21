from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from panel.domain.value_objects.config_profile import ConfigProfile
from panel.domain.value_objects.config_status import ConfigStatus
from panel.domain.value_objects.protocol import VpnProtocolType


@dataclass(frozen=True, slots=True)
class VpnConfigVersion:
    id: uuid.UUID
    config_id: uuid.UUID
    version: int
    port: int
    public_key: str
    cert_fingerprint: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class VpnConfig:
    id: uuid.UUID
    name: str
    protocol: VpnProtocolType
    profile: ConfigProfile
    status: ConfigStatus
    current_version: int | None
    last_task_id: str | None
    error_message: str | None
    is_active: bool
    created_by: uuid.UUID
    updated_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    current_version_detail: VpnConfigVersion | None = None
