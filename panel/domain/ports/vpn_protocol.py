from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class KeyPair:
    private_key: str
    public_key: str
    cert_fingerprint: str = ""


class VpnProtocol(ABC):
    @abstractmethod
    def generate_keys(self) -> KeyPair:
        raise NotImplementedError

    @abstractmethod
    def build_config(self, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def sensitive_fields(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def write_files(self, config: dict[str, Any], base_path: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def build_client_uris(
        self,
        config: dict[str, Any],
        *,
        host: str,
        public_key: str,
        label: str = "",
    ) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def reload_service(self) -> None:
        raise NotImplementedError
