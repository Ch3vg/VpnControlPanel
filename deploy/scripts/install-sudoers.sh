#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_root
load_env

bash "${SCRIPT_DIR}/render.sh"

install -m 440 "${OUTPUT_DIR}/sudoers/vpn-worker" /etc/sudoers.d/vpn-worker
visudo -cf /etc/sudoers.d/vpn-worker

log "sudoers installed for ${VCP_WORKER_USER}"
