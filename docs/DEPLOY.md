# Деплой VPN Control Panel

Production-деплой на **Debian/Ubuntu** с автоматизацией через `Makefile` и скрипты в `deploy/scripts/`.

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
│   │   └── vpn-worker.service.in
│   ├── nginx/
│   │   └── vpn-panel.conf.in
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
| `VCP_DB_*` | PostgreSQL | см. env.example |
| `VCP_JWT_SECRET` | JWT (≥32 символов) | auto `make secrets` |
| `VCP_ENCRYPTION_KEY` | Шифрование БД | auto |
| `VCP_BROKER_API_KEY` | API key брокера | auto |
| `VCP_TASK_BROKER_WHL` | Путь к wheel | **обязательно** |
| `VCP_PUBLIC_HOST` | IP/домен VPN-сервера | |
| `VCP_PANEL_DOMAIN` | Домен панели (nginx) | |
| `VCP_NGINX_SSL` | HTTPS :443 (`1`) или только HTTP :80 (`0`) | `0` |
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
make create-admin      # vpn-create-admin
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

Шаблон HTTPS: `deploy/templates/nginx/vpn-panel.ssl.conf.in` (редirect 80→443 + proxy на API).

---

## Worker и systemctl

Worker и API читают `panel.yaml` от пользователя `vpn-panel` (группа). Пользователь **`vpn-worker` добавлен в группу `vpn-panel`** и может читать конфиг при правах `640` на файле и `750` на каталоге.

Xray и Hysteria2 **не поддерживают** `systemctl reload` — worker вызывает **`restart`** (по умолчанию `VPN_SYSTEMCTL_ACTION=restart`).

```bash
VPN_SYSTEMCTL_CMD="sudo -n /bin/systemctl"
VPN_SYSTEMCTL_ACTION=restart
```

В `vpn-worker.service`:

```ini
Environment="VPN_SYSTEMCTL_CMD=sudo -n /bin/systemctl"
Environment=VPN_SYSTEMCTL_ACTION=restart
```

Sudoers (`/etc/sudoers.d/vpn-worker`, `make install-sudoers`):

- `xray_reality`, `xray_grpc`, `xray_xhttp`, `xray_client`
- `hysteria-server`

Имена должны совпадать с `vpn.profiles.*.service_name` в `panel.yaml`.

Проверка:

```bash
sudo visudo -cf /etc/sudoers.d/vpn-worker
sudo -u vpn-worker sudo -n /bin/systemctl restart xray_reality
sudo systemctl daemon-reload
sudo systemctl restart vpn-worker
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

## Обновление версии

```bash
cd /opt/vpn-control-panel
sudo make update
```

Или без `git pull` / nginx:

```bash
sudo make update-quick
```

`make update` выполняет: `git pull`, `pip install`, перерендер `panel.yaml`, миграции, systemd/sudoers, restart.

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

- [ ] `vpn-broker`, `vpn-api`, `vpn-worker` — `active`
- [ ] Login в `/admin`
- [ ] Создание конфига → `pending` → `active`
- [ ] Файл в `VCP_VPN_CONFIGS_DIR/{uuid}/`
- [ ] Share-ссылка без auth

---

## Troubleshooting

| Симптом | Решение |
|---------|---------|
| Конфиг в `pending` | `journalctl -u vpn-worker`; проверьте `broker.api_key` |
| `Job type reload is not applicable` | Xray не поддерживает reload — используйте `restart` в коде/sudoers (см. выше) |
| Порт в UI ≠ порт Xray | Задайте `active_config_path` в `panel.yaml` = путь из unit VPN-сервиса; `make update` |
| `sudo: command not allowed` / `COMMAND=reload` | В unit не в кавычках `VPN_SYSTEMCTL_CMD` → вызывается `sudo reload`. Исправьте unit, установите sudoers, см. ниже |
| `Permission denied: panel.yaml` | Worker не в группе `vpn-panel`: `sudo usermod -aG vpn-panel vpn-worker`, каталог conf `750 root:vpn-panel`, файл `640`; `make fix-config-perms` |
| `failed` при create | Права на `VCP_VPN_CONFIGS_DIR`, sudoers для systemctl |
| nginx -t fail | Проверьте `deploy/output/nginx/vpn-panel.conf`; для SSL нужен `VCP_NGINX_SSL=1` и certbot |
| `invalid number of arguments in proxy_set_header` | Перерендерите nginx: `make render && sudo make install-nginx` (старый баг envsubst затирал `$host`) |
| `task-broker` not found | `VCP_TASK_BROKER_WHL` неверный путь |
| 401 в UI | JWT истёк — перелогин |

Логи:

```bash
make logs
journalctl -u vpn-worker -n 100 --no-pager
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
sudo systemctl stop vpn-worker vpn-api vpn-broker
sudo systemctl disable vpn-worker vpn-api vpn-broker
sudo rm -f /etc/systemd/system/vpn-{worker,api,broker}.service
sudo systemctl daemon-reload

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
