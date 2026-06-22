from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock

import pytest

from panel.domain.value_objects.config_profile import ConfigProfile
from panel.domain.value_objects.protocol import VpnProtocolType
from panel.infrastructure.persistence.repositories.vpn_config import ConfigVersionSnapshot
from panel.infrastructure.vpn.service_runtime import probe_config_availability
from panel.infrastructure.vpn.vpn_connectivity import (
    VpnConnectivityProbe,
    _build_xray_client_config,
    clear_connectivity_cache,
    probe_config_connectivity,
)


@pytest.fixture(autouse=True)
def _clear_connectivity_cache() -> None:
    clear_connectivity_cache()


def _reality_snapshot(panel_settings) -> ConfigVersionSnapshot:
    template_path = panel_settings.paths.templates / "config_reality.json"
    config_data = json.loads(template_path.read_text(encoding="utf-8"))
    return ConfigVersionSnapshot(
        config_id=uuid.uuid4(),
        protocol=VpnProtocolType.XRAY,
        profile=ConfigProfile.XRAY_REALITY,
        name="test",
        version=1,
        port=8443,
        public_key="test-public-key",
        cert_fingerprint="ab" * 32,
        config_data=config_data,
    )


def test_build_xray_reality_client_uses_public_host(panel_settings) -> None:
    snapshot = _reality_snapshot(panel_settings)
    client = _build_xray_client_config(
        snapshot,
        host="vpn.example.com",
        socks_port=19080,
        settings=panel_settings,
    )
    outbound = client["outbounds"][0]
    assert outbound["settings"]["vnext"][0]["address"] == "vpn.example.com"
    assert outbound["settings"]["vnext"][0]["port"] == 8443
    assert outbound["streamSettings"]["realitySettings"]["publicKey"] == "test-public-key"
    assert client["inbounds"][0]["port"] == 19080


def test_probe_config_connectivity_success(panel_settings, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _reality_snapshot(panel_settings)
    fake_xray = tmp_path / "xray"
    fake_xray.write_text("", encoding="utf-8")
    settings = panel_settings.model_copy(
        update={
            "systemd": panel_settings.systemd.model_copy(update={"xray_binary": fake_xray}),
            "vpn": panel_settings.vpn.model_copy(
                update={"public_host": "vpn.example.com", "connectivity_probe_cache_seconds": 1},
            ),
        },
    )

    proc = MagicMock()
    proc.poll.return_value = None
    monkeypatch.setattr(
        "panel.infrastructure.vpn.vpn_connectivity.subprocess.Popen",
        lambda *_a, **_k: proc,
    )
    monkeypatch.setattr("panel.infrastructure.vpn.vpn_connectivity._wait_for_port", lambda *_a, **_k: True)
    monkeypatch.setattr(
        "panel.infrastructure.vpn.vpn_connectivity._curl_via_socks",
        lambda *_a, **_k: (True, ""),
    )

    probe = probe_config_connectivity(snapshot, settings)
    assert probe.reachable is True
    assert probe.detail is None


def test_probe_config_connectivity_uses_cache(panel_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _reality_snapshot(panel_settings)
    settings = panel_settings.model_copy(
        update={
            "vpn": panel_settings.vpn.model_copy(
                update={"public_host": "vpn.example.com", "connectivity_probe_cache_seconds": 60},
            ),
        },
    )
    calls = {"count": 0}

    def fake_probe(*_a, **_k):
        calls["count"] += 1
        return VpnConnectivityProbe(reachable=True)

    monkeypatch.setattr(
        "panel.infrastructure.vpn.vpn_connectivity._probe_via_xray",
        fake_probe,
    )

    first = probe_config_connectivity(snapshot, settings)
    second = probe_config_connectivity(snapshot, settings)
    assert first.reachable is True
    assert second.reachable is True
    assert calls["count"] == 1


def test_probe_config_availability_merges_connectivity(
    panel_settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _reality_snapshot(panel_settings)
    monkeypatch.setattr(
        "panel.infrastructure.vpn.service_runtime.probe_config_runtime",
        lambda **_k: __import__(
            "panel.infrastructure.vpn.service_runtime",
            fromlist=["ServiceRuntimeProbe"],
        ).ServiceRuntimeProbe(
            online=True,
            systemd_active=True,
            port_listening=True,
            detail=None,
        ),
    )
    monkeypatch.setattr(
        "panel.infrastructure.vpn.vpn_connectivity.probe_config_connectivity",
        lambda *_a, **_k: VpnConnectivityProbe(reachable=False, detail="tls handshake failed"),
    )

    probe = probe_config_availability(
        config_id=snapshot.config_id,
        profile=snapshot.profile,
        port=snapshot.port,
        settings=panel_settings,
        snapshot=snapshot,
    )
    assert probe.online is False
    assert probe.systemd_active is True
    assert probe.detail == "tls handshake failed"
