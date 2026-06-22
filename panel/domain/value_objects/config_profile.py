from __future__ import annotations

from enum import StrEnum


class ConfigProfile(StrEnum):
    XRAY_REALITY = "xray-reality"
    XRAY_GRPC = "xray-grpc"
    XRAY_XHTTP = "xray-xhttp"
    HYSTERIA2 = "hysteria2"

    @classmethod
    def default_for_protocol(cls, protocol: str) -> ConfigProfile:
        if protocol == "hysteria2":
            return cls.HYSTERIA2
        return cls.XRAY_REALITY
