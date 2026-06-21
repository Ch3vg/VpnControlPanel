#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

NO_PULL=0
SKIP_NGINX=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-pull) NO_PULL=1 ;;
    --skip-nginx) SKIP_NGINX=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: update.sh [options]

  --no-pull      Skip git pull
  --skip-nginx   Skip nginx config reinstall
EOF
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

require_root
load_env

log "Updating VPN Control Panel at ${VCP_INSTALL_DIR}"

if [[ "${NO_PULL}" -eq 0 && -d "${VCP_INSTALL_DIR}/.git" ]]; then
  git -C "${VCP_INSTALL_DIR}" pull --ff-only
fi

bash "${SCRIPT_DIR}/install-app.sh"
bash "${SCRIPT_DIR}/setup-config.sh"
bash "${SCRIPT_DIR}/migrate.sh"
bash "${SCRIPT_DIR}/fix-config-perms.sh"
bash "${SCRIPT_DIR}/install-sudoers.sh"
bash "${SCRIPT_DIR}/install-systemd.sh"

if [[ "${SKIP_NGINX}" -eq 0 ]]; then
  bash "${SCRIPT_DIR}/install-nginx.sh" || log "nginx update skipped — check TLS/config manually"
fi

systemctl restart vpn-broker vpn-api vpn-worker

log "Update complete"
log "Admin UI: http://${VCP_PANEL_DOMAIN}/admin"
