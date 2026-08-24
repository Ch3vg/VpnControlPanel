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
    # No share_public_port in default test profiles → internal inbound port.
    assert outbound["settings"]["vnext"][0]["port"] == 8443
    assert outbound["streamSettings"]["realitySettings"]["publicKey"] == "test-public-key"
    assert outbound["streamSettings"]["realitySettings"]["serverName"] == "ya.ru"
    assert client["inbounds"][0]["port"] == 19080


def test_probe_dial_port_uses_share_public_port_for_hostname(panel_settings) -> None:
    from panel.infrastructure.vpn.vpn_connectivity import _probe_allow_loopback, _probe_connect_hosts, _probe_dial_port

    profiles = dict(panel_settings.vpn.profiles)
    profiles["xray-xhttp"] = profiles["xray-xhttp"].model_copy(
        update={"share_public_port": 443, "listen_address": "127.0.0.1", "share_public_host": "learn.example.com"},
    )
    settings = panel_settings.model_copy(
        update={"vpn": panel_settings.vpn.model_copy(update={"profiles": profiles})},
    )
    template_path = panel_settings.paths.templates / "config_xhttp.json"
    config_data = json.loads(template_path.read_text(encoding="utf-8"))
    snapshot = ConfigVersionSnapshot(
        config_id=uuid.uuid4(),
        protocol=VpnProtocolType.XRAY,
        profile=ConfigProfile.XRAY_XHTTP,
        name="xhttp",
        version=1,
        port=8444,
        public_key="",
        cert_fingerprint="ab" * 32,
        config_data=config_data,
        share_public_host="foo.example.com",
    )
    assert _probe_dial_port(snapshot, "foo.example.com", settings) == 443
    assert _probe_dial_port(snapshot, "127.0.0.1", settings) == 8444
    assert _probe_allow_loopback(snapshot, settings) is False
    hosts = _probe_connect_hosts(
        settings,
        prefer_host="foo.example.com",
        allow_loopback=_probe_allow_loopback(snapshot, settings),
    )
    assert hosts == ["foo.example.com"]
    # Mux: never fall back to panel vpn.public_host (would bypass share-host DNS).
    assert settings.vpn.public_host not in hosts
    assert "127.0.0.1" not in hosts

    client = _build_xray_client_config(
        snapshot,
        host="foo.example.com",
        socks_port=19080,
        settings=settings,
    )
    assert client["outbounds"][0]["settings"]["vnext"][0]["port"] == 443


def test_mux_probe_hosts_without_prefer_are_empty(panel_settings) -> None:
    from panel.infrastructure.vpn.vpn_connectivity import _probe_connect_hosts

    hosts = _probe_connect_hosts(
        panel_settings,
        prefer_host=None,
        allow_loopback=False,
    )
    assert hosts == []


def test_legacy_probe_hosts_include_public_and_loopback(panel_settings) -> None:
    from panel.infrastructure.vpn.vpn_connectivity import _probe_connect_hosts

    settings = panel_settings.model_copy(
        update={"vpn": panel_settings.vpn.model_copy(update={"public_host": "vpn.example.com"})},
    )
    hosts = _probe_connect_hosts(settings, prefer_host=None, allow_loopback=True)
    assert hosts == ["vpn.example.com", "127.0.0.1"]


def test_build_xray_grpc_client_uses_pinned_peer_cert_sha256(panel_settings) -> None:
    template_path = panel_settings.paths.templates / "config_grpc.json"
    config_data = json.loads(template_path.read_text(encoding="utf-8"))
    config_data["inbounds"][0]["streamSettings"]["tlsSettings"]["serverName"] = "pochta.ru"
    snapshot = ConfigVersionSnapshot(
        config_id=uuid.uuid4(),
        protocol=VpnProtocolType.XRAY,
        profile=ConfigProfile.XRAY_GRPC,
        name="grpc",
        version=1,
        port=8443,
        public_key="",
        cert_fingerprint="ab" * 32,
        config_data=config_data,
    )
    client = _build_xray_client_config(
        snapshot,
        host="vpn.example.com",
        socks_port=19080,
        settings=panel_settings,
    )
    tls = client["outbounds"][0]["streamSettings"]["tlsSettings"]
    assert tls["pinnedPeerCertSha256"] == ("AB" * 32)
    assert "pinnedPeerCertChainSha256" not in tls


