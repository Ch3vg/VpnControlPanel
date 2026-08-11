from __future__ import annotations

import random
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
from panel.infrastructure.vpn.crypto_utils import cert_has_dns_san, generate_self_signed_cert, to_base64
from panel.infrastructure.vpn.port_picker import pick_port
from panel.infrastructure.vpn.client_uri import build_share_uris, dest_hostname
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
    obfs_password: str | None = None


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
        preferred_port: int | None = None,
        preferred_grpc_sni: str | None = None,
        preferred_grpc_service_name: str | None = None,
    ) -> BuildResult:
        profile_settings = self._settings.vpn.profiles[profile.value]
        template_path = self._resolve_template_path(profile_settings.template_file)
        config = load_template(template_path)

        if profile is ConfigProfile.XRAY_REALITY:
            result = self._build_xray_reality(
                config, profile_settings, previous=previous, exclude_ports=exclude_ports, preferred_port=preferred_port,
            )
        elif profile is ConfigProfile.XRAY_GRPC:
            result = self._build_xray_grpc(
                config, profile_settings, previous=previous, exclude_ports=exclude_ports,
                preferred_port=preferred_port, preferred_grpc_sni=preferred_grpc_sni,
                preferred_grpc_service_name=preferred_grpc_service_name,
            )
        elif profile is ConfigProfile.XRAY_XHTTP:
            result = self._build_xray_xhttp(
                config, profile_settings, previous=previous, exclude_ports=exclude_ports, preferred_port=preferred_port,
            )
        elif profile is ConfigProfile.HYSTERIA2:
            result = self._build_hysteria2(
                config, profile_settings, previous=previous, exclude_ports=exclude_ports, preferred_port=preferred_port,
            )
        else:
            raise ValueError(f"Unsupported profile: {profile}")

        return result

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

        systemd = self._settings.systemd
        live_path: Path | None = None
        if systemd.per_config:
            from panel.infrastructure.vpn.systemd_unit import install_config_unit, live_config_path

            live_path = live_config_path(
                profile,
                config_id,
                profile_settings.config_filename,
                systemd,
            )
            live_path.parent.mkdir(parents=True, exist_ok=True)

        if result.extra_files:
            cert_dir = profile_settings.cert_dir
            # Per-config units: keep certs next to the live config so regenerate
            # of one profile cannot overwrite shared grpc/hysteria cert files.
            if live_path is not None:
                cert_base = live_path.parent
            elif cert_dir is not None:
                cert_base = Path(cert_dir)
                cert_base.mkdir(parents=True, exist_ok=True)
            else:
                cert_base = base_path
            cert_base.mkdir(parents=True, exist_ok=True)
            prefix = profile_settings.cert_prefix or "cert"
            cert_file = cert_base / f"{prefix}-cert.pem"
            key_file = cert_base / f"{prefix}-key.pem"
            _apply_tls_cert_paths(profile, result.config_data, cert_file=cert_file, key_file=key_file)

            timestamp = int(time.time())
            for kind, content in result.extra_files.items():
                versioned = cert_base / f"{prefix}-{kind}-{timestamp}.pem"
                body = content if content.endswith("\n") else content + "\n"
                atomic_write(versioned, body, mode=0o640)
                stable = cert_base / f"{prefix}-{kind}.pem"
                if stable.exists() or stable.is_symlink():
                    stable.unlink()
                stable.symlink_to(versioned.name)

        if profile is ConfigProfile.HYSTERIA2:
            body = yaml.safe_dump(result.config_data, sort_keys=False)
        else:
            body = json_dumps(result.config_data)

        config_path = base_path / profile_settings.config_filename
        atomic_write(config_path, body)

        if systemd.per_config:
            from panel.infrastructure.vpn.systemd_unit import install_config_unit

            assert live_path is not None
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
        else:
            reload_service(profile_settings.service_name)
            wait_for_service_ready(profile_settings.service_name, profile, systemd)

    def sensitive_fields(self, profile: ConfigProfile) -> list[str]:
        if profile is ConfigProfile.HYSTERIA2:
            return ["auth.password", "obfs.salamander.password"]
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
            public_port=profile_settings.share_public_port,
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
        preferred_port: int | None,
    ) -> BuildResult:
        inbound_tag = profile.inbound_tag
        port = pick_port(profile.port_candidates, exclude=exclude_ports, preferred=preferred_port)
        inbound = find_inbound(config, inbound_tag)
        inbound["port"] = port
        if profile.listen_address:
            inbound["listen"] = profile.listen_address

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
        reality = inbound["streamSettings"]["realitySettings"]
        reality["shortIds"] = short_ids
        reality["privateKey"] = private_key
        if profile.reality_dest_hosts:
            reality["dest"] = random.choice(profile.reality_dest_hosts)
        # SNI must equal dest hostname (TSPU flags mismatched SNI/dest pools).
        dest_host = dest_hostname(str(reality.get("dest") or ""))
        if dest_host:
            reality["serverNames"] = [dest_host]
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
        preferred_port: int | None,
        preferred_grpc_sni: str | None = None,
        preferred_grpc_service_name: str | None = None,
    ) -> BuildResult:
        inbound_tag = profile.inbound_tag
        port = pick_port(profile.port_candidates, exclude=exclude_ports, preferred=preferred_port)
        inbound = find_inbound(config, inbound_tag)
        inbound["port"] = port

        if previous and previous.client_id:
            client_id = previous.client_id
        else:
            client_id = str(uuid.uuid4())
        set_client_id(config, client_id, inbound_tag)

        tls = inbound["streamSettings"]["tlsSettings"]
        tls["alpn"] = ["h2"]
        tls.pop("fingerprint", None)
        if profile.grpc_sni_hosts:
            if preferred_grpc_sni and preferred_grpc_sni in profile.grpc_sni_hosts:
                tls["serverName"] = preferred_grpc_sni
            else:
                tls["serverName"] = random.choice(profile.grpc_sni_hosts)

        grpc = inbound["streamSettings"]["grpcSettings"]
        if profile.grpc_service_names:
            if preferred_grpc_service_name and preferred_grpc_service_name in profile.grpc_service_names:
                grpc["serviceName"] = preferred_grpc_service_name
            else:
                grpc["serviceName"] = random.choice(profile.grpc_service_names)

        private_pem, cert_pem, fingerprint = _tls_material(previous, dns_names=[self._tls_server_name()])
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
        preferred_port: int | None,
    ) -> BuildResult:
        inbound_tag = profile.inbound_tag
        port = pick_port(profile.port_candidates, exclude=exclude_ports, preferred=preferred_port)
        inbound = find_inbound(config, inbound_tag)
        inbound["port"] = port

        if previous and previous.client_id:
            client_id = previous.client_id
        else:
            client_id = str(uuid.uuid4())
        set_client_id(config, client_id, inbound_tag)

        stream = inbound["streamSettings"]
        stream["security"] = "tls"
        xhttp = stream["xhttpSettings"]
        tls_name = self._tls_server_name()
        # Host must match TLS SNI (foreign Host + self-signed SNI is a DPI marker).
        xhttp["host"] = tls_name
        xhttp["mode"] = "stream-up"
        if profile.xhttp_paths:
            xhttp["path"] = random.choice(profile.xhttp_paths)

        private_pem, cert_pem, fingerprint = _tls_material(previous, dns_names=[tls_name])
        cert_dir = profile.cert_dir or Path("/usr/local/etc/xray/certs")
        prefix = profile.cert_prefix or "xhttp"
        cert_file = str(cert_dir / f"{prefix}-cert.pem")
        key_file = str(cert_dir / f"{prefix}-key.pem")
        stream["tlsSettings"] = {
            "serverName": tls_name,
            "alpn": ["h2", "http/1.1"],
            "certificates": [
                {"certificateFile": cert_file, "keyFile": key_file},
            ],
        }

        return BuildResult(
            config_data=config,
            port=port,
            private_key=private_pem,
            public_key=cert_pem,
            cert_fingerprint=fingerprint,
            client_id=client_id,
            extra_files={"cert": cert_pem, "key": private_pem},
        )

    def _build_hysteria2(
        self,
        config: dict[str, Any],
        profile: VpnProfileSettings,
        *,
        previous: PreviousSecrets | None,
        exclude_ports: set[int] | None,
        preferred_port: int | None,
    ) -> BuildResult:
        from panel.infrastructure.vpn.hysteria2 import generate_auth_password

        blocked = set(exclude_ports or ())
        blocked.add(self._settings.server.port)
        port = pick_port(profile.port_candidates, exclude=blocked, udp=True, preferred=preferred_port)
        if previous and previous.password:
            password = previous.password
        else:
            password = generate_auth_password()

        if previous and previous.obfs_password:
            obfs_password = previous.obfs_password
        else:
            obfs_password = generate_auth_password()

        tls_name = self._tls_server_name()
        private_pem, cert_pem, fingerprint = _tls_material(previous, dns_names=[tls_name])
        cert_dir = profile.cert_dir or Path("/usr/local/etc/xray/certs")
        prefix = profile.cert_prefix or "hysteria"
        config["listen"] = f":{port}"
        config["auth"]["password"] = password
        config["tls"]["cert"] = str(cert_dir / f"{prefix}-cert.pem")
        config["tls"]["key"] = str(cert_dir / f"{prefix}-key.pem")
        config["tls"]["sni"] = tls_name
        config["obfs"] = {
            "type": "salamander",
            "salamander": {"password": obfs_password},
        }

        return BuildResult(
            config_data=config,
            port=port,
            private_key=private_pem,
            public_key=cert_pem,
            cert_fingerprint=fingerprint,
            extra_files={"cert": cert_pem, "key": private_pem},
        )

    def _tls_server_name(self) -> str:
        """SNI / cert SAN for self-signed profiles — always vpn.public_host, never a fake label."""
        return (self._settings.vpn.public_host or "").strip() or "localhost"


