from __future__ import annotations

import argparse
import asyncio
import contextlib
from pathlib import Path
from typing import Any

import structlog

from panel.config import PanelSettings, load_panel_settings
from panel.infrastructure.broker import HttpBrokerClient
from panel.infrastructure.crypto import FieldEncryptor
from panel.infrastructure.logging import configure_logging
from panel.infrastructure.persistence.database import create_engine, create_session_factory
from panel.worker.context import WorkerContext
from panel.worker.handlers import HANDLERS, Handler
from panel.worker.identity import resolve_worker_id

logger = structlog.get_logger(__name__)


async def _process_task(
    broker: HttpBrokerClient,
    settings: PanelSettings,
    ctx: WorkerContext,
    worker_id: str,
    task_id: str,
    task_type: str,
    payload: dict[str, Any],
    lock_ttl_seconds: int,
) -> None:
    handler: Handler | None = HANDLERS.get(task_type)
    if handler is None:
        await broker.nack(task_id, worker_id, reason=f"Unknown task type: {task_type}")
        return

    heartbeat_interval = max(lock_ttl_seconds // 3, 1)
    stop_event = asyncio.Event()

    async def heartbeat_loop() -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=heartbeat_interval)
            except TimeoutError:
                await broker.heartbeat(task_id, worker_id)

    heartbeat_task = asyncio.create_task(heartbeat_loop())
    try:
        await handler(payload, ctx)
    except Exception as exc:
        logger.exception("task_failed", task_id=task_id, task_type=task_type, worker_id=worker_id)
        await broker.nack(task_id, worker_id, reason=str(exc))
    else:
        await broker.ack(task_id, worker_id)
    finally:
        stop_event.set()
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task


async def run_worker(settings: PanelSettings, *, worker_id: str) -> None:
    engine = create_engine(settings.database.url)
    session_factory = create_session_factory(engine)
    ctx = WorkerContext(
        settings=settings,
        session_factory=session_factory,
        encryptor=FieldEncryptor(settings.security.encryption_key),
    )
    broker = HttpBrokerClient(settings.broker)
    task_types = settings.worker.task_types

    logger.info("worker_started", worker_id=worker_id, task_types=task_types)
    try:
        while True:
            task = await broker.pull(worker_id, task_types)
            if task is None:
                continue
            logger.info("task_received", task_id=task.task_id, task_type=task.task_type, worker_id=worker_id)
            await _process_task(
                broker,
                settings,
                ctx,
                worker_id,
                task.task_id,
                task.task_type,
                task.payload,
                task.lock_ttl_seconds,
            )
    finally:
        await broker.close()
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the VPN Control Panel worker")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to panel.yaml (default: ./panel.yaml or PANEL_CONFIG_PATH)",
    )
    parser.add_argument(
        "--instance",
        default=None,
        help="Worker instance suffix (overrides VPN_WORKER_INSTANCE env)",
    )
    args = parser.parse_args()

    settings = load_panel_settings(args.config)
    worker_id = resolve_worker_id(settings, instance=args.instance)
    configure_logging("DEBUG" if settings.app.environment.value == "development" else "INFO")
    asyncio.run(run_worker(settings, worker_id=worker_id))


if __name__ == "__main__":
    main()
