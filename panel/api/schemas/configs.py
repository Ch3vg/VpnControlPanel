from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from panel.domain.entities.vpn_config import VpnConfig, VpnConfigVersion
from panel.domain.value_objects.config_profile import ConfigProfile
from panel.domain.value_objects.config_status import ConfigStatus
from panel.domain.value_objects.protocol import VpnProtocolType


class ConfigVersionResponse(BaseModel):
    id: str
    version: int
    port: int
    public_key: str
    cert_fingerprint: str
    created_at: datetime


class ConfigListItemResponse(BaseModel):
    id: str
    name: str
    protocol: VpnProtocolType
    status: ConfigStatus
    current_version: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ConfigListResponse(BaseModel):
    items: list[ConfigListItemResponse]
    total: int
    limit: int
    offset: int


class CreateConfigRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    protocol: VpnProtocolType
    profile: ConfigProfile | None = None

    @model_validator(mode="after")
    def default_profile(self) -> CreateConfigRequest:
        if self.profile is None:
            object.__setattr__(
                self,
                "profile",
                ConfigProfile.default_for_protocol(self.protocol.value),
            )
        return self


class CreateConfigResponse(BaseModel):
    task_id: str
    config_id: str


class RegenerateConfigResponse(BaseModel):
    task_id: str
    config_id: str


class RegenerateAllItemResponse(BaseModel):
    config_id: str
    task_id: str


class RegenerateAllSkippedResponse(BaseModel):
    config_id: str
    reason: str


class RegenerateAllResponse(BaseModel):
    queued: list[RegenerateAllItemResponse]
    skipped: list[RegenerateAllSkippedResponse]


class ConfigStatusResponse(BaseModel):
    config_id: str
    status: ConfigStatus
    task_id: str | None
    task_status: str | None = None
    retries: int | None = None
    max_retries: int | None = None
    error_message: str | None = None
    runtime_online: bool | None = None
    runtime_systemd_active: bool | None = None
    runtime_port_listening: bool | None = None
    runtime_detail: str | None = None


class ConfigRuntimeItemResponse(BaseModel):
    config_id: str
    online: bool | None
    systemd_active: bool | None
    port_listening: bool | None
    detail: str | None = None


class ConfigRuntimeListResponse(BaseModel):
    items: list[ConfigRuntimeItemResponse]


class ConfigDetailResponse(BaseModel):
    id: str
    name: str
    protocol: VpnProtocolType
    status: ConfigStatus
    current_version: int | None
    last_task_id: str | None
    error_message: str | None
    is_active: bool
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    current_version_detail: ConfigVersionResponse | None = None


def _version_response(version: VpnConfigVersion) -> ConfigVersionResponse:
    return ConfigVersionResponse(
        id=str(version.id),
        version=version.version,
        port=version.port,
        public_key=version.public_key,
        cert_fingerprint=version.cert_fingerprint,
        created_at=version.created_at,
    )


def config_to_list_item(config: VpnConfig) -> ConfigListItemResponse:
    return ConfigListItemResponse(
        id=str(config.id),
        name=config.name,
        protocol=config.protocol,
        status=config.status,
        current_version=config.current_version,
        is_active=config.is_active,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def config_to_detail(config: VpnConfig) -> ConfigDetailResponse:
    version_detail = (
        _version_response(config.current_version_detail)
        if config.current_version_detail is not None
        else None
    )
    return ConfigDetailResponse(
        id=str(config.id),
        name=config.name,
        protocol=config.protocol,
        status=config.status,
        current_version=config.current_version,
        last_task_id=config.last_task_id,
        error_message=config.error_message,
        is_active=config.is_active,
        created_by=str(config.created_by),
        updated_by=str(config.updated_by),
        created_at=config.created_at,
        updated_at=config.updated_at,
        current_version_detail=version_detail,
    )
