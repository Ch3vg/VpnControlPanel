from __future__ import annotations

import pytest

from panel.domain.value_objects.config_profile import ConfigProfile
from panel.infrastructure.vpn.service_ready import (
    ServiceNotReadyError,
    _journal_has_startup_marker,
    _systemd_start_failed,
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
    monkeypatch.setattr("panel.infrastructure.vpn.service_ready._systemd_start_failed", lambda _: False)
    monkeypatch.setattr("panel.infrastructure.vpn.service_ready._journal_has_startup_marker", lambda *_: True)
    monkeypatch.setattr("panel.infrastructure.vpn.service_ready.time.sleep", lambda _: None)

    wait_for_service_ready("xray_reality", ConfigProfile.XRAY_REALITY, settings)


def test_wait_direct_retries_until_max_wait(panel_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = panel_settings.systemd.model_copy(
        update={
            "service_ready_timeout_seconds": 2,
            "service_ready_max_wait_seconds": 5,
        },
    )
    attempts = {"chunks": 0}

    def fake_once(*_args, **_kwargs) -> bool:
        attempts["chunks"] += 1
        return False

    monkeypatch.setattr("panel.infrastructure.vpn.service_ready._uses_vpn_systemctl_wrapper", lambda: False)
    monkeypatch.setattr("panel.infrastructure.vpn.service_ready._systemd_start_failed", lambda _: False)
    monkeypatch.setattr("panel.infrastructure.vpn.service_ready._wait_direct_once", fake_once)
    monkeypatch.setattr("panel.infrastructure.vpn.service_ready._run_journalctl", lambda *_a, **_k: "still starting")

    with pytest.raises(ServiceNotReadyError, match="did not become ready within 5s"):
        wait_for_service_ready("xray_reality", ConfigProfile.XRAY_REALITY, settings)

    assert attempts["chunks"] >= 2


def test_wait_direct_fails_fast_when_service_crashed(panel_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = panel_settings.systemd.model_copy(update={"service_ready_max_wait_seconds": 600})
    monkeypatch.setattr("panel.infrastructure.vpn.service_ready._uses_vpn_systemctl_wrapper", lambda: False)
    monkeypatch.setattr("panel.infrastructure.vpn.service_ready._systemd_start_failed", lambda _: True)
    monkeypatch.setattr("panel.infrastructure.vpn.service_ready._run_journalctl", lambda *_a, **_k: "exit status 1")

    with pytest.raises(ServiceNotReadyError, match="failed during startup"):
        wait_for_service_ready("xray_reality", ConfigProfile.XRAY_REALITY, settings)


def test_systemd_start_failed_ignores_activating(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "panel.infrastructure.vpn.service_ready._systemd_show",
        lambda _name: {"ActiveState": "activating", "Result": "success"},
    )
    monkeypatch.setattr(
        "panel.infrastructure.vpn.service_ready.subprocess.run",
        lambda *args, **kwargs: type("R", (), {"stdout": "active"})(),
    )
    assert _systemd_start_failed("vpn-test") is False
