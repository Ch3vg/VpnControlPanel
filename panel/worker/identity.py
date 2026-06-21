from __future__ import annotations

import os

from panel.config import PanelSettings


def resolve_worker_id(settings: PanelSettings, *, instance: str | None = None) -> str:
    raw = (instance if instance is not None else os.environ.get("VPN_WORKER_INSTANCE", "")).strip()
    base_id = settings.worker.worker_id
    if raw:
        return f"{base_id}-{raw}"
    return base_id
