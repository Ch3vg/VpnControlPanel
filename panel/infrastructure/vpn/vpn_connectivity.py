from __future__ import annotations

import json
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from panel.config import PanelSettings
from panel.domain.value_objects.config_profile import ConfigProfile
from panel.infrastructure.persistence.repositories.vpn_config import ConfigVersionSnapshot
from panel.infrastructure.vpn.client_uri import _pin_hex
from panel.infrastructure.vpn.service_runtime import is_tcp_port_open
from panel.infrastructure.vpn.template_loader import find_inbound


@dataclass(frozen=True, slots=True)
class VpnConnectivityProbe:
    reachable: bool | None
    detail: str | None = None


_CACHE: dict[tuple[uuid.UUID, int], tuple[float, VpnConnectivityProbe]] = {}


def _pick_free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _first_server_name(names: list[Any]) -> str:
    for name in names:
        text = str(name).strip()
        if text:
            return text
    return ""


def _find_curl() -> str | None:
    for candidate in ("/usr/bin/curl", "/bin/curl"):
        if Path(candidate).is_file():
            return candidate
    return shutil.which("curl")


def _wait_for_port(port: int, *, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_tcp_port_open(port):
            return True
        time.sleep(0.2)
    return False


def _curl_via_socks(port: int, url: str, *, timeout: float) -> tuple[bool, str]:
    curl = _find_curl()
    if curl is None:
        return False, "curl not found"

    try:
        result = subprocess.run(
            [
                curl,
                "-fsS",
                "--max-time",
                str(max(1, int(timeout))),
                "-x",
                f"socks5h://127.0.0.1:{port}",
                url,
            ],
            capture_output=True,
            timeout=timeout + 2,
        )
    except subprocess.TimeoutExpired:
        return False, "connectivity probe timed out"
    except OSError as exc:
        return False, str(exc)

    if result.returncode != 0:
        err = result.stderr.decode(errors="replace").strip() or "curl failed"
        return False, err[:240]
    return True, ""


def _terminate_process(proc: subprocess.Popen[Any]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


def _build_xray_client_config(
    snapshot: ConfigVersionSnapshot,
    *,
    host: str,
    socks_port: int,
    settings: PanelSettings,
) -> dict[str, Any]:
    profile_settings = settings.vpn.profiles[snapshot.profile.value]
    inbound = find_inbound(snapshot.config_data, profile_settings.inbound_tag)
    client = inbound["settings"]["clients"][0]
    client_id = str(client["id"])
    stream = inbound["streamSettings"]
    network = stream["network"]
    security = stream.get("security", "none")

    outbound: dict[str, Any] = {
        "tag": "proxy",
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": host,
                    "port": snapshot.port,
                    "users": [
                        {
                            "id": client_id,
                            "encryption": "none",
                        },
                    ],
                },
            ],
        },
        "streamSettings": {
            "network": network,
            "security": security,
        },
    }

    users = outbound["settings"]["vnext"][0]["users"]
    if snapshot.profile is ConfigProfile.XRAY_REALITY:
        reality = stream["realitySettings"]
        users[0]["flow"] = client.get("flow", "xtls-rprx-vision")
        outbound["streamSettings"]["realitySettings"] = {
            "serverName": _first_server_name(reality.get("serverNames", [])),
            "fingerprint": "chrome",
            "publicKey": snapshot.public_key,
            "shortId": str(reality["shortIds"][0]),
        }
    elif snapshot.profile is ConfigProfile.XRAY_GRPC:
        tls = stream["tlsSettings"]
        grpc = stream["grpcSettings"]
        sni = str(tls.get("serverName") or "").strip() or host
        tls_settings: dict[str, Any] = {
            "serverName": sni,
            "fingerprint": "randomized",
        }
        pin = _pin_hex(snapshot.cert_fingerprint)
        if pin:
            tls_settings["pinnedPeerCertChainSha256"] = [pin]
        outbound["streamSettings"]["security"] = "tls"
        outbound["streamSettings"]["tlsSettings"] = tls_settings
        outbound["streamSettings"]["grpcSettings"] = {
            "serviceName": grpc.get("serviceName", ""),
        }
    elif snapshot.profile is ConfigProfile.XRAY_XHTTP:
        xhttp = stream["xhttpSettings"]
        outbound["streamSettings"]["security"] = "none"
        outbound["streamSettings"]["xhttpSettings"] = {
            "host": xhttp.get("host", host),
            "path": xhttp.get("path", "/"),
            "mode": xhttp.get("mode", "packet-up"),
        }
    else:
        raise ValueError(f"Unsupported xray profile: {snapshot.profile}")

    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "socks-in",
                "listen": "127.0.0.1",
                "port": socks_port,
                "protocol": "socks",
                "settings": {"udp": True},
            },
        ],
        "outbounds": [
            outbound,
            {"tag": "direct", "protocol": "freedom"},
        ],
    }


