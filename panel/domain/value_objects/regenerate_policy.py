from __future__ import annotations

from typing import Any, TYPE_CHECKING

from pydantic import BaseModel

from panel.domain.value_objects.config_profile import ConfigProfile

if TYPE_CHECKING:
    from panel.config import VpnProfileSettings


class RegeneratePolicy(BaseModel):
    """Per-config flags controlling what regenerate may change."""

    rotate_port: bool = True
    rotate_client_id: bool = True
    rotate_reality_keys: bool = True
    rotate_short_ids: bool = True
    rotate_dest: bool = True
    rotate_path: bool = True
    rotate_service_name: bool = False
    rotate_tls: bool = True
    rotate_auth: bool = False
    rotate_obfs: bool = False

    @classmethod
    def for_profile(
        cls,
        profile: ConfigProfile,
        profile_settings: VpnProfileSettings | None = None,
    ) -> RegeneratePolicy:
        rotate_port = True
        rotate_tls = True
        if profile_settings is not None:
            share_port = profile_settings.share_public_port
            if (
                profile is ConfigProfile.HYSTERIA2
                and share_port is not None
                and share_port in profile_settings.port_candidates
            ):
                rotate_port = False
            if profile_settings.tls_cert_file and profile_settings.tls_key_file:
                rotate_tls = False

        if profile is ConfigProfile.XRAY_REALITY:
            return cls(
                rotate_port=rotate_port,
                rotate_client_id=True,
                rotate_reality_keys=True,
                rotate_short_ids=True,
                rotate_dest=True,
                rotate_path=True,
                rotate_service_name=False,
                rotate_tls=True,
                rotate_auth=False,
                rotate_obfs=False,
            )
        if profile is ConfigProfile.XRAY_XHTTP:
            return cls(
                rotate_port=rotate_port,
                rotate_client_id=True,
                rotate_reality_keys=False,
                rotate_short_ids=False,
                rotate_dest=False,
                rotate_path=True,
                rotate_service_name=False,
                rotate_tls=rotate_tls,
                rotate_auth=False,
                rotate_obfs=False,
            )
        if profile is ConfigProfile.XRAY_GRPC:
            return cls(
                rotate_port=rotate_port,
                rotate_client_id=True,
                rotate_reality_keys=False,
                rotate_short_ids=False,
                rotate_dest=False,
                rotate_path=False,
                rotate_service_name=False,
                rotate_tls=rotate_tls,
                rotate_auth=False,
                rotate_obfs=False,
            )
        if profile is ConfigProfile.HYSTERIA2:
            return cls(
                rotate_port=rotate_port,
                rotate_client_id=False,
                rotate_reality_keys=False,
                rotate_short_ids=False,
                rotate_dest=False,
                rotate_path=False,
                rotate_service_name=False,
                rotate_tls=rotate_tls,
                rotate_auth=False,
                rotate_obfs=False,
            )
        return cls()

    @classmethod
    def from_stored(
        cls,
        raw: dict[str, Any] | None,
        *,
        profile: ConfigProfile,
        profile_settings: VpnProfileSettings | None = None,
    ) -> RegeneratePolicy:
        if raw is None:
            return cls.for_profile(profile, profile_settings)
        return cls.model_validate(raw)

    def to_stored(self) -> dict[str, Any]:
        return self.model_dump()


# Fields shown in create UI per profile (others still stored with defaults).
POLICY_UI_FIELDS: dict[ConfigProfile, tuple[str, ...]] = {
    ConfigProfile.XRAY_REALITY: (
        "rotate_port",
        "rotate_client_id",
        "rotate_reality_keys",
        "rotate_short_ids",
        "rotate_dest",
    ),
    ConfigProfile.XRAY_XHTTP: (
        "rotate_port",
        "rotate_client_id",
        "rotate_path",
        "rotate_tls",
    ),
    ConfigProfile.XRAY_GRPC: (
        "rotate_port",
        "rotate_client_id",
        "rotate_service_name",
        "rotate_tls",
    ),
    ConfigProfile.HYSTERIA2: (
        "rotate_port",
        "rotate_tls",
        "rotate_auth",
        "rotate_obfs",
    ),
}

POLICY_FIELD_LABELS: dict[str, str] = {
    "rotate_port": "Порт",
    "rotate_client_id": "UUID клиента",
    "rotate_reality_keys": "Reality privateKey / pbk",
    "rotate_short_ids": "shortIds",
    "rotate_dest": "dest / serverNames",
    "rotate_path": "xHTTP path",
    "rotate_service_name": "gRPC serviceName",
    "rotate_tls": "Self-signed TLS (вместо LE профиля)",
    "rotate_auth": "Hysteria auth",
    "rotate_obfs": "Hysteria obfs",
}
