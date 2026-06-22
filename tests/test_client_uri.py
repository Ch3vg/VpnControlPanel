from __future__ import annotations

from panel.domain.value_objects.config_profile import ConfigProfile
from panel.infrastructure.vpn.client_uri import build_share_uris
from panel.infrastructure.vpn.config_builder import ProfileConfigBuilder


def test_reality_share_uri_format(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    result = builder.build(ConfigProfile.XRAY_REALITY, name="ignored")
    uris = build_share_uris(
        ConfigProfile.XRAY_REALITY,
        result.config_data,
        host="chevg.ignorelist.com",
        public_key=result.public_key,
        inbound_tag="vless-reality-in",
    )
    uri = uris[0]
    assert uri.startswith("vless://")
    assert "encryption=none" not in uri
    assert "type=tcp" in uri
    assert "security=reality" in uri
    assert "flow=xtls-rprx-vision" in uri
    assert "fp=chrome" in uri
    assert f"pbk={result.public_key}" in uri
    assert "sid=" in uri
    assert "sni=" in uri
    assert "fragment=true" in uri
    assert uri.endswith("#Reality-Dynamic")


def test_xhttp_share_uri_format(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    result = builder.build(ConfigProfile.XRAY_XHTTP, name="ignored")
    uris = build_share_uris(
        ConfigProfile.XRAY_XHTTP,
        result.config_data,
        host="chevg.ignorelist.com",
        public_key="",
        inbound_tag="vless-xhttp-in",
    )
    uri = uris[0]
    assert "type=xhttp" in uri
    assert "security=none" in uri
    assert "host=" in uri
    assert "path=" in uri
    assert "mode=packet-up" in uri
    assert uri.endswith("#XHTTP-Dynamic")


def test_grpc_share_uri_format(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    result = builder.build(ConfigProfile.XRAY_GRPC, name="ignored")
    inbound = result.config_data["inbounds"][0]
    sni = inbound["streamSettings"]["tlsSettings"]["serverName"]
    assert sni in panel_settings.vpn.profiles["xray-grpc"].grpc_sni_hosts
    uris = build_share_uris(
        ConfigProfile.XRAY_GRPC,
        result.config_data,
        host="chevg.ignorelist.com",
        public_key="",
        cert_fingerprint=result.cert_fingerprint,
        inbound_tag="vless-grpc-trusted",
    )
    uri = uris[0]
    assert "type=grpc" in uri
    assert "security=tls" in uri
    assert f"sni={sni}" in uri
    assert "serviceName=" in uri
    assert "fingerprint=randomized" in uri
    assert "pcs=" in uri
    assert "insecure=0" in uri
    assert "fragment=true" not in uri
    assert uri.endswith("#gRPC-Dynamic")


def test_grpc_sni_preserved_on_regenerate(panel_settings, monkeypatch) -> None:
    monkeypatch.setattr(
        "panel.infrastructure.vpn.config_builder.random.choice",
        lambda hosts: "gosuslugi.ru",
    )
    builder = ProfileConfigBuilder(panel_settings)
    first = builder.build(ConfigProfile.XRAY_GRPC, name="ignored")
    sni = first.config_data["inbounds"][0]["streamSettings"]["tlsSettings"]["serverName"]
    assert sni == "gosuslugi.ru"

    second = builder.build(
        ConfigProfile.XRAY_GRPC,
        name="ignored",
        preferred_grpc_sni=sni,
    )
    second_sni = second.config_data["inbounds"][0]["streamSettings"]["tlsSettings"]["serverName"]
    assert second_sni == sni


def test_hysteria2_share_uri_insecure(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    result = builder.build(ConfigProfile.HYSTERIA2, name="ignored")
    uris = build_share_uris(
        ConfigProfile.HYSTERIA2,
        result.config_data,
        host="chevg.ignorelist.com",
        public_key="",
        cert_fingerprint=result.cert_fingerprint,
        secure=False,
    )
    uri = uris[0]
    assert "pinSHA256=" not in uri
    assert "insecure=1" in uri


def test_grpc_share_uri_insecure(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    result = builder.build(ConfigProfile.XRAY_GRPC, name="ignored")
    uris = build_share_uris(
        ConfigProfile.XRAY_GRPC,
        result.config_data,
        host="chevg.ignorelist.com",
        public_key="",
        cert_fingerprint=result.cert_fingerprint,
        inbound_tag="vless-grpc-trusted",
        secure=False,
    )
    uri = uris[0]
    assert "pcs=" not in uri
    assert "fragment=true" not in uri
    assert "insecure=1" in uri


def test_hysteria2_share_uri_format(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    result = builder.build(ConfigProfile.HYSTERIA2, name="ignored")
    uris = build_share_uris(
        ConfigProfile.HYSTERIA2,
        result.config_data,
        host="chevg.ignorelist.com",
        public_key="",
        cert_fingerprint=result.cert_fingerprint,
    )
    uri = uris[0]
    assert uri.startswith("hysteria2://")
    assert "sni=" in uri
    assert "pinSHA256=" in uri
    assert "insecure=0" in uri
    assert uri.endswith("#Hysteria2-Dynamic")
