from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from cryptography.hazmat.primitives.asymmetric import x25519

from panel.config import PanelSettings, VpnProfileSettings
from panel.domain.value_objects.config_profile import ConfigProfile
from panel.infrastructure.filesystem.writer import atomic_write
from panel.infrastructure.vpn.crypto_utils import generate_self_signed_cert, to_base64
from panel.infrastructure.vpn.port_picker import pick_port
from panel.infrastructure.vpn.client_uri import build_share_uris
from panel.infrastructure.vpn.template_loader import find_inbound, load_template, set_client_id
from panel.infrastructure.vpn.systemd_reload import reload_service
from panel.infrastructure.vpn.service_ready import wait_for_service_ready


@dataclass(slots=True)
class BuildResult:
    config_data: dict[str, Any]
    port: int
    private_key: str
    public_key: str
    cert_fingerprint: str = ""
    client_id: str | None = None
    extra_files: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class PreviousSecrets:
    client_id: str | None = None
    private_key: str | None = None
    public_key: str | None = None
    cert_fingerprint: str | None = None
    password: str | None = None


def listening_port(profile: ConfigProfile, config_data: dict[str, Any], profile_settings: VpnProfileSettings) -> int:
    if profile is ConfigProfile.HYSTERIA2:
        return int(str(config_data["listen"]).lstrip(":"))
    inbound = find_inbound(config_data, profile_settings.inbound_tag)
    return int(inbound["port"])


