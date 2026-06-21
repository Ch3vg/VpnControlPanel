from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

from panel.config import SystemdSettings
from panel.domain.value_objects.config_profile import ConfigProfile
from panel.infrastructure.filesystem.writer import atomic_write
from panel.infrastructure.vpn.systemd_reload import (
    enable_service,
    reload_service,
    remove_unit_file,
    run_systemctl,
    write_unit_file,
)


def config_service_name(config_id: uuid.UUID, *, prefix: str = "vpn") -> str:
    return f"{prefix}-{config_id}"


def live_config_path(
    profile: ConfigProfile,
    config_id: uuid.UUID,
    config_filename: str,
    settings: SystemdSettings,
) -> Path:
    if profile is ConfigProfile.HYSTERIA2:
        base = settings.hysteria_config_dir
    else:
        base = settings.xray_config_dir
    return base / f"{config_id}" / config_filename


def unit_file_path(service_name: str, settings: SystemdSettings) -> Path:
    return settings.unit_dir / f"{service_name}.service"


def render_unit(
    profile: ConfigProfile,
    *,
    service_name: str,
    config_path: Path,
    config_name: str,
    settings: SystemdSettings,
) -> str:
    description = config_name.strip() or service_name
    if profile is ConfigProfile.HYSTERIA2:
        exec_start = f"{settings.hysteria_binary.as_posix()} server -c {config_path.as_posix()}"
    else:
        exec_start = f"{settings.xray_binary.as_posix()} run -config {config_path.as_posix()}"

    return (
        "[Unit]\n"
        f"Description=VPN {description} ({profile.value})\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={exec_start}\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "LimitNOFILE=1048576\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def install_config_unit(
    profile: ConfigProfile,
    config_id: uuid.UUID,
    *,
    config_filename: str,
    config_name: str,
    settings: SystemdSettings,
) -> str:
    service_name = config_service_name(config_id, prefix=settings.service_prefix)
    config_path = live_config_path(profile, config_id, config_filename, settings)
    unit_path = unit_file_path(service_name, settings)
    unit_content = render_unit(
        profile,
        service_name=service_name,
        config_path=config_path,
        config_name=config_name,
        settings=settings,
    )

    first_install = not unit_path.is_file()
    try:
        atomic_write(unit_path, unit_content, mode=0o644)
    except PermissionError:
        write_unit_file(service_name, unit_content)
    if first_install:
        run_systemctl("daemon-reload")
        enable_service(service_name)
    reload_service(service_name)
    return service_name


def remove_config_unit(
    profile: ConfigProfile,
    config_id: uuid.UUID,
    *,
    config_filename: str,
    settings: SystemdSettings,
) -> None:
    service_name = config_service_name(config_id, prefix=settings.service_prefix)
    unit_path = unit_file_path(service_name, settings)
    if not unit_path.is_file():
        return

    try:
        for action in ("stop", "disable"):
            try:
                run_systemctl(action, service_name)
            except subprocess.CalledProcessError:
                pass
        unit_path.unlink()
        run_systemctl("daemon-reload")
    except (OSError, PermissionError, subprocess.CalledProcessError):
        remove_unit_file(service_name)

    live_dir = live_config_path(profile, config_id, config_filename, settings).parent
    shutil.rmtree(live_dir, ignore_errors=True)
