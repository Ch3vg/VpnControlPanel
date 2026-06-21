#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
load_env

: "${VCP_CRON_ADMIN_USERNAME:=${VCP_ADMIN_USERNAME:-admin}}"

cmd=(
  "$(venv_bin vpn-regenerate-all)"
  --config "${VCP_CONFIG_DIR}/panel.yaml"
  --username "${VCP_CRON_ADMIN_USERNAME}"
)

if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
  sudo -u "${VCP_PANEL_USER}" env PANEL_CONFIG_PATH="${VCP_CONFIG_DIR}/panel.yaml" "${cmd[@]}"
else
  env PANEL_CONFIG_PATH="${VCP_CONFIG_DIR}/panel.yaml" "${cmd[@]}"
fi
