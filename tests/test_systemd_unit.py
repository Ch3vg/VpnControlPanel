from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from panel.domain.value_objects.config_profile import ConfigProfile
from panel.infrastructure.vpn.config_builder import ProfileConfigBuilder
from panel.infrastructure.vpn.systemd_unit import (
    config_service_name,
    install_config_unit,
    live_config_path,
    render_unit,
    unit_file_path,
)


def test_config_service_name() -> None:
    config_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
    assert config_service_name(config_id) == "vpn-550e8400-e29b-41d4-a716-446655440000"


def test_render_xray_unit(panel_settings) -> None:
    config_id = uuid.uuid4()
    settings = panel_settings.systemd.model_copy(update={"per_config": True})
    config_path = live_config_path(
        ConfigProfile.XRAY_REALITY,
        config_id,
        "config.json",
        settings,
    )
    unit = render_unit(
        ConfigProfile.XRAY_REALITY,
        service_name=config_service_name(config_id),
        config_path=config_path,
        config_name="Office",
        settings=settings,
    )
    assert "ExecStart=/usr/local/bin/xray run -config" in unit
    assert config_path.as_posix() in unit
    assert "Description=VPN Office" in unit


def test_render_hysteria_unit(panel_settings) -> None:
    config_id = uuid.uuid4()
    settings = panel_settings.systemd.model_copy(update={"per_config": True})
    config_path = live_config_path(
        ConfigProfile.HYSTERIA2,
        config_id,
        "config.yaml",
        settings,
    )
    unit = render_unit(
        ConfigProfile.HYSTERIA2,
        service_name=config_service_name(config_id),
        config_path=config_path,
        config_name="Office",
        settings=settings,
    )
    assert "ExecStart=/usr/local/bin/hysteria server -c" in unit
    assert config_path.as_posix() in unit


def test_write_files_per_config_unit(panel_settings, tmp_path, monkeypatch) -> None:
    settings = panel_settings.model_copy(
        update={
            "paths": panel_settings.paths.model_copy(update={"configs": tmp_path / "archive"}),
            "systemd": panel_settings.systemd.model_copy(
                update={
                    "per_config": True,
                    "unit_dir": tmp_path / "units",
                    "xray_config_dir": tmp_path / "live" / "xray",
                },
            ),
        },
    )
    calls: list[tuple[str, str | None]] = []

    def fake_run_systemctl(action: str, service_name: str | None = None) -> None:
        calls.append((action, service_name))

    monkeypatch.setattr("panel.infrastructure.vpn.systemd_unit.run_systemctl", fake_run_systemctl)
    monkeypatch.setattr("panel.infrastructure.vpn.systemd_unit.reload_service", lambda s: calls.append(("restart", s)))
    monkeypatch.setattr("panel.infrastructure.vpn.systemd_unit.enable_service", lambda s: calls.append(("enable", s)))

    builder = ProfileConfigBuilder(settings)
    result = builder.build(ConfigProfile.XRAY_REALITY, name="Office")
    config_id = uuid.uuid4()
    builder.write_files(ConfigProfile.XRAY_REALITY, config_id, result, config_name="Office")

    service_name = config_service_name(config_id)
    live_path = live_config_path(ConfigProfile.XRAY_REALITY, config_id, "config.json", settings.systemd)
    unit_path = unit_file_path(service_name, settings.systemd)

    assert live_path.is_file()
    assert unit_path.is_file()
    assert ("daemon-reload", None) in calls
    assert ("enable", service_name) in calls
    assert ("restart", service_name) in calls


def test_install_config_unit_skips_enable_on_regenerate(panel_settings, tmp_path) -> None:
    settings = panel_settings.systemd.model_copy(
        update={
            "per_config": True,
            "unit_dir": tmp_path / "units",
            "xray_config_dir": tmp_path / "live" / "xray",
        },
    )
    config_id = uuid.uuid4()
    service_name = config_service_name(config_id)
    unit_path = unit_file_path(service_name, settings)
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text("[Unit]\n", encoding="utf-8")

    calls: list[tuple[str, str | None]] = []
    with patch("panel.infrastructure.vpn.systemd_unit.run_systemctl", side_effect=lambda a, s=None: calls.append((a, s))):
        with patch("panel.infrastructure.vpn.systemd_unit.reload_service", side_effect=lambda s: calls.append(("restart", s))):
            with patch("panel.infrastructure.vpn.systemd_unit.enable_service", side_effect=lambda s: calls.append(("enable", s))):
                install_config_unit(
                    ConfigProfile.XRAY_REALITY,
                    config_id,
                    config_filename="config.json",
                    config_name="Office",
                    settings=settings,
                )

    assert ("enable", service_name) not in calls
    assert ("restart", service_name) in calls
