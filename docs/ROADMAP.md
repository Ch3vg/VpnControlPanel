# Roadmap

Идеи и отложенные улучшения. Не обязательства по срокам.

## Сделано недавно

### Per-config regenerate policy

При создании VPN-конфига задаётся `regenerate_policy` (БД + UI create): какие параметры ротируются на последующих regenerate. Builder/worker читают policy; для TLS-профилей стабильный LE через `tls_cert_file` / `tls_key_file` в профиле.

### Редактор шаблонов профилей

В UI (Обзор → Шаблоны) и API `GET/PUT /api/v1/templates` можно править файлы шаблонов (`configs/config_*.json`, `hysteria.server.yaml`). Изменения влияют на новые create/regenerate, не на уже развёрнутые конфиги до regenerate.

### Логи конфига в UI

На странице конфига — хвост journald unit `vpn-{id}` через polling `GET /api/v1/configs/{id}/logs` (`vpn-systemctl logs`).

## Идеи (бэклог)

- Массовый PATCH `regenerate_policy` у уже созданных конфигов
- Автоподстановка LE-путей в профили с `share_public_host` без явных `tls_*_file`
- Доп. SNI backends в mux из UI (не только regenerate Reality/xHTTP)
