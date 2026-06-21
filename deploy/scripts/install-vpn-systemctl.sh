#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_root
load_env

bash "${SCRIPT_DIR}/render.sh"

install -m 755 "${OUTPUT_DIR}/bin/vpn-systemctl" /usr/local/bin/vpn-systemctl
log "Installed /usr/local/bin/vpn-systemctl"
