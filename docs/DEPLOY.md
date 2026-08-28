# Деплой VPN Control Panel

Production-деплой на **Debian/Ubuntu** с автоматизацией через `Makefile` и скрипты в `deploy/scripts/`.  
Актуальная версия панели: **1.1.0** (см. `pyproject.toml` / `panel.__version__`).

## Архитектура

```
Internet → Nginx (:80 HTTP) → vpn-api :8000
                              ↓
                         PostgreSQL
                              ↓
vpn-broker :8001 ← vpn-worker (файлы + systemctl restart)
     ↑
  SQLite queue
```

| Процесс | systemd unit | Пользователь |
|---------|--------------|--------------|
| Task broker | `vpn-broker` | `vpn-panel` |
| REST API + UI | `vpn-api` | `vpn-panel` |
| Worker | `vpn-worker` | `vpn-worker` |

---

## Быстрый старт

На **чистом сервере** (от root или через sudo):

```bash
git clone https://github.com/YOUR_ORG/VpnControlPanel.git /opt/vpn-control-panel
cd /opt/vpn-control-panel

make init-env
# отредактируйте deploy/.env:
#   VCP_TASK_BROKER_WHL=/path/to/task_broker-*.whl
#   VCP_PUBLIC_HOST, VCP_PANEL_DOMAIN
#   пути (по умолчанию уже под /opt)

make deploy
```

После деплоя:

- Admin UI: `https://<VCP_PANEL_DOMAIN>/admin`
- Health: `curl http://127.0.0.1:8000/health`

---

## Шаблоны и артефакты

```
deploy/
├── env.example                 # переменные окружения (копируется в .env)
├── templates/
│   ├── panel.yaml.in           # production panel.yaml
│   ├── broker.yaml.in          # broker.yaml
│   ├── systemd/
│   │   ├── vpn-broker.service.in
│   │   ├── vpn-api.service.in
│   │   └── vpn-worker@.service.in
│   ├── nginx/
│   │   ├── vpn-panel.conf.in           # HTTP :80
│   │   ├── vpn-panel.ssl.conf.in       # HTTPS public :443
│   │   ├── vpn-panel.shared443.conf.in # panel TLS on 127.0.0.1:8443
│   │   └── vcp-shared-443.stream.conf.in  # SNI mux on public :443
│   └── sudoers/
│       └── vpn-worker.in       # NOPASSWD systemctl restart
├── scripts/                    # шаги деплоя
└── output/                     # сгенерированные файлы (gitignore)
```

Рендер шаблонов: `envsubst` подставляет переменные из `deploy/.env`.

```bash
make render    # → deploy/output/
```

---

## Переменные (`deploy/.env`)

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `VCP_INSTALL_DIR` | Каталог приложения | `/opt/vpn-control-panel` |
| `VCP_CONFIG_DIR` | panel.yaml, broker.yaml | `/etc/vpn-control-panel` |
| `VCP_DATA_DIR` | SQLite брокера | `/var/lib/vpn-control-panel` |
| `VCP_VPN_CONFIGS_DIR` | Выход worker | `/opt/vpn/configs` |
| `VCP_CERT_DIR` | Сертификаты grpc/hysteria | `/usr/local/etc/xray/certs` |
| `VCP_PANEL_USER` | User API/broker | `vpn-panel` |
| `VCP_WORKER_USER` | User worker | `vpn-worker` |
| `VCP_WORKER_INSTANCES` | Число systemd-воркеров `vpn-worker@1..N` | `1` |
| `VCP_DB_*` | PostgreSQL | см. env.example |
| `VCP_JWT_SECRET` | JWT (≥32 символов) | auto `make secrets` |
| `VCP_ENCRYPTION_KEY` | Шифрование БД | auto |
| `VCP_BROKER_API_KEY` | API key брокера | auto |
| `VCP_TASK_BROKER_WHL` | Путь к wheel | **обязательно** |
| `VCP_PUBLIC_HOST` | IP/домен VPN-сервера | |
| `VCP_PANEL_DOMAIN` | Домен панели (nginx) | |
| `VCP_CONNECTIVITY_PROBE_ENABLED` | Реальная проверка VPN через клиент | `true` |
| `VCP_CONNECTIVITY_PROBE_TIMEOUT_SECONDS` | Таймаут probe (сек) | `12` |
| `VCP_CONNECTIVITY_PROBE_CACHE_SECONDS` | Кэш результата probe (сек) | `60` |
| `VCP_CONNECTIVITY_PROBE_URL` | URL для curl через SOCKS (лучше `.ru` — идёт в `direct-out`) | `https://ya.ru/` |
| `VCP_NGINX_SSL` | HTTPS :443 (`1`) или только HTTP :80 (`0`) | `0` |
| `VCP_NGINX_SHARED_443` | SNI mux: панель + Reality на TCP 443 | `0` |
| `VCP_REALITY_BACKEND` | Loopback Reality для mux | `127.0.0.1:10443` |
| `VCP_REALITY_SNI_LIST` | CSV SNI → Reality | `ya.ru,vk.com,...` |
| `VCP_PANEL_TLS_CERT` / `KEY` | Cert для panel на `:8443` при shared | LE paths |
| `VCP_ADMIN_USERNAME` | Первый админ | `admin` |

