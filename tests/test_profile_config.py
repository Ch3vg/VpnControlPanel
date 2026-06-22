from __future__ import annotations

import uuid

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

    outbound_tags = {o["tag"] for o in result.config_data["outbounds"]}
    assert outbound_tags == {"direct-out", "client-in-loop"}
    assert result.config_data["routing"]["rules"][-1]["outboundTag"] == "client-in-loop"


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


def test_write_files_active_config_path(panel_settings, tmp_path, monkeypatch) -> None:
    active = tmp_path / "live" / "config.json"
    profiles = dict(panel_settings.vpn.profiles)
    profiles["xray-reality"] = profiles["xray-reality"].model_copy(
        update={"active_config_path": active},
    )
    settings = panel_settings.model_copy(
        update={"vpn": panel_settings.vpn.model_copy(update={"profiles": profiles})},
    )
    settings.paths.configs = tmp_path / "archive"
    monkeypatch.setattr("panel.infrastructure.vpn.config_builder.reload_service", lambda _s: None)
    monkeypatch.setattr("panel.infrastructure.vpn.config_builder.wait_for_service_ready", lambda *_a, **_k: None)

    builder = ProfileConfigBuilder(settings)
    result = builder.build(ConfigProfile.XRAY_REALITY, name="Office")
    config_id = uuid.uuid4()
    builder.write_files(ConfigProfile.XRAY_REALITY, config_id, result)

    assert active.is_file()
    archive = settings.paths.configs / str(config_id) / "config.json"
    assert archive.is_file()
    assert active.read_text(encoding="utf-8") == archive.read_text(encoding="utf-8")
    assert str(result.port) in active.read_text(encoding="utf-8")
