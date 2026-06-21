# Шаблоны VPN-конфигов

Каталог используется воркером как `paths.templates` в `panel.yaml`.

| Файл | Профиль | Описание |
|------|---------|----------|
| `config_reality.json` | `xray-reality` | VLESS + Reality inbound |
| `config_grpc.json` | `xray-grpc` | VLESS + gRPC/TLS, cert/key — файлы на диске |
| `config_xhttp.json` | `xray-xhttp` | VLESS + xHTTP |
| `config_client_in.json` | `xray-client-in` | SOCKS inbound для цепочки |
| `hysteria.server.yaml` | `hysteria2` | Hysteria2 server |

При **create/regenerate** воркер:

- загружает шаблон;
- подставляет port, keys, client UUID, shortIds (Reality) и т.д.;
- обновляет `inboundTag` в `routing.rules`;
- пишет итог в `{paths.configs}/{config_id}/` (архив версии);
- при `systemd.per_config: true` — live-конфиг в `/usr/local/etc/xray/configs/{config_id}/` (или hysteria) и unit `vpn-{config_id}.service`;
- при `systemd.per_config: false` и заданном `active_config_path` — в путь из профиля (legacy, один конфиг на профиль).

**Legacy:** `active_config_path` должен совпадать с `-config` в unit-файле VPN-сервиса.

Перед production скопируйте шаблоны и настройте под свой сервер: outbounds, routing, `dest`/`serverNames`, пути к сертификатам, upstream-адреса. Значения в репозитории — **примеры** (TEST-NET IP, placeholder keys).
