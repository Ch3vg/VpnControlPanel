from __future__ import annotations

from typing import Any

from panel.worker.context import WorkerContext
from panel.worker.services.config_task import run_config_initialize

async def handle_config_initialize(payload: dict[str, Any], ctx: WorkerContext) -> None:
    await run_config_initialize(payload, ctx)
