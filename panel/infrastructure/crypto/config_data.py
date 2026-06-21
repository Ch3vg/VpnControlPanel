from __future__ import annotations

import copy
from typing import Any

from panel.infrastructure.crypto.field_encryptor import FieldEncryptor


def _get_by_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        else:
            current = current[part]
    return current


def _set_by_path(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current: Any = data
    for part in parts[:-1]:
        if isinstance(current, list):
            current = current[int(part)]
        else:
            current = current[part]
    last = parts[-1]
    if isinstance(current, list):
        current[int(last)] = value
    else:
        current[last] = value


def decrypt_config_data_fields(
    config_data: dict[str, Any],
    sensitive_paths: list[str],
    encryptor: FieldEncryptor,
) -> dict[str, Any]:
    result = copy.deepcopy(config_data)
    for path in sensitive_paths:
        try:
            value = _get_by_path(result, path)
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if isinstance(value, str) and value:
            _set_by_path(result, path, encryptor.decrypt(value))
    return result


def encrypt_config_data_fields(
    config_data: dict[str, Any],
    sensitive_paths: list[str],
    encryptor: FieldEncryptor,
) -> dict[str, Any]:
    result = copy.deepcopy(config_data)
    for path in sensitive_paths:
        try:
            value = _get_by_path(result, path)
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if isinstance(value, str) and value:
            _set_by_path(result, path, encryptor.encrypt(value))
    return result
