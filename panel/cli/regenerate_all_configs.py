from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from panel.application.audit_service import AuditService
from panel.application.regenerate_all_configs import RegenerateAllConfigsUseCase
from panel.config import load_panel_settings
from panel.infrastructure.broker import HttpBrokerClient
from panel.infrastructure.persistence.database import create_engine, create_session_factory
from panel.infrastructure.persistence.repositories.audit import AuditRepository
from panel.infrastructure.persistence.repositories.user import UserRepository
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository


async def _regenerate_all(config_path: Path | None, username: str) -> int:
    settings = load_panel_settings(config_path)
    engine = create_engine(settings.database.url)
    session_factory = create_session_factory(engine)
    broker = HttpBrokerClient(settings.broker)

    try:
        async with session_factory() as session:
            user = await UserRepository(session).get_by_username(username)
            if user is None:
                raise SystemExit(f"User not found: {username}")

            use_case = RegenerateAllConfigsUseCase(
                settings,
                session,
                VpnConfigRepository(session),
                broker,
                AuditService(settings, AuditRepository(session)),
            )
            result = await use_case.execute(user)
    finally:
        await broker.close()
        await engine.dispose()

    for item in result.queued:
        print(f"queued {item.config_id} task={item.task_id}")
    for item in result.skipped:
        print(f"skipped {item.config_id}: {item.reason}", flush=True)
    print(f"Done: queued={len(result.queued)} skipped={len(result.skipped)}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Queue regenerate for all active VPN configs")
    parser.add_argument("--config", type=Path, default=None, help="Path to panel.yaml")
    parser.add_argument(
        "--username",
        required=True,
        help="Panel admin username recorded as requested_by in audit/tasks",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_regenerate_all(args.config, args.username)))


if __name__ == "__main__":
    main()
