from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import yaml

from panel.config import OutboundVlessSettings


def load_template(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Template must be a mapping: {path}")
    return copy.deepcopy(data)


def find_inbound(config: dict[str, Any], tag: str) -> dict[str, Any]:
    for inbound in config.get("inbounds", []):
        if inbound.get("tag") == tag:
            return inbound
    raise KeyError(f"Inbound tag not found: {tag}")


def set_client_id(config: dict[str, Any], client_id: str, inbound_tag: str) -> None:
    inbound = find_inbound(config, inbound_tag)
    for client in inbound.get("settings", {}).get("clients", []):
        client["id"] = client_id


def apply_outbound_secrets(
    config: dict[str, Any],
    secrets: dict[str, OutboundVlessSettings],
) -> None:
    if not secrets:
        return
    for outbound in config.get("outbounds", []):
        tag = outbound.get("tag", "")
        if tag not in secrets or outbound.get("protocol") != "vless":
            continue
        user_id = secrets[tag].user_id.strip()
        if not user_id:
            continue
        for vnext in outbound.get("settings", {}).get("vnext", []):
            for user in vnext.get("users", []):
                user["id"] = user_id
