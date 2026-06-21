from __future__ import annotations

import uuid
from typing import Any

from panel.config import PanelSettings
from panel.infrastructure.audit.sanitizer import sanitize_audit_payload
from panel.infrastructure.persistence.repositories.audit import AuditRepository


class AuditService:
    def __init__(self, settings: PanelSettings, audit: AuditRepository) -> None:
        self._settings = settings
        self._audit = audit

    async def log(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        user_id: uuid.UUID | None = None,
    ) -> None:
        if not self._settings.audit.enabled:
            return
        await self._audit.log(
            event_type,
            sanitize_audit_payload(payload),
            user_id=user_id,
        )

    async def log_failed_login(self, username: str, client_ip: str) -> None:
        if not self._settings.audit.enabled or not self._settings.audit.log_failed_login:
            return
        await self.log(
            "auth.login.failed",
            {"ip": client_ip, "username_attempt": username},
        )
