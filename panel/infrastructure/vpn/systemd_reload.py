from __future__ import annotations

import subprocess


def reload_service(service_name: str) -> None:
    subprocess.run(
        ["systemctl", "reload", service_name],
        check=True,
        timeout=30,
    )