def _build_hysteria_client_config(
    snapshot: ConfigVersionSnapshot,
    *,
    host: str,
    socks_port: int,
) -> dict[str, Any]:
    config_data = snapshot.config_data
    password = str(config_data["auth"]["password"])
    sni = config_data.get("sni") or config_data.get("tls", {}).get("sni") or "vpn-panel"
    tls: dict[str, Any] = {"sni": str(sni), "insecure": False}
    pin = _pin_hex(snapshot.cert_fingerprint)
    if pin:
        tls["pinSHA256"] = pin
    return {
        "server": f"{host}:{snapshot.port}",
        "auth": password,
        "tls": tls,
        "socks5": {"listen": f"127.0.0.1:{socks_port}"},
        "log": {"level": "warn"},
    }


def _probe_via_xray(snapshot: ConfigVersionSnapshot, settings: PanelSettings) -> VpnConnectivityProbe:
    binary = settings.systemd.xray_binary
    if not binary.is_file():
        return VpnConnectivityProbe(reachable=None, detail="xray binary not found")

    host = settings.vpn.public_host.strip()
    if not host:
        return VpnConnectivityProbe(reachable=None, detail="vpn.public_host is empty")

    socks_port = _pick_free_tcp_port()
    client_config = _build_xray_client_config(snapshot, host=host, socks_port=socks_port, settings=settings)
    timeout = settings.vpn.connectivity_probe_timeout_seconds

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(client_config, handle)
        config_path = Path(handle.name)

    proc: subprocess.Popen[Any] | None = None
    try:
        proc = subprocess.Popen(
            [binary.as_posix(), "run", "-config", config_path.as_posix()],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not _wait_for_port(socks_port, timeout=min(5.0, timeout)):
            return VpnConnectivityProbe(reachable=False, detail="local socks proxy did not start")
        ok, detail = _curl_via_socks(socks_port, settings.vpn.connectivity_probe_url, timeout=timeout)
        if ok:
            return VpnConnectivityProbe(reachable=True)
        return VpnConnectivityProbe(reachable=False, detail=detail or "connectivity probe failed")
    except OSError as exc:
        return VpnConnectivityProbe(reachable=False, detail=str(exc))
    finally:
        if proc is not None:
            _terminate_process(proc)
        config_path.unlink(missing_ok=True)


def _probe_via_hysteria(snapshot: ConfigVersionSnapshot, settings: PanelSettings) -> VpnConnectivityProbe:
    binary = settings.systemd.hysteria_binary
    if not binary.is_file():
        return VpnConnectivityProbe(reachable=None, detail="hysteria binary not found")

    host = settings.vpn.public_host.strip()
    if not host:
        return VpnConnectivityProbe(reachable=None, detail="vpn.public_host is empty")

    socks_port = _pick_free_tcp_port()
    client_config = _build_hysteria_client_config(snapshot, host=host, socks_port=socks_port)
    timeout = settings.vpn.connectivity_probe_timeout_seconds

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as handle:
        yaml.safe_dump(client_config, handle, sort_keys=False)
        config_path = Path(handle.name)

    proc: subprocess.Popen[Any] | None = None
    try:
        proc = subprocess.Popen(
            [binary.as_posix(), "client", "-c", config_path.as_posix()],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not _wait_for_port(socks_port, timeout=min(5.0, timeout)):
            return VpnConnectivityProbe(reachable=False, detail="local socks proxy did not start")
        ok, detail = _curl_via_socks(socks_port, settings.vpn.connectivity_probe_url, timeout=timeout)
        if ok:
            return VpnConnectivityProbe(reachable=True)
        return VpnConnectivityProbe(reachable=False, detail=detail or "connectivity probe failed")
    except OSError as exc:
        return VpnConnectivityProbe(reachable=False, detail=str(exc))
    finally:
        if proc is not None:
            _terminate_process(proc)
        config_path.unlink(missing_ok=True)


def probe_config_connectivity(
    snapshot: ConfigVersionSnapshot,
    settings: PanelSettings,
) -> VpnConnectivityProbe:
    if not settings.vpn.connectivity_probe_enabled:
        return VpnConnectivityProbe(reachable=None)

    cache_key = (snapshot.config_id, snapshot.version)
    cache_ttl = settings.vpn.connectivity_probe_cache_seconds
    now = time.monotonic()
    cached = _CACHE.get(cache_key)
    if cached is not None and now - cached[0] < cache_ttl:
        return cached[1]

    if snapshot.profile is ConfigProfile.HYSTERIA2:
        probe = _probe_via_hysteria(snapshot, settings)
    elif snapshot.profile in {
        ConfigProfile.XRAY_REALITY,
        ConfigProfile.XRAY_GRPC,
        ConfigProfile.XRAY_XHTTP,
    }:
        probe = _probe_via_xray(snapshot, settings)
    else:
        probe = VpnConnectivityProbe(reachable=None, detail=f"unsupported profile: {snapshot.profile}")

    _CACHE[cache_key] = (now, probe)
    return probe


def clear_connectivity_cache() -> None:
    _CACHE.clear()
