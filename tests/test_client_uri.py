from __future__ import annotations

from panel.domain.value_objects.config_profile import ConfigProfile
from panel.infrastructure.vpn.client_uri import (
    _REALITY_FINGERPRINTS,
    build_share_uris,
    dest_hostname,
    pick_reality_fingerprint,
    pick_server_name,
    reality_share_sni,
)
from panel.infrastructure.vpn.config_builder import ProfileConfigBuilder


def test_pick_server_name_skips_empty_and_uses_pool() -> None:
    assert pick_server_name(["", "ya.ru", "vk.com"]) in {"ya.ru", "vk.com"}
    assert pick_server_name([]) == ""


def test_pick_reality_fingerprint_from_pool() -> None:
    assert pick_reality_fingerprint() in _REALITY_FINGERPRINTS


def test_dest_hostname_and_reality_share_sni() -> None:
    assert dest_hostname("ya.ru:443") == "ya.ru"
    assert dest_hostname("www.microsoft.com:443") == "www.microsoft.com"
    assert reality_share_sni({"dest": "vk.com:443", "serverNames": ["other.ru"]}) == "vk.com"
    assert reality_share_sni({"dest": "", "serverNames": ["", "ya.ru"]}) == "ya.ru"


def test_hysteria_share_uri_uses_share_public_host(panel_settings) -> None:
    profiles = dict(panel_settings.vpn.profiles)
    profiles["hysteria2"] = profiles["hysteria2"].model_copy(
        update={
            "share_public_host": "hy.example.com",
            "share_public_port": 443,
            "port_candidates": [443, 1935],
        },
    )
    settings = panel_settings.model_copy(
        update={"vpn": panel_settings.vpn.model_copy(update={"profiles": profiles})},
    )
    builder = ProfileConfigBuilder(settings)
    result = builder.build(ConfigProfile.HYSTERIA2, name="Hy")
    assert result.config_data["tls"]["sni"] == "hy.example.com"
    assert result.config_data["listen"] == ":443"
    uris = builder.build_client_uris(
        ConfigProfile.HYSTERIA2,
        result.config_data,
        public_key=result.public_key,
        cert_fingerprint=result.cert_fingerprint,
    )
    assert uris[0].startswith("hysteria2://")
    assert "@hy.example.com:443?" in uris[0]
    assert "sni=hy.example.com" in uris[0]


def test_reality_share_uri_uses_share_public_port(panel_settings) -> None:
    profiles = dict(panel_settings.vpn.profiles)
    profiles["xray-reality"] = profiles["xray-reality"].model_copy(
        update={"share_public_port": 443, "listen_address": "127.0.0.1"},
    )
    settings = panel_settings.model_copy(
        update={"vpn": panel_settings.vpn.model_copy(update={"profiles": profiles})},
    )
    builder = ProfileConfigBuilder(settings)
    result = builder.build(ConfigProfile.XRAY_REALITY, name="ignored")
    inbound = result.config_data["inbounds"][0]
    assert inbound["listen"] == "127.0.0.1"
    assert inbound["port"] != 443
    uris = builder.build_client_uris(
        ConfigProfile.XRAY_REALITY,
        result.config_data,
        public_key=result.public_key,
    )
    assert f"@{settings.vpn.public_host}:443?" in uris[0]
    assert f":{inbound['port']}?" not in uris[0]


def test_reality_share_uri_uses_share_public_host(panel_settings) -> None:
    profiles = dict(panel_settings.vpn.profiles)
    profiles["xray-reality"] = profiles["xray-reality"].model_copy(
        update={
            "share_public_host": "auth.example.com",
            "share_public_port": 443,
            "listen_address": "127.0.0.1",
        },
    )
    settings = panel_settings.model_copy(
        update={"vpn": panel_settings.vpn.model_copy(update={"profiles": profiles})},
    )
    builder = ProfileConfigBuilder(settings)
    result = builder.build(ConfigProfile.XRAY_REALITY, name="ignored")
    dest = result.config_data["inbounds"][0]["streamSettings"]["realitySettings"]["dest"]
    uris = builder.build_client_uris(
        ConfigProfile.XRAY_REALITY,
        result.config_data,
        public_key=result.public_key,
    )
    assert "@auth.example.com:443?" in uris[0]
    assert f"sni={dest.split(':')[0]}" in uris[0] or "sni=" in uris[0]
    assert "sni=auth.example.com" not in uris[0]