Секреты: `make secrets` генерирует пустые поля через `openssl rand`.

---

## Makefile — все цели

```bash
make help              # список команд
make init-env          # cp env.example → .env
make secrets           # сгенерировать секреты
make render            # шаблоны → deploy/output/

make deploy            # полный деплой (sudo)
make deploy-quick      # без apt, nginx, create-admin

make deploy-deps       # apt: python3, postgres, nginx, …
make deploy-users      # пользователи + каталоги
make deploy-db         # PostgreSQL role + DB
make install-app       # venv + pip install
make setup-config      # /etc/vpn-control-panel/*.yaml
make migrate           # alembic upgrade head
make create-admin      # vpn-create-admin (USERNAME=alice для доп. админов)
make regenerate-all    # очередь regenerate для всех active конфигов
make install-sudoers   # /etc/sudoers.d/vpn-worker
make install-systemd   # enable + start units
make install-nginx     # sites-available/vpn-panel.conf

make restart           # restart all services
make status            # systemctl status
make logs              # journalctl -f
make check-scripts     # bash -n syntax check
```

---

## Пошаговый деплой (вручную)

Если нужен контроль над каждым шагом:

```bash
make init-env
$EDITOR deploy/.env
make secrets

sudo make deploy-deps
sudo make deploy-users
sudo make deploy-db
sudo make install-app
sudo make setup-config
sudo make migrate
sudo make create-admin
sudo make install-sudoers
sudo make install-systemd
sudo make install-nginx   # опционально
```

---

## TLS (опционально, позже)

По умолчанию nginx слушает **только порт 80** без сертификатов (`VCP_NGINX_SSL=0`).

Admin UI: `http://<VCP_PANEL_DOMAIN>/admin`

Когда появятся сертификаты:

```bash
apt install certbot python3-certbot-nginx
certbot certonly --webroot -w /var/www/html -d panel.example.com

# в deploy/.env: VCP_NGINX_SSL=1
make render
sudo make install-nginx
```

Шаблон HTTPS: `deploy/templates/nginx/vpn-panel.ssl.conf.in` (redirect 80→443 + proxy на API).

### Shared TCP 443 (панель + Reality)

Один публичный **TCP 443**: nginx `stream` + `ssl_preread` по SNI.

| SNI | Куда |
|-----|------|
| `VCP_PANEL_DOMAIN` | `127.0.0.1:8443` (HTTPS панели) |
| имена из `VCP_REALITY_SNI_LIST` | `VCP_REALITY_BACKEND` (Reality passthrough) |
| default | панель |

В `deploy/.env`:

```bash
VCP_NGINX_SHARED_443=1
VCP_REALITY_BACKEND=127.0.0.1:10443
VCP_PANEL_TLS_BACKEND=127.0.0.1:8443
VCP_REALITY_SNI_LIST=ya.ru,vk.com,gosuslugi.ru,pochta.ru
VCP_PANEL_TLS_CERT=/etc/letsencrypt/live/panel.example.com/fullchain.pem
VCP_PANEL_TLS_KEY=/etc/letsencrypt/live/panel.example.com/privkey.pem
```

Требования:

