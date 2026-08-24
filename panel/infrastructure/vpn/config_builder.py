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
from panel.domain.value_objects.regenerate_policy import RegeneratePolicy
from panel.infrastructure.filesystem.writer import atomic_write
from panel.infrastructure.vpn.crypto_utils import (
    cert_fingerprint_sha256,
    cert_has_dns_san,
    cert_matches_private_key,
    generate_self_signed_cert,
    to_base64,
)
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
    short_ids: list[str] | None = None
    reality_dest: str | None = None
    reality_server_names: list[str] | None = None
    xhttp_path: str | None = None
    grpc_service_name: str | None = None
    grpc_sni: str | None = None


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
        policy: RegeneratePolicy | None = None,
    ) -> BuildResult:
        profile_settings = self._settings.vpn.profiles[profile.value]
        template_path = self._resolve_template_path(profile_settings.template_file)
        config = load_template(template_path)
        resolved = policy or RegeneratePolicy.for_profile(profile, profile_settings)

        if profile is ConfigProfile.XRAY_REALITY:
            result = self._build_xray_reality(
                config,
                profile_settings,
                previous=previous,
                exclude_ports=exclude_ports,
                preferred_port=preferred_port,
                policy=resolved,
            )
        elif profile is ConfigProfile.XRAY_GRPC:
            result = self._build_xray_grpc(
                config,
                profile_settings,
                previous=previous,
                exclude_ports=exclude_ports,
                preferred_port=preferred_port,
                preferred_grpc_sni=preferred_grpc_sni,
                preferred_grpc_service_name=preferred_grpc_service_name,
                policy=resolved,
            )
        elif profile is ConfigProfile.XRAY_XHTTP:
            result = self._build_xray_xhttp(
                config,
                profile_settings,
                previous=previous,
                exclude_ports=exclude_ports,
                preferred_port=preferred_port,
                policy=resolved,
            )
        elif profile is ConfigProfile.HYSTERIA2:
            result = self._build_hysteria2(
                config,
                profile_settings,
                previous=previous,
                exclude_ports=exclude_ports,
                preferred_port=preferred_port,
                policy=resolved,
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

        if profile is ConfigProfile.XRAY_REALITY:
            from panel.infrastructure.vpn.nginx_shared_443 import sync_reality_shared_443

            sync_reality_shared_443(self._settings, result.config_data)
        elif profile in {ConfigProfile.XRAY_XHTTP, ConfigProfile.XRAY_GRPC}:
            from panel.infrastructure.vpn.nginx_shared_443 import sync_reality_shared_443

            # Refresh mux so this profile's share_public_host route stays current.
            reality_live = None
            try:
                from panel.infrastructure.vpn.nginx_shared_443 import _load_live_profile_config

                reality_live = _load_live_profile_config(self._settings, ConfigProfile.XRAY_REALITY.value)
            except Exception:
                reality_live = None
            if reality_live is not None:
                sync_reality_shared_443(self._settings, reality_live)

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
        host = (profile_settings.share_public_host or self._settings.vpn.public_host or "").strip()
        return build_share_uris(
            profile,
            config_data,
            host=host,
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
        policy: RegeneratePolicy,
    ) -> BuildResult:
        inbound_tag = profile.inbound_tag
        port = pick_port(profile.port_candidates, exclude=exclude_ports, preferred=preferred_port)
        inbound = find_inbound(config, inbound_tag)
        inbound["port"] = port
        if profile.listen_address:
            inbound["listen"] = profile.listen_address

        if previous and previous.client_id and not policy.rotate_client_id:
            client_id = previous.client_id
        else:
            client_id = str(uuid.uuid4())

        if previous and previous.private_key and previous.public_key and not policy.rotate_reality_keys:
            private_key = previous.private_key
            public_key = previous.public_key
        else:
            private_key_obj = x25519.X25519PrivateKey.generate()
            public_key_obj = private_key_obj.public_key()
            private_key = to_base64(private_key_obj.private_bytes_raw())
            public_key = to_base64(public_key_obj.public_bytes_raw())

        reality = inbound["streamSettings"]["realitySettings"]
        if previous and previous.short_ids and not policy.rotate_short_ids:
            short_ids = list(previous.short_ids)
        else:
            short_ids = [secrets.token_hex(4) for _ in range(3)]
        reality["shortIds"] = short_ids
        reality["privateKey"] = private_key

        if previous and previous.reality_dest and not policy.rotate_dest:
            reality["dest"] = previous.reality_dest
            if previous.reality_server_names:
                reality["serverNames"] = list(previous.reality_server_names)
            else:
                dest_host = dest_hostname(str(reality.get("dest") or ""))
                if dest_host:
                    reality["serverNames"] = [dest_host]
        else:
            if profile.reality_dest_hosts:
                reality["dest"] = random.choice(profile.reality_dest_hosts)
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
        policy: RegeneratePolicy,
    ) -> BuildResult:
        inbound_tag = profile.inbound_tag
        port = pick_port(profile.port_candidates, exclude=exclude_ports, preferred=preferred_port)
        inbound = find_inbound(config, inbound_tag)
        inbound["port"] = port
        if profile.listen_address:
            inbound["listen"] = profile.listen_address

        if previous and previous.client_id and not policy.rotate_client_id:
            client_id = previous.client_id
        else:
            client_id = str(uuid.uuid4())
        set_client_id(config, client_id, inbound_tag)

        tls = inbound["streamSettings"]["tlsSettings"]
        tls["alpn"] = ["h2"]
        tls.pop("fingerprint", None)
        tls_name = self._tls_server_name(profile)
        if (profile.share_public_host or "").strip():
            tls["serverName"] = tls_name
        elif profile.grpc_sni_hosts:
            keep_sni = preferred_grpc_sni or (previous.grpc_sni if previous else None)
            if keep_sni and keep_sni in profile.grpc_sni_hosts:
                tls["serverName"] = keep_sni
            else:
                tls["serverName"] = random.choice(profile.grpc_sni_hosts)

        grpc = inbound["streamSettings"]["grpcSettings"]
        if profile.grpc_service_names:
            keep_svc = preferred_grpc_service_name or (previous.grpc_service_name if previous else None)
            if not policy.rotate_service_name and keep_svc and keep_svc in profile.grpc_service_names:
                grpc["serviceName"] = keep_svc
            else:
                grpc["serviceName"] = random.choice(profile.grpc_service_names)

        private_pem, cert_pem, fingerprint, extra = self._resolve_tls(
            profile, previous, dns_names=[tls_name], rotate_tls=policy.rotate_tls, prefix="grpc",
        )
        cert_file, key_file, extra_files = extra
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
            extra_files=extra_files,
        )

    def _build_xray_xhttp(
        self,
        config: dict[str, Any],
        profile: VpnProfileSettings,
        *,
        previous: PreviousSecrets | None,
        exclude_ports: set[int] | None,
        preferred_port: int | None,
        policy: RegeneratePolicy,
    ) -> BuildResult:
        inbound_tag = profile.inbound_tag
        port = pick_port(profile.port_candidates, exclude=exclude_ports, preferred=preferred_port)
        inbound = find_inbound(config, inbound_tag)
        inbound["port"] = port
        if profile.listen_address:
            inbound["listen"] = profile.listen_address

        if previous and previous.client_id and not policy.rotate_client_id:
            client_id = previous.client_id
        else:
            client_id = str(uuid.uuid4())
        set_client_id(config, client_id, inbound_tag)

        stream = inbound["streamSettings"]
        stream["security"] = "tls"
        xhttp = stream["xhttpSettings"]
        tls_name = self._tls_server_name(profile)
        xhttp["host"] = tls_name
        xhttp["mode"] = "stream-up"
        if previous and previous.xhttp_path and not policy.rotate_path:
            xhttp["path"] = previous.xhttp_path
        elif profile.xhttp_paths:
            xhttp["path"] = random.choice(profile.xhttp_paths)

        private_pem, cert_pem, fingerprint, extra = self._resolve_tls(
            profile, previous, dns_names=[tls_name], rotate_tls=policy.rotate_tls, prefix="xhttp",
        )
        cert_file, key_file, extra_files = extra
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
            extra_files=extra_files,
        )

    def _build_hysteria2(
        self,
        config: dict[str, Any],
        profile: VpnProfileSettings,
        *,
        previous: PreviousSecrets | None,
        exclude_ports: set[int] | None,
        preferred_port: int | None,
        policy: RegeneratePolicy,
    ) -> BuildResult:
        from panel.infrastructure.vpn.hysteria2 import generate_auth_password

        blocked = set(exclude_ports or ())
        blocked.add(self._settings.server.port)
        preferred = preferred_port
        if (
            preferred is None
            and profile.share_public_port is not None
            and profile.share_public_port in profile.port_candidates
        ):
            preferred = profile.share_public_port
        port = pick_port(profile.port_candidates, exclude=blocked, udp=True, preferred=preferred)

        if previous and previous.password and not policy.rotate_auth:
            password = previous.password
        else:
            password = generate_auth_password()

        if previous and previous.obfs_password and not policy.rotate_obfs:
            obfs_password = previous.obfs_password
        else:
            obfs_password = generate_auth_password()

        tls_name = self._tls_server_name(profile)
        private_pem, cert_pem, fingerprint, extra = self._resolve_tls(
            profile, previous, dns_names=[tls_name], rotate_tls=policy.rotate_tls, prefix="hysteria",
        )
        cert_file, key_file, extra_files = extra
        config["listen"] = f":{port}"
        config["auth"]["password"] = password
        config["tls"]["cert"] = cert_file
        config["tls"]["key"] = key_file
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
            extra_files=extra_files,
        )

    def _tls_server_name(self, profile: VpnProfileSettings | None = None) -> str:
        """SNI / cert SAN for self-signed profiles.

        Prefer profile.share_public_host (e.g. Hysteria on hy.example.com), else vpn.public_host.
        """
        if profile is not None:
            override = (profile.share_public_host or "").strip()
            if override:
                return override
        return (self._settings.vpn.public_host or "").strip() or "localhost"

    def _resolve_tls(
        self,
        profile: VpnProfileSettings,
        previous: PreviousSecrets | None,
        *,
        dns_names: list[str],
        rotate_tls: bool,
        prefix: str,
    ) -> tuple[str, str, str, tuple[str, str, dict[str, str]]]:
        """Return private_pem, cert_pem, fingerprint, (cert_path, key_path, extra_files)."""
        external = _load_external_tls(profile)
        if external is not None:
            private_pem, cert_pem, fingerprint, cert_path, key_path = external
            return private_pem, cert_pem, fingerprint, (cert_path, key_path, {})

        cert_dir = profile.cert_dir or Path("/usr/local/etc/xray/certs")
        file_prefix = profile.cert_prefix or prefix
        cert_file = str(cert_dir / f"{file_prefix}-cert.pem")
        key_file = str(cert_dir / f"{file_prefix}-key.pem")

        if not rotate_tls:
            reused = _try_reuse_tls(previous, dns_names=dns_names)
            if reused is not None:
                private_pem, cert_pem, fingerprint = reused
                return private_pem, cert_pem, fingerprint, (
                    cert_file,
                    key_file,
                    {"cert": cert_pem, "key": private_pem},
                )

        private_pem, cert_pem, fingerprint = generate_self_signed_cert(dns_names=dns_names)
        return private_pem, cert_pem, fingerprint, (
            cert_file,
            key_file,
            {"cert": cert_pem, "key": private_pem},
        )


