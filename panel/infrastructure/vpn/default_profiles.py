from __future__ import annotations

from pathlib import Path


def default_vpn_profiles(*, cert_dir: str = "/usr/local/etc/xray/certs") -> dict:
    return {
        "xray-reality": {
            "template_file": "config_reality.json",
            "service_name": "xray",
            "config_filename": "config.json",
            "inbound_tag": "vless-reality-in",
            # Prefer 443 when free (best anti-TSPU). Do not add while host 443 is occupied.
            "port_candidates": [8443, 2053, 2083, 2096, 9443, 10443, 8444],
            "reality_dest_hosts": [
                "ya.ru:443",
                "vk.com:443",
                "gosuslugi.ru:443",
                "pochta.ru:443",
            ],
            # Unused by builder (SNI = dest hostname). Kept for yaml compatibility.
            "reality_server_names": [
                "ya.ru",
                "gosuslugi.ru",
                "vk.com",
                "pochta.ru",
            ],
        },
        "xray-grpc": {
            "template_file": "config_grpc.json",
            "service_name": "xray",
            "config_filename": "config.json",
            "inbound_tag": "vless-grpc-trusted",
            "port_candidates": [8443, 2053, 2083, 2096, 9443, 10443, 4433, 8444],
            "cert_dir": cert_dir,
            "cert_prefix": "grpc",
            "grpc_sni_hosts": [
                "ya.ru",
                "gosuslugi.ru",
                "www.microsoft.com",
                "vk.com",
                "kremlin.ru",
                "pochta.ru",
                "government.ru",
                "rzd.ru",
            ],
            "grpc_service_names": [
                "Drive",
                "Download",
                "Api",
                "TunService",
                "v1.Messenger",
                "grpc.health.v1.Health",
            ],
        },
        "xray-xhttp": {
            "template_file": "config_xhttp.json",
            "service_name": "xray",
            "config_filename": "config.json",
            "inbound_tag": "vless-xhttp-in",
            # Web-like ports; Host/SNI come from vpn.public_host (not xhttp_hosts).
            "port_candidates": [8443, 9443, 10443, 8080, 8444, 2083, 2096, 8888],
            "cert_dir": cert_dir,
            "cert_prefix": "xhttp",
            "xhttp_hosts": [],
            "xhttp_paths": ["/search", "/assets", "/api", "/download", "/news", "/login"],
        },
        "hysteria2": {
            "template_file": "hysteria.server.yaml",
            "service_name": "hysteria-server",
            "config_filename": "config.yaml",
            "inbound_tag": "",
            "port_candidates": [8443, 3478, 8800, 1935, 8080, 5000, 9443, 10443],
            "cert_dir": cert_dir,
            "cert_prefix": "hysteria",
        },
    }


def templates_path_from_repo() -> Path:
    return Path(__file__).resolve().parents[3] / "configs"
