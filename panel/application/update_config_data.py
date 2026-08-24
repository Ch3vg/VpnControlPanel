from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import yaml

from panel.application.audit_service import AuditService
from panel.application.configs import ConfigNotFound
from panel.config import PanelSettings
from panel.domain.entities.user import User
from panel.domain.value_objects.config_profile import ConfigProfile
from panel.domain.value_objects.config_status import ConfigStatus
from panel.infrastructure.crypto import FieldEncryptor
from panel.infrastructure.crypto.config_data import decrypt_config_data_fields, encrypt_config_data_fields
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository
from panel.infrastructure.vpn.config_builder import BuildResult, ProfileConfigBuilder, listening_port


class ConfigDataUnavailable(Exception):
    pass


class InvalidConfigData(Exception):
    pass


ConfigFormat = Literal["json", "yaml"]


def format_for_profile(profile: ConfigProfile) -> ConfigFormat:
    return "yaml" if profile is ConfigProfile.HYSTERIA2 else "json"


def serialize_config_data(config_data: dict[str, Any], fmt: ConfigFormat) -> str:
    if fmt == "yaml":
        return yaml.safe_dump(config_data, sort_keys=False, allow_unicode=True)
    return json.dumps(config_data, indent=2, ensure_ascii=False)


def parse_config_content(content: str, fmt: ConfigFormat) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        raise InvalidConfigData("Empty document")
    try:
        if fmt == "yaml":
            data = yaml.safe_load(text)
        else:
            data = json.loads(text)
    except Exception as exc:
        raise InvalidConfigData(f"Syntax error: {exc}") from exc
    if not isinstance(data, dict) or not data:
        raise InvalidConfigData("Root must be a non-empty object")
    return data


@dataclass(frozen=True, slots=True)
class ConfigDataResult:
    config_id: uuid.UUID
    version: int
    profile: str
    format: ConfigFormat
    content: str
    config_data: dict[str, Any]


class GetConfigDataUseCase:
    def __init__(
        self,
        settings: PanelSettings,
        configs: VpnConfigRepository,
        encryptor: FieldEncryptor,
    ) -> None:
        self._settings = settings
        self._configs = configs
        self._encryptor = encryptor

    async def execute(self, config_id: uuid.UUID) -> ConfigDataResult:
        config = await self._configs.get_by_id(config_id)
        if config is None or config.current_version is None:
            raise ConfigNotFound
        snapshot = await self._configs.get_version_snapshot(config_id, config.current_version)
        if snapshot is None:
            raise ConfigDataUnavailable("Current version not found")
        builder = ProfileConfigBuilder(self._settings)
        plain = decrypt_config_data_fields(
            snapshot.config_data,
            builder.sensitive_fields(snapshot.profile),
            self._encryptor,
        )
        fmt = format_for_profile(snapshot.profile)
        return ConfigDataResult(
            config_id=config_id,
            version=snapshot.version,
            profile=snapshot.profile.value,
            format=fmt,
            content=serialize_config_data(plain, fmt),
            config_data=plain,
        )


class UpdateConfigDataUseCase:
    def __init__(
        self,
        settings: PanelSettings,
        configs: VpnConfigRepository,
        encryptor: FieldEncryptor,
        audit: AuditService,
    ) -> None:
        self._settings = settings
        self._configs = configs
        self._encryptor = encryptor
        self._audit = audit

    async def execute(
        self,
        config_id: uuid.UUID,
        user: User,
        *,
        config_data: dict[str, Any] | None = None,
        content: str | None = None,
        format: ConfigFormat | None = None,
    ) -> ConfigDataResult:
        config = await self._configs.get_by_id(config_id)
        if config is None or config.current_version is None:
            raise ConfigNotFound
        if config.status in (ConfigStatus.PENDING, ConfigStatus.PROCESSING):
            raise InvalidConfigData("Config is busy; wait until status is active/failed")

        snapshot = await self._configs.get_version_snapshot(config_id, config.current_version)
        if snapshot is None:
            raise ConfigDataUnavailable("Current version not found")

        profile = snapshot.profile
        if profile.value not in self._settings.vpn.profiles:
            raise InvalidConfigData(f"Unknown profile: {profile.value}")
        profile_settings = self._settings.vpn.profiles[profile.value]
        builder = ProfileConfigBuilder(self._settings)
        fmt = format or format_for_profile(profile)

        if content is not None:
            parsed = parse_config_content(content, fmt)
        elif isinstance(config_data, dict) and config_data:
            parsed = config_data
        else:
            raise InvalidConfigData("Provide content or config_data object")

        try:
            port = listening_port(profile, parsed, profile_settings)
        except Exception:
            port = snapshot.port

        stored = encrypt_config_data_fields(
            parsed,
            builder.sensitive_fields(profile),
            self._encryptor,
        )
        await self._configs.update_version_config_data(
            config_id,
            snapshot.version,
            config_data=stored,
            port=port,
            updated_by=user.id,
        )

        result = BuildResult(
            config_data=parsed,
            port=port,
            private_key="",
            public_key=snapshot.public_key,
            cert_fingerprint=snapshot.cert_fingerprint,
            extra_files={},
        )
        await asyncio.to_thread(
            builder.write_files,
            profile,
            config_id,
            result,
            config_name=snapshot.name,
        )

        await self._audit.log(
            "config.config_data_updated",
            {
                "config_id": str(config_id),
                "version": snapshot.version,
                "port": port,
                "format": fmt,
            },
            user_id=user.id,
        )
        return ConfigDataResult(
            config_id=config_id,
            version=snapshot.version,
            profile=profile.value,
            format=fmt,
            content=serialize_config_data(parsed, fmt),
            config_data=parsed,
        )
