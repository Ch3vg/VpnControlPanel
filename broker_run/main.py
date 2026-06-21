from __future__ import annotations

import argparse
from pathlib import Path

from broker import Broker

from broker_run.config import load_broker_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the task broker HTTP server")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to broker.yaml (default: ./broker.yaml or BROKER_CONFIG_PATH)",
    )
    args = parser.parse_args()

    settings = load_broker_settings(args.config)
    queue = settings.queue

    broker = Broker(
        dsn=settings.database.dsn,
        host=settings.server.host,
        port=settings.server.port,
        default_lock_ttl_seconds=queue.default_lock_ttl_seconds,
        default_max_retries=queue.default_max_retries,
        retry_delay_seconds=queue.retry_delay_seconds,
        default_pull_timeout_seconds=queue.default_pull_timeout_seconds,
        pull_interval_seconds=queue.pull_interval_seconds,
        api_key=settings.security.api_key,
        log_level=settings.logging.level,
    )
    broker.run()


if __name__ == "__main__":
    main()
