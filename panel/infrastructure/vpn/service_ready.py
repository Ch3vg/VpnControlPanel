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

_FAILED_RESULTS = frozenset({"exit-code", "signal", "core-dump", "timeout"})


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


def _systemd_show(service_name: str) -> dict[str, str]:
    result = subprocess.run(
        ["systemctl", "show", service_name, "-p", "ActiveState", "-p", "SubState", "-p", "Result"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    props: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            props[key] = value
    return props


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


def _systemd_start_failed(service_name: str) -> bool:
    failed = subprocess.run(
        ["systemctl", "is-failed", service_name],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if failed.stdout.strip() == "failed":
        return True

    props = _systemd_show(service_name)
    active_state = props.get("ActiveState", "")
    if active_state == "failed":
        return True
    if active_state in ("activating", "active", "reloading"):
        return False

    result = props.get("Result", "")
    return result in _FAILED_RESULTS


def _raise_service_failed(service_name: str) -> None:
    log_tail = _run_journalctl(service_name, lines=20)
    raise ServiceNotReadyError(
        f"Service {service_name} failed during startup. Recent log:\n{log_tail}",
    )


def _wait_direct_once(service_name: str, profile: ConfigProfile, settings: SystemdSettings) -> bool:
    deadline = time.monotonic() + settings.service_ready_timeout_seconds
    while time.monotonic() < deadline:
        if _systemd_start_failed(service_name):
            _raise_service_failed(service_name)
        if _systemd_running(service_name):
            time.sleep(settings.service_ready_settle_seconds)
            if _systemd_start_failed(service_name):
                _raise_service_failed(service_name)
            if _systemd_running(service_name) and _journal_has_startup_marker(service_name, profile):
                return True
        time.sleep(1)
    return False


def _wait_via_wrapper_once(service_name: str, profile: ConfigProfile, settings: SystemdSettings) -> None:
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
        if _systemd_start_failed(service_name):
            _raise_service_failed(service_name)
        detail = (result.stderr or result.stdout or "").strip()
        raise ServiceNotReadyError(
            f"Service {service_name} not ready after "
            f"{settings.service_ready_timeout_seconds}s: {detail or 'wait-ready failed'}",
        )


def wait_for_service_ready(
    service_name: str,
    profile: ConfigProfile,
    settings: SystemdSettings,
) -> None:
    max_deadline = time.monotonic() + settings.service_ready_max_wait_seconds
    use_wrapper = _uses_vpn_systemctl_wrapper() and _service_managed_by_wrapper(service_name, settings)
    last_detail = ""

    while time.monotonic() < max_deadline:
        if _systemd_start_failed(service_name):
            _raise_service_failed(service_name)

        try:
            if use_wrapper:
                _wait_via_wrapper_once(service_name, profile, settings)
                return
            if _wait_direct_once(service_name, profile, settings):
                return
            last_detail = f"not ready after {settings.service_ready_timeout_seconds}s chunk"
        except ServiceNotReadyError as exc:
            if _systemd_start_failed(service_name):
                raise
            last_detail = str(exc)
            if time.monotonic() >= max_deadline:
                raise
            continue

        if time.monotonic() >= max_deadline:
            break

    log_tail = _run_journalctl(service_name, lines=20)
    raise ServiceNotReadyError(
        f"Service {service_name} did not become ready within "
        f"{settings.service_ready_max_wait_seconds}s "
        f"({settings.service_ready_timeout_seconds}s per attempt). "
        f"{last_detail}. Recent log:\n{log_tail}",
    )
