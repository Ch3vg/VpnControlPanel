from unittest.mock import patch

import pytest

from panel.infrastructure.vpn.systemd_reload import reload_service


def test_reload_service_default_restart() -> None:
    with patch("panel.infrastructure.vpn.systemd_reload.subprocess.run") as run:
        reload_service("xray_reality")
    run.assert_called_once_with(
        ["systemctl", "restart", "xray_reality"],
        check=True,
        timeout=30,
    )


def test_run_systemctl_daemon_reload() -> None:
    from panel.infrastructure.vpn.systemd_reload import run_systemctl

    with patch("panel.infrastructure.vpn.systemd_reload.subprocess.run") as run:
        run_systemctl("daemon-reload")
    run.assert_called_once_with(
        ["systemctl", "daemon-reload"],
        check=True,
        timeout=30,
    )


def test_enable_service() -> None:
    from panel.infrastructure.vpn.systemd_reload import enable_service

    with patch("panel.infrastructure.vpn.systemd_reload.subprocess.run") as run:
        enable_service("vpn-test")
    run.assert_called_once_with(
        ["systemctl", "enable", "vpn-test"],
        check=True,
        timeout=30,
    )


def test_reload_service_custom_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VPN_SYSTEMCTL_CMD", "sudo -n /bin/systemctl")
    with patch("panel.infrastructure.vpn.systemd_reload.subprocess.run") as run:
        reload_service("hysteria-server")
    run.assert_called_once_with(
        ["sudo", "-n", "/bin/systemctl", "restart", "hysteria-server"],
        check=True,
        timeout=30,
    )


def test_reload_service_action_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VPN_SYSTEMCTL_ACTION", "reload")
    with patch("panel.infrastructure.vpn.systemd_reload.subprocess.run") as run:
        reload_service("nginx")
    run.assert_called_once_with(
        ["systemctl", "reload", "nginx"],
        check=True,
        timeout=30,
    )
