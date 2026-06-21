from __future__ import annotations

import argparse
import asyncio
import getpass
from pathlib import Path

from panel.config import load_panel_settings
from panel.infrastructure.persistence.database import create_engine, create_session_factory
from panel.infrastructure.persistence.repositories.user import UserRepository
from panel.infrastructure.security import hash_password


async def _create_admin(config_path: Path | None, username: str, password: str) -> None:
    settings = load_panel_settings(config_path)
    engine = create_engine(settings.database.url)
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        users = UserRepository(session)
        existing = await users.get_by_username(username)
        if existing is not None:
            raise SystemExit(f"User already exists: {username}")
        await users.create(username, hash_password(password))
        await session.commit()
    await engine.dispose()
    print(f"Admin user created: {username}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an admin user")
    parser.add_argument("--config", type=Path, default=None, help="Path to panel.yaml")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", default=None, help="If omitted, prompt securely")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Password: ")
    if not password:
        raise SystemExit("Password must not be empty")

    asyncio.run(_create_admin(args.config, args.username, password))


if __name__ == "__main__":
    main()