def _tls_material(
    previous: PreviousSecrets | None,
    *,
    dns_names: list[str],
) -> tuple[str, str, str]:
    primary = dns_names[0]
    if (
        previous
        and previous.private_key
        and previous.public_key
        and previous.cert_fingerprint
        and cert_has_dns_san(previous.public_key, required_name=primary)
    ):
        return previous.private_key, previous.public_key, previous.cert_fingerprint
    return generate_self_signed_cert(dns_names=dns_names)


def _apply_tls_cert_paths(
    profile: ConfigProfile,
    config_data: dict[str, Any],
    *,
    cert_file: Path,
    key_file: Path,
) -> None:
    if profile is ConfigProfile.HYSTERIA2:
        tls = config_data.setdefault("tls", {})
        tls["cert"] = str(cert_file)
        tls["key"] = str(key_file)
        return
    if profile in {ConfigProfile.XRAY_GRPC, ConfigProfile.XRAY_XHTTP}:
        for inbound in config_data.get("inbounds", []):
            certificates = (
                inbound.get("streamSettings", {})
                .get("tlsSettings", {})
                .get("certificates")
            )
            if not certificates:
                continue
            certificates[0]["certificateFile"] = str(cert_file)
            certificates[0]["keyFile"] = str(key_file)
            return


