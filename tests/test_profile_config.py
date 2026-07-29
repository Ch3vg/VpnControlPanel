from __future__ import annotations

import uuid
from unittest.mock import patch

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


def test_hysteria2_regenerate_keeps_password_and_cert(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    first = builder.build(ConfigProfile.HYSTERIA2, name="Office")
    second = builder.build(
        ConfigProfile.HYSTERIA2,
        name="Office",
        previous=PreviousSecrets(
            password=first.config_data["auth"]["password"],
            private_key=first.private_key,
            public_key=first.public_key,
            cert_fingerprint=first.cert_fingerprint,
        ),
    )
    assert second.config_data["auth"]["password"] == first.config_data["auth"]["password"]
    assert second.cert_fingerprint == first.cert_fingerprint
    assert second.private_key == first.private_key
    assert second.public_key == first.public_key


def test_write_files_per_config_certs_are_isolated(panel_settings, tmp_path, monkeypatch) -> None:
    settings = panel_settings.model_copy(
        update={
            "paths": panel_settings.paths.model_copy(update={"configs": tmp_path / "archive"}),
            "systemd": panel_settings.systemd.model_copy(
                update={
                    "per_config": True,
                    "hysteria_config_dir": tmp_path / "hysteria",
                    "unit_dir": tmp_path / "units",
                },
            ),
        },
    )
    monkeypatch.setattr("panel.infrastructure.vpn.systemd_unit.run_systemctl", lambda *_a, **_k: None)
    monkeypatch.setattr("panel.infrastructure.vpn.systemd_unit.enable_service", lambda *_a, **_k: None)
    monkeypatch.setattr("panel.infrastructure.vpn.systemd_unit.reload_service", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "panel.infrastructure.vpn.systemd_unit.wait_for_service_ready",
        lambda *_a, **_k: None,
    )

    builder = ProfileConfigBuilder(settings)
    first = builder.build(ConfigProfile.HYSTERIA2, name="A")
    second = builder.build(ConfigProfile.HYSTERIA2, name="B")
    id_a, id_b = uuid.uuid4(), uuid.uuid4()
    builder.write_files(ConfigProfile.HYSTERIA2, id_a, first, config_name="A")
    builder.write_files(ConfigProfile.HYSTERIA2, id_b, second, config_name="B")

    live_a = tmp_path / "hysteria" / str(id_a) / "config.yaml"
    live_b = tmp_path / "hysteria" / str(id_b) / "config.yaml"
    assert live_a.is_file() and live_b.is_file()
    text_a = live_a.read_text(encoding="utf-8")
    text_b = live_b.read_text(encoding="utf-8")
    assert str(tmp_path / "hysteria" / str(id_a) / "hysteria-cert.pem") in text_a
    assert str(tmp_path / "hysteria" / str(id_b) / "hysteria-cert.pem") in text_b
    assert (tmp_path / "hysteria" / str(id_a) / "hysteria-cert.pem").exists()
    assert (tmp_path / "hysteria" / str(id_b) / "hysteria-cert.pem").exists()


def test_hysteria2_excludes_api_port(panel_settings) -> None:
    settings = panel_settings.model_copy(
        update={"server": panel_settings.server.model_copy(update={"port": 3478})},
    )
    builder = ProfileConfigBuilder(settings)
    with patch("panel.infrastructure.vpn.config_builder.pick_port") as mock_pick:
        mock_pick.return_value = 8800
        builder.build(ConfigProfile.HYSTERIA2, name="Office")
    assert settings.server.port in mock_pick.call_args.kwargs["exclude"]


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
