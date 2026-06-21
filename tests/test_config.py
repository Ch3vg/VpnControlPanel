from __future__ import annotations

from pathlib import Path

import pytest

from broker_run.config import load_broker_settings
from panel.config import PanelSettings, load_panel_settings


def test_load_panel_settings(panel_config_file: Path) -> None:
    settings = load_panel_settings(panel_config_file)
    assert settings.app.name == "test-panel"
    assert settings.security.secret_key == "a" * 32


def test_panel_settings_rejects_equal_keys(panel_config_dict: dict) -> None:
    panel_config_dict["security"]["encryption_key"] = panel_config_dict["security"]["secret_key"]
    with pytest.raises(ValueError, match="must differ"):
        PanelSettings.model_validate(panel_config_dict)


def test_load_broker_settings(broker_config_file: Path) -> None:
    settings = load_broker_settings(broker_config_file)
    assert settings.server.port == 8001
    assert settings.security.api_key == "d" * 32