class ProfileConfigBuilder:
    def __init__(self, settings: PanelSettings) -> None:
        self._settings = settings

    def build(
        self,
        profile: ConfigProfile,
        *,
        name: str,
        previous: PreviousSecrets | None = None,
        exclude_ports: set[int] | None = None,
    ) -> BuildResult:
        profile_settings = self._settings.vpn.profiles[profile.value]
        template_path = self._resolve_template_path(profile_settings.template_file)
        config = load_template(template_path)

        if profile is ConfigProfile.XRAY_REALITY:
            return self._build_xray_reality(config, profile_settings, previous=previous, exclude_ports=exclude_ports)
        if profile is ConfigProfile.XRAY_GRPC:
            return self._build_xray_grpc(config, profile_settings, previous=previous, exclude_ports=exclude_ports)
        if profile is ConfigProfile.XRAY_XHTTP:
            return self._build_xray_xhttp(config, profile_settings, previous=previous, exclude_ports=exclude_ports)
        if profile is ConfigProfile.XRAY_CLIENT_IN:
            return self._build_xray_client_in(config, profile_settings, previous=previous, exclude_ports=exclude_ports)
        if profile is ConfigProfile.HYSTERIA2:
            return self._build_hysteria2(config, profile_settings, previous=previous, exclude_ports=exclude_ports)
        raise ValueError(f"Unsupported profile: {profile}")

    def write_files(
        self,
        profile: ConfigProfile,
        config_id: uuid.UUID,
        result: BuildResult,
        *,
        config_name: str = "",
    ) -> None:
        import time

        profile_settings = self._settings.vpn.profiles[profile.value]
        base_path = Path(self._settings.paths.configs) / str(config_id)
        base_path.mkdir(parents=True, exist_ok=True)

        if profile is ConfigProfile.HYSTERIA2:
            body = yaml.safe_dump(result.config_data, sort_keys=False)
        else:
            body = json_dumps(result.config_data)

        config_path = base_path / profile_settings.config_filename
        atomic_write(config_path, body)

        systemd = self._settings.systemd
        if systemd.per_config:
            from panel.infrastructure.vpn.systemd_unit import install_config_unit, live_config_path

            live_path = live_config_path(
                profile,
                config_id,
                profile_settings.config_filename,
                systemd,
            )
            live_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(live_path, body)
            install_config_unit(
                profile,
                config_id,
                config_filename=profile_settings.config_filename,
                config_name=config_name,
                settings=systemd,
            )
        elif profile_settings.active_config_path is not None:
            active_path = Path(profile_settings.active_config_path)
            active_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(active_path, body)
            reload_service(profile_settings.service_name)
            wait_for_service_ready(profile_settings.service_name, profile, systemd)

        cert_dir = profile_settings.cert_dir
        if cert_dir is not None and result.extra_files:
            cert_path = Path(cert_dir)
            cert_path.mkdir(parents=True, exist_ok=True)
            prefix = profile_settings.cert_prefix or "cert"
            timestamp = int(time.time())
            for kind, content in result.extra_files.items():
                versioned = cert_path / f"{prefix}-{kind}-{timestamp}.pem"
                body = content if content.endswith("\n") else content + "\n"
                atomic_write(versioned, body, mode=0o640)
                stable = cert_path / f"{prefix}-{kind}.pem"
                if stable.exists() or stable.is_symlink():
                    stable.unlink()
                stable.symlink_to(versioned.name)

        if not systemd.per_config and profile_settings.active_config_path is None:
            reload_service(profile_settings.service_name)
            wait_for_service_ready(profile_settings.service_name, profile, systemd)

    def sensitive_fields(self, profile: ConfigProfile) -> list[str]:
        if profile is ConfigProfile.HYSTERIA2:
            return ["auth.password"]
        if profile is ConfigProfile.XRAY_REALITY:
            return ["inbounds.0.streamSettings.realitySettings.privateKey"]
        if profile is ConfigProfile.XRAY_GRPC:
            return []
        return []

    def build_client_uris(
        self,
        profile: ConfigProfile,
        config_data: dict[str, Any],
        *,
        public_key: str,
        cert_fingerprint: str = "",
        label: str = "",
        secure: bool = True,
    ) -> list[str]:
        profile_settings = self._settings.vpn.profiles[profile.value]
        return build_share_uris(
            profile,
            config_data,
            host=self._settings.vpn.public_host,
            public_key=public_key,
            cert_fingerprint=cert_fingerprint,
            inbound_tag=profile_settings.inbound_tag,
            secure=secure,
        )

    def _resolve_template_path(self, template_file: str) -> Path:
        path = Path(template_file)
        if path.is_file():
            return path
        templates_root = self._settings.paths.templates
        candidate = templates_root / template_file
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"Template not found: {template_file} (looked in {templates_root})")

    def _build_xray_reality(
        self,
        config: dict[str, Any],
        profile: VpnProfileSettings,
        *,
        previous: PreviousSecrets | None,
        exclude_ports: set[int] | None,
    ) -> BuildResult:
        inbound_tag = profile.inbound_tag
        port = pick_port(profile.port_candidates, exclude=exclude_ports)
        inbound = find_inbound(config, inbound_tag)
        inbound["port"] = port

        if previous and previous.client_id and previous.private_key and previous.public_key:
            client_id = previous.client_id
            private_key = previous.private_key
            public_key = previous.public_key
        else:
            client_id = str(uuid.uuid4())
            private_key_obj = x25519.X25519PrivateKey.generate()
            public_key_obj = private_key_obj.public_key()
            private_key = to_base64(private_key_obj.private_bytes_raw())
            public_key = to_base64(public_key_obj.public_bytes_raw())

        short_ids = [secrets.token_hex(4) for _ in range(3)]
        inbound["streamSettings"]["realitySettings"]["shortIds"] = short_ids
        inbound["streamSettings"]["realitySettings"]["privateKey"] = private_key
        set_client_id(config, client_id, inbound_tag)

        return BuildResult(
            config_data=config,
            port=port,
            private_key=private_key,
            public_key=public_key,
            client_id=client_id,
        )

    def _build_xray_grpc(
        self,
        config: dict[str, Any],
        profile: VpnProfileSettings,
        *,
        previous: PreviousSecrets | None,
        exclude_ports: set[int] | None,
    ) -> BuildResult:
        inbound_tag = profile.inbound_tag
        port = pick_port(profile.port_candidates, exclude=exclude_ports)
        inbound = find_inbound(config, inbound_tag)
        inbound["port"] = port

        if previous and previous.client_id:
            client_id = previous.client_id
        else:
            client_id = str(uuid.uuid4())
        set_client_id(config, client_id, inbound_tag)

        private_pem, cert_pem, fingerprint = generate_self_signed_cert()
        cert_dir = profile.cert_dir or Path("/usr/local/etc/xray/certs")
        prefix = profile.cert_prefix or "grpc"
        cert_file = str(cert_dir / f"{prefix}-cert.pem")
        key_file = str(cert_dir / f"{prefix}-key.pem")
        inbound["streamSettings"]["tlsSettings"]["certificates"] = [
            {"certificateFile": cert_file, "keyFile": key_file},
        ]

        return BuildResult(
            config_data=config,
            port=port,
            private_key=private_pem,
            public_key=cert_pem,
            cert_fingerprint=fingerprint,
            client_id=client_id,
            extra_files={"cert": cert_pem, "key": private_pem},
        )

    def _build_xray_xhttp(
        self,
        config: dict[str, Any],
        profile: VpnProfileSettings,
        *,
        previous: PreviousSecrets | None,
        exclude_ports: set[int] | None,
    ) -> BuildResult:
        import random

        inbound_tag = profile.inbound_tag
        port = pick_port(profile.port_candidates, exclude=exclude_ports)
        inbound = find_inbound(config, inbound_tag)
        inbound["port"] = port

        if previous and previous.client_id:
            client_id = previous.client_id
        else:
            client_id = str(uuid.uuid4())
        set_client_id(config, client_id, inbound_tag)

        xhttp = inbound["streamSettings"]["xhttpSettings"]
        if profile.xhttp_hosts:
            xhttp["host"] = random.choice(profile.xhttp_hosts)
        if profile.xhttp_paths:
            xhttp["path"] = random.choice(profile.xhttp_paths)

        return BuildResult(
            config_data=config,
            port=port,
            private_key="",
            public_key="",
            client_id=client_id,
        )

    def _build_xray_client_in(
        self,
        config: dict[str, Any],
        profile: VpnProfileSettings,
        *,
        previous: PreviousSecrets | None,
        exclude_ports: set[int] | None,
    ) -> BuildResult:
        inbound_tag = profile.inbound_tag
        port = pick_port(profile.port_candidates, exclude=exclude_ports)
        inbound = find_inbound(config, inbound_tag)
        inbound["port"] = port
        return BuildResult(
            config_data=config,
            port=port,
            private_key="",
            public_key="",
        )

    def _build_hysteria2(
        self,
        config: dict[str, Any],
        profile: VpnProfileSettings,
        *,
        previous: PreviousSecrets | None,
        exclude_ports: set[int] | None,
    ) -> BuildResult:
        from panel.infrastructure.vpn.hysteria2 import generate_auth_password

        port = pick_port(profile.port_candidates, exclude=exclude_ports)
        if previous and previous.password:
            password = previous.password
        else:
            password = generate_auth_password()

        private_pem, cert_pem, fingerprint = generate_self_signed_cert()
        cert_dir = profile.cert_dir or Path("/usr/local/etc/xray/certs")
        prefix = profile.cert_prefix or "hysteria"
        config["listen"] = f":{port}"
        config["auth"]["password"] = password
        config["tls"]["cert"] = str(cert_dir / f"{prefix}-cert.pem")
        config["tls"]["key"] = str(cert_dir / f"{prefix}-key.pem")

        return BuildResult(
            config_data=config,
            port=port,
            private_key=private_pem,
            public_key=cert_pem,
            cert_fingerprint=fingerprint,
            extra_files={"cert": cert_pem, "key": private_pem},
        )


def json_dumps(data: dict[str, Any]) -> str:
    import json

    return json.dumps(data, indent=2, ensure_ascii=False)


def previous_for_regenerate(
    profile: ConfigProfile,
    config_data: dict[str, Any],
    *,
    private_key_plain: str,
    public_key: str,
) -> PreviousSecrets | None:
    client_id = None
    for inbound in config_data.get("inbounds", []):
        clients = inbound.get("settings", {}).get("clients", [])
        if clients and clients[0].get("id"):
            client_id = clients[0]["id"]
            break

    if profile is ConfigProfile.XRAY_REALITY:
        return PreviousSecrets(
            client_id=client_id,
            private_key=private_key_plain,
            public_key=public_key,
        )
    if profile in (ConfigProfile.XRAY_GRPC, ConfigProfile.XRAY_XHTTP):
        return PreviousSecrets(client_id=client_id)
    return None
