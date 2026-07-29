#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
load_env

: "${VCP_CRON_ADMIN_USERNAME:=${VCP_ADMIN_USERNAME:-admin}}"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log_msg() { printf '[%s] %s\n' "$(ts)" "$*"; }

log_msg "start regenerate-all (admin=${VCP_CRON_ADMIN_USERNAME} install=${VCP_INSTALL_DIR})"

if [[ ! -x "$(venv_bin vpn-regenerate-all)" ]]; then
  log_msg "ERROR: missing $(venv_bin vpn-regenerate-all)"
  exit 1
fi
if [[ ! -f "${VCP_CONFIG_DIR}/panel.yaml" ]]; then
  log_msg "ERROR: missing ${VCP_CONFIG_DIR}/panel.yaml"
  exit 1
fi

if command -v systemctl >/dev/null 2>&1; then
  for unit in vpn-broker vpn-worker@1; do
    if systemctl is-active --quiet "${unit}" 2>/dev/null; then
      log_msg "ok ${unit} is active"
    else
      log_msg "WARNING: ${unit} is not active — tasks may stay queued"
    fi
  done
fi

cmd=(
  "$(venv_bin vpn-regenerate-all)"
  --config "${VCP_CONFIG_DIR}/panel.yaml"
  --username "${VCP_CRON_ADMIN_USERNAME}"
)

set +e
if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
  sudo -u "${VCP_PANEL_USER}" env PANEL_CONFIG_PATH="${VCP_CONFIG_DIR}/panel.yaml" "${cmd[@]}"
  rc=$?
else
  env PANEL_CONFIG_PATH="${VCP_CONFIG_DIR}/panel.yaml" "${cmd[@]}"
  rc=$?
fi
set -e

if [[ "${rc}" -ne 0 ]]; then
  log_msg "ERROR: vpn-regenerate-all exited with ${rc}"
  exit "${rc}"
fi

log_msg "done (queued tasks; UI dates update after vpn-worker finishes)"
exit 0
