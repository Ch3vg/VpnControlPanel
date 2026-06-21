from __future__ import annotations

from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "private_key",
        "secret",
        "api_key",
        "secret_key",
        "encryption_key",
        "access_token",
        "authorization",
        "raw_token",
        "cert_pem",
        "key_pem",
    },
)


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    if lower in _SENSITIVE_KEYS:
        return True
    if lower == "token":
        return True
    if lower.endswith("_token") and lower != "token_hash":
        return True
    return False


def sanitize_audit_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED if _is_sensitive_key(key) else sanitize_audit_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_audit_payload(item) for item in value]
    return value
