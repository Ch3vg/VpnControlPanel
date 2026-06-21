#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_root
load_env

usermod -aG "${VCP_PANEL_USER}" "${VCP_WORKER_USER}"

fix_vpn_live_dirs

install -d -m 750 -o root -g "${VCP_PANEL_USER}" "${VCP_CONFIG_DIR}"
if [[ -f "${VCP_CONFIG_DIR}/panel.yaml" ]]; then
  chown root:"${VCP_PANEL_USER}" "${VCP_CONFIG_DIR}/panel.yaml"
  chmod 640 "${VCP_CONFIG_DIR}/panel.yaml"
fi
if [[ -f "${VCP_CONFIG_DIR}/broker.yaml" ]]; then
  chown root:"${VCP_PANEL_USER}" "${VCP_CONFIG_DIR}/broker.yaml"
  chmod 640 "${VCP_CONFIG_DIR}/broker.yaml"
fi

log "Config permissions fixed (${VCP_CONFIG_DIR}: 750 root:${VCP_PANEL_USER}, *.yaml: 640; live VPN dirs: 770 root:${VCP_PANEL_USER})"
