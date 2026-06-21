from __future__ import annotations

from panel.config import PanelSettings, VpnServiceSettings
from panel.domain.ports.vpn_protocol import VpnProtocol
from panel.domain.value_objects.protocol import VpnProtocolType
from panel.infrastructure.vpn.hysteria2 import Hysteria2Protocol
from panel.infrastructure.vpn.xray import XrayProtocol


def get_vpn_protocol(protocol: VpnProtocolType | str, settings: PanelSettings) -> VpnProtocol:
    protocol_type = VpnProtocolType(protocol)
    if protocol_type is VpnProtocolType.XRAY:
        service = settings.vpn.xray or _service_from_profile(settings, "xray-reality")
        return XrayProtocol(service)
    if protocol_type is VpnProtocolType.HYSTERIA2:
        service = settings.vpn.hysteria2 or _service_from_profile(settings, "hysteria2")
        return Hysteria2Protocol(service)
    raise ValueError(f"Unsupported protocol: {protocol}")


def _service_from_profile(settings: PanelSettings, profile_key: str) -> VpnServiceSettings:
    profile = settings.vpn.profiles[profile_key]
    return VpnServiceSettings(
        service_name=profile.service_name,
        config_filename=profile.config_filename,
    )
