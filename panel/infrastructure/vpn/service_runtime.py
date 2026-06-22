from __future__ import annotations

import socket
import uuid
from dataclasses import dataclass

from panel.config import PanelSettings
from panel.domain.value_objects.config_profile import ConfigProfile
from panel.infrastructure.persistence.repositories.vpn_config import ConfigVersionSnapshot
from panel.infrastructure.vpn.service_ready import _systemd_running
from panel.infrastructure.vpn.systemd_unit import config_service_name


@dataclass(frozen=True, slots=True)
class ServiceRuntimeProbe:
    online: bool | None
    systemd_active: bool | None
    port_listening: bool | None
    detail: str | None = None


def is_tcp_port_open(port: int, *, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _service_name_for_config(
    config_id: uuid.UUID,
    profile: ConfigProfile,
    settings: PanelSettings,
) -> str | None:
    if settings.systemd.per_config:
        return config_service_name(config_id, prefix=settings.systemd.service_prefix)
    profile_settings = settings.vpn.profiles.get(profile.value)
    if profile_settings is None:
        return None
    return profile_settings.service_name


def probe_config_runtime(
    *,
    config_id: uuid.UUID,
    profile: ConfigProfile,
    port: int | None,
    settings: PanelSettings,
) -> ServiceRuntimeProbe:
    service_name = _service_name_for_config(config_id, profile, settings)
    if service_name is None:
        return ServiceRuntimeProbe(
            online=None,
            systemd_active=None,
            port_listening=None,
            detail="service name not configured",
        )

    try:
        systemd_active = _systemd_running(service_name)
    except OSError:
        return ServiceRuntimeProbe(
            online=None,
            systemd_active=None,
            port_listening=None,
            detail="systemctl unavailable",
        )

    port_listening: bool | None = None
    if port is not None and profile is not ConfigProfile.HYSTERIA2:
        port_listening = is_tcp_port_open(port)

    if profile is ConfigProfile.HYSTERIA2 or port is None:
        online = systemd_active
        if online:
            detail = None
        else:
            detail = "service not running"
    elif systemd_active and port_listening:
        online = True
        detail = None
    else:
        online = False
        if not systemd_active:
            detail = "service not running"
        else:
            detail = f"port {port} not listening"

    return ServiceRuntimeProbe(
        online=online,
        systemd_active=systemd_active,
        port_listening=port_listening,
        detail=detail,
    )


def probe_config_availability(
    *,
    config_id: uuid.UUID,
    profile: ConfigProfile,
    port: int | None,
    settings: PanelSettings,
    snapshot: ConfigVersionSnapshot | None = None,
) -> ServiceRuntimeProbe:
    runtime = probe_config_runtime(
        config_id=config_id,
        profile=profile,
        port=port,
        settings=settings,
    )
    if not runtime.online or snapshot is None:
        return runtime

    from panel.infrastructure.vpn.vpn_connectivity import probe_config_connectivity

    connectivity = probe_config_connectivity(snapshot, settings)
    if connectivity.reachable is None:
        return runtime
    if connectivity.reachable:
        return ServiceRuntimeProbe(
            online=True,
            systemd_active=runtime.systemd_active,
            port_listening=runtime.port_listening,
            detail=None,
        )
    return ServiceRuntimeProbe(
        online=False,
        systemd_active=runtime.systemd_active,
        port_listening=runtime.port_listening,
        detail=connectivity.detail or "connectivity probe failed",
    )
