from __future__ import annotations

import os
import shlex
import subprocess


def _systemctl_command() -> list[str]:
    raw = os.environ.get("VPN_SYSTEMCTL_CMD", "systemctl")
    return shlex.split(raw)


def _systemctl_action() -> str:
    action = os.environ.get("VPN_SYSTEMCTL_ACTION", "restart").strip().lower()
    if action not in {"reload", "restart"}:
        raise ValueError(f"VPN_SYSTEMCTL_ACTION must be 'reload' or 'restart', got: {action}")
    return action


def reload_service(service_name: str) -> None:
    subprocess.run(
        [*_systemctl_command(), _systemctl_action(), service_name],
        check=True,
        timeout=30,
    )
