# VPN Control Panel

Веб-панель для администрирования серверных VPN-конфигураций (Xray и Hysteria2).

**v0.2.0** — REST API + **admin UI** (`/admin`), worker, шаблоны конфигов.

---

## Обзор

Панель решает проблему ручного редактирования конфигов и генерации ключей: **REST API** с JWT и **веб-интерфейс** `/admin` для админов.

Ключевые принципы:

- **Тяжёлые операции асинхронны** — генерация ключей, запись файлов, reload VPN-сервисов выполняются воркером через брокер задач. API сразу возвращает `task_id`.
- **Секреты только в воркере** — панель публикует в брокер metadata без VPN-ключей; воркер генерирует, шифрует и сохраняет в БД приложения.
- **Версионирование конфигов** — share-ссылки привязаны к конкретной версии и не ломаются при regenerate.
- **Луковая архитектура** — domain → application → infrastructure; HTTP-слои тонкие.

---

## Компоненты

Три независимых процесса, два конфигурационных файла:

```
┌─────────────────────┐     publish/status      ┌─────────────────────┐
│  panel/api  :8000   │ ───────────────────────►│  broker/   :8001    │
│  JWT, CRUD, share   │                         │  task-broker lib    │
└──────────┬──────────┘                         └──────────┬──────────┘
           │                                               │
           │ PostgreSQL (app)                              │ SQLite/PG (queue)
           │                                               │
┌──────────▼──────────┐     pull/ack/nack/heartbeat      │
│  panel/worker         │ ◄────────────────────────────────┘
│  keys, files, reload  │
└───────────────────────┘
```

| Процесс | Entrypoint | Конфиг | Назначение |
|---------|------------|--------|------------|
| `vpn-broker` | `broker_run/main.py` | `broker.yaml` | HTTP-брокер задач (пакет `task-broker`) |
| `vpn-api` | `panel/api/main.py` | `panel.yaml` | Admin API, публичный `/share/{token}` |
| `vpn-worker` | `panel/worker/main.py` | `panel.yaml` | Потребитель задач, side effects |

---

## Структура проекта

```
VpnControlPanel/
├── broker_run/                   # запуск task-broker (не broker/ — конфликт имён с библиотекой)
│   ├── main.py
│   └── config.py
├── broker.yaml.example
│
├── panel/
│   ├── api/                      # FastAPI backend
│   │   ├── main.py
│   │   ├── routers/
│   │   ├── schemas/
│   │   └── deps.py
│   │
│   ├── domain/                   # сущности, value objects, порты
│   │   ├── entities/
│   │   ├── value_objects/
│   │   └── ports/
│   │
│   ├── application/              # use cases
│   │   ├── create_config.py
│   │   ├── regenerate_config.py
│   │   ├── create_share_link.py
│   │   └── resolve_share.py
│   │
│   ├── infrastructure/           # реализации портов
│   │   ├── persistence/
│   │   ├── broker/               # HTTP-клиент к брокеру
│   │   ├── crypto/
│   │   ├── vpn/                  # profiles, config_builder, templates
│   │   └── filesystem/
│   │
│   ├── worker/
│   │   ├── main.py               # pull loop + heartbeat
│   │   └── handlers/
│   │       ├── config_initialize.py
│   │       └── config_regenerate.py
│   │
│   ├── web/                      # admin UI (SPA, /admin)
│   │   ├── index.html
│   │   └── static/
│   │
│   └── config.py                 # загрузка panel.yaml
│
├── configs/                      # шаблоны Xray/Hysteria2 (см. configs/README.md)
├── deploy/                       # production-деплой (шаблоны, scripts, Makefile)
├── docs/
│   └── DEPLOY.md                 # инструкция по деплою
├── panel.yaml.example
│
├── alembic/
├── tests/
└── pyproject.toml
```

### Зависимости между слоями

```
domain          ← ни от кого
application     ← domain
infrastructure  ← application, domain
panel/api       ← application (+ infrastructure через DI)
panel/worker    ← application (+ infrastructure через DI)
broker_run/       ← task-broker (внешняя библиотека), broker.yaml (локально)
```

---

## Архитектурные решения

### Генерация ключей и сертификатов

Только **воркер**. Панель при `POST /configs` создаёт запись со `status=pending` и публикует задачу. Payload задачи не содержит секретов.

### Жизненный цикл конфига

```
pending → processing → active
              ↓
           failed
```