def test_reality_share_uri_format(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    result = builder.build(ConfigProfile.XRAY_REALITY, name="ignored")
    uris = build_share_uris(
        ConfigProfile.XRAY_REALITY,
        result.config_data,
        host="vpn.example.com",
        public_key=result.public_key,
        inbound_tag="vless-reality-in",
    )
    uri = uris[0]
    dest = result.config_data["inbounds"][0]["streamSettings"]["realitySettings"]["dest"]
    sni = dest_hostname(dest)
    assert uri.startswith("vless://")
    assert "encryption=none" not in uri
    assert "type=tcp" in uri
    assert "security=reality" in uri
    assert "flow=xtls-rprx-vision" in uri
    assert "fp=chrome" in uri
    assert f"pbk={result.public_key}" in uri
    assert "sid=" in uri
    assert f"sni={sni}" in uri
    assert "fragment=" not in uri
    assert uri.endswith("#Reality-Dynamic")


def test_xhttp_share_uri_format(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    result = builder.build(ConfigProfile.XRAY_XHTTP, name="ignored")
    assert result.cert_fingerprint
    assert result.private_key
    inbound = result.config_data["inbounds"][0]
    sni = panel_settings.vpn.public_host
    assert inbound["streamSettings"]["security"] == "tls"
    assert inbound["streamSettings"]["tlsSettings"]["serverName"] == sni
    assert inbound["streamSettings"]["xhttpSettings"]["host"] == sni
    uris = build_share_uris(
        ConfigProfile.XRAY_XHTTP,
        result.config_data,
        host="vpn.example.com",
        public_key="",
        cert_fingerprint=result.cert_fingerprint,
        inbound_tag="vless-xhttp-in",
    )
    uri = uris[0]
    assert "type=xhttp" in uri
    assert "security=tls" in uri
    assert f"host={sni}" in uri
    assert "path=" in uri
    assert "mode=stream-up" in uri
    assert f"sni={sni}" in uri
    assert "vpn-panel" not in uri
    assert "fp=chrome" in uri
    assert "pcs=" in uri
    assert "insecure=" not in uri
    assert "allowInsecure" not in uri
    assert uri.endswith("#XHTTP-Dynamic")


def test_xhttp_share_uri_insecure(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    result = builder.build(ConfigProfile.XRAY_XHTTP, name="ignored")
    uris = build_share_uris(
        ConfigProfile.XRAY_XHTTP,
        result.config_data,
        host="vpn.example.com",
        public_key="",
        cert_fingerprint=result.cert_fingerprint,
        inbound_tag="vless-xhttp-in",
        secure=False,
    )
    uri = uris[0]
    assert "pcs=" not in uri
    assert "insecure=1" in uri
    assert "security=tls" in uri


def test_grpc_share_uri_format(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    result = builder.build(ConfigProfile.XRAY_GRPC, name="ignored")
    inbound = result.config_data["inbounds"][0]
    sni = inbound["streamSettings"]["tlsSettings"]["serverName"]
    service_name = inbound["streamSettings"]["grpcSettings"]["serviceName"]
    assert sni in panel_settings.vpn.profiles["xray-grpc"].grpc_sni_hosts
    assert service_name in panel_settings.vpn.profiles["xray-grpc"].grpc_service_names
    assert inbound["streamSettings"]["tlsSettings"]["alpn"] == ["h2"]
    assert "fingerprint" not in inbound["streamSettings"]["tlsSettings"]
    uris = build_share_uris(
        ConfigProfile.XRAY_GRPC,
        result.config_data,
        host="vpn.example.com",
        public_key="",
        cert_fingerprint=result.cert_fingerprint,
        inbound_tag="vless-grpc-trusted",
    )
    uri = uris[0]
    assert "type=grpc" in uri
    assert "security=tls" in uri
    assert f"sni={sni}" in uri
    assert f"serviceName={service_name}" in uri
    assert "fp=chrome" in uri
    assert "pcs=" in uri
    assert "insecure=" not in uri
    assert "fragment=true" not in uri
    assert uri.endswith("#gRPC-Dynamic")


def test_grpc_sni_and_service_preserved_on_regenerate(panel_settings, monkeypatch) -> None:
    monkeypatch.setattr(
        "panel.infrastructure.vpn.config_builder.random.choice",
        lambda hosts: "gosuslugi.ru" if "gosuslugi.ru" in hosts else "Api",
    )
    builder = ProfileConfigBuilder(panel_settings)
    first = builder.build(ConfigProfile.XRAY_GRPC, name="ignored")
    sni = first.config_data["inbounds"][0]["streamSettings"]["tlsSettings"]["serverName"]
    service_name = first.config_data["inbounds"][0]["streamSettings"]["grpcSettings"]["serviceName"]
    assert sni == "gosuslugi.ru"
    assert service_name == "Api"

    second = builder.build(
        ConfigProfile.XRAY_GRPC,
        name="ignored",
        preferred_grpc_sni=sni,
        preferred_grpc_service_name=service_name,
    )
    second_inbound = second.config_data["inbounds"][0]["streamSettings"]
    assert second_inbound["tlsSettings"]["serverName"] == sni
    assert second_inbound["grpcSettings"]["serviceName"] == service_name


def test_hysteria2_share_uri_insecure(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    result = builder.build(ConfigProfile.HYSTERIA2, name="ignored")
    uris = build_share_uris(
        ConfigProfile.HYSTERIA2,
        result.config_data,
        host="vpn.example.com",
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
        host="vpn.example.com",
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
    obfs_password = result.config_data["obfs"]["salamander"]["password"]
    uris = build_share_uris(
        ConfigProfile.HYSTERIA2,
        result.config_data,
        host="vpn.example.com",
        public_key="",
        cert_fingerprint=result.cert_fingerprint,
    )
    uri = uris[0]
    assert uri.startswith("hysteria2://")
    assert f"sni={panel_settings.vpn.public_host}" in uri
    assert "vpn-panel" not in uri
    assert "obfs=salamander" in uri
    assert f"obfs-password={obfs_password}" in uri
    assert "pinSHA256=" in uri
    assert "insecure=0" in uri
    assert uri.endswith("#Hysteria2-Dynamic")
