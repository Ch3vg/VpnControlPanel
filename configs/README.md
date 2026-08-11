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
- подставляет port, keys, client UUID, shortIds / Reality dest+`serverNames`(=hostname dest), gRPC SNI/serviceName, xHTTP host=SNI=`public_host` + mode `stream-up`, Hysteria obfs и т.д.;
- пишет итог в `{paths.configs}/{config_id}/`;
- при `systemd.per_config: true` — live-конфиг в `/usr/local/etc/xray/configs/{config_id}/` и unit `vpn-{config_id}.service`;
- при `systemd.per_config: false` и заданном `active_config_path` — в путь из профиля (legacy).

**Legacy:** `active_config_path` должен совпадать с `-config` в unit-файле VPN-сервиса.

Перед production настройте шаблоны под свой сервер: routing, `reality_dest_hosts` (только хосты, **достижимые с VPS**), пути к сертификатам, порт SOCKS-петли в `client-in-loop` (если не 51820). Reality на non-443 легче замечает ТСПУ — по возможности слушайте `:443`.

Самоподписанные сертификаты (gRPC / xHTTP / Hysteria2) выпускаются с DNS SAN = `vpn.public_host` (например `chevg.ignorelist.com`) и хранятся per-config рядом с live-конфигом. У xHTTP HTTP Host совпадает с этим SNI (чужой Host + self-signed SNI — маркер DPI). gRPC по-прежнему может брать SNI из `grpc_sni_hosts`. Secure share отдаёт fingerprint (`pinSHA256` / `pcs`) для клиентов без `insecure`.
