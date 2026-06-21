from __future__ import annotations

from typing import Any
from urllib.parse import quote

from panel.domain.value_objects.config_profile import ConfigProfile
from panel.infrastructure.vpn.template_loader import find_inbound

_SHARE_LABELS: dict[ConfigProfile, str] = {
    ConfigProfile.XRAY_REALITY: "Reality-Dynamic",
    ConfigProfile.XRAY_XHTTP: "XHTTP-Dynamic",
    ConfigProfile.XRAY_GRPC: "gRPC-Dynamic",
    ConfigProfile.HYSTERIA2: "Hysteria2-Dynamic",
    ConfigProfile.XRAY_CLIENT_IN: "Client-In",
}


def _pick_server_name(names: list[Any]) -> str:
    for name in names:
        text = str(name).strip()
        if text:
            return text
    return ""


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
            ),
        ]

    inbound = find_inbound(config_data, inbound_tag)
    port = int(inbound["port"])
    client_id = inbound["settings"]["clients"][0]["id"]

    if profile is ConfigProfile.XRAY_REALITY:
        return [_build_reality_uri(inbound, client_id, host, port, public_key, label, secure=secure)]
    if profile is ConfigProfile.XRAY_XHTTP:
        return [_build_xhttp_uri(inbound, client_id, host, port, label)]
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
    sni = _pick_server_name(reality.get("serverNames", []))

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
    if secure:
        params.append("fragment=true")
    return f"vless://{client_id}@{host}:{port}?{'&'.join(params)}#{quote(label)}"


def _build_xhttp_uri(
    inbound: dict[str, Any],
    client_id: str,
    host: str,
    port: int,
    label: str,
) -> str:
    xhttp = inbound["streamSettings"]["xhttpSettings"]
    xhost = xhttp.get("host", host)
    path = xhttp.get("path", "/")
    mode = xhttp.get("mode", "packet-up")
    params = [
        "type=xhttp",
        "security=none",
        f"host={quote(str(xhost), safe='')}",
        f"path={quote(str(path), safe='')}",
        f"mode={quote(str(mode), safe='')}",
    ]
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
        "fingerprint=randomized",
        f"sni={quote(str(sni), safe='')}",
    ]
    if secure:
        pcs = _pin_hex(cert_fingerprint)
        if pcs:
            params.append(f"pcs={pcs}")
        params.extend(["insecure=0", "fragment=true"])
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
) -> str:
    port = int(str(config_data["listen"]).lstrip(":"))
    password = config_data["auth"]["password"]
    sni = config_data.get("sni") or config_data.get("tls", {}).get("sni") or "ya.ru"
    params = [f"sni={quote(str(sni), safe='')}"]
    if secure:
        pin = _pin_hex(cert_fingerprint)
        if pin:
            params.append(f"pinSHA256={pin}")
        params.append("insecure=0")
    else:
        params.append("insecure=1")
    return f"hysteria2://{quote(password, safe='')}@{host}:{port}?{'&'.join(params)}#{quote(label)}"
