#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

SKIP_DEPS=0
SKIP_NGINX=0
SKIP_ADMIN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-deps) SKIP_DEPS=1 ;;
    --skip-nginx) SKIP_NGINX=1 ;;
    --skip-admin) SKIP_ADMIN=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: deploy.sh [options]

  --skip-deps    Skip apt package installation
  --skip-nginx   Skip nginx site installation
  --skip-admin   Skip admin user creation
EOF
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

require_root
load_env

log "Starting VPN Control Panel deploy"
log "Install dir: ${VCP_INSTALL_DIR}"

if [[ "${SKIP_DEPS}" -eq 0 ]]; then
  bash "${SCRIPT_DIR}/install-deps.sh"
fi

bash "${SCRIPT_DIR}/generate-secrets.sh"
bash "${SCRIPT_DIR}/setup-users.sh"
bash "${SCRIPT_DIR}/setup-postgres.sh"
bash "${SCRIPT_DIR}/install-app.sh"
bash "${SCRIPT_DIR}/setup-config.sh"
bash "${SCRIPT_DIR}/migrate.sh"

if [[ "${SKIP_ADMIN}" -eq 0 ]]; then
  bash "${SCRIPT_DIR}/create-admin.sh"
fi

bash "${SCRIPT_DIR}/install-sudoers.sh"
bash "${SCRIPT_DIR}/install-vpn-systemctl.sh"
bash "${SCRIPT_DIR}/fix-config-perms.sh"
bash "${SCRIPT_DIR}/install-systemd.sh"

if [[ "${SKIP_NGINX}" -eq 0 ]]; then
  bash "${SCRIPT_DIR}/install-nginx.sh" || log "Nginx skipped/failed — configure TLS manually"
fi

log "Deploy complete"
log "Admin UI: http://${VCP_PANEL_DOMAIN}/admin"
if [[ "${VCP_NGINX_SSL:-0}" == "1" || "${VCP_NGINX_SSL:-0}" == "true" ]]; then
  log "Admin UI (TLS): https://${VCP_PANEL_DOMAIN}/admin"
fi
log "Check: make status"
