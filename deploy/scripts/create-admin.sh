#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_root
load_env

: "${VCP_ADMIN_USERNAME:=admin}"

run_create_admin() {
  local -a cmd=(
    "$(venv_bin vpn-create-admin)"
    --config "${VCP_CONFIG_DIR}/panel.yaml"
    --username "${VCP_ADMIN_USERNAME}"
  )
  if [[ -n "${VCP_ADMIN_PASSWORD:-}" ]]; then
    cmd+=(--password "${VCP_ADMIN_PASSWORD}")
  fi
  sudo -u "${VCP_PANEL_USER}" env PANEL_CONFIG_PATH="${VCP_CONFIG_DIR}/panel.yaml" "${cmd[@]}"
}

if [[ -n "${VCP_ADMIN_PASSWORD:-}" ]]; then
  run_create_admin
else
  log "Create admin user ${VCP_ADMIN_USERNAME} (interactive password prompt)"
  run_create_admin
fi

log "Admin user ready"
