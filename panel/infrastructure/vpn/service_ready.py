from __future__ import annotations

import os
import re
import shlex
import subprocess
import time

from panel.config import SystemdSettings
from panel.domain.value_objects.config_profile import ConfigProfile

_STARTUP_PATTERNS: dict[ConfigProfile, re.Pattern[str]] = {
    ConfigProfile.XRAY_REALITY: re.compile(r"\bstarted\b", re.IGNORECASE),
    ConfigProfile.XRAY_GRPC: re.compile(r"\bstarted\b", re.IGNORECASE),
    ConfigProfile.XRAY_XHTTP: re.compile(r"\bstarted\b", re.IGNORECASE),
    ConfigProfile.XRAY_CLIENT_IN: re.compile(r"\bstarted\b", re.IGNORECASE),
    ConfigProfile.HYSTERIA2: re.compile(r"listening|server up|started", re.IGNORECASE),
}


class ServiceNotReadyError(RuntimeError):
    pass


def startup_log_pattern(profile: ConfigProfile) -> str:
    pattern = _STARTUP_PATTERNS.get(profile)
    if pattern is None:
        return r"started|listening"
    return pattern.pattern


def _systemctl_command() -> list[str]:
    raw = os.environ.get("VPN_SYSTEMCTL_CMD", "systemctl")
    return shlex.split(raw)


def _uses_vpn_systemctl_wrapper() -> bool:
    return "vpn-systemctl" in os.environ.get("VPN_SYSTEMCTL_CMD", "")


def _service_managed_by_wrapper(service_name: str, settings: SystemdSettings) -> bool:
    prefix = f"{settings.service_prefix}-"
    return service_name.startswith(prefix)


def _run_journalctl(service_name: str, *, lines: int = 40) -> str:
    result = subprocess.run(
        ["journalctl", "-u", service_name, "-n", str(lines), "--no-pager"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    return result.stdout + result.stderr


def _journal_has_startup_marker(service_name: str, profile: ConfigProfile) -> bool:
    log = _run_journalctl(service_name)
    pattern = _STARTUP_PATTERNS.get(profile, re.compile(r"started|listening", re.IGNORECASE))
    return pattern.search(log) is not None


def _systemd_running(service_name: str) -> bool:
    active = subprocess.run(
        ["systemctl", "is-active", service_name],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if active.stdout.strip() != "active":
        return False
    state = subprocess.run(
        ["systemctl", "show", "-p", "SubState", "--value", service_name],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return state.stdout.strip() == "running"


def _wait_direct(service_name: str, profile: ConfigProfile, settings: SystemdSettings) -> None:
    deadline = time.monotonic() + settings.service_ready_timeout_seconds
    while time.monotonic() < deadline:
        if _systemd_running(service_name):
            time.sleep(settings.service_ready_settle_seconds)
            if _systemd_running(service_name) and _journal_has_startup_marker(service_name, profile):
                return
        time.sleep(1)

    log_tail = _run_journalctl(service_name, lines=20)
    raise ServiceNotReadyError(
        f"Service {service_name} did not become ready within "
        f"{settings.service_ready_timeout_seconds}s. Recent log:\n{log_tail}",
    )


def _wait_via_wrapper(service_name: str, profile: ConfigProfile, settings: SystemdSettings) -> None:
    env = os.environ.copy()
    env["VPN_SERVICE_READY_TIMEOUT"] = str(settings.service_ready_timeout_seconds)
    env["VPN_SERVICE_READY_SETTLE"] = str(settings.service_ready_settle_seconds)
    env["VPN_SERVICE_READY_LOG_PATTERN"] = startup_log_pattern(profile)
    cmd = [*_systemctl_command(), "wait-ready", service_name]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=settings.service_ready_timeout_seconds + 20,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ServiceNotReadyError(
            f"Service {service_name} did not become ready: {detail or 'wait-ready failed'}",
        )


def wait_for_service_ready(
    service_name: str,
    profile: ConfigProfile,
    settings: SystemdSettings,
) -> None:
    if _uses_vpn_systemctl_wrapper() and _service_managed_by_wrapper(service_name, settings):
        _wait_via_wrapper(service_name, profile, settings)
    else:
        _wait_direct(service_name, profile, settings)
