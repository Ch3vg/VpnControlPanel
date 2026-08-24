"""Fetch systemd journal lines for a VPN config unit."""

from __future__ import annotations

import logging
import os
import shlex
import subprocess

from panel.config import SystemdSettings

logger = logging.getLogger(__name__)

DEFAULT_LOG_LINES = 100
MAX_LOG_LINES = 500


def clamp_log_lines(lines: int | None) -> int:
    if lines is None:
        return DEFAULT_LOG_LINES
    return max(1, min(MAX_LOG_LINES, int(lines)))


def _systemctl_command() -> list[str]:
    raw = os.environ.get("VPN_SYSTEMCTL_CMD", "systemctl")
    return shlex.split(raw)


def _uses_vpn_systemctl_wrapper() -> bool:
    return "vpn-systemctl" in os.environ.get("VPN_SYSTEMCTL_CMD", "")


def _service_managed_by_wrapper(service_name: str, settings: SystemdSettings) -> bool:
    prefix = f"{settings.service_prefix}-"
    return service_name.startswith(prefix)


def fetch_unit_journal(
    service_name: str,
    *,
    lines: int = DEFAULT_LOG_LINES,
    settings: SystemdSettings | None = None,
) -> tuple[str, bool]:
    """Return (text, ok). ok=False when journalctl/wrapper failed."""
    lines = clamp_log_lines(lines)
    if settings is not None and _uses_vpn_systemctl_wrapper() and _service_managed_by_wrapper(
        service_name,
        settings,
    ):
        cmd = [*_systemctl_command(), "logs", service_name, str(lines)]
    else:
        cmd = ["journalctl", "-u", service_name, "-n", str(lines), "--no-pager", "-o", "short-iso"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("journal fetch failed for %s: %s", service_name, exc)
        return f"Failed to read journal for {service_name}: {exc}", False

    text = (result.stdout or "").rstrip()
    if result.returncode != 0:
        err = (result.stderr or "").strip() or text or f"exit {result.returncode}"
        return err, False
    if not text:
        return f"(no journal entries for {service_name})", True
    return text, True
