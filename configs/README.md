# Шаблоны VPN-конфигов

Каталог используется воркером как `paths.templates` в `panel.yaml`.

| Файл | Профиль | Описание |
|------|---------|----------|
| `config_reality.json` | `xray-reality` | VLESS + Reality inbound |
| `config_grpc.json` | `xray-grpc` | VLESS + gRPC/TLS |
| `config_xhttp.json` | `xray-xhttp` | VLESS + xHTTP/TLS (self-signed) |
| `hysteria.server.yaml` | `hysteria2` | Hysteria2 server |

Динамические шаблоны (reality / grpc / xhttp) содержат inbound панели и outbound `client-in-loop` — SOCKS на `127.0.0.1:51820`. Локальная петля с балансировщиком и upstream-outbound **настраивается на сервере вручную**, панель ею не управляет.

При **create/regenerate** воркер:

- загружает шаблон;
- подставляет port, keys, client UUID, shortIds / Reality dest+serverNames, gRPC SNI/serviceName, Hysteria obfs и т.д.;
- пишет итог в `{paths.configs}/{config_id}/`;
- при `systemd.per_config: true` — live-конфиг в `/usr/local/etc/xray/configs/{config_id}/` и unit `vpn-{config_id}.service`;
- при `systemd.per_config: false` и заданном `active_config_path` — в путь из профиля (legacy).

**Legacy:** `active_config_path` должен совпадать с `-config` в unit-файле VPN-сервиса.

Перед production настройте шаблоны под свой сервер: routing, `dest`/`serverNames`, пути к сертификатам, порт SOCKS-петли в `client-in-loop` (если не 51820).

Самоподписанные сертификаты (gRPC / xHTTP / Hysteria2) выпускаются с DNS SAN = `vpn.public_host` (например `chevg.ignorelist.com`) и хранятся per-config рядом с live-конфигом. SNI для xHTTP/Hysteria совпадает с этим именем; gRPC по-прежнему может брать SNI из `grpc_sni_hosts`. Secure share отдаёт fingerprint (`pinSHA256` / `pcs`) для клиентов без `insecure`.
