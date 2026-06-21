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


def run_systemctl(action: str, service_name: str | None = None) -> None:
    cmd = [*_systemctl_command(), action]
    if service_name is not None:
        cmd.append(service_name)
    subprocess.run(cmd, check=True, timeout=30)


def reload_service(service_name: str) -> None:
    run_systemctl(_systemctl_action(), service_name)


def enable_service(service_name: str) -> None:
    run_systemctl("enable", service_name)


def write_unit_file(service_name: str, content: str) -> None:
    cmd = [*_systemctl_command(), "write-unit", service_name]
    subprocess.run(cmd, input=content.encode(), check=True, timeout=30)
