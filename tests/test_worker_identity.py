from __future__ import annotations

import pytest

from panel.worker.identity import resolve_worker_id


def test_resolve_worker_id_without_instance(panel_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VPN_WORKER_INSTANCE", raising=False)
    assert resolve_worker_id(panel_settings) == panel_settings.worker.worker_id


def test_resolve_worker_id_from_env(panel_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VPN_WORKER_INSTANCE", "2")
    assert resolve_worker_id(panel_settings) == f"{panel_settings.worker.worker_id}-2"


def test_resolve_worker_id_from_argument(panel_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VPN_WORKER_INSTANCE", "9")
    assert resolve_worker_id(panel_settings, instance="3") == f"{panel_settings.worker.worker_id}-3"