Поля на `vpn_configs`: `status`, `last_task_id`, `error_message`, `current_version`.

### Версионирование

Две таблицы:

- **`vpn_configs`** — метаданные (name, protocol, status, is_active, audit fields).
- **`vpn_config_versions`** — immutable снимки: port, keys, config_data, version number.

При regenerate создаётся новая строка в `vpn_config_versions`. Share-ссылки ссылаются на `(config_id, config_version)`.

### Протоколы (Strategy)

Абстрактный класс `VpnProtocol` в `domain/ports/`:

```python
class VpnProtocol(ABC):
    def generate_keys(self) -> KeyPair: ...
    def build_config(self, params) -> dict: ...
    def sensitive_fields(self) -> list[str]: ...
    def write_files(self, config, path) -> None: ...
    def build_client_uris(self, config) -> list[str]: ...
    def reload_service(self) -> None: ...
```

Реализации: `infrastructure/vpn/xray.py`, `infrastructure/vpn/hysteria2.py`.

### Идемпотентность задач

В брокере нет `idempotency_key`. Воркер перед генерацией проверяет: если `vpn_config_versions` с `target_version` уже существует — завершает задачу без повторной работы.

---

## Модели данных (PostgreSQL)

### `users`

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | UUID PK | |
| username | TEXT UNIQUE | |
| password_hash | TEXT | bcrypt |
| created_at | TIMESTAMPTZ | |

Ролевая модель не планируется — все пользователи равноправные админы.

### `vpn_configs`

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | UUID PK | |
| name | TEXT | |
| protocol | TEXT | `xray` \| `hysteria2` |
| status | TEXT | `pending`, `processing`, `active`, `failed` |
| current_version | INTEGER | последняя успешная версия (NULL до первой) |
| last_task_id | TEXT | ID задачи в брокере |
| error_message | TEXT | при `failed` |
| is_active | BOOLEAN | мягкое удаление |
| created_by | UUID FK → users | |
| updated_by | UUID FK → users | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### `vpn_config_versions`

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | UUID PK | |
| config_id | UUID FK → vpn_configs | |
| version | INTEGER | уникально в рамках config_id |
| port | INTEGER | |
| private_key | TEXT | зашифрован на уровне приложения |
| public_key | TEXT | |
| cert_fingerprint | TEXT | |
| config_data | JSONB | чувствительные поля внутри JSON тоже шифруются |
| created_at | TIMESTAMPTZ | |

### `share_tokens`

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | UUID PK | |
| token_hash | TEXT UNIQUE | SHA-256 от raw token |
| config_id | UUID FK | |
| config_version | INTEGER | snapshot версии |
| is_permanent | BOOLEAN | |
| expires_at | TIMESTAMPTZ | NULL для постоянных |
| revoked_at | TIMESTAMPTZ | |
| created_by | UUID FK | |
| created_at | TIMESTAMPTZ | |
| last_accessed_at | TIMESTAMPTZ | |
| access_count | INTEGER | |

Raw token возвращается админу **один раз** при создании; в БД хранится только hash.

### `rate_limit_entries`

Rate limiting без Redis — через Postgres (fixed window).

| Колонка | Тип | Описание |
|---------|-----|----------|
| key | TEXT | `login:ip:...` или `share:ip:...` |
| window_start | TIMESTAMPTZ | |
| count | INTEGER | |

### `audit_logs`

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | UUID PK | |
| user_id | UUID FK | NULL для failed login |
| event_type | TEXT | |
| payload | JSONB | без секретов |
| created_at | TIMESTAMPTZ | |

Append-only. События `share.accessed` не пишутся на каждый GET — только агрегаты в `share_tokens`.

---

## API

> Все эндпоинты, кроме `/share/{token}` и `/health`, требуют JWT (`Authorization: Bearer <token>`).

### Авторизация

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/auth/login` | username/password → JWT |

### Конфиги

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/v1/configs` | Список (пагинация, фильтр по protocol) |
| POST | `/api/v1/configs` | Создать → `202 {task_id}` (`profile`: `xray-reality`, `xray-grpc`, …) |
| GET | `/api/v1/configs/{id}` | Детали + текущая версия |
| POST | `/api/v1/configs/{id}/regenerate` | Regenerate → `202 {task_id}` |
| GET | `/api/v1/configs/{id}/status` | Статус последней задачи |
| DELETE | `/api/v1/configs/{id}` | Soft delete |

