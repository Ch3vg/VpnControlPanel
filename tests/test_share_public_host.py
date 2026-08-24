from __future__ import annotations

import pytest

from panel.domain.value_objects.config_profile import ConfigProfile
from panel.domain.value_objects.regenerate_policy import RegeneratePolicy
from panel.domain.value_objects.share_public_host import (
    InvalidSharePublicHost,
    normalize_share_public_host,
)
from panel.infrastructure.vpn.config_builder import ProfileConfigBuilder


def test_normalize_share_public_host() -> None:
    assert normalize_share_public_host("  Foo.Example.COM. ") == "foo.example.com"
    assert normalize_share_public_host("") is None
    assert normalize_share_public_host(None) is None
    with pytest.raises(InvalidSharePublicHost):
        normalize_share_public_host("https://foo.example.com")
    with pytest.raises(InvalidSharePublicHost):
        normalize_share_public_host("foo.example.com:443")


def test_xhttp_build_uses_config_share_public_host(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    result = builder.build(
        ConfigProfile.XRAY_XHTTP,
        name="X",
        policy=RegeneratePolicy(rotate_tls=True),
        share_public_host="foo.example.com",
    )
    inbound = result.config_data["inbounds"][0]
    assert inbound["streamSettings"]["xhttpSettings"]["host"] == "foo.example.com"
    assert inbound["streamSettings"]["tlsSettings"]["serverName"] == "foo.example.com"
    uris = builder.build_client_uris(
        ConfigProfile.XRAY_XHTTP,
        result.config_data,
        public_key=result.public_key,
        cert_fingerprint=result.cert_fingerprint,
        share_public_host="foo.example.com",
    )
    assert "@foo.example.com:" in uris[0]
