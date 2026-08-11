from __future__ import annotations

import random
from typing import Any
from urllib.parse import quote

from panel.domain.value_objects.config_profile import ConfigProfile
from panel.infrastructure.vpn.template_loader import find_inbound

_SHARE_LABELS: dict[ConfigProfile, str] = {
    ConfigProfile.XRAY_REALITY: "Reality-Dynamic",
    ConfigProfile.XRAY_XHTTP: "XHTTP-Dynamic",
    ConfigProfile.XRAY_GRPC: "gRPC-Dynamic",
    ConfigProfile.HYSTERIA2: "Hysteria2-Dynamic",
}

_REALITY_FINGERPRINTS = ("chrome", "firefox", "safari", "randomized")


def pick_server_name(names: list[Any]) -> str:
    """Pick a random non-empty serverName; empty string is skipped."""
    candidates = [str(name).strip() for name in names if str(name).strip()]
    if not candidates:
        return ""
    return random.choice(candidates)


def pick_reality_fingerprint() -> str:
    return random.choice(_REALITY_FINGERPRINTS)


def dest_hostname(dest: str) -> str:
    """Extract host from Reality dest like 'ya.ru:443' (not for IPv6 brackets)."""
    value = str(dest).strip()
    if not value:
        return ""
    if ":" in value and not value.startswith("["):
        return value.rsplit(":", 1)[0].strip()
    return value


def reality_share_sni(reality: dict[str, Any]) -> str:
    """SNI must match dest hostname (anti-DPI); fall back to serverNames."""
    host = dest_hostname(str(reality.get("dest") or ""))
    if host:
        return host
    return pick_server_name(list(reality.get("serverNames") or []))


def _pin_hex(cert_fingerprint: str) -> str:
    return cert_fingerprint.replace(":", "").upper()


def build_share_uris(
    profile: ConfigProfile,
    config_data: dict[str, Any],
    *,
    host: str,
    public_key: str,
    cert_fingerprint: str = "",
    inbound_tag: str = "",
    secure: bool = True,
    public_port: int | None = None,
) -> list[str]:
    label = _SHARE_LABELS.get(profile, profile.value)

    if profile is ConfigProfile.HYSTERIA2:
        return [
            _build_hysteria2_uri(
                config_data,
                host=host,
                cert_fingerprint=cert_fingerprint,
                label=label,
                secure=secure,
                public_port=public_port,
            ),
        ]

    inbound = find_inbound(config_data, inbound_tag)
    port = int(public_port) if public_port else int(inbound["port"])
    client_id = inbound["settings"]["clients"][0]["id"]

    if profile is ConfigProfile.XRAY_REALITY:
        return [_build_reality_uri(inbound, client_id, host, port, public_key, label, secure=secure)]
    if profile is ConfigProfile.XRAY_XHTTP:
        return [
            _build_xhttp_uri(
                inbound,
                client_id,
                host,
                port,
                cert_fingerprint,
                label,
                secure=secure,
            ),
        ]
    if profile is ConfigProfile.XRAY_GRPC:
        return [
            _build_grpc_uri(
                inbound,
                client_id,
                host,
                port,
                cert_fingerprint,
                label,
                secure=secure,
            ),
        ]
    return []


def _build_reality_uri(
    inbound: dict[str, Any],
    client_id: str,
    host: str,
    port: int,
    public_key: str,
    label: str,
    *,
    secure: bool,
) -> str:
    reality = inbound["streamSettings"]["realitySettings"]
    short_id = reality["shortIds"][0]
    flow = inbound["settings"]["clients"][0].get("flow", "xtls-rprx-vision")
    sni = reality_share_sni(reality)
    # chrome is the most reliable uTLS profile across v2rayNG / Hiddify;
    # random safari/firefox/randomized often breaks phone clients.

    params = [
        "type=tcp",
        "security=reality",
        f"flow={flow}",
        "fp=chrome",
        f"pbk={public_key}",
        f"sid={short_id}",
    ]
    if sni:
        params.append(f"sni={quote(sni, safe='')}")
    # Do not set fragment=true: many phone cores hang or fail Reality handshake with it.
    return f"vless://{client_id}@{host}:{port}?{'&'.join(params)}#{quote(label)}"