def json_dumps(data: dict[str, Any]) -> str:
    import json

    return json.dumps(data, indent=2, ensure_ascii=False)


def previous_for_regenerate(
    profile: ConfigProfile,
    config_data: dict[str, Any],
    *,
    private_key_plain: str,
    public_key: str,
    cert_fingerprint: str = "",
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
    if profile is ConfigProfile.XRAY_GRPC:
        return PreviousSecrets(
            client_id=client_id,
            private_key=private_key_plain or None,
            public_key=public_key or None,
            cert_fingerprint=cert_fingerprint or None,
        )
    if profile is ConfigProfile.XRAY_XHTTP:
        return PreviousSecrets(
            client_id=client_id,
            private_key=private_key_plain or None,
            public_key=public_key or None,
            cert_fingerprint=cert_fingerprint or None,
        )
    if profile is ConfigProfile.HYSTERIA2:
        password = (config_data.get("auth") or {}).get("password")
        obfs_password = (
            ((config_data.get("obfs") or {}).get("salamander") or {}).get("password")
        )
        return PreviousSecrets(
            password=str(password) if password else None,
            obfs_password=str(obfs_password) if obfs_password else None,
            private_key=private_key_plain or None,
            public_key=public_key or None,
            cert_fingerprint=cert_fingerprint or None,
        )
    return None