### Share-ссылки

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| POST | `/api/v1/configs/{id}/share` | JWT | Создать ссылку |
| DELETE | `/api/v1/share/{token}` | JWT | Отозвать |
| GET | `/share/{token}` | — | Публичный: список client URI |

Пример ответа `/share/{token}`:

```json
[
  "vless://...@...",
  "hysteria2://...@..."
]
```

---

## Интеграция с брокером

Зависимость `task-broker` объявляется в `pyproject.toml` и устанавливается через pip.  
Библиотека экспортирует `from broker import Broker`. Каталог `broker_run/` — тонкая обёртка для запуска.

### Типы задач

| task_type | Когда |
|-----------|-------|
| `config.initialize` | POST /configs |
| `config.regenerate` | POST /configs/{id}/regenerate |

### Payload (без секретов)

```json
{
  "config_id": "uuid",
  "protocol": "xray",
  "name": "Office",
  "requested_by": "user_uuid",
  "target_version": 1
}
```

### Маппинг BrokerPort → HTTP

| Метод порта | HTTP брокера |
|-------------|--------------|
| `publish_task` | `POST /api/v1/tasks` |
| `get_status` | `GET /api/v1/tasks/{id}/status` |
| `pull` | `GET /api/v1/tasks/pull` |
| `heartbeat` | `POST /api/v1/tasks/{id}/heartbeat` |
| `ack` | `POST /api/v1/tasks/{id}/ack` |
| `nack` | `POST /api/v1/tasks/{id}/nack` |

### Аутентификация

Один `api_key` для panel и worker (`Authorization: Bearer <key>`).  
mTLS планируется в брокере позже — схема HTTP API не изменится.

### Heartbeat

Интервал: `lock_ttl_seconds / 3`. Рекомендуемый `lock_ttl`: 180–300 с (генерация сертификатов).

### Поток create config

```
1. API: INSERT vpn_configs (status=pending)
2. API: POST /api/v1/tasks → task_id
3. API: UPDATE last_task_id → 202
4. Worker: pull → processing
5. Worker: generate keys → INSERT vpn_config_versions
6. Worker: write files → systemctl reload
7. Worker: ack → status=active
```

---

## Безопасность

### Шифрование в БД

- `SECRET_KEY` — только JWT.
- `ENCRYPTION_KEY` — шифрование `private_key` и sensitive paths в `config_data` (AES-256-GCM / Fernet).
- Весь `config_data` целиком **не** шифруется.
- Список sensitive paths определяет `VpnProtocol.sensitive_fields()`.

### JWT

- HS256, TTL 60 мин (настраивается).
- Refresh tokens — не в MVP.

### Share endpoint

- Token: `secrets.token_urlsafe(32)` → SHA-256 hash в БД.
- Любая ошибка валидации → `404` с единым сообщением.
- `Cache-Control: no-store`.
- CORS не настраивается (deeplink для VPN-клиентов).
- Rate limit: 30 req/min per IP (Postgres).

### Login

- bcrypt, единый ответ при неверном user/password.
- Rate limit: 5 попыток / 15 мин per IP.
- `auth.login.failed` в audit — включается флагом `audit.log_failed_login`.

### Воркер

- Не слушает входящие HTTP-соединения.
- OS-пользователь с минимальными правами.
- `systemctl reload` через sudoers (без `shell=True`).
- Запись файлов: temp → atomic rename (`os.replace`).

### Admin UI (v0.2.0)

| URL | Описание |
|-----|----------|
| `/admin` | SPA: login, список конфигов, карточка конфига |
| `/admin/static/*` | CSS/JS без сборки (vanilla ES modules) |

JWT хранится в `sessionStorage`. Отключение: `web.enabled: false` в `panel.yaml`.

Экраны:
- **Login** — `/auth/login`
- **Список** — фильтр по protocol, создание конфига (name + protocol + profile)
- **Детали** — polling статуса, regenerate, share-ссылка, revoke, delete

### Swagger / OpenAPI

| `app.max_secure` | Поведение |
|------------------|-----------|
| `false` | `/docs` доступен только с JWT |
| `true` | Swagger не монтируется |

### Fail-fast при старте

- `secret_key` / `encryption_key` — не дефолтные, длина ≥ 32.
- `encryption_key` ≠ `secret_key`.

### TLS

HTTP допустим на этапе разработки (нет домена). HTTPS — при появлении домена / reverse proxy.

---

## Конфигурация

