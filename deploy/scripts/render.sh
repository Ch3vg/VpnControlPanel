#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

load_env

mkdir -p "${OUTPUT_DIR}/systemd" "${OUTPUT_DIR}/nginx" "${OUTPUT_DIR}/bin" "${OUTPUT_DIR}/sudoers"

render_template "${DEPLOY_DIR}/templates/broker.yaml.in" "${OUTPUT_DIR}/broker.yaml"
render_template "${DEPLOY_DIR}/templates/panel.yaml.in" "${OUTPUT_DIR}/panel.yaml"
render_template "${DEPLOY_DIR}/templates/systemd/vpn-broker.service.in" "${OUTPUT_DIR}/systemd/vpn-broker.service"
render_template "${DEPLOY_DIR}/templates/systemd/vpn-api.service.in" "${OUTPUT_DIR}/systemd/vpn-api.service"
render_template "${DEPLOY_DIR}/templates/systemd/vpn-worker@.service.in" "${OUTPUT_DIR}/systemd/vpn-worker@.service"
cp "${DEPLOY_DIR}/templates/bin/vpn-systemctl.sh" "${OUTPUT_DIR}/bin/vpn-systemctl"
chmod 755 "${OUTPUT_DIR}/bin/vpn-systemctl"

SHARED="${VCP_NGINX_SHARED_443:-0}"
if [[ "${SHARED}" == "1" || "${SHARED}" == "true" ]]; then
  : "${VCP_REALITY_BACKEND:=127.0.0.1:10443}"
  : "${VCP_PANEL_TLS_BACKEND:=127.0.0.1:8443}"
  : "${VCP_REALITY_SNI_LIST:=ya.ru,vk.com,gosuslugi.ru,pochta.ru}"
  : "${VCP_PANEL_TLS_CERT:=/etc/letsencrypt/live/${VCP_PANEL_DOMAIN}/fullchain.pem}"
  : "${VCP_PANEL_TLS_KEY:=/etc/letsencrypt/live/${VCP_PANEL_DOMAIN}/privkey.pem}"
  # Space-separated hostnames for nginx server_name (primary + legacy aliases).
  : "${VCP_PANEL_SERVER_NAMES:=${VCP_PANEL_DOMAIN}}"
  export VCP_PANEL_TLS_CERT VCP_PANEL_TLS_KEY VCP_PANEL_TLS_BACKEND VCP_REALITY_BACKEND
  export VCP_PANEL_SERVER_NAMES

  render_template "${DEPLOY_DIR}/templates/nginx/vpn-panel.shared443.conf.in" "${OUTPUT_DIR}/nginx/vpn-panel.conf" \
    '$VCP_PANEL_SERVER_NAMES $VCP_API_HOST $VCP_API_PORT $VCP_PANEL_TLS_CERT $VCP_PANEL_TLS_KEY'

  map_lines=""
  # Panel aliases (comma-separated) also route to panel TLS backend.
  IFS=',' read -ra _panel_list <<< "${VCP_PANEL_DOMAIN_ALIASES:-}"
  panel_map_lines="    ${VCP_PANEL_DOMAIN} ${VCP_PANEL_TLS_BACKEND};"$'\n'
  for sni in "${_panel_list[@]}"; do
    sni="$(echo "${sni}" | tr -d '[:space:]')"
    [[ -z "${sni}" || "${sni}" == "${VCP_PANEL_DOMAIN}" ]] && continue
    panel_map_lines+="    ${sni} ${VCP_PANEL_TLS_BACKEND};"$'\n'
  done

  IFS=',' read -ra _sni_list <<< "${VCP_REALITY_SNI_LIST}"
  for sni in "${_sni_list[@]}"; do
    sni="$(echo "${sni}" | tr -d '[:space:]')"
    [[ -z "${sni}" ]] && continue
    if [[ "${sni}" == "${VCP_PANEL_DOMAIN}" ]]; then
      continue
    fi
    skip=0
    for psni in "${_panel_list[@]}"; do
      psni="$(echo "${psni}" | tr -d '[:space:]')"
      if [[ "${sni}" == "${psni}" ]]; then
        skip=1
        break
      fi
    done
    [[ "${skip}" == "1" ]] && continue
    map_lines+="    ${sni} ${VCP_REALITY_BACKEND};"$'\n'
  done

  stream_out="${OUTPUT_DIR}/nginx/vcp-shared-443.stream.conf"
  export VCP_STREAM_MAP_LINES="${panel_map_lines}${map_lines}"
  export VCP_STREAM_OUT="${stream_out}"
  export VCP_STREAM_TEMPLATE="${DEPLOY_DIR}/templates/nginx/vcp-shared-443.stream.conf.in"
  python3 - <<'PY'
import os
from pathlib import Path
template = Path(os.environ["VCP_STREAM_TEMPLATE"]).read_text()
# Template has a single __VCP_PANEL_DOMAIN__ line; replace with full panel+reality map body.
text = template
# Drop the single panel line placeholder and inject combined map lines instead.
text = text.replace(
    "    __VCP_PANEL_DOMAIN__ __VCP_PANEL_TLS_BACKEND__;\n__VCP_REALITY_SNI_MAP_LINES__",
    os.environ.get("VCP_STREAM_MAP_LINES", "").rstrip("\n"),
)
text = (
    text
    .replace("__VCP_PANEL_DOMAIN__", os.environ["VCP_PANEL_DOMAIN"])
    .replace("__VCP_PANEL_TLS_BACKEND__", os.environ["VCP_PANEL_TLS_BACKEND"])
    .replace("__VCP_REALITY_BACKEND__", os.environ["VCP_REALITY_BACKEND"])
    .replace("__VCP_REALITY_SNI_MAP_LINES__", os.environ.get("VCP_STREAM_MAP_LINES", "").rstrip("\n"))
)
Path(os.environ["VCP_STREAM_OUT"]).write_text(text)
print("Rendered", os.environ["VCP_STREAM_OUT"])
PY
  unset VCP_STREAM_MAP_LINES VCP_STREAM_OUT VCP_STREAM_TEMPLATE
elif [[ "${VCP_NGINX_SSL:-0}" == "1" || "${VCP_NGINX_SSL:-0}" == "true" ]]; then
  rm -f "${OUTPUT_DIR}/nginx/vcp-shared-443.stream.conf"
  render_template "${DEPLOY_DIR}/templates/nginx/vpn-panel.ssl.conf.in" "${OUTPUT_DIR}/nginx/vpn-panel.conf" \
    '$VCP_PANEL_DOMAIN $VCP_API_HOST $VCP_API_PORT'
else
  rm -f "${OUTPUT_DIR}/nginx/vcp-shared-443.stream.conf"
  render_template "${DEPLOY_DIR}/templates/nginx/vpn-panel.conf.in" "${OUTPUT_DIR}/nginx/vpn-panel.conf" \
    '$VCP_PANEL_DOMAIN $VCP_API_HOST $VCP_API_PORT'
fi
render_template "${DEPLOY_DIR}/templates/sudoers/vpn-worker.in" "${OUTPUT_DIR}/sudoers/vpn-worker"

log "All templates rendered to ${OUTPUT_DIR}/"
