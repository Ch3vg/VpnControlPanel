# Шаблоны VPN-конфигов

Каталог используется воркером как `paths.templates` в `panel.yaml`.

| Файл | Профиль | Описание |
|------|---------|----------|
| `config_reality.json` | `xray-reality` | VLESS + Reality inbound |
| `config_grpc.json` | `xray-grpc` | VLESS + gRPC/TLS |
| `config_xhttp.json` | `xray-xhttp` | VLESS + xHTTP |
| `hysteria.server.yaml` | `hysteria2` | Hysteria2 server |

Динамические шаблоны (reality / grpc / xhttp) содержат inbound панели и outbound `client-in-loop` — SOCKS на `127.0.0.1:51820`. Локальная петля с балансировщиком и upstream-outbound **настраивается на сервере вручную**, панель ею не управляет.

При **create/regenerate** воркер:

- загружает шаблон;
- подставляет port, keys, client UUID, shortIds (Reality), gRPC SNI и т.д.;
- пишет итог в `{paths.configs}/{config_id}/`;
- при `systemd.per_config: true` — live-конфиг в `/usr/local/etc/xray/configs/{config_id}/` и unit `vpn-{config_id}.service`;
- при `systemd.per_config: false` и заданном `active_config_path` — в путь из профиля (legacy).

**Legacy:** `active_config_path` должен совпадать с `-config` в unit-файле VPN-сервиса.

Перед production настройте шаблоны под свой сервер: routing, `dest`/`serverNames`, пути к сертификатам, порт SOCKS-петли в `client-in-loop` (если не 51820).
