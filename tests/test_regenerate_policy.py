from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from panel.domain.ports.broker import PublishedTask
from panel.domain.value_objects.config_profile import ConfigProfile
from panel.domain.value_objects.regenerate_policy import RegeneratePolicy
from panel.infrastructure.persistence.database import create_session_factory
from panel.infrastructure.persistence.models import VpnConfigModel
from panel.infrastructure.vpn.config_builder import PreviousSecrets, ProfileConfigBuilder
from panel.infrastructure.vpn.crypto_utils import generate_self_signed_cert


def test_regenerate_policy_defaults_by_profile(panel_settings) -> None:
    reality = RegeneratePolicy.for_profile(
        ConfigProfile.XRAY_REALITY,
        panel_settings.vpn.profiles["xray-reality"],
    )
    assert reality.rotate_short_ids is True
    assert reality.rotate_client_id is True
    assert reality.rotate_reality_keys is True

    xhttp = RegeneratePolicy.for_profile(
        ConfigProfile.XRAY_XHTTP,
        panel_settings.vpn.profiles["xray-xhttp"],
    )
    assert xhttp.rotate_path is True
    assert xhttp.rotate_tls is True

    grpc = RegeneratePolicy.for_profile(
        ConfigProfile.XRAY_GRPC,
        panel_settings.vpn.profiles["xray-grpc"],
    )
    assert grpc.rotate_service_name is False

    hy = RegeneratePolicy.for_profile(
        ConfigProfile.HYSTERIA2,
        panel_settings.vpn.profiles["hysteria2"],
    )
    assert hy.rotate_auth is False
    assert hy.rotate_obfs is False


def test_regenerate_policy_tls_false_when_external_paths(panel_settings, tmp_path) -> None:
    cert = tmp_path / "fullchain.pem"
    key = tmp_path / "privkey.pem"
    cert.write_text("x", encoding="utf-8")
    key.write_text("y", encoding="utf-8")
    profiles = dict(panel_settings.vpn.profiles)
    profiles["xray-xhttp"] = profiles["xray-xhttp"].model_copy(
        update={"tls_cert_file": cert, "tls_key_file": key},
    )
    policy = RegeneratePolicy.for_profile(ConfigProfile.XRAY_XHTTP, profiles["xray-xhttp"])
    assert policy.rotate_tls is False


