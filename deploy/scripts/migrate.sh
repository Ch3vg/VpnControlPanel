#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_root
load_env

sudo -u "${VCP_PANEL_USER}" bash -c "
  set -euo pipefail
  cd '${VCP_INSTALL_DIR}'
  export PANEL_CONFIG_PATH='${VCP_CONFIG_DIR}/panel.yaml'
  .venv/bin/alembic upgrade head
"

log "Database migrations applied"
