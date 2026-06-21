from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from panel.worker.context import WorkerContext
from panel.worker.handlers.config_initialize import handle_config_initialize
from panel.worker.handlers.config_regenerate import handle_config_regenerate

Handler = Callable[[dict[str, Any], WorkerContext], Awaitable[None]]

HANDLERS: dict[str, Handler] = {
    "config.initialize": handle_config_initialize,
    "config.regenerate": handle_config_regenerate,
}

__all__ = ["HANDLERS", "Handler"]
