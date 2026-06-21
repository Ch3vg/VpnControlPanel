from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class ServerSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8001, ge=1, le=65535)


class DatabaseSettings(BaseModel):
    dsn: str


class QueueSettings(BaseModel):
    default_lock_ttl_seconds: int = Field(default=180, ge=1)
    default_max_retries: int = Field(default=3, ge=0)
    retry_delay_seconds: int = Field(default=10, ge=0)
    default_pull_timeout_seconds: int = Field(default=30, ge=1)
    pull_interval_seconds: int = Field(default=1, ge=1)


class SecuritySettings(BaseModel):
    api_key: str | None = None

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return value
        _reject_placeholder(value, "security.api_key")
        if len(value) < 32:
            raise ValueError("security.api_key must be at least 32 characters")
        return value


class LoggingSettings(BaseModel):
    level: str = "INFO"


class BrokerYamlSettings(BaseModel):
    server: ServerSettings = Field(default_factory=ServerSettings)
    database: DatabaseSettings
    queue: QueueSettings = Field(default_factory=QueueSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)


_FORBIDDEN = frozenset(
    {
        "changeme",
        "replace-with-at-least-32-char-secret-key",
        "your-secret-key",
        "secret",
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


def load_broker_settings(config_path: Path | None = None) -> BrokerYamlSettings:
    path = config_path or _resolve_config_path(
        env_var="BROKER_CONFIG_PATH",
        default_name="broker.yaml",
    )
    return BrokerYamlSettings.model_validate(_load_yaml(path))


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
