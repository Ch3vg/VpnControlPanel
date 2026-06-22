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

  VCP_CONNECTIVITY_PROBE_ENABLED="${VCP_CONNECTIVITY_PROBE_ENABLED:-true}"
  VCP_CONNECTIVITY_PROBE_TIMEOUT_SECONDS="${VCP_CONNECTIVITY_PROBE_TIMEOUT_SECONDS:-12}"
  VCP_CONNECTIVITY_PROBE_CACHE_SECONDS="${VCP_CONNECTIVITY_PROBE_CACHE_SECONDS:-60}"
  VCP_CONNECTIVITY_PROBE_URL="${VCP_CONNECTIVITY_PROBE_URL:-https://www.cloudflare.com/cdn-cgi/trace}"
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

# Live VPN config dirs (active_config_path targets) must allow vpn-worker (group vpn-panel)
# to create temp files and atomically replace configs.
fix_vpn_live_dirs() {
  local cert_dir xray_dir hysteria_dir
  cert_dir="${VCP_CERT_DIR:-/usr/local/etc/xray/certs}"
  xray_dir="$(dirname "${cert_dir}")"
  hysteria_dir="${VCP_HYSTERIA_CONFIG_DIR:-/usr/local/etc/hysteria}"

  install -d -m 770 -o root -g "${VCP_PANEL_USER}" "${xray_dir}" "${hysteria_dir}" "${cert_dir}"
  install -d -m 770 -o root -g "${VCP_PANEL_USER}" "${xray_dir}/configs" "${hysteria_dir}/configs"

  find "${xray_dir}" -maxdepth 1 -type f \( -name '*.json' -o -name '*.yaml' \) \
    -exec chown root:"${VCP_PANEL_USER}" {} \; -exec chmod 660 {} \; 2>/dev/null || true

  find "${hysteria_dir}" -maxdepth 1 -type f -name '*.yaml' \
    -exec chown root:"${VCP_PANEL_USER}" {} \; -exec chmod 660 {} \; 2>/dev/null || true

  find "${cert_dir}" -type f -exec chown root:"${VCP_PANEL_USER}" {} \; -exec chmod 640 {} \; 2>/dev/null || true
  find "${cert_dir}" -type l -exec chown -h root:"${VCP_PANEL_USER}" {} \; 2>/dev/null || true
}

worker_instances() {
  local count="${VCP_WORKER_INSTANCES:-1}"
  if ! [[ "${count}" =~ ^[0-9]+$ ]] || [[ "${count}" -lt 1 ]]; then
    die "VCP_WORKER_INSTANCES must be a positive integer, got: ${count}"
  fi
  echo "${count}"
}

worker_for_each() {
  local action="$1"
  local count i
  count="$(worker_instances)"
  for ((i = 1; i <= count; i++)); do
    systemctl "${action}" "vpn-worker@${i}"
  done
}

install_worker_units() {
  install -m 644 "${OUTPUT_DIR}/systemd/vpn-worker@.service" /etc/systemd/system/vpn-worker@.service
  rm -f /etc/systemd/system/vpn-worker.service
}

sync_worker_units() {
  local count i
  count="$(worker_instances)"
  install_worker_units
  systemctl daemon-reload
  for ((i = count + 1; i <= 32; i++)); do
    systemctl stop "vpn-worker@${i}" 2>/dev/null || true
    systemctl disable "vpn-worker@${i}" 2>/dev/null || true
  done
  for ((i = 1; i <= count; i++)); do
    systemctl enable "vpn-worker@${i}"
    systemctl restart "vpn-worker@${i}"
  done
  log "Worker units: vpn-worker@1..${count}"
}

stop_worker_units() {
  local count i
  count="$(worker_instances)"
  for ((i = 1; i <= count; i++)); do
    systemctl stop "vpn-worker@${i}" 2>/dev/null || true
  done
  systemctl stop vpn-worker 2>/dev/null || true
}

stop_all_worker_units() {
  local i
  for ((i = 1; i <= 32; i++)); do
    systemctl stop "vpn-worker@${i}" 2>/dev/null || true
  done
  systemctl stop vpn-worker 2>/dev/null || true
}

disable_worker_units() {
  local count i
  count="$(worker_instances)"
  for ((i = 1; i <= count; i++)); do
    systemctl disable "vpn-worker@${i}" 2>/dev/null || true
  done
  systemctl disable vpn-worker 2>/dev/null || true
}

disable_all_worker_units() {
  local i
  for ((i = 1; i <= 32; i++)); do
    systemctl disable "vpn-worker@${i}" 2>/dev/null || true
  done
  systemctl disable vpn-worker 2>/dev/null || true
}