def _load_external_tls(
    profile: VpnProfileSettings,
) -> tuple[str, str, str, str, str] | None:
    """Load LE/external PEM pair. Returns private, cert, fingerprint, cert_path, key_path."""
    if not profile.tls_cert_file or not profile.tls_key_file:
        return None
    cert_path = Path(profile.tls_cert_file)
    key_path = Path(profile.tls_key_file)
    if not cert_path.is_file() or not key_path.is_file():
        return None
    cert_pem = cert_path.read_text(encoding="utf-8")
    private_pem = key_path.read_text(encoding="utf-8")
    if not cert_matches_private_key(cert_pem, private_pem):
        return None
    fingerprint = cert_fingerprint_sha256(cert_pem)
    return private_pem, cert_pem, fingerprint, str(cert_path), str(key_path)


def _try_reuse_tls(
    previous: PreviousSecrets | None,
    *,
    dns_names: list[str],
) -> tuple[str, str, str] | None:
    primary = dns_names[0]
    if (
        previous
        and previous.private_key
        and previous.public_key
        and previous.cert_fingerprint
        and cert_has_dns_san(previous.public_key, required_name=primary)
        and cert_matches_private_key(previous.public_key, previous.private_key)
    ):
        return previous.private_key, previous.public_key, previous.cert_fingerprint
    return None


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
    short_ids = None
    reality_dest = None
    reality_server_names = None
    xhttp_path = None
    grpc_service_name = None
    grpc_sni = None

    for inbound in config_data.get("inbounds", []):
        clients = inbound.get("settings", {}).get("clients", [])
        if clients and clients[0].get("id") and client_id is None:
            client_id = clients[0]["id"]
        stream = inbound.get("streamSettings") or {}
        reality = stream.get("realitySettings") or {}
        if reality.get("shortIds"):
            short_ids = list(reality["shortIds"])
        if reality.get("dest"):
            reality_dest = str(reality["dest"])
        if reality.get("serverNames"):
            reality_server_names = list(reality["serverNames"])
        xhttp = stream.get("xhttpSettings") or {}
        if xhttp.get("path"):
            xhttp_path = str(xhttp["path"])
        grpc = stream.get("grpcSettings") or {}
        if grpc.get("serviceName"):
            grpc_service_name = str(grpc["serviceName"])
        tls = stream.get("tlsSettings") or {}
        if tls.get("serverName"):
            grpc_sni = str(tls["serverName"])

    if profile is ConfigProfile.XRAY_REALITY:
        return PreviousSecrets(
            client_id=client_id,
            private_key=private_key_plain,
            public_key=public_key,
            short_ids=short_ids,
            reality_dest=reality_dest,
            reality_server_names=reality_server_names,
        )
    if profile is ConfigProfile.XRAY_GRPC:
        return PreviousSecrets(
            client_id=client_id,
            private_key=private_key_plain or None,
            public_key=public_key or None,
            cert_fingerprint=cert_fingerprint or None,
            grpc_service_name=grpc_service_name,
            grpc_sni=grpc_sni,
        )
    if profile is ConfigProfile.XRAY_XHTTP:
        return PreviousSecrets(
            client_id=client_id,
            private_key=private_key_plain or None,
            public_key=public_key or None,
            cert_fingerprint=cert_fingerprint or None,
            xhttp_path=xhttp_path,
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
