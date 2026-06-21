from __future__ import annotations

import pytest

from panel.domain.value_objects.config_profile import ConfigProfile
from panel.infrastructure.vpn.service_ready import (
    ServiceNotReadyError,
    _journal_has_startup_marker,
    startup_log_pattern,
    wait_for_service_ready,
)


def test_startup_log_pattern_xray() -> None:
    assert startup_log_pattern(ConfigProfile.XRAY_REALITY) == r"\bstarted\b"


def test_journal_has_startup_marker(panel_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "panel.infrastructure.vpn.service_ready._run_journalctl",
        lambda service_name, lines=40: "core: Xray 26.3.27 started",
    )
    assert _journal_has_startup_marker("vpn-test", ConfigProfile.XRAY_REALITY) is True


def test_wait_direct_success(panel_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = panel_settings.systemd.model_copy(update={"service_ready_timeout_seconds": 5})
    calls = {"running": 0}

    def fake_running(service_name: str) -> bool:
        calls["running"] += 1
        return calls["running"] >= 2

    monkeypatch.setattr("panel.infrastructure.vpn.service_ready._uses_vpn_systemctl_wrapper", lambda: False)
    monkeypatch.setattr("panel.infrastructure.vpn.service_ready._systemd_running", fake_running)
    monkeypatch.setattr("panel.infrastructure.vpn.service_ready._journal_has_startup_marker", lambda *_: True)
    monkeypatch.setattr("panel.infrastructure.vpn.service_ready.time.sleep", lambda _: None)

    wait_for_service_ready("xray_reality", ConfigProfile.XRAY_REALITY, settings)


def test_wait_direct_raises_when_not_ready(panel_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = panel_settings.systemd.model_copy(update={"service_ready_timeout_seconds": 1})
    monkeypatch.setattr("panel.infrastructure.vpn.service_ready._uses_vpn_systemctl_wrapper", lambda: False)
    monkeypatch.setattr("panel.infrastructure.vpn.service_ready._systemd_running", lambda _: False)
    monkeypatch.setattr("panel.infrastructure.vpn.service_ready.time.sleep", lambda _: None)
    monkeypatch.setattr("panel.infrastructure.vpn.service_ready._run_journalctl", lambda *_a, **_k: "crash")

    with pytest.raises(ServiceNotReadyError, match="did not become ready"):
        wait_for_service_ready("xray_reality", ConfigProfile.XRAY_REALITY, settings)
