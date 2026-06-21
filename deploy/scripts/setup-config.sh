#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_root
load_env

bash "${SCRIPT_DIR}/render.sh"

install -d -m 750 -o root -g "${VCP_PANEL_USER}" "${VCP_CONFIG_DIR}"
install -m 640 -o root -g "${VCP_PANEL_USER}" "${OUTPUT_DIR}/panel.yaml" "${VCP_CONFIG_DIR}/panel.yaml"
install -m 640 -o root -g "${VCP_PANEL_USER}" "${OUTPUT_DIR}/broker.yaml" "${VCP_CONFIG_DIR}/broker.yaml"

log "Configs installed to ${VCP_CONFIG_DIR}"
