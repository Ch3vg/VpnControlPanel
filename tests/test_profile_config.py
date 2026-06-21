from __future__ import annotations

import pytest

from panel.domain.value_objects.config_profile import ConfigProfile
from panel.infrastructure.crypto.config_data import encrypt_config_data_fields
from panel.infrastructure.crypto.field_encryptor import FieldEncryptor
from panel.infrastructure.vpn.config_builder import PreviousSecrets, ProfileConfigBuilder


def test_xray_reality_template_build(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    result = builder.build(ConfigProfile.XRAY_REALITY, name="Office")

    inbound = result.config_data["inbounds"][0]
    assert inbound["tag"] == "vless-reality-in"
    assert inbound["port"] == result.port
    assert len(inbound["streamSettings"]["realitySettings"]["shortIds"]) == 3
    assert inbound["streamSettings"]["realitySettings"]["privateKey"]
    assert result.client_id
    assert result.config_data["routing"]["rules"][-1]["inboundTag"] == ["vless-reality-in"]


def test_xray_reality_regenerate_keeps_keys(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    first = builder.build(ConfigProfile.XRAY_REALITY, name="Office")
    second = builder.build(
        ConfigProfile.XRAY_REALITY,
        name="Office",
        previous=PreviousSecrets(
            client_id=first.client_id,
            private_key=first.private_key,
            public_key=first.public_key,
        ),
    )
    assert second.client_id == first.client_id
    assert second.private_key == first.private_key
    assert second.port != first.port or second.config_data["inbounds"][0]["streamSettings"]["realitySettings"]["shortIds"] != (
        first.config_data["inbounds"][0]["streamSettings"]["realitySettings"]["shortIds"]
    )


def test_hysteria2_writes_cert_paths(panel_settings, tmp_path) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    result = builder.build(ConfigProfile.HYSTERIA2, name="Office")
    assert result.config_data["tls"]["cert"].endswith("hysteria-cert.pem")
    assert result.config_data["tls"]["key"].endswith("hysteria-key.pem")
    assert result.extra_files["cert"]
    assert result.extra_files["key"]