### `broker.yaml` (только брокер)

```yaml
server:
  host: "127.0.0.1"
  port: 8001

database:
  dsn: "sqlite+aiosqlite:///./data/broker.db"

queue:
  default_lock_ttl_seconds: 180
  default_max_retries: 3
  retry_delay_seconds: 10
  default_pull_timeout_seconds: 30
  pull_interval_seconds: 1

security:
  api_key: "..."   # один ключ для panel + worker

logging:
  level: INFO
```

### `panel.yaml` (API + worker)

```yaml
app:
  name: vpn-control-panel
  max_secure: false
  environment: development

server:
  host: "0.0.0.0"
  port: 8000

database:
  url: "postgresql+asyncpg://user:pass@localhost/panel"

security:
  secret_key: "..."
  encryption_key: "..."
  jwt_algorithm: HS256
  jwt_expire_minutes: 60

broker:
  url: "http://127.0.0.1:8001"
  api_key: "..."
  # mtls:                         # когда будет готово в брокере
  #   ca_file: ...
  #   cert_file: ...
  #   key_file: ...

worker:
  worker_id: "panel-worker-1"
  task_types:
    - config.initialize
    - config.regenerate

paths:
  configs: "/opt/vpn/configs"
  templates: "configs"

rate_limit:
  login:
    max_attempts: 5
    window_seconds: 900
  share:
    max_requests: 30
    window_seconds: 60

audit:
  enabled: true
  log_failed_login: true

metrics:
  enabled: true

security_headers:
  enabled: true

web:
  enabled: true
  mount_path: /admin

vpn:
  public_host: "vpn.example.com"
  profiles:
    xray-reality:
      template_file: config_reality.json
      service_name: xray_reality
      config_filename: config.json
      inbound_tag: vless-reality-in
      port_candidates: [443, 8443, 2053]
    hysteria2:
      template_file: hysteria.server.yaml
      service_name: hysteria-server
      config_filename: config.yaml
      port_candidates: [443, 8443]
      cert_dir: /usr/local/etc/xray/certs
      cert_prefix: hysteria

telegram:
  enabled: false
  bot_token: ""
  chat_id: ""
```

Панель **не читает** `broker.yaml`. Брокер **не знает** о панели.

---

## Деплой (production)

Полная инструкция: **[docs/DEPLOY.md](docs/DEPLOY.md)**

```bash
make init-env    # cp deploy/env.example deploy/.env
# задайте VCP_TASK_BROKER_WHL и домены
make deploy      # sudo, Debian/Ubuntu
make update      # sudo, после git pull
```

---

## Запуск (разработка)

```bash
# task-broker не в PyPI — установите wheel отдельно (не входит в репозиторий)
pip install /path/to/task_broker-*.whl

cp panel.yaml.example panel.yaml
cp broker.yaml.example broker.yaml
# отредактируйте секреты и пути; шаблоны — каталог configs/

pip install -e ".[dev]"

# БД панели
alembic upgrade head

# Первый админ
vpn-create-admin --config panel.yaml --username admin

# Три терминала:
vpn-broker --config broker.yaml
vpn-api --config panel.yaml
vpn-worker --config panel.yaml
```

---

## Тестирование

```bash
pytest tests/
```

Покрытие:

- domain и application (unit)
- API с моком брокера
- protocol strategies
- share / rate limit / audit
- worker handlers (integration)

---

## Дорожная карта реализации

| Этап | Содержание |
|------|------------|
| 0 | Каркас: pyproject.toml, конфиги, структура пакетов, health |
| 1 | Auth: users, JWT, login, rate limit |
| 2 | Модели БД, миграции, GET/DELETE configs |
| 3 | Broker client, worker pull loop, `config.initialize` |
| 4 | `config.regenerate`, версионирование |
| 5 | Share links, публичный endpoint |
| 6 | Audit, метрики, hardening |

---

## Расширение

### Новый тип задачи

1. Handler в `panel/worker/handlers/`.
2. Регистрация в worker dispatch table.
3. Use case в API публикует задачу с новым `task_type`.

### Новый VPN-протокол

1. Реализация `VpnProtocol` в `infrastructure/vpn/`.
2. Регистрация в factory.
3. Добавить protocol в валидацию API.

### Замена брокера

Реализовать `BrokerPort` заново (HTTP-клиент к другому backend). Application layer не меняется.

---

## Лицензия

[MIT](LICENSE)
