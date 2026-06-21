#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

KEEP_DB=0
KEEP_INSTALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-db) KEEP_DB=1 ;;
    --keep-install) KEEP_INSTALL=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: uninstall.sh [options]

  --keep-db        Do not drop PostgreSQL role/database
  --keep-install   Do not remove VCP_INSTALL_DIR (git clone / venv)
EOF
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

require_root
load_env

log "Stopping services"
systemctl stop vpn-worker vpn-api vpn-broker 2>/dev/null || true
systemctl disable vpn-worker vpn-api vpn-broker 2>/dev/null || true

log "Removing systemd units"
rm -f /etc/systemd/system/vpn-worker.service
rm -f /etc/systemd/system/vpn-api.service
rm -f /etc/systemd/system/vpn-broker.service
systemctl daemon-reload

log "Removing nginx site"
rm -f /etc/nginx/sites-enabled/vpn-panel.conf
rm -f /etc/nginx/sites-available/vpn-panel.conf
nginx -t && systemctl reload nginx || true

log "Removing sudoers"
rm -f /etc/sudoers.d/vpn-worker

if [[ "${KEEP_DB}" -eq 0 ]]; then
  log "Dropping PostgreSQL database ${VCP_DB_NAME}"
  sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL || true
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${VCP_DB_NAME}' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS ${VCP_DB_NAME};
DROP USER IF EXISTS ${VCP_DB_USER};
SQL
fi

log "Removing runtime data"
rm -rf "${VCP_DATA_DIR}"
rm -rf "${VCP_CONFIG_DIR}"
rm -rf "${VCP_VPN_CONFIGS_DIR}"/*
rm -rf "${DEPLOY_DIR}/output"

if [[ "${KEEP_INSTALL}" -eq 0 && -d "${VCP_INSTALL_DIR}" ]]; then
  log "Removing ${VCP_INSTALL_DIR}"
  rm -rf "${VCP_INSTALL_DIR}"
fi

if id "${VCP_WORKER_USER}" &>/dev/null; then
  userdel "${VCP_WORKER_USER}" 2>/dev/null || true
fi
if id "${VCP_PANEL_USER}" &>/dev/null; then
  userdel "${VCP_PANEL_USER}" 2>/dev/null || true
fi

log "Uninstall complete"
log "Optional: remove deploy/.env secrets and re-run make init-env before redeploy"
