from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from panel.domain.value_objects.config_profile import ConfigProfile
from panel.infrastructure.vpn.service_runtime import is_tcp_port_open, probe_config_runtime


def test_is_tcp_port_open_free_port() -> None:
    with patch("panel.infrastructure.vpn.service_runtime.socket.socket") as socket_cls:
        sock = socket_cls.return_value.__enter__.return_value
        sock.connect_ex.return_value = 0
        assert is_tcp_port_open(8443) is True


def test_probe_config_runtime_online(panel_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    config_id = uuid.uuid4()
    monkeypatch.setattr("panel.infrastructure.vpn.service_runtime._systemd_running", lambda _: True)
    monkeypatch.setattr("panel.infrastructure.vpn.service_runtime.is_tcp_port_open", lambda *_a, **_k: True)

    probe = probe_config_runtime(
        config_id=config_id,
        profile=ConfigProfile.XRAY_REALITY,
        port=8443,
        settings=panel_settings,
    )

    assert probe.online is True
    assert probe.systemd_active is True
    assert probe.port_listening is True
    assert probe.detail is None


def test_probe_config_runtime_offline_when_port_closed(panel_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    config_id = uuid.uuid4()
    settings = panel_settings.model_copy(
        update={"systemd": panel_settings.systemd.model_copy(update={"per_config": True})},
    )
    monkeypatch.setattr("panel.infrastructure.vpn.service_runtime._systemd_running", lambda _: True)
    monkeypatch.setattr("panel.infrastructure.vpn.service_runtime.is_tcp_port_open", lambda *_a, **_k: False)

    probe = probe_config_runtime(
        config_id=config_id,
        profile=ConfigProfile.XRAY_REALITY,
        port=8443,
        settings=settings,
    )

    assert probe.online is False
    assert probe.detail == "port 8443 not listening"


def test_probe_config_runtime_hysteria_uses_systemd_only(panel_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    config_id = uuid.uuid4()
    monkeypatch.setattr("panel.infrastructure.vpn.service_runtime._systemd_running", lambda _: False)

    probe = probe_config_runtime(
        config_id=config_id,
        profile=ConfigProfile.HYSTERIA2,
        port=8443,
        settings=panel_settings,
    )

    assert probe.online is False
    assert probe.port_listening is None
    assert probe.detail == "service not running"