1. Reality inbound: `listen: 127.0.0.1`, порт = backend (например `10443`) — **не** `0.0.0.0:443`.
2. В Reality `serverNames` **нет** домена панели; клиентский share `sni=` из dest (маскировка), **не** из `share_public_host`.
3. Клиенты Reality ходят на **`:443`** (публичный mux). В `panel.yaml` у профиля `xray-reality` задайте `share_public_port: 443` и `listen_address: "127.0.0.1"`. Опционально `share_public_host: auth.example.com` — только адрес в `vless://…@host:443` (удобный DNS); SNI по-прежнему dest (`ya.ru` и т.п.). Не путать с HTTP `sites-available`: Reality нельзя маршрутизировать по `server_name` своего домена — нужен stream mux по SNI dest.
4. Hysteria2 — **UDP** (не TCP mux). Отдельный hostname через `share_public_host` (например `hy.example.com`) и `port_candidates` с `443` для UDP/443 рядом с TCP/443 nginx.
5. Пакет `libnginx-mod-stream` (Ubuntu/Debian). Затем `make render && sudo bash deploy/scripts/install-nginx.sh`

После **create/regenerate** Reality worker сам переписывает `/etc/nginx/stream.d/vcp-shared-443.conf` (backend = текущий `listen:port`, SNI = dest/hostnames из профиля) и делает `nginx -t && reload` через `vpn-systemctl`. Ручной sync не нужен, пока в профиле заданы `share_public_port` + `listen_address`. Смена только `share_public_host` достаточно reload `vpn-api` — share URI собирается из профиля при выдаче, regenerate не обязателен.

Опционально в профиле: `share_public_host` (override `vpn.public_host` в share/TLS), `nginx_stream_conf`, `nginx_panel_backend` (по умолчанию `127.0.0.1:8443`).

### Стабильный Let’s Encrypt на regenerate

Для профилей с TLS (xHTTP / gRPC / Hysteria) укажите в профиле `panel.yaml` пути к LE:

```yaml
tls_cert_file: /etc/letsencrypt/live/example.com/fullchain.pem
tls_key_file: /etc/letsencrypt/live/example.com/privkey.pem
```

Тогда create/regenerate **по умолчанию** использует эти пути (`rotate_tls: false`). Если в политике конфига включить **Self-signed TLS (вместо LE профиля)** (`rotate_tls: true`), билдер игнорирует `tls_*_file` и пишет self-signed в каталог этого конфига (`…/configs/{id}/`). Так можно держать один LE-конфиг на `share_public_host` и отдельно self-signed на другом порту/режиме — но SNI mux на `:443` по одному hostname по-прежнему один backend (последний sync).

При **создании** конфига можно указать свой `share_public_host` (поддомен): он хранится в БД, используется в share URI и как TLS/SNI для xHTTP/gRPC/Hysteria; для Reality — только dial-адрес (`@host`), `sni=` остаётся dest. Mux пересобирает маршруты по **всем** live xHTTP/gRPC конфигам (разные host → разные backend).

Connectivity probe для mux-профилей (`share_public_port`) ходит **только** на `share_public_host` (per-config или профиля) и `share_public_port` — как клиент. Без fallback на `vpn.public_host` и без `127.0.0.1:internal`: иначе SNI всё равно попадёт в nginx map, а DNS share-хоста не проверяется (ложное «online»). Нет DNS у share-хоста → offline с `DNS failed for …`.

### Regenerate policy при создании

`POST /api/v1/configs` принимает опциональное `regenerate_policy` (флаги `rotate_port`, `rotate_client_id`, `rotate_reality_keys`, `rotate_short_ids`, `rotate_dest`, `rotate_path`, `rotate_service_name`, `rotate_tls`, `rotate_auth`, `rotate_obfs`). В админке — чекбоксы «При regenerate ротировать». Старые конфиги с `NULL` в БД используют дефолты `RegeneratePolicy.for_profile`.

Без нормального LE для панели ветка HTTPS на 443 (SNI панели) будет с self-signed (браузер предупредит); **HTTP :80 остаётся без редиректа и без сертификата**. Reality-ветка на 443 при этом работает.

---

## Worker и systemctl

Worker и API читают `panel.yaml` от пользователя `vpn-panel` (группа). Пользователь **`vpn-worker` добавлен в группу `vpn-panel`** и может читать конфиг при правах `640` на файле и `750` на каталоге.

Xray и Hysteria2 **не поддерживают** `systemctl reload` — worker вызывает **`restart`** (по умолчанию `VPN_SYSTEMCTL_ACTION=restart`).

```bash
VPN_SYSTEMCTL_CMD="sudo -n /bin/systemctl"
VPN_SYSTEMCTL_ACTION=restart
```

В `vpn-worker@.service`:

