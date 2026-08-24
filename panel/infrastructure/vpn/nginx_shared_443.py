"""Sync nginx stream SNI mux after Reality/xHTTP create/regenerate."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from panel.config import PanelSettings, VpnProfileSettings
from panel.domain.value_objects.config_profile import ConfigProfile
from panel.infrastructure.vpn.client_uri import dest_hostname
from panel.infrastructure.vpn.systemd_reload import run_systemctl
from panel.infrastructure.vpn.template_loader import find_inbound

logger = logging.getLogger(__name__)

DEFAULT_STREAM_CONF = Path("/etc/nginx/stream.d/vcp-shared-443.conf")
DEFAULT_PANEL_BACKEND = "127.0.0.1:8443"

_MUX_PROFILES = (
    ConfigProfile.XRAY_REALITY.value,
    ConfigProfile.XRAY_XHTTP.value,
    ConfigProfile.XRAY_GRPC.value,
)


def shared_443_enabled(profile: VpnProfileSettings) -> bool:
    return bool(profile.share_public_port and profile.listen_address)


def panel_sni_hosts(settings: PanelSettings) -> list[str]:
    hosts: list[str] = []
    for candidate in [settings.vpn.public_host, *settings.vpn.public_host_aliases]:
        value = (candidate or "").strip()
        if value and value not in hosts:
            hosts.append(value)
    return hosts


def reality_sni_hosts(profile: VpnProfileSettings, config_data: dict[str, Any]) -> list[str]:
    hosts: set[str] = set()
    for dest in profile.reality_dest_hosts:
        host = dest_hostname(dest)
        if host:
            hosts.add(host)
    for name in profile.reality_server_names:
        if name.strip():
            hosts.add(name.strip())
    try:
        inbound = find_inbound(config_data, profile.inbound_tag or "inbound-reality")
    except Exception:
        inbound = (config_data.get("inbounds") or [{}])[0]
    reality = (inbound.get("streamSettings") or {}).get("realitySettings") or {}
    for name in reality.get("serverNames") or []:
        if isinstance(name, str) and name.strip():
            hosts.add(name.strip())
    dest = reality.get("dest")
    if dest:
        host = dest_hostname(str(dest))
        if host:
            hosts.add(host)
    return sorted(hosts)


def render_shared_443_stream_conf(
    *,
    panel_snis: list[str],
    panel_backend: str,
    routes: list[tuple[str, str]],
) -> str:
    """routes: (sni, backend) for non-panel traffic (Reality, xHTTP, …).

    Duplicate SNIs are collapsed (last wins) — nginx map rejects conflicting keys.
    """
    panel_set = {s.strip() for s in panel_snis if s.strip()}
    lines: list[str] = []
    for sni in panel_snis:
        sni = sni.strip()
        if sni:
            lines.append(f"    {sni} {panel_backend};")
    by_sni: dict[str, str] = {}
    for sni, backend in routes:
        sni = sni.strip()
        backend = backend.strip()
        if not sni or not backend or sni in panel_set:
            continue
        prev = by_sni.get(sni)
        if prev is not None and prev != backend:
            logger.warning(
                "shared-443 duplicate SNI %s: keeping %s, dropping %s",
                sni,
                backend,
                prev,
            )
        by_sni[sni] = backend
    for sni, backend in by_sni.items():
        lines.append(f"    {sni} {backend};")
    map_body = "\n".join(lines) if lines else f"    default {panel_backend};"
    return (
        "# Managed by VpnControlPanel — do not edit by hand.\n"
        "# Updated automatically on Reality/xHTTP create/regenerate when share_public_port is set.\n"
        "\n"
        "map $ssl_preread_server_name $vcp_443_backend {\n"
        f"{map_body}\n"
        f"    default {panel_backend};\n"
        "}\n"
        "\n"
        "server {\n"
        "    listen 443 reuseport;\n"
        "    listen [::]:443 reuseport;\n"
        "    proxy_pass $vcp_443_backend;\n"
        "    ssl_preread on;\n"
        "    proxy_connect_timeout 10s;\n"
        "    proxy_timeout 300s;\n"
        "}\n"
    )


def _inbound_backend(inbound: dict[str, Any], *, fallback_listen: str | None) -> str | None:
    port = inbound.get("port")
    if not isinstance(port, int) or port < 1:
        return None
    listen = str(inbound.get("listen") or fallback_listen or "127.0.0.1").strip()
    if listen in {"0.0.0.0", "::", ""}:
        listen = "127.0.0.1"
    return f"{listen}:{port}"


def _load_live_configs_for_profile(
    settings: PanelSettings,
    profile_key: str,
) -> list[dict[str, Any]]:
    profile = settings.vpn.profiles.get(profile_key)
    if profile is None:
        return []
    root = settings.systemd.xray_config_dir
    if profile_key == ConfigProfile.HYSTERIA2.value:
        root = settings.systemd.hysteria_config_dir
    if not root.is_dir():
        return []
    tag = profile.inbound_tag
    items: list[dict[str, Any]] = []
    pattern = "*/config.yaml" if profile_key == ConfigProfile.HYSTERIA2.value else "*/config.json"
    for path in sorted(root.glob(pattern)):
        try:
            if profile_key == ConfigProfile.HYSTERIA2.value:
                import yaml

                data = yaml.safe_load(path.read_text(encoding="utf-8"))
            else:
                data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, Exception):
            continue
        if not isinstance(data, dict):
            continue
        if not tag:
            items.append(data)
            continue
        try:
            find_inbound(data, tag)
            items.append(data)
        except KeyError:
            continue
    return items


def _tls_host_from_config(profile_key: str, data: dict[str, Any], profile: VpnProfileSettings) -> str | None:
    if profile_key == ConfigProfile.HYSTERIA2.value:
        host = ((data.get("tls") or {}).get("sni") or "").strip()
        return host or None
    try:
        inbound = find_inbound(data, profile.inbound_tag)
    except Exception:
        return None
    stream = inbound.get("streamSettings") or {}
    tls = stream.get("tlsSettings") or {}
    host = (tls.get("serverName") or "").strip()
    if host:
        return host
    xhttp = stream.get("xhttpSettings") or {}
    host = (xhttp.get("host") or "").strip()
    return host or None


def _detect_mux_profile_key(settings: PanelSettings, config_data: dict[str, Any]) -> str | None:
    """Return mux profile key whose inbound_tag is present in config_data."""
    for key in _MUX_PROFILES:
        profile = settings.vpn.profiles.get(key)
        tag = (profile.inbound_tag if profile is not None else None) or ""
        if not tag:
            continue
        try:
            find_inbound(config_data, tag)
            return key
        except Exception:
            continue
    return None


def _routes_for_mux_profile(
    settings: PanelSettings,
    profile_key: str,
    config_data: dict[str, Any] | None,
) -> list[tuple[str, str]]:
    profile = settings.vpn.profiles.get(profile_key)
    if profile is None or not shared_443_enabled(profile):
        return []

    if profile_key == ConfigProfile.XRAY_REALITY.value:
        data = config_data or (_load_live_configs_for_profile(settings, profile_key) or [None])[0]
        if data is None:
            return []
        try:
            inbound = find_inbound(data, profile.inbound_tag)
        except Exception:
            return []
        backend = _inbound_backend(inbound, fallback_listen=profile.listen_address)
        if not backend:
            return []
        return [(sni, backend) for sni in reality_sni_hosts(profile, data)]

    live_items = _load_live_configs_for_profile(settings, profile_key)
    if config_data is not None:
        # Append last so this config wins SNI collisions after dedupe.
        live_items = [*live_items, config_data]

    # host -> backend (last wins). Same SNI cannot map to two backends in nginx.
    by_host: dict[str, str] = {}
    seen_backends: set[str] = set()
    for data in live_items:
        try:
            inbound = find_inbound(data, profile.inbound_tag)
        except Exception:
            continue
        backend = _inbound_backend(inbound, fallback_listen=profile.listen_address)
        if not backend or backend in seen_backends:
            continue
        host = _tls_host_from_config(profile_key, data, profile)
        if not host:
            host = (profile.share_public_host or settings.vpn.public_host or "").strip()
        if not host:
            continue
        prev = by_host.get(host)
        if prev is not None and prev != backend:
            logger.warning(
                "shared-443 profile %s: SNI %s backend %s replaces %s",
                profile_key,
                host,
                backend,
                prev,
            )
        by_host[host] = backend
        seen_backends.add(backend)
    return list(by_host.items())


def sync_reality_shared_443(settings: PanelSettings, config_data: dict[str, Any]) -> None:
    """Rewrite stream mux (panel aliases + Reality + other mux profiles) and reload nginx."""
    reality = settings.vpn.profiles.get(ConfigProfile.XRAY_REALITY.value)
    if reality is None or not shared_443_enabled(reality):
        return

    panel_snis = panel_sni_hosts(settings)
    if not panel_snis:
        logger.warning("shared-443 sync skipped: empty panel SNI list")
        return

    panel_backend = (reality.nginx_panel_backend or DEFAULT_PANEL_BACKEND).strip()
    owner = _detect_mux_profile_key(settings, config_data)
    routes: list[tuple[str, str]] = []
    for key in _MUX_PROFILES:
        # Inject only into the matching profile; other profiles scan live on disk.
        injected = config_data if key == owner else None
        routes.extend(_routes_for_mux_profile(settings, key, injected))

    conf = render_shared_443_stream_conf(
        panel_snis=panel_snis,
        panel_backend=panel_backend,
        routes=routes,
    )
    conf_path = Path(reality.nginx_stream_conf or DEFAULT_STREAM_CONF)
    run_systemctl("write-nginx-stream", conf_path.as_posix(), input_text=conf)
    run_systemctl("reload-nginx")
    logger.info(
        "synced nginx shared-443: panel=%s owner=%s routes=%s",
        ",".join(panel_snis),
        owner,
        ",".join(f"{sni}->{backend}" for sni, backend in routes),
    )


# Back-compat alias kept for importers that still pass the old keyword style via wrapper.
def render_shared_443_stream_conf_legacy(**kwargs: Any) -> str:
    if "panel_snis" in kwargs or "routes" in kwargs:
        return render_shared_443_stream_conf(**kwargs)
    return render_shared_443_stream_conf(
        panel_snis=[kwargs["panel_sni"]],
        panel_backend=kwargs["panel_backend"],
        routes=[(sni, kwargs["reality_backend"]) for sni in kwargs.get("reality_snis", [])],
    )
