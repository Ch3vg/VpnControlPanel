#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_root
load_env

if ! id "${VCP_PANEL_USER}" &>/dev/null; then
  useradd --system --home "${VCP_INSTALL_DIR}" --shell /usr/sbin/nologin "${VCP_PANEL_USER}"
  log "Created user ${VCP_PANEL_USER}"
fi

if ! id "${VCP_WORKER_USER}" &>/dev/null; then
  useradd --system --home "${VCP_INSTALL_DIR}" --shell /usr/sbin/nologin "${VCP_WORKER_USER}"
  log "Created user ${VCP_WORKER_USER}"
fi

# Worker must read panel.yaml (group-readable, owned root:vpn-panel).
usermod -aG "${VCP_PANEL_USER}" "${VCP_WORKER_USER}"
log "Added ${VCP_WORKER_USER} to group ${VCP_PANEL_USER}"

mkdir -p "${VCP_CONFIG_DIR}" "${VCP_DATA_DIR}" "${VCP_VPN_CONFIGS_DIR}" "${VCP_INSTALL_DIR}"
chown "${VCP_PANEL_USER}:${VCP_PANEL_USER}" "${VCP_DATA_DIR}"
chown "${VCP_WORKER_USER}:${VCP_WORKER_USER}" "${VCP_VPN_CONFIGS_DIR}"
fix_vpn_live_dirs

log "Users and directories ready"