```ini
Environment=VPN_WORKER_INSTANCE=%i
Environment="VPN_SYSTEMCTL_CMD=sudo -n /usr/local/bin/vpn-systemctl"
Environment=VPN_SYSTEMCTL_ACTION=restart
```

Sudoers (`/etc/sudoers.d/vpn-worker`, `make install-sudoers`):

- `/usr/local/bin/vpn-systemctl` — per-config units `vpn-{config_id}` (`systemd.per_config: true`); доступен `vpn-worker` и `vpn-panel` (API delete / чтение journal через `logs`)
- Legacy: `xray_reality`, `xray_grpc`, … — если `systemd.per_config: false`

Действие `vpn-systemctl logs <vpn-uuid> [N]` отдаёт хвост `journalctl -u … -n N` (до 500 строк). UI: страница конфига → «Логи сервиса» (polling `GET /api/v1/configs/{id}/logs`; интервал 2/5/10/30 с или свой в мс, min 500). После обновления кода: `make render && sudo bash deploy/scripts/install-vpn-systemctl.sh` (или `sudo make update`).

При `systemd.per_config: true` воркер при create/regenerate:

1. Пишет live-конфиг в `/usr/local/etc/xray/configs/{config_id}/` или `/usr/local/etc/hysteria/configs/{config_id}/`
2. Создаёт `/etc/systemd/system/vpn-{config_id}.service`
3. Выполняет `daemon-reload`, `enable`, `restart`

При **delete** конфига API останавливает сервис, удаляет unit-файл и каталог live-конфига (через `vpn-systemctl remove-unit`).

После `restart` воркер ждёт, пока VPN действительно поднимется:

1. `systemctl`: `active` + `SubState=running`, пауза `service_ready_settle_seconds` (по умолчанию 2 с), повторная проверка
2. `journalctl`: строка с `started` (Xray) или `listening` (Hysteria2)

Если за `service_ready_timeout_seconds` (по умолчанию 30 с) сервис не готов — воркер повторяет проверку (heartbeat продлевает lock задачи) до `service_ready_max_wait_seconds` (по умолчанию **10 минут**). При падении systemd (`failed`, exit-code) — сразу `failed`. Если за 10 минут так и не готов — `failed`, конфиг не переходит в `active`.

Проверка:

```bash
sudo visudo -cf /etc/sudoers.d/vpn-worker
sudo -u vpn-worker sudo -n /usr/local/bin/vpn-systemctl daemon-reload
sudo systemctl restart vpn-worker@1
```

---

## Предварительные требования на сервере

1. **Python 3.10+** (ставится через `make deploy-deps`)
2. **PostgreSQL** — БД панели
3. **task-broker wheel** — не в PyPI, положите на сервер и укажите `VCP_TASK_BROKER_WHL`
4. **Xray / Hysteria2** — systemd-сервисы с именами из профилей
5. **Домен** (рекомендуется) для HTTPS

Порты **8000** и **8001** слушают только `127.0.0.1` — наружу открыт **80** (nginx, без TLS по умолчанию).

---

## Администраторы

Первый админ при деплое:

```bash
sudo make create-admin
```

Дополнительные админы (интерактивный пароль):

```bash
sudo make create-admin USERNAME=alice
# или
sudo bash deploy/scripts/create-admin.sh bob
sudo -u vpn-panel /opt/vpn-control-panel/.venv/bin/vpn-create-admin \
  --config /etc/vpn-control-panel/panel.yaml --username bob
```

---

## Regenerate всех конфигов

**UI:** кнопка «Regenerate all» на главной странице `/admin`.

**API:** `POST /api/v1/configs/regenerate-all` (Bearer auth).

**CLI / cron:**

```bash
sudo make regenerate-all
# или напрямую:
sudo bash deploy/scripts/regenerate-all-configs.sh
```

Скрипт только **ставит задачи в очередь**. Дата/версия на сайте обновляются после того, как `vpn-worker@*` их выполнит. Логи CLI: stdout (для cron — в файл ниже); прогресс воркера — `journalctl -u 'vpn-worker@*'`.

Пользователь для audit (`requested_by`): `VCP_CRON_ADMIN_USERNAME` в `deploy/.env` (по умолчанию `VCP_ADMIN_USERNAME`).

Конфиги в статусе `pending` / `processing` пропускаются.

**Важно:** формат `crontab -e` и `/etc/cron.d/` разный. В user crontab **нет** поля user — строка с `root` перед командой запускает несуществующую команду `root` и молча ничего не делает.

