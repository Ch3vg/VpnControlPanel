#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEPLOY_DIR="${REPO_ROOT}/deploy"
ENV_FILE="${DEPLOY_DIR}/.env"
OUTPUT_DIR="${DEPLOY_DIR}/output"

log() {
  printf '[deploy] %s\n' "$*"
}

die() {
  printf '[deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    die "Run as root (sudo make deploy)"
  fi
}

load_env() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    die "Missing ${ENV_FILE}. Run: cp deploy/env.example deploy/.env"
  fi
  # shellcheck disable=SC1090
  set -a
  source "${ENV_FILE}"
  set +a

  : "${VCP_INSTALL_DIR:?VCP_INSTALL_DIR is required}"
  : "${VCP_CONFIG_DIR:?VCP_CONFIG_DIR is required}"
  : "${VCP_DATA_DIR:?VCP_DATA_DIR is required}"
  : "${VCP_VPN_CONFIGS_DIR:?VCP_VPN_CONFIGS_DIR is required}"
  : "${VCP_PANEL_USER:?VCP_PANEL_USER is required}"
  : "${VCP_WORKER_USER:?VCP_WORKER_USER is required}"
  : "${VCP_DB_NAME:?VCP_DB_NAME is required}"
  : "${VCP_DB_USER:?VCP_DB_USER is required}"
  : "${VCP_PUBLIC_HOST:?VCP_PUBLIC_HOST is required}"
  : "${VCP_PANEL_DOMAIN:?VCP_PANEL_DOMAIN is required}"
}

venv_python() {
  echo "${VCP_INSTALL_DIR}/.venv/bin/python"
}

venv_bin() {
  echo "${VCP_INSTALL_DIR}/.venv/bin/$1"
}

render_template() {
  local template="$1"
  local output="$2"
  local envsubst_vars="${3:-}"
  mkdir -p "$(dirname "${output}")"
  if [[ -n "${envsubst_vars}" ]]; then
    envsubst "${envsubst_vars}" < "${template}" > "${output}"
  else
    envsubst < "${template}" > "${output}"
  fi
  log "Rendered $(basename "${output}")"
}

update_env_var() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" "${ENV_FILE}"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
  else
    echo "${key}=${value}" >> "${ENV_FILE}"
  fi
}
