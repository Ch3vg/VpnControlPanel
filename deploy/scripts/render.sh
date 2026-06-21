#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

load_env

mkdir -p "${OUTPUT_DIR}/systemd" "${OUTPUT_DIR}/nginx" "${OUTPUT_DIR}/bin"

render_template "${DEPLOY_DIR}/templates/broker.yaml.in" "${OUTPUT_DIR}/broker.yaml"
render_template "${DEPLOY_DIR}/templates/panel.yaml.in" "${OUTPUT_DIR}/panel.yaml"
render_template "${DEPLOY_DIR}/templates/systemd/vpn-broker.service.in" "${OUTPUT_DIR}/systemd/vpn-broker.service"
render_template "${DEPLOY_DIR}/templates/systemd/vpn-api.service.in" "${OUTPUT_DIR}/systemd/vpn-api.service"
render_template "${DEPLOY_DIR}/templates/systemd/vpn-worker.service.in" "${OUTPUT_DIR}/systemd/vpn-worker.service"
cp "${DEPLOY_DIR}/templates/bin/vpn-systemctl.sh" "${OUTPUT_DIR}/bin/vpn-systemctl"
chmod 755 "${OUTPUT_DIR}/bin/vpn-systemctl"
if [[ "${VCP_NGINX_SSL:-0}" == "1" || "${VCP_NGINX_SSL:-0}" == "true" ]]; then
  render_template "${DEPLOY_DIR}/templates/nginx/vpn-panel.ssl.conf.in" "${OUTPUT_DIR}/nginx/vpn-panel.conf" \
    '$VCP_PANEL_DOMAIN $VCP_API_HOST $VCP_API_PORT'
else
  render_template "${DEPLOY_DIR}/templates/nginx/vpn-panel.conf.in" "${OUTPUT_DIR}/nginx/vpn-panel.conf" \
    '$VCP_PANEL_DOMAIN $VCP_API_HOST $VCP_API_PORT'
fi
render_template "${DEPLOY_DIR}/templates/sudoers/vpn-worker.in" "${OUTPUT_DIR}/sudoers/vpn-worker"

log "All templates rendered to ${OUTPUT_DIR}/"
