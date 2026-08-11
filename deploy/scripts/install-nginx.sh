#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_root
load_env

bash "${SCRIPT_DIR}/render.sh"

install -m 644 "${OUTPUT_DIR}/nginx/vpn-panel.conf" "/etc/nginx/sites-available/vpn-panel.conf"
ln -sf /etc/nginx/sites-available/vpn-panel.conf /etc/nginx/sites-enabled/vpn-panel.conf

SHARED="${VCP_NGINX_SHARED_443:-0}"
if [[ "${SHARED}" == "1" || "${SHARED}" == "true" ]]; then
  bash "${SCRIPT_DIR}/ensure-nginx-stream.sh"
  mkdir -p /etc/nginx/stream.d
  if [[ -f "${OUTPUT_DIR}/nginx/vcp-shared-443.stream.conf" ]]; then
    install -m 644 "${OUTPUT_DIR}/nginx/vcp-shared-443.stream.conf" \
      /etc/nginx/stream.d/vcp-shared-443.conf
  else
    die "shared 443 enabled but ${OUTPUT_DIR}/nginx/vcp-shared-443.stream.conf missing — run render"
  fi
else
  rm -f /etc/nginx/stream.d/vcp-shared-443.conf
fi

if nginx -t; then
  systemctl reload nginx
  if [[ "${SHARED}" == "1" || "${SHARED}" == "true" ]]; then
    log "Nginx installed with shared TCP 443 (SNI mux). Reality backend=${VCP_REALITY_BACKEND:-unset}"
  else
    log "Nginx config installed (run certbot if TLS certs are missing)"
  fi
else
  die "nginx -t failed — install TLS certs or adjust ${OUTPUT_DIR}/nginx/vpn-panel.conf"
fi
