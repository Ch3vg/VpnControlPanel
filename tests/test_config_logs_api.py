from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_config_logs(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_config: uuid.UUID,
    panel_settings,
) -> None:
    service = f"vpn-{sample_config}"
    with patch(
        "panel.application.get_config_logs.fetch_unit_journal",
        return_value=("line-one\nline-two", True),
    ) as fetch_mock:
        response = await api_client.get(
            f"/api/v1/configs/{sample_config}/logs?lines=50",
            headers=auth_headers,
        )
    assert response.status_code == 200
    body = response.json()
    assert body["config_id"] == str(sample_config)
    assert body["content"] == "line-one\nline-two"
    assert body["available"] is True
    assert body["lines"] == 50
    if panel_settings.systemd.per_config:
        assert body["service_name"] == service
    fetch_mock.assert_called_once()
    assert fetch_mock.call_args.args[0] == body["service_name"]
    assert fetch_mock.call_args.kwargs["lines"] == 50


@pytest.mark.asyncio
async def test_get_config_logs_not_found(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    missing = uuid.uuid4()
    response = await api_client.get(f"/api/v1/configs/{missing}/logs", headers=auth_headers)
    assert response.status_code == 404


def test_clamp_log_lines() -> None:
    from panel.infrastructure.vpn.service_logs import clamp_log_lines

    assert clamp_log_lines(None) == 100
    assert clamp_log_lines(0) == 1
    assert clamp_log_lines(9999) == 500