def test_build_xray_xhttp_client_uses_tls_pin(panel_settings) -> None:
    template_path = panel_settings.paths.templates / "config_xhttp.json"
    config_data = json.loads(template_path.read_text(encoding="utf-8"))
    snapshot = ConfigVersionSnapshot(
        config_id=uuid.uuid4(),
        protocol=VpnProtocolType.XRAY,
        profile=ConfigProfile.XRAY_XHTTP,
        name="xhttp",
        version=1,
        port=8080,
        public_key="",
        cert_fingerprint="ab" * 32,
        config_data=config_data,
    )
    client = _build_xray_client_config(
        snapshot,
        host="vpn.example.com",
        socks_port=19080,
        settings=panel_settings,
    )
    stream = client["outbounds"][0]["streamSettings"]
    assert stream["security"] == "tls"
    assert stream["tlsSettings"]["serverName"] == "vpn.example.com"
    assert stream["tlsSettings"]["fingerprint"] == "chrome"
    assert stream["tlsSettings"]["pinnedPeerCertSha256"] == ("AB" * 32)
    assert stream["xhttpSettings"]["mode"] == "stream-up"
    assert stream["xhttpSettings"]["path"]


def test_build_hysteria_client_decrypts_auth_password(panel_settings, tmp_path) -> None:
    from panel.infrastructure.crypto import FieldEncryptor
    from panel.infrastructure.vpn.vpn_connectivity import _build_hysteria_client_config

    plain_password = "super-secret-hy2-password"
    encryptor = FieldEncryptor(panel_settings.security.encryption_key)
    ca_path = tmp_path / "hy-ca.pem"
    ca_path.write_text("-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n", encoding="utf-8")
    snapshot = ConfigVersionSnapshot(
        config_id=uuid.uuid4(),
        protocol=VpnProtocolType.HYSTERIA2,
        profile=ConfigProfile.HYSTERIA2,
        name="hy2",
        version=1,
        port=8443,
        public_key=ca_path.read_text(encoding="utf-8"),
        cert_fingerprint="cd" * 32,
        config_data={
            "listen": ":8443",
            "auth": {"type": "password", "password": encryptor.encrypt(plain_password)},
            "tls": {"cert": "/tmp/c.pem", "key": "/tmp/k.pem"},
        },
    )
    client = _build_hysteria_client_config(
        snapshot,
        host="vpn.example.com",
        socks_port=19081,
        settings=panel_settings,
        ca_path=ca_path,
    )
    assert client["auth"] == plain_password
    assert client["tls"]["insecure"] is False
    assert client["tls"]["ca"] == ca_path.as_posix()
    assert "pinSHA256" in client["tls"]
    assert not str(client["auth"]).startswith("gAAAA")


def test_probe_hysteria_falls_back_to_localhost(panel_settings, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from panel.infrastructure.crypto import FieldEncryptor

    encryptor = FieldEncryptor(panel_settings.security.encryption_key)
    fake_hy = tmp_path / "hysteria"
    fake_hy.write_text("", encoding="utf-8")
    settings = panel_settings.model_copy(
        update={
            "systemd": panel_settings.systemd.model_copy(update={"hysteria_binary": fake_hy}),
            "vpn": panel_settings.vpn.model_copy(
                update={"public_host": "vpn.example.com", "connectivity_probe_cache_seconds": 1},
            ),
        },
    )
    snapshot = ConfigVersionSnapshot(
        config_id=uuid.uuid4(),
        protocol=VpnProtocolType.HYSTERIA2,
        profile=ConfigProfile.HYSTERIA2,
        name="hy2",
        version=1,
        port=8443,
        public_key="-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n",
        cert_fingerprint="cd" * 32,
        config_data={
            "listen": ":8443",
            "auth": {"type": "password", "password": encryptor.encrypt("pw")},
            "tls": {"cert": "/tmp/c.pem", "key": "/tmp/k.pem"},
        },
    )

    attempts: list[str] = []

    def fake_run_client_probe(*, cmd, config_path, socks_port, host, timeout, probe_url):
        attempts.append(host)
        config_path.unlink(missing_ok=True)
        if host == "127.0.0.1":
            return VpnConnectivityProbe(reachable=True)
        return VpnConnectivityProbe(reachable=False, detail=f"local socks proxy did not start (host={host})")

    monkeypatch.setattr(
        "panel.infrastructure.vpn.vpn_connectivity._run_client_probe",
        fake_run_client_probe,
    )

    probe = probe_config_connectivity(snapshot, settings)
    assert probe.reachable is True
    assert attempts == ["vpn.example.com", "127.0.0.1"]


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
    assert probe.detail == "via vpn.example.com:8443"


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
