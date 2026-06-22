#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
load_env

BROKER_URL="http://${VCP_BROKER_HOST}:${VCP_BROKER_PORT}"
BROKER_DB="${VCP_DATA_DIR}/broker.db"

exec "$(venv_python)" - "${BROKER_URL}" "${VCP_BROKER_API_KEY:-}" "${BROKER_DB}" <<'PY'
from __future__ import annotations

import json
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

broker_url = sys.argv[1].rstrip("/")
api_key = sys.argv[2]
broker_db = Path(sys.argv[3])

STATUSES = ("PENDING", "PROCESSING", "COMPLETED", "DEAD")


def request_json(path: str) -> dict:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(f"{broker_url}{path}", headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def task_total(status: str) -> int:
    payload = request_json(f"/api/v1/tasks?status={status}&limit=1&offset=0")
    return int(payload.get("total", 0))


def sqlite_pending_split() -> tuple[int, int]:
    if not broker_db.is_file():
        return 0, 0
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(f"file:{broker_db}?mode=ro", uri=True)
    try:
        ready = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'PENDING' AND available_at <= ?",
            (now,),
        ).fetchone()[0]
        scheduled = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'PENDING' AND available_at > ?",
            (now,),
        ).fetchone()[0]
        return int(ready), int(scheduled)
    finally:
        conn.close()


def main() -> None:
    print(f"Broker: {broker_url}")
    print()

    try:
        health = request_json("/api/v1/health")
        if health.get("status") != "ok":
            print(f"health: {health}")
    except urllib.error.URLError as exc:
        print(f"ERROR: broker unreachable: {exc}", file=sys.stderr)
        sys.exit(1)

    totals = {status: task_total(status) for status in STATUSES}
    pending_ready, pending_scheduled = sqlite_pending_split()

    # pending — в очереди на pull; waiting — отложены (retry) + в работе у воркера
    print(f"{'pending (ready)':<22} {pending_ready:>6}")
    print(f"{'waiting (scheduled)':<22} {pending_scheduled:>6}")
    print(f"{'waiting (processing)':<22} {totals['PROCESSING']:>6}")
    print(f"{'done (completed)':<22} {totals['COMPLETED']:>6}")
    print(f"{'dead':<22} {totals['DEAD']:>6}")
    print()
    print(
        f"pending total: {totals['PENDING']:>6}  "
        f"(ready {pending_ready} + scheduled {pending_scheduled})"
    )

    if totals["PENDING"] != pending_ready + pending_scheduled:
        print(
            "note: pending split from broker.db; API pending total may differ slightly",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
PY
