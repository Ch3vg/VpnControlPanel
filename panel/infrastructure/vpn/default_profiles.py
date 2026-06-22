from __future__ import annotations

from pathlib import Path


def default_vpn_profiles(*, cert_dir: str = "/usr/local/etc/xray/certs") -> dict:
    return {
        "xray-reality": {
            "template_file": "config_reality.json",
            "service_name": "xray",
            "config_filename": "config.json",
            "inbound_tag": "vless-reality-in",
            "port_candidates": [8443, 2053, 2083, 2096, 9443, 10443, 8444],
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
        },
        "xray-xhttp": {
            "template_file": "config_xhttp.json",
            "service_name": "xray",
            "config_filename": "config.json",
            "inbound_tag": "vless-xhttp-in",
            "port_candidates": [8080, 8000, 8888, 8081, 8090, 3000, 5000, 9000],
            "xhttp_hosts": ["yandex.ru", "gosuslugi.ru", "kremlin.ru", "rzd.ru"],
            "xhttp_paths": ["/search", "/assets", "/api", "/download", "/news", "/login"],
        },
        "hysteria2": {
            "template_file": "hysteria.server.yaml",
            "service_name": "hysteria-server",
            "config_filename": "config.yaml",
            "inbound_tag": "",
            "port_candidates": [8443, 3478, 8800, 1935, 8000, 8080, 53, 123, 5000],
            "cert_dir": cert_dir,
            "cert_prefix": "hysteria",
        },
    }


def templates_path_from_repo() -> Path:
    return Path(__file__).resolve().parents[3] / "configs"
