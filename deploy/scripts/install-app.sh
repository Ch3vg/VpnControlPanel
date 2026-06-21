#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_root
load_env

REAL_INSTALL="$(readlink -f "${VCP_INSTALL_DIR}")"
REAL_REPO="$(readlink -f "${REPO_ROOT}")"

if [[ "${REAL_REPO}" != "${REAL_INSTALL}" ]]; then
  log "Syncing ${REAL_REPO} -> ${REAL_INSTALL}"
  rsync -a --delete \
    --exclude .venv \
    --exclude .git \
    --exclude deploy/.env \
    --exclude deploy/output \
    --exclude __pycache__ \
    "${REAL_REPO}/" "${REAL_INSTALL}/"
fi

if [[ ! -d "${VCP_INSTALL_DIR}/.venv" ]]; then
  python3 -m venv "${VCP_INSTALL_DIR}/.venv"
fi

"${VCP_INSTALL_DIR}/.venv/bin/pip" install --upgrade pip
"${VCP_INSTALL_DIR}/.venv/bin/pip" install "${VCP_TASK_BROKER_WHL}"
"${VCP_INSTALL_DIR}/.venv/bin/pip" install "${VCP_INSTALL_DIR}"

chown -R "${VCP_PANEL_USER}:${VCP_PANEL_USER}" "${VCP_INSTALL_DIR}"
log "Application installed to ${VCP_INSTALL_DIR}"