def _build_xhttp_uri(
    inbound: dict[str, Any],
    client_id: str,
    host: str,
    port: int,
    cert_fingerprint: str,
    label: str,
    *,
    secure: bool,
) -> str:
    xhttp = inbound["streamSettings"]["xhttpSettings"]
    tls = inbound["streamSettings"].get("tlsSettings") or {}
    xhost = xhttp.get("host", host)
    path = xhttp.get("path", "/")
    mode = xhttp.get("mode", "stream-up")
    sni = tls.get("serverName") or host
    params = [
        "type=xhttp",
        "security=tls",
        f"host={quote(str(xhost), safe='')}",
        f"path={quote(str(path), safe='')}",
        f"mode={quote(str(mode), safe='')}",
        "fp=chrome",
        f"sni={quote(str(sni), safe='')}",
    ]
    # Dual share:
    # - secure: pcs only (Xray ≥26.6 removed allowInsecure; v2rayNG needs pin).
    # - insecure: insecure=1 for Hiddify / older cores; do not mix with pcs.
    if secure:
        pcs = _pin_hex(cert_fingerprint)
        if pcs:
            params.append(f"pcs={pcs}")
    else:
        params.append("insecure=1")
    return f"vless://{client_id}@{host}:{port}?{'&'.join(params)}#{quote(label)}"


def _build_grpc_uri(
    inbound: dict[str, Any],
    client_id: str,
    host: str,
    port: int,
    cert_fingerprint: str,
    label: str,
    *,
    secure: bool,
) -> str:
    tls = inbound["streamSettings"]["tlsSettings"]
    grpc = inbound["streamSettings"]["grpcSettings"]
    sni = tls.get("serverName") or host
    service_name = grpc.get("serviceName", "")

    params = [
        "type=grpc",
        "security=tls",
        f"serviceName={quote(str(service_name), safe='')}",
        "fp=chrome",
        f"sni={quote(str(sni), safe='')}",
    ]
    if secure:
        pcs = _pin_hex(cert_fingerprint)
        if pcs:
            params.append(f"pcs={pcs}")
    else:
        params.append("insecure=1")
    return f"vless://{client_id}@{host}:{port}?{'&'.join(params)}#{quote(label)}"


def _build_hysteria2_uri(
    config_data: dict[str, Any],
    *,
    host: str,
    cert_fingerprint: str,
    label: str,
    secure: bool,
    public_port: int | None = None,
) -> str:
    port = int(public_port) if public_port else int(str(config_data["listen"]).lstrip(":"))
    password = config_data["auth"]["password"]
    sni = config_data.get("sni") or config_data.get("tls", {}).get("sni") or host
    params = [f"sni={quote(str(sni), safe='')}"]

    obfs = config_data.get("obfs") or {}
    if str(obfs.get("type", "")).strip().lower() == "salamander":
        obfs_password = (obfs.get("salamander") or {}).get("password")
        if obfs_password:
            params.append("obfs=salamander")
            params.append(f"obfs-password={quote(str(obfs_password), safe='')}")

    if secure:
        # URI scheme has no `ca=` param. pinSHA256 + insecure=0 is the secure share form;
        # clients that trust the pin (or import the cert) connect without insecure mode.
        pin = _pin_hex(cert_fingerprint)
        if pin:
            params.append(f"pinSHA256={pin}")
        params.append("insecure=0")
    else:
        params.append("insecure=1")
    return f"hysteria2://{quote(password, safe='')}@{host}:{port}?{'&'.join(params)}#{quote(label)}"