`crontab -e` от root (ежедневно в 04:00):

```cron
0 4 * * * cd /srv/VpnControlPanel && /bin/bash deploy/scripts/regenerate-all-configs.sh >> /var/log/vpn-panel-regenerate.log 2>&1
```

Или файл `/etc/cron.d/vpn-panel-regenerate` (здесь поле user нужно):

```cron
0 4 * * * root cd /srv/VpnControlPanel && /bin/bash deploy/scripts/regenerate-all-configs.sh >> /var/log/vpn-panel-regenerate.log 2>&1
```

Проверка:

```bash
sudo bash deploy/scripts/regenerate-all-configs.sh
tail -n 50 /var/log/vpn-panel-regenerate.log
# на сайте: номер версии и «Обновлён» / «Создана» у version должны сдвинуться после воркера
```

---

## Worker: параллелизм

Каждый воркер — **отдельный systemd instance** `vpn-worker@1`, `vpn-worker@2`, …

Число задаётся в **`deploy/.env`**:

```bash
VCP_WORKER_INSTANCES=2
```

Базовый `worker_id` для broker — из `panel.yaml` (`worker.worker_id`, по умолчанию `panel-worker-1`).  
Instance `@3` получает id **`panel-worker-1-3`**.

После изменения:

```bash
sudo make install-systemd
# или полный update:
sudo make update
```

Проверка:

```bash
make status
systemctl status vpn-worker@1 vpn-worker@2
sudo journalctl -u 'vpn-worker@*' -n 50 --no-pager
```

При уменьшении `VCP_WORKER_INSTANCES` лишние `@N` отключаются автоматически (`install-systemd` / `update`).

---

## Обновление версии

```bash
cd /opt/vpn-control-panel
sudo make update
```

Или без `git pull` / nginx:

```bash
sudo make update-quick
```

`make update` выполняет: `git pull`, `pip install`, перерендер `panel.yaml` из `deploy/.env`, миграции, systemd/sudoers, restart.

> **Не правьте `panel.yaml` вручную** — при каждом `make update` он пересоздаётся из шаблона `deploy/templates/panel.yaml.in` и переменных `deploy/.env`. Настройки VPN, probe, `public_host` и секреты — только в `.env`.
>
> **Не правьте файлы репозитория на сервере.** Скрипты запускаются через `bash deploy/scripts/...`, без `chmod` в tracked-файлах.

### Вручную

---

## Проверка после деплоя

```bash
make status

curl -s http://127.0.0.1:8000/health
# {"status":"ok"}

curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"..."}'
```

Чеклист:

- [ ] `vpn-broker`, `vpn-api`, `vpn-worker@*` — `active`
- [ ] Login в `/admin`
- [ ] Создание конфига → `pending` → `active`
- [ ] Файл в `VCP_VPN_CONFIGS_DIR/{uuid}/`
- [ ] Share-ссылка без auth

---

## Troubleshooting

| Симптом | Решение |
|---------|---------|
| Конфиг в `pending` | `journalctl -u 'vpn-worker@*'`; проверьте `broker.api_key` |
| `Job type reload is not applicable` | Xray не поддерживает reload — используйте `restart` в коде/sudoers (см. выше) |
| Порт в UI ≠ порт Xray | Задайте `active_config_path` в `panel.yaml` = путь из unit VPN-сервиса; `make update` |
| `sudo: command not allowed` / `COMMAND=reload` | В unit не в кавычках `VPN_SYSTEMCTL_CMD` → вызывается `sudo reload`. Исправьте unit, установите sudoers, см. ниже |
| `Permission denied: panel.yaml` | Worker не в группе `vpn-panel`: `sudo usermod -aG vpn-panel vpn-worker`, каталог conf `750 root:vpn-panel`, файл `640`; `make fix-config-perms` |
| `Permission denied: .../letsencrypt/.../fullchain.pem` | При `rotate_tls: false` worker читает `tls_*_file` профиля. `/etc/letsencrypt/live` и `archive` обычно `0700 root` — `vpn-worker` не проходит. Либо включите «Self-signed TLS» в политике, либо дайте доступ: `sudo chgrp -R ssl-cert /etc/letsencrypt/{live,archive}` && `sudo chmod 750 /etc/letsencrypt/{live,archive}` && `sudo chmod 640 /etc/letsencrypt/archive/*/privkey*.pem` && `sudo usermod -aG ssl-cert vpn-worker` && restart `vpn-worker@*` |
| `Permission denied: .../xray/tmp*` | Worker не может писать в каталог live-конфига Xray: `sudo make fix-config-perms` (каталог `/usr/local/etc/xray` → `770 root:vpn-panel`, конфиги `660`) |
| `Permission denied: /etc/systemd/system/tmp*` при regenerate | Старая версия писала unit-файлы без sudo. `sudo make update` (переустановит `vpn-systemctl` с `write-unit`) |
| `git pull` / `would be overwritten by merge` в `deploy/scripts/` | Старый `make update` менял права на скрипты. Один раз: `git checkout -- deploy/scripts/ && git pull`, затем `sudo make update` (новая версия не трогает index) |
| `failed` при create | Права на `VCP_VPN_CONFIGS_DIR`, sudoers для systemctl |
| nginx -t fail | Проверьте `deploy/output/nginx/vpn-panel.conf`; для SSL нужен `VCP_NGINX_SSL=1` и certbot |
| `invalid number of arguments in proxy_set_header` | Перерендерите nginx: `make render && sudo make install-nginx` (старый баг envsubst затирал `$host`) |
| `task-broker` not found | `VCP_TASK_BROKER_WHL` неверный путь |
| 401 в UI | JWT истёк — перелогин |

