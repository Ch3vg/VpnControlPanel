from __future__ import annotations

from panel.infrastructure.vpn.nginx_shared_443 import (
    panel_sni_hosts,
    reality_sni_hosts,
    render_shared_443_stream_conf,
    shared_443_enabled,
    sync_reality_shared_443,
)


def test_shared_443_enabled() -> None:
    from panel.config import VpnProfileSettings

    base = {
        "template_file": "x.json",
        "service_name": "x",
        "config_filename": "config.json",
    }
    assert not shared_443_enabled(VpnProfileSettings(**base))
    assert not shared_443_enabled(
        VpnProfileSettings(**base, share_public_port=443),
    )
    assert shared_443_enabled(
        VpnProfileSettings(**base, share_public_port=443, listen_address="127.0.0.1"),
    )


def test_render_shared_443_stream_conf() -> None:
    text = render_shared_443_stream_conf(
        panel_snis=["panel.example.com", "legacy.example.com"],
        panel_backend="127.0.0.1:8443",
        routes=[
            ("ya.ru", "127.0.0.1:2083"),
            ("panel.example.com", "127.0.0.1:2083"),
            ("vk.com", "127.0.0.1:2083"),
        ],
    )
    assert "panel.example.com 127.0.0.1:8443;" in text
    assert "legacy.example.com 127.0.0.1:8443;" in text
    assert "ya.ru 127.0.0.1:2083;" in text
    assert "vk.com 127.0.0.1:2083;" in text
    # Panel SNI must not be routed to Reality even if listed.
    assert "panel.example.com 127.0.0.1:2083;" not in text
    assert "proxy_pass $vcp_443_backend;" in text
    assert "ssl_preread on;" in text


def test_panel_sni_hosts_includes_aliases(panel_settings) -> None:
    panel_settings.vpn.public_host = "learn.example.com"
    panel_settings.vpn.public_host_aliases = ["old.example.com", "learn.example.com", ""]
    assert panel_sni_hosts(panel_settings) == ["learn.example.com", "old.example.com"]


def test_reality_sni_hosts_from_dest_and_config() -> None:
    from panel.config import VpnProfileSettings

    profile = VpnProfileSettings(
        template_file="x.json",
        service_name="x",
        config_filename="config.json",
        inbound_tag="inbound-reality",
        reality_dest_hosts=["ya.ru:443", "vk.com:443"],
    )
    config = {
        "inbounds": [
            {
                "tag": "inbound-reality",
                "port": 2083,
                "listen": "127.0.0.1",
                "streamSettings": {
                    "realitySettings": {
                        "dest": "pochta.ru:443",
                        "serverNames": ["pochta.ru"],
                    },
                },
            },
        ],
    }
    hosts = reality_sni_hosts(profile, config)
    assert hosts == ["pochta.ru", "vk.com", "ya.ru"]


def test_sync_reality_shared_443_writes_and_reloads(panel_settings, monkeypatch) -> None:
    profile = panel_settings.vpn.profiles["xray-reality"]
    panel_settings.vpn.profiles["xray-reality"] = profile.model_copy(
        update={
            "share_public_port": 443,
            "listen_address": "127.0.0.1",
            "inbound_tag": "inbound-reality",
            "reality_dest_hosts": ["ya.ru:443"],
        },
    )
    panel_settings.vpn.public_host = "panel.example.com"
    panel_settings.vpn.public_host_aliases = ["legacy.example.com"]

    calls: list[tuple] = []

    def fake_run(action: str, service_name: str | None = None, *, input_text: str | None = None) -> None:
        calls.append((action, service_name, input_text))

    monkeypatch.setattr("panel.infrastructure.vpn.nginx_shared_443.run_systemctl", fake_run)

    config = {
        "inbounds": [
            {
                "tag": "inbound-reality",
                "port": 2083,
                "listen": "127.0.0.1",
                "streamSettings": {
                    "realitySettings": {
                        "dest": "ya.ru:443",
                        "serverNames": ["ya.ru"],
                    },
                },
            },
        ],
    }
    sync_reality_shared_443(panel_settings, config)

    assert len(calls) == 2
    assert calls[0][0] == "write-nginx-stream"
    body = calls[0][2] or ""
    assert "panel.example.com 127.0.0.1:8443;" in body
    assert "legacy.example.com 127.0.0.1:8443;" in body
    assert "ya.ru 127.0.0.1:2083;" in body
    assert calls[1] == ("reload-nginx", None, None)


def test_sync_reality_shared_443_noop_without_mux(panel_settings, monkeypatch) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(
        "panel.infrastructure.vpn.nginx_shared_443.run_systemctl",
        lambda *a, **k: calls.append((a, k)),
    )
    sync_reality_shared_443(panel_settings, {"inbounds": []})
    assert calls == []
