#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_root
load_env

bash "${SCRIPT_DIR}/render.sh"

install -m 644 "${OUTPUT_DIR}/systemd/vpn-broker.service" /etc/systemd/system/vpn-broker.service
install -m 644 "${OUTPUT_DIR}/systemd/vpn-api.service" /etc/systemd/system/vpn-api.service

systemctl daemon-reload
systemctl enable vpn-broker vpn-api
systemctl restart vpn-broker vpn-api
sync_worker_units

log "systemd units enabled and started"
