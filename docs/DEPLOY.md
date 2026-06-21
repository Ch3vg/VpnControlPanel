# Деплой VPN Control Panel

Production-деплой на **Debian/Ubuntu** с автоматизацией через `Makefile` и скрипты в `deploy/scripts/`.

## Архитектура

```
Internet → Nginx (TLS) → vpn-api :8000
                              ↓
                         PostgreSQL
                              ↓
vpn-broker :8001 ← vpn-worker (файлы + systemctl reload)
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
│       └── vpn-worker.in       # NOPASSWD systemctl reload
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

## TLS (Let's Encrypt)

Nginx-шаблон ожидает сертификаты certbot. **Перед** `make install-nginx` или после `--skip-nginx`:

```bash
apt install certbot python3-certbot-nginx
certbot certonly --nginx -d panel.example.com
make install-nginx
```

Либо временно закомментируйте SSL-блок в `deploy/output/nginx/vpn-panel.conf` для первого запуска API на localhost.

---

## Worker и systemctl

Worker перезагружает VPN-сервисы через:

```bash
VPN_SYSTEMCTL_CMD="sudo -n /bin/systemctl"
```

Это задано в `vpn-worker.service.in`. Sudoers-шаблон разрешает reload для:

- `xray_reality`, `xray_grpc`, `xray_xhttp`, `xray_client`
- `hysteria-server`

Имена должны совпадать с `vpn.profiles.*.service_name` в `panel.yaml`.

Проверка:

```bash
sudo -u vpn-worker sudo -n /bin/systemctl reload xray_reality
```

---

## Предварительные требования на сервере

1. **Python 3.10+** (ставится через `make deploy-deps`)
2. **PostgreSQL** — БД панели
3. **task-broker wheel** — не в PyPI, положите на сервер и укажите `VCP_TASK_BROKER_WHL`
4. **Xray / Hysteria2** — systemd-сервисы с именами из профилей
5. **Домен** (рекомендуется) для HTTPS

Порты **8000** и **8001** слушают только `127.0.0.1` — наружу открыт **443** (nginx).

---

## Обновление версии

```bash
cd /opt/vpn-control-panel
git pull
sudo make install-app
sudo make migrate
sudo make setup-config   # если менялись шаблоны
sudo make restart
```

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
| `failed` при create | Права на `VCP_VPN_CONFIGS_DIR`, sudoers для systemctl |
| nginx -t fail | Нет TLS-сертификатов — certbot или `--skip-nginx` |
| `task-broker` not found | `VCP_TASK_BROKER_WHL` неверный путь |
| 401 в UI | JWT истёк — перелогин |

Логи:

```bash
make logs
journalctl -u vpn-worker -n 100 --no-pager
```

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
