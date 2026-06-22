from __future__ import annotations

from panel.config import OutboundVlessSettings
from panel.domain.value_objects.config_profile import ConfigProfile
from panel.infrastructure.vpn.config_builder import PreviousSecrets, ProfileConfigBuilder
from panel.infrastructure.vpn.template_loader import apply_outbound_secrets


STATIC_GRPC_OUT_ID = "aaaaaaaa-bbbb-4ccc-dddd-eeeeeeeeeeee"


def _grpc_out_user_id(config_data: dict) -> str:
    for outbound in config_data.get("outbounds", []):
        if outbound.get("tag") != "grpc-out":
            continue
        return outbound["settings"]["vnext"][0]["users"][0]["id"]
    raise AssertionError("grpc-out not found")


def test_apply_outbound_secrets_sets_vless_user_id() -> None:
    config = {
        "outbounds": [
            {
                "tag": "grpc-out",
                "protocol": "vless",
                "settings": {"vnext": [{"users": [{"id": "placeholder"}]}]},
            },
        ],
    }
    apply_outbound_secrets(
        config,
        {"grpc-out": OutboundVlessSettings(user_id=STATIC_GRPC_OUT_ID)},
    )
    assert _grpc_out_user_id(config) == STATIC_GRPC_OUT_ID


def test_grpc_out_secret_static_on_regenerate(panel_settings) -> None:
    vpn = panel_settings.vpn.model_copy(
        update={
            "outbound_secrets": {
                "grpc-out": OutboundVlessSettings(user_id=STATIC_GRPC_OUT_ID),
            },
        },
    )
    settings = panel_settings.model_copy(update={"vpn": vpn})
    builder = ProfileConfigBuilder(settings)

    first = builder.build(ConfigProfile.XRAY_GRPC, name="Office")
    second = builder.build(
        ConfigProfile.XRAY_GRPC,
        name="Office",
        previous=PreviousSecrets(
            client_id=first.client_id,
            private_key=first.private_key,
            public_key=first.public_key,
            cert_fingerprint=first.cert_fingerprint,
        ),
    )

    assert first.client_id != STATIC_GRPC_OUT_ID
    assert second.client_id == first.client_id
    assert _grpc_out_user_id(first.config_data) == STATIC_GRPC_OUT_ID
    assert _grpc_out_user_id(second.config_data) == STATIC_GRPC_OUT_ID


def test_inbound_client_id_not_copied_to_grpc_out_without_secrets(panel_settings) -> None:
    settings = panel_settings.model_copy(
        update={"vpn": panel_settings.vpn.model_copy(update={"outbound_secrets": {}})},
    )
    builder = ProfileConfigBuilder(settings)
    result = builder.build(ConfigProfile.XRAY_GRPC, name="Office")

    inbound_id = result.config_data["inbounds"][0]["settings"]["clients"][0]["id"]
    grpc_out_id = _grpc_out_user_id(result.config_data)
    assert inbound_id == result.client_id
    assert grpc_out_id != inbound_id
    assert grpc_out_id == "00000000-0000-4000-8000-000000000001"
