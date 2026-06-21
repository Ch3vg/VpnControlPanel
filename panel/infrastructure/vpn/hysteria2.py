from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from urllib.parse import quote

from panel.config import VpnServiceSettings
from panel.domain.ports.vpn_protocol import KeyPair, VpnProtocol
from panel.infrastructure.filesystem.writer import atomic_write
from panel.infrastructure.vpn.crypto_utils import generate_self_signed_cert, generate_token
from panel.infrastructure.vpn.systemd_reload import reload_service


class Hysteria2Protocol(VpnProtocol):
    def __init__(self, service: VpnServiceSettings) -> None:
        self._service = service

    def generate_keys(self) -> KeyPair:
        private_pem, cert_pem, fingerprint = generate_self_signed_cert()
        return KeyPair(
            private_key=private_pem,
            public_key=cert_pem,
            cert_fingerprint=fingerprint,
        )

    def build_config(self, params: dict[str, Any]) -> dict[str, Any]:
        keys: KeyPair = params["keys"]
        password = params["password"]
        return {
            "listen": f":{params['port']}",
            "auth": {"type": "password", "password": password},
            "tls": {
                "cert": keys.public_key,
                "key": keys.private_key,
            },
        }

    def sensitive_fields(self) -> list[str]:
        return ["auth.password", "tls.key"]

    def write_files(self, config: dict[str, Any], base_path: str) -> None:
        path = Path(base_path) / self._service.config_filename
        atomic_write(path, yaml.safe_dump(config, sort_keys=False))

    def build_client_uris(
        self,
        config: dict[str, Any],
        *,
        host: str,
        public_key: str,
        label: str = "",
    ) -> list[str]:
        listen = config["listen"]
        port = int(str(listen).lstrip(":"))
        password = config["auth"]["password"]
        name = quote(label or "vpn")
        uri = f"hysteria2://{quote(password, safe='')}@{host}:{port}?insecure=1#{name}"
        return [uri]

    def reload_service(self) -> None:
        reload_service(self._service.service_name)


def generate_auth_password() -> str:
    return generate_token(24)
