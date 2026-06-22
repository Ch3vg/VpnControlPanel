from __future__ import annotations

from unittest.mock import patch

import pytest

from panel.infrastructure.vpn.port_picker import PortUnavailableError, is_port_available, pick_port


def test_pick_port_returns_first_available() -> None:
    with patch(
        "panel.infrastructure.vpn.port_picker.is_port_available",
        side_effect=lambda port, **_: port == 8443,
    ):
        port = pick_port([2053, 8443, 9443], exclude={2053})
    assert port == 8443


def test_pick_port_raises_when_none_available() -> None:
    with patch("panel.infrastructure.vpn.port_picker.is_port_available", return_value=False):
        with pytest.raises(PortUnavailableError, match="No free TCP port"):
            pick_port([8443, 9443])


def test_pick_port_udp_mode() -> None:
    with patch(
        "panel.infrastructure.vpn.port_picker.is_port_available",
        side_effect=lambda port, udp=False, **_: udp and port == 3478,
    ) as mock_check:
        port = pick_port([8443, 3478], udp=True)
    assert port == 3478
    assert mock_check.call_args.kwargs["udp"] is True


def test_pick_port_retries_all_candidates_when_excluded() -> None:
    with patch(
        "panel.infrastructure.vpn.port_picker.is_port_available",
        side_effect=lambda port, **_: port == 2053,
    ):
        port = pick_port([2053, 8443], exclude={2053, 8443})
    assert port == 2053


def test_is_port_available_bind_failure() -> None:
    with patch("panel.infrastructure.vpn.port_picker.socket.socket") as socket_cls:
        sock = socket_cls.return_value.__enter__.return_value
        sock.bind.side_effect = OSError("Address already in use")
        assert is_port_available(443) is False
