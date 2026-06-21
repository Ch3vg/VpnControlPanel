from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric import x25519

from urllib.parse import quote

from panel.config import VpnServiceSettings
from panel.domain.ports.vpn_protocol import KeyPair, VpnProtocol
from panel.infrastructure.filesystem.writer import atomic_write
from panel.infrastructure.vpn.crypto_utils import to_base64
from panel.infrastructure.vpn.systemd_reload import reload_service


class XrayProtocol(VpnProtocol):
    def __init__(self, service: VpnServiceSettings) -> None:
        self._service = service

    def generate_keys(self) -> KeyPair:
        private_key = x25519.X25519PrivateKey.generate()
        public_key = private_key.public_key()
        return KeyPair(
            private_key=to_base64(private_key.private_bytes_raw()),
            public_key=to_base64(public_key.public_bytes_raw()),
        )

    def build_config(self, params: dict[str, Any]) -> dict[str, Any]:
        port = params["port"]
        keys: KeyPair = params["keys"]
        return {
            "inbounds": [
                {
                    "port": port,
                    "protocol": "vless",
                    "settings": {
                        "clients": [{"id": params["client_id"], "flow": "xtls-rprx-vision"}],
                    },
                    "streamSettings": {
                        "network": "tcp",
                        "security": "reality",
                        "realitySettings": {
                            "privateKey": keys.private_key,
                            "shortIds": [params["short_id"]],
                        },
                    },
                },
            ],
            "outbounds": [{"protocol": "freedom"}],
            "tls": {"private_key": keys.private_key},
        }

    def sensitive_fields(self) -> list[str]:
        return ["tls.private_key", "inbounds.0.streamSettings.realitySettings.privateKey"]

    def write_files(self, config: dict[str, Any], base_path: str) -> None:
        path = Path(base_path) / self._service.config_filename
        atomic_write(path, json.dumps(config, indent=2))

    def build_client_uris(
        self,
        config: dict[str, Any],
        *,
        host: str,
        public_key: str,
        label: str = "",
    ) -> list[str]:
        inbound = config["inbounds"][0]
        client_id = inbound["settings"]["clients"][0]["id"]
        port = inbound["port"]
        short_id = inbound["streamSettings"]["realitySettings"]["shortIds"][0]
        name = quote(label or "vpn")
        uri = (
            f"vless://{client_id}@{host}:{port}"
            f"?encryption=none&security=reality&type=tcp&flow=xtls-rprx-vision"
            f"&pbk={quote(public_key, safe='')}&sid={short_id}#{name}"
        )
        return [uri]

    def reload_service(self) -> None:
        reload_service(self._service.service_name)


def pick_port() -> int:
    return random.randint(10000, 60000)