Логи:

```bash
make logs
journalctl -u 'vpn-worker@*' -n 100 --no-pager
```

---

## Полная переустановка (очистка)

Перед повторным `make deploy` удалите следы установки. В `deploy/.env` должны быть **актуальные пути** (у вас, например, `VCP_INSTALL_DIR=/srv/VpnControlPanel`, `VCP_CONFIG_DIR=/srv/VpnControlPanel/conf`).

### Автоматически

```bash
cd /srv/VpnControlPanel   # каталог с репозиторием и deploy/.env
sudo make uninstall       # удалит сервисы, nginx, sudoers, БД, конфиги, каталог установки
rm -f deploy/.env
make init-env             # новый .env
# отредактируйте deploy/.env
make deploy
```

Сохранить PostgreSQL (только сервисы и файлы):

```bash
sudo make uninstall-keep-db
```

### Вручную (если пути отличались от .env)

```bash
sudo systemctl stop vpn-api vpn-broker
sudo systemctl stop 'vpn-worker@*' 2>/dev/null || true
sudo systemctl disable vpn-api vpn-broker
sudo systemctl disable 'vpn-worker@*' 2>/dev/null || true
sudo rm -f /etc/systemd/system/vpn-worker@.service
sudo rm -f /etc/systemd/system/vpn-worker.service
sudo rm -f /etc/systemd/system/vpn-api.service
sudo rm -f /etc/systemd/system/vpn-broker.service
sudo systemctl daemon-reload
```

sudo rm -f /etc/nginx/sites-enabled/vpn-panel.conf /etc/nginx/sites-available/vpn-panel.conf
sudo nginx -t && sudo systemctl reload nginx

sudo rm -f /etc/sudoers.d/vpn-worker

sudo -u postgres psql -c "DROP DATABASE IF EXISTS vpn_panel;"
sudo -u postgres psql -c "DROP USER IF EXISTS vpn_panel;"

sudo rm -rf /var/lib/vpn-control-panel
sudo rm -rf /srv/VpnControlPanel/conf    # если конфиги здесь
sudo rm -rf /opt/vpn/configs/*
sudo userdel vpn-worker 2>/dev/null || true
sudo userdel vpn-panel 2>/dev/null || true

# опционально — полностью снести клон:
# sudo rm -rf /srv/VpnControlPanel
# git clone ... && cd ... && make init-env && make deploy
```

VPN-сервисы (xray, hysteria) и их конфиги **не удаляются** — только панель.

---

## Локальная разработка

Скрипты деплоя рассчитаны на Linux. Для dev используйте [README](../README.md#запуск-разработка):

```bash
pip install task_broker-*.whl
pip install -e ".[dev]"
cp panel.yaml.example panel.yaml
alembic upgrade head
vpn-create-admin --config panel.yaml --username admin
```

---

## Связанные файлы в репозитории

| Файл | Назначение |
|------|------------|
| `panel.yaml.example` | Dev-конфиг (reference) |
| `broker.yaml.example` | Dev broker |
| `configs/` | Шаблоны Xray/Hysteria2 |
| `Makefile` | Точка входа автоматизации |
