from __future__ import annotations

import os
import shlex
import subprocess


def _systemctl_command() -> list[str]:
    raw = os.environ.get("VPN_SYSTEMCTL_CMD", "systemctl")
    return shlex.split(raw)


def reload_service(service_name: str) -> None:
    subprocess.run(
        [*_systemctl_command(), "reload", service_name],
        check=True,
        timeout=30,
    )
