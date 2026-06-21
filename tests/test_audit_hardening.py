from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from panel.application.audit_service import AuditService
from panel.config import PanelSettings
from panel.infrastructure.audit.sanitizer import REDACTED, sanitize_audit_payload
from panel.infrastructure.persistence.repositories.audit import AuditRepository
from panel.infrastructure.persistence.models import AuditLogModel
from sqlalchemy import select


def test_sanitize_audit_payload_redacts_nested_secrets() -> None:
    payload = {
        "config_id": "uuid",
        "credentials": {"password": "secret", "token": "raw"},
        "token_hash": "abc123",
        "task_id": "task-1",
    }
    sanitized = sanitize_audit_payload(payload)
    assert sanitized["config_id"] == "uuid"
    assert sanitized["credentials"]["password"] == REDACTED
    assert sanitized["credentials"]["token"] == REDACTED
    assert sanitized["token_hash"] == "abc123"
    assert sanitized["task_id"] == "task-1"


@pytest.mark.asyncio
async def test_audit_service_redacts_before_persist(
    panel_settings: PanelSettings,
    db_session: AsyncSession,
) -> None:
    service = AuditService(panel_settings, AuditRepository(db_session))
    await service.log(
        "test.event",
        {"password": "leak", "name": "Office"},
    )
    await db_session.commit()

    row = (await db_session.execute(select(AuditLogModel))).scalar_one()
    assert row.payload["password"] == REDACTED
    assert row.payload["name"] == "Office"


@pytest.mark.asyncio
async def test_audit_service_respects_disabled(panel_settings: PanelSettings, db_session: AsyncSession) -> None:
    panel_settings.audit.enabled = False
    service = AuditService(panel_settings, AuditRepository(db_session))
    await service.log("test.event", {"name": "x"})
    await db_session.commit()
    result = await db_session.execute(select(AuditLogModel))
    assert result.scalar_one_or_none() is None
