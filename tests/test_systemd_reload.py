from unittest.mock import patch

import pytest

from panel.infrastructure.vpn.systemd_reload import reload_service


def test_reload_service_default_command() -> None:
    with patch("panel.infrastructure.vpn.systemd_reload.subprocess.run") as run:
        reload_service("xray_reality")
    run.assert_called_once_with(
        ["systemctl", "reload", "xray_reality"],
        check=True,
        timeout=30,
    )


def test_reload_service_custom_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VPN_SYSTEMCTL_CMD", "sudo -n /bin/systemctl")
    with patch("panel.infrastructure.vpn.systemd_reload.subprocess.run") as run:
        reload_service("hysteria-server")
    run.assert_called_once_with(
        ["sudo", "-n", "/bin/systemctl", "reload", "hysteria-server"],
        check=True,
        timeout=30,
    )
