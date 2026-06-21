from __future__ import annotations

import uuid
from typing import Any

import structlog

from panel.domain.value_objects.config_profile import ConfigProfile
from panel.domain.value_objects.protocol import VpnProtocolType
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository
from panel.worker.context import WorkerContext
from panel.worker.services.config_build import build_and_persist_version

logger = structlog.get_logger(__name__)


async def _run_config_task(
    payload: dict[str, Any],
    ctx: WorkerContext,
    *,
    task_name: str,
) -> None:
    config_id = uuid.UUID(str(payload["config_id"]))
    profile = ConfigProfile(str(payload["profile"]))
    target_version = int(payload["target_version"])
    name = str(payload.get("name", ""))

    async with ctx.session_factory() as session:
        repo = VpnConfigRepository(session)
        try:
            if await repo.has_version(config_id, target_version):
                logger.info(
                    f"{task_name}_idempotent",
                    config_id=str(config_id),
                    version=target_version,
                )
                await repo.mark_active(config_id, target_version)
                await session.commit()
                return

            await repo.mark_processing(config_id)
            await build_and_persist_version(
                repo=repo,
                config_id=config_id,
                profile=profile,
                target_version=target_version,
                name=name,
                ctx=ctx,
            )
            await repo.mark_active(config_id, target_version)
            await session.commit()
            logger.info(f"{task_name}_completed", config_id=str(config_id), version=target_version)
        except Exception as exc:
            await session.rollback()
            async with ctx.session_factory() as fail_session:
                fail_repo = VpnConfigRepository(fail_session)
                await fail_repo.mark_failed(config_id, str(exc))
                await fail_session.commit()
            raise


async def run_config_initialize(payload: dict[str, Any], ctx: WorkerContext) -> None:
    await _run_config_task(payload, ctx, task_name="config_initialize")


async def run_config_regenerate(payload: dict[str, Any], ctx: WorkerContext) -> None:
    await _run_config_task(payload, ctx, task_name="config_regenerate")
