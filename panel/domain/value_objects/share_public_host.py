"""Normalize / validate public share hostnames."""

from __future__ import annotations

import re

_HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$",
)


class InvalidSharePublicHost(ValueError):
    pass


def normalize_share_public_host(value: str | None) -> str | None:
    """Return stripped hostname or None. Raises InvalidSharePublicHost if invalid."""
    if value is None:
        return None
    host = value.strip().lower().rstrip(".")
    if not host:
        return None
    if host.startswith("http://") or host.startswith("https://"):
        raise InvalidSharePublicHost("Укажите только hostname без схемы (например foo.example.com)")
    if "/" in host or ":" in host or " " in host:
        raise InvalidSharePublicHost("Hostname не должен содержать порт, путь или пробелы")
    if not _HOST_RE.match(host):
        raise InvalidSharePublicHost(f"Некорректный hostname: {value}")
    return host
