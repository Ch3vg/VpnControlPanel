# Roadmap

Идеи и отложенные улучшения. Не обязательства по срокам.

## Планируется

### Per-config regenerate policy (при создании конфига)

При **создании** VPN-конфига задавать, какие параметры будут ротироваться при последующих regenerate — гибкость на уровне экземпляра, а не только профиля в `panel.yaml`.

Примеры флагов (черновик):

- порт
- Reality: `shortIds`, `dest` / `serverNames`
- xHTTP: `path`
- gRPC: `serviceName`
- TLS: перевыпуск self-signed vs сохранить внешний LE
- Hysteria: auth / obfs (по умолчанию сохранять)

Сохранять в метаданных конфига (БД); UI create + API; builder читает policy при regenerate.  
Секреты клиента (UUID, Reality keypair, пароли) по умолчанию **не** ротировать, если явно не включено.

Связано с текущей схемой shared-443 + LE на своих доменах: для xHTTP/gRPC/Hysteria часто нужен стабильный LE, для Reality — ротация dest/shortIds.

## Идеи (бэклог)

- Автоподстановка LE-путей в профили с `share_public_host` без ручного overlay после regenerate
- Доп. SNI backends в mux из UI (не только regenerate Reality/xHTTP)
