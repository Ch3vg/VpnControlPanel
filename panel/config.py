from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class Environment(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class AppSettings(BaseModel):
    name: str = "vpn-control-panel"
    max_secure: bool = False
    environment: Environment = Environment.DEVELOPMENT


class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)


class DatabaseSettings(BaseModel):
    url: str


class SecuritySettings(BaseModel):
    secret_key: str
    encryption_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(default=60, ge=1)

    @field_validator("secret_key", "encryption_key")
    @classmethod
    def validate_secret_length(cls, value: str) -> str:
        _reject_placeholder(value, "security key")
        if len(value) < 32:
            raise ValueError("security keys must be at least 32 characters")
        return value

    @model_validator(mode="after")
    def keys_must_differ(self) -> SecuritySettings:
        if self.secret_key == self.encryption_key:
            raise ValueError("security.encryption_key must differ from security.secret_key")
        return self


class MtlsSettings(BaseModel):
    ca_file: Path
    cert_file: Path
    key_file: Path


class BrokerClientSettings(BaseModel):
    url: str
    api_key: str | None = None
    mtls: MtlsSettings | None = None

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return value
        _reject_placeholder(value, "broker.api_key")
        if len(value) < 32:
            raise ValueError("broker.api_key must be at least 32 characters")
        return value


class WorkerSettings(BaseModel):
    worker_id: str = "panel-worker-1"
    task_types: list[str] = Field(
        default_factory=lambda: ["config.initialize", "config.regenerate"],
    )


class RateLimitRule(BaseModel):
    max_attempts: int | None = Field(default=None, ge=1)
    max_requests: int | None = Field(default=None, ge=1)
    window_seconds: int = Field(ge=1)


class RateLimitSettings(BaseModel):
    login: RateLimitRule
    share: RateLimitRule


class AuditSettings(BaseModel):
    enabled: bool = True
    log_failed_login: bool = True


class MetricsSettings(BaseModel):
    enabled: bool = True


class SecurityHeadersSettings(BaseModel):
    enabled: bool = True


class WebSettings(BaseModel):
    enabled: bool = True
    mount_path: str = "/admin"


class PathsSettings(BaseModel):
    configs: Path = Path("/opt/vpn/configs")
    templates: Path = Path("configs")


class SystemdSettings(BaseModel):
    per_config: bool = False
    unit_dir: Path = Path("/etc/systemd/system")
    service_prefix: str = "vpn"
    xray_binary: Path = Path("/usr/local/bin/xray")
    hysteria_binary: Path = Path("/usr/local/bin/hysteria")
    xray_config_dir: Path = Path("/usr/local/etc/xray/configs")
    hysteria_config_dir: Path = Path("/usr/local/etc/hysteria/configs")
    service_ready_timeout_seconds: int = Field(default=30, ge=5, le=120)
    service_ready_settle_seconds: float = Field(default=2.0, ge=0, le=10)


class VpnProfileSettings(BaseModel):
    template_file: str
    service_name: str
    config_filename: str
    inbound_tag: str = ""
    port_candidates: list[int] = Field(default_factory=list)
    active_config_path: Path | None = None
    cert_dir: Path | None = None
    cert_prefix: str | None = None
    xhttp_hosts: list[str] = Field(default_factory=list)
    xhttp_paths: list[str] = Field(default_factory=list)


class VpnServiceSettings(BaseModel):
    service_name: str
    config_filename: str


class VpnSettings(BaseModel):
    public_host: str = "127.0.0.1"
    profiles: dict[str, VpnProfileSettings] = Field(default_factory=dict)
    xray: VpnServiceSettings | None = None
    hysteria2: VpnServiceSettings | None = None


class TelegramSettings(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


class PanelSettings(BaseModel):
    app: AppSettings = Field(default_factory=AppSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    database: DatabaseSettings
    security: SecuritySettings
    broker: BrokerClientSettings
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    paths: PathsSettings = Field(default_factory=PathsSettings)
    systemd: SystemdSettings = Field(default_factory=SystemdSettings)
    rate_limit: RateLimitSettings
    audit: AuditSettings = Field(default_factory=AuditSettings)
    metrics: MetricsSettings = Field(default_factory=MetricsSettings)
    security_headers: SecurityHeadersSettings = Field(default_factory=SecurityHeadersSettings)
    web: WebSettings = Field(default_factory=WebSettings)
    vpn: VpnSettings
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)


_FORBIDDEN = frozenset(
    {
        "changeme",
        "your-secret-key",
        "secret",
        "replace-with-at-least-32-char-jwt-secret-key",
        "replace-with-at-least-32-char-db-encryption-key",
        "replace-with-at-least-32-char-secret-key",
    }
)


def _reject_placeholder(value: str, field_name: str) -> None:
    normalized = value.strip().lower()
    if normalized in _FORBIDDEN or normalized.startswith("replace-with-"):
        raise ValueError(f"{field_name} must be replaced with a real secret")


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {path}")
    return data


def load_panel_settings(config_path: Path | None = None) -> PanelSettings:
    path = config_path or _resolve_config_path(
        env_var="PANEL_CONFIG_PATH",
        default_name="panel.yaml",
    )
    settings = PanelSettings.model_validate(_load_yaml(path))
    templates = settings.paths.templates
    if not templates.is_absolute():
        templates = (path.parent / templates).resolve()
    return settings.model_copy(update={"paths": settings.paths.model_copy(update={"templates": templates})})


def _resolve_config_path(*, env_var: str, default_name: str) -> Path:
    raw = os.environ.get(env_var)
    if raw:
        path = Path(raw)
    else:
        path = Path(default_name)
    if not path.is_file():
        raise FileNotFoundError(
            f"Config not found: {path}. Copy {default_name}.example and adjust values."
        )
    return path