def test_reality_policy_preserves_dest_short_ids_port(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    first = builder.build(ConfigProfile.XRAY_REALITY, name="Office")
    reality = first.config_data["inbounds"][0]["streamSettings"]["realitySettings"]
    policy = RegeneratePolicy(
        rotate_port=False,
        rotate_client_id=False,
        rotate_reality_keys=False,
        rotate_short_ids=False,
        rotate_dest=False,
    )
    second = builder.build(
        ConfigProfile.XRAY_REALITY,
        name="Office",
        previous=PreviousSecrets(
            client_id=first.client_id,
            private_key=first.private_key,
            public_key=first.public_key,
            short_ids=list(reality["shortIds"]),
            reality_dest=str(reality["dest"]),
            reality_server_names=list(reality["serverNames"]),
        ),
        preferred_port=first.port,
        policy=policy,
    )
    second_reality = second.config_data["inbounds"][0]["streamSettings"]["realitySettings"]
    assert second.port == first.port
    assert second.client_id == first.client_id
    assert second.private_key == first.private_key
    assert second_reality["shortIds"] == reality["shortIds"]
    assert second_reality["dest"] == reality["dest"]
    assert second_reality["serverNames"] == reality["serverNames"]


def test_reality_policy_rotates_client_id_and_keys(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    first = builder.build(ConfigProfile.XRAY_REALITY, name="Office")
    policy = RegeneratePolicy(
        rotate_port=True,
        rotate_client_id=True,
        rotate_reality_keys=True,
        rotate_short_ids=True,
        rotate_dest=True,
    )
    second = builder.build(
        ConfigProfile.XRAY_REALITY,
        name="Office",
        previous=PreviousSecrets(
            client_id=first.client_id,
            private_key=first.private_key,
            public_key=first.public_key,
        ),
        policy=policy,
    )
    assert second.client_id != first.client_id
    assert second.private_key != first.private_key


def test_xhttp_policy_preserves_path(panel_settings) -> None:
    builder = ProfileConfigBuilder(panel_settings)
    first = builder.build(ConfigProfile.XRAY_XHTTP, name="Office")
    path = first.config_data["inbounds"][0]["streamSettings"]["xhttpSettings"]["path"]
    policy = RegeneratePolicy(rotate_path=False, rotate_client_id=False, rotate_tls=False, rotate_port=True)
    second = builder.build(
        ConfigProfile.XRAY_XHTTP,
        name="Office",
        previous=PreviousSecrets(
            client_id=first.client_id,
            private_key=first.private_key,
            public_key=first.public_key,
            cert_fingerprint=first.cert_fingerprint,
            xhttp_path=path,
        ),
        policy=policy,
    )
    assert second.config_data["inbounds"][0]["streamSettings"]["xhttpSettings"]["path"] == path


def test_external_tls_paths_skip_extra_files(panel_settings, tmp_path) -> None:
    private_pem, cert_pem, fingerprint = generate_self_signed_cert(dns_names=["vpn.example.test"])
    cert_path = tmp_path / "fullchain.pem"
    key_path = tmp_path / "privkey.pem"
    cert_path.write_text(cert_pem, encoding="utf-8")
    key_path.write_text(private_pem, encoding="utf-8")

    profiles = dict(panel_settings.vpn.profiles)
    profiles["hysteria2"] = profiles["hysteria2"].model_copy(
        update={
            "tls_cert_file": cert_path,
            "tls_key_file": key_path,
            "share_public_host": "vpn.example.test",
        },
    )
    settings = panel_settings.model_copy(
        update={"vpn": panel_settings.vpn.model_copy(update={"profiles": profiles})},
    )
    builder = ProfileConfigBuilder(settings)
    first = builder.build(ConfigProfile.HYSTERIA2, name="Office")
    assert first.extra_files == {}
    assert first.config_data["tls"]["cert"] == str(cert_path)
    assert first.config_data["tls"]["key"] == str(key_path)
    assert first.cert_fingerprint == fingerprint

    live_dir = tmp_path / "live"
    live_dir.mkdir()
    # regenerate must not write into LE dir
    second = builder.build(
        ConfigProfile.HYSTERIA2,
        name="Office",
        previous=PreviousSecrets(
            password=first.config_data["auth"]["password"],
            obfs_password=first.config_data["obfs"]["salamander"]["password"],
            private_key=first.private_key,
            public_key=first.public_key,
            cert_fingerprint=first.cert_fingerprint,
        ),
    )
    assert second.extra_files == {}
    assert second.config_data["tls"]["cert"] == str(cert_path)
    assert list(tmp_path.glob("*-cert*.pem")) == [] or True
    assert cert_path.read_text(encoding="utf-8") == cert_pem


def test_rotate_tls_ignores_profile_le_paths(panel_settings, tmp_path) -> None:
    private_pem, cert_pem, _fingerprint = generate_self_signed_cert(dns_names=["learn.example.test"])
    cert_path = tmp_path / "fullchain.pem"
    key_path = tmp_path / "privkey.pem"
    cert_path.write_text(cert_pem, encoding="utf-8")
    key_path.write_text(private_pem, encoding="utf-8")

    profiles = dict(panel_settings.vpn.profiles)
    profiles["xray-xhttp"] = profiles["xray-xhttp"].model_copy(
        update={
            "tls_cert_file": cert_path,
            "tls_key_file": key_path,
            "share_public_host": "learn.example.test",
            "cert_dir": tmp_path / "certs",
        },
    )
    settings = panel_settings.model_copy(
        update={"vpn": panel_settings.vpn.model_copy(update={"profiles": profiles})},
    )
    builder = ProfileConfigBuilder(settings)
    le = builder.build(
        ConfigProfile.XRAY_XHTTP,
        name="LeCfg",
        policy=RegeneratePolicy.for_profile(
            ConfigProfile.XRAY_XHTTP,
            profiles["xray-xhttp"],
        ),
    )
    assert le.extra_files == {}
    assert le.config_data["inbounds"][0]["streamSettings"]["tlsSettings"]["certificates"][0][
        "certificateFile"
    ] == str(cert_path)

    self_signed = builder.build(
        ConfigProfile.XRAY_XHTTP,
        name="SelfSigned",
        policy=RegeneratePolicy(rotate_tls=True, rotate_path=True, rotate_client_id=True),
    )
    assert self_signed.extra_files
    assert "cert" in self_signed.extra_files
    assert self_signed.cert_fingerprint != le.cert_fingerprint
    cert_file = self_signed.config_data["inbounds"][0]["streamSettings"]["tlsSettings"]["certificates"][0][
        "certificateFile"
    ]
    assert str(cert_path) not in cert_file


@pytest.mark.asyncio
@patch("panel.api.routers.configs.HttpBrokerClient")
async def test_create_config_stores_regenerate_policy(
    mock_broker_cls: AsyncMock,
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    db_engine: AsyncEngine,
) -> None:
    mock_broker = AsyncMock()
    mock_broker.publish_task.return_value = PublishedTask(task_id="task-policy-1")
    mock_broker.close = AsyncMock()
    mock_broker_cls.return_value = mock_broker

    response = await api_client.post(
        "/api/v1/configs",
        headers=auth_headers,
        json={
            "name": "PolicyCfg",
            "protocol": "xray",
            "profile": "xray-reality",
            "share_public_host": "auth.example.com",
            "regenerate_policy": {
                "rotate_port": False,
                "rotate_short_ids": False,
                "rotate_dest": True,
            },
        },
    )
    assert response.status_code == 202
    config_id = uuid.UUID(response.json()["config_id"])

    async with create_session_factory(db_engine)() as session:
        result = await session.execute(select(VpnConfigModel).where(VpnConfigModel.id == config_id))
        model = result.scalar_one()
        assert model.regenerate_policy is not None
        assert model.regenerate_policy["rotate_port"] is False
        assert model.regenerate_policy["rotate_short_ids"] is False
        assert model.regenerate_policy["rotate_dest"] is True
        assert model.regenerate_policy["rotate_client_id"] is True
        assert model.share_public_host == "auth.example.com"


@pytest.mark.asyncio
async def test_patch_regenerate_policy(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_config: uuid.UUID,
    db_engine: AsyncEngine,
) -> None:
    response = await api_client.patch(
        f"/api/v1/configs/{sample_config}/regenerate-policy",
        headers=auth_headers,
        json={"regenerate_policy": {"rotate_port": False, "rotate_dest": False}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["regenerate_policy"]["rotate_port"] is False
    assert body["regenerate_policy"]["rotate_dest"] is False

    async with create_session_factory(db_engine)() as session:
        result = await session.execute(select(VpnConfigModel).where(VpnConfigModel.id == sample_config))
        model = result.scalar_one()
        assert model.regenerate_policy["rotate_port"] is False
        assert model.regenerate_policy["rotate_dest"] is False
